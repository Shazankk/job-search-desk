"""Low-volume public guest-page collector; no login, cookies, proxies or bypass.

Endpoint workflow adapted from ashutoshgh/ai-job-search-india's MIT-licensed
linkedin-search (original copyright 2026 Mads Lorentzen). See THIRD_PARTY_NOTICES.
The stdlib HTML parser, budgets, cache and integration below are local additions.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode
import requests

BASE='https://www.linkedin.com/jobs-guest/jobs/api/'
HEADERS={'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
         'Accept':'text/html,application/xhtml+xml','Accept-Language':'en-US,en;q=0.9','X-Requested-With':'XMLHttpRequest'}


class AccessBlocked(RuntimeError):
    pass


class Node:
    def __init__(self,tag='',attrs=()):
        self.tag=tag;self.attrs=dict(attrs);self.children=[]
    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child,Node):yield from child.walk()
    def by_class(self,name):
        return next((n for n in self.walk() if name in (n.attrs.get('class') or '').split()),None)
    def text(self):
        if self.tag in ('script','style'):return ''
        text=''.join(c.text() if isinstance(c,Node) else c for c in self.children)
        return text+('\n' if self.tag in ('p','div','li','br','h1','h2','h3','h4','ul') else '')


class DOM(HTMLParser):
    def __init__(self,html):
        super().__init__(convert_charrefs=True)
        self.root=Node();self.stack=[self.root];self.feed(html)
    def handle_starttag(self,tag,attrs):
        node=Node(tag,attrs);self.stack[-1].children.append(node)
        if tag not in ('br','hr','img','input','meta','link','source','wbr','area','base','embed','param'):
            self.stack.append(node)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:
                self.stack=self.stack[:i];break
    def handle_data(self,text):
        self.stack[-1].children.append(text)


def clean(node):
    return re.sub(r'\s+',' ',node.text()).strip() if node else ''


def parse_cards(html):
    root=DOM(html).root
    cards={}
    for node in root.walk():
        match=re.fullmatch(r'urn:li:jobPosting:(\d+)',node.attrs.get('data-entity-urn',''))
        if not match:continue
        ident=match.group(1)
        title=clean(node.by_class('base-search-card__title')) or clean(node.by_class('sr-only'))
        if not title:continue
        dated=next((n.attrs['datetime'] for n in node.walk() if n.tag=='time' and n.attrs.get('datetime')), '')
        cards[ident]={'external_id':ident,'title':title,
                     'company':clean(node.by_class('base-search-card__subtitle')) or 'Unknown',
                     'location':clean(node.by_class('job-search-card__location')) or 'Unknown',
                     'published':dated,'url':f'https://www.linkedin.com/jobs/view/{ident}/',
                     'apply_url':f'https://www.linkedin.com/jobs/view/{ident}/',
                     'source_url':f'https://www.linkedin.com/jobs/view/{ident}/',
                     'description':'','source':'linkedin-public','needs_review':True}
    return list(cards.values())


def parse_detail(html,card):
    root=DOM(html).root
    title=clean(root.by_class('top-card-layout__title')) or clean(root.by_class('topcard__title'))
    company=clean(root.by_class('topcard__org-name-link'))
    loc=clean(root.by_class('topcard__flavor--bullet'))
    description=root.by_class('show-more-less-html__markup') or root.by_class('description__text')
    text=re.sub(r'\n[ \t]*\n+','\n\n',description.text()).strip() if description else ''
    loc=loc or card['location']
    if re.search(r'\bremote\b',card['location'],re.I) and not re.search(r'\bremote\b',loc,re.I):
        loc='Remote, '+loc  # found through LinkedIn's remote filter; the detail page omits it
    value={**card,'title':title or card['title'],'company':company or card['company'],
           'location':loc,'description':text,'needs_review':len(text)<100}
    return value


def fetch_html(root,path,params=None,settings=None):
    settings=settings or {}
    cache=Path(root)/'data/cache/linkedin';cache.mkdir(parents=True,exist_ok=True,mode=0o700)
    state_path=cache/'request-state.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    now=time.time();day=datetime.now(timezone.utc).date().isoformat()
    if state.get('day')!=day:state={**state,'day':day,'count':0}
    if state.get('blocked_until',0)>now:
        raise AccessBlocked(state.get('reason','LinkedIn public access is paused after a block'))
    import hashlib
    url=BASE+path+('?' + urlencode(params) if params else '')
    key=hashlib.sha256(url.encode()).hexdigest()
    cached=cache/(key+'.json')
    if cached.exists():
        data=json.loads(cached.read_text())
        if now-data['at']<86400:return data['html']
    budget=max(1,min(80,int(settings.get('daily_request_limit',50))))
    if state.get('count',0)>=budget:
        raise AccessBlocked('LinkedIn daily request budget reached; cached results and email alerts remain available')
    delay=max(2,min(10,float(settings.get('delay_seconds',3))))
    wait=delay-(now-state.get('last',0))
    if wait>0:time.sleep(wait)
    state.update(count=state.get('count',0)+1,last=time.time())
    state_path.write_text(json.dumps(state));state_path.chmod(0o600)
    r=requests.get(url,headers=HEADERS,timeout=(10,25),allow_redirects=False,stream=True)
    with r:
        if r.status_code in (401,403,429,999) or 300<=r.status_code<400:
            reason=f'LinkedIn public access blocked/redirected (HTTP {r.status_code}); paused for 24 hours. No bypass attempted.'
            state.update(blocked_until=time.time()+86400,reason=reason)
            state_path.write_text(json.dumps(state))
            raise AccessBlocked(reason)
        if r.status_code==404:return ''
        r.raise_for_status()
        raw=bytearray()
        for chunk in r.iter_content(65536):
            raw.extend(chunk)
            if len(raw)>3_000_000:raise ValueError('LinkedIn response exceeds size bound')
    text=raw.decode('utf-8',errors='replace')
    if re.search(r'/checkpoint/challenge|id=[\"\']captcha|class=[\"\']authwall',text,re.I):
        state.update(blocked_until=time.time()+86400,reason='LinkedIn access challenge detected; paused without bypass')
        state_path.write_text(json.dumps(state));raise AccessBlocked(state['reason'])
    cached.write_text(json.dumps({'at':time.time(),'html':text}));cached.chmod(0o600)
    return text


def detail_budget(settings):
    return max(0,min(25,int(settings.get('max_details_per_run',15))))


def search(root,spec,config):
    from .scoring import score
    from .resume import read_facts
    settings=config.get('discovery',{}).get('linkedin_public',{})
    params={'keywords':spec['query'],'location':spec['location'],'start':0,
            'f_TPR':'r'+str(max(1,min(30,int(settings.get('job_age_days',30))))*86400)}
    if spec.get('remote'):
        params['f_WT']='2'
    elif spec.get('work_type'):
        params['f_WT']=spec['work_type']
    raw=fetch_html(root,'seeMoreJobPostings/search',params,settings)
    cards=parse_cards(raw)
    if spec.get('remote'):
        for card in cards:
            if not re.search(r'\bremote\b',card['location'],re.I):
                card['location']='Remote, '+card['location']
    if raw.strip() and not cards:
        if re.search(r'authwall|sign.in|captcha|checkpoint',raw,re.I):
            raise AccessBlocked('LinkedIn returned an access page instead of job cards; use alert intake')
        if '<li' in raw.lower() or 'jobposting' in raw.lower():
            raise ValueError('LinkedIn markup changed; parser could not verify any job cards')
    facts=read_facts(Path(root)/config['resume'])
    cards.sort(key=lambda j:score(j,facts,config)['score'],reverse=True)
    details=config.setdefault('_linkedin_detail_cache',{})
    remaining=config.setdefault('_linkedin_detail_remaining',detail_budget(settings))
    result=[]
    for card in cards:
        if card['external_id'] in details:
            result.append(details[card['external_id']]);continue
        basic=score(card,facts,config)
        if remaining>0 and basic['role_aligned'] and basic['location_eligible']:
            remaining-=1;config['_linkedin_detail_remaining']=remaining
            detail_error=''
            try:
                detail=fetch_html(root,'jobPosting/'+card['external_id'],settings=settings)
                if detail:
                    card=parse_detail(detail,card)
                    if card['needs_review'] and re.search(r'authwall|sign.in|captcha|checkpoint',detail,re.I):
                        raise AccessBlocked('LinkedIn description access unavailable; retained as a lead')
            except AccessBlocked as exc:
                # Preserve already collected cards, then stop LinkedIn requests in this run.
                config['_linkedin_paused']=True
                config['_linkedin_pause_reason']=str(exc)
                result.append(card)
                result.extend(j for j in cards if j not in result and j['external_id'] not in {x['external_id'] for x in result})
                break
            except (requests.RequestException,ValueError) as exc:
                # Keep the useful card and report that its description was unavailable.
                detail_error=type(exc).__name__
            if card['needs_review'] and not config.get('_linkedin_paused'):
                config.setdefault('_linkedin_detail_errors',[]).append(detail_error or 'No complete public description')
        if not card['needs_review']:details[card['external_id']]=card
        result.append(card)
    return result


def enrich_leads(root,con,config):
    """Fetch full public descriptions for stored LinkedIn leads, including links from alert emails.

    Uses the run's remaining description budget, so total requests stay bounded.
    Returns (completed, closed, errors).
    """
    from .core import save_job, event
    from .scoring import score
    from .resume import read_facts
    settings=config.get('discovery',{}).get('linkedin_public',{})
    if not settings.get('enabled') or config.get('_linkedin_paused'):
        return 0,0,0
    remaining=config.setdefault('_linkedin_detail_remaining',detail_budget(settings))
    rows=con.execute("""SELECT * FROM jobs WHERE needs_review=1 AND duplicate_of IS NULL
      AND source IN ('linkedin-public','linkedin-alert') AND status NOT IN ('dismissed','applied','closed')
      ORDER BY score DESC,first_seen DESC""").fetchall()
    candidates=[]
    for row in rows:
        detail=json.loads(row['explanation'])
        unknown=row['location'] in ('','Unknown')
        match=re.search(r'/jobs/view/(\d+)',row['url'])
        if match and detail.get('role_aligned') and (detail.get('location_eligible') or unknown):
            candidates.append((unknown,row,match.group(1)))
    facts=read_facts(Path(root)/config['resume'])
    completed=closed=errors=0
    for _,row,ident in sorted(candidates,key=lambda c:c[0]):
        if remaining<=0:
            break
        remaining-=1;config['_linkedin_detail_remaining']=remaining
        try:
            html=fetch_html(root,'jobPosting/'+ident,settings=settings)
        except AccessBlocked as exc:
            config['_linkedin_paused']=True;config['_linkedin_pause_reason']=str(exc)
            break
        except (requests.RequestException,ValueError):
            errors+=1;continue
        if not html:
            con.execute("UPDATE jobs SET status='closed' WHERE id=?",(row['id'],))
            event(con,'source_closed','LinkedIn listing no longer available: '+row['title'])
            closed+=1;continue
        card={**dict(row),'external_id':ident}
        job=parse_detail(html,card)
        if job['needs_review']:
            errors+=1;continue
        job.update(source='linkedin-public',eligibility_note='',eligibility='')
        save_job(con,job,score(job,facts,config))
        completed+=1
    con.commit()
    return completed,closed,errors
