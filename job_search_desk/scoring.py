"""Deterministic fit heuristic, never a probability of hire."""
import re
from datetime import datetime, timezone

from .profile import HR_GROUPS as GROUPS, infer_profile, title_families, TECH
from .places import match_terms, country_terms


INDUSTRIES = {
 'hospitality':['hotel','hotels','hospitality','resort','resorts'],
 'manufacturing':['manufacturing','plant','factory','shop floor','production unit'],
 'automotive':['automotive','automobile','auto components'],
 'energy':['renewable','solar','wind energy','wind turbine','power plant','oil and gas'],
 'pharma':['pharma','pharmaceutical','pharmaceuticals','life sciences'],
 'healthcare':['hospital','hospitals','healthcare','clinical','patient care'],
 'retail':['retail','store operations','e-commerce','ecommerce'],
 'fmcg':['fmcg','consumer goods'],
 'construction':['construction','real estate','infrastructure projects'],
 'logistics':['logistics','warehousing','freight'],
 'education':['school','university','edtech','education'],
 'bfsi':['bank','banking','insurance','nbfc','financial services','bfsi'],
 'technology':['software','saas','it services','information technology','technology company','tech company','product company']}
MONTHS = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*'


def has(text, phrase):
    return bool(re.search(r'(?<!\w)' + re.escape(phrase.lower()) + r'(?!\w)', text.lower()))


def count(text, phrase):
    return len(re.findall(r'(?<!\w)' + re.escape(phrase.lower()) + r'(?!\w)', text.lower()))


def resume_years(facts):
    """Stated total experience, else the span since the earliest dated role."""
    for line in facts[:12]:
        m = re.search(r'(\d{1,2})\+?\s*(?:years?|yrs)\s+(?:of\s+)?(?:\w+\s+)?(?:experience|exp)\b', line, re.I)
        if m:
            return int(m.group(1))
    starts = [int(y) for y in re.findall(MONTHS+r'\s+((?:19|20)\d{2})\s*[–-]', '\n'.join(facts))]
    return datetime.now(timezone.utc).year-min(starts) if starts else None


def required_years(description):
    """Largest experience lower bound stated near the word experience, as (low, high or None)."""
    found = []
    pattern = r'(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*(\d{1,2})\s*\+?\s*)?(?:years?|yrs)'
    for m in re.finditer(pattern, description, re.I):
        context = description[max(0,m.start()-60):m.end()+60].lower()
        low, high = int(m.group(1)), int(m.group(2)) if m.group(2) else None
        if ('experience' in context or 'exp ' in context) and 0 < low <= 30:
            found.append((low, high if high and high >= low else None))
    return max(found, default=None)


def industries(text, strict):
    return sorted(k for k,terms in INDUSTRIES.items() if any((has(text,t) if not strict else count(text,t)>=3) for t in terms))


MODE_NAMES = {'onsite':'On-site','hybrid':'Hybrid','remote':'Remote'}
# Location text is trusted for any mention; descriptions only for unambiguous phrases.
LOCATION_MODES = [('hybrid',r'\bhybrid\b'),('remote',r'\bremote\b|work from home|\bwfh\b'),
                  ('onsite',r'\bon[- ]?site\b|\bin[- ]office\b|work from office|\bwfo\b')]
DESCRIPTION_MODES = [('hybrid',r'\bhybrid (?:role|work|working|model|position)\b'),
                     ('remote',r'\bfully remote\b|\b100% remote\b|\bremote[- ]first\b|\bthis is a remote (?:role|position)\b'),
                     ('onsite',r'\bwork from office\b|\bfully on[- ]?site\b|\bon[- ]?site (?:role|position)\b')]


def work_mode(job):
    for text,patterns in ((job.get('location',''),LOCATION_MODES),(job.get('description','')[:2000],DESCRIPTION_MODES)):
        for mode,pattern in patterns:
            if re.search(pattern,text,re.I):
                return mode
    return None


def place_terms(label):
    try:
        terms = match_terms(label)
    except (KeyError,ValueError,TypeError):
        terms = []
    return terms or [label.split(',')[0].strip().lower()]


def location_fit(job, config):
    """Points out of 2, a reason and warnings for the user's places and work arrangements."""
    loc = job.get('location','').lower()
    modes = set(config.get('work_modes') or MODE_NAMES)
    chosen = ' / '.join(MODE_NAMES[m] for m in MODE_NAMES if m in modes)
    home = config.get('home_country')
    mode = work_mode(job)
    place = any(has(loc,t) for label in config.get('locations',[]) for t in place_terms(label))
    if mode == 'remote':
        if 'remote' not in modes:
            return 0.5, None, [f'Remote role; you chose {chosen} only']
        in_region = place or bool(home and any(has(loc,t) for t in country_terms(home)))
        if in_region or re.search(r'\bworldwide\b|\bglobal\b|\banywhere\b',loc):
            return 2.0, f'Location: 2/2; remote role open to {home or "your country"} or worldwide; verify work eligibility', []
        return 0.5, None, [f'Remote role without a stated region; check it accepts applicants in {home or "your country"}']
    if place:
        if mode and mode not in modes:
            return 0.5, None, [f'{MODE_NAMES[mode]} role; you chose {chosen} only']
        return 2.0, 'Location: 2/2; in one of your places'+(f' ({MODE_NAMES[mode].lower()})' if mode else ''), []
    if loc.strip() in ('','unknown') or (home and loc.strip() in country_terms(home)):
        return 0.5, None, ['Location too general to match your places; review it']
    return 0.0, None, ['Location outside your places; review relocation or remote options']


