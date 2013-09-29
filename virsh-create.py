#!/usr/bin/env python

from __future__ import unicode_literals

import argparse
import glob
import os
import sys

from libvirtpy.conn import conn
from libvirtpy.constants import DOMAIN_STATUS_SHUTOFF

from util import lvm
from util import settings
from util.cli import ex
from util.cli import chroot

parser = argparse.ArgumentParser()
# optional arguments:
parser.add_argument('-f', '--from', nargs=1, default="wheezy", metavar='VM',
                    dest='frm',
                    help="Virtual machine to clone from (Default: %(default)s)")
parser.add_argument('--desc', default='',
                   help="Description for the new virtual machine")
parser.add_argument('--mem', default=1.0, type=float,
                    help="Amount of Memory in GigaByte (Default: %(default)s))")
parser.add_argument('--cpus', default=1, type=int,
                    help="Number of CPUs (Default: %(default)s)")
parser.add_argument('--verbose', default=False, action="store_true",
                    help="Print executed commands to stdout.")

parser.add_argument('name', help="Name of the new virtual machine")
parser.add_argument(
    'id', type=int, help="Id of the virtual machine. Used for VNC-port, MAC-address and IP")
args = parser.parse_args()

# set a few global settings.
settings.VERBOSE = args.verbose

###########################
### Variable definition ###
###########################
# define some variables
lv_name = 'vm_%s' % args.name
ipv4 = '128.130.95.%s' % args.id
ipv6 = '2001:629:3200:95::1:%s' % args.id
ipv4_priv = '192.168.1.%s' % args.id
ipv6_priv = 'fc00::%s' % args.id
vncport = int('59%s' % args.id)

##########################
### BASIC SANITY TESTS ###
##########################
if os.getuid() != 0:  # check if we are root
    print('Error: You need to be root to create a virtual machine.')
    sys.exit(1)
if os.path.exists(settings.CHROOT):
    print('Error: %s: chroot target exists.' % settings.CHROOT)
    sys.exit(1)

#############################
### LIBVIRT SANITY CHECKS ###
#############################
# get template domain:
template = conn.getDomain(name=args.frm)
if template.status != DOMAIN_STATUS_SHUTOFF:
    print("Error: VM '%s' is not shut off" % args.frm)
    sys.exit(1)
template_id = template.domain_id  # i.e. 89.

# check if domain is already defined
if args.name in [d.name for d in conn.getAllDomains()]:
    print("Error: Domain already defined.")
    sys.exit(1)
bootdisk_path = '/dev/%s' % template.getBootDisk()  # i.e. /dev/vda

if os.path.exists(bootdisk_path):
    print("Error: %s already exists" % bootdisk_path)
    sys.exit(1)

##########################
### LVM SANITIY CHECKS ###
##########################
# get a list of logical volumes (so we can verify it doesn't exist yet)
lvs = {(lv.vg, lv.name): lv for lv in lvm.lvs()}  # list of all logical volumes

# Create mappings from template LVMs to target LVMs, check if they exist
lv_mapping = {}
for path in template.getDiskPaths():
    lv = lvm.lvdisplay(path)

    new_lv_name = lv.name.replace(template.name, args.name)
    if (lv.vg, new_lv_name) in lvs:
        print("Error: LV %s in VG %s is already defined." % (new_lv_name, lv.vg))
        sys.exit(1)
    lv_mapping[(lv.vg, lv.name)] = (lv.vg, new_lv_name)

#####################
### COPY TEMPLATE ###
#####################
# finally get the full xml of the template
domain = template.copy()
domain.name = args.name
domain.uuid = ''
domain.description = args.desc
domain.vcpu = args.cpus
domain.memory = int(args.mem * 1024 * 1024)
domain.currentMemory = int(args.mem * 1024 * 1024)
domain.vncport = vncport
domain.fix_macs(args.id)

# 2013-07-21: Virtual Functions are currently disabled
#vf = conn.getVirtualFunction()
#domain.setVirtualFunction(*vf)

##################
### Copy disks ###
##################
for path in template.getDiskPaths():
    # create logical volume
    lv = lvm.lvdisplay(path)
    new_vg, new_lv = lv_mapping[(lv.vg, lv.name)]
    new_path = path.replace(lv.name, new_lv)
    lvm.lvcreate(new_vg, new_lv, lv.size)

    # replace disk in template
    domain.replaceDisk(path, new_path)

    # copy data
    ex(['dd', 'if=%s' % path, 'of=%s' % new_path, 'bs=4M'], desc='Copy disc')

#############################
### MOUNT ROOT FILESYSTEM ###
#############################
bootdisk = domain.getBootDisk()
root_vg = 'vm_%s' % args.name
os.makedirs(settings.CHROOT)
mounted = []

