from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger('job_search_desk')


def now():
    return datetime.now(timezone.utc).isoformat()


def setup_logging(root=ROOT):
    folder = root / 'logs'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not LOG.handlers:
        handler = RotatingFileHandler(folder / 'agent.log', maxBytes=1_000_000, backupCount=3)
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        LOG.addHandler(handler)
        LOG.setLevel(logging.INFO)


def load_config(root=ROOT):
    p = root / 'config/settings.json'
    if not p.exists():
        p.write_text((root / 'config/settings.example.json').read_text())
        p.chmod(0o600)
    c = json.loads(p.read_text())
    if 'discovery' not in c:
        c['discovery'] = {'max_queries':3,'queries':[],'himalayas':{'enabled':True,'pages_per_query':2},'adzuna':{'enabled':False,'pages_per_query':1,'radius_km':25}}
        p.write_text(json.dumps(c,indent=2)+'\n')
    if c.get('discovery') and 'linkedin_public' not in c['discovery']:
        c['discovery']['linkedin_public']={'enabled':False,'max_searches_per_run':5,'max_details_per_run':15,'delay_seconds':3,'daily_request_limit':50,'job_age_days':30}
        p.write_text(json.dumps(c,indent=2)+'\n')
    if c.get('discovery') and 'naukri_sitemap' not in c['discovery']:
        c['discovery']['naukri_sitemap']={'enabled':True,'max_leads_per_run':40,'job_age_days':30}
        p.write_text(json.dumps(c,indent=2)+'\n')
    if 'work_modes' not in c:
        # Older configs: plain city names and an India-only remote switch.
        from .places import resolve, country_of
        c['locations'] = [resolve(x) or x for x in c.get('locations',[])]
        c['work_modes'] = ['onsite','hybrid']+(['remote'] if c.pop('remote_india',True) else [])
        c['home_country'] = next((country_of(x) for x in c['locations'] if country_of(x)),None)
        p.write_text(json.dumps(c,indent=2,ensure_ascii=False)+'\n')
    if not c['work_modes'] or not set(c['work_modes']) <= {'onsite','hybrid','remote'}:
        raise ValueError('work_modes must include at least one of onsite, hybrid, remote')
    if c.get('llm', {}).get('provider', 'none') not in ('none', 'openai', 'claude'):
        raise ValueError('Choose AI provider none, openai or claude')
    if not 0 <= float(c['min_score']) <= 10:
        raise ValueError('min_score must be between 0 and 10')
    if not 0 <= int(c['schedule']['hour']) <= 23 or not 0 <= int(c['schedule']['minute']) <= 59:
        raise ValueError('Invalid schedule')
    if c['email']['security'] not in ('ssl', 'starttls'):
        raise ValueError('SMTP requires ssl or starttls')
    return c


def secret(name):
    """Environment takes precedence; LaunchAgents can use the login Keychain."""
    if os.environ.get(name):
        return os.environ[name]
    if os.uname().sysname == 'Darwin':
        try:
            from .credentials import read
            value=read(name)
            if value:
                return value
        except (ImportError,OSError):
            pass
        try:
            for prefix in ('local.job-search-desk.','local.hr-search.'):
                p = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s',
                                    prefix + name, '-w'], capture_output=True, text=True, timeout=15)
                if p.returncode == 0:
                    return p.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            LOG.warning('Keychain unavailable; run interactively to check access')
    return ''


def safe_url(url):
    p = urlsplit(str(url).strip())
    if p.scheme != 'https' or not p.hostname or p.username or p.password:
        raise ValueError('Use a public HTTPS URL without credentials')
    if p.port not in (None, 443):
        raise ValueError('Only HTTPS port 443 is supported')
    if p.hostname.lower() in ('localhost',) or p.hostname.lower().endswith(('.local', '.internal')):
        raise ValueError('Local URLs are not supported')
    try:
        if not ipaddress.ip_address(p.hostname).is_global:
            raise ValueError('Private addresses are not supported')
    except ValueError as e:
        if 'addresses' in str(e):
            raise
    return urlunsplit(('https', p.netloc.lower(), p.path or '/', p.query, ''))


