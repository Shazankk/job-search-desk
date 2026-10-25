import json
from hr_agent.core import load_config
from hr_agent.profile import infer_profile, skill_items, sync_profile, PARSER_VERSION
from hr_agent.resume import read_facts
from hr_agent.scoring import score, required_years, resume_years

HR_DUTIES = ('Own people strategy as HR business partner, performance management and KPIs, talent acquisition and workforce planning, '
             'compensation and benefits, learning and leadership development, employee engagement, statutory compliance and POSH. ')


def setup(root):
    cfg = load_config(root)
    facts = read_facts(root/cfg['resume'])
    return {**cfg,**infer_profile(facts)}, facts


def hr_job(title='Head of HR', company='Synthetic Software Pvt Ltd', description=HR_DUTIES*2):
    return {'title':title,'company':company,'location':'Pune, India','url':'https://example.com/j','published':'','description':description}


def test_bracketed_skill_lists_split_cleanly():
    line = 'Performance Management (KRAs, KPIs, Competency Framework)  •  Employer Branding (LinkedIn, AmbitionBox)'
    assert skill_items(line) == ['Performance Management','KRAs','KPIs','Competency Framework','Employer Branding','LinkedIn','AmbitionBox']
    assert skill_items('HRMS / HR Tech: Keka, Zoho People; exposure to SAP and People Factor') == ['Keka','Zoho People','SAP','People Factor']
    assert skill_items('Learning and Development, 84%, 2019') == ['Learning and Development']


def test_real_resume_skills_have_no_fragments(root):
    cfg, facts = setup(root)
    listed = cfg['search_profile']['resume_skills']
    assert 'Competency Framework' in listed and 'Keka' in listed
    assert not [x for x in listed if x.count('(') != x.count(')') or ':' in x]
    # Listed skills are evidence only; the catalogued groups drive skill coverage.
    assert set(cfg['skill_groups']) <= {'strategy','operations','performance','talent','rewards','development','culture','compliance','change','analytics','sap'}


def test_old_parser_config_migrates_without_losing_edits(root):
    cfg, facts = setup(root)
    cfg['target_titles'] = ['My Edited Title']
    cfg['skill_groups']['ambitionbox)'] = ['AmbitionBox)']
    cfg['search_profile'].pop('parser')
    updated, changed = sync_profile(root,cfg,facts)
    assert changed and updated['search_profile']['parser'] == PARSER_VERSION
    assert updated['target_titles'] == ['My Edited Title'] and 'ambitionbox)' not in updated['skill_groups']
    assert json.loads((root/'config/settings.json').read_text())['target_titles'] == ['My Edited Title']


def test_thin_description_cannot_earn_full_skill_points(root):
    cfg, facts = setup(root)
    thin = score(hr_job(description='We need someone strong in talent acquisition for our Pune office team. '*3),facts,cfg)
    assert 'Skill groups: 0.75/3' in ' '.join(thin['reasons'])


def test_experience_years_are_compared(root):
    cfg, facts = setup(root)
    assert resume_years(facts) == 16
    assert required_years('Requirements: 8-12 years of HR experience.') == (8,12)
    assert required_years('Minimum 20+ years experience in HR leadership. Company founded 50 years ago.') == (20,None)
    assert required_years('Founded 50 years ago.') is None
    base = score(hr_job(),facts,cfg)['score']
    senior = score(hr_job(description=HR_DUTIES*2+'Requires 22+ years of experience.'),facts,cfg)
    junior = score(hr_job(description=HR_DUTIES*2+'Requires 2-4 years of experience.'),facts,cfg)
    assert senior['score'] == base-1.5 and 'Experience: role asks 22+' in ' '.join(senior['warnings'])
    assert junior['score'] == base-1.0 and 'too junior' in ' '.join(junior['warnings'])


def test_sector_mismatch_lowers_score_and_says_why(root):
    cfg, facts = setup(root)
    tech = score(hr_job(),facts,cfg)
    hotel = score(hr_job(title='Director of Human Resources',company='Grand Example Hotel Company'),facts,cfg)
    insurer = score(hr_job(company='Example Insurance Ltd'),facts,cfg)
    assert hotel['industries'] == ['hospitality'] and hotel['score'] == tech['score']-1
    assert 'Industry: hospitality' in ' '.join(hotel['warnings'])
    assert insurer['score'] == tech['score']  # insurance appears in the resume
