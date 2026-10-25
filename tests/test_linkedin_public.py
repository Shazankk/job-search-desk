"""Synthetic HTML only: no live LinkedIn dataset or credentials in fixtures."""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from hr_agent import linkedin_public as li
from hr_agent.core import load_config, db
from hr_agent.discovery import plan
from hr_agent.profile import infer_profile
from hr_agent.resume import read_facts
from hr_agent.runner import run

CARDS='''<li><div data-entity-urn="urn:li:jobPosting:123"><h3 class="extra base-search-card__title">HR Head</h3><h4 class="base-search-card__subtitle">Synthetic Employer</h4><span class="job-search-card__location">Pune, India</span><time datetime="2026-10-21">4 days ago</time></div></li>'''
DETAIL='''<h1 class="top-card-layout__title">HR Head</h1><a class="topcard__org-name-link">Synthetic Employer</a><span class="topcard__flavor--bullet">Pune, India</span><div class><p>Ignored empty class attribute</p></div><div class="show-more-less-html__markup"><p>Lead strategic HR and payroll operations.</p><ul><li>Manage performance management and employee relations.</li><li>Oversee recruitment and talent management for the team.</li></ul></div>'''


def configuration(root):
    c=load_config(root);c.update(infer_profile(read_facts(root/c['resume'])))
    c['discovery']={'linkedin_public':{'enabled':True,'max_searches_per_run':1,'max_details_per_run':1},'naukri_sitemap':{'enabled':False}}
    c['sources']=[];c['min_score']=7;c['llm']={'provider':'none'}
    return c


def response(body=CARDS,status=200):
    r=MagicMock();r.status_code=status;r.iter_content.return_value=[body.encode()]
    r.__enter__.return_value=r
    return r


def test_public_card_and_detail_parser_handles_empty_class_and_blocks():
    cards=li.parse_cards(CARDS)
    assert len(cards)==1 and cards[0]['needs_review']
    assert cards[0]['url']=='https://www.linkedin.com/jobs/view/123/'
    j=li.parse_detail(DETAIL,cards[0])
    assert not j['needs_review'] and j['location']=='Pune, India'
    assert 'operations.\n' in j['description'] and 'Ignored' not in j['description']
    assert li.parse_detail('<h1>No description</h1>',cards[0])['needs_review']


def test_linkedin_queries_follow_replaced_profile_and_city(root):
    c=configuration(root);assert plan(c)[0]['query']=='HR Head'
    c.update(infer_profile(['TEST PERSON','Senior Software Engineer','SKILLS','Python, Django','Built Python APIs.']))
    p=plan(c)
    assert p[0]['location']=='Pune, India' and 'software' in p[0]['query'].lower()
    assert not any('HR' in row['query'] for row in p)
    c['discovery']['queries']=['HR Director']
    assert plan(c)[0]['query']=='HR Director'
    c['discovery']['linkedin_public']['enabled']=False
    assert not plan(c)


def test_public_fetch_cache_no_cookies_login_or_redirects(root):
    with patch.object(li.requests,'get',return_value=response()) as get:
        assert li.fetch_html(root,'seeMoreJobPostings/search',{'keywords':'HR Head'})==CARDS
        assert li.fetch_html(root,'seeMoreJobPostings/search',{'keywords':'HR Head'})==CARDS
        assert get.call_count==1
        assert get.call_args.kwargs['allow_redirects'] is False
        assert 'cookies' not in get.call_args.kwargs and 'auth' not in get.call_args.kwargs


@pytest.mark.parametrize('status',[302,403,429,999])
def test_block_stops_without_retry_and_survives_day_rollover(root,status):
    with patch.object(li.requests,'get',return_value=response(status=status)) as get:
        with pytest.raises(li.AccessBlocked):li.fetch_html(root,'blocked')
        path=root/'data/cache/linkedin/request-state.json'
        state=json.loads(path.read_text());state['day']='2000-01-01';path.write_text(json.dumps(state))
        with pytest.raises(li.AccessBlocked):li.fetch_html(root,'another')
        assert get.call_count==1


