#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of virsh-create (https://github.com/fsinf/virsh-create).
#
# virsh-create is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# virsh-create is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
# for more details.
#
# You should have received a copy of the GNU General Public License along with virsh-create. If not, see
# <http://www.gnu.org/licenses/>.

import configparser
import argparse
import logging
import os
import sys

from libvirtpy.conn import conn
from libvirtpy.constants import DOMAIN_STATUS_SHUTOFF

from util import lvm
from util import process
from util import settings
from util.cli import chroot
from util.cli import ex

log = logging.getLogger(__name__)

parser = argparse.ArgumentParser()
parser.add_argument('-f', '--from', default="jessie", metavar='VM', dest='frm',
                    help="Virtual machine to clone from (Default: %(default)s)")
parser.add_argument('--desc', default='',
                    help="Description for the new virtual machine")
parser.add_argument('--kind', default='debian', choices=('debian', 'ubuntu', ),
                    help="Set to 'ubuntu' if this is a Ubuntu and not a Debian template.")
parser.add_argument('--mem', default=1.0, type=float,
                    help="Amount of Memory in GigaByte (Default: %(default)s).")
parser.add_argument('--cpus', default=1, type=int,
                    help="Number of CPUs (Default: %(default)s)")
parser.add_argument('-v', '--verbose', default=0, action="count",
                    help="Verbose output. Can be given up to three times to increase verbosity.")
parser.add_argument('-s', '--section', default='DEFAULT',
                    help="Use different section in config file (Default: %(default)s).")
parser.add_argument('--dry', action='store_true', help="Dry-run, don't really do anything")
parser.add_argument('name', help="Name of the new virtual machine")
parser.add_argument(
    'id', type=int, help="Id of the virtual machine. Used for VNC-port, MAC-address and IP")
args = parser.parse_args()

# parse local machine dependent configuration
config = configparser.ConfigParser(defaults={
    'transfer-from': '',
    'transfer-to': '',
    'transfer-source': '',
    'public_bridge': 'br0',
    'priv_bridge': 'br1',
    'vnc_port': '59%(guest_id)s',
})
config.read('virsh-create.conf')
config[args.section]['guest_id'] = str(args.id)
host_id = config.get(args.section, 'host_id')
transfer_from = config.get(args.section, 'transfer-from')

# configure logging
logging.basicConfig(
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.ERROR - (args.verbose * 10 if args.verbose <= 3 else 30)
)

# common configuration:
settings.DRY = args.dry

#######################
# Variable definition #
#######################
# define some variables
lv_name = 'vm_%s' % args.name
public_bridge = config.get(args.section, 'public_bridge')
public_mac = config.get(args.section, 'public_mac')
public_ip4 = config.get(args.section, 'public_ip4')
public_ip6 = config.get(args.section, 'public_ip6')
priv_bridge = config.get(args.section, 'priv_bridge')
priv_mac = config.get(args.section, 'priv_mac')
priv_ip4 = config.get(args.section, 'priv_ip4')
priv_ip6 = config.get(args.section, 'priv_ip6')
vnc_port = config.get(args.section, 'vnc_port')

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
if template.status != DOMAIN_STATUS_SHUTOFF and not transfer_from:
    log.error('Error: VM "%s" is not shut off', args.frm)
    sys.exit(1)
template_id = template.domain_id  # i.e. 89.

# check if domain is already defined
if args.name in [d.name for d in conn.getAllDomains()]:
    log.error("Error: Domain already defined.")
    sys.exit(1)
# path to bootdisk, including chroot prefix, e.g. /target/dev/vda
bootdisk_path = os.path.join('/dev', template.getBootTarget())

if os.path.lexists(bootdisk_path):
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
domain.vncport = vnc_port
domain.update_interface(public_bridge, public_mac, public_ip4, public_ip6)
domain.update_interface(priv_bridge, priv_mac, priv_ip4, priv_ip6)

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

    if transfer_from:
        transfer_to = config.get(args.section, 'transfer-to')
        transfer_source = config.get(args.section, 'transfer-source')
        log.warn('Copy disk by executing on %s', transfer_from)
        log.warn("  dd if=%s bs=4096 | pv | gzip | ssh %s 'gzip -d | dd of=%s bs=4096'",
                 transfer_source or path, transfer_to, new_path)
        log.warn("Press enter when done.")
        if not settings.DRY:
            input()
    else:
        # copy data from local volume
        log.info("Copying LV %s to %s", path, new_path)
        ex(['dd', 'if=%s' % path, 'of=%s' % new_path, 'bs=4M'])

############################
# Define domain in libvirt #
############################
log.info('Load new libvirt XML configuration')
if not settings.DRY:
    conn.loadXML(domain.xml)


#####################
# MODIFY FILESYSTEM #
#####################
sed_ex = 's/%s/%s/g' % (args.frm, args.name)

bootdisk = domain.getBootDisk()
with process.mount(args.frm, lv_name, bootdisk, bootdisk_path):
    # copy /etc/resolv.conf, so that e.g. apt-get update works
    ex(['cp', '-S', '.backup', '-ba', '/etc/resolv.conf', 'etc/resolv.conf'])

    # update hostname
    log.info('Update hostname')
    ex(['sed', '-i', sed_ex, 'etc/hostname'])
    ex(['sed', '-i', sed_ex, 'etc/hosts'])
    ex(['sed', '-i', sed_ex, 'etc/fstab'])
    ex(['sed', '-i', sed_ex, 'etc/mailname'])
    ex(['sed', '-i', sed_ex, 'etc/postfix/main.cf'])

    process.prepare_cga(args.frm, args.name)
    process.update_ips(template_id, public_ip4, priv_ip4, public_ip6, priv_ip6)
    process.update_macs(public_mac, priv_mac)
    process.cleanup_homes()
    process.prepare_sshd(template_id, priv_ip6)
    process.update_grub(sed_ex)
    process.update_system(args.kind)
    process.create_ssh_client_keys(args.name)
    key, pem = process.create_tls_cert(args.name)
    process.prepare_munin(priv_ip6, key, pem)

    log.info('Done, cleaning up.')
    chroot(['mv', '/etc/resolv.conf.backup', '/etc/resolv.conf'])