ex(['kpartx', '-a', bootdisk], desc='Discover partitions on bootdisk')
ex(['vgrename', 'vm_%s' % args.frm, root_vg], desc='Rename volume group')
ex(['vgchange', '-a', 'y', root_vg], desc='Activate volume group')

print('# Mount filesystems')
ex(['mount', '/dev/%s/root' % root_vg, settings.CHROOT])
mounted.append(settings.CHROOT)
for dir in ['boot', 'home', 'usr', 'var', 'tmp']:
    dev = '/dev/%s/%s' % (root_vg, dir)
    if os.path.exists(dev):
        mytarget = '%s/%s' % (settings.CHROOT, dir)
        ex(['mount', dev, mytarget])
        mounted.append(mytarget)

# mount dev and proc
ex(['mount', '-o', 'bind', '/dev/', '%s/dev/' % settings.CHROOT])
ex(['mount', '-o', 'bind', '/dev/pts', '%s/dev/pts' % settings.CHROOT])
ex(['mount', '-o', 'bind', '/proc/', '%s/proc/' % settings.CHROOT])
ex(['mount', '-o', 'bind', '/sys/', '%s/sys/' % settings.CHROOT])
mounted += ['%s/proc' % settings.CHROOT, '%s/dev' % settings.CHROOT,
            '%s/dev/pts' % settings.CHROOT, '%s/sys' % settings.CHROOT]

#########################
### MODIFY FILESYSTEM ###
#########################
os.chdir(settings.CHROOT)
sed_ex = 's/%s/%s/' % (args.frm, args.name)

# create a file that disables restarting of services:
policy_d = 'usr/sbin/policy-rc.d'
f = open(policy_d, 'w')
f.write("#!/bin/sh\nexit 101")
f.close()
ex(['chmod', 'a+rx', policy_d])

# create symlink for bootdisk named like it is in the VM
ex(['ln', '-s', bootdisk, bootdisk_path])

# update hostname
ex(['sed', '-i', sed_ex, 'etc/hostname'])
ex(['sed', '-i', sed_ex, 'etc/hosts'])
ex(['sed', '-i', sed_ex, 'etc/fstab'])

# update IP-address
interfaces = 'etc/network/interfaces'
ex(['sed', '-i', 's/128.130.95.%s/%s/g' % (template_id, ipv4), interfaces])
ex(['sed', '-i', 's/192.168.1.%s/%s/g' % (template_id, ipv4_priv), interfaces])
ex(['sed', '-i', 's/2001:629:3200:95::1:%s/%s/g' % (template_id, ipv6),
    interfaces])
ex(['sed', '-i', 's/fc00::%s/%s/g' % (template_id, ipv6_priv), interfaces])

# update munin config-file:
ex(['sed', '-i', 's/192.168.1.%s/%s/g' % (template_id, ipv4_priv),
    'etc/munin/munin-node.conf'])

# update cgabackup:
ex(['sed', '-i', 's/backup-cga-host/backup-cga-%s/' % args.name,
    'etc/cgabackup/client.conf'])
ex(['sed', '-i', 's/\/backup\/cga\/host/\/backup\/cga\/%s/' % args.name,
    'etc/cgabackup/client.conf'])

# update MAC-address
ex(['sed', '-i', 's/:%s/:%s/g' % (template_id, args.id), 'etc/udev/rules.d/70-persistent-net.rules'])

# reconfigure ssh key
ex(['rm'] + glob.glob('etc/ssh/ssh_host_*'))
chroot(['dpkg-reconfigure', 'openssh-server'])

# update grub
f = open('boot/grub/device.map', 'w')
f.write("(hd0)\t%s\n" % bootdisk_path)
f.close()
chroot(['update-grub'])
chroot(['update-initramfs', '-u', '-k', 'all'])
chroot(['grub-install', '/dev/mapper/vm_test-boot'], ignore_errors=True)
chroot(['sync'])
chroot(['sync'])  # sync it from orbit, just to be sure.
chroot(['grub-setup', '(hd0)'])
chroot(['sync'])
chroot(['sync'])  # sync it from orbit, just to be sure.

# update system
chroot(['apt-get', 'update'])
chroot(['apt-get', '-y', 'dist-upgrade'])

# generate SSH key
chroot(['ssh-keygen', '-t', 'rsa', '-q', '-N', '',
    '-f', '/root/.ssh/id_rsa', '-O', 'no-x11-forwarding',
    '-O', 'source-address=%s,%s,%s,%s' % (ipv4, ipv6, ipv4_priv, ipv6_priv)])

###############
### CLEANUP ###
###############
ex(['rm', bootdisk_path])  # symlink to mimik boot disk inside vm
ex(['rm', policy_d])
os.chdir('/root')
for mount in reversed(mounted):
    ex(['umount', mount])
ex(['vgchange', '-a', 'n', root_vg])
ex(['kpartx', '-d', bootdisk])
os.removedirs(settings.CHROOT)