def test_daily_budget_cache_still_available_and_query_separation(root):
    with patch.object(li.requests,'get',return_value=response()) as get:
        li.fetch_html(root,'search',{'q':'hr'},{'daily_request_limit':1})
        assert li.fetch_html(root,'search',{'q':'hr'},{'daily_request_limit':1})==CARDS
        with pytest.raises(li.AccessBlocked):li.fetch_html(root,'search',{'q':'software'},{'daily_request_limit':1})
        assert get.call_count==1


def test_detail_budget_and_stop_preserve_leads(root):
    c=configuration(root)
    cards=CARDS+CARDS.replace('123','456')
    with patch.object(li,'fetch_html',side_effect=[cards,li.AccessBlocked('test block')]) as fetch:
        rows=li.search(root,plan(c)[0],c)
        assert len(rows)==2 and all(j['needs_review'] for j in rows)
        assert c['_linkedin_paused'] and fetch.call_count==2


def test_real_pipeline_on_synthetic_public_pages_creates_factual_packet(root):
    c=configuration(root);(root/'config/settings.json').write_text(json.dumps(c))
    with patch.object(li,'fetch_html',side_effect=[CARDS,DETAIL]):
        result=run(root,allow_email=False)
    assert result['prepared']==1 and result['failures']==0
    con=db(root);row=con.execute('SELECT * FROM jobs').fetchone();con.close()
    assert row['location']=='Pune, India' and row['score']>=7
    from docx import Document
    rendered=[p.text for p in Document(root/row['artifact']/'tailored-resume.docx').paragraphs if p.text.strip()]
    assert sorted(rendered)==sorted(read_facts(root/c['resume']))


def test_access_page_is_failure_not_zero_jobs(root):
    c=configuration(root)
    with patch.object(li,'fetch_html',return_value='<html>Sign in /authwall</html>'):
        with pytest.raises(li.AccessBlocked):li.search(root,plan(c)[0],c)


def test_dashboard_saving_discovery_preserves_linkedin_controls(root,monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    import hr_agent.core as core
    c=configuration(root);(root/'config/settings.json').write_text(json.dumps(c))
    original=core.load_config
    monkeypatch.setattr(core,'ROOT',root)
    monkeypatch.setattr(core,'load_config',lambda *args:original(args[0] if args else root))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'dashboard.py'),default_timeout=20).run()
    assert not app.exception
    next(w for w in app.number_input if w.label.startswith('Maximum LinkedIn full descriptions per run')).set_value(4)
    next(w for w in app.checkbox if w.label.startswith('Read Naukri')).check()
    next(w for w in app.button if w.label=='Save discovery settings').click().run()
    assert not app.exception
    discovery=json.loads((root/'config/settings.json').read_text())['discovery']
    assert discovery['linkedin_public']['enabled'] and discovery['linkedin_public']['max_details_per_run']==4
    assert discovery['naukri_sitemap']=={'max_leads_per_run':40,'job_age_days':30,'enabled':True}


def stored_lead(con,c,ident,source='linkedin-public',location='Pune, India',title='HR Head'):
    from hr_agent.core import save_job
    from hr_agent.scoring import score
    j={'title':title,'company':'Not supplied in alert' if source=='linkedin-alert' else 'Synthetic Employer','location':location,
       'url':f'https://www.linkedin.com/jobs/view/{ident}/','description':'','source':source,'needs_review':True}
    return save_job(con,j,score(j,c['_facts'],c))[0]