def canonical(url):
    p = urlsplit(safe_url(url))
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith('utm_')
         and k.lower() not in ('trk', 'trackingid', 'ref', 'source', 'gh_src')]
    return urlunsplit((p.scheme, p.netloc, p.path.rstrip('/') or '/', urlencode(sorted(q)), ''))


def public_host(url):
    host = urlsplit(safe_url(url)).hostname
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Feed must resolve to public addresses')


def job_id(url):
    return hashlib.sha256(canonical(url).encode()).hexdigest()[:20]


def db(root=ROOT):
    (root / 'data').mkdir(exist_ok=True, mode=0o700)
    con = sqlite3.connect(root / 'data/jobs.sqlite', timeout=20)
    con.row_factory = sqlite3.Row
    con.executescript('''
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY, url TEXT UNIQUE NOT NULL, title TEXT, company TEXT,
      location TEXT, description TEXT, source TEXT, published TEXT,
      first_seen TEXT, last_seen TEXT, score REAL, explanation TEXT,
      status TEXT DEFAULT 'new', needs_review INTEGER DEFAULT 0, artifact TEXT);
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY, at TEXT, kind TEXT, detail TEXT);
    CREATE TABLE IF NOT EXISTS digests (
      day TEXT PRIMARY KEY, state TEXT, at TEXT);
    CREATE TABLE IF NOT EXISTS digest_jobs (job_id TEXT PRIMARY KEY, sent_at TEXT);
    CREATE TABLE IF NOT EXISTS digest_leads (job_id TEXT PRIMARY KEY, sent_at TEXT);
    CREATE TABLE IF NOT EXISTS imports (hash TEXT PRIMARY KEY, at TEXT);
    CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT);
    ''')
    for column in ('apply_url','source_url','expires','eligibility','eligibility_note','duplicate_of'):
        if column not in {r[1] for r in con.execute('PRAGMA table_info(jobs)')}:
            con.execute(f'ALTER TABLE jobs ADD COLUMN {column} TEXT')
    con.commit()
    return con


def save_job(con, j, result):
    if j.get('apply_url'):
        safe_url(j['apply_url'])
    if j.get('source_url'):
        safe_url(j['source_url'])
    url = canonical(j['url'])
    ident = job_id(url)
    old = con.execute('SELECT * FROM jobs WHERE id=?', (ident,)).fetchone()
    if old and not old['needs_review'] and j.get('needs_review') and j.get('source') in ('linkedin-alert','naukri-alert','email-alert','adzuna','linkedin-public','naukri-sitemap'):
        con.execute('UPDATE jobs SET last_seen=? WHERE id=?',(now(),ident))
        con.commit()
        return ident,False
    con.execute('''INSERT INTO jobs
      (id,url,title,company,location,description,source,published,first_seen,last_seen,score,explanation,needs_review)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
      title=excluded.title,company=excluded.company,location=excluded.location,
      description=excluded.description,source=excluded.source,published=excluded.published,
      last_seen=excluded.last_seen,score=excluded.score,explanation=excluded.explanation,
      needs_review=excluded.needs_review''',
      (ident,url,j['title'],j.get('company','Unknown'),j.get('location','Unknown'),
       j.get('description',''),j.get('source','manual'),j.get('published',''),now(),now(),
       result['score'],json.dumps(result),int(j.get('needs_review',False))))
    con.execute('UPDATE jobs SET apply_url=?,source_url=?,expires=?,eligibility=?,eligibility_note=? WHERE id=?',
                (j.get('apply_url') or j['url'],j.get('source_url',''),j.get('expires',''),j.get('eligibility',''),j.get('eligibility_note',''),ident))
    con.commit()
    return ident, old is None


def event(con, kind, detail):
    con.execute('INSERT INTO events(at,kind,detail) VALUES(?,?,?)', (now(),kind,detail))
    con.commit()


GENERATED_FILES = {'tailored-resume.docx','resume-provenance.json','brief.md','contacts.md','outreach.md','job.json','.DS_Store'}
UNKNOWN_COMPANIES = {'','unknown','not supplied in alert','unverified alert','see naukri listing'}


