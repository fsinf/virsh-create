import logging
import sys

from subprocess import PIPE
from subprocess import Popen

from util import settings

log = logging.getLogger(__name__)


def ex(cmd, quiet=False, ignore_errors=False):
    """Execute a command"""
    if not quiet:
        log.debug('- %s', ' '.join(cmd))

    if settings.DRY:
        return '', ''
    else:
        p = Popen(cmd, stdout=PIPE, stderr=PIPE)
        out, err = p.communicate()
        status = p.returncode

        if status != 0:
            if ignore_errors:
                log.warn('Error: %s returned status code %s: %s (IGNORED)', cmd[0], status, err)
            else:
                log.error('Error: %s returned status code %s: %s', cmd[0], status, err)
                sys.exit(1)
        return out, err

def chroot(cmd, quiet=False, ignore_errors=False):
    cmd = ['chroot', settings.CHROOT, ] + cmd
    ex(cmd, quiet=quiet, ignore_errors=ignore_errors)
