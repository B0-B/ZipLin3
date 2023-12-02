'''
ZipLin3 uses zip and ssh to transfer files, directories and archives safely from one computer to another.
Although RAR is faster for large file compression, zip is superior for cross-platform compatiility.
'''

import os
import paramiko
import pathlib
from cryptography.fernet import Fernet
from traceback import print_exc
import shutil
import hashlib
import platform

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
    
    def backup (self, originPath: str|pathlib.PosixPath, targetPath: str|pathlib.PosixPath, compress: bool=True, force: bool=True) -> bool:

        # convert string paths to posix paths
        if type(originPath) is str:
            originPath = pathlib.Path(originPath)
        if type(targetPath) is str:
            targetPath = pathlib.Path(targetPath)

        # check if the origin path is a zip already
        isArchiveAlready = False
        originStringPath = str(originPath.absolute())
        for ext in ['.zip', '.rar', '.tar']:
            if ext in originStringPath:
                isArchiveAlready = True
                break
        
        # for both cases (file, or dir) create an archive
        # if compression is enabled
        if compress and not isArchiveAlready:
            parent = originPath.parent
            base = originPath.name
            self.container(originPath)
            originPath = parent.joinpath( base + '.zip' )
        
        # send
        try:
            self.send(originPath, targetPath, force)
        except:
            print_exc()

        # remove the zip if it was compressed
        if compress and not isArchiveAlready:
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
        targetPath:     destination directory path as string or posix
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
            targetPath =  self.join(targetPath, formattedfilename)

        # check if scp is enabled
        # based on result determine the target checksum
        if self.sshEnabled:
            sftp = self.open_sftp()
            target_sum = self.checksum_remote(targetPath)
        else:
            target_sum = self.checksum(targetPath)

        # if not forced check for checksum
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

    def send (self, originPath: str|pathlib.PosixPath, targetPath: str|pathlib.PosixPath, force: bool=False):

        '''
        Sends a file or whole directory at origin into a directory at targetPath.
        If client.ssh was called beforehand, the targetPath will
        be considered on remote system.

        originPath:     path to file as string or posix
        targetPath:     destination directory path as string or posix
        '''

        # originPath pointing at single file
        if originPath.is_dir():

            for _, dirs, files in os.walk(originPath):

                # send all files in current pointer directory
                for file in files:

                    self.sendFile(os.path.join(originPath, file), targetPath, force=force)

                # next recurse for directories
                for dir in dirs:

                    self.send(os.path.join(originPath, dir), os.path.join(targetPath, dir))
        
        # originPath pointing at single file
        else:

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

if __name__ == '__main__':

    usr = "root"
    testIP = "5.161.46.77"
    pw = "powpal"

    zl = client()
    zl.ssh(usr, testIP, pw)
    # print('test:', zl.exec('pwd'))
    # print('test:', zl.exec('ls $HOME/tracker/'))
    # print('checksum', zl.checksum('testFolder.zip'))
    # print('checksum remote', zl.checksum_remote('$HOME/tracker/notexistent.js'))
    # zl.container('./testFolder')
    # print('test', pathlib.Path('testFolder.zip').is_dir())
    zl.send( 'testFolder', '/root/target' )
    # zl.backup('testFolder', '$HOME')