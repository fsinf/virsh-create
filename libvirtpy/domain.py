import copy
import logging

from lxml import etree

log = logging.getLogger(__name__)

class LibVirtBase(object):
    def getBootDisk(self):
        # NOTE: according to documentation, the xml description sorts disks by
        # boot device priority. So the first disk is the boot-disk.

        # We convert returned value to str because for some reason the script
        # segfaults (!) otherwise.
        return str(self.xml.find('devices/disk[@type="block"]/source').get('dev'))

    def getBootTarget(self):
        return str(self.xml.find('devices/disk[@type="block"]/target').get('dev'))

class LibVirtDomain(LibVirtBase):
    def __init__(self, conn, name=None, id=None, domain=None):
        assert name is not None or id is not None or domain is not None
        self._conn = conn
        if domain is None:
            self._domain = conn.getRawDomain(name=name, id=id)
        else:
            self._domain = domain
        self._xml = None

    @property
    def name(self):
        return self._domain.name()

    @property
    def id(self):
        return self._domain.ID()

    @property
    def domain_id(self):
        vncport = self.xml.find('devices/graphics[@type="vnc"]').get('port')
        return int(vncport) - 5900

    @property
    def status(self):
        return self._domain.info()[0]

    @property
    def xml(self):
        if self._xml is None:
            self._xml = etree.fromstring(self._domain.XMLDesc(0))

        return copy.deepcopy(self._xml)

    @property
    def virtual_function(self):
        elem = self.xml.find('devices/interface/source/address')
        if elem is None:
            return None

        domain = int(elem.get('domain'), 16)
        bus = int(elem.get('bus'), 16)
        slot = int(elem.get('slot'), 16)
        func = int(elem.get('function'), 16)
        return domain, bus, slot, func

    def getDiskPaths(self):
        for elem in self.xml.findall('devices/disk[@type="block"]'):
            source = elem.find('source')
            if source is None:
                continue
            yield source.get('dev')

    def copy(self):
        return LibVirtDomainXML(self.xml)

class LibVirtDomainXML(LibVirtBase):
    def __init__(self, xml):
        self.xml = xml

    @property
    def name(self):
        return self.xml.find('name').text

    @name.setter
    def name(self, value):
        self.xml.find('name').text = value

    @name.deleter
    def name(self):
        self.xml.find('name').text = ''

    @property
    def uuid(self):
        return self.xml.find('uuid').text

    @uuid.setter
    def uuid(self, value):
        self.xml.find('uuid').text = value

    @uuid.deleter
    def uuid(self):
        self.xml.find('uuid').text = ''

    @property
    def description(self):
        return self.xml.find('description').text

    @description.setter
    def description(self, value):
        elem = self.xml.find('description')
        if elem is not None:
            self.xml.find('description').text = value
        else:
            log.warn("Warning: Could not set description.")

    @description.deleter
    def description(self):
        self.xml.find('description').text = ''

    @property
    def vcpu(self):
        return int(self.xml.find('vcpu').text)

    @vcpu.setter
    def vcpu(self, value):
        self.xml.find('vcpu').text = str(value)

    @vcpu.deleter
    def vcpu(self):
        self.xml.find('vcpu').text = ''

    @property
    def memory(self):
        return int(self.xml.find('memory').text)

    @memory.setter
    def memory(self, value):
        self.xml.find('memory').text = str(value)

    @memory.deleter
    def memory(self):
        self.xml.find('memory').text = ''

    @property
    def currentMemory(self):
        return int(self.xml.find('currentMemory').text)

    @currentMemory.setter
    def currentMemory(self, value):
        self.xml.find('currentMemory').text = str(value)

    @currentMemory.deleter
    def currentMemory(self):
        self.xml.find('currentMemory').text = ''

    @property
    def vncport(self):
        return self.xml.find('devices/graphics[@type="vnc"]').get('port')

    @vncport.setter
    def vncport(self, value):
        if value < 1 or value > 65535:
            raise RuntimeError("Port out of range.")
        self.xml.find('devices/graphics[@type="vnc"]').set('port', str(value))

    def get_interface(self, source):
        """Get the XML element with the specified source."""
        interfaces = self.xml.findall('devices/interface')
        return [i for i in interfaces if i.find('source[@bridge="%s"]' % source) is not None][0]

    def fix_mac(self, source, mac):
        iface = self.get_interface(source)
        iface.find('mac').set('address', mac)

        # set the filterref variable
        filterref = iface.find('filterref/parameter[@name="MAC"]')
        if filterref is not None:
            filterref.set('value', mac)

    def replaceDisk(self, old_path, new_path):
        elem = self.xml.find('devices/disk/source[@dev="%s"]' % old_path)
        elem.set('dev', new_path)

    def __str__(self):
        return etree.tostring(self.xml)

    def save(self):
        pass
