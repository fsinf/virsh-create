import copy

from lxml import etree

class LibVirtDomain(object):
    def __init__(self, conn, name=None, id=None):
        assert name is not None or id is not None, "give either name or id"
        self._conn = conn
        self._domain = conn.getRawDomain(name=name, id=id)
        self._xml = None

    @property
    def name(self):
        return self._domain.name()

    @property
    def id(self):
        return self._domain.ID()

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

class LibVirtDomainXML(object):
    def __init__(self, xml):
        self._xml = xml

    @property
    def name(self):
        return self._xml.find('name').text

    @name.setter
    def name(self, value):
        self._xml.find('name').text = value

    @name.deleter
    def name(self):
        self.name = ''

    @property
    def uuid(self):
        return self._xml.find('uuid').text

    @uuid.setter
    def uuid(self, value):
        self._xml.find('uuid').text = value

    @uuid.deleter
    def uuid(self):
        self._xml.find('uuid').text = ''

    @property
    def description(self):
        return self._xml.find('description').text

    @description.setter
    def description(self, value):
        self._xml.find('description').text = value

    @description.deleter
    def description(self):
        self._xml.find('description').text = ''

    @property
    def vcpu(self):
        return int(self._xml.find('vcpu').text)

    @vcpu.setter
    def vcpu(self, value):
        self._xml.find('vcpu').text = str(value)

    @vcpu.deleter
    def vcpu(self):
        self._xml.find('vcpu').text = ''

    @property
    def memory(self):
        return int(self._xml.find('memory').text)

    @memory.setter
    def memory(self, value):
        self._xml.find('memory').text = str(value)

    @memory.deleter
    def memory(self):
        self._xml.find('memory').text = ''

    @property
    def currentMemory(self):
        return int(self._xml.find('currentMemory').text)

    @currentMemory.setter
    def currentMemory(self, value):
        self._xml.find('currentMemory').text = str(value)

    @currentMemory.deleter
    def currentMemory(self):
        self._xml.find('currentMemory').text = ''

    @property
    def vncport(self):
        return self._xml.find('devices/graphics[@type="vnc"]').get('port')

    @vncport.setter
    def vncport(self, value):
        if value < 1 or value > 65535:
            raise RuntimeError("Port out of range.")
        self._xml.find('devices/graphics[@type="vnc"]').set('port', str(value))

    @property
    def mac(self):
        self._xml.find('devices/interface/mac').get('address')

    @mac.setter
    def mac(self, value):
        self._xml.find('devices/interface/mac').set('address', value)

    @property
    def virtual_function(self):
        elem = self._xml.find('devices/interface/source/address')
        if elem is None:
            return None

        domain = int(elem.get('domain'), 16)
        bus = int(elem.get('bus'), 16)
        slot = int(elem.get('slot'), 16)
        func = int(elem.get('function'), 16)
        return domain, bus, slot, func

    def setVirtualFunction(self, domain, bus, slot, func):
        elem = self._xml.find('devices/interface/source/address')
        elem.set('domain', hex(domain))
        elem.set('bus', hex(bus))
        elem.set('slot', hex(slot))
        elem.set('function', hex(func))

    def replaceDisk(self, old_path, new_path):
        elem = self._xml.find('devices/disk/source[@dev="%s"]' % old_path)
        elem.set('dev', new_path)

    def __str__(self):
        return etree.tostring(self._xml)

    def save(self):
        pass
