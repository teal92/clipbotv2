"""Portable encrypted master-key export; passwords are entered locally, never arguments."""
import argparse,getpass,json,os,secrets,sys
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from .encrypted_backup import BackupRejected,atomic_write,safe_path,master_key,drill_backup,MAX_ENVELOPE

MAGIC=b'CLIPBOT-RECOVERY\x01'
SIZE=len(MAGIC)+16+12+48


def unlock_key(secret,salt):
    if not isinstance(secret,str) or not 20<=len(secret)<=1024 or any(ord(c)<32 for c in secret):
        raise BackupRejected('Use a unique recovery passphrase of at least 20 characters, without control characters.')
    return Argon2id(salt=salt,length=32,iterations=3,lanes=4,memory_cost=64*1024).derive(secret.encode('utf-8'))


def seal_recovery(key,secret):
    if type(key) is not bytes or len(key)!=32:raise BackupRejected('Invalid recovery master key.')
    salt=secrets.token_bytes(16);nonce=secrets.token_bytes(12);prefix=MAGIC+salt+nonce
    return prefix+AESGCM(unlock_key(secret,salt)).encrypt(nonce,key,prefix)


def open_recovery(blob,secret):
    try:
        if type(blob) is not bytes or len(blob)!=SIZE or not blob.startswith(MAGIC):raise ValueError()
        salt=blob[len(MAGIC):len(MAGIC)+16];nonce=blob[len(MAGIC)+16:len(MAGIC)+28];prefix=blob[:-48]
        key=AESGCM(unlock_key(secret,salt)).decrypt(nonce,blob[-48:],prefix)
        if len(key)!=32:raise ValueError()
        return key
    except Exception:raise BackupRejected('Recovery authentication or format validation failed.') from None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('export','drill'))
    parser.add_argument('--recovery-file',required=True)
    parser.add_argument('--key-file',default=str(Path(os.environ.get('LOCALAPPDATA',''))/'ClipBotRecovery/master.dpapi'))
    parser.add_argument('--backup-file')
    args=parser.parse_args()
    try:
        if not sys.stdin.isatty() or not sys.stderr.isatty():raise BackupRejected('Use an interactive terminal so the passphrase is hidden.')
        recovery=safe_path(args.recovery_file)
        if args.action=='export':
            if recovery.exists() or not recovery.parent.is_dir():raise BackupRejected('Choose a new output file in an existing private folder.')
            secret=getpass.getpass('New recovery passphrase (20+ characters; do not reuse an account password): ')
            if secret!=getpass.getpass('Confirm recovery passphrase: '):raise BackupRejected('Passphrases did not match.')
            key=master_key(args.key_file,create=False);blob=seal_recovery(key,secret)
            if open_recovery(blob,secret)!=key:raise BackupRejected('Recovery verification failed.')
            atomic_write(recovery,blob)
            print('Encrypted recovery key created. Transfer it with encrypted backups to your second computer. Keep the passphrase separately.')
        else:
            if not args.backup_file or not recovery.is_file() or recovery.stat().st_size!=SIZE:raise BackupRejected('Select the encrypted recovery and backup files.')
            backup=safe_path(args.backup_file)
            if not backup.is_file() or backup.stat().st_size>MAX_ENVELOPE:raise BackupRejected('Invalid backup file.')
            key=open_recovery(recovery.read_bytes(),getpass.getpass('Recovery passphrase: '))
            print(json.dumps(drill_backup(backup.read_bytes(),key),sort_keys=True))
    except BackupRejected as error:print(str(error),file=sys.stderr);return 1
    return 0

if __name__=='__main__':sys.exit(main())
