#!/usr/bin/env python3

'''
ZipLin3 is an automated backup program which uses zip and ssh 
to transfer files, directories and archives safely from one 
computer to another. Although RAR is faster for large file 
compression, zip is superior for cross-platform compatibility.
'''

import os
import json
import base64
import paramiko
import pathlib
from time import sleep
from cryptography.fernet import Fernet
from traceback import print_exc
import shutil
import hashlib
import getpass

class client (paramiko.SSHClient):

    def __init__ (self) -> None:

        super().__init__()

        # set policy
        self.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # ssh and file sharing
        self.ssh_enabled = False
        self.sftp = None

        # store routes: origin-target-pairs
        self.routes = {}
        self.host = 'localhost'
    
    def backup (self, origin_path: str|pathlib.PosixPath, target_path: str|pathlib.PosixPath, 
                compress: bool=False, compress_format: str='zip', force: bool=False, verbose: bool=True) -> bool:

        '''
        Backups the origin path (host) which points at a file or directory, to target
        path, the destination diectory on host or remote client if ssh is enabled.

        If compress is true the origin_path will be zipped, but only if it's not an 
        archive already e.g. of type .zip, .rar, .tar.
        '''

        # convert paths to posix
        origin_path = pathlib.Path(origin_path)
        target_path = pathlib.PurePosixPath(target_path)
        
        # extend the base name of the target path
        # if target_path.name != origin_path.name:
        #     target_path = target_path.joinpath(origin_path.name)

        # check if the origin path is a zip already
        is_archive = False
        for ext in ['.zip', '.rar', '.tar']:
            if ext in origin_path.name:
                is_archive = True
                break
        
        # for both cases (file, or dir) create an archive
        # if compression is enabled
        if compress and not is_archive:

            zipPath = origin_path.parent.joinpath( origin_path.name + '.zip' )
            if verbose: print(f'prepare zip container {zipPath} ...')
            self.compress(origin_path, compress=compress_format)
            # transform origin path to zip path
            origin_path = zipPath

        # send
        try:
            self.send(origin_path, target_path, force, verbose)
        except:
            print_exc()

        # remove the zip if it was compressed
        if compress and not is_archive:
            origin_path.unlink()
        
        if verbose: print(f'done.')

    def checksum (self, path: str|pathlib.PosixPath, remote: bool = False) -> str:

        '''
        Returns checksum in md5 format for provided local or remote file.

        [Parameter]
        path            the path to file which needs be checksummed
                        (if the target is a linux system use absolute string, .as_posix or pure_posix)
        remote          boolean: declares wether the file is on remote or local host system
        '''

        if remote:

            if not self.ssh_enabled:
                ValueError('Please enable ssh first with client.ssh!')
            
            # convert filepath to string
            if type(path) is pathlib.PosixPath:
                path = path.__str__()

            cs = self.exec(f'md5sum {path}').split(' ')[0]
            
            # remote execute
            return cs
        
        else:
        
            with open(path, 'rb') as file:
        
                return hashlib.file_digest(file, 'md5').hexdigest()
        
    def compress (self, path: str|pathlib.PosixPath, format: str='zip') -> None:

        '''
        Will create a container from provided directory path 
        with same base name and the same (parent) directory.
        The container is a zip archive with same basename.

        [Parameter]
        path            path to directory which should be archived
        format          a registered format, e.g. zip, tar
                        for more info see: shutil.make_archive
        '''
        
        if type(path) is not pathlib.PosixPath:
            path = pathlib.Path(path)
        
        if not path.is_dir():
            ValueError('Provided path is not a directory!')

        base_name = path.name
        archive_path = path.parent.joinpath(base_name)
        suffixed_path = archive_path.with_suffix('.'+format)

        shutil.make_archive(archive_path, format=format, root_dir=path)

        while not suffixed_path.exists():
            sleep(.001)

        # FileNotFoundError('The archive could not be created.')        
    
    def exec (self, command: str) -> str:

        _, stdout, stderr = self.exec_command( command )
        if stderr:
            ValueError(stderr)
        return stdout.read().decode('utf-8')
    
    def send_file (self, origin_path: str|pathlib.PosixPath, target_path: str|pathlib.PosixPath, 
                  force: bool=False, verbose: bool=True) -> None:

        '''
        Sends a file from origin_path to target_path.
        If client.ssh method was called beforehand, the target_path will
        be considered on remote system. A check_sum check is performed
        apriori to prevent redundant copying.

        origin_path:     path to file as string or posix
        target_path:     destination directory path as string or posix.
                        Directory needs to exist already.
        '''

        # check if this is a one-time use to activate sftp
        one_time_sftp = False
        if not self.sftp:
            one_time_sftp = True
            self.sftp = self.open_sftp()

        # set the types correctly
        origin_path = pathlib.Path(origin_path)
        target_path = pathlib.PurePosixPath(target_path)

        # paramiko requires target_path to include the filename,
        # so append it.
        # https://github.com/paramiko/paramiko/issues/1000
        target_path = target_path.joinpath(origin_path.name)
        
        # based on result determine the target checksum
        target_sum = None
        # checks remotely or locally if the given target_path exists
        # if not creates it
        if self.path_exists(target_path, remote=self.ssh_enabled):
            target_sum = self.checksum(target_path, remote=self.ssh_enabled) 

        # if not forced, and a target exists (and thus a target sum) 
        # the algo needs to compare checksums first
        if not force and target_sum:
            orgin_sum = self.checksum(origin_path)
            # skip if the checksums match
            if orgin_sum == target_sum:
                print(f'{target_path} is already up-to-date with origin.')
                return

        # paramiko requires target_path to include the filename,
        # so append it.
        # https://github.com/paramiko/paramiko/issues/1000
        # target_path = target_path.joinpath(origin_path.name)

        # continue otherwise with sending
        if verbose: print(f'{origin_path} ---> {self.host}:{target_path}', end='\r')
        if self.ssh_enabled:
            # move remotely if client.ssh was called apriori
            self.sftp.put(str(origin_path), target_path.as_posix())
        else:
            # move file locally
            shutil.move(str(origin_path), str(target_path))
        if verbose: 
            print(f'{origin_path} ---> {self.host}:{target_path} ✅', end='\n')
        
        # close the sftp if one-time use
        if one_time_sftp:
            self.sftp = self.sftp.close()

    def send (self, origin_path: str|pathlib.PosixPath, target_path: str|pathlib.PosixPath, 
              force: bool=False, verbose: bool=True) -> None:

        '''
        Sends a file or whole directory at origin into a directory at target_path.
        If client.ssh was called beforehand, the target_path will
        be considered on remote system.

        origin_path:     path to file as string or posix
        target_path:     destination directory path as string or posix
        '''

        # convert paths to posix
        origin_path = pathlib.Path(origin_path)
        target_path = pathlib.PurePosixPath(target_path)

        # open sftp connection
        if self.ssh_enabled:
            self.sftp = self.open_sftp()
        
        # origin_path pointing at directory
        if origin_path.is_dir():

            # apriori check if the target directory exists (as it should not)
            # if not create it remote or locally
            target_basename = origin_path.name
            target_final = target_path.joinpath(target_basename)
            if not self.path_exists(target_final.as_posix(), remote=self.ssh_enabled):
                if self.ssh_enabled:
                    self.sftp.mkdir(target_final.as_posix())
                else:
                    os.mkdir(str(target_final))

            # override the current target_path with the new base name
            target_path = target_final
            
            for _, dirs, files in os.walk(str(origin_path.absolute())):

                # send all files in current pointer directory
                for file in files:

                    # file has an extension already!
                    file_path = origin_path.joinpath(file)
                    self.send_file(file_path, target_path, force=force, verbose=verbose)

                # next recurse for directories
                for dir in dirs:

                    dir_path = origin_path.joinpath(dir)
                    self.send(dir_path, target_path.joinpath(dir).as_posix(), verbose=verbose)

                # stop the loop after one iteration
                return

        # origin_path pointing at single file
        elif origin_path.is_file():

            # if verbose: print(f'sending file {origin_path} ...')
            self.send_file(origin_path, target_path, force=force, verbose=verbose)
        
        # close the sftp connection
        if self.ssh_enabled:
            self.sftp = self.sftp.close() if self.sftp else None

    def join (self, path: str, *paths: str) -> str:

        '''
        An improved join path method.
        '''

        extendedPath = os.path.join(path, *paths)

        # in any case convert to unix path if unix is detected
        if '/' in path or '$HOME' in path:
            extendedPath = extendedPath.replace('\\', '/')

        return extendedPath

    def ssh (self, user: str, host: str, password: str|None=None, ssh_path: str|pathlib.PosixPath|None=None, port: int=22) -> None:
        
        '''
        Connects to host via ssh.
        This method takes either a password or path to ssh file to derve login credentials.

        ssh_path:    OpenSSH file format
        '''

        try:

            if not ssh_path and not password:
                ValueError('Please provide either a password or an ssh file path')
            
            if not password:
                password = ''

            self.user = user
            self.host = host
            self.port = port

            self.connect(self.host, username=self.user, password=password, key_filename=ssh_path)
            
            # flip the ssh flag
            self.ssh_enabled = True
        
        except:

            print_exc()

    def path_exists (self, path: str|pathlib.PosixPath, remote: bool=False) -> bool:

        '''
        Checks if a local or remote path, pointing at file or directory, exists.
        The path is considered remote if client.ssh_enabled is true.
        '''

        path = pathlib.Path(path)

        if remote and not self.ssh_enabled:
            ValueError('For calling path_exists on remote host please enable ssh by calling the client.ssh method first!')

        if remote:

            # check if this is a one-time use to activate sftp
            one_time_sftp = False
            if not self.sftp:
                one_time_sftp = True
                self.sftp = self.open_sftp()

            # check remotely
            exists = False
            try:
                self.sftp.stat(path.as_posix())
                exists = True
            except IOError:
                pass # FileNotFoundError if the path is not found
            
            # close the sftp if one-time use
            if one_time_sftp:
                self.sftp = self.sftp.close()
            
            return exists

            # return bool(zl.exec(f'[ -d "{path}" ] && echo 1') + zl.exec(f'[ -f "{path}" ] && echo 1'))
        
        # check locally
        elif path.is_file() or path.is_dir():
        
            return True
        
        return False

