#!/usr/bin/python

import argparse
import os
import sys

parser = argparse.ArgumentParser()
# optional arguments:
parser.add_argument('-f', '--from', nargs=1, default="wheezy", metavar='VM',
                    help="Virtual machine to clone from (Default: %(default)s)")

parser.add_argument('name', help="Name of the new virtual machine")
parser.add_argument(
    'id', type=int, help="Id of the virtual machine. Used for VNC-port, MAC-address and IP")
args = parser.parse_args()

#TODO: Do loads of sanity checks

if os.getuid() != 0:  # check if we are root
    print('Error: You need to be root to create a virtual machine.')
    sys.exit(1)
