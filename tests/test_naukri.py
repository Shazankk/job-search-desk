"""Synthetic sitemaps only: no Naukri data is bundled and no request leaves the test."""
from datetime import datetime, timedelta, timezone
import gzip
import json
from unittest.mock import MagicMock, patch
import pytest
from job_search_desk import naukri
from job_search_desk.core import load_config, db, save_job
from job_search_desk.discovery import plan
from job_search_desk.profile import infer_profile
from job_search_desk.resume import read_facts
from job_search_desk.scoring import score


def ident(days_ago, serial='013720'):
    return (datetime.now(timezone.utc)-timedelta(days=days_ago)).strftime('%d%m%y')+serial


def urlset(*slugs):
    return '<urlset>'+''.join(f'<url><loc>https://www.naukri.com/job-listings-{s}</loc></url>' for s in slugs)+'</urlset>'


INDEX = '''<urlset><url><loc>https://www.naukri.com/sitemap/jobDescPagesPune.xml</loc></url>
<url><loc>https://www.naukri.com/sitemap/jobDescPagesBangalore.xml</loc></url>
<url><loc>https://www.naukri.com/sitemap/jobDescPagesOtherCities-1.xml.gz</loc></url>
<url><loc>https://www.naukri.com/sitemap/company-pages.xml</loc></url></urlset>'''
PUNE = urlset(
    f'hr-leader-shavish-group-pune-10-to-18-years-{ident(9)}',              # match, midpoint closest to 16 years
    f'head-hr-example-industries-pune-15-to-22-years-{ident(12)}',          # match ("Head of HR" without "of")
    f'head-hr-example-industries-pune-15-to-22-years-{ident(2,"013999")}',  # repost of the same listing: newest kept
    f'hr-manager-codevian-technologies-pune-3-to-6-years-{ident(9)}',       # too junior
    f'hr-leader-old-company-pune-12-to-18-years-{ident(45)}',               # stale
    f'sr-project-architect-le-human-resources-solutions-pune-12-to-18-years-{ident(3)}',  # agency name, not title
    f'purchase-manager-talent-corner-hr-services-pune-10-to-14-years-{ident(3)}')        # agency name, not title
OTHER = urlset(f'hr-head-nashik-foods-nashik-14-to-20-years-{ident(4)}', f'hr-head-surat-mills-surat-14-to-20-years-{ident(4)}')


def configuration(root):
    c = load_config(root)
    c.update(infer_profile(read_facts(root/c['resume'])))
    c['discovery'] = {'naukri_sitemap':{'enabled':True,'max_leads_per_run':40,'job_age_days':30}}
    return c


def serve(pages):
    return patch.object(naukri,'fetch',side_effect=lambda root,url,settings=None:pages[url])


def test_city_sitemap_filters_by_title_position_experience_and_date(root):
    c = configuration(root)
    with serve({naukri.INDEX:INDEX,'https://www.naukri.com/sitemap/jobDescPagesPune.xml':PUNE}):
        rows = naukri.search(root,{'location':'Pune'},c)
    assert [r['title'] for r in rows] == ['HR Leader Shavish Group Pune','Head HR Example Industries Pune']
    assert rows[1]['url'].endswith('013999')
    lead = rows[0]
    assert lead['needs_review'] and lead['source'] == 'naukri-sitemap' and lead['company'] == 'See Naukri listing'
    assert '10–18 years (resume: 16)' in lead['eligibility_note'] and lead['published'][:10] == (datetime.now(timezone.utc)-timedelta(days=9)).date().isoformat()
    result = score(lead,read_facts(root/c['resume']),c)
    assert result['role_aligned'] and result['location_eligible'] and result['score'] <= 4


def test_unlisted_city_uses_other_cities_with_city_filter(root):
    c = configuration(root)
    files, token = naukri.sitemap_files(INDEX,'Nashik')
    assert files == ['https://www.naukri.com/sitemap/jobDescPagesOtherCities-1.xml.gz'] and token == 'nashik'
    assert naukri.sitemap_files(INDEX,'Bengaluru') == (['https://www.naukri.com/sitemap/jobDescPagesBangalore.xml'],None)
    with serve({naukri.INDEX:INDEX,files[0]:OTHER}):
        rows = naukri.search(root,{'location':'Nashik'},c)
    assert [r['title'] for r in rows] == ['HR Head Nashik Foods Nashik']


def test_plan_lists_naukri_per_city_and_respects_toggle(root):
    c = configuration(root);c['locations'] = ['Pune, India','London, United Kingdom','Mumbai, India']
    assert [s['location'] for s in plan(c) if s['provider'] == 'naukri_sitemap'] == ['Pune, India','Mumbai, India']
    c['discovery']['naukri_sitemap']['enabled'] = False
    assert not [s for s in plan(c) if s['provider'] == 'naukri_sitemap']


def response(body, status=200):
    r = MagicMock();r.status_code = status;r.iter_content.return_value = [body]
    r.__enter__.return_value = r
    return r


def test_fetch_reads_gzip_caches_and_sends_no_cookies(root):
    with patch.object(naukri.requests,'get',return_value=response(gzip.compress(OTHER.encode()))) as get, patch.object(naukri.time,'sleep'):
        assert naukri.fetch(root,'https://www.naukri.com/sitemap/x.xml.gz') == OTHER
        assert naukri.fetch(root,'https://www.naukri.com/sitemap/x.xml.gz') == OTHER
    assert get.call_count == 1 and get.call_args.kwargs['allow_redirects'] is False
    assert 'cookies' not in get.call_args.kwargs and 'JobSearchDesk' in get.call_args.kwargs['headers']['User-Agent']


@pytest.mark.parametrize('status',[302,403,406,429])
def test_refusal_pauses_for_a_day_without_retry(root,status):
    with patch.object(naukri.requests,'get',return_value=response(b'',status)) as get, patch.object(naukri.time,'sleep'):
        with pytest.raises(naukri.Blocked):
            naukri.fetch(root,naukri.INDEX)
        with pytest.raises(naukri.Blocked):
            naukri.fetch(root,'https://www.naukri.com/sitemap/jobDescPagesPune.xml')
    assert get.call_count == 1


def test_non_sitemap_response_is_rejected(root):
    with patch.object(naukri.requests,'get',return_value=response(b'<html>captcha</html>')), patch.object(naukri.time,'sleep'):
        with pytest.raises(ValueError):
            naukri.fetch(root,naukri.INDEX)


def test_pasted_description_is_not_downgraded_by_next_sitemap_run(root):
    c = configuration(root);facts = read_facts(root/c['resume'])
    with serve({naukri.INDEX:INDEX,'https://www.naukri.com/sitemap/jobDescPagesPune.xml':PUNE}):
        lead = naukri.search(root,{'location':'Pune'},c)[0]
    con = db(root)
    ident_,_ = save_job(con,lead,score(lead,facts,c))
    full = {**lead,'title':'Head HR','company':'Example Industries','description':'Lead people strategy and HR operations. '*10,
            'source':'manual-naukri-sitemap','needs_review':False}
    save_job(con,full,score(full,facts,c))
    save_job(con,lead,score(lead,facts,c))
    row = con.execute('SELECT * FROM jobs WHERE id=?',(ident_,)).fetchone()
    assert not row['needs_review'] and row['company'] == 'Example Industries'
