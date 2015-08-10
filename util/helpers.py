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

import logging
import os

from util import settings

log = logging.getLogger(__name__)


def get_chroot_gid(name):
    with open(os.path.join(settings.CHROOT, '/etc/group'), 'r') as file:
        lines = file.readlines()
    line = [l for l in lines if l.startswith('%s:' % name)][0]
    name, pwd, gid, userlist = line.split(':')
    return int(gid)
