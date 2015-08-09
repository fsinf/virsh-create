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
from util.cli import chroot
from util.context import gid, umask
from util.helpers import get_chroot_gid

log = logging.getLogger(__name__)


def create_tls_cert(name):
    log.info('Generate TLS certificate')
    key = '/etc/ssl/private/%s.key' % name
    pem = '/etc/ssl/public/%s.pem' % name
    csr = '/etc/ssl/%s.csr' % name
    subject = 'subject="/C=AT/ST=Vienna/L=Vienna/CN=%s.local/"' % name
    ssl_cert_gid = get_chroot_gid('ssl-cert')

    sign_cmd = 'fsinf-ca-sign --alt=%s.local --alt=%s4.local --alt=%s6.local --watch=<your email>' % (
        name, name, name)
    with gid(ssl_cert_gid), umask(0277):
        chroot(['openssl', 'genrsa', '-out', key, '4096'])

    chroot(['openssl', 'req', '-new', '-key', key, '-out', csr, '-utf8',
            '-batch', '-sha256', '-subj', subject])
    log.critical('On enceladus, do:')
    log.critical('\t%s' % sign_cmd)
    log.critical('... and paste the CSR:')
    with open(os.path.join(settings.CHROOT, csr), 'r') as csr_file:
        csr_content = csr_file.read()
    log.critical(csr_content)

    # read certificate
    cert_content = ''
    line = ''
    while line != '-----END CERTIFICATE REQUEST-----':
        line = raw_input().strip()
        cert_content.append('%s\n' % line)
    with open(os.path.join(settings.CHROOT, pem), 'w') as cert_file:
        cert_file.write(cert_content)
