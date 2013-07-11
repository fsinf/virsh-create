class LibVirtPyError(Exception):
    pass

class ConnectionError(LibVirtPyError):
    pass

class DomainLookupError(LibVirtPyError):
    pass
