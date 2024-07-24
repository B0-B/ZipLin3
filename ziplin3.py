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
    
    def backup (self, originPath: str|pathlib.PosixPath, targetPath: str|pathlib.PosixPath, 
                compress: bool=False, compress_format: str='zip', force: bool=False, verbose: bool=True) -> bool:

        '''
        Backups the origin path (host) which points at a file or directory, to target
        path, the destination diectory on host or remote client if ssh is enabled.

        If compress is true the originPath will be zipped, but only if it's not an 
        archive already e.g. of type .zip, .rar, .tar.
        '''

        # convert string paths to posix paths
        if type(originPath) is str:
            originPath = pathlib.Path(originPath)
        if type(targetPath) is not str:
            targetPath = self.join(targetPath, '')

        # check if the origin path is a zip already
        isArchive = False
        for ext in ['.zip', '.rar', '.tar']:
            if ext in originPath.name:
                isArchive = True
                break
        
        # for both cases (file, or dir) create an archive
        # if compression is enabled
        if compress and not isArchive:

            zipPath = originPath.parent.joinpath( originPath.name + '.zip' )
            if verbose: print(f'prepare zip container {zipPath} ...')
            self.compress(originPath, compress=compress_format)
            # transform origin path to zip path
            originPath = zipPath

        # send
        try:
            self.send(originPath, targetPath, force, verbose)
        except:
            print_exc()

        # remove the zip if it was compressed
        if compress and not isArchive:
            originPath.unlink()
        
        if verbose: print(f'done.')

    def checksum (self, filePath: str|pathlib.PosixPath) -> str:

        '''
        Returns checksum in md5 format for provided local file.
        '''
 
        with open(filePath, 'rb') as file:
            return hashlib.file_digest(file, 'md5').hexdigest()
        
    def checksum_remote (self, filePath: str|pathlib.PosixPath) -> str:
        
        '''
        Returns checksum in md5 format for provided remote file.
        If the filepath does not exist, the return will be an empty string.
        '''

        if not self.ssh_enabled:
            ValueError('Please enable ssh first with client.ssh!')
        
        # convert filepath to string
        if type(filePath) is pathlib.PosixPath:
            filePath = filePath.__str__()

        cs = self.exec(f'md5sum {filePath}').split(' ')[0]
        
        # remote execute
        return cs

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

        shutil.make_archive(archive_path, format=format, root_dir=path)

        if archive_path.with_suffix('.'+format).exists():
            print(f'Successfully created archive {str(archive_path.absolute())}.')
        else:
            FileNotFoundError('The archive could not be created.')
    
    def exec (self, command: str) -> str:

        _, stdout, stderr = self.exec_command( command )
        if stderr:
            ValueError(stderr)
        return stdout.read().decode('utf-8')
    
    def send_file (self, originPath: str|pathlib.PosixPath, targetPath: str|pathlib.PosixPath, 
                  force: bool=False, verbose: bool=True) -> None:

        '''
        Sends a file from originPath to targetPath.
        If client.ssh was called beforehand, the targetPath will
        be considered on remote system. A check_sum check is performed
        apriori to prevent redundant copying.

        originPath:     path to file as string or posix
        targetPath:     destination directory path as string or posix.
                        Directory needs to exist already.
        '''

        # check if this is a one-time use to activate sftp
        one_time_sftp = False
        if not self.sftp:
            one_time_sftp = True
            self.sftp = self.open_sftp()

        # set the types correctly
        if type(originPath) is str:
            originPath = pathlib.Path(originPath)
        if type(targetPath) in [pathlib.PosixPath, pathlib.WindowsPath]:
            targetPath = str(targetPath.absolute())
        
        # get the file name
        formattedfilename = originPath.name

        # check if the filename is included in targetPath, if not include it
        if not formattedfilename in targetPath:
            targetPath = self.join(targetPath, formattedfilename)

        # check if scp is enabled
        # based on result determine the target checksum
        target_sum = None
        if self.path_exists(targetPath): # checks remotely or locally
            if self.ssh_enabled:
                target_sum = self.checksum_remote(targetPath)
            else:
                target_sum = self.checksum(targetPath)

        # if not forced, and a target exists (and thus a target sum) 
        # the algo needs to compare checksums first
        if not force and target_sum:

            orgin_sum = self.checksum(originPath)
            
            if orgin_sum == target_sum:
                print(f'{targetPath} is already up-to-date with origin.')
                return

        # send
        if verbose: print(f'{originPath} ---> {self.host}:{targetPath}')
        if self.ssh_enabled:
            # move remotely if client.ssh was called apriori
            self.sftp.put(originPath, targetPath)
        else:
            # move file locally
            shutil.move(originPath, targetPath)
        
        # close the sftp if one-time use
        if one_time_sftp:
            self.sftp = self.sftp.close()

    def send (self, originPath: str|pathlib.PosixPath, targetPath: str|pathlib.PosixPath, 
              force: bool=False, verbose: bool=True) -> None:

        '''
        Sends a file or whole directory at origin into a directory at targetPath.
        If client.ssh was called beforehand, the targetPath will
        be considered on remote system.

        originPath:     path to file as string or posix
        targetPath:     destination directory path as string or posix
        '''

        # open sftp connection
        if self.ssh_enabled:
            self.sftp = self.open_sftp()

        # check if targetpath is a dir
        is_dir = False
        try:
            self.sftp.stat(targetPath)
        except:
            is_dir = True
        if is_dir:
            ValueError('targetPath must point at a directory, not a file!')
        
        # originPath pointing at directory
        if os.path.isdir(originPath):
            
            # if verbose: print(f'sending directory {originPath} ...')
            for _, dirs, files in os.walk(originPath):

                # send all files in current pointer directory
                for file in files:
                    
                    # if verbose: print(f'{self.join(originPath, file)} ---> {targetPath}')
                    self.send_file(self.join(originPath, file), targetPath, force=force)

                # next recurse for directories
                for dir in dirs:

                    self.send(self.join(originPath, dir), self.join(targetPath, dir))

                # stop the loop after one iteration
                return

        # originPath pointing at single file
        elif os.path.isfile(originPath):

            # if verbose: print(f'sending file {originPath} ...')
            self.send_file(originPath, targetPath, force=force)
        
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

    def ssh (self, user: str, host: str, password: str|None=None, sshPath: str|pathlib.PosixPath|None=None, port: int=22) -> None:
        
        '''
        Connects to host via ssh.
        This method takes either a password or path to ssh file to derve login credentials.

        sshPath:    OpenSSH file format
        '''

        try:

            if not sshPath and not password:
                ValueError('Please provide either a password or an ssh file path')
            
            if not password:
                password = ''

            self.user = user
            self.host = host
            self.port = port

            self.connect(self.host, username=self.user, password=password, key_filename=sshPath)
            
            # flip the ssh flag
            self.ssh_enabled = True
        
        except:

            print_exc()

    def path_exists (self, path: str|pathlib.PosixPath) -> bool:

        '''
        Checks if a local or remote path, pointing at file or directory, exists.
        The path is considered remote if client.sshEnabled is true.
        '''

        if self.ssh_enabled:

            # check if this is a one-time use to activate sftp
            one_time_sftp = False
            if not self.sftp:
                one_time_sftp = True
                self.sftp = self.open_sftp()

            # check remotely
            exists = False
            try:
                self.sftp.stat(path)
                # close the sftp if one-time use
                if one_time_sftp:
                    self.sftp = self.sftp.close()
                exists = True
            except IOError:
                pass 
            
            # close the sftp if one-time use
            if one_time_sftp:
                self.sftp = self.sftp.close()
            
            return exists

            # return bool(zl.exec(f'[ -d "{path}" ] && echo 1') + zl.exec(f'[ -f "{path}" ] && echo 1'))
        
        # check locally
        elif os.path.isfile(path) or os.path.isdir(path):
        
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
            originPath: str|pathlib.PosixPath, 
            targetPath: str|pathlib.PosixPath,
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
            'originPath': originPath,
            'targetPath': targetPath,
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
        cl.backup(job['originPath'], job['targetPath'], job['compress'], job['force'])

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