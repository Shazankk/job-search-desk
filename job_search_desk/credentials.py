"""macOS login-Keychain storage for explicitly submitted credentials."""
import getpass
import sys
import keyring

SERVICE='local.job-search-desk.'
LEGACY_SERVICE='local.hr-search.'  # earlier releases; still read so saved keys keep working
ALLOWED={'OPENAI_API_KEY','ANTHROPIC_API_KEY','SMTP_PASSWORD','IMAP_PASSWORD','ADZUNA_APP_ID','ADZUNA_APP_KEY'}


def store(name,value):
    if name not in ALLOWED or not isinstance(value,str) or not value.strip():
        raise ValueError('Choose a supported credential and provide its value')
    if sys.platform!='darwin':
        raise ValueError('Dashboard credential storage requires macOS Keychain')
    from keyring.backends.macOS import Keyring
    # Explicit backend; never fall back to a plaintext or third-party keyring backend.
    Keyring().set_password(SERVICE+name,getpass.getuser(),value.strip())


def read(name):
    if name not in ALLOWED or sys.platform!='darwin':
        return ''
    from keyring.backends.macOS import Keyring
    try:
        return next((v for v in (Keyring().get_password(prefix+name,getpass.getuser()) for prefix in (SERVICE,LEGACY_SERVICE)) if v),'')
    except keyring.errors.KeyringError:
        return ''
