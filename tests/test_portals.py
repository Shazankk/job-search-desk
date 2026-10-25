import json
from pathlib import Path
from unittest.mock import patch
from job_search_desk.core import load_config,db,save_job
from job_search_desk.portals import search_links,portal_job_url,alert_jobs
from job_search_desk.sources import read_alert,plain
from job_search_desk.runner import run
from job_search_desk.scoring import score
from job_search_desk.resume import read_facts
from job_search_desk.digest import send_digest


def test_native_search_links_use_current_titles_and_location(root):
    cfg=load_config(root);cfg['discovery']={'queries':['Python developer'],'max_queries':1}
    links=search_links(cfg)
    assert any(x['portal']=='LinkedIn' and 'Python+developer' in x['url'] and 'Pune' in x['url'] for x in links)
    assert any(x['portal']=='Naukri' and 'python-developer-jobs-in-pune' in x['url'] for x in links)
    assert any(x['location']=='Remote, India' and 'f_WT=2' in x['url'] for x in links)


def test_linkedin_job_cards_dedup_and_ignore_non_job_links():
    path=Path(__file__).resolve().parents[1]/'examples/linkedin-alert.eml'
    jobs=read_alert(path)
    assert len(jobs)==1
    j=jobs[0]
    assert j['url']=='https://www.linkedin.com/jobs/view/9999990001/'
    assert j['title']=='Senior HR Manager'
    assert j['company']=='DEMO ONLY — Pune Employer' and j['location']=='Pune, India'
    assert j['source']=='linkedin-alert' and j['needs_review']


def test_naukri_and_slug_linkedin_urls():
    assert portal_job_url('https://www.linkedin.com/jobs/view/hr-manager-at-example-12345678?trk=test')[1].endswith('/12345678/')
    assert portal_job_url('https://www.naukri.com/job-listings-hr-head-demo-1234?utm_source=mail')[0]=='naukri-alert'
    assert portal_job_url('https://www.linkedin.com/feed/')[1] is None


def test_alert_only_run_does_not_call_job_search_or_ai(root):
    path=Path(__file__).resolve().parents[1]/'examples/linkedin-alert.eml'
    (root/'data/inbox/linkedin.eml').write_bytes(path.read_bytes())
    with patch('job_search_desk.runner.search',side_effect=AssertionError('No search')),patch('job_search_desk.runner.fetch',side_effect=AssertionError('No feeds')),patch('job_search_desk.resume.ai_order',side_effect=AssertionError('No AI')):
        result=run(root,allow_email=False,alerts_only=True)
    assert result['alert_leads']==1 and result['prepared']==0 and result['failures']==0


def test_full_job_is_not_downgraded_by_later_alert(root):
    cfg=load_config(root);facts=read_facts(root/cfg['resume'])
    j=read_alert(Path(__file__).resolve().parents[1]/'examples/linkedin-alert.eml')[0]
    full={**j,'source':'manual-linkedin','description':'This is the full job description, with HR operations, strategic HR, compensation, benefits and talent acquisition. Lead performance management and HR analytics for a senior HR team in Pune.','needs_review':False}
    con=db(root);save_job(con,full,score(full,facts,cfg));save_job(con,j,score(j,facts,cfg))
    row=con.execute('SELECT * FROM jobs').fetchone()
    assert not row['needs_review'] and row['description']==full['description'] and row['source']=='manual-linkedin'
    con.close()


def test_digest_includes_leads_below_full_score_threshold(root):
    cfg=load_config(root);facts=read_facts(root/cfg['resume'])
    cfg['email'].update(enabled=True,username='sender@example.com',include_job_details=True,**{'from':'sender@example.com','to':'self@example.com'})
    j=read_alert(Path(__file__).resolve().parents[1]/'examples/linkedin-alert.eml')[0]
    con=db(root);save_job(con,j,score(j,facts,cfg))
    with patch('job_search_desk.digest.secret',return_value='test-only'),patch('job_search_desk.digest.smtplib.SMTP_SSL') as smtp:
        smtp.return_value.__enter__.return_value.send_message.return_value={}
        assert send_digest(con,cfg,root)=='sent'
        message=smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
        assert '1 new alert/search leads' in message.get_content()
        assert 'Senior HR Manager' in message.get_content()
    assert con.execute('SELECT count(*) FROM digest_leads').fetchone()[0]==1
    assert con.execute('SELECT count(*) FROM digest_jobs').fetchone()[0]==0
    con.close()


def test_leads_visible_even_when_jobs_fit_filter_is_seven(root,monkeypatch):
    from streamlit.testing.v1 import AppTest
    import job_search_desk.core as core
    cfg=load_config(root);facts=read_facts(root/cfg['resume'])
    con=db(root);j=read_alert(Path(__file__).resolve().parents[1]/'examples/linkedin-alert.eml')[0]
    save_job(con,j,score(j,facts,cfg));con.close()
    original=core.load_config
    monkeypatch.setattr(core,'ROOT',root)
    monkeypatch.setattr(core,'load_config',lambda *args:original(args[0] if args else root))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'dashboard.py'),default_timeout=20).run()
    next(w for w in app.slider if w.label=='Minimum fit score').set_value(7.0).run()
    assert not app.exception
    assert any(x.label.startswith('Lead · Senior HR Manager') for x in app.expander)
    assert any(t.label=='LinkedIn & Naukri' for t in app.tabs)
