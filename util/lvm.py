from collections import namedtuple

from util.cli import ex

LV = namedtuple('lv', ['name', 'vg', 'attr', 'size', 'pool', 'origin', 'data',
                       'move', 'log', 'copy', 'convert'])

def lvs():
    stdout, stderr = ex(['lvs', '--noheadings',
                         '--separator', ';', '--units=b'], quiet=True)
    return [LV(*line.strip().split(';')) for line in stdout.split()]

def lvdisplay(path):
    stdout, stderr = ex(['lvdisplay', '--noheadings', '--separator', ';',
                         '--units=b', '-C', path], quiet=True)
    return LV(*stdout.strip().split(';'))

def lvcreate(vg, name, size):
    ex(['lvcreate', '-L', size, '-n', name, vg],
       desc='Create LV %s on VG %s' % (name, vg))
