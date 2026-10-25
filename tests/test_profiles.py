import json
from pathlib import Path
from unittest.mock import patch
from collections import Counter
import pytest
from job_search_desk.core import load_config, db, save_job
from job_search_desk.profile import replace_resume, infer_profile, sync_profile, refresh_scores, source_hash
from job_search_desk.scoring import score
from job_search_desk.runner import run
from job_search_desk.resume import read_facts
from job_search_desk.ai import connection_status, test_connection as probe_connection

SOFTWARE = '''ALEX EXAMPLE
Senior Software Engineer | Backend Engineer
Pune, India
alex@example.com
PROFESSIONAL SUMMARY
Backend engineer building distributed systems and REST APIs.
TECHNICAL SKILLS
Python, Django, PostgreSQL, Docker, AWS, Kubernetes, pytest
PROFESSIONAL EXPERIENCE
Senior Software Engineer Jan 2021 – Present
Synthetic Company
Designed Python REST APIs using Django and PostgreSQL.
Deployed Docker workloads to AWS and Kubernetes.
EDUCATION
BSc Computer Science
'''


def job(title='Senior Software Engineer',location='Pune, India'):
    return dict(title=title,company='Synthetic Company',location=location,
                url='https://example.com/software-job',published='',
                description='Build distributed systems and REST APIs using Python, Django, PostgreSQL, Docker and AWS. Maintain automated testing and pytest coverage. Work with Kubernetes in a backend engineering team.')


def test_resume_switch_rebuilds_config_and_rescores(root):
    old=load_config(root)
    old['llm']={'provider':'claude','model':'already-configured','share_resume_facts':True,'max_calls_per_run':2}
    (root/'config/settings.json').write_text(json.dumps(old))
    facts=read_facts(root/old['resume'])
    con=db(root)
    hr=json.loads((root/'examples/jobs.json').read_text())[0]
    for j in [hr,job()]:
        ident,_=save_job(con,j,score(j,facts,old))
        con.execute('UPDATE jobs SET artifact=? WHERE id=?',('artifacts/old-person',ident))
    con.commit();con.close()
    cfg=replace_resume(root,SOFTWARE.encode(),'.txt')
    assert cfg['candidate_name']=='ALEX EXAMPLE'
    assert cfg['search_profile']['families']==['software']
    assert 'HR Head' not in cfg['target_titles']
    assert 'python' in cfg['skill_groups'] and 'talent' not in cfg['skill_groups']
    for key in ['llm','sources','locations','work_modes','home_country','email','schedule','min_score']:
        assert cfg[key]==old[key]
    assert load_config(root)==cfg
    con=db(root)
    rows={r['title']:dict(r) for r in con.execute('SELECT * FROM jobs')}
    assert rows['Senior Software Engineer']['score']>=7
    assert rows['Head of HR']['score']<=3
    assert all(r['artifact'] is None for r in rows.values())
    con.close()


def test_prepare_old_install_migrates_without_network(root):
    old=load_config(root)
    path=root/'data/resumes/new.txt';path.write_text(SOFTWARE)
    old['resume']='data/resumes/new.txt'
    for k in ['search_profile','skill_groups','target_seniority']:
        old.pop(k,None)
    (root/'config/settings.json').write_text(json.dumps(old))
    con=db(root)
    save_job(con,job(),{'score':1,'reasons':[],'warnings':[],'evidence':[],'gaps':[],'disclaimer':'old'})
    con.close()
    with patch('job_search_desk.runner.fetch',side_effect=AssertionError('No discovery')),patch('job_search_desk.runner.ingest_imap',side_effect=AssertionError('No mailbox')):
        result=run(root,allow_email=False,refresh_sources=False)
    assert result['prepared']==1 and result['failures']==0
    cfg=load_config(root)
    assert cfg['candidate_name']=='ALEX EXAMPLE'
    assert cfg['search_profile']['families']==['software']
    con=db(root);row=con.execute('SELECT * FROM jobs').fetchone();con.close()
    output=root/row['artifact']/'tailored-resume.docx'
    assert Counter(read_facts(output))==Counter(SOFTWARE.strip().splitlines())


def test_manual_search_preferences_survive_same_resume(root):
    cfg=replace_resume(root,SOFTWARE.encode(),'.txt')
    cfg['target_titles']=['Principal Platform Engineer']
    cfg['locations']=['Bengaluru']
    (root/'config/settings.json').write_text(json.dumps(cfg))
    updated,changed=sync_profile(root,cfg,read_facts(root/cfg['resume']))
    assert not changed and updated['target_titles']==['Principal Platform Engineer']
    assert updated['locations']==['Bengaluru']


