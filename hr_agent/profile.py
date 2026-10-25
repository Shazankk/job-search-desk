"""Resume-derived search settings. Suggestions never become resume claims."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path

HR_GROUPS = {
 'strategy': ['people strategy', 'strategic hr', 'business partner', 'hrbp'],
 'operations': ['hr operations', 'people operations', 'hr policies', 'payroll'],
 'performance': ['performance management', 'appraisals', 'kras', 'kpis'],
 'talent': ['talent acquisition', 'recruitment', 'workforce planning'],
 'rewards': ['compensation', 'benefits', 'rewards'],
 'development': ['learning', 'l&d', 'leadership development', 'training'],
 'culture': ['engagement', 'culture', 'employee experience', 'gptw'],
 'compliance': ['compliance', 'posh', 'labour law', 'labor law'],
 'change': ['m&a', 'integration', 'change management', 'organisation development'],
 'analytics': ['analytics', 'dashboards', 'hris', 'hrms', 'keka', 'zoho']}

FAMILIES = {
 'hr': {'titles':['HR Head','Head of HR','HR Director','Director HR','Human Resources','HR Manager','HR Business Partner','HRBP','People Partner','People Operations','People and Culture','People Practice','CHRO','Chief Human Resources Officer','Chief People Officer','HR Leader'],
        'signals':['hrbp','human resources','strategic hr','talent acquisition','people operations','payroll'], 'groups':HR_GROUPS},
 'software': {'titles':['Software Engineer','Software Developer','Backend Engineer','Backend Developer','Frontend Engineer','Frontend Developer','Full Stack Developer','Full Stack Engineer','Python Developer','Java Developer','Engineering Manager','Software Architect','DevOps Engineer','Site Reliability Engineer','Platform Engineer','Mobile Developer','Technical Lead'],
        'signals':['software engineer','software developer','backend','frontend','full stack','devops','kubernetes','react','django'],
        'groups':{'system design':['system design','distributed systems'], 'apis':['rest','restful','api design','graphql'], 'testing':['unit testing','pytest','automated testing'], 'delivery':['ci/cd','continuous integration','continuous delivery'], 'observability':['observability','monitoring','opentelemetry']}},
 'data': {'titles':['Data Analyst','Data Engineer','Data Scientist','Analytics Engineer','Business Intelligence Analyst','BI Analyst','Machine Learning Engineer','Analytics Manager'],
        'signals':['data analyst','data engineer','data scientist','machine learning','power bi','tableau','data pipelines','statistical modeling'],
        'groups':{'pipelines':['etl','elt','data pipelines'], 'statistics':['statistics','statistical modeling','hypothesis testing'], 'machine learning':['machine learning','predictive modeling'], 'visualization':['data visualization','business intelligence']}},
 'product': {'titles':['Product Manager','Product Owner','Product Lead','Head of Product','Product Director'],
        'signals':['product manager','product owner','product strategy','product roadmap','product discovery'],
        'groups':{'product strategy':['product strategy','product roadmap','roadmap'], 'discovery':['product discovery','user research'], 'experimentation':['a/b testing','experimentation'], 'prioritization':['prioritization','backlog']}},
 'project': {'titles':['Project Manager','Program Manager','Delivery Manager','Scrum Master','PMO Manager','Project Coordinator'],
        'signals':['project manager','program manager','scrum master','project management','pmp','pmo'],
        'groups':{'project management':['project management','program management'], 'agile':['agile','scrum'], 'risk':['risk management','risk register'], 'delivery':['project delivery','delivery management'], 'stakeholders':['stakeholder management']}},
 'finance': {'titles':['Accountant','Finance Manager','Financial Analyst','Finance Director','Financial Controller','Accounts Manager','FP&A Analyst','Auditor','Chartered Accountant'],
        'signals':['accountant','financial analyst','financial reporting','fp&a','chartered accountant','accounts payable','financial controller'],
        'groups':{'reporting':['financial reporting','financial statements'], 'accounting':['accounting','general ledger','bookkeeping'], 'forecasting':['financial forecasting','fp&a','budgeting'], 'audit':['audit','auditing'], 'tax':['taxation','gst','tax compliance'], 'valuation':['valuation','financial modeling']}},
 'marketing': {'titles':['Marketing Manager','Marketing Director','Digital Marketing Manager','Content Strategist','SEO Specialist','Growth Manager','Brand Manager','Performance Marketing Manager','Marketing Executive'],
        'signals':['digital marketing','marketing manager','seo','google ads','content marketing','performance marketing'],
        'groups':{'seo':['seo','search engine optimization'], 'paid media':['google ads','paid media','ppc','meta ads'], 'content':['content marketing','copywriting','content strategy'], 'campaigns':['campaign management','marketing campaigns'], 'measurement':['google analytics','ga4','conversion optimization'], 'email marketing':['email marketing','marketing automation']}},
 'sales': {'titles':['Sales Manager','Sales Director','Account Executive','Account Manager','Business Development Manager','Sales Development Representative','Business Development Executive','Head of Sales'],
        'signals':['sales manager','sales director','account executive','business development','sales pipeline','quota'],
        'groups':{'pipeline':['sales pipeline','pipeline management'], 'selling':['b2b sales','enterprise sales','solution selling'], 'negotiation':['negotiation','negotiations'], 'prospecting':['prospecting','lead generation'], 'crm':['crm','salesforce','hubspot']}},
 'design': {'titles':['Product Designer','UX Designer','UI Designer','UX Researcher','Graphic Designer','Design Lead'],
        'signals':['ux designer','ui designer','product designer','figma','interaction design','graphic designer'],
        'groups':{'research':['user research','usability testing'], 'interaction':['interaction design','wireframes'], 'prototyping':['prototyping','prototype'], 'systems':['design systems'], 'visual':['visual design','graphic design']}},
 'operations': {'titles':['Operations Manager','Operations Director','Supply Chain Manager','Logistics Manager','Procurement Manager','Warehouse Manager'],
        'signals':['supply chain','logistics','procurement','warehouse management','operations manager'],
        'groups':{'supply chain':['supply chain','demand planning'], 'logistics':['logistics','transportation'], 'procurement':['procurement','sourcing'], 'inventory':['inventory','warehouse management'], 'process':['process improvement','lean','six sigma']}},
 'support': {'titles':['Customer Success Manager','Customer Support Specialist','Customer Service Manager','Technical Support Engineer','Customer Success Lead'],
        'signals':['customer success','customer support','technical support','zendesk'],
        'groups':{'support':['customer support','technical support','customer service'], 'success':['customer success','customer retention'], 'service':['sla','ticketing','incident management']}},
 'security': {'titles':['Security Engineer','Security Analyst','Cybersecurity Analyst','Information Security Manager','SOC Analyst','Application Security Engineer'],
        'signals':['cybersecurity','security analyst','security engineer','siem','penetration testing','soc analyst'],
        'groups':{'security testing':['penetration testing','vulnerability assessment'], 'response':['incident response','threat hunting'], 'governance':['iso 27001','nist','information security'], 'soc':['siem','soc operations']}},
 'healthcare': {'titles':['Registered Nurse','Staff Nurse','Pharmacist','Physician','Clinical Research Associate','Medical Laboratory Technician','Healthcare Administrator','Medical Officer','Clinical Research Coordinator','Hospital Administrator'],
        'signals':['registered nurse','clinical nursing','clinical pharmacy','patient assessment','clinical research','medical laboratory','healthcare administration','medical officer'],
        'groups':{'patient care':['patient assessment','patient care','medication administration'], 'pharmacy':['clinical pharmacy','dispensing medications','medication reconciliation'], 'clinical research':['clinical trials','good clinical practice','clinical research'], 'laboratory':['specimen collection','laboratory testing','clinical diagnostics'], 'administration':['healthcare administration','hospital operations','medical records']}},
 'education': {'titles':['Teacher','Lecturer','Professor','Instructional Designer','Education Counsellor','Academic Coordinator','Corporate Trainer','School Teacher','Assistant Professor','Learning and Development Trainer'],
        'signals':['classroom teaching','lesson planning','curriculum development','instructional design','student counselling','academic coordination','faculty development','corporate training'],
        'groups':{'teaching':['classroom teaching','lesson planning','classroom management'], 'curriculum':['curriculum development','curriculum design','instructional design'], 'assessment':['student assessment','learning outcomes','educational assessment'], 'student support':['student counselling','academic advising','student engagement'], 'training':['training delivery','adult learning','corporate training']}},
 'legal': {'titles':['Lawyer','Advocate','Legal Counsel','Paralegal','Compliance Officer','Contract Manager','Company Secretary','Legal Associate','Corporate Counsel'],
        'signals':['legal counsel','paralegal','litigation','legal drafting','bar admission','company secretarial','contract law','corporate law'],
        'groups':{'legal research':['legal research','case law','statutory interpretation'], 'contracts':['contract drafting','contract review','contract negotiation'], 'litigation':['litigation','court proceedings','dispute resolution'], 'regulatory':['regulatory filings','regulatory compliance','legal due diligence'], 'corporate governance':['corporate governance','board meetings','company secretarial']}},
 'engineering': {'titles':['Mechanical Engineer','Civil Engineer','Electrical Engineer','Electronics Engineer','Chemical Engineer','Manufacturing Engineer','Production Engineer','Quality Engineer','Maintenance Engineer','Structural Engineer'],
        'signals':['mechanical engineer','civil engineer','electrical engineer','electronics engineer','chemical engineer','manufacturing engineering','plant maintenance','structural analysis'],
        'groups':{'mechanical':['mechanical design','thermodynamics','finite element analysis'], 'civil':['structural analysis','structural design','construction supervision'], 'electrical':['electrical design','power systems','circuit design','pcb design'], 'process':['process engineering','chemical processes','production planning'], 'quality':['quality control','root cause analysis','statistical process control'], 'maintenance':['preventive maintenance','plant maintenance','equipment reliability']}}
}

# Atomic technologies prevent e.g. Python from being mistaken for Java experience.
TECH = ['Python','Java','JavaScript','TypeScript','React','Angular','Vue','Node.js','Django','FastAPI',
        'Flask','Spring','SQL','PostgreSQL','MySQL','MongoDB','Redis','Kafka','Spark','Airflow','dbt',
        'Snowflake','Databricks','AWS','Azure','GCP','Docker','Kubernetes','Terraform','Git',
        'Scala','PHP','Ruby','Elixir','Dart','Laravel','Rails','Next.js','Matlab','Julia','Linux','C++','C#','.NET','Go','Rust','Swift','Kotlin','Excel','Power BI','Tableau',
        'SAP','Figma','TensorFlow','PyTorch','Scikit-learn','Looker','Jira','Selenium']


PARSER_VERSION = 2
SKILL_HEADINGS = ('skills','technical skills','core skills','core competencies','key skills','technologies','expertise','areas of expertise')
SECTION_HEADINGS = ('experience','professional experience','work experience','education','projects','certifications','professional summary','summary','key achievements','achievements')
FILLER = re.compile(r'^(?:exposure to|experience (?:in|with)|knowledge of|familiar(?:ity)? with|proficient in|working knowledge of)\s+',re.I)


def skill_items(line):
    """Split a skills line on separators outside brackets; bracket contents become their own items."""
    items, depth, current = [], 0, ''
    for ch in line:
        depth = depth+1 if ch in '([' else max(0,depth-1) if ch in ')]' else depth
        if depth == 0 and ch in ',;|•\t':
            items.append(current)
            current = ''
        else:
            current += ch
    items.append(current)
    result = []
    for item in items:
        inner = [x for group in re.findall(r'[(\[]([^)\]]*)[)\]]?',item) for x in re.split(r'[,;/]',group)]
        for part in [re.sub(r'[(\[][^)\]]*[)\]]?','',item)]+inner:
            part = part.split(':')[-1].strip(' .:-–')  # "HRMS / HR Tech: Keka" -> "Keka"
            stripped = FILLER.sub('',part)
            for piece in re.split(r'\s+and\s+',stripped) if stripped != part else [part]:
                piece = piece.strip(' .:-–')
                if 2<=len(piece)<=55 and len(piece.split())<=6 and not re.search(r'[\d%@]|https?://',piece):
                    result.append(piece)
    return result


def has(text, phrase):
    return bool(re.search(r'(?<!\w)'+re.escape(phrase.lower())+r'(?!\w)',text.lower()))


def source_hash(facts):
    return hashlib.sha256('\n'.join(facts).encode()).hexdigest()


def title_families(title):
    return [name for name, family in FAMILIES.items() if any(has(title,t) for t in family['titles'])]


def infer_profile(facts, selected=None):
    full = '\n'.join(facts)
    # Prefer the headline and dated roles over incidental keywords in old duties.
    headline = '\n'.join(facts[1:4])
    counts = {}
    for name, family in FAMILIES.items():
        title_hit = sum(has(headline,t) for t in family['titles'])
        signals = sum(has(full,s) for s in family['signals'])
        counts[name] = title_hit*5 + signals
    if selected is not None:
        names = [n for n in selected if n in FAMILIES]
    else:
        best = max(counts.values(),default=0)
        names = [n for n,v in counts.items() if v>=max(2,best*.65)] if best>=2 else []
    groups = {}
    titles = []
    for name in names:
        titles.extend(FAMILIES[name]['titles'])
        for k, phrases in FAMILIES[name]['groups'].items():
            groups[k if len(names)==1 else name+': '+k] = phrases
    for tech in TECH:
        if names and any(n in names for n in ('software','data','security')) or has(full,tech):
            groups[tech.lower()] = [tech]
    # Listed skills are evidence; they become scoring groups only for uncatalogued careers.
    resume_skills = []
    in_skills = False
    for line in facts:
        normalized = line.lower().strip(': ')
        if normalized in SKILL_HEADINGS:
            in_skills = True
            continue
        if in_skills and (normalized in SECTION_HEADINGS or line.isupper() and len(line.split())<=4):
            in_skills = False
        if in_skills:
            resume_skills.extend(skill_items(line))
    if not names:
        # No catalogued career field: listed skills are the only usable matching vocabulary.
        for item in resume_skills:
            groups.setdefault(item.lower(),[item])
        for line in facts[1:5]:
            if not any(x in line for x in ('@','https://')):
                for part in re.split(r'[|\t]',line):
                    part = re.split(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}',part)[0].strip(' -–')
                    if 1<len(part.split())<=8 and len(part)<90 and not re.search(r'\d',part):
                        titles.append(part)
    first = facts[0].strip()
    name = first if 1<=len(first.split())<=7 and not re.search(r'[@\d:/|]',first) and first.lower() not in ('resume','curriculum vitae') else 'Candidate'
    level = 'senior' if re.search(r'\b(head|director|senior|lead|chief|vp|principal|staff)\b',headline,re.I) else 'mid'
    if re.search(r'\b(junior|intern|trainee|graduate|entry.level)\b',headline,re.I):
        level = 'entry'
    supported = {k:[p for p in phrases if has(full,p)] for k,phrases in groups.items()}
    supported = {k:v for k,v in supported.items() if v}
    return {'candidate_name':name,'target_titles':list(dict.fromkeys(titles)),
            'target_seniority':level,'skill_groups':groups,
            'search_profile':{'source_hash':source_hash(facts),'families':names,
                              'detected_skills':supported,'resume_skills':list(dict.fromkeys(resume_skills)),
                              'parser':PARSER_VERSION,'method':'local resume evidence',
                              'review_needed':not names or not titles,
                              'note':'Search suggestions only. Location preferences are kept separately; no resume claims are added.'}}


def atomic_config(root, config):
    path = Path(root)/'config/settings.json'
    staging = path.with_suffix('.tmp')
    staging.write_text(json.dumps(config,indent=2,ensure_ascii=False)+'\n')
    staging.chmod(0o600)
    staging.replace(path)


def sync_profile(root, config, facts, force=False, selected=None):
    current = config.get('search_profile',{})
    if not force and current.get('source_hash') == source_hash(facts):
        if current.get('parser') == PARSER_VERSION:
            return config,False
        # Same resume, older parser: replace only parsed skills so edited titles/locations survive.
        inferred = infer_profile(facts,current.get('families'))
        updated = deepcopy(config)
        updated['skill_groups'] = inferred['skill_groups']
        updated['search_profile'] = {**current,**{k:inferred['search_profile'][k] for k in ('detected_skills','resume_skills','parser')}}
        atomic_config(root,updated)
        return updated,True
    updated = deepcopy(config)
    updated.update(infer_profile(facts,selected))
    atomic_config(root,updated)
    return updated,True


def refresh_scores(root, config, facts):
    """Rescore immediately and hide old packets when resume or matching settings change."""
    from .core import db, save_job, dedupe
    from .scoring import score
    fields = {k:config.get(k) for k in ('target_titles','target_seniority','skill_groups','locations','work_modes','home_country','stale_days','min_score','search_profile','discovery')}
    fingerprint = hashlib.sha256((source_hash(facts)+json.dumps(fields,sort_keys=True)).encode()).hexdigest()
    con = db(root)
    try:
        prune_expired(root,con)
        dedupe(con,root)
        con.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT)')
        old = con.execute("SELECT value FROM metadata WHERE key='search_fingerprint'").fetchone()
        if old and old[0] == fingerprint:
            return False
        rows = con.execute('SELECT * FROM jobs').fetchall()
        for row in rows:
            save_job(con,dict(row),score(dict(row),facts,config))
        con.execute('UPDATE jobs SET artifact=NULL')
        con.execute("INSERT OR REPLACE INTO metadata VALUES('search_fingerprint',?)",(fingerprint,))
        con.commit()
        return True
    finally:
        con.close()


def replace_resume(root, content, suffix, selected=None):
    from .core import load_config
    from .resume import read_facts
    from .runner import run_lock
    if suffix not in ('.docx','.txt'):
        raise ValueError('Use DOCX or text')
    with run_lock(root):
        folder = Path(root)/'data/resumes'
        folder.mkdir(parents=True,exist_ok=True)
        path = folder/('current-'+hashlib.sha256(content).hexdigest()[:16]+suffix)
        existed = path.exists()
        path.write_bytes(content)
        path.chmod(0o600)
        try:
            facts = read_facts(path)
            cfg = load_config(root)
            cfg['resume'] = str(path.relative_to(root))
            cfg,_ = sync_profile(root,cfg,facts,force=True,selected=selected)
        except Exception:
            if not existed:
                path.unlink(missing_ok=True)
            raise
        refresh_scores(root,cfg,facts)
        return cfg


def prune_expired(root, con):
    """Remove expired licensed source listings and their generated packets."""
    from .core import now, in_artifacts, tidy_empty
    import shutil
    expired=con.execute("SELECT id,artifact FROM jobs WHERE source='himalayas' AND expires IS NOT NULL AND expires!='' AND expires<=?",(now(),)).fetchall()
    base=Path(root)/'artifacts'
    for row in expired:
        ident=row['id']
        folders=[base/ident] if re.fullmatch(r'[a-f0-9]{20}',ident) else []
        if row['artifact']:
            folders.append(Path(root)/row['artifact'])
        for folder in folders:
            if not in_artifacts(root,folder):
                continue
            if folder.is_symlink():
                folder.unlink()
            elif folder.exists():
                shutil.rmtree(folder)
            tidy_empty(root,folder)
        con.execute('DELETE FROM jobs WHERE id=?',(ident,))
    con.commit()