def score(job, facts, config):
    title = job['title'].lower()
    text = title + '\n' + job.get('description','').lower()
    resume = '\n'.join(facts).lower()
    reasons, gaps, warnings = [], [], []
    profile = config if config.get('search_profile') else {**config,**infer_profile(facts)}
    role = any(has(title,x) for x in profile.get('target_titles',[]))
    families = profile.get('search_profile',{}).get('families',[])
    aligned = role or bool(set(families) & set(title_families(title)))
    senior = bool(re.search(r'\b(head|director|senior|lead|vp|chief|principal|staff|architect)\b', title))
    junior = bool(re.search(r'\bintern\b|\btrainee\b|\bjunior\b|\bassociate\b|\bcoordinator\b|\bassistant\b', title)) and not senior
    target_level = profile.get('target_seniority','mid')
    title_points = 3.0 if role and (target_level != 'senior' or senior) else 2.5 if aligned else 0.0
    match_text = 'matches one of your target titles' if role else 'in your career field' if aligned else 'outside your target roles'
    reasons.append(f'Role and seniority: {title_points}/3; {match_text}'+('; senior-level title' if senior else ''))
    location_points, location_reason, location_warnings = location_fit(job, config)
    if location_reason:
        reasons.append(location_reason)
    warnings.extend(location_warnings)
    if job.get('eligibility') in ('excluded','unconfirmed'):
        location_points = min(location_points,0.5)
        warnings.append(job.get('eligibility_note') or 'Source eligibility requires review')
    if job.get('eligibility_note') and job.get('eligibility') not in ('excluded','unconfirmed'):
        warnings.append(job['eligibility_note'])
    skill_groups = profile.get('skill_groups',{})
    requested = {k for k,v in skill_groups.items() if any(has(text,x) for x in v)}
    supported = {k for k,v in skill_groups.items() if any(has(resume,x) for x in v)}
    overlap = sorted(requested & supported)
    gaps = sorted(requested - supported)
    # At least four requested areas are needed for full credit; thin descriptions cannot max out.
    coverage = len(overlap) / max(len(requested), 4) if requested else 0
    skill_points = round(3 * coverage, 2)
    reasons.append(f'Skill groups: {skill_points}/3; {len(overlap)}/{len(requested)} requested groups supported')
    evidence = [line for line in facts if any(has(line,x) for k in overlap for x in skill_groups[k])]
    evidence_points = 1.0 if evidence else 0
    reasons.append(f'Resume evidence: {evidence_points}/1; exact source paragraphs available')
    freshness = 0.0
    published = job.get('published','')
    if published:
        try:
            dt = datetime.fromisoformat(published.replace('Z','+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc)-dt).days
            freshness = 1.0 if 0 <= age <= config['stale_days'] else 0.0
            if age < 0 or age > config['stale_days']:
                warnings.append('Posting date is future or stale; check source')
        except ValueError:
            warnings.append('Posting date could not be interpreted')
    else:
        warnings.append('Publication date unknown; first-seen is not publication date')
    reasons.append(f'Freshness: {freshness}/1; based on source date, never inferred')
    total = title_points + location_points + skill_points + evidence_points + freshness
    have_years, needed = resume_years(facts), required_years(job.get('description',''))
    if have_years is not None and needed:
        low, high = needed
        span = f"{low}–{high}" if high else f"{low}+"
        if low > have_years + 2:
            total -= 1.5
            warnings.append(f'Experience: role asks {span} years; resume shows {have_years} (−1.5)')
        elif high is not None and high < have_years - 6:
            total -= 1.0
            warnings.append(f'Experience: role asks {span} years; resume shows {have_years}, likely too junior (−1)')
        else:
            reasons.append(f'Experience: role asks {span} years; resume shows {have_years}')
    job_industries = sorted(set(industries(title+' '+job.get('company',''),False)) | set(industries(job.get('description',''),True)))
    own_industries = industries(resume,False)
    if job_industries and not set(job_industries) & set(own_industries):
        total -= 1.0
        warnings.append('Industry: '+', '.join(job_industries)+' — not in resume (−1); check whether sector experience is required')
    listed = [x for x in profile.get('search_profile',{}).get('resume_skills',[]) if len(x)>2 and has(text,x)]
    if not aligned:
        total = min(total, 3.0)
        warnings.append('Title outside current target roles/career fields: score capped at 3')
    if junior and target_level == 'senior':
        total = min(total, 4.0)
        warnings.append('Junior title: score capped at 4')
    if location_points < 2:
        total = min(total, 5.0)
        warnings.append('Unconfirmed/outside target location: score capped at 5')
    title_gaps=[tech for tech in TECH if len(tech)>1 and has(title,tech) and not has(resume,tech)] if set(families)&{'software','data','security'} else []
    if title_gaps:
        total=min(total,6.0)
        warnings.append('Technology named in job title is absent from resume: '+', '.join(title_gaps)+'; capped at 6 pending requirement review')
        gaps=sorted(set(gaps)|set(title_gaps))
    if job.get('needs_review'):
        total = min(total, 4.0)
        warnings.append('Alert/link only: paste the full job description before preparing a packet')
    return {'score': round(min(10,max(0,total)),1), 'reasons': reasons,
            'matched_groups': overlap, 'gaps': gaps, 'warnings': warnings,
            'evidence': evidence[:6], 'listed_skills_matched':listed[:12], 'industries':job_industries,
            'required_years':needed, 'resume_years':have_years, 'career_fields':families, 'role_aligned':aligned, 'location_eligible':location_points==2, 'disclaimer': 'Heuristic fit score, not a hiring probability. Keyword overlap cannot prove eligibility.'}
