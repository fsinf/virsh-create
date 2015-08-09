import logging
import sys
import time

from subprocess import PIPE
from subprocess import Popen

from util import settings

log = logging.getLogger(__name__)


def ex(cmd, quiet=False, ignore_errors=False, dry=False):
    """Execute a command

    :param dry: Execute even if --dry was specified
    """
    if not quiet:
        log.debug('- %s', ' '.join([c if c else '""' for c in cmd]))

    if settings.DRY and not dry:
        return '', ''
    else:
        p = Popen(cmd, stdout=PIPE, stderr=PIPE)
        out, err = p.communicate()
        status = p.returncode

        if settings.SLEEP > 0:  # sleep for given number of seconds
            log.debug('(Sleeping for %s seconds)' % settings.SLEEP)
            time.sleep(settings.SLEEP)

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
