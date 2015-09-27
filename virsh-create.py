#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of virsh-create (https://github.com/fsinf/virsh-create).
#
# virsh-create is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# virsh-create is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with virsh-create.  If
# not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

import ConfigParser
import argparse
import logging
import os
import sys

from libvirtpy.conn import conn
from libvirtpy.constants import DOMAIN_STATUS_SHUTOFF

from util import context
from util import lvm
from util import process
from util import settings
from util.cli import chroot
from util.cli import ex

log = logging.getLogger(__name__)

parser = argparse.ArgumentParser()
# optional arguments:
parser.add_argument('-f', '--from', default="jessie", metavar='VM', dest='frm',
                    help="Virtual machine to clone from (Default: %(default)s)")
parser.add_argument('--desc', default='',
                    help="Description for the new virtual machine")
parser.add_argument('--kind', default='debian', choices=('debian', 'ubuntu', ),
                    help="Set to 'ubuntu' if this is a Ubuntu and not a Debian template.")
parser.add_argument('--mem', default=1.0, type=float,
                    help="Amount of Memory in GigaByte (Default: %(default)s))")
parser.add_argument('--cpus', default=1, type=int,
                    help="Number of CPUs (Default: %(default)s)")
parser.add_argument('-v', '--verbose', default=0, action="count",
                    help="Verbose output. Can be given up to three times to increase verbosity.")
parser.add_argument('--dry', action='store_true', help="Dry-run, don't really do anything")
parser.add_argument('name', help="Name of the new virtual machine")
parser.add_argument(
    'id', type=int, help="Id of the virtual machine. Used for VNC-port, MAC-address and IP")
args = parser.parse_args()

# parse local machine dependent configuration
config = ConfigParser.ConfigParser()
config.read('virsh-create.conf')
vmhost_id = config.get('DEFAULT', 'vmhost_id')

# configure logging
logging.basicConfig(
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.ERROR - args.verbose * 10 if args.verbose <= 3 else 30
)

# common configuration:
settings.DRY = args.dry

#######################
# Variable definition #
#######################
# define some variables
lv_name = 'vm_%s' % args.name
ipv4 = '128.130.95.%s' % args.id
ipv6 = '2001:629:3200:95::1:%s' % args.id
ipv4_priv = '192.168.1.%s' % args.id
ipv6_priv = 'fd00::%s' % args.id
vncport = int('59%s' % args.id)

######################
# BASIC SANITY TESTS #
######################
if os.getuid() != 0:  # check if we are root
    log.error('Error: You need to be root to create a virtual machine.')
    sys.exit(1)
if os.path.exists(settings.CHROOT):
    log.error('Error: %s: chroot target exists.', settings.CHROOT)
    sys.exit(1)

log.debug('Creating VM %s...', args.name)

#########################
# LIBVIRT SANITY CHECKS #
#########################
# get template domain:
template = conn.getDomain(name=args.frm)
if template.status != DOMAIN_STATUS_SHUTOFF:
    log.error('Error: VM "%s" is not shut off', args.frm)
    sys.exit(1)
template_id = template.domain_id  # i.e. 89.

# check if domain is already defined
if args.name in [d.name for d in conn.getAllDomains()]:
    log.error("Error: Domain already defined.")
    sys.exit(1)
# path to bootdisk, including chroot prefix, e.g. /target/dev/vda
bootdisk_path = os.path.join('/dev', template.getBootTarget())

if os.path.exists(bootdisk_path):
    log.error("Error: %s already exists", bootdisk_path)
    sys.exit(1)

######################
# LVM SANITIY CHECKS #
######################
# get a list of logical volumes (so we can verify it doesn't exist yet)
lvs = {(lv.vg, lv.name): lv for lv in lvm.lvs()}  # list of all logical volumes

# Create mappings from template LVMs to target LVMs, check if they exist
lv_mapping = {}
for path in template.getDiskPaths():
    lv = lvm.lvdisplay(path)

    new_lv_name = lv.name.replace(template.name, args.name)
    if (lv.vg, new_lv_name) in lvs:
        log.error("Error: LV %s in VG %s is already defined.", new_lv_name, lv.vg)
        sys.exit(1)
    lv_mapping[(lv.vg, lv.name)] = (lv.vg, new_lv_name)

#################
# COPY TEMPLATE #
#################
# finally get the full xml of the template
log.info("Copying libvirt XML configuration...")
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

##############
# Copy disks #
##############
for path in template.getDiskPaths():
    # create logical volume
    lv = lvm.lvdisplay(path)
    new_vg, new_lv = lv_mapping[(lv.vg, lv.name)]
    new_path = path.replace(lv.name, new_lv)
    lvm.lvcreate(new_vg, new_lv, lv.size)

    # replace disk in template
    domain.replaceDisk(path, new_path)

    # copy data
    log.info("Copying LV %s to %s", path, new_path)
    ex(['dd', 'if=%s' % path, 'of=%s' % new_path, 'bs=4M'])

