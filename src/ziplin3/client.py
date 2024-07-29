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
from pathlib import PosixPath, PurePosixPath, Path
from time import sleep
from cryptography.fernet import Fernet
from traceback import print_exc
from time import time
from datetime import datetime, timedelta
import shutil
import hashlib
import getpass

__root__ = Path(__file__).parent

def log (*stdout: any, header:str='', log_path: PosixPath|str|None=None, 
         verbose: bool=True, end='\n') -> None:

    '''
    Global logging function.
    '''

    if not verbose and not log_path:
        return
    
    if log_path:

        log_path = Path(log_path)

        # create a log file if it doesnt exist
        if not log_path.exists():
            log_path.touch()

    # assemble output
    body = '\t'.join(stdout)
    timestamp = datetime.now().strftime('%d-%m %H:%M:%S')
    
    if verbose:
        output_str = f'{timestamp}  {header}  {body}'
        pad = ''
        if end == '\r':
            pad = ''.join([' ']*(os.get_terminal_size()[0]-len(output_str)))
        print(f'{timestamp}  {header}  {body}{pad}', end=end)

    # log to file
    if log_path:
        with open(log_path, 'a', encoding="utf-8") as log_file:
            log_file.write(f'{timestamp}  |  {body}\n')

def size_format (size_in_bytes: int) -> tuple[float, str]:

        '''
        Returns the memory used by the current process.
        Will return a tuple (value, string suffix), the suffix is
        from 'b', 'kb', 'mb', 'gb', 'tb', depending on size.
        '''
        
        suffix = ['b', 'kb', 'mb', 'gb', 'tb']

        # select correct suffix
        ind = 0
        while size_in_bytes >= 100:
            size_in_bytes /= 1024
            ind += 1
        size_in_bytes = round(size_in_bytes, 1)

        return (size_in_bytes, suffix[ind])

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

        self.bar_sym = '█'
        self.completed_size = 0
        self.copied_size = 0      # actually copied size
        self.deleted_size = 0
        self.files_sent = 0
        self.pad = ''.join([' ']*100)
        self.total_backup_size = 0
        self.progress = 0
        self.process = 0
    
    def backup (self, origin_path: str|PosixPath, target_path: str|PosixPath, 
                compress: bool=False, compress_format: str='zip', clean_artifacts: bool=True, 
                force: bool=False, verbose: bool=True, log_path: PosixPath|str|None=None, progress_bar:bool=True) -> bool:

        '''
        Backups the origin path (host) which points at a file or directory, to target
        path, the destination diectory on host or remote client if ssh is enabled.

        If compress is true the origin_path will be zipped, but only if it's not an 
        archive already e.g. of type .zip, .rar, .tar.

        [Parameters]
        origin_path         path to file as string or posix
        target_path         destination directory path as string or posix,
                            the path needs to exist
        compress            if to compress before backup;
                            if enabled will create an archive from origin_path 
                            which will be sent as a single 'file'
        compress_format     a compression format, default: 'zip' 
                            other registered formats: rar, tar.
                            Note: Although RAR is faster for large file 
                            compression, zip is superior for 
                            cross-platform compatibility.
        clean_artifacts     will clear all artifacts in provided target_path 
                            which are not tracked in corresponding origin_path.
        force               if enabled will ignorantly copy everything
        verbose             verbose shell output
        '''

        start_ts = datetime.now()
        
        log(f'start backup {origin_path} ---> {self.host}:{target_path}', verbose=False, log_path=log_path)

        # convert paths to posix
        origin_path = Path(origin_path)
        target_path = PurePosixPath(target_path)

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
            log(f'prepare zip container {zipPath} ...', verbose=verbose)
            self.compress(origin_path, compress=compress_format)
            # transform origin path to zip path
            origin_path = zipPath

        # backup
        try:
            # sends all contents in origin_path recursively into target_path
            self.send(origin_path, target_path, force, clean_artifacts, verbose, log_path=log_path)
        except:
            print_exc()

        # remove the zip if it was compressed
        if compress and not is_archive:
            origin_path.unlink()

        # determine backup time
        dt = datetime.now() - start_ts
        copied = size_format(self.copied_size)
        checked = size_format(self.completed_size)
        completed = size_format(self.completed_size)

        # output
        log(f'\n\nBackup time: {str(dt)}', header='info', verbose=verbose, log_path=log_path)
        log(f'Backup size: {completed[0]} {completed[1]} ', header='info', verbose=verbose, log_path=log_path)
        log(f'Checked    : {checked[0]} {checked[1].upper()}', header='info', verbose=verbose, log_path=log_path)
        log(f'Copied     : {copied[0]} {copied[1].upper()}', header='info', verbose=verbose, log_path=log_path)
        log(f'Files sent : {self.files_sent}', header='info')
        log(header=f'🏁 successfully backed up {origin_path.name}.', verbose=verbose, log_path=log_path)

    def checksum (self, path: str|PosixPath, remote: bool = False) -> str:

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
            if type(path) is PosixPath:
                path = path.__str__()

            cs = self.exec(f'md5sum {path}').split(' ')[0]
            
            # remote execute
            return cs
        
        else:
        
            with open(path, 'rb') as file:
        
                return hashlib.file_digest(file, 'md5').hexdigest()

    def clean_artifacts (self, target_path: str|PosixPath, local_dirs: list[str], 
                         local_files: list[str], verbose: bool=True, log_path: PosixPath|str|None=None) -> None:

        '''
        Will clear all artifacts in provided target_path which are not tracked in corresponding origin_path.
        The base_names in corr. origin_path are splitted across local_dirs and local_files.

        [Parameters]
        target_path         the path on remote host in which to clean
        local_dirs          list of expected local dirs in corr. origin branch
        local_files         list of expected local files in corr. origin branch
        '''

        remote_names = self.sftp.listdir(target_path.as_posix()) if self.ssh_enabled else os.listdir(target_path)
                    
        for base_name in remote_names:
            
            if base_name in local_files or base_name in local_dirs:
                continue
            
            # otherwise delete file or folder if not in origin dirs or files
            node = target_path.joinpath(base_name)
            log(f'clean artifact: {node.as_posix()}', verbose=verbose, log_path=log_path, end='\r')

            if self.ssh_enabled:

                try: # file
                    self.sftp.remove(node.as_posix())
                except IOError: # directory
                    self.sftp.rmdir(node.as_posix())
            
            else:

                if os.path.isdir(str(node.absolute())):
                    os.rmdir(str(node.absolute()))
                else:
                    os.remove(str(node.absolute()))

    def compress (self, path: str|PosixPath, format: str='zip') -> None:

        '''
        Will create a container from provided directory path 
        with same base name and the same (parent) directory.
        The container is a zip archive with same basename.

        [Parameter]
        path            path to directory which should be archived
        format          a registered format, e.g. zip, tar
                        for more info see: shutil.make_archive
        '''
        
        if type(path) is not PosixPath:
            path = Path(path)
        
        if not path.is_dir():
            ValueError('Provided path is not a directory!')

        base_name = path.name
        archive_path = path.parent.joinpath(base_name)
        suffixed_path = archive_path.with_suffix('.'+format)

        shutil.make_archive(archive_path, format=format, root_dir=path)

        # await the file creation
        while not suffixed_path.exists():
            sleep(.001)  
    
    def exec (self, command: str) -> str:

        _, stdout, stderr = self.exec_command( command )
        if stderr:
            ValueError(stderr)
        return stdout.read().decode('utf-8')
    
    def format_progress (self) -> str:
        fulls = int(self.completed_size / self.total_backup_size * 50)
        empty = 50 - fulls
        return '|' + ''.join([self.bar_sym]*fulls) + ''.join([' ']*empty) + f'| ({int(self.completed_size / self.total_backup_size * 100)}%)'
    
    def get_size (self, path: str|PosixPath) -> int:

        '''
        Returns the size of provided path which points at a folder
        or file in bytes. For local usage only.

        [Parameter]
        path        the node whose size is of interest

        [Return]
        The node size in integer bytes.
        '''

        path = Path(path)
        
        return sum(f.stat().st_size for f in path.glob('**/*') if f.is_file()) if path.is_dir() else path.stat().st_size

    def send_file (self, origin_path: str|PosixPath, target_path: str|PosixPath, 
                  force: bool=False, verbose: bool=True, log_path: PosixPath|str|None=None) -> None:

        '''
        Sends a file from origin_path to target_path.
        If client.ssh method was called beforehand, the target_path will
        be considered on remote system. A check_sum check is performed
        apriori to prevent redundant copying.

        origin_path         path to file as string or posix
        target_path         destination directory path as string or posix.
                            Directory needs to exist already.
        '''

        # check if this is a one-time use to activate sftp
        one_time_sftp = False
        if not self.sftp:
            one_time_sftp = True
            self.sftp = self.open_sftp()

        # set the types correctly
        origin_path = Path(origin_path)
        target_path = PurePosixPath(target_path)

        # paramiko requires target_path to include the filename,
        # so append it.
        # https://github.com/paramiko/paramiko/issues/1000
        target_path = target_path.joinpath(origin_path.name)

        # determine file size and aggregate to completed bytes
        size = self.get_size(origin_path)
        self.completed_size += size
        
        # check if there is a difference in origin and target
        if self.is_identical(origin_path, target_path, self.ssh_enabled, force):
            log(f'{target_path} is already up-to-date with origin.', header=self.format_progress(), verbose=verbose, log_path=log_path, end='\r')
            return

        # try to copy
        try:

            # continue otherwise with sending
            log(f'{origin_path}', header=self.format_progress(), verbose=verbose, end='\r')

            if self.ssh_enabled:
                # move remotely if client.ssh was called apriori
                self.sftp.put(str(origin_path), target_path.as_posix())
            else:
                # move file locally
                shutil.move(str(origin_path), str(target_path))
            if verbose: 
                log(f'{origin_path} ---> {self.host}:{target_path}', verbose=False, log_path=log_path)
            
            # close the sftp if one-time use
            if one_time_sftp:
                self.sftp = self.sftp.close()
            
            # denote the copied size
            self.copied_size += size
            self.files_sent  += 1
        
        except Exception as e:
                
            log(f'{origin_path} ---> {self.host}:{target_path}:', e, header='error', verbose=False, log_path=log_path)
            
    def send (self, origin_path: str|PosixPath, target_path: str|PosixPath, 
              force: bool=False, clean_artifacts: bool=True, verbose: bool=True, log_path: PosixPath|str|None=None) -> None:

        '''
        Sends a file or whole directory at origin into a directory at target_path.
        If client.ssh was called beforehand, the target_path will
        be assumed to be located on the remote system.

        [Parameter]
        origin_path:        path to file as string or posix
        target_path:        destination directory path as string or posix
        force               if enabled will always send the file
        clean_artifact      if enabled will remove all files in target which are not 
                            tracked in origin
        verbose             if enabled will log process in shell
        '''

        # remember the root level
        root = False
        if not self.total_backup_size:
            root = True
            self.total_backup_size = self.get_size(origin_path)

        # convert paths to posix
        origin_path = Path(origin_path)
        target_path = PurePosixPath(target_path)

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
                    self.send_file(file_path, target_path, force=force, verbose=verbose, log_path=log_path)

                # next recurse for directories
                for dir in dirs:

                    dir_path = origin_path.joinpath(dir)
                    self.send(dir_path, target_path, verbose=verbose, log_path=log_path)

                # cleaning
                if clean_artifacts:

                    self.clean_artifacts(target_path, dirs, files, log_path=log_path)

                # stop the loop after one iteration
                return

        # origin_path pointing at single file
        elif origin_path.is_file():

            self.send_file(origin_path, target_path, force=force, verbose=verbose, log_path=log_path)
        
        # close the sftp connection
        if self.ssh_enabled:
            self.sftp = self.sftp.close() if self.sftp else None
        
        # reset progress values
        if root:
            self.total_backup_size = self.completed_size = self.copied_size = self.deleted_size = self.files_sent = 0

    def join (self, path: str, *paths: str) -> str:

        '''
        An improved join path method.
        '''

        extendedPath = os.path.join(path, *paths)

        # in any case convert to unix path if unix is detected
        if '/' in path or '$HOME' in path:
            extendedPath = extendedPath.replace('\\', '/')

        return extendedPath

    def ssh (self, user: str, host: str, password: str|None=None, ssh_path: str|PosixPath|None=None, port: int=22) -> None:
        
        '''
        Connects to host via ssh.
        This method takes either a password or path to ssh file to derve login credentials.

        ssh_path:    OpenSSH file format
        '''

        try:

            if not ssh_path and not password:
                ValueError('Please provide either a password or an ssh file path')

            self.user = user
            self.host = host
            self.port = port

            self.connect(self.host, username=self.user, password=password, key_filename=ssh_path)
            
            # flip the ssh flag
            self.ssh_enabled = True
        
        except:

            print_exc()

    def path_exists (self, path: str|PosixPath, remote: bool=False) -> bool:

        '''
        Checks if a local or remote path, pointing at file or directory, exists.
        The path is considered remote if client.ssh_enabled is true.
        '''

        path = Path(path)

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

    def is_identical (self, origin_path: str|PosixPath, target_path: str|PosixPath, remote: bool=False, force: bool=False):

        '''
        Returns a boolean result from whether two files on the same or varying hosts differ.
        If the target_path does not exist the return will be true.

        [Parameter]
        origin_path         the origin file
        target_path         the path of the file for comparison
        remote              boolean: declares wether the target file is 
                            on remote or local host system
        force               if force is enabled the return will be False
                            and everything else is ignored - this will
                            indicate that the files always differ.
        '''

        target_sum = None

        # checks remotely or locally if the given target_path exists
        # if not creates it
        if force or not self.path_exists(target_path, remote=remote):
            return False
        
        # compare checksums
        target_sum = self.checksum(target_path, remote=remote) 
        orgin_sum = self.checksum(origin_path)

        return orgin_sum == target_sum

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
            origin_path: str|PosixPath, 
            target_path: str|PosixPath,
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