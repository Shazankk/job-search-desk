"""Optional read-only IMAP folder ingestion, disabled unless explicitly configured."""
from datetime import datetime, timedelta, timezone
import hashlib
import imaplib
import ssl
from .core import secret


def ingest_imap(root, cfg):
    if not cfg.get('enabled'):
        return 0
    password = secret('IMAP_PASSWORD')
    if not password or not cfg.get('username') or not cfg.get('host'):
        raise ValueError('IMAP requires a configured host, username and Keychain IMAP_PASSWORD')
    cutoff = datetime.now(timezone.utc)-timedelta(days=max(1,min(30,int(cfg.get('lookback_days',7)))))
    month = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][cutoff.month-1]
    date = f'{cutoff.day:02d}-{month}-{cutoff.year}'
    folder = root/'data/inbox'
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    client = imaplib.IMAP4_SSL(cfg['host'],int(cfg.get('port',993)),ssl_context=ssl.create_default_context(),timeout=30)
    count = 0
    try:
        client.login(cfg['username'],password)
        mailbox=cfg.get('folder','Job Alerts')
        if not mailbox.isascii() or any(c in mailbox for c in ('\r','\n')):
            raise ValueError('Use an ASCII alert-folder name without control characters')
        mailbox='\"'+mailbox.replace('\\','\\\\').replace('\"','\\\"')+'\"'
        status,_ = client.select(mailbox,readonly=True)
        if status != 'OK':
            raise ValueError('Alert folder could not be opened')
        status, data = client.uid('search',None,'SINCE',date)
        if status != 'OK':
            raise ValueError('Alert search failed')
        limit = max(1,min(100,int(cfg.get('max_messages',30))))
        for uid in data[0].split()[-limit:]:
            # Limit fetch to 1 MB and do not set the Seen flag.
            status,parts = client.uid('fetch',uid,'(BODY.PEEK[]<0.1000000>)')
            if status != 'OK':
                raise ValueError('Alert fetch failed')
            raw = b''.join(x[1] for x in parts if isinstance(x,tuple) and isinstance(x[1],bytes))
            if not raw or len(raw)>=1_000_000:
                continue
            path = folder/(hashlib.sha256(raw).hexdigest()+'.eml')
            if not path.exists():
                path.write_bytes(raw)
                path.chmod(0o600)
                count += 1
        return count
    finally:
        try:
            client.logout()
        except (OSError,imaplib.IMAP4.error):
            pass
