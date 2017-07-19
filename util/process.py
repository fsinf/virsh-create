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

from contextlib import contextmanager

from util import settings
from util.cli import chroot
from util.cli import ex
from util.context import gid, umask, setting
from util.helpers import get_chroot_gid

log = logging.getLogger(__name__)


@contextmanager
def mount(frm, lv_name, bootdisk, bootdisk_path):
    if not settings.DRY:
        os.makedirs(settings.CHROOT)

    log.info('Detecting logical volumes')
    with setting(SLEEP=3):
        ex(['kpartx', '-s', '-a', bootdisk])  # Discover partitions on bootdisk
        ex(['vgrename', 'vm_%s' % frm, lv_name])  # Rename volume group
        ex(['vgchange', '-a', 'y', lv_name])  # Activate volume group

    log.info('Mounting logical volumes...')
    mounted = []
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

    # create symlink for grub
    ex(['ln', '-s', bootdisk, bootdisk_path])

    policy_d = 'usr/sbin/policy-rc.d'
    log.debug('- echo -e "#!/bin/sh\\nexit 101" > %s', policy_d)
    if not settings.DRY:
        os.chdir(settings.CHROOT)  # just while we're at it :-)

        with open(policy_d, 'w') as f:
            f.write("#!/bin/sh\nexit 101")
    ex(['chmod', 'a+rx', policy_d])

    # execute code in context
    try:
        yield
    finally:

        # remove files
        ex(['rm', policy_d, bootdisk_path])

        # chdir back to /root
        if not settings.DRY:
            os.chdir('/root')

        # unmount filesystems
        for mount in reversed(mounted):
            ex(['umount', mount])

        # deactivate volume group
        with setting(SLEEP=3):
            ex(['vgchange', '-a', 'n', lv_name])
            ex(['kpartx', '-s', '-d', bootdisk])

        if not settings.DRY:
            log.debug('- rmdir %s', settings.CHROOT)
            os.removedirs(settings.CHROOT)

def update_macs(mac, mac_priv):
    log.info("Update MAC addresses")
    rules = 'etc/udev/rules.d/70-persistent-net.rules'
    ex(['sed', '-i', '/NAME="eth0"/s/ATTR{address}=="[^"]*"/%s/g' % mac, rules])
    ex(['sed', '-i', '/NAME="eth1"/s/ATTR{address}=="[^"]*"/%s/g' % mac_priv, rules])


def update_ips(template_id, ipv4, ipv4_priv, ipv6, ipv6_priv):
    log.info('Update IP addresses')
    eth0 = 'etc/network/interfaces.d/eth0'
    eth1 = 'etc/network/interfaces.d/eth1'
    ex(['sed', '-i', 's/128.130.95.%s/%s/g' % (template_id, ipv4), eth0])
    ex(['sed', '-i', 's/192.168.1.%s/%s/g' % (template_id, ipv4_priv), eth1])
    ex(['sed', '-i', 's/2001:629:3200:95::1:%s/%s/g' % (template_id, ipv6), eth0])
    ex(['sed', '-i', 's/fd00::%s/%s/g' % (template_id, ipv6_priv), eth1])


def prepare_sshd(tid, id):
    log.info('Preparing SSH daemon')
    ex(['sed', '-i', 's/fd00::%s/fd00::%s/g' % (tid, id), 'etc/ssh/sshd_config'])
    log.debug('- rm /etc/ssh/ssh_host_*')
    ex(['rm'] + glob.glob('etc/ssh/ssh_host_*'), quiet=True)
    ex(['ssh-keygen', '-t', 'ed25519', '-f', 'etc/ssh/ssh_host_ed25519_key', '-N', ''])

    ed25519_fp = ex(['ssh-keygen', '-lf', 'etc/ssh/ssh_host_ed25519_key'])[0]
    log.info('ed25519 fingerprint: %s', ed25519_fp)
    ex(['ssh-keygen', '-t', 'rsa', '-b', '4096', '-f', 'etc/ssh/ssh_host_rsa_key', '-N', ''])
    log.info('rsa fingerprint: %s', ex(['ssh-keygen', '-lf', 'etc/ssh/ssh_host_rsa_key'])[0])


def prepare_munin(ipv6_priv, key, pem):
    log.info('Preparing munin-node')
    path = 'etc/munin/munin-node.conf'
    ex(['sed', '-i', 's/^host fd00::.*/host %s/g' % ipv6_priv, path])
    ex(['sed', '-i', 's/^#tls/tls/', path])
    ex(['sed', '-i', 's~^tls_private_key.*~tls_private_key %s~' % key, path])
    ex(['sed', '-i', 's~^tls_certificate.*~tls_certificate %s~' % pem, path])


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
    chroot(['apt-get', 'update'])
    chroot(['apt-get', '-y', 'dist-upgrade'])


def create_ssh_client_keys(name):
    log.info('Generate SSH client keys')
    rsa, ed25519 = '/root/.ssh/id_rsa', '/root/.ssh/id_ed25519'
    rsa_pub, ed25519_pub = '%s.pub' % rsa, '%s.pub' % ed25519

    # remove any prexisting SSH keys
    chroot(['rm', '-f', rsa, rsa_pub, ed25519, ed25519_pub])

    # Note: We force -t rsa, because we have to pass -f in order to be non-interactive
    chroot(['ssh-keygen', '-t', 'rsa', '-q', '-N', '', '-o', '-a', '100', '-b', '4096', '-f', rsa])
    chroot(['ssh-keygen', '-t', 'ed25519', '-q', '-N', '', '-o', '-a', '100', '-f', ed25519])

    # Fix hostname
    for pub in [rsa_pub, ed25519_pub]:
        chroot(['sed', '-i', 's/@[^@]*$/@%s/' % name, pub])  # fix hostname in public keys


def cleanup_homes():
    """Remove various sensitive files from users home directories."""

    log.info('Cleaning up home directories')
    homes = ['root']
    if settings.DRY:
        return
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
    ssl_cert_gid = get_chroot_gid('ssl-cert')

    sign = 'fsinf-ca --alt=%s.local --alt=%s4.local --alt=%s6.local --watch=<your email>' % (
        name, name, name)
    with gid(ssl_cert_gid), umask(0o277):
        chroot(['openssl', 'genrsa', '-out', key, '4096'])

    chroot(['openssl', 'req', '-new', '-key', key, '-out', csr, '-utf8', '-batch', '-sha256', ])
    log.critical('On intns1, do:')
    log.critical('\t%s' % sign)
    csr_path = os.path.join(settings.CHROOT, csr.lstrip('/'))
    if settings.DRY:
        log.info('... reading CSR content')
    else:
        with open(csr_path, 'r') as csr_file:
            csr_content = csr_file.read()
        log.critical('... and paste the CSR:\n%s' % csr_content)

    # read certificate
    cert_content = ''
    line = ''
    if settings.DRY:
        log.info('... reading public certificate')
    else:
        while line != '-----END CERTIFICATE-----':
            line = input().strip()
            cert_content += '%s\n' % line

        with open(os.path.join(settings.CHROOT, pem.lstrip('/')), 'w') as cert_file:
            cert_file.write(cert_content)

        # remove CSR:
        os.remove(csr_path)

    return key, pem
