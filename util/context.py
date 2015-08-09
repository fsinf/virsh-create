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

from contextlib import contextmanager

from util import settings

log = logging.getLogger(__name__)


@contextmanager
def gid(id):
    old = os.getgid()
    os.setgid(id)
    yield
    os.setgid(old)


@contextmanager
def umask(mask):
    oldmask = os.umask(mask)
    yield
    os.umask(oldmask)


@contextmanager
def setting(**kwargs):
    old = {}
    for k, v in kwargs.items():
        old[k] = getattr(settings, k, None)
        setattr(settings, k, v)

    yield

    for k, v in old.items():
        setattr(settings, k, v)
