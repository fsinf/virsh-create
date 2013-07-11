from libvirtpy._libvirt import libvirt

# no state
DOMAIN_STATUS_NOSTATE     = libvirt.VIR_DOMAIN_NOSTATE

# the domain is running
DOMAIN_STATUS_RUNNING     = libvirt.VIR_DOMAIN_RUNNING

# the domain is blocked on resource
DOMAIN_STATUS_BLOCKED     = libvirt.VIR_DOMAIN_BLOCKED

# the domain is paused by user
DOMAIN_STATUS_PAUSED      = libvirt.VIR_DOMAIN_PAUSED

# the domain is being shut down
DOMAIN_STATUS_SHUTDOWN    = libvirt.VIR_DOMAIN_SHUTDOWN

# the domain is shut off
DOMAIN_STATUS_SHUTOFF     = libvirt.VIR_DOMAIN_SHUTOFF

# the domain is crashed
DOMAIN_STATUS_CRASHED     = libvirt.VIR_DOMAIN_CRASHED

# the domain is suspended by guest power management
DOMAIN_STATUS_PMSUSPENDED = libvirt.VIR_DOMAIN_PMSUSPENDED

# NB: this enum value will increase over time as new events are added to the
# libvirt API. It reflects the last state supported by this version of the
# libvirt API.
if hasattr(libvirt, 'VIR_DOMAIN_LAST'):
    DOMAIN_STATUS_LAST = libvirt.VIR_DOMAIN_LAST
else:
    DOMAIN_STATUS_LAST = libvirt.VIR_DOMAIN_PMSUSPENDED
