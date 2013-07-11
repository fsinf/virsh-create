class LibVirtDomain(object):
    def __init__(self, conn, name=None, id=None):
        assert name is not None or id is not None, "give either name or id"
        self._conn = conn
        self._domain = conn.getRawDomain(name=name, id=id)

    @property
    def name(self):
        return self._domain.name()

    @property
    def id(self):
        return self._domain.ID()

    @property
    def status(self):
        return self._domain.info()[0]
