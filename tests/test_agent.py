from collections import Counter
import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from docx import Document
from job_search_desk.core import load_config, db, canonical, safe_url, save_job, job_id
from job_search_desk.scoring import score
from job_search_desk.resume import read_facts, write_resume, validated_order, groups, ai_order
from job_search_desk.sources import normalize, rss, read_alert, read_import
from job_search_desk.runner import run, run_lock
from job_search_desk.packets import contacts_for
from job_search_desk.digest import send_digest


def inputs(root):
    cfg = load_config(root)
    facts = read_facts(root/cfg['resume'])
    jobs = json.loads((root/'examples/jobs.json').read_text())
    return cfg,facts,jobs


def test_fit_and_geography(root):
    cfg,facts,jobs = inputs(root)
    good = score(jobs[0],facts,cfg)
    assert good['score'] >= 8 and good['evidence']
    assert score(jobs[2],facts,cfg)['score'] <= 4
    assert score(jobs[3],facts,cfg)['score'] <= 5
    jobs[0]['location'] = 'Remote'
    assert score(jobs[0],facts,cfg)['score'] <= 5
    jobs[0]['location'] = 'Pune, India'
    jobs[0]['needs_review'] = True
    assert score(jobs[0],facts,cfg)['score'] <= 4
    jobs[0]['title'] = 'Senior Software Engineer'
    assert score(jobs[0],facts,cfg)['score'] <= 3
    assert 'Publication date unknown' in ' '.join(good['warnings'])


def test_resume_verbatim_and_chronology(root):
    cfg,facts,jobs = inputs(root)
    folder = root/'packet'
    folder.mkdir()
    order = write_resume(facts,jobs[0],folder/'resume.docx',{'provider':'none'},[0])
    output = [p.text for p in Document(folder/'resume.docx').paragraphs if p.text]
    assert Counter(output) == Counter(facts)
    movable = {i for g in groups(facts) for i in g}
    assert all(order[i] == i for i in range(len(facts)) if i not in movable)
    for g in groups(facts):
        assert set(order[i] for i in g) == set(g)
    assert (folder/'resume-provenance.json').exists()


def test_model_cannot_add_or_drop_facts(root):
    cfg,facts,jobs = inputs(root)
    assert not validated_order([1,2,999],[1,2,3])
    assert not validated_order([1,1,2],[1,2,3])
    assert not validated_order([True,2,3],[1,2,3])
    response = MagicMock()
    response.json.return_value = {'output':[{'content':[{'type':'output_text','text':'{"order":[999]}'}]}]}
    with patch('job_search_desk.resume.secret',return_value='test-only'),patch('job_search_desk.resume.requests.post',return_value=response) as post:
        assert ai_order([1,2],facts,jobs[0],{'provider':'openai','model':'test','share_resume_facts':True}) is None
        assert post.call_args.kwargs['json']['store'] is False
    response.json.return_value = {'content':[{'type':'text','text':'{"order":[2,1]}'}]}
    with patch('job_search_desk.resume.secret',return_value='test-only'),patch('job_search_desk.resume.requests.post',return_value=response):
        assert ai_order([1,2],facts,jobs[0],{'provider':'claude','model':'test','share_resume_facts':True}) == [2,1]


def test_url_safety_and_dedup(root):
    assert canonical('https://example.com/job/1?utm_source=x&ref=y') == 'https://example.com/job/1'
    for u in ['file:///etc/passwd','http://example.com','https://localhost/a','https://127.0.0.1/','https://user:pass@example.com/']:
        with pytest.raises(ValueError):
            safe_url(u)
    cfg,facts,jobs = inputs(root)
    con = db(root)
    ident,fresh = save_job(con,jobs[0],score(jobs[0],facts,cfg))
    con.execute("UPDATE jobs SET status='applied' WHERE id=?",(ident,))
    con.commit()
    assert fresh
    jobs[0]['url'] += '?utm_source=email'
    assert save_job(con,jobs[0],score(jobs[0],facts,cfg))[1] is False
    assert con.execute('SELECT count(*) FROM jobs').fetchone()[0] == 1
    assert con.execute('SELECT status FROM jobs').fetchone()[0] == 'applied'
    con.close()


def test_adapters_and_alerts(root):
    gh = normalize({'title':'HR Head','absolute_url':'https://example.com/j','content':'<p>HR operations</p>',
                    'location':{'name':'Pune'},'updated_at':'2026-10-20'}, {'type':'greenhouse','company':'Test'})
    assert gh['description'] == 'HR operations' and not gh['published']
    lever = normalize({'text':'HR Head','hostedUrl':'https://example.com/j','description':'<p>Strategy</p>',
                       'lists':[{'content':'<ul><li>Compliance</li></ul>'}],'categories':{'location':'India'},'workplaceType':'remote'},
                      {'type':'lever','company':'Test'})
    assert 'Compliance' in lever['description'] and 'remote' in lever['location']
    ash = normalize({'title':'HR Head','jobUrl':'https://example.com/j','location':'Pune','descriptionPlain':'Facts',
                     'publishedAt':'2026-10-20'}, {'type':'ashby','company':'Test'})
    assert ash['published']
    raw = b'<rss><channel><item><title>HR Head</title><link>https://example.com/hr</link><description>short</description></item></channel></rss>'
    assert rss(raw,{'company':'Test'})[0]['needs_review']
    atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>HR Head</title><link href="https://example.com/hr"/><summary>Test</summary></entry></feed>'
    assert len(rss(atom,{})) == 1
    assert read_alert(root/'examples/alert.eml')[0]['needs_review']


