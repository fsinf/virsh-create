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

import glob
import logging
import os
import random

from util import settings
from util.cli import chroot
from util.cli import ex
from util.context import gid, umask
from util.helpers import get_chroot_gid

log = logging.getLogger(__name__)


def prepare_sshd(tid, id):
    log.info('Preparing SSH daemon')
    ex(['sed', '-i', 's/fc00::%s/fc00::%s/g' % (tid, id), 'etc/ssh/sshd_config'])
    log.debug('- rm /etc/ssh/ssh_host_*')
    ex(['rm'] + glob.glob('etc/ssh/ssh_host_*'), quiet=True)
    ex(['ssh-keygen', '-t', 'ed25519', '-f', 'etc/ssh/ssh_host_ed25519_key', '-N', ''])

    ed25519_fp = ex(['ssh-keygen', '-lf', 'etc/ssh/ssh_host_ed25519_key'])[0]
    log.info('ed25519 fingerprint: %s', ed25519_fp)
    ex(['ssh-keygen', '-t', 'rsa', '-b', '4096', '-f', 'etc/ssh/ssh_host_rsa_key', '-N', ''])
    log.info('rsa fingerprint: %s', ex(['ssh-keygen', '-lf', 'etc/ssh/ssh_host_rsa_key'])[0])


def prepare_cga(frm, name):
    log.info('Prepare cgabackup...')
    cga_config = 'etc/cgabackup/client.conf'
    ex(['sed', '-i', 's/backup-cga-%s/backup-cga-%s/' % (frm, name), cga_config])
    ex(['sed', '-i', 's/\/backup\/cga\/%s/\/backup\/cga\/%s/' % (frm, name), cga_config])

    # randomize the backup-time a bit:
    hour = random.choice(range(1, 8))
    minute = random.choice(range(0, 60))
    ex(['sed', '-i', 's/^0 5/%s %s/' % (minute, hour), 'etc/cron.d/cgabackup'])

def update_grub(sed_ex):
    log.info('Update GRUB')
    # update-grub is suspected to cause problems, so we just replace the hsotname manually
    # chroot(['update-grub'])
    ex(['sed', '-i', sed_ex, 'boot/grub/grub.cfg'])
    chroot(['update-initramfs', '-u', '-k', 'all'])


def update_system(kind):
    log.info('Update system')
    ex(['sed', '-i.backup', 's/http:\/\/%s.local/https:\/\/%s.fsinf.at/' % (kind, kind),
        'etc/apt/sources.list'])
    ex(['sed', '-i.backup', 's/apt.local/apt.fsinf.at/', 'etc/apt/sources.list.d/fsinf.list'])
    chroot(['apt-get', 'update'])
    chroot(['apt-get', '-y', 'dist-upgrade'])
    ex(['mv', 'etc/apt/sources.list.backup', 'etc/apt/sources.list'])
    ex(['mv', 'etc/apt/sources.list.d/fsinf.list.backup', 'etc/apt/sources.list.d/fsinf.list'])


def create_ssh_client_keys(name, ipv4, ipv6, ipv4_priv, ipv6_priv):
    log.info('Generate SSH client keys')
    rsa, ed25519 = '/root/.ssh/id_rsa', '/root/.ssh/id_ed25519'
    rsa_pub, ed25519_pub = os.path.splitext(rsa)[0], os.path.splitext(ed25519)[0]
    sources = (ipv4, ipv6, ipv4_priv, ipv6_priv)

    # remove any prexisting SSH keys
    chroot(['rm', '-f', rsa, rsa_pub, ed25519, ed25519_pub])

    # Note: We force -t rsa, because we have to pass -f in order to be non-interactive
    chroot(['ssh-keygen', '-t', 'rsa', '-q', '-N', '', '-o', '-a', '100', '-b', '4096', '-f', rsa])
    chroot(['ssh-keygen', '-t', 'ed25519', '-q', '-N', '', '-o', '-a', '100', '-f', ed25519])

    for pub in [rsa_pub, ed25519_pub]:
        # Add limiting options:
        chroot(['sed', '-i', 's/^/source-address="%s,%s,%s,%s",no-x11-forwarding/' % sources, pub])
        chroot(['sed', '-i', 's/@[^@]*$/@%s/' % name, pub]) # fix hostname in public keys:


def cleanup_homes():
    """Remove various sensitive files from users home directories."""

    homes = ['root']
    homes += [os.path.join('home', d) for d
              in os.listdir(os.path.join(settings.CHROOT, 'home'))]
    for homedir in homes:
        path = os.path.join(settings.CHROOT, homedir)
        if not os.path.isdir(path):
            continue
        log.info('checking %s...', path)
        for filename in ['.bash_history', '.lesshst', '.viminfo', '.rnd', '.histfile', ]:
            filepath = os.path.join(path, filename)
            if os.path.exists(filepath):
                log.info('Removing %s', filepath)
                os.remove(filepath)

def create_tls_cert(name):
    log.info('Generate TLS certificate')
    key = '/etc/ssl/private/%s.local.key' % name
    pem = '/etc/ssl/public/%s.local.pem' % name
    csr = '/etc/ssl/%s.local.csr' % name
    subject = '/C=AT/ST=Vienna/L=Vienna/CN=%s.local/' % name
    ssl_cert_gid = get_chroot_gid('ssl-cert')

    sign = 'fsinf-ca-sign --alt=%s.local --alt=%s4.local --alt=%s6.local --watch=<your email>' % (
        name, name, name)
    with gid(ssl_cert_gid), umask(0277):
        chroot(['openssl', 'genrsa', '-out', key, '4096'])

    chroot(['openssl', 'req', '-new', '-key', key, '-out', csr, '-utf8',
            '-batch', '-sha256', '-subj', subject])
    log.critical('On enceladus, do:')
    log.critical('\t%s' % sign)
    csr_path = os.path.join(settings.CHROOT, csr.lstrip('/'))
    with open(csr_path, 'r') as csr_file:
        csr_content = csr_file.read()
    log.critical('... and paste the CSR:\n%s' % csr_content)

    # read certificate
    cert_content = ''
    line = ''
    while line != '-----END CERTIFICATE-----':
        line = raw_input().strip()
        cert_content += '%s\n' % line
    with open(os.path.join(settings.CHROOT, pem.lstrip('/')), 'w') as cert_file:
        cert_file.write(cert_content)

    # remove CSR:
    os.remove(csr_path)
