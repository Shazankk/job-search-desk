"""Role/location-driven searches. API credentials are never written to URLs in logs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlencode
import time
import requests
from .core import secret, safe_url
from .sources import get, plain
from .places import country_of, country_info, country_terms

FAMILY_QUERIES = {
 'hr':['human resources','HR business partner','HR manager'],
 'software':['software engineer','backend engineer','software developer'],
 'data':['data analyst','data engineer','data scientist'],
 'product':['product manager','product owner'],
 'project':['project manager','program manager'],
 'finance':['finance manager','financial analyst','accountant'],
 'marketing':['marketing manager','digital marketing'],
 'sales':['sales manager','business development'],
 'design':['product designer','UX designer'],
 'operations':['operations manager','supply chain'],
 'support':['customer success','customer support'],
 'security':['security engineer','security analyst'],
 'healthcare':['registered nurse','clinical research','healthcare administrator'],
 'education':['teacher','lecturer','instructional designer'],
 'legal':['legal counsel','paralegal','compliance officer'],
 'engineering':['mechanical engineer','civil engineer','electrical engineer']}


def queries(config):
    settings=config.get('discovery',{})
    explicit=settings.get('queries',[])
    if explicit:
        values=explicit
    else:
        values=[q for name in config.get('search_profile',{}).get('families',[]) for q in FAMILY_QUERIES.get(name,[])]
        values+=config['target_titles']
    return list(dict.fromkeys(q.strip() for q in values if isinstance(q,str) and q.strip()))[:max(1,min(6,int(settings.get('max_queries',3))))]


def plan(config):
    settings=config.get('discovery',{})
    out=[]
    home=config.get('home_country')
    modes=set(config.get('work_modes') or ('onsite','hybrid','remote'))
    remote_on=bool(home) and 'remote' in modes
    linkedin=settings.get('linkedin_public',{})
    if linkedin.get('enabled',False):
        values=queries(config) if settings.get('queries') else list(config.get('target_titles',[])[:1])+queries(config)
        seen=set();selected=[]
        for value in values:
            if value.casefold() not in seen:
                seen.add(value.casefold());selected.append(value)
        budget=max(1,min(8,int(linkedin.get('max_searches_per_run',5))))
        office=modes&{'onsite','hybrid'}
        # On-site/hybrid only: LinkedIn's own work-type filter (1 on-site, 3 hybrid); both: no filter.
        work_type={'onsite':'1','hybrid':'3'}[next(iter(office))] if len(office)==1 else ''
        remote=remote_on and (budget>=2 or not office)
        remote_budget=(budget if not office else 1) if remote else 0
        budget-=remote_budget
        for query in selected if office else []:
            for loc in config['locations'][:3]:
                if budget<=0:break
                out.append({'provider':'linkedin_public','query':query,'location':loc,'work_type':work_type,'scope':'Unofficial public guest pages; no login or API key; bounded volume'})
                budget-=1
            if budget<=0:break
        for query in selected[:remote_budget]:
            out.append({'provider':'linkedin_public','query':query,'location':home,'remote':True,'scope':f'LinkedIn remote filter, {home}; no login or API key; bounded volume'})
    if settings.get('naukri_sitemap',{}).get('enabled',False):
        for loc in [x for x in config['locations'] if country_of(x)=='India'][:3]:
            out.append({'provider':'naukri_sitemap','query':'resume target titles','location':loc,'scope':'Published Naukri sitemap; title and experience filter; paste descriptions'})
    for query in queries(config):
        if settings.get('himalayas',{}).get('enabled',False) and remote_on:
            out.append({'provider':'himalayas','query':query,'location':'Remote, '+home,'country':home,'scope':f'Remote roles open to {home}; country and timezone checked locally'})
        if settings.get('adzuna',{}).get('enabled',False):
            for loc in config['locations'][:3]:
                code=(country_info(country_of(loc) or '') or {}).get('adzuna')
                if code and ',' in loc:
                    out.append({'provider':'adzuna','query':query,'location':loc,'country_code':code,'scope':'Configured radius; key required'})
    return out


def cached_public(root,url):
    folder=Path(root)/'data/cache'
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=folder/(hashlib.sha256(url.encode()).hexdigest()+'.json')
    if path.exists():
        value=json.loads(path.read_text())
        if time.time()-value['saved']<86400:
            return value['data']
    value=json.loads(get(url))
    path.write_text(json.dumps({'saved':time.time(),'data':value}))
    path.chmod(0o600)
    return value


def himalayas_job(item,home):
    countries=item.get('locationRestrictions') or []
    zones=item.get('timezoneRestrictions')
    info=country_info(home) or {}
    names=set(country_terms(home))|{info.get('iso2','').lower()}
    countries_ok=not countries or any(str(c).lower() in names for c in countries)
    zones_ok=bool(zones) and any(float(z) in info.get('utc',[]) for z in zones)
    desc=plain(item.get('description',''))
    restriction=re.search(r'(?:remote\s*[,:(–-]?\s*(?:europe|european union|united states only|us only|usa only)|(?:must|need to)\s+(?:be\s+)?(?:based|located|reside)\s+in\s+(?:the\s+)?(?:us\b|usa\b|united states|europe|uk\b|united kingdom))',desc[:3000],re.I)
    eligible=countries_ok and zones_ok and not restriction
    eligibility='confirmed' if eligible else 'excluded' if not countries_ok or zones and not zones_ok else 'unconfirmed'
    note=(f'{home} is allowed by source country/timezone metadata. Confirm work authorization and employer terms.' if eligible
          else f'Country/timezone metadata or description conflicts with {home} eligibility; review before applying.')
    expiry=item.get('expiryDate')
    expires=datetime.fromtimestamp(float(expiry),timezone.utc).isoformat() if expiry else ''
    guid=safe_url(item['guid'])
    if not guid.startswith('https://himalayas.app/'):
        raise ValueError('Unexpected Himalayas job identifier')
    return {'title':item['title'],'company':item['companyName'],'url':guid,
            'apply_url':item['applicationLink'],'source_url':guid,'source':'himalayas',
            'location':f'Remote, {home}' if eligible else f'Remote; {home} eligibility not established',
            'description':desc,'published':'','expires':expires,'eligibility':eligibility,
            'eligibility_note':note,'needs_review':len(desc)<100}


def search_himalayas(root,spec,settings):
    result=[]
    pages=max(1,min(5,int(settings.get('pages_per_query',2))))
    for page in range(1,pages+1):
        url='https://himalayas.app/jobs/api/search?'+urlencode({'q':spec['query'],'country':spec['country'],'sort':'recent','page':page})
        data=cached_public(root,url)
        jobs=data.get('jobs',[])
        if not jobs:
            break
        for item in jobs:
            j=himalayas_job(item,spec['country'])
            if j['expires'] and j['expires']<=datetime.now(timezone.utc).isoformat():
                continue
            safe_url(j['apply_url'])  # validate; preserve the supplied applicationLink unchanged
            result.append(j)
    return result


def search_adzuna(root,spec,settings):
    app_id,app_key=secret('ADZUNA_APP_ID'),secret('ADZUNA_APP_KEY')
    if not app_id or not app_key:
        raise ValueError('Adzuna requires ADZUNA_APP_ID and ADZUNA_APP_KEY in Keychain')
    result=[]
    pages=max(1,min(3,int(settings.get('pages_per_query',1))))
    cache_dir=Path(root)/'data/cache';cache_dir.mkdir(parents=True,exist_ok=True)
    for page in range(1,pages+1):
        params={'what':spec['query'],'where':spec['location'].split(',')[0].strip(),'distance':int(settings.get('radius_km',25)),
                'results_per_page':50,'max_days_old':30,'sort_by':'date'}
        ident=hashlib.sha256(json.dumps([spec['country_code'],params,page],sort_keys=True).encode()).hexdigest()
        cache=cache_dir/('adzuna-'+ident+'.json')
        cached=json.loads(cache.read_text()) if cache.exists() else None
        if cached and time.time()-cached['saved']<86400:
            data=cached['data']
        else:
            # Required credentials travel only to the fixed HTTPS vendor endpoint. No URL/error body is logged.
            r=requests.get(f"https://api.adzuna.com/v1/api/jobs/{spec['country_code']}/search/{page}",
                params={**params,'app_id':app_id,'app_key':app_key},timeout=(10,30))
            r.raise_for_status()
            if len(r.content)>12_000_000:
                raise ValueError('Adzuna response exceeds size limit')
            data=r.json();cache.write_text(json.dumps({'saved':time.time(),'data':data}));cache.chmod(0o600)
        items=data.get('results',[])
        if not items:break
        for item in items:
            url=safe_url(item['redirect_url'])
            result.append({'title':plain(item['title']),'company':item.get('company',{}).get('display_name','Unknown'),
                'url':url,'apply_url':item['redirect_url'],'source_url':'https://www.adzuna.com/',
                'location':item.get('location',{}).get('display_name','Unknown'),
                'description':plain(item.get('description','')),'published':item.get('created',''),
                'source':'adzuna','needs_review':True,
                'eligibility_note':'Search lead: Adzuna descriptions may be excerpts. Import the full job description before preparing documents.'})
    return result


def search(root,spec,config):
    settings=config.get('discovery',{}).get(spec['provider'],{})
    if spec['provider']=='linkedin_public':
        from .linkedin_public import search as linkedin_search
        return linkedin_search(root,spec,config)
    if spec['provider']=='naukri_sitemap':
        from .naukri import search as naukri_search
        return naukri_search(root,spec,config)
    if spec['provider']=='himalayas':
        return search_himalayas(root,spec,settings)
    if spec['provider']=='adzuna':
        return search_adzuna(root,spec,settings)
    raise ValueError('Unsupported search provider')


def coverage_report(con):
    """Observed source contribution, not a claim about market coverage/hiring odds."""
    rows=con.execute("SELECT * FROM jobs WHERE status NOT IN ('dismissed','closed')").fetchall()
    sets={}
    for row in rows:
        detail=json.loads(row['explanation'])
        if not detail.get('role_aligned') or not detail.get('location_eligible'):
            continue
        normalize=lambda s:re.sub(r'[^a-z0-9]+',' ',s.lower()).strip()
        # Conservative cross-source signature: multiple requisitions may collapse.
        area='remote' if 'remote' in row['location'].lower() else normalize(row['location'])
        ident=(normalize(row['title']),normalize(row['company']),area)
        sets.setdefault(row['source'],set()).add(ident)
    baseline=set().union(*(v for k,v in sets.items() if k!='adzuna'))
    extra=sets.get('adzuna',set())-baseline
    active=con.execute("SELECT value FROM metadata WHERE key='search_fingerprint'").fetchone()
    checked_at=con.execute("SELECT value FROM metadata WHERE key='adzuna_checked_fingerprint'").fetchone()
    checked=bool(active and checked_at and active[0]==checked_at[0])
    return {'counts':{k:len(v) for k,v in sets.items()},'baseline':len(baseline),'additional_adzuna':len(extra) if checked else None,
            'percent_added':round(100*len(extra)/len(baseline),1) if checked and baseline else None,
            'note':'Observed relevant leads grouped by title/company/location, not total market coverage or interview odds. Some duplicates or separate requisitions may be misclassified.'}


def verify_himalayas(root,job):
    """Daily cached single-job check before preparing a retained remote listing."""
    from urllib.parse import urlsplit
    guid=safe_url(job['source_url'] or job['url'])
    if urlsplit(guid).hostname!='himalayas.app':
        raise ValueError('Invalid source job URL')
    endpoint='https://himalayas.app/jobs/api'+urlsplit(guid).path
    try:
        data=cached_public(root,endpoint)
    except requests.HTTPError as exc:
        if exc.response.status_code in (404,410):
            return False
        raise
    return bool(data.get('job'))
