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

import logging

from collections import namedtuple

from util.cli import ex

LV = namedtuple('lv', ['name', 'vg', 'attr', 'size', 'pool', 'origin', 'data', 'meta', 'move',
                       'log', 'copy', 'convert'])
log = logging.getLogger(__name__)


def lvs():
    stdout, stderr = ex(['lvs', '--noheadings', '--separator', ';', '--units=b'], quiet=True,
                        dry=True)
    return [LV(*line.strip().split(';')) for line in stdout.decode('utf-8').split()]


def lvdisplay(path):
    stdout, stderr = ex(['lvdisplay', '--noheadings', '--separator', ';', '--units=b', '-C', path],
                        quiet=True, dry=True)
    return LV(*stdout.decode('utf-8').strip().split(';'))


def lvcreate(vg, name, size):
    log.info('Create LV %s on VG %s', name, vg)
    ex(['lvcreate', '-L', size, '-n', name, vg])
