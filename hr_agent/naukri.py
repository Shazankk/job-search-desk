"""Naukri leads from its published per-city job sitemaps.

Naukri's search API requires reCAPTCHA and its job pages render with JavaScript, so this
collector reads only the sitemaps robots.txt publishes for generic clients. Each job URL
carries the title, company, places, experience range and a listing ID. Descriptions are
not available without a browser, so leads ask the user to paste them.
"""
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import time
import requests
from .discovery import FAMILY_QUERIES
from .resume import read_facts
from .scoring import resume_years

INDEX = 'https://www.naukri.com/sitemap/sitemap.xml'
HEADERS = {'User-Agent':'JobSearchDesk/1.3 (personal job search; reads published sitemaps only)',
           'Accept':'application/xml,text/xml'}
SLUG = re.compile(r'https://www\.naukri\.com/job-listings-([a-z0-9-]+?)-(\d{1,2})-to-(\d{1,2})-years?-(\d{12})')
ALIASES = {'bengaluru':'bangalore','new delhi':'delhi','navi mumbai':'mumbai','thane':'mumbai','gurgaon':'gurugram'}
ACRONYMS = {'hr','hrbp','chro','cpo','vp','avp','agm','gm','ta','it','ir','er','bd','hris','hrms','ld','md','ceo','coo','cfo','cto'}
MAX_BYTES = 25_000_000


class Blocked(RuntimeError):
    pass


def fetch(root, url, settings=None):
    settings = settings or {}
    cache = Path(root)/'data/cache/naukri'
    cache.mkdir(parents=True,exist_ok=True,mode=0o700)
    state_path = cache/'request-state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state.get('blocked_until',0) > time.time():
        raise Blocked(state.get('reason','Naukri sitemap access is paused after a refusal'))
    cached = cache/(hashlib.sha256(url.encode()).hexdigest()+'.xml')
    if cached.exists() and time.time()-cached.stat().st_mtime < 86400:
        return cached.read_text()
    wait = max(2,float(settings.get('delay_seconds',2)))-(time.time()-state.get('last',0))
    if wait > 0:
        time.sleep(wait)
    state['last'] = time.time()
    state_path.write_text(json.dumps(state));state_path.chmod(0o600)
    r = requests.get(url,headers=HEADERS,timeout=(10,60),allow_redirects=False,stream=True)
    with r:
        if r.status_code in (401,403,406,429) or 300 <= r.status_code < 400:
            reason = f'Naukri refused sitemap access (HTTP {r.status_code}); paused for 24 hours. No bypass attempted.'
            state.update(blocked_until=time.time()+86400,reason=reason)
            state_path.write_text(json.dumps(state))
            raise Blocked(reason)
        r.raise_for_status()
        raw = bytearray()
        for chunk in r.iter_content(262144):
            raw.extend(chunk)
            if len(raw) > MAX_BYTES:
                raise ValueError('Naukri sitemap exceeds size bound')
    if raw[:2] == b'\x1f\x8b':
        with gzip.GzipFile(fileobj=io.BytesIO(bytes(raw))) as handle:
            raw = handle.read(MAX_BYTES+1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Naukri sitemap exceeds size bound')
    text = bytes(raw).decode('utf-8',errors='replace')
    if '<urlset' not in text and '<sitemapindex' not in text:
        raise ValueError('Naukri returned something other than a sitemap')
    cached.write_text(text);cached.chmod(0o600)
    return text


def sitemap_files(index, city):
    """City sitemaps, or the shared other-cities files plus a city token to filter by."""
    key = ALIASES.get(city.lower().split(',')[0].strip(),city.lower().split(',')[0].strip())
    compact = re.sub(r'[^a-z]','',key)
    files = re.findall(r'<loc>\s*([^<\s]+/jobDescPages([A-Za-z]+)(?:-\d+)?\.xml(?:\.gz)?)\s*</loc>',index)
    named = [url for url,name in files if name.lower() == compact]
    if named:
        return named, None
    return [url for url,name in files if name.lower() == 'othercities'], re.sub(r'[^a-z0-9]+','-',key).strip('-')


def listing_date(ident):
    try:
        return datetime.strptime(ident[:6],'%d%m%y').replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def phrases(config):
    values = list(config.get('target_titles',[]))
    for family in config.get('search_profile',{}).get('families',[]):
        values += FAMILY_QUERIES.get(family,[])
    slugs = {re.sub(r'[^a-z0-9]+','-',v.lower()).strip('-') for v in values}
    # Listing addresses often drop filler words: "Head - HR" is published as head-hr.
    slugs |= {'-'.join(w for w in s.split('-') if w not in ('of','the','and')) for s in slugs}
    return [s.split('-') for s in slugs if s]


def title_position(tokens, wanted, window=3):
    """Earliest start of a wanted title phrase among the first tokens; titles precede company names."""
    best = None
    for phrase in wanted:
        for i in range(min(window,len(tokens)-len(phrase)+1)):
            if tokens[i:i+len(phrase)] == phrase:
                best = i if best is None else min(best,i)
                break
    return best


def display(tokens):
    return ' '.join(t.upper() if t in ACRONYMS else t.capitalize() for t in tokens)


def search(root, spec, config):
    settings = config.get('discovery',{}).get('naukri_sitemap',{})
    years = resume_years(read_facts(Path(root)/config['resume']))
    age = max(1,min(60,int(settings.get('job_age_days',30))))
    limit = max(1,min(100,int(settings.get('max_leads_per_run',40))))
    files, token = sitemap_files(fetch(root,INDEX,settings),spec['location'])
    if not files:
        raise ValueError('Naukri publishes no sitemap covering this city')
    wanted, today, found = phrases(config), datetime.now(timezone.utc), {}
    for url in files:
        for match in SLUG.finditer(fetch(root,url,settings)):
            head, low, high, ident = match.group(1), int(match.group(2)), int(match.group(3)), match.group(4)
            tokens = head.split('-')
            if token and f'-{token}-' not in f'-{head}-':
                continue
            position = title_position(tokens,wanted)
            posted = listing_date(ident)
            if position is None or not posted or not 0 <= (today-posted).days <= age:
                continue
            if years is not None and not (low <= years+3 and high >= years-3):
                continue
            closeness = abs((low+high)/2-years) if years is not None else 0
            # Reposts keep the same address text under a new ID; keep the newest.
            key = (head,low,high)
            if key not in found or posted > found[key][-1]:
                found[key] = (position,closeness,match.group(0),tokens,low,high,posted)
    ranked = sorted(found.values(),key=lambda item:item[:2])[:limit]
    result = []
    for _,_,url,tokens,low,high,posted in ranked:
        title = display(tokens)
        note = (f'Naukri sitemap lead. Experience asked: {low}–{high} years'+(f' (resume: {years})' if years is not None else '')
                +f'. Listed {posted.date().isoformat()} (date from the Naukri listing ID). Title and employer are read from the '
                'listing address; open it, confirm them and paste the full description to score it.')
        result.append({'title':title,'company':'See Naukri listing','location':spec['location'],
                       'url':url,'apply_url':url,'source_url':url,'source':'naukri-sitemap','needs_review':True,
                       'published':posted.isoformat(),'eligibility_note':note,
                       'description':f'Naukri listing: {title}\nExperience: {low}–{high} years\nListed: {posted.date().isoformat()}'})
    return result
