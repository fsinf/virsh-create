import sys

from subprocess import PIPE
from subprocess import Popen

from utils import settings

def ex(cmd, quiet=False, ignore_errors=False, desc=''):
    """Execute a command"""
    if not quiet and settings.VERBOSE:
        cl = ' '.join(cmd)
        if desc:
            cl += '  # %s' % desc
        print(cl)

    p = Popen(cmd, stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()
    status = p.returncode

    if status != 0:
        if ignore_errors:
            print('Error: %s returned status code %s: %s (IGNORED)' % (cmd[0], status, err))
        else:
            print('Error: %s returned status code %s: %s' % (cmd[0], status, err))
            sys.exit(1)
    return out, err

def chroot(cmd, quiet=False, ignore_errors=False, desc=''):
    cmd = ['chroot', settings.CHROOT, ] + cmd
    ex(cmd, quiet=quiet, ignore_errors=ignore_errors, desc=desc)
