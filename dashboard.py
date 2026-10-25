"""Loopback-only local Streamlit UI. Untrusted content displayed as plain text."""
import json
import os
from pathlib import Path
import re
import webbrowser
import streamlit as st
from hr_agent.core import ROOT, load_config, db, save_job, safe_url, now
from hr_agent.runner import run, demo_root, run_lock
from hr_agent.resume import read_facts
from hr_agent.scoring import score
from hr_agent.profile import sync_profile, refresh_scores, replace_resume, atomic_config, source_hash
from hr_agent.ai import connection_status, test_connection
from hr_agent.discovery import plan, coverage_report
from hr_agent.credentials import store as store_credential
from hr_agent.core import secret
from hr_agent.portals import search_links
from hr_agent.places import resolve, countries, country_of
from hr_agent.scoring import MODE_NAMES

os.umask(0o077)
st.set_page_config(page_title='Job Search Desk',page_icon='🌱',layout='wide')
st.title('Job Search Desk')
st.caption('Resume-based matching · factual preparation · you review and apply')
cfg = load_config()
facts = read_facts(ROOT/cfg['resume'])
try:
    with run_lock(ROOT):
        cfg,_ = sync_profile(ROOT,cfg,facts)
        refresh_scores(ROOT,cfg,facts)
except RuntimeError:
    st.info('Another preparation run is active. Refresh after it finishes to see updated results.')
if 'notice' in st.session_state:
    st.success(st.session_state.pop('notice'))
mode = st.sidebar.radio('Workspace',['Live jobs','Offline demo'])
root = ROOT if mode == 'Live jobs' else demo_root(ROOT)
con = db(root)
st.sidebar.caption('Candidate: '+cfg['candidate_name'])
st.sidebar.caption('Career fields: '+(', '.join(cfg.get('search_profile',{}).get('families',[])) or 'Custom — review target roles'))
st.sidebar.caption('Places: '+(' · '.join(cfg['locations']) or 'none yet')+' · '+' / '.join(MODE_NAMES[m] for m in MODE_NAMES if m in cfg.get('work_modes',[])))
st.sidebar.info('Nothing auto-applies or sends outreach. The daily digest runs only when you enable it in settings.')
if st.sidebar.button('Find & prepare jobs',type='primary'):
    try:
        with st.spinner('Collecting sources and preparing documents…'):
            result = run(root,dry_run=mode=='Offline demo',allow_email=False)
        st.session_state['notice'] = f"Prepared {result['prepared']} packets; {result['failures']} failures. AI: {result.get('ai',{}).get('used',0)} orderings used, {result.get('ai',{}).get('fallback',0)} local fallbacks."
        con.close()
        st.rerun()
    except Exception as exc:
        st.sidebar.error(f'{type(exc).__name__}: check settings and activity log.')
if st.sidebar.button('Prepare saved jobs (no discovery)'):
    try:
        result = run(root,dry_run=mode=='Offline demo',allow_email=False,refresh_sources=False)
        st.session_state['notice'] = f"Saved jobs rescored and {result['prepared']} packets prepared. AI: {result.get('ai',{}).get('used',0)} orderings used; local fallbacks: {result.get('ai',{}).get('fallback',0)}."
        con.close()
        st.rerun()
    except Exception as exc:
        st.sidebar.error(f'{type(exc).__name__}: check settings and activity log.')
if mode == 'Offline demo':
    st.warning('Synthetic example jobs. These are not current vacancies. No network or email is used.')

