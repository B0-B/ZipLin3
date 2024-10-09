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

def weekday_to_int (weekday: str) -> int:

    '''
    Turn weekday string into datetime.weekday()-compliant integer i.e. 0-6.

    [Parameter]
    weekday             Weekday as string e.g. Mon or Monday, monday etc.

    [Return]
    Corresponding datetime integer.
    '''

    weekday = weekday.lower()

    if 'mon' in weekday:
        return 0
    elif 'tue' in weekday:
        return 1
    elif 'wed' in weekday:
        return 2
    elif 'thu' in weekday:
        return 3
    elif 'fri' in weekday:
        return 4
    elif 'sat' in weekday:
        return 5
    elif 'sun' in weekday:
        return 6

class client (paramiko.SSHClient):

    def __init__ (self) -> None:

        super().__init__()

        # ---- remote policy ----
        self.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # ssh and file sharing variables
        self.ssh_enabled = False
        self.sftp = None
        self.host = 'localhost'
        self.ssh_path = None
        self.bar_sym = '█'
        self.completed_size = 0
        self.copied_size = 0      # actually copied size
        self.deleted_size = 0
        self.files_sent = 0
        self.pad = ''.join([' ']*100)
        self.total_backup_size = 0
        self.progress = 0
        self.process = 0

        # ---- cache ----
        # get user hash path
        # self.cache_dir = Path.home().joinpath('.cache/zipLin3') 
        # if not self.cache_dir.exists():
        #     self.cache_dir.mkdir()
    
    def backup (self, origin_path: str|PosixPath, target_path: str|PosixPath, 
                compress: bool=False, compress_format: str='zip', clean_artifacts: bool=True, 
                force: bool=False, verbose: bool=True, log_path: PosixPath|str|None=None) -> None:

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

        # if as_cron:
        #     cron(origin_path, target_path, origin_path.name, '22:00', 'weekly', self.host, self.user, self.ssh_path).save()

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

        '''
        Optional method for executing remote code.
        
        [Parameter]
        Shell command (remote shell) as string.

        [Return]
        The stdout as string.
        '''

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
            self.ssh_path = ssh_path

            self.connect(self.host, username=self.user, password=password, key_filename=ssh_path)
            
            # flip the ssh flag
            self.ssh_enabled = True
        
        except:

            print_exc()

class cron:

    '''
    Object for storing cron job information.
    A cron for remote backups requires a setup for ssh key-based authentication on the remote host.
    '''

    CACHE_DIR = Path.home().joinpath('.cache/zipLin3')
    CRON_DIR = CACHE_DIR.joinpath('crons')


    def __init__ (self, origin: str|PosixPath|None=None, target: str|PosixPath|None=None, name: str|None=None, 
                  day_time: str|None=None, week_day: str|None=None, cadence: str='once', host: str|None=None, 
                  user: str|None=None, ssh_path: str|PosixPath|None=None, compress: bool=False, compress_format: str='zip', clean_artifacts: bool=True, 
                  force: bool=False, log_path: PosixPath|str|None=None) -> None:
        
        '''
        [Parameter]

        origin_path         path to file as string or posix
        target_path         destination directory path as string or posix
        name                name of the cron job
        cadence             once, hourly, daily, weekly, monthly
        
        host                remote host name or IP address
        user                corresponding remote user name 
        ssh_path            OpenSSH public key path 

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
        '''

        self.name = name

        # cron variables
        self.compress = compress
        self.compress_format = compress_format
        self.day_time = day_time
        self.week_day = week_day
        self.clean_artifacts = clean_artifacts
        self.force = force
        self.cadence = cadence
        self.origin = Path(origin) if origin else None
        self.target = PurePosixPath(target) if target else None
        self.host = host 
        self.user = user 
        self.log_path = log_path
        self.ssh_path = ssh_path

        # scheduling
        self.last_trigger = None

    def load (name: str) -> 'cron':

        '''
        Loads the cron job from file for backup.

        [Parameter]
        name            name of the cron job i.e. the base name of the folder to archive
                        example: /path/to/folder -> folder
        '''

        # try to load the cron file
        try:
            
            cron_path = cron.CACHE_DIR.joinpath(name + '.json')

            with open(cron_path) as f:
                
                data = json.load(f)

                return cron(
                    Path(data['origin']),
                    PurePosixPath(data['target']),
                    name,
                    data['day_time'],
                    data['cadence'],
                    data['week_day'],
                    data['host'],
                    data['user'],
                    data['ssh_path'],
                    data['compress'],
                    data['compress_forma'],
                    data['clean_artifacts'],
                    data['force'],
                    data['log_path'])

        except:

            print_exc()

    def save (self) -> None:

        '''
        Saves the current cron job in user cache.
        '''

        if not (self.name or self.origin):
            ValueError('cron object requires either a name or origin!')
        elif not self.name and self.origin:
            self.name = Path(self.origin)
        
        try:

            cron_path = cron.CACHE_DIR.joinpath(self.name + '.json')

            # dump the data
            data = {}
            data['name'] = self.name
            data['day_time'] = self.day_time
            data['cadence'] = self.cadence
            data['week_day'] = self.week_day
            data['origin'] = str(self.origin.absolute())
            data['target'] = str(self.target.absolute())
            data['host'] = self.host
            data['ssh_path'] = self.ssh_path 
            data['compress'] = self.compress
            data['compress_format'] = self.compress_format
            data['clean_artifacts'] = self.clean_artifacts
            data['force'] = self.force
            data['log_path'] = self.log_path

            with open(cron_path, 'w+') as f:
                json.dump(data, f)

        except:

            print_exc()

