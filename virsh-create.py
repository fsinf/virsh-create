#!/usr/bin/python

from __future__ import unicode_literals

import argparse
import os
import sys

from collections import namedtuple
from subprocess import PIPE
from subprocess import Popen

from lvm2py import *
from lxml import etree

from libvirtpy.conn import conn
from libvirtpy.constants import DOMAIN_STATUS_SHUTOFF


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

# define some varialbes
lv_name = 'vm_%s' % args.name
ipv4 = '128.130.95.%s' % args.id
ipv6 = '2001:629:3200:95::1:%s' % args.id
vnc = '59%s' % args.id

# do some sanity checks:
if os.getuid() != 0:  # check if we are root
    print('Error: You need to be root to create a virtual machine.')
    sys.exit(1)

#############################
### LIBVIRT SANITY CHECKS ###
#############################
# get template domain:
template = conn.getDomain(name=args.frm)
if template.status != DOMAIN_STATUS_SHUTOFF:
    print("Error: VM '%s' is not shut off" % args.frm)
    sys.exit(1)

# check if domain is already defined
if args.name in [d.name for d in conn.getAllDomains()]:
    print("Error: Domain already defined.")
    sys.exit(1)

##########################
### LVM SANITIY CHECKS ###
##########################
# get a list of logical volumes (so we can verify it doesn't exist yet)
lvs = Popen(['lvs', '--noheadings', '--separator', ';', '--units=b'],
            stdout=PIPE, stderr=PIPE)
stdout, stderr = lvs.communicate()
if lvs.returncode != 0:
    print("Error: lvs exited with status code %s: %s" % (lvs.returncode, stderr))
    sys.exit(1)

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
print(domain)

#devices = template_xml.find('devices')
#devices.find('graphics[@type="vnc"]').set('port', str(vnc))
