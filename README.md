simple script to clone virtual machines:

    virsh destroy wheezy
    source py2/bin/activate
    python virsh-create.py <hostname> <id>

Where <hostname> is the new hostname, <id> is the last digit of IPv4/IPv6 address. 

By default, a clone from the VM "wheezy" is created. To create a clone from a
different VM, use --from=vm_name. Note that the source-VM should not be
running during the cloning.
