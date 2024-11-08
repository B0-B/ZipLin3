# ZipLin3
Interface software for local and remote backups via ssh.

# Features
- Simple setup and designed for proprietary integration
- Comes as CLI tool and importable module
- Scheduling of automated backups
- Checksum mechanism for faster and more efficient backups
- Supports the typical registered compression formats for large data
- Automated cleaning of legacies and artifact files / directories
- Supports logging 

# Setup
First clone or download the project and change into the root directory.
Run the following ``pip`` command from the root level to install

```bash
pip install .
```

# Usage

## Getting-Started

```python
from ziplin3 import client
    
usr = "root"
address = "host_name_or_ip"
password = getpass.getpass(f'password for {usr}: ')

# establish connection
zl = client()
zl.ssh(usr, address, password)

# start backup
origin = '/path/to/folder/of/interest'  # local path
target = '/home/user/backups'           # path on remote machine
compress = True
zl.backup(origin, target, compress)
```

```bash
# output
27-07 20:25:03  |███                                               | (6%)  /home/User/.git/hooks/commit-msg.sample is already up-to-date with origin.
```

## Local Backups

`zipLin3` also supports local backups like e.g. on backup partitions or drives.
Generally, if the `client.ssh` method was called on a ``client`` instance, zipLin3 will assume a remote backup, otherwise if the call is left out, a local backup can be achieved

```py
...
from ziplin3 import client

zl = client()

local_origin = '/path/to/local/folder'
local_target = '/path/to/backup/folder'

zl.backup(local_origin, local_target)
```