class cron:

    '''
    Automated cron job daemon for scheduling backups.
    Add jobs which are triggered at specified cadence and day time.
    '''

    def __init__ (self, masterSecret: str) -> None:
        
        self.jobs = []
        self.dailyStack = [] # a subset of self.jobs

        # derive master key from secret
        self.masterKey = self.keyGen(masterSecret) # do not save master secret
        self.sshFilePath = None

    def addJob (self, 
            origin_path: str|pathlib.PosixPath, 
            target_path: str|pathlib.PosixPath,
            host: str='localhost',
            user: str|None=None,
            password: str|None=None,
            sshFilePath: str|None=None,
            compress: bool=True,
            force: bool=False,
            dayTime: str='00:00',
            weekDay: str='Sunday',
            cadence: str='weekly'):
        
        '''
        Adds a new job to jobs list.
        cadence     once, daily, weekly, monthly, quarterly
                    if once is selected, the job will delete itself.
        host        If host is not default (localhost), the method
                    will require user and password to establish
                    ssh connection.
        '''

        # corpus
        job = {
            'id': None,
            'origin_path': origin_path,
            'target_path': target_path,
            'host': host,
            'user': user,
            'fingerprint': None,
            'sshFilePath': sshFilePath,
            'compress': compress,
            'force': force,
            'dayTime': dayTime,
            'weekday': weekDay,
            'cadence': cadence,
            'timestamp': None
        }

        # generate unique job id and label job object
        job['id'] = hashlib.md5(json.dumps(job).encode('ascii'))

        # generate a fingerprint for job
        job['fingerprint'] = self.encrypt(self.masterKey, password)

        # add job object to jobs list
        self.jobs.append(job)

    def startJob (self, job: dict) -> bool:

        '''
        Triggers a backup job.
        '''

        cl = client()

        # check if host is remote
        if job['host'] != 'localhost':
            cl.ssh(job['user'], job['host'], self.decrypt(self.masterKey, job['fingerprint']), job['sshFilePath'])
        
        # backup
        cl.backup(job['origin_path'], job['target_path'], job['compress'], job['force'])

    def decrypt (self, key: bytes, ciphertext: str) -> str:

        '''
        AES decryption method.
        The Fernet class generates a new initialization vector for 
        each encryption operation and prepends it to the ciphertext.
        '''

        cipher = Fernet(key)
        return cipher.decrypt(str.encode(ciphertext)).decode()

    def encrypt (self, key: bytes, plaintext: str) -> str:

        '''
        AES encryption method.
        The Fernet class generates a new initialization vector for 
        each encryption operation and prepends it to the ciphertext.
        '''

        cipher = Fernet(key)
        return cipher.encrypt(str.encode(plaintext)).decode()
    
    def keyGen (self, secret:str) -> bytes:

        '''
        Generates url-safe b64-encoded 32 bit key in bytes format from provided secret.
        This method is useful to generate keys from secrets for Fernet module.
        '''

        hash_object = hashlib.sha256(secret.encode())
        hash_hex = hash_object.hexdigest()
        hash_base64 = base64.b64encode(bytes.fromhex(hash_hex))

        return hash_base64
    
    def daemon (self) -> None:

        try:

            

            # select the daily stack
            for j in self.jobs:

                pass

        except:
            print_exc()
        

if __name__ == '__main__':

    usr = "root"
    address = "5.161.46.77"
    password = getpass.getpass(f'password for {usr}: ')

    # initialize a new client
    zl = client()
    zl.ssh(usr, address, password)

    zl.backup('C:\\Users\\weezl\\Desktop\\B0-B\\Gaming', '/root/target/', compress=True)