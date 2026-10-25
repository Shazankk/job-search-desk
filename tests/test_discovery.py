import importlib.util
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from job_search_desk.core import db,save_job,load_config,event
from job_search_desk.discovery import plan,queries,himalayas_job,search_himalayas,search_adzuna,coverage_report
from job_search_desk.profile import infer_profile,refresh_scores,replace_resume
from job_search_desk.scoring import score
from job_search_desk.resume import read_facts


def remote(**changes):
    item=dict(title='HR Manager',companyName='Synthetic Company',guid='https://himalayas.app/companies/demo/jobs/hr',
              applicationLink='https://himalayas.app/companies/demo/jobs/hr?utm_source=api',
              description='<p>Lead HR operations, strategic HR, payroll and performance management for a remote team in India.</p>',
              locationRestrictions=['India'],timezoneRestrictions=[5.5],expiryDate=1999999999)
    return {**item,**changes}


def config(root):
    c=load_config(root)
    c['discovery']={'max_queries':3,'queries':[],'himalayas':{'enabled':True,'pages_per_query':1},'adzuna':{'enabled':True,'pages_per_query':1}}
    return c


def test_query_plan_changes_with_resume_and_targets_city(root):
    c=config(root)
    c.update(infer_profile(read_facts(root/c['resume'])))
    old=plan(c)
    assert any(x['provider']=='adzuna' and x['location']=='Pune, India' and x['country_code']=='in' for x in old)
    assert any(x['query']=='human resources' for x in old)
    c.update(infer_profile(['TEST PERSON','Senior Software Engineer','Pune','SKILLS','Python, Django','Built REST APIs using Python.']))
    new=plan(c)
    assert any(x['query']=='software engineer' for x in new)
    assert not any('HR' in x['query'] or 'human resources' in x['query'] for x in new)
    c['discovery']['queries']=['my chosen query']
    assert queries(c)==['my chosen query']


def test_remote_india_country_timezone_and_conflicting_description():
    assert himalayas_job(remote(),'India')['eligibility']=='confirmed'
    assert himalayas_job(remote(locationRestrictions=['United States']),'India')['eligibility']=='excluded'
    assert himalayas_job(remote(timezoneRestrictions=[-5]),'India')['eligibility']=='excluded'
    assert himalayas_job(remote(timezoneRestrictions=[]),'India')['eligibility']=='unconfirmed'
    assert himalayas_job(remote(locationRestrictions=[],description='<h3>Remote (Europe)</h3> HR operations and payroll.'),'India')['eligibility']=='unconfirmed'


def test_source_apply_link_is_preserved_and_visible_in_brief(root):
    from job_search_desk.packets import packet
    c=config(root);facts=read_facts(root/c['resume'])
    j=himalayas_job(remote(),'India')
    con=db(root);ident,_=save_job(con,j,score(j,facts,c));row=con.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone()
    assert row['apply_url']==j['apply_url'] and 'utm_source=api' in row['apply_url']
    folder=packet(root,row,facts,c,[0])
    text=(root/folder/'brief.md').read_text()
    assert j['apply_url'] in text and j['source_url'] in text
    con.close()


def test_search_cache_is_separate_for_different_queries(root):
    response=json.dumps({'jobs':[remote()]}).encode()
    spec={'query':'human resources','country':'India'}
    with patch('job_search_desk.discovery.get',return_value=response) as get:
        assert len(search_himalayas(root,spec,{'pages_per_query':1}))==1
        search_himalayas(root,spec,{'pages_per_query':1})
        search_himalayas(root,{'query':'software engineer','country':'India'},{'pages_per_query':1})
        assert get.call_count==2
        assert 'country=India' in get.call_args.args[0]


def test_expired_listings_and_packets_removed(root):
    c=config(root);facts=read_facts(root/c['resume']);j=himalayas_job(remote(expiryDate=1),'India')
    con=db(root);ident,_=save_job(con,j,score(j,facts,c));con.close()
    path=root/'artifacts'/ident;path.mkdir(parents=True);(path/'brief.md').write_text('expired')
    refresh_scores(root,c,facts)
    con=db(root);assert con.execute('SELECT count(*) FROM jobs').fetchone()[0]==0;con.close()
    assert not path.exists()


def test_adzuna_requires_credentials_and_sends_city_no_salary(root):
    spec={'query':'HR manager','location':'Pune, India','country_code':'in'}
    with patch('job_search_desk.discovery.secret',return_value=''),patch('job_search_desk.discovery.requests.get') as get:
        with pytest.raises(ValueError):search_adzuna(root,spec,{})
        get.assert_not_called()
    response=MagicMock();response.content=b'{}'
    response.json.return_value={'results':[{'title':'HR Manager','company':{'display_name':'Synthetic'},'redirect_url':'https://example.com/adzuna-job','location':{'display_name':'Pune'},'description':'Snippet only','created':''}]}
    with patch('job_search_desk.discovery.secret',return_value='test-only'),patch('job_search_desk.discovery.requests.get',return_value=response) as get:
        rows=search_adzuna(root,spec,{})
        params=get.call_args.kwargs['params']
        assert params['where']=='Pune' and params['what']=='HR manager'
        assert '/jobs/in/search/' in get.call_args.args[0]
        assert not any('salary' in k for k in params)
        assert rows[0]['needs_review']
        assert 'test-only' not in ''.join(p.read_text() for p in (root/'data/cache').glob('*'))


