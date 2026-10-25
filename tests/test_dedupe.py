from job_search_desk.core import db, save_job, dedupe

TEXT = 'Lead people strategy, performance management, rewards and engagement for a growing software company. '*6
BLANK = {'score':5,'reasons':[],'gaps':[],'warnings':[],'evidence':[]}


def add(con, url, title, company='Example Software Pvt Ltd', location='Pune, India', description=TEXT, score=8, **extra):
    ident,_ = save_job(con,{'url':url,'title':title,'company':company,'location':location,'description':description,
                            'source':extra.pop('source','linkedin-public'),**extra},{**BLANK,'score':score})
    return ident


def visible(con):
    return {r['title']+' @ '+r['location'] for r in con.execute('SELECT * FROM jobs WHERE duplicate_of IS NULL')}


def test_repost_under_new_title_and_lead_copy_are_hidden(root):
    con = db(root)
    a = add(con,'https://example.com/1','Chief Human Resources Officer',score=9)
    b = add(con,'https://example.com/2','CHRO / Head of People',company='Example Software Limited',score=9)
    lead = add(con,'https://example.com/3','Chief Human Resources Officer',location='Remote, India',description='',needs_review=True,score=4)
    assert dedupe(con) == 2
    assert visible(con) == {'Chief Human Resources Officer @ Pune, India'}
    assert {r['duplicate_of'] for r in con.execute('SELECT * FROM jobs WHERE id IN (?,?)',(b,lead))} == {a}


def test_distinct_roles_cities_and_agency_templates_stay_separate(root):
    con = db(root)
    add(con,'https://example.com/1','HR Manager',location='Pune, India')
    add(con,'https://example.com/2','HR Manager',location='Bengaluru, India',description='',needs_review=True)
    add(con,'https://example.com/3','Sales Manager',description=TEXT+'Sales targets. '*3)
    add(con,'https://example.com/4','HR Manager',company='Other Co',description='',needs_review=True)
    assert dedupe(con) == 0
    assert con.execute('SELECT count(*) FROM jobs WHERE duplicate_of IS NULL').fetchone()[0] == 4


def test_naukri_slug_matches_named_listing(root):
    con = db(root)
    add(con,'https://www.linkedin.com/jobs/view/1/','HR Leader',company='Shavish Group')
    add(con,'https://www.naukri.com/job-listings-hr-leader-shavish-group-pune-10-to-18-years-161026017292','Hr Leader Shavish Group',
        company='See Naukri listing',description='',needs_review=True,source='naukri-sitemap',score=4)
    assert dedupe(con) == 1


def test_duplicate_packet_removed_only_when_untouched(root):
    con = db(root)
    add(con,'https://example.com/1','Head of HR',score=9)
    dup = add(con,'https://example.com/2','Head of HR',score=8)
    folder = root/'artifacts'/'Example - Head of HR [x]';folder.mkdir(parents=True)
    (folder/'brief.md').write_text('generated')
    con.execute('UPDATE jobs SET artifact=? WHERE id=?',('artifacts/Example - Head of HR [x]',dup))
    (folder/'my-notes.txt').write_text('mine')
    dedupe(con,root)
    assert folder.exists()
    (folder/'my-notes.txt').unlink()
    dedupe(con,root)
    assert not folder.exists() and con.execute('SELECT artifact FROM jobs WHERE id=?',(dup,)).fetchone()[0] is None
