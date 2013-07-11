import six

from libvirtpy.error import ConnectionError
from libvirtpy.error import DomainLookupError
from libvirtpy.domain import LibVirtDomain
from libvirtpy._libvirt import libvirt


class LibVirtConnection(object):
    def __init__(self, name=None):
        self._conn = libvirt.openReadOnly(name)
        if self._conn is None:
            raise ConnectionError('Failed to open connection to the hypervisor')

        self._fetched_all = False
        self._name_cache = {}
        self._id_cache = {}

    def getRawDomain(self, name=None, id=None):
        try:
            if name is not None:
                return self._conn.lookupByName(name)
            if id is not None:
                return self._conn.lookupByID(id)
        except Exception as e:
            raise DomainLookupError("Error looking up domain", e)

    def getDomain(self, name=None, id=None):
        assert name is not None or id is not None, "give either name or id"

        if name is not None and name in self._name_cache:
            return self._name_cache[name]
        if id is not None and id in self._id_cache:
            return self._id_cache[id]

        domain = LibVirtDomain(conn=self, name=name, id=id)

        # populate cache:
        self._name_cache[domain.name] = domain
        self._id_cache[domain.id] = domain

        return domain

    def getAllDomains(self, cache=True):
        if cache and self._fetched_all is True:
            return list(six.itervalues(self._name_cache))

        for name in self._conn.listDefinedDomains():  # only powered-off domains!
            domain = LibVirtDomain(conn=self, name=name)
            self._name_cache[name] = domain
            self._id_cache[domain.id] = domain

        for did in self._conn.listDomainsID():  # only powered-on domains!
            domain = LibVirtDomain(conn=self, id=did)
            self._name_cache[domain.name] = domain
            self._id_cache[did] = domain

        self._fetched_all = True
        return list(six.itervalues(self._name_cache))




conn = LibVirtConnection(None)
