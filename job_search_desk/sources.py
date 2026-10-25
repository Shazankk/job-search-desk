"""Public GET adapters. No application endpoints or authenticated browser sessions."""
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlsplit
import xml.etree.ElementTree as ET
import requests
from .core import safe_url, public_host


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'):
            self.hidden += 1
        if tag in ('p','br','li','div'):
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style'):
            self.hidden = max(0,self.hidden-1)
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain(value):
    p = TextOnly()
    p.feed(html.unescape(str(value or '')))
    return re.sub(r'\n\s*\n','\n',''.join(p.parts)).strip()


def get(url, attempts=3):
    """Bound size/time/retries and validate every redirect. No cookies persisted."""
    for attempt in range(attempts):
        try:
            current = url
            for _ in range(4):
                public_host(current)
                with requests.get(current, headers={'User-Agent':'LocalHRSearch/1.0 (public job feeds)'},
                                  timeout=(10,30), allow_redirects=False, stream=True) as r:
                    if r.is_redirect:
                        from urllib.parse import urljoin
                        current = safe_url(urljoin(current, r.headers['Location']))
                        continue
                    r.raise_for_status()
                    chunks, size = [], 0
                    for chunk in r.iter_content(65536):
                        size += len(chunk)
                        if size > 12_000_000:
                            raise ValueError('Feed exceeds 12 MB limit')
                        chunks.append(chunk)
                    return b''.join(chunks)
            raise ValueError('Too many redirects')
        except (requests.Timeout, requests.ConnectionError):
            if attempt == attempts-1:
                raise
            time.sleep(attempt+1)
        except requests.HTTPError as exc:
            if exc.response.status_code not in (429,500,502,503,504) or attempt == attempts-1:
                raise
            time.sleep(min(10, 2**attempt))
    raise ValueError('Feed failed')


def normalize(item, source):
    kind = source['type']
    base = {'company': source.get('company',source.get('board','Unknown')), 'source':kind}
    if kind == 'greenhouse':
        base.update(title=item['title'],url=item['absolute_url'],location=item.get('location',{}).get('name','Unknown'),
                    description=plain(item.get('content','')),published=item.get('updated_at',''))
        # Greenhouse updated_at is an update date, not original publication date.
        base['published'] = ''
    elif kind == 'lever':
        cats = item.get('categories',{})
        loc = cats.get('location','Unknown')
        loc += ' ' + item.get('workplaceType','')
        extra = '\n'.join(plain(x.get('content','')) for x in item.get('lists',[]))
        base.update(title=item['text'],url=item['hostedUrl'],location=loc,
                    description=plain(item.get('description',''))+'\n'+extra+'\n'+plain(item.get('additional','')),
                    published='')
    elif kind == 'ashby':
        locations = [item.get('location','')] + [x.get('location','') for x in item.get('secondaryLocations',[])]
        loc = ' / '.join(locations) + ' ' + item.get('workplaceType','')
        base.update(title=item['title'],url=item['jobUrl'],location=loc,
                    description=item.get('descriptionPlain') or plain(item.get('descriptionHtml','')),
                    published=item.get('publishedAt',''))
    safe_url(base['url'])
    return base


def fetch(source):
    kind = source['type']
    board = quote(source.get('board',''),safe='')
    if kind == 'greenhouse':
        data = json.loads(get(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true'))['jobs']
    elif kind == 'lever':
        host = 'api.eu.lever.co' if source.get('region') == 'eu' else 'api.lever.co'
        data, skip = [], 0
        for _ in range(20):
            page = json.loads(get(f'https://{host}/v0/postings/{board}?mode=json&skip={skip}&limit=100'))
            data.extend(page)
            if len(page) < 100:
                break
            skip += 100
        else:
            raise ValueError('Lever board exceeds 2000 jobs; narrow board configuration')
    elif kind == 'ashby':
        data = [j for j in json.loads(get(f'https://api.ashbyhq.com/posting-api/job-board/{board}'))['jobs']
                if j.get('isListed',True)]
    elif kind == 'rss':
        return rss(get(safe_url(source['url'])),source)
    else:
        raise ValueError('Unsupported source type')
    return [normalize(item,source) for item in data]


def rss(raw, source):
    root = ET.fromstring(raw)
    atom = '{http://www.w3.org/2005/Atom}'
    items = root.findall('./channel/item') or root.findall(atom+'entry')
    jobs = []
    for x in items:
        title = x.findtext('title') or x.findtext(atom+'title') or 'Untitled alert'
        link = x.findtext('link')
        if not link:
            links = [y for y in x.findall(atom+'link') if y.get('rel','alternate') == 'alternate']
            link = links[0].get('href') if links else ''
        if not link:
            continue
        desc = plain(x.findtext('description') or x.findtext(atom+'content') or x.findtext(atom+'summary') or '')
        date = x.findtext('pubDate') or x.findtext(atom+'published') or ''
        try:
            date = parsedate_to_datetime(date).isoformat()
        except (TypeError,ValueError):
            pass
        jobs.append({'title':title,'url':safe_url(link),'company':source.get('company','Unknown'),
                     'location':source.get('location','Unknown'),'description':desc,'source':'rss',
                     'published':date,'needs_review':source.get('location','Unknown') == 'Unknown' or len(desc)<200})
    return jobs


def read_import(path):
    value = json.loads(path.read_text())
    jobs = value if isinstance(value,list) else [value]
    for j in jobs:
        if not str(j.get('title','')).strip():
            raise ValueError('Import requires title')
        safe_url(j['url'])
        j['description'] = plain(j.get('description',''))
        j['source'] = 'manual'
        j['needs_review'] = bool(j.get('needs_review')) or len(j['description']) < 100
    return jobs


def read_alert(path):
    msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    body = msg.get_body(preferencelist=('html','plain'))
    text = body.get_content() if body else (msg.get_content() if not msg.is_multipart() else '')
    from .portals import alert_jobs
    return alert_jobs(str(text),plain(text),str(msg.get('Subject','Job alert')))
