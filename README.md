virsh-create
============

**virsh-create** is a script we use to clone virtual machines. It is mostly
tailored to our environment, so you probably have to modify it to use it
yourself.

Installation
------------

The script requires lxml, so you need the following patches on a Debian based
system:

    apt-get install git python-virtualenv libxml2-dev

If you want to install the script manually, you should create a virtualenv:

    git clone https://github.com/fsinf/virsh-create.git
    virtualenv virsh-create
    virsh-create/bin/pip install -r requirements.txt
    virsh-create/bin/python virsh-create/virsh-create.py -h

Usage 
-----

simple script to clone virtual machines:

    virsh destroy wheezy
    source py2/bin/activate
    python virsh-create.py <hostname> <id>

Where <hostname> is the new hostname, <id> is the last digit of IPv4/IPv6 address. 

By default, a clone from the VM "wheezy" is created. To create a clone from a
different VM, use --from=vm_name. Note that the source-VM should not be
running during the cloning.