class CronDaemon (client):

    '''
    A daemon extension for [client] class.
    Manages all cron jobs in user cache.
    '''

    CHECK_PATH = cron.CACHE_DIR.joinpath('daemon')
    ACTIVE_PATH = CHECK_PATH.joinpath('active')

    def __init__(self) -> None:

        super().__init__()

        self.crons: dict[str, cron] = dict()
        self.cron_paths: dict[str, PosixPath]

        self.check_create_paths()

        self.load_crons()
    
    def delete_cron (self, name: str) -> None:

        '''
        Deletes a cron file in cache.

        [Parameter]

        name            backup folder base name i.e. name of saved cron
        '''

        # remove file in cache
        self.crons[name].origin.unlink()

        # remove from object
        self.crons.pop(name)
        self.cron_paths.pop(name)
    
    def check_create_paths (self):

        '''
        Checks if all necessary paths exist, if not creates them.
        '''

        for p in [cron.CACHE_DIR, cron.CRON_DIR, CronDaemon.CHECK_PATH]:
            if not p.exists():
                p.mkdir()
        
        # initialize activity file
        if not CronDaemon.ACTIVE_PATH.exists():
            CronDaemon.ACTIVE_PATH.touch()
        
        # disable the service
        self.set_activity(False)
    
    def check_cron (self, name: str) -> bool:

        '''
        Checks if a cron needs to be triggered based on it's schedule info.
        If the criteria are met the method will directly trigger.

        [Return]
        Boolean which indicates backup demand.
        '''

        _cron = self.crons[name]
        now = datetime.now()

        # check for cadence and if the idle threshold was reached
        if _cron.cadence == 'once':

            pass
        
        # once, hourly, daily, weekly, monthly
        else:

            string_time = now.strftime('%H:%M')
            
            if not _cron.last_trigger:

                # pass if there was no triggering yet
                pass

            else:

                # otherwise check if the time threshold was reached
                idle_time_in_sec = int(now.timestamp()) - _cron.last_trigger

                if _cron.cadence == 'daily':
                    idle_threshold =  86340 
                elif _cron.cadence == 'hourly':
                    idle_threshold = 3600
                elif _cron.cadence == 'weekly':
                    idle_threshold = 604740
                elif _cron.cadence == 'montly':
                    idle_threshold = 2419140

                # directly return if the threshold was not met yet
                if idle_time_in_sec < idle_threshold:
                    return False
        
        # if weekday is enabled check for this criterion
        if _cron.week_day and weekday_to_int(_cron.week_day) != now.weekday():
            return False
        
        # if the script had some rest time and the time is 
        # exact to the minute will trigger the cron job
        if _cron.day_time and _cron.day_time != string_time:
            return False

        return True
        # self.trigger_cron(name)

    def is_enabled (self):

        '''
        Checks if the service is enabled via check file.

        [Return]

        Boolean for success.
        '''

        with open(CronDaemon.ACTIVE_PATH) as f:

            return bool(int(f.read()))

    def load_cron_paths (self) -> dict[str, PosixPath]:

        '''
        Loads all cron paths in a dict map. 

        [Return]
        A dict with base_name mapping to corr. posix paths.
        '''

        paths = {}

        for _, _, files in os.walk(str(cron.CACHE_DIR.absolute())):

            for file_name in files:

                file_path = cron.CACHE_DIR.joinpath(file_name)
                cron_name = file_path.name
                paths[cron_name] = file_path
        
        return paths

    def load_cron (self, name: str) -> None:

        '''
        Alias for cron.load method.
        '''

        return cron.load(name)

    def load_crons (self) -> None:

        '''
        Loads all crons from cache. The crons will be stored in client.crons.
        '''

        # load all cron paths from cache and arange in a map
        self.cron_paths = self.load_cron_paths()
        
        # load all cron files from cache
        for name in self.cron_paths:

            if not name in self.crons:

                self.crons[name] = cron.load(name) 

    def register_cron (self, origin: str|PosixPath|None=None, target: str|PosixPath|None=None, name: str|None=None, 
                  day_time: str|None=None, cadence: str='once', host: str|None=None, 
                  user: str|None=None, ssh_path: str|PosixPath|None=None, compress: bool=False, compress_format: str='zip', clean_artifacts: bool=True, 
                  force: bool=False, log_path: PosixPath|str|None=None) -> cron:
        
        '''
        Wrapping alias for cron.__init_ and cron.save.
        Registers new cron in cache and instance.

        [Parameter]

        See cron.__init__ method.

        [Return]

        Returns the newly registered cron object.
        '''
        
        _cron = cron(origin, target, name,day_time, cadence, host, user, 
             ssh_path, compress, compress_format, clean_artifacts, force, log_path)
        _cron.save()

        # refresh
        self.load_crons()

        return _cron

    def service (self) -> None:

        '''
        Automated scheduling service.
        '''

        # enable the service
        self.set_activity(True)

        while self.is_enabled():

            try:

                # update crons
                self.load_crons()

                # check crons iteratively
                for name in self.crons:

                    if not self.check_cron(name):
                        continue

                    log(f"Scheduled backup '{name}' triggering ...", header=self.__class__.__name__)

                    self.trigger_cron(name)

                    # some resource relief
                    sleep(.01)
            
            except:

                print_exc()

            finally:

                sleep(1)
    
    def set_activity (self, value: bool=False) -> None:

        '''
        Sets the activity state in active file upon which the service will act on.
        The activity can independently be disabled again using the same method and another process.

        [Parameter]
        value           Boolean value representing the service activity.
        '''

        with open(CronDaemon.CHECK_PATH, 'w+') as f:

            f.write(str(int(value)))
        
    def trigger_cron (self, name: str) -> None:

        '''
        Triggers a cron backup by overriding all scheduling.

        [Parameter]

        name            backup folder base name i.e. name of saved cron
        '''

        if not name in self.cron_paths:
            ValueError(f'No cron job named "{name}"')

        try:

            _cron = self.crons[name]

            self.backup(_cron.origin, 
                        _cron.target,
                        _cron.compress,
                        _cron.compress_format,
                        _cron.clean_artifacts,
                        _cron.force,
                        True,
                        _cron.log_path)

        except:
            
            print_exc()
        
        finally:
            
            # denote the timestamp
            self.crons[name].last_trigger = datetime.now().timestamp()

    
if __name__ == '__main__':

    pass