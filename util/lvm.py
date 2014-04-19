import logging

from collections import namedtuple

from util.cli import ex

LV = namedtuple('lv', ['name', 'vg', 'attr', 'size', 'pool', 'origin', 'data', 'move', 'log',
                       'copy', 'convert'])
log = logging.getLogger(__name__)


def lvs():
    stdout, stderr = ex(['lvs', '--noheadings', '--separator', ';', '--units=b'], quiet=True,
                        dry=True)
    return [LV(*line.strip().split(';')) for line in stdout.split()]

def lvdisplay(path):
    stdout, stderr = ex(['lvdisplay', '--noheadings', '--separator', ';', '--units=b', '-C', path],
                        quiet=True, dry=True)
    return LV(*stdout.strip().split(';'))

def lvcreate(vg, name, size):
    log.info('Create LV %s on VG %s', name, vg)
    ex(['lvcreate', '-L', size, '-n', name, vg]),
