# ZipLin3
Automated daemon for compressed backups via ssh.


# Usage

### Windows Host
Assuming the host is a Windows machine and the target client is a Debian linux distro, then a backup of a local folder `testFolder` can be triggered with

```py
from ziplin3 import client
    
usr = "root"
address = "5.161.46.77"
password = getpass.getpass(f'password for {usr}: ')

# initialize a new client
zl = client()
zl.ssh(usr, address, password)

zl.backup('C:\\Users\\zip\\ZipLin3\\testFolder', '/root/target/', compress=True)
```

### Linux Host
Easy backup example from linux to linux machine

```py
from ziplin3 import client
    
usr = "root"
address = "5.161.46.77" # address of storage machine
password = getpass.getpass(f'password for {usr}: ')

# initialize a new client with enabled ssh connection to host
zl = client()
zl.ssh(usr, address, password)

zl.backup('$HOME/testFolder', '/root/target/', compress=True)
```

