#!/usr/bin/env python3

import argparse
from pathlib import Path
from client import client


__root__ = Path(__file__).parent

def interface (args: argparse.Namespace) -> None:

    zl = client()

    if not args.target:
        print('No target path provided! Use the flag --target to provide a target path or see the help menu -h.')
        return

    # if host is provided, enable ssh
    if args.host:

        if not args.user:
            print('No user provided! Use the flag --user to provide a user name or see the help menu -h.')
            return
        
        # ssh credentials
        key_file = None
        password = None
        port = 22
        if args.pwd:
            password = args.pwd
        elif args.key:
            key_file = args.key
        if args.port:
            port = args.port
            
        zl.ssh(args.user, args.host, password, key_file, port)
    
    # logging
    logging = None
    if args.log:
        logging = args.log

    # start backup    
    zl.backup(args.origin, args.target, args.c, args.compression_format, args.a, args.f, log_path=logging)



if __name__ == '__main__':

    # display banner
    with open(__root__.joinpath('banner')) as f:
        print(f.read())

    # ---- define argparser ----
    parser = argparse.ArgumentParser(
                    prog='ziplin3',
                    description='A modular tool for local and remote backup management via ssh.',
                    epilog='For simple and convenient backups!')
    # route details
    parser.add_argument('-o', '--origin', help="Origin path of the directory of archive which should be backuped.", default='./')
    parser.add_argument('-t', '--target', help="Target path of the directory on local or remote host e.g. '/home/linuxUser/.backups/'")
    # ssh credentials
    parser.add_argument('--host', help="Target host name, or IPv4 address. If not set the host will by default be the local machine i.e. 'localhost'.")
    parser.add_argument('-u', '--user', help="The user on target host. Only needed if --host is set.")
    parser.add_argument('--pwd', help="Provide SSH password. If none provided will by default use the public key in .ssh file. Only needed if --host is set.")
    parser.add_argument('-k', '--key', help="Provide path to SSH public-key file. Only needed if --host is set.")
    parser.add_argument('-p', '--port', help="SSH port on target host. Only needed if --host is set.")
    # backup options
    parser.add_argument('-c', action='store_true', help="Enable compression.")
    parser.add_argument('--compression_format', help="Enable compression. Only needed if compression is enabled.", default='zip')
    parser.add_argument('-a', action='store_true', help="Will delete all artifact files during backup.")
    parser.add_argument('-f', action='store_true', help="Forces a copy of every file, regardless of redundance.")
    parser.add_argument('-l', '--log', help='Optional path to logging file.')


    args = parser.parse_args()

    # ---- forward to interface ----
    interface(args=args)