def test_stored_and_alert_leads_get_full_descriptions_within_budget(root):
    c=configuration(root);c['discovery']['linkedin_public']['max_details_per_run']=2
    c['_facts']=read_facts(root/c['resume'])
    con=db(root)
    a=stored_lead(con,c,'111');b=stored_lead(con,c,'222',source='linkedin-alert',location='Unknown')
    elsewhere=stored_lead(con,c,'333',location='Chennai, India')
    third=stored_lead(con,c,'444')
    with patch.object(li,'fetch_html',side_effect=[DETAIL,DETAIL]) as fetch:
        assert li.enrich_leads(root,con,c)==(2,0,0)
        assert fetch.call_count==2
    rows={r['id']:r for r in con.execute('SELECT * FROM jobs')}
    # Known target locations first; the unknown-location alert lead waits for budget.
    assert not rows[a]['needs_review'] and not rows[third]['needs_review'] and rows[a]['score']>=7
    assert 'performance management' in rows[a]['description']
    assert rows[b]['needs_review'] and rows[elsewhere]['needs_review']
    c['_linkedin_detail_remaining']=1
    with patch.object(li,'fetch_html',side_effect=[DETAIL]):
        assert li.enrich_leads(root,con,c)==(1,0,0)
    row=con.execute('SELECT * FROM jobs WHERE id=?',(b,)).fetchone()
    assert row['company']=='Synthetic Employer' and row['source']=='linkedin-public' and not row['eligibility_note']
    assert con.execute('SELECT needs_review FROM jobs WHERE id=?',(elsewhere,)).fetchone()[0]


def test_enrichment_stops_on_block_and_closes_removed_listings(root):
    c=configuration(root);c['discovery']['linkedin_public']['max_details_per_run']=5
    c['_facts']=read_facts(root/c['resume'])
    con=db(root)
    for ident in ('111','222','333'):stored_lead(con,c,ident)
    with patch.object(li,'fetch_html',side_effect=['',li.AccessBlocked('blocked')]) as fetch:
        assert li.enrich_leads(root,con,c)==(0,1,0)
        assert fetch.call_count==2 and c['_linkedin_paused']
        assert li.enrich_leads(root,con,c)==(0,0,0) and fetch.call_count==2
    status=sorted(r['status'] for r in con.execute('SELECT * FROM jobs'))
    assert status==['closed','new','new']


def test_remote_india_search_uses_remote_filter_and_keeps_label(root):
    c=configuration(root);c['work_modes']=['onsite','hybrid','remote'];c['home_country']='India';c['discovery']['linkedin_public']['max_searches_per_run']=3
    specs=plan(c)
    remote=[s for s in specs if s['provider']=='linkedin_public' and s.get('remote')]
    assert len(remote)==1 and remote[0]['location']=='India'
    assert len([s for s in specs if s['provider']=='linkedin_public'])==3
    card=CARDS.replace('Pune, India','India')
    with patch.object(li,'fetch_html',side_effect=[card,DETAIL.replace('Pune, India','India')]) as fetch:
        rows=li.search(root,remote[0],c)
    assert fetch.call_args_list[0].args[2]['f_WT']=='2'
    assert rows[0]['location']=='Remote, India' and not rows[0]['needs_review']
    c['work_modes']=['onsite','hybrid']
    assert not any(s.get('remote') for s in plan(c))
    c['work_modes']=['remote']  # remote only: no city searches, whole budget on remote
    assert [s.get('remote') for s in plan(c) if s['provider']=='linkedin_public']==[True,True,True]
    c['work_modes']=['hybrid','remote']
    assert {s.get('work_type') for s in plan(c) if not s.get('remote')}=={'3'}


def test_saving_keeps_the_open_tab(root,monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    import hr_agent.core as core
    c=configuration(root);(root/'config/settings.json').write_text(json.dumps(c))
    original=core.load_config
    monkeypatch.setattr(core,'ROOT',root)
    monkeypatch.setattr(core,'load_config',lambda *args:original(args[0] if args else root))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'dashboard.py'),default_timeout=20).run()
    # Only a keyed, state-tracking tab bar registers its selection; an untracked one resets to
    # the first tab in the browser whenever a notice above it changes the page.
    assert app.session_state['section']=='Jobs'
    app.session_state['section']='Discovery sources'
    app.run()
    next(w for w in app.button if w.label=='Save discovery settings').click().run()
    assert not app.exception
    assert app.session_state['section']=='Discovery sources'
    assert any('Discovery settings saved' in s.value for s in app.success)