def in_artifacts(root, path):
    base = Path(root)/'artifacts'
    return base in path.parents and '..' not in path.parts


def tidy_empty(root, folder):
    """Drop a date folder left empty (Finder metadata aside) after its last packet moved or was removed."""
    parent = folder.parent
    if parent == Path(root)/'artifacts' or not in_artifacts(root,parent) or not parent.is_dir() or parent.is_symlink():
        return
    if all(p.name == '.DS_Store' for p in parent.iterdir()):
        (parent/'.DS_Store').unlink(missing_ok=True)
        parent.rmdir()


def _norm(text):
    return re.sub(r'[^a-z0-9]+',' ',(text or '').lower()).strip()


def company_key(name):
    return ' '.join(w for w in _norm(name).split() if w not in
                    {'pvt','private','ltd','limited','inc','llc','llp','co','corp','corporation','company','plc','gmbh','the'})


def _shingles(text, n=5):
    words = _norm(text).split()
    return {' '.join(words[i:i+n]) for i in range(len(words)-n+1)}


def _same_job(a, b):
    same_title = _norm(a['title']) == _norm(b['title'])
    if a['_desc'] and b['_desc']:
        # Templated agency text reaches ~0.85 across different roles; true reposts are near-identical.
        overlap = len(a['_desc'] & b['_desc'])/len(a['_desc'] | b['_desc'])
        return overlap >= (0.8 if same_title else 0.95)
    if not same_title:
        return False
    # One side is a bare lead: the same title only merges when the places can be the same listing.
    places = [_norm(r['location']) for r in (a,b)]
    return any('remote' in p or not p or p == 'unknown' for p in places) or places[0].split()[:1] == places[1].split()[:1]


def dedupe(con, root=None):
    """Mark reposts and cross-source copies; the most complete, best-scored copy stays visible."""
    rows = [dict(r) for r in con.execute('SELECT id,url,title,company,location,description,source,score,needs_review,first_seen,artifact FROM jobs')]
    parent = {r['id']:r['id'] for r in rows}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    by_company = {}
    for r in rows:
        r['_desc'] = _shingles(r['description']) if len(r['description'] or '') >= 300 and not r['needs_review'] else set()
        key = company_key(r['company'])
        if key not in UNKNOWN_COMPANIES:
            by_company.setdefault(key,[]).append(r)
    for group in by_company.values():
        for i,a in enumerate(group):
            for b in group[i+1:]:
                if _same_job(a,b):
                    parent[find(b['id'])] = find(a['id'])
    for r in rows:
        if r['source'] == 'naukri-sitemap':
            slug = '-'+r['url'].rsplit('/job-listings-',1)[-1]+'-'
            for other in rows:
                if other['source'] != 'naukri-sitemap' and company_key(other['company']) not in UNKNOWN_COMPANIES:
                    title = '-'+'-'.join(_norm(other['title']).split())+'-'
                    company = '-'+'-'.join(company_key(other['company']).split())+'-'
                    if title in slug and company in slug:
                        parent[find(r['id'])] = find(other['id'])
                        break
    clusters = {}
    for r in rows:
        clusters.setdefault(find(r['id']),[]).append(r)
    con.execute('UPDATE jobs SET duplicate_of=NULL')
    hidden = 0
    for members in clusters.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda r:(r['needs_review'],-(r['score'] or 0),r['first_seen'] or ''))
        for dup in members[1:]:
            con.execute('UPDATE jobs SET duplicate_of=? WHERE id=?',(members[0]['id'],dup['id']))
            hidden += 1
            folder = Path(root)/dup['artifact'] if root and dup['artifact'] else None
            if folder and in_artifacts(root,folder) and folder.is_dir() and not folder.is_symlink():
                # Remove only untouched generated packets; anything the user added keeps the folder.
                if {p.name for p in folder.iterdir()} <= GENERATED_FILES:
                    for p in folder.iterdir():
                        p.unlink()
                    folder.rmdir()
                    tidy_empty(root,folder)
                    con.execute('UPDATE jobs SET artifact=NULL WHERE id=?',(dup['id'],))
    con.commit()
    return hidden
