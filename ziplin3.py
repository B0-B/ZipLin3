'''
ZipLin3 uses zip and ssh to transfer files safely from one computer to another.
RAR is better for large file compression, but zip is better for cross-platform compatiility.
'''


import os
import paramiko
import random
import string
import pathlib
import hashlib
import base64
from cryptography.fernet import Fernet
from traceback import print_exc
import shutil

class client (paramiko.SSHClient):

    def __init__ (self, user: str, password: str, host: str, port: int=22) -> None:

        super().__init__()

        # generate a random string seed
        self.seed = ''.join([random.choice( string.ascii_letters + string.digits + string.punctuation ) for i in range(16)])

        # generate an AES key from seed
        hash_object = hashlib.sha256(self.seed.encode())
        hash_hex = hash_object.hexdigest()
        self.sessionKey = base64.b64encode(bytes.fromhex(hash_hex))

        # secret the password
        self.secret = self.encrypt(self.sessionKey, password)

        self.user = user
        self.host = host
        self.port = port

        # set policy
        self.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    def encrypt (self, key: bytes, plaintext: str) -> str:

        '''
        AES encryption method.
        The Fernet class generates a new initialization vector for 
        each encryption operation and prepends it to the ciphertext.
        '''

        cipher = Fernet(key)
        return cipher.encrypt(str.encode(plaintext)).decode()
    
    def decrypt (self, key: bytes, ciphertext: str) -> str:

        '''
        AES decryption method.
        The Fernet class generates a new initialization vector for 
        each encryption operation and prepends it to the ciphertext.
        '''

        cipher = Fernet(key)
        return cipher.decrypt(str.encode(ciphertext)).decode()

    def ssh (self) -> None:
        '''
        Connects to host via ssh.
        '''
        self.connect(self.host, username=self.user, password=self.decrypt(self.sessionKey, self.secret))

    def exec (self, command: str) -> str:

        _, stdout, stderr = self.exec_command( command )
        if stderr:
            ValueError(stderr)
        return stdout.read().decode()
    
    def container (self, path: str|pathlib.PosixPath):

        '''
        Will create a container from provided directory path 
        with same base name and the same (parent) directory.
        '''

        if type(path) is not pathlib.PosixPath:
            path = pathlib.Path(path)
        
        if not path.is_dir():
            ValueError('Provided path is not a directory!')

        containerName = path.name

        shutil.make_archive(containerName, 'zip', path)

if __name__ == '__main__':

    usr = "root"
    testIP = "5.161.46.77"
    pw = "powpal"

    zl = client(usr, pw, testIP)
    # zl.ssh()
    # print('test:', zl.exec('ls'))

    zl.container('./testFolder')
