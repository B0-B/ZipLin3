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

# Getting-Started

## Use as CLI

Use the ``cli.py`` in the ziplin3 project directory to access all functions from the command line

```
> python .\ziplin3\cli.py -h
             _       _     _        _____ 
            (_)     | |   (_)      |____ |
         _____ _ __ | |    _ _ __      / /
        |_  / | '_ \| |   | | '_ \     \ \
         / /| | |_) | |___| | | | |.___/ /
        /___|_| .__/\_____/_|_| |_|\____/
              | |
              |_|

usage: ziplin3 [-h] [-o ORIGIN] [-t TARGET] [--host HOST] [-u USER] [--pwd PWD] [-k KEY] [-p PORT] [-c] [--compression_format COMPRESSION_FORMAT] [-a] [-f] [-l LOG]

A modular tool for local and remote backup management via ssh.

options:
  -h, --help            show this help message and exit
  -o ORIGIN, --origin ORIGIN
                        Origin path of the directory of archive which should be backuped.
  -t TARGET, --target TARGET
                        Target path of the directory on local or remote host e.g. '/home/linuxUser/.backups/'
  --host HOST           Target host name, or IPv4 address. If not set the host will by default be the local machine i.e. 'localhost'.
  -u USER, --user USER  The user on target host. Only needed if --host is set.
  --pwd PWD             Provide SSH password. If none provided will by default use the public key in .ssh file. Only needed if --host is set.
  -k KEY, --key KEY     Provide path to SSH public-key file. Only needed if --host is set.
  -p PORT, --port PORT  SSH port on target host. Only needed if --host is set.
  -c                    Enable compression.
  --compression_format COMPRESSION_FORMAT
                        Enable compression. Only needed if compression is enabled.
  -a                    Will delete all artifact files during backup.
  -f                    Forces a copy of every file, regardless of redundance.
  -l LOG, --log LOG     Optional path to logging file.

For simple and convenient backups!
```

A simple backup to a local target can be performed as 
```
python cli.py -o /user/Desktop/myfolder -t /user/backups/ 
```
while e.g. compressed backups to a remote host can be executed as follows

```
python cli.py -o /path/to/folder/or/archive -t /home/username/ --host <backup host name or ip> -p <port> 
```

To keep the folder in backup up-to-date with the current working folder requires artifact cleaning. These are files and folders which are not being tracked in the actual working space anymore. Note that this feature can purge data if enabled, so use it is highly advised to keep it disabled in archives where untracked data should persist. To clean artifacts append the ``-a`` flag.

```
python cli.py -o /path/to/folder/or/archive -t /home/username/ --host <backup host name or ip> -p <port> -a
```


## Use as Python Module

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

Local backups like e.g. on backup partitions or drives.
Generally, if the `client.ssh` method was called on a ``client`` instance, zipLin3 will assume a remote backup, otherwise if the call is left out, a local backup is performed

```py
...
from ziplin3 import client

zl = client()

local_origin = '/path/to/local/folder'
local_target = '/path/to/backups/'

zl.backup(local_origin, local_target, compress)
```