revision=str(st.session_state.get('settings_revision',0))+'_'+cfg.get('search_profile',{}).get('source_hash','')
# A keyed, state-tracking tab bar keeps the open tab across st.rerun(); an untracked one resets to Jobs
# whenever a notice above it shifts the page.
tabs = st.tabs(['Jobs','LinkedIn & Naukri','Import a job','Contacts','Resume & settings','Discovery sources','AI connection','Activity'],key='section',on_change='rerun')
with tabs[0]:
    rows = con.execute('SELECT * FROM jobs WHERE duplicate_of IS NULL ORDER BY score DESC,first_seen DESC').fetchall()
    duplicates = con.execute('SELECT count(*) FROM jobs WHERE duplicate_of IS NOT NULL').fetchone()[0]
    a,b,c = st.columns(3)
    a.metric('All stored postings',len(rows))
    b.metric('Ready to review',sum(bool(j['artifact']) and j['score']>=cfg['min_score'] for j in rows))
    c.metric('Needs description',sum(bool(j['needs_review']) for j in rows))
    matching=sum(bool(json.loads(j['explanation']).get('role_aligned')) and bool(json.loads(j['explanation']).get('location_eligible')) for j in rows)
    st.caption('LinkedIn/Naukri leads have their own tab and are never hidden by this fit-score slider.'
               +(f' {duplicates} duplicate listings (reposts or the same job from another source) are hidden.' if duplicates else ''))
    st.info(f'{matching} stored postings match both your career field and location rules. Employer feeds can contain every function and country; these are not all candidate matches. Discovery sources shows the actual searches used.')
    gap_counts={}
    for j in rows:
        detail=json.loads(j['explanation'])
        if detail.get('role_aligned') and detail.get('location_eligible') and not j['needs_review']:
            for gap in detail.get('gaps',[]):
                gap_counts[gap]=gap_counts.get(gap,0)+1
    if gap_counts:
        with st.expander('Skills your matching jobs ask for that your resume does not show'):
            st.caption('Counted across your matching jobs with full descriptions. Add a skill to your resume only if you genuinely have it; otherwise it shows what to learn next.')
            st.dataframe([{'Skill area':k,'Jobs asking':v} for k,v in sorted(gap_counts.items(),key=lambda x:-x[1])[:15]],hide_index=True)
    diagnostics=st.checkbox('Include other locations and career fields (diagnostics)',False)
    cutoff = st.slider('Minimum fit score',0.0,10.0,0.0,.5)
    st.caption('This slider filters displayed results; it does not change how jobs are scored. The packet threshold is saved under Resume & settings.')
    states = st.multiselect('Show status',['new','shortlisted','applied','dismissed','closed'],default=['new','shortlisted'])
    if not rows:
        st.info('Use Find & prepare jobs, try the offline demo, or paste a job in Import a job.')
    candidates=[j for j in rows if diagnostics or (json.loads(j['explanation']).get('role_aligned') and json.loads(j['explanation']).get('location_eligible'))]
    visible = [j for j in candidates if j['score']>=cutoff and j['status'] in states]
    if rows and not visible:
        best = max(j['score'] for j in rows)
        st.warning(f'No jobs match this view. Highest stored score: {best}/10. Lower the display filter to inspect explanations; scores are not boosted to meet the filter.')
        capped = sum('location: score capped at 5' in ' '.join(json.loads(j['explanation'])['warnings']) for j in rows)
        st.info(f'{capped} jobs have unconfirmed or outside-target locations. Your location preferences remain '+', '.join(cfg['locations'])+'. A new resume keeps these preferences until you change them. Check LinkedIn & Naukri for alert leads; Discovery sources shows enabled API searches and employer watchlists.')
    if st.button('Open prepared documents folder'):
        import subprocess
        (root/'artifacts').mkdir(exist_ok=True)
        subprocess.run(['/usr/bin/open',str(root/'artifacts')],check=False)
    for j in candidates:
        if j['score'] < cutoff or j['status'] not in states:
            continue
        with st.expander(f"{j['score']}/10 · {j['title']} · {j['company']} · {j['location']}"):
            result = json.loads(j['explanation'])
            st.caption(f"{j['source']} · first seen {j['first_seen'][:10]} · last seen {j['last_seen'][:10]}")
            st.link_button('Open job / apply yourself',j['apply_url'] or safe_url(j['url']))
            if j['source_url']:
                st.link_button('Source: '+j['source'].title(),safe_url(j['source_url']))
            st.write(result['disclaimer'])
            for reason in result['reasons']:
                st.text(reason)
            if result['warnings']:
                st.warning('\n'.join(result['warnings']))
            st.write('Unsupported skill groups:',', '.join(result['gaps']) or 'None detected')
            for item in result['evidence']:
                st.text(item)
            status = st.selectbox('Application status',['new','shortlisted','applied','dismissed','closed'],
                                  index=['new','shortlisted','applied','dismissed','closed'].index(j['status']),key='status'+j['id'])
            if status != j['status']:
                con.execute('UPDATE jobs SET status=? WHERE id=?',(status,j['id']))
                con.commit()
            if j['artifact'] and j['score']>=cfg['min_score'] and not j['needs_review']:
                folder = root/j['artifact']
                for name,mime in [('tailored-resume.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
                                  ('brief.md','text/markdown'),('contacts.md','text/markdown'),('outreach.md','text/markdown'),
                                  ('resume-provenance.json','application/json')]:
                    path = folder/name
                    if path.exists():
                        st.download_button('Download '+name,path.read_bytes(),file_name=name,mime=mime,key=j['id']+name)
            st.text_area('Job description (untrusted source text)',j['description'],height=160,key='jd'+j['id'],disabled=True)

with tabs[1]:
    st.subheader('LinkedIn & Naukri — primary portal workflow')
    st.write('Find & prepare jobs searches your enabled sources for your resume roles, places and work arrangements. '
             'LinkedIn leads — including links from your LinkedIn alert emails — get their full descriptions fetched automatically within the run budget. '
             'For places in India it also reads Naukri’s published job sitemap; Naukri does not publish descriptions outside its app, so open a Naukri lead and paste its description below. No account or AI key is needed.')
    if not cfg.get('discovery',{}).get('linkedin_public',{}).get('enabled'):
        st.info('LinkedIn public search is off. It is unofficial (LinkedIn’s terms prohibit scraping) and can stop working at any time, so you decide: turn it on under Discovery sources if you accept that. Alerts and other sources work without it.')
    st.warning('LinkedIn public search is an unofficial scraper, adapted from the MIT-licensed project you suggested. LinkedIn prohibits scraping; access may fail or stop without notice. It stops on blocks and does not use accounts, cookies or CAPTCHA bypass. Disable it in Discovery sources if you prefer alerts only.')
    st.link_button('LinkedIn access rules','https://www.linkedin.com/help/linkedin/answer/a1341387/prohibition-of-scraping-software?lang=en')
    lead_rows=con.execute("SELECT * FROM jobs WHERE needs_review=1 AND duplicate_of IS NULL AND status NOT IN ('dismissed','applied','closed') ORDER BY score DESC,first_seen DESC").fetchall()
    st.metric('Alert / search leads to review',len(lead_rows))
    st.caption('Leads can contain only a title and link. They are shown here without a misleading full fit score, regardless of the Jobs-tab slider. Full descriptions are needed for factual document preparation.')
    if st.button('Check alert mailbox & inbox now'):
        if mode!='Live jobs':
            st.warning('Switch to Live jobs to check your own alerts.')
        else:
            result=run(ROOT,allow_email=False,alerts_only=True)
            st.session_state['notice']=f"Alert check complete: {result['alert_leads']} leads stored; {result['failures']} failures. No recruiter messages or applications were sent."
            con.close()
            st.rerun()
    if not lead_rows:
        st.info('No incomplete leads yet. Run Find & prepare jobs for public LinkedIn search, or set up daily portal emails below. Complete matches appear in Jobs.')
    lead_search=st.text_input('Search lead titles or employers')
    filtered_leads=[j for j in lead_rows if not lead_search.strip() or lead_search.casefold() in (j['title']+' '+j['company']).casefold()]
    st.caption(f'Showing up to 60 of {len(filtered_leads)} matching leads, ordered by role-interest signals. Use search to find older leads; these are not full fit scores.')
    for lead in filtered_leads[:60]:
        portal={'naukri-sitemap':'Naukri','naukri-alert':'Naukri alert','linkedin-public':'LinkedIn','linkedin-alert':'LinkedIn alert'}.get(lead['source'],lead['source'])
        with st.expander(f"Lead · {lead['title']} · {portal}"):
            st.link_button('Open this listing yourself',lead['apply_url'] or lead['url'])
            if lead['eligibility_note']:
                st.caption(lead['eligibility_note'])
            match=json.loads(lead['explanation']).get('role_aligned')
            st.caption(('Role wording matches your profile. ' if match else 'Role match unconfirmed. ')+f"Location from source: {lead['location']}; employer from source: {lead['company']}. These source details still need your review.")
            st.text_area('Received source text',lead['description'],height=120,disabled=True,key='alert_text_'+lead['id'])
            with st.form('promote_'+lead['id']):
                full_title=st.text_input('Confirm exact job title',lead['title'])
                full_company=st.text_input('Confirm employer','' if lead['company'] in ('Not supplied in alert','Unverified alert','Unknown') else lead['company'])
                full_location=st.text_input('Confirm location / remote eligibility','' if lead['location']=='Unknown' else lead['location'])
                full_description=st.text_area('Paste the full job description from the listing',height=180)
                promote=st.form_submit_button('Save complete job for preparation')
            if promote:
                if not all(x.strip() for x in (full_title,full_company,full_location)) or len(full_description.strip())<100:
                    st.error('Confirm title, employer, location and paste a complete description of at least 100 characters.')
                else:
                    item=dict(lead)
                    item.update(title=full_title.strip(),company=full_company.strip(),location=full_location.strip(),description=full_description.strip(),
                                source='manual-'+lead['source'].removesuffix('-alert'),needs_review=False,eligibility_note='',eligibility='')
                    save_job(con,item,score(item,facts,cfg))
                    st.session_state['notice']='Complete job saved and scored. Use Prepare saved jobs to create its documents when it meets your threshold.'
                    con.close()
                    st.rerun()
            if st.button('Dismiss this lead',key='dismiss_'+lead['id']):
                con.execute("UPDATE jobs SET status='dismissed' WHERE id=?",(lead['id'],));con.commit()
                con.close();st.rerun()
    st.subheader('1. Create daily searches and email alerts')
    st.write('These links use your current resume-based role queries and chosen cities. Open a link, check its filters, and turn on the portal’s own daily email alert. LinkedIn supports up to 20 alerts. Nothing is created on your behalf.')
    for spec in search_links(cfg):
        st.link_button(f"{spec['portal']}: {spec['role']} / {spec['location']}",spec['url'])
    st.link_button('LinkedIn: official job-alert instructions','https://www.linkedin.com/help/linkedin/answer/a511279/job-alerts-on-linkedin')
    st.link_button('Naukri: free email-alert instructions','https://resume.naukri.com/frequently-asked-questions-faq/how-to-create-free-job-alerts/')
    with st.expander('Optional: research more openings with any web-enabled assistant'):
        st.write('Download a ready-made prompt with your target roles and places, paste it into an assistant that can search the web, then import the listings you verify under Import a job.')
        prompt=(Path(__file__).resolve().parent/'docs/PUBLIC_RESEARCH_PROMPT.md').read_text()
        prompt=prompt.replace('[paste current target roles and cities]',', '.join(cfg['target_titles'][:12])+'; places: '+', '.join(cfg['locations'])+'; work arrangements: '+', '.join(MODE_NAMES[m] for m in cfg.get('work_modes',[])))
        st.download_button('Download research prompt with my target roles',prompt,file_name='job-research-prompt.md',mime='text/markdown')
    st.subheader('2. Route alert emails into one mailbox folder')
    st.write('In your email account, create a JobAlerts folder/label and a rule for job alerts you want to read. Then configure read-only IMAP here. This needs your existing mailbox account, not an Adzuna account. Gmail commonly needs a separate app password and 2-step verification. OAuth-only or administrator-blocked mailboxes are not supported in this version.')
    mailbox=cfg.get('alerts_imap',{})
    if not mailbox.get('enabled'):
        st.warning('Automatic alert-mail intake is OFF. Enable your existing mailbox below, or import saved emails. The app is not currently reading LinkedIn/Naukri emails by itself.')
    with st.form('mailbox_'+revision,clear_on_submit=True):
        mail_enabled=st.checkbox('Enable daily read-only alert-mail ingestion',mailbox.get('enabled',False))
        mail_host=st.text_input('IMAP server',mailbox.get('host','imap.gmail.com'))
        mail_user=st.text_input('Mailbox email address',mailbox.get('username',''))
        mail_folder=st.text_input('Alert folder / label',mailbox.get('folder','JobAlerts'))
        mail_password=st.text_input('Mailbox app password (optional if already stored)',type='password')
        mail_save=st.form_submit_button('Save alert-mail settings')
    if mail_save:
        if mail_enabled and not all(x.strip() for x in (mail_host,mail_user,mail_folder)):
            st.error('Server, email address and alert folder are required.')
        else:
            try:
                with run_lock(ROOT):
                    if mail_password.strip():store_credential('IMAP_PASSWORD',mail_password)
                    cfg['alerts_imap']={**mailbox,'enabled':mail_enabled,'host':mail_host.strip(),'username':mail_user.strip(),'folder':mail_folder.strip(),'port':993}
                    atomic_config(ROOT,cfg)
                st.session_state['settings_revision']=st.session_state.get('settings_revision',0)+1
                st.session_state['notice']='Alert mailbox settings saved. Use Check alert mailbox & inbox now, then verify the imported leads.'
                con.close();st.rerun()
            except Exception:
                st.error('Could not save settings or Keychain password. Check the login Keychain and whether another run is active.')
    st.link_button('Google: app-password setup','https://support.google.com/accounts/answer/185833')
    st.subheader('Or import saved alert emails without connecting a mailbox')
    alert_upload=st.file_uploader('Saved job-alert email (.eml)',type=['eml'],key='alert_email_upload')
    if st.button('Import uploaded alert email'):
        if not alert_upload or mode!='Live jobs':
            st.error('Choose an .eml file in Live jobs first.')
        else:
            from hr_agent.sources import read_alert
            import hashlib
            payload=alert_upload.getvalue();folder=ROOT/'data/inbox';folder.mkdir(parents=True,exist_ok=True)
            path=folder/(hashlib.sha256(payload).hexdigest()+'.eml');path.write_bytes(payload)
            for item in read_alert(path):save_job(con,item,score(item,facts,cfg))
            st.session_state['notice']='Alert email imported. Its leads are visible here; paste full descriptions before preparation.'
            con.close();st.rerun()
    st.caption('Daily runs combine bounded public LinkedIn searches, enabled remote/API sources and your alerts. None is exhaustive. Public pages may be blocked; alerts can arrive late. Naukri uses alerts/imports. Contacts always need verification.')

with tabs[2]:

    st.write('Paste a LinkedIn, Naukri, Indeed or employer job URL and the description you can lawfully use. The app does not fetch that page.')
    with st.form('import'):
        url = st.text_input('Job URL (HTTPS)')
        title = st.text_input('Job title')
        company = st.text_input('Company')
        location = st.text_input('Location / work arrangement',placeholder='City, Country · Hybrid, or Remote, Country')
        description = st.text_area('Full job description',height=220)
        published = st.text_input('Published date, if known (YYYY-MM-DD; otherwise leave empty)')
        submitted = st.form_submit_button('Save job')
    if submitted:
        try:
            if mode != 'Live jobs':
                raise ValueError('Switch to Live jobs to import real jobs')
            if not title.strip() or not company.strip():
                raise ValueError('Title and company are required')
            job = dict(url=safe_url(url),title=title.strip(),company=company.strip(),location=location.strip() or 'Unknown',
                       description=description,source='manual',published=published,needs_review=len(description)<100)
            save_job(con,job,score(job,facts,cfg))
            st.success('Saved. Find & prepare jobs generates a packet when score and review requirements are met.')
        except (ValueError,KeyError) as exc:
            st.error(str(exc))
    st.write('For daily alert ingestion: save email alerts as .eml files under data/inbox. The next run imports links as unverified leads without visiting them. Full jobs can also be dropped as JSON under data/imports; see examples/manual-job.json.')

with tabs[3]:

    st.write('Add only contacts whose company and current role you have checked. No names, email addresses or hiring relationships are inferred.')
    with st.form('contacts'):
        name = st.text_input('Contact name')
        role = st.text_input('Current role')
        employer = st.text_input('Company (match job company exactly)')
        profile = st.text_input('Public profile URL')
        evidence_url = st.text_input('Evidence URL for current company and role')
        reason = st.text_area('Why this person is relevant to the role')
        checked = st.checkbox('I checked this identity, company and role today')
        add = st.form_submit_button('Save verified contact')
    if add:
        try:
            if not checked or not all([name.strip(),role.strip(),employer.strip(),reason.strip()]):
                raise ValueError('Complete all fields and verify before saving')
            item = dict(name=name,role=role,company=employer,profile_url=safe_url(profile),
                        evidence_url=safe_url(evidence_url),reason=reason,verified=True,verified_on=now()[:10])
            folder = ROOT/'data/contacts'
            folder.mkdir(parents=True,exist_ok=True)
            path = folder/'contacts.json'
            items = json.loads(path.read_text()) if path.exists() else []
            items.append(item)
            path.write_text(json.dumps(items,indent=2))
            st.success('Saved locally. Prepare jobs again to update contact briefs.')
        except ValueError as exc:
            st.error(str(exc))

with tabs[4]:

    st.subheader('Factual resume')
    st.caption(f'Current source: {cfg["resume"]} · {len(facts)} paragraphs. Source statements are user supplied, not independently verified.')
    upload = st.file_uploader('Replace source resume',type=['docx','txt'])
    pasted = st.text_area('Or paste your factual resume (one paragraph per line)',height=120)
    confirm = st.checkbox('I confirm this is my factual current resume and have checked dates and qualifications')
    if st.button('Use replacement resume'):
        if not confirm or not (upload or pasted.strip()):
            st.error('Provide a resume and confirm the facts first.')
        else:
            try:
                content = upload.getvalue() if upload else pasted.encode()
                suffix = '.docx' if upload and upload.name.lower().endswith('.docx') else '.txt'
                cfg = replace_resume(ROOT,content,suffix)
                st.session_state['settings_revision'] = st.session_state.get('settings_revision',0)+1
                st.session_state['notice'] = ('Resume and search profile updated: candidate name, career fields, target roles, skills and seniority. '
                    'Stored jobs are already rescored; old packet links are hidden. Location, sources, AI, email and schedule preferences were kept. '
                    'Use Prepare saved jobs to create fresh documents, or Find & prepare jobs to fetch sources too.')
                con.close()
                st.rerun()
            except (ValueError, RuntimeError, OSError):
                st.error('Could not replace the resume. Use an editable DOCX/plain text and wait for any active run to finish.')
    with st.expander('Review extracted source facts'):
        for line in facts:
            st.text(line)
    st.subheader('Search profile — updated from your resume')
    profile = cfg.get('search_profile',{})
    st.write('Career fields:', ', '.join(profile.get('families',[])) or 'Custom / needs review')
    detected = profile.get('detected_skills',{})
    st.write('Skills with resume evidence:', ', '.join(dict.fromkeys(p for values in detected.values() for p in values)) or 'No catalogued skills detected; add target roles and skill_groups in advanced settings.')
    if profile.get('review_needed'):
        st.warning('The career field could not be inferred confidently. Review target roles and add skill_groups in the configuration before relying on scores.')
    st.caption('These are editable search suggestions, not new claims added to your resume. Uploading a different resume rebuilds them automatically. Location preferences are preserved.')
    revision = str(st.session_state.get('settings_revision',0))+'_'+profile.get('source_hash','')
    st.markdown('**Where do you want to work?**')
    places_text = st.text_input('Cities or countries, separated by commas — any spelling or capitals (e.g. pune, LONDON, bangalore, Germany)',
                                ', '.join(cfg['locations']),key='places_'+revision)
    entries = [x.strip() for x in places_text.split(',') if x.strip()]
    resolved = {x:resolve(x) for x in entries}
    unknown = [x for x,v in resolved.items() if not v]
    fixes = {}
    for x in unknown:
        country = st.selectbox(f'Which country is “{x}” in?',['Choose a country']+countries(),key='country_'+x+revision)
        if country != 'Choose a country':
            fixes[x] = resolve(f'{x}, {country}')
    places = list(dict.fromkeys(resolved[x] or fixes.get(x) for x in entries if resolved[x] or fixes.get(x)))
    if places:
        st.caption('Recognised: '+' · '.join(places))
    with st.form('preferences_'+revision):
        candidate = st.text_input('Candidate name',cfg['candidate_name'])
        roles = st.text_area('Target job titles (one per line)','\n'.join(cfg['target_titles']),height=150)
        seniority = st.selectbox('Target seniority',['entry','mid','senior'],index=['entry','mid','senior'].index(cfg.get('target_seniority','mid')))
        modes = st.pills('Work arrangements you will accept',list(MODE_NAMES),selection_mode='multi',
                         default=cfg.get('work_modes') or list(MODE_NAMES),format_func=MODE_NAMES.get)
        st.caption('Remote means remote roles open to applicants in your country (the country of your first place).')
        packet_cutoff = st.number_input('Minimum score for preparing documents',0.0,10.0,float(cfg['min_score']),.5)
        save_preferences = st.form_submit_button('Save search preferences')
    if save_preferences:
        if not candidate.strip() or not roles.strip() or not places or not modes:
            st.error('Candidate name, target roles, at least one recognised place and one work arrangement are required.')
        elif len(places) < len(entries):
            st.error('Choose a country for each place that was not recognised, or remove it.')
        else:
            try:
                with run_lock(ROOT):
                    cfg.update(candidate_name=candidate.strip(),target_titles=[r.strip() for r in roles.splitlines() if r.strip()],
                               target_seniority=seniority,locations=places,work_modes=[m for m in MODE_NAMES if m in modes],
                               home_country=next((country_of(x) for x in places if country_of(x)),cfg.get('home_country')),min_score=packet_cutoff)
                    atomic_config(ROOT,cfg)
                    refresh_scores(ROOT,cfg,facts)
                st.session_state['settings_revision'] = st.session_state.get('settings_revision',0)+1
                st.session_state['notice'] = 'Preferences saved and existing jobs rescored. Prepare saved jobs to regenerate documents.'
                con.close()
                st.rerun()
            except RuntimeError:
                st.error('Wait for the active preparation run to finish, then save.')
    with st.expander('Advanced settings — configuration JSON'):
        st.write('The JSON below reflects the current resume profile. Configure employer boards, email and schedule here. Credentials belong in Keychain. Reinstall the daily schedule after changing its time.')
        edited = st.text_area('Configuration JSON',json.dumps(cfg,indent=2),height=440,key='config_json_'+revision)
        if st.button('Save settings'):
            old = load_config()
            try:
                parsed = json.loads(edited)
                template = json.loads((ROOT/'config/settings.example.json').read_text())
                if not set(template) <= set(parsed):
                    raise ValueError('Keep all top-level settings keys')
                with run_lock(ROOT):
                    atomic_config(ROOT,parsed)
                    load_config()
                    refresh_scores(ROOT,parsed,read_facts(ROOT/parsed['resume']))
                st.session_state['settings_revision'] = st.session_state.get('settings_revision',0)+1
                st.session_state['notice'] = 'Settings saved. Scores refreshed; prepare saved jobs to regenerate documents.'
                con.close()
                st.rerun()
            except (ValueError,KeyError,TypeError,OSError):
                atomic_config(ROOT,old)
                st.error('Invalid settings; previous settings restored.')
            except RuntimeError:
                st.error('Wait for the active preparation run to finish before saving settings.')

with tabs[5]:

    st.subheader('Search across employers using your resume profile')
    st.write('Employer watchlists (configured in advanced settings) follow only the companies you add. They are optional. The searches below use your current career fields and location preferences; changing your resume changes the role queries.')
    discovery=cfg.get('discovery',{})
    st.caption('Public LinkedIn collection costs ₹0 and requires no account. It is unofficial and conflicts with LinkedIn’s scraping rules; it pauses on access blocks instead of bypassing them. A separate blank account is unnecessary and is not supported.')
    with st.form('discovery_'+revision):
        linkedin=discovery.get('linkedin_public',{})
        use_linkedin=st.checkbox('Search LinkedIn public jobs without login (unofficial)',linkedin.get('enabled',False))
        linkedin_searches=st.number_input('Maximum LinkedIn role/place searches per run (one is used for remote roles when Remote is chosen)',1,8,min(8,int(linkedin.get('max_searches_per_run',5))))
        linkedin_details=st.number_input('Maximum LinkedIn full descriptions per run (new cards first, then saved leads)',0,25,min(25,int(linkedin.get('max_details_per_run',15))))
        naukri_settings=discovery.get('naukri_sitemap',{})
        use_naukri=st.checkbox('Read Naukri’s published job sitemap for my places in India (title and experience filter; descriptions need pasting)',naukri_settings.get('enabled',True))
        use_remote=st.checkbox('Search Himalayas for remote roles open to your country (no API key required)',discovery.get('himalayas',{}).get('enabled',True))
        use_adzuna=st.checkbox('Search Adzuna for jobs near my places (free API key; 19 countries)',discovery.get('adzuna',{}).get('enabled',False))
        query_override=st.text_area('Optional search queries — one per line; blank uses your resume career fields','\n'.join(discovery.get('queries',[])))
        query_limit=st.number_input('Maximum role queries per provider',1,6,int(discovery.get('max_queries',3)))
        pages=st.number_input('Result pages per remote query',1,5,int(discovery.get('himalayas',{}).get('pages_per_query',2)))
        save_discovery=st.form_submit_button('Save discovery settings')
    if save_discovery:
        try:
            with run_lock(ROOT):
                cfg['discovery']={**discovery,'linkedin_public':{**linkedin,'enabled':use_linkedin,'max_searches_per_run':int(linkedin_searches),'max_details_per_run':int(linkedin_details)},'max_queries':int(query_limit),'queries':[q.strip() for q in query_override.splitlines() if q.strip()],
                    'himalayas':{'enabled':use_remote,'pages_per_query':int(pages)},
                    'naukri_sitemap':{'max_leads_per_run':40,'job_age_days':30,**naukri_settings,'enabled':use_naukri},
                    'adzuna':{**discovery.get('adzuna',{}),'enabled':use_adzuna}}
                atomic_config(ROOT,cfg)
            st.session_state['settings_revision']=st.session_state.get('settings_revision',0)+1
            st.session_state['notice']='Discovery settings saved. Find & prepare jobs runs the searches shown below.'
            con.close()
            st.rerun()
        except RuntimeError:
            st.error('Wait for the active preparation run to finish before saving.')
    st.caption('Naukri sitemap: 1–3 requests per city per day, 24-hour cache, allowed for generic clients by Naukri’s robots.txt; it pauses for a day if Naukri refuses. '
               'LinkedIn public defaults: 50 uncached requests/day, 24-hour cache and 3-second spacing. Search/detail limits above bound each run; shared access may still fail. Requests send role/city queries, never your resume. Advanced JSON can lower the daily limit.')
    st.write('Current query plan')
    specs=plan(cfg)
    if specs:
        st.dataframe(specs,hide_index=True,use_container_width=True)
    else:
        st.warning('No cross-employer searches are enabled. Employer watchlists and manual imports alone have limited coverage.')
    if discovery.get('adzuna',{}).get('enabled'):
        if secret('ADZUNA_APP_ID') and secret('ADZUNA_APP_KEY'):
            st.success('Adzuna credentials found. Live access will be verified during discovery.')
        else:
            st.warning('Adzuna is not connected yet. Use CREDENTIALS.command to save both ADZUNA_APP_ID and ADZUNA_APP_KEY. Only Adzuna searches need these credentials; public LinkedIn searches can run without them.')
    st.subheader('Optional Adzuna connection — enter credentials here')
    st.write('Create a free Adzuna developer account at the link below for city searches in the countries Adzuna covers (including the UK, US, India, Germany, Australia and Canada). Paste its app ID and app key here, then enable Adzuna above. These fields save to this Mac’s login Keychain, not the settings file. Environment variables, if set, take precedence.')
    with st.form('adzuna_credentials',clear_on_submit=True):
        app_id=st.text_input('Adzuna app ID',type='password')
        app_key=st.text_input('Adzuna app key',type='password')
        save_credentials=st.form_submit_button('Save Adzuna credentials to Keychain')
    if save_credentials:
        if not app_id.strip() or not app_key.strip():
            st.error('Enter both the app ID and app key.')
        else:
            try:
                store_credential('ADZUNA_APP_ID',app_id)
                store_credential('ADZUNA_APP_KEY',app_key)
                st.session_state['notice']='Adzuna credentials saved securely. Enable its search above, then Find & prepare jobs to test live access.'
                con.close()
                st.rerun()
            except Exception:
                st.error('Could not save both credentials. Unlock the login Keychain, allow Python access if prompted, and retry. No values were saved to configuration.')
    st.subheader('Costs and likely benefit — choose before connecting')
    st.table([
        {'Option':'LinkedIn public jobs (opt-in)','Account needed':'No','Provider cost':'Free; unofficial guest pages, access can stop','Coverage':'Your roles and places worldwide; limited searches and full descriptions'},
        {'Option':'Naukri sitemap','Account needed':'No','Provider cost':'Free','Coverage':'Places in India; leads need the description pasted'},
        {'Option':'Himalayas remote','Account needed':'No','Provider cost':'Free public API; shared rate limits','Coverage':'Remote vacancies open to your country'},
        {'Option':'Public employer feeds','Account needed':'No','Provider cost':'Free','Coverage':'Only employers you explicitly watch'},
        {'Option':'Adzuna city search','Account needed':'Yes, optional','Provider cost':'Free evaluation key; ongoing quotas/paid prices shown in your Adzuna account','Coverage':'Extra city leads in 19 countries; may need full-description import'},
        {'Option':'LinkedIn / Naukri alerts','Account needed':'Your normal account for alerts','Provider cost':'Standard alerts; this app buys no subscriptions','Coverage':'Ingest saved alerts or your read-only mail folder'}])
    ad=discovery.get('adzuna',{})
    daily=int(discovery.get('max_queries',3))*min(3,len(cfg['locations']))*max(1,min(3,int(ad.get('pages_per_query',1))))
    st.caption(f'Configured Adzuna request ceiling: approximately {daily}/day or {daily*30}/30 days, before cache hits. This is usage, not a paid-plan quote. Adzuna’s public terms provide a free evaluation key without payment details; current quotas and ongoing paid prices are account-specific. Check those before paying. Default free mode makes no Adzuna requests. AI costs are separate and optional.')
    st.link_button('Adzuna free-key and pricing terms','https://developer.adzuna.com/docs/terms_of_service')
    report=coverage_report(con)
    if report['counts']:
        st.write('Observed relevant leads by source:',report['counts'])
    if report['additional_adzuna'] is None:
        st.info('Adzuna’s added coverage is not measured yet. An upfront promise such as “50% more jobs” would be unreliable. Connect it and run the same search to compare actual results.')
    else:
        pct=f"{report['percent_added']}% more than the current non-Adzuna baseline" if report['percent_added'] is not None else 'percentage undefined because the non-Adzuna baseline is zero'
        st.info(f"Observed Adzuna contribution: {report['additional_adzuna']} additional relevant leads; {pct}.")
    st.caption(report['note']+' This is not a share of all vacancies or an estimate of hiring probability.')
    st.write('No single site lists every job. Use your country’s main job boards’ own email alerts alongside this app and your personal network. This application does not claim to search all their listings, and an Adzuna connection does not unlock a LinkedIn API.')
    st.link_button('Adzuna developer registration','https://developer.adzuna.com/')
    st.link_button('Himalayas API and coverage','https://himalayas.app/api')
    st.caption('Himalayas supplies remote vacancies, not a comprehensive office-job feed. Adzuna supplies city-specific search leads; descriptions may be excerpts and require a full-description import before documents are prepared. Neither guarantees vacancies. Search results are cached for 24 hours; changing the role query produces a separate search. No salary filter is sent.')
    st.write('Employer watchlist (optional, configured in advanced JSON)')
    st.dataframe([{'company':x.get('company',''),'type':x['type'],'enabled':x.get('enabled',True)} for x in cfg['sources']],hide_index=True)

with tabs[6]:

    st.subheader('Connect AI for factual resume ordering')
    st.write('Local resume analysis and matching run automatically. AI can additionally rank existing resume paragraphs by relevance. It cannot invent facts or raise a fit score. If API access fails, local preparation continues.')
    ready,message = connection_status(cfg['llm'])
    st.info(message)
    with st.form('ai_settings_'+revision):
        providers = ['none','openai','claude']
        provider = st.selectbox('AI provider',providers,index=providers.index(cfg['llm'].get('provider','none')),
                               format_func=lambda x: {'none':'Off — local preparation','openai':'OpenAI API','claude':'Claude API'}[x])
        model = st.text_input('API model ID',cfg['llm'].get('model',''),placeholder='Enter a model available on your API account')
        sharing = st.checkbox('Allow sending job descriptions and factual resume paragraphs to this provider',cfg['llm'].get('share_resume_facts',False))
        calls = st.number_input('Maximum AI calls per preparation run',0,20,int(cfg['llm'].get('max_calls_per_run',3)))
        save_ai = st.form_submit_button('Save AI settings')
    if save_ai:
        try:
            with run_lock(ROOT):
                cfg['llm'] = dict(provider=provider,model=model.strip(),share_resume_facts=sharing,max_calls_per_run=int(calls))
                atomic_config(ROOT,cfg)
            st.session_state['settings_revision'] = st.session_state.get('settings_revision',0)+1
            st.session_state['notice'] = 'AI settings saved. Test the connection, then prepare jobs to use it.'
            con.close()
            st.rerun()
        except RuntimeError:
            st.error('Wait for the active preparation run to finish before changing AI settings.')
    with st.form('ai_credentials',clear_on_submit=True):
        api_key=st.text_input('API key for the saved AI provider',type='password')
        save_key=st.form_submit_button('Save AI key to Keychain')
    if save_key:
        if cfg['llm'].get('provider') not in ('openai','claude') or not api_key.strip():
            st.error('Save a provider choice above and enter its API key first.')
        else:
            try:
                name='OPENAI_API_KEY' if cfg['llm']['provider']=='openai' else 'ANTHROPIC_API_KEY'
                store_credential(name,api_key)
                st.session_state['notice']='AI key saved to Keychain. Test the connection below.'
                con.close()
                st.rerun()
            except Exception:
                st.error('Could not save the key. Unlock the login Keychain and allow Python access if prompted.')
    st.write('Store your API key by double-clicking CREDENTIALS.command in the project folder. Choose OpenAI or Claude. Existing Keychain or environment settings still work; no key is saved in configuration JSON.')
    st.caption('Test AI connection makes one small API request using synthetic text. API charges may apply. ChatGPT/Claude subscriptions do not automatically provide API credits.')
    if st.button('Test AI connection'):
        with st.spinner('Testing API access with synthetic text…'):
            ok,message = test_connection(cfg['llm'])
        (st.success if ok else st.warning)(message)
    st.caption('AI is used when an eligible job has a document to prepare and the resume has safely reorderable paragraph groups. Activity and run results show attempted, successful and fallback ordering counts. The output folder button is in Jobs and is unrelated to AI.')

with tabs[7]:

    st.write('A source failure leaves other sources usable. Review failures before treating a day as having no vacancies.')
    for row in con.execute('SELECT at,kind,detail FROM events ORDER BY id DESC LIMIT 60'):
        st.text(f"{row['at'][:19]} {row['kind']} — {row['detail']}")
    st.caption('Logs are under logs/agent.log. No remote error bodies or credentials are written to logs. Logs and data remain private local files.')
con.close()
