"""Native portal searches and parsing of user-received email; never fetch portals."""
from html.parser import HTMLParser
import html
import re
from urllib.parse import urlencode,urlsplit,parse_qs
from .core import safe_url,canonical
from .discovery import queries
from .places import country_of


def search_links(config):
    result=[]
    home=config.get('home_country')
    for role in queries(config):
        for place in config['locations'][:3]:
            result.append({'portal':'LinkedIn','role':role,'location':place,'url':'https://www.linkedin.com/jobs/search/?'+urlencode({'keywords':role,'location':place,'f_TPR':'r86400'})})
            if country_of(place)=='India':
                city=place.split(',')[0].strip()
                slug=re.sub(r'[^a-z0-9]+','-',role.lower()).strip('-')
                loc=re.sub(r'[^a-z0-9]+','-',city.lower()).strip('-')
                result.append({'portal':'Naukri','role':role,'location':city,'url':f'https://www.naukri.com/{slug}-jobs-in-{loc}?'+urlencode({'k':role,'l':city})})
        if home and 'remote' in config.get('work_modes',[]):
            result.append({'portal':'LinkedIn','role':role,'location':'Remote, '+home,'url':'https://www.linkedin.com/jobs/search/?'+urlencode({'keywords':role,'location':home,'f_WT':'2','f_TPR':'r86400'})})
    return result


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__();self.items=[];self.current=None
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            self.current={'href':dict(attrs).get('href',''),'text':''}
    def handle_data(self,text):
        if self.current is not None:self.current['text']+=text
    def handle_endtag(self,tag):
        if tag=='a' and self.current is not None:
            self.current['text']=re.sub(r'\s+',' ',self.current['text']).strip()
            self.items.append(self.current);self.current=None


def portal_job_url(url):
    value=safe_url(html.unescape(url).rstrip('.,;'))
    p=urlsplit(value);host=p.hostname.lower()
    if host=='linkedin.com' or host.endswith('.linkedin.com'):
        match=re.search(r'/(?:comm/)?jobs/view/(?:[^/?]*-)?(\d+)(?:/|$)',p.path)
        ident=match.group(1) if match else parse_qs(p.query).get('currentJobId',[''])[0]
        if ident.isdigit():
            return 'linkedin-alert',f'https://www.linkedin.com/jobs/view/{ident}/'
        return None,None
    if host=='naukri.com' or host.endswith('.naukri.com'):
        if '/job-listings-' in p.path:
            return 'naukri-alert',canonical(value)
        return None,None
    return None,None


def alert_jobs(text,cleaned,subject):
    parser=Anchors();parser.feed(text)
    links=parser.items+[{'href':x,'text':''} for x in re.findall(r'https://[^\s<>"\)]+',text)]
    result={};portal_seen=any('linkedin.com/' in x['href'] or 'naukri.com/' in x['href'] for x in links)
    for anchor in links[:300]:
        link=html.unescape(anchor['href']).rstrip('.,;')
        try:
            link=safe_url(link)
            source,portal_url=portal_job_url(link)
        except ValueError:
            continue
        if not portal_url and any(x in link.lower() for x in ('unsubscribe','preferences','tracking','/pixel','/email/')):continue
        if portal_seen and not portal_url:continue  # do not import profile/footer/navigation links as jobs
        url=portal_url or link
        title=anchor['text']
        if not title or title.lower() in ('view job','apply','see job','view','apply now','see more'):
            title=subject
        # Labels are accepted only if explicitly present next to the supplied title.
        pos=cleaned.find(anchor['text']) if anchor['text'] else -1
        end=pos+500
        if pos>=0:
            for other in parser.items:
                if other['text'] and other['text']!=anchor['text']:
                    try:other_source,other_url=portal_job_url(other['href'])
                    except ValueError:continue
                    next_pos=cleaned.find(other['text'],pos+len(anchor['text']))
                    if other_url and next_pos>=0:end=min(end,next_pos)
        context=cleaned[pos:end] if pos>=0 else ''
        company=re.search(r'(?:^|\n)\s*(?:Company|Employer)\s*:\s*([^\n]+)',context,re.I)
        location=re.search(r'(?:^|\n)\s*Location\s*:\s*([^\n]+)',context,re.I)
        item={'title':title,'company':company.group(1).strip() if company else 'Not supplied in alert',
              'location':location.group(1).strip() if location else 'Unknown',
              'url':url,'apply_url':url,'source_url':url,'description':cleaned[:30000],
              'source':source or 'email-alert','needs_review':True,'published':'',
              'eligibility_note':'Email lead only. Sender, employer, location and full requirements need review; no full fit score is asserted.'}
        if url not in result or result[url]['title']==subject and title!=subject:
            result[url]=item
    return list(result.values())