def test_observed_lift_does_not_invent_percentage(root):
    c=config(root);facts=read_facts(root/c['resume']);con=db(root)
    first=himalayas_job(remote(),'India');save_job(con,first,score(first,facts,c))
    assert coverage_report(con)['additional_adzuna'] is None
    second={**first,'source':'adzuna','url':'https://example.com/extra','company':'Other Synthetic Company'}
    save_job(con,second,score(second,facts,c));event(con,'search_ok','adzuna: HR Manager / Pune: 1 records')
    con.execute("INSERT OR REPLACE INTO metadata VALUES('search_fingerprint','test')")
    con.execute("INSERT OR REPLACE INTO metadata VALUES('adzuna_checked_fingerprint','test')")
    con.commit()
    report=coverage_report(con)
    assert report['baseline']==1 and report['additional_adzuna']==1 and report['percent_added']==100
    con.close()


def test_upgrade_keeps_old_resume_and_job_history(root,tmp_path):
    old=tmp_path/'old';old.mkdir();(old/'config').mkdir();(old/'data/resumes').mkdir(parents=True)
    text='TEST CANDIDATE\nSenior Data Analyst\nPune, India\nSKILLS\nSQL, Excel, Power BI\nBuilt SQL dashboards.\n'
    (old/'data/resumes/current.txt').write_text(text)
    cfg=load_config(root);cfg['resume']='data/resumes/current.txt'
    for k in ['search_profile','skill_groups','target_seniority','discovery']:cfg.pop(k,None)
    (old/'config/settings.json').write_text(json.dumps(cfg))
    con=db(old);j={'title':'Senior Data Analyst','url':'https://example.com/saved','company':'Synthetic','location':'Pune','description':'SQL Excel Power BI'}
    save_job(con,j,{'score':1,'reasons':[],'warnings':[],'gaps':[],'evidence':[],'disclaimer':'old'});con.close()
    path=Path(__file__).resolve().parents[1]/'scripts/import_previous.py'
    spec=importlib.util.spec_from_file_location('import_previous',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    updated=module.import_previous(old,root)
    assert updated['candidate_name']=='TEST CANDIDATE' and 'data' in updated['search_profile']['families']
    assert (old/'data/resumes/current.txt').read_text()==text
    con=db(root);assert con.execute('SELECT score FROM jobs').fetchone()[0]>=7;con.close()


def test_dashboard_credentials_never_go_to_configuration(root,monkeypatch):
    from streamlit.testing.v1 import AppTest
    import job_search_desk.core as core
    original=core.load_config
    monkeypatch.setattr(core,'ROOT',root)
    monkeypatch.setattr(core,'load_config',lambda *args:original(args[0] if args else root))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'dashboard.py'),default_timeout=20).run()
    assert not app.exception
    next(w for w in app.text_input if w.label=='Adzuna app ID').set_value('test-only-id')
    next(w for w in app.text_input if w.label=='Adzuna app key').set_value('test-only-key')
    with patch('job_search_desk.credentials.store') as store:
        next(w for w in app.button if w.label=='Save Adzuna credentials to Keychain').click().run()
        assert store.call_count==2
    assert not app.exception
    config_text=(root/'config/settings.json').read_text()
    assert 'test-only-id' not in config_text and 'test-only-key' not in config_text


def test_primary_title_technology_gap_is_not_high_fit(root):
    facts=['TEST PERSON','Senior Software Engineer','Pune','SKILLS','Python, Django','Built Python APIs.']
    c={**config(root),**infer_profile(facts)}
    j=dict(title='Senior Software Engineer (Scala Developer)',company='Test',location='Pune',description='Build Python APIs and distributed systems using Scala.',url='https://example.com/scala')
    result=score(j,facts,c)
    assert result['score']<=6 and 'Scala' in result['gaps']


def test_packet_folder_is_dated_named_after_the_job_and_migrates_old_layouts(root):
    from datetime import datetime
    from job_search_desk.packets import packet, folder_name, organize_packets
    c=config(root);facts=read_facts(root/c['resume'])
    j=himalayas_job(remote(),'India')
    con=db(root);ident,_=save_job(con,j,score(j,facts,c))
    con.execute("UPDATE jobs SET first_seen='2026-03-04T10:00:00+00:00' WHERE id=?",(ident,))
    row=con.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone()
    day=datetime.fromisoformat(row['first_seen']).astimezone().date().isoformat()
    legacy=root/'artifacts'/ident;legacy.mkdir(parents=True);(legacy/'notes.txt').write_text('mine')
    folder=packet(root,row,facts,c,[0])
    assert folder==f'artifacts/{day}/'+folder_name(row)
    assert row['company'] in folder and row['title'] in folder and ident[:6] in folder
    assert not legacy.exists() and (root/folder/'notes.txt').read_text()=='mine'
    assert folder_name({'id':ident,'company':'A/B: Co.','title':'Head of HR?'})=='A B Co. - Head of HR ['+ident[:6]+']'
    # A folder recorded elsewhere (here under another date) moves, its path is updated,
    # and the emptied date folder is removed even with Finder metadata in it.
    other=root/'artifacts'/'2000-01-01'/folder_name(row);other.parent.mkdir()
    (root/folder).rename(other);(other.parent/'.DS_Store').write_text('')
    con.execute('UPDATE jobs SET artifact=? WHERE id=?',(str(other.relative_to(root)),ident))
    assert organize_packets(root,con)==1
    assert not other.parent.exists()
    assert con.execute('SELECT artifact FROM jobs WHERE id=?',(ident,)).fetchone()[0]==folder
    assert (root/folder/'notes.txt').exists() and organize_packets(root,con)==0
    con.close()