def test_entry_data_profile_and_location_cap(root):
    facts=['JAMIE EXAMPLE','Junior Data Analyst','Pune, India','SKILLS','SQL, Excel, Power BI','Built SQL dashboards using Power BI.']
    cfg={**load_config(root),**infer_profile(facts)}
    j=job('Junior Data Analyst');j['description']='Analyze data using SQL, Excel and Power BI.'
    result=score(j,facts,cfg)
    assert cfg['target_seniority']=='entry' and 'data' in cfg['search_profile']['families']
    assert result['score']>=7
    j['location']='Remote, United States only'
    assert score(j,facts,cfg)['score']<=5
    assert 'location' in ' '.join(score(j,facts,cfg)['warnings'])


def test_niche_profile_uses_explicit_headline_and_skills(root):
    # A career outside the catalogue (civil engineering now has its own family).
    facts=['TAYLOR EXAMPLE','Senior Sommelier','Pune, India','SKILLS','Wine Pairing, Cellar Management','Designed wine pairing menus and ran cellar management.']
    cfg={**load_config(root),**infer_profile(facts)}
    j=job('Senior Sommelier');j['description']='Design wine pairing menus and lead cellar management for the restaurant group.'
    assert not cfg['search_profile']['families']
    assert 'Senior Sommelier' in cfg['target_titles']
    assert score(j,facts,cfg)['score']>=7


def test_invalid_replacement_keeps_current_profile(root):
    before=load_config(root)
    with pytest.raises(ValueError):
        replace_resume(root,b'too short','.txt')
    assert load_config(root)==before


def test_ai_readiness_and_synthetic_probe():
    assert not connection_status({'provider':'none'})[0]
    cfg={'provider':'openai','model':'chosen-model','share_resume_facts':True,'max_calls_per_run':3}
    with patch('job_search_desk.ai.secret',return_value=''):
        assert 'missing' in connection_status(cfg)[1]
    with patch('job_search_desk.ai.secret',return_value='test-only'),patch('job_search_desk.ai.ai_order',return_value=[0,1]) as call:
        ok,message=probe_connection(cfg)
        assert ok and 'synthetic' in message
        assert all('Synthetic fact' in fact for fact in call.call_args.args[1])


def test_ai_counters_report_local_fallback(root):
    cfg=replace_resume(root,SOFTWARE.encode(),'.txt')
    cfg['llm']={'provider':'openai','model':'test-model','share_resume_facts':True,'max_calls_per_run':2}
    (root/'config/settings.json').write_text(json.dumps(cfg))
    con=db(root);save_job(con,job(),score(job(),read_facts(root/cfg['resume']),cfg));con.close()
    with patch('job_search_desk.resume.ai_order',return_value=None):
        result=run(root,allow_email=False,refresh_sources=False)
    assert result['prepared']==1
    assert result['ai']=={'attempted':1,'used':0,'fallback':1}


def test_dashboard_replacement_refreshes_json_and_results(root,monkeypatch):
    from streamlit.testing.v1 import AppTest
    import job_search_desk.core as core
    original=core.load_config
    monkeypatch.setattr(core,'ROOT',root)
    monkeypatch.setattr(core,'load_config',lambda *args:original(args[0] if args else root))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'dashboard.py'),default_timeout=20).run()
    assert not app.exception
    area=next(a for a in app.text_area if a.label.startswith('Or paste'))
    area.set_value(SOFTWARE)
    next(c for c in app.checkbox if c.label.startswith('I confirm this')).check()
    next(b for b in app.button if b.label=='Use replacement resume').click().run()
    assert not app.exception
    text=next(a.value for a in app.text_area if a.label=='Configuration JSON')
    current=json.loads(text)
    assert current['candidate_name']=='ALEX EXAMPLE'
    assert current['search_profile']['families']==['software']
    assert 'HR Head' not in current['target_titles']
    assert any(t.label=='AI connection' for t in app.tabs)


def test_offline_demo_adapts_to_software_profile(root):
    from job_search_desk.runner import demo_root
    cfg=replace_resume(root,SOFTWARE.encode(),'.txt')
    demo=demo_root(root)
    sample=json.loads((demo/'examples/jobs.json').read_text())
    assert sample[0]['title']=='Senior Software Engineer'
    assert 'Python' in sample[0]['description']
    with patch('requests.get',side_effect=AssertionError('No network')),patch('requests.post',side_effect=AssertionError('No AI')):
        result=run(demo,dry_run=True,allow_email=False)
    assert result['prepared']==2 and result['failures']==0