############################
# Define domain in libvirt #
############################
log.info('Load new libvirt XML configuration')
if not settings.DRY:
    conn.loadXML(domain.xml)

#########################
# MOUNT ROOT FILESYSTEM #
#########################
bootdisk = domain.getBootDisk()
if not settings.DRY:
    os.makedirs(settings.CHROOT)
mounted = []

log.info('Detecting logical volumes')
with context.setting(SLEEP=3):
    ex(['kpartx', '-s', '-a', bootdisk])  # Discover partitions on bootdisk
    ex(['vgrename', 'vm_%s' % args.frm, lv_name])  # Rename volume group
    ex(['vgchange', '-a', 'y', lv_name])  # Activate volume group

log.info('Mounting logical volumes...')
ex(['mount', os.path.join('/dev', lv_name, 'root'), settings.CHROOT])
mounted.append(settings.CHROOT)
for dir in ['boot', 'home', 'usr', 'var', 'tmp']:
    dev = '/dev/%s/%s' % (lv_name, dir)
    if os.path.exists(dev):
        mytarget = os.path.join(settings.CHROOT, dir)
        ex(['mount', dev, mytarget])
        mounted.append(mytarget)

# mount dev and proc
log.info('Mounting /dev, /dev/pts, /proc, /sys')
pseudo_filesystems = (
    ('sysfs', 'sysfs', os.path.join(settings.CHROOT, 'sys')),
    ('devtmpfs', 'udev', os.path.join(settings.CHROOT, 'dev')),
    ('devpts', 'devpts', os.path.join(settings.CHROOT, 'dev', 'pts')),
    ('proc', 'proc', os.path.join(settings.CHROOT, 'proc')),
)
for typ, dev, target in pseudo_filesystems:
    ex(['mount', '-t', typ, dev, target])
    mounted.append(target)

#####################
# MODIFY FILESYSTEM #
#####################
sed_ex = 's/%s/%s/g' % (args.frm, args.name)

# create a file that disables restarting of services:
policy_d = 'usr/sbin/policy-rc.d'
log.debug('- echo -e "#!/bin/sh\\nexit 101" > %s', policy_d)
if not settings.DRY:
    os.chdir(settings.CHROOT)  # just while we're at it :-)

    with open(policy_d, 'w') as f:
        f.write("#!/bin/sh\nexit 101")
ex(['chmod', 'a+rx', policy_d])

# create symlink for bootdisk named like it appears in the VM
ex(['ln', '-s', bootdisk, bootdisk_path])

# copy /etc/resolv.conf, so that e.g. apt-get update works
ex(['cp', '-S', '.backup', '-ba', '/etc/resolv.conf', 'etc/resolv.conf'])

# update hostname
log.info('Update hostname')
ex(['sed', '-i', sed_ex, 'etc/hostname'])
ex(['sed', '-i', sed_ex, 'etc/hosts'])
ex(['sed', '-i', sed_ex, 'etc/fstab'])
ex(['sed', '-i', sed_ex, 'etc/mailname'])
ex(['sed', '-i', sed_ex, 'etc/postfix/main.cf'])

# update cgabackup
process.prepare_cga(args.frm, args.name)

# Update IP-addresses
log.info('Update IP addresses')
interfaces = 'etc/network/interfaces'
ex(['sed', '-i', 's/128.130.95.%s/%s/g' % (template_id, ipv4), interfaces])
ex(['sed', '-i', 's/192.168.1.%s/%s/g' % (template_id, ipv4_priv), interfaces])
ex(['sed', '-i', 's/2001:629:3200:95::1:%s/%s/g' % (template_id, ipv6), interfaces])
ex(['sed', '-i', 's/fd00::%s/%s/g' % (template_id, ipv6_priv), interfaces])

# Update munin config-file:
ex(['sed', '-i', 's/fd00::%s/%s/g' % (template_id, ipv6_priv), 'etc/munin/munin-node.conf'])

# Update MAC address
log.info("Update MAC address")
ex(['sed', '-i', 's/:%s/:%s/g' % (template_id, args.id),
    'etc/udev/rules.d/70-persistent-net.rules'])

process.cleanup_homes()
process.prepare_sshd(template_id, args.id)
process.update_grub(sed_ex)
process.update_system(args.kind)
process.create_ssh_client_keys(args.name, ipv4, ipv6, ipv4_priv, ipv6_priv)
process.create_tls_cert(args.name)

###########
# CLEANUP #
###########
log.info('Done, cleaning up.')
ex(['rm', policy_d, bootdisk_path])
chroot(['mv', '/etc/resolv.conf.backup', '/etc/resolv.conf'])

if not settings.DRY:
    os.chdir('/root')

for mount in reversed(mounted):
    ex(['umount', mount])

with context.setting(SLEEP=3):
    ex(['vgchange', '-a', 'n', lv_name])
    ex(['kpartx', '-s', '-d', bootdisk])

if not settings.DRY:
    log.debug('- rmdir %s', settings.CHROOT)
    os.removedirs(settings.CHROOT)