def test_offline_run_idempotent_and_no_network(root):
    with patch('requests.get',side_effect=AssertionError('No network allowed')),patch('requests.post',side_effect=AssertionError('No AI allowed')):
        a = run(root,dry_run=True)
        b = run(root,dry_run=True)
    assert a['prepared'] == 2 and a['failures'] == 0
    assert b['new_feed_records'] == 0
    assert a['email'] == 'not sent'
    con = db(root)
    assert con.execute('SELECT count(*) FROM jobs').fetchone()[0] == 4
    assert len(list((root/'artifacts').glob('*/*/tailored-resume.docx'))) == 2
    con.close()


def test_failure_isolation_and_import_recovery(root):
    cfg,facts,jobs = inputs(root)
    cfg['sources'] = [{'type':'greenhouse','board':'bad','company':'Bad','enabled':True},
                      {'type':'greenhouse','board':'good','company':'Good','enabled':True}]
    (root/'config/settings.json').write_text(json.dumps(cfg))
    (root/'data/imports/bad.json').write_text('{')
    with patch('job_search_desk.runner.fetch',side_effect=[ValueError('fail'),[jobs[0]]]):
        result = run(root,allow_email=False)
    assert result['prepared'] == 1 and result['failures'] == 2
    cfg['sources'] = []
    (root/'config/settings.json').write_text(json.dumps(cfg))
    (root/'data/imports/bad.json').write_text(json.dumps(jobs[1]))
    assert run(root,allow_email=False)['prepared'] == 2
    assert run(root,allow_email=False)['failures'] == 0


def test_verified_contacts_only(root):
    path = root/'data/contacts/contacts.json'
    path.write_text(json.dumps([{'name':'Synthetic','company':'Test','verified':False}]))
    assert contacts_for(root,'Test') == []


def test_digest_disabled_reservation_and_no_outreach(root):
    cfg,facts,jobs = inputs(root)
    con = db(root)
    with patch('job_search_desk.digest.smtplib.SMTP_SSL') as smtp:
        assert send_digest(con,cfg,root) == 'disabled'
        smtp.assert_not_called()
    cfg['email'].update(enabled=True,username='sender@example.com',**{'from':'sender@example.com','to':'self@example.com'})
    with patch('job_search_desk.digest.secret',return_value='test-only'),patch('job_search_desk.digest.smtplib.SMTP_SSL') as smtp:
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        assert send_digest(con,cfg,root) == 'sent'
        assert send_digest(con,cfg,root) == 'sent'
        assert smtp.call_count == 1
    con.close()


def test_digest_failure_not_retried(root):
    cfg,_,_ = inputs(root)
    cfg['email'].update(enabled=True,username='sender@example.com',**{'from':'sender@example.com','to':'self@example.com'})
    con = db(root)
    with patch('job_search_desk.digest.secret',return_value='test-only'),patch('job_search_desk.digest.smtplib.SMTP_SSL',side_effect=OSError('offline')) as smtp:
        assert send_digest(con,cfg,root) == 'uncertain_or_failed'
        assert send_digest(con,cfg,root) == 'uncertain_or_failed'
        assert smtp.call_count == 1
    con.close()


def test_lock_prevents_overlap(root):
    with run_lock(root):
        with pytest.raises(RuntimeError):
            with run_lock(root):
                pass


def test_schedule_paths_and_xml(root):
    script = Path(__file__).resolve().parents[1]/'scripts/schedule.py'
    spec = importlib.util.spec_from_file_location('schedule',script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cfg = load_config(root)
    import plistlib
    value = module.plist(root/'a folder & name',cfg)
    restored = plistlib.loads(plistlib.dumps(value))
    assert restored['StartCalendarInterval'] == {'Hour':6,'Minute':30}
    assert restored['ProgramArguments'][0].endswith('a folder & name/.venv/bin/python')


def test_imap_readonly_and_content_dedup(root):
    from job_search_desk.mailbox import ingest_imap
    client = MagicMock()
    client.select.return_value = ('OK',[])
    raw = (root/'examples/alert.eml').read_bytes()
    client.uid.side_effect = [('OK',[b'1']),('OK',[(b'meta',raw)]),('OK',[b'1']),('OK',[(b'meta',raw)])]
    cfg = {'enabled':True,'host':'imap.example.com','username':'test','folder':'Job Alerts'}
    with patch('job_search_desk.mailbox.secret',return_value='test-only'),patch('job_search_desk.mailbox.imaplib.IMAP4_SSL',return_value=client):
        assert ingest_imap(root,cfg) == 1
        assert ingest_imap(root,cfg) == 0
    client.select.assert_called_with('"Job Alerts"',readonly=True)
    assert all('PEEK' in call.args[2] for call in client.uid.call_args_list if call.args[0] == 'fetch')


def test_dashboard_demo_flow(root,monkeypatch):
    from streamlit.testing.v1 import AppTest
    import job_search_desk.core as core
    original = core.load_config
    monkeypatch.setattr(core,'ROOT',root)
    monkeypatch.setattr(core,'load_config',lambda *args: original(args[0] if args else root))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'dashboard.py'),default_timeout=20).run()
    assert not app.exception
    app.sidebar.radio[0].set_value('Offline demo').run()
    assert not app.exception
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert any(m.value == '4' for m in app.metric)
