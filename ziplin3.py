#!/usr/bin/env python3

'''
ZipLin3 is an automated backup program which uses zip and ssh 
to transfer files, directories and archives safely from one 
computer to another. Although RAR is faster for large file 
compression, zip is superior for cross-platform compatibility.
'''

import os
import paramiko
import pathlib
from cryptography.fernet import Fernet
from traceback import print_exc
import shutil
import hashlib

class client (paramiko.SSHClient):

    def __init__ (self) -> None:

        super().__init__()

        # generate a random string seed
        # self.seed = ''.join([random.choice( string.ascii_letters + string.digits + string.punctuation ) for i in range(16)])

        self.sshEnabled = False

        # set policy
        self.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # store routes: origin-target-pairs
        self.routes = {}
    
    def backup (self, originPath: str|pathlib.PosixPath, targetPath: str|pathlib.PosixPath, 
                compress: bool=True, force: bool=False, verbose: bool=True) -> bool:

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
        # originStringPath = str(originPath.absolute())
        for ext in ['.zip', '.rar', '.tar']:
            if ext in originPath.name:
                isArchive = True
                break
        
        # for both cases (file, or dir) create an archive
        # if compression is enabled
        if compress and not isArchive:

            zipPath = originPath.parent.joinpath( originPath.name + '.zip' )
            if verbose: print(f'prepare zip container {zipPath} ...')
            self.container(originPath)
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

    def checksum (self, filePath: str|pathlib.PosixPath) -> str:

        '''
        Returns checksum in md5 format for provided local file.
        '''
 
        with open(filePath, 'rb') as file:
            return hashlib.file_digest(file, 'md5').hexdigest()
        
    def checksum_remote(self, filePath: str|pathlib.PosixPath) -> str:
        
        '''
        Returns checksum in md5 format for provided remote file.
        If the filepath does not exist, the return will be an empty string.
        '''

        if not self.sshEnabled:
            ValueError('Please enable ssh first with client.ssh!')
        
        # convert filepath to string
        if type(filePath) is pathlib.PosixPath:
            filePath = filePath.__str__()

        cs = self.exec(f'md5sum {filePath}').split(' ')[0]
        
        # remote execute
        return cs

    def container (self, path: str|pathlib.PosixPath) -> None:

        '''
        Will create a container from provided directory path 
        with same base name and the same (parent) directory.
        The container is a zip archive with same basename.
        '''
        

        if type(path) is not pathlib.PosixPath:
            path = pathlib.Path(path)
        
        if not path.is_dir():
            ValueError('Provided path is not a directory!')

        containerName = path.name

        shutil.make_archive(containerName, 'zip', path)
    
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
    
    def exec (self, command: str) -> str:

        _, stdout, stderr = self.exec_command( command )
        if stderr:
            ValueError(stderr)
        return stdout.read().decode('utf-8')
    
    def sendFile (self, originPath: str|pathlib.PosixPath, targetPath: str|pathlib.PosixPath, force: bool=False) -> None:

        '''
        Sends a file from originPath to targetPath.
        If client.ssh was called beforehand, the targetPath will
        be considered on remote system.

        originPath:     path to file as string or posix
        targetPath:     destination directory path as string or posix.
                        Directory needs to exist already.
        '''

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
        if self.sshEnabled:
            sftp = self.open_sftp()
            target_sum = self.checksum_remote(targetPath)
        else:
            target_sum = self.checksum(targetPath)

        # if not forced compare checksums first
        if not force:

            orgin_sum = self.checksum(originPath)
            
            if orgin_sum == target_sum:

                print(f'{targetPath} is already up-to-date with origin.')
                return

        # send
        if self.sshEnabled:
            sftp.put(originPath, targetPath)
        else:
            shutil.move(originPath, targetPath)

    def send (self, originPath: str|pathlib.PosixPath, targetPath: str|pathlib.PosixPath, 
              force: bool=False, verbose: bool=True) -> None:

        '''
        Sends a file or whole directory at origin into a directory at targetPath.
        If client.ssh was called beforehand, the targetPath will
        be considered on remote system.

        originPath:     path to file as string or posix
        targetPath:     destination directory path as string or posix
        '''

        if not os.path.isdir(targetPath):
            ValueError('targetPath must point at a directory, not a file!')

        # make sure the target path exists
        if not self.pathExists(targetPath):
            if verbose: print(f'create target directory: {targetPath}')
            self.createDir(targetPath)

        # originPath pointing at directory
        if os.path.isdir(originPath):
            
            if verbose: print(f'directory detected: {originPath}')
            for _, dirs, files in os.walk(originPath):

                # send all files in current pointer directory
                for file in files:
                    
                    if verbose: print(f'{self.join(originPath, file)} ---> {targetPath}')
                    self.sendFile(self.join(originPath, file), targetPath, force=force)

                # next recurse for directories
                for dir in dirs:

                    self.send(self.join(originPath, dir), self.join(targetPath, dir))

                # stop the loop after one iteration
                return

        # originPath pointing at single file
        elif os.path.isfile(originPath):

            if verbose: print(f'file detected: {originPath}')
            self.sendFile(originPath, targetPath, force=force)

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
            self.sshEnabled = True
        
        except:

            print_exc()

    def pathExists (self, path: str|pathlib.PosixPath) -> bool:

        '''
        Checks if a local or remote path, pointing at file or directory, exists.
        The path is considered remote if client.sshEnabled is true.
        '''

        if self.sshEnabled:
            # check remotely
            # if os.path.isdir(path):
            #     exists = zl.exec(f'[ -d "{path}" ] && echo 1')
            # else:
            #     exists = zl.exec(f'[ -f "{path}" ] && echo 1')
            return bool(zl.exec(f'[ -d "{path}" ] && echo 1') + zl.exec(f'[ -f "{path}" ] && echo 1'))
        else:
            # check locally
            if os.path.isfile(path) or os.path.isdir(path):
                return True
            return False
    
    def createDir (self, path: str|pathlib.PosixPath):

        '''
        Creates a local or remote directory.
        The path is considered remote if client.sshEnabled is true.
        '''

        if self.sshEnabled:
            zl.exec(f'mkdir {path}')
        else:
            # check locally
            if not os.path.isdir(path):
                os.makedirs(path)

if __name__ == '__main__':

    

    usr = "root"
    testIP = "5.161.46.77"
    pw = "powpal"

    zl = client()
    zl.ssh(usr, testIP, pw)
    # zl.container('testFolder')
    # zl.sendFile('C:\\Users\\weezl\\Desktop\\B0-B\\Scripting\\ZipLin3\\testFolder.zip', '/root/target')
    # zl.createDir('/root/target/remove')
    # zl.send('testFolder.zip', '/root/target/')
    # print('mkdir test:', zl.pathExists("./testFolder"))
    zl.backup('testFolder', '/root/target/', compress=True)
