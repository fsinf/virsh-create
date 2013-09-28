#!/usr/bin/python

from __future__ import unicode_literals

import argparse
import glob
import os
import sys

from collections import namedtuple
from subprocess import PIPE
from subprocess import Popen

from lvm2py import LVM

from libvirtpy.conn import conn
from libvirtpy.constants import DOMAIN_STATUS_SHUTOFF

def ex(cmd, quiet=False, ignore_errors=False):
    if not quiet:
        print(' '.join(cmd))

    p = Popen(cmd, stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()
    status = p.returncode

    if status != 0:
        if ignore_errors:
            print('Error: %s returned status code %s: %s (IGNORED)' % (cmd[0], status, err))
        else:
            print('Error: %s returned status code %s: %s' % (cmd[0], status, err))
            sys.exit(1)
    return out, err


LV = namedtuple('lv', ['name', 'vg', 'attr', 'size', 'pool', 'origin', 'data',
                'move', 'log', 'copy', 'convert'])

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

parser.add_argument('name', help="Name of the new virtual machine")
parser.add_argument(
    'id', type=int, help="Id of the virtual machine. Used for VNC-port, MAC-address and IP")
args = parser.parse_args()

# define some variables
lv_name = 'vm_%s' % args.name
ipv4 = '128.130.95.%s' % args.id
ipv6 = '2001:629:3200:95::1:%s' % args.id
ipv4_priv = '192.168.1.%s' % args.id
ipv6_priv = 'fc00::%s' % args.id
vncport = int('59%s' % args.id)
target = '/target'

##########################
### BASIC SANITY TESTS ###
##########################
if os.getuid() != 0:  # check if we are root
    print('Error: You need to be root to create a virtual machine.')
    sys.exit(1)
if os.path.exists(target):
    print('Error: %s: Target exists' % target)
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
bootdisk_path = '/dev/%s' % template.getBootTarget()

if os.path.exists(bootdisk_path):
    print("Error: %s already exists" % bootdisk_path)
    sys.exit(1)

##########################
### LVM SANITIY CHECKS ###
##########################
lvm = LVM()  # init

# get a list of logical volumes (so we can verify it doesn't exist yet)
stdout, stderr = ex(['lvs', '--noheadings', '--separator', ';', '--units=b'], quiet=True)

lvs = {}  # list of all logical volumes
for line in stdout.split():
    lv = LV(*line.strip().split(';'))
    lvs[(lv.name, lv.vg)] = lv

# see if the desired logical volume name is already defined anywhere
err_lvs = [lv for lv in lvs if lv[0] == lv_name]
if err_lvs:
    for lv, vg in err_lvs:
        print("Error: %s already exists on VG %s" % (lv_name, vg))
    sys.exit(1)

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

lv_mapping = {}
for path in template.getDiskPaths():

    # get LV and VG from path
    stdout, stderr = ex(['lvdisplay', '-C', path], quiet=True)
    line = stdout.split("\n")[1].strip()
    lv_name, vg_name = line.split()[:2]

    # compute/test new LV-name
    new_lv_name = lv_name.replace(template.name, args.name)
    new_path = path.replace(lv_name, new_lv_name)
    if (new_lv_name, vg_name) in lvs:
        print("Error: LV %s in VG %s is already defined." % (new_lv_name, vg_name))
        sys.exit(1)
    print('Copying %s --> %s' % (path, new_path))

    # get vg/lv from lvm, create new lv:
    vg = lvm.get_vg(vg_name, 'w')
    lv = vg.get_lv(lv_name)
    lv_size = int(lv.size('B'))
    print('Create LV %s on VG %s' % (new_lv_name, vg_name))
    new_lv = vg.create_lv(new_lv_name, lv_size, 'B')

    # replace disk in template
    domain.replaceDisk(path, new_path)

    print('# Copy disk')
    ex(['dd', 'if=%s' % path, 'of=%s' % new_path, 'bs=4M'])

print('Load modified xml definition')
domain = conn.loadXML(domain)

#############################
### MOUNT ROOT FILESYSTEM ###
#############################
bootdisk = domain.getBootDisk()
root_vg = 'vm_%s' % args.name
os.makedirs(target)
mounted = []

print('# Discover partitions on bootdisk')
ex(['kpartx', '-a', bootdisk])

print('# Rename volume group:')
ex(['vgrename', 'vm_%s' % args.frm, root_vg])

print('# Acvivate volume group:')
ex(['vgchange', '-a', 'y', root_vg])

print('# Mount filesystems')
ex(['mount', '/dev/%s/root' % root_vg, target])
mounted.append(target)
for dir in ['boot', 'home', 'usr', 'var', 'tmp']:
    dev = '/dev/%s/%s' % (root_vg, dir)
    if os.path.exists(dev):
        mytarget = '%s/%s' % (target, dir)
        ex(['mount', dev, mytarget])
        mounted.append(mytarget)

# mount dev and proc
ex(['mount', '-o', 'bind', '/dev/', '%s/dev/' % target])
ex(['mount', '-o', 'bind', '/dev/pts', '%s/dev/pts' % target])
ex(['mount', '-o', 'bind', '/proc/', '%s/proc/' % target])
ex(['mount', '-o', 'bind', '/sys/', '%s/sys/' % target])
mounted += ['%s/proc' % target, '%s/dev' % target, '%s/dev/pts' % target,
            '%s/sys' % target]

#########################
### MODIFY FILESYSTEM ###
#########################
os.chdir(target)
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
ex(['chroot', target, 'dpkg-reconfigure', 'openssh-server'])

# update grub
f = open('boot/grub/device.map', 'w')
f.write("(hd0)\t%s\n" % bootdisk_path)
f.close()
ex(['chroot', target, 'update-grub'])
ex(['chroot', target, 'update-initramfs', '-u', '-k', 'all'])
ex(['chroot', target, 'grub-install', '/dev/mapper/vm_test-boot'], ignore_errors=True)
ex(['chroot', target, 'sync'])
ex(['chroot', target, 'sync'])
ex(['chroot', target, 'grub-setup', '(hd0)'])
ex(['chroot', target, 'sync'])
ex(['chroot', target, 'sync'])

# update system
ex(['chroot', target, 'apt-get', 'update'])
ex(['chroot', target, 'apt-get', '-y', 'dist-upgrade'])

# generate SSH key
ex(['chroot', 'target', 'ssh-keygen', '-t', 'rsa', '-q', '-N', '',
    '-f', '.ssh/id_rsa', '-O', 'no-x11-forwarding',
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
os.removedirs(target)
