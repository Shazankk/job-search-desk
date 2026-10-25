from datetime import datetime
import json
import re
from pathlib import Path
from urllib.parse import quote_plus
from .core import safe_url, now, in_artifacts, tidy_empty
from .resume import write_resume


def contacts_for(root, company):
    path = root/'data/contacts/contacts.json'
    if not path.exists():
        return []
    contacts = json.loads(path.read_text())
    result = []
    for c in contacts:
        if c.get('company','').strip().casefold() == company.strip().casefold() and c.get('verified') is True:
            safe_url(c['profile_url'])
            safe_url(c['evidence_url'])
            if all(c.get(k) for k in ('name','role','reason','verified_on')):
                result.append(c)
    return result


def folder_name(job):
    """Readable, filesystem-safe folder name; the short id keeps reposts and same-title roles apart."""
    label = re.sub(r'[\\/:*?"<>|\x00-\x1f]+',' ',f"{job['company']} - {job['title']}")
    label = re.sub(r'\s+',' ',label).strip(' .')[:100].rstrip(' .')
    return f"{label} [{job['id'][:6]}]"


def packet_dir(root, job):
    """artifacts/<day first found, local time>/<Company - Title [id]>; stable across daily rebuilds."""
    day = datetime.fromisoformat(job.get('first_seen') or now()).astimezone().date().isoformat()
    return Path(root)/'artifacts'/day/folder_name(job)


def move_packet(root, job):
    """Move a job's earlier packet (id-named, flat or stored path) to its dated folder."""
    folder = packet_dir(root,job)
    previous = [Path(root)/job['artifact']] if job.get('artifact') else []
    previous += [Path(root)/'artifacts'/job['id'],Path(root)/'artifacts'/folder_name(job)]
    for old in previous:
        if old != folder and in_artifacts(root,old) and old.is_dir() and not old.is_symlink() and not folder.exists():
            folder.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            old.rename(folder)
            tidy_empty(root,old)
    return folder


def organize_packets(root, con):
    """Sort existing packet folders into date folders and keep stored paths in step."""
    moved = 0
    for row in con.execute('SELECT id,title,company,first_seen,artifact FROM jobs').fetchall():
        folder = move_packet(root,dict(row))
        path = str(folder.relative_to(root))
        if row['artifact'] and row['artifact'] != path and folder.is_dir():
            con.execute('UPDATE jobs SET artifact=? WHERE id=?',(path,row['id']))
            moved += 1
    con.commit()
    return moved


def packet(root, job, facts, cfg, budget):
    job=dict(job)
    folder = move_packet(root,job)
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    result = json.loads(job['explanation'])
    contacts = contacts_for(root,job['company'])
    write_resume(facts,dict(job),folder/'tailored-resume.docx',cfg['llm'],budget)
    evidence = '\n'.join('- '+s for s in result['evidence']) or '- No matching evidence found; review manually.'
    reasons = '\n'.join('- '+s for s in result['reasons'])
    warnings = '\n'.join('- '+s for s in result['warnings']) or '- None detected by heuristic.'
    city = (cfg.get('locations') or [''])[0]
    search = 'https://www.google.com/search?q='+quote_plus(f"{job['company']} talent acquisition recruiter {city}".strip())
    contact_text = '\n\n'.join(
        f"### {c['name']} — {c['role']}\nProfile: {c['profile_url']}\nEvidence: {c['evidence_url']}\n"
        f"User verified: {c['verified_on']}\nWhy relevant: {c['reason']}" for c in contacts)
    if not contact_text:
        contact_text = ('No verified contact supplied. Suggested people to look for: the recruiter handling '
                        'this role, the hiring manager\'s talent acquisition partner, or a known employee who can refer you.\n'
                        f'Public search (a search link, not a verified contact): {search}')
    greeting = 'Hello '+contacts[0]['name']+',' if contacts else 'Hello,'
    draft = (f"{greeting}\n\nI'm interested in the {job['title']} role at {job['company']}. "
             f"Would you be the right person to ask about this opportunity, or could you point me to the relevant recruiter? "
             f"I'd be happy to share my resume.\n\nThank you,\n{cfg['candidate_name']}")
    (folder/'brief.md').write_text(
        f"# {job['title']} — {job['company']}\n\nPrepared: {now()}\n\n"
        f"Job/application: {job.get('apply_url') or job['url']}\n\nSource link: {job.get('source_url') or job['url']}\n\nLocation: {job['location']}\nSource: {job['source']}\n\n"
        f"Fit: {job['score']}/10\n\n{result['disclaimer']}\n\n## Why this scored this way\n{reasons}\n\n"
        f"## Relevant factual resume evidence\n{evidence}\n\n"
        + (f"Skills from your resume that this job mentions: {', '.join(result['listed_skills_matched'])}\n\n" if result.get('listed_skills_matched') else '')
        + "## Gaps to check\n"
        + ('\n'.join('- '+s for s in result['gaps']) or '- No unsupported groups detected; this is not a complete eligibility check.')
        + f"\n\n## Review flags\n{warnings}\n\n## Contacts\n{contact_text}\n\n"
        + f"## Outreach draft — review and send manually\n{draft}\n\n"
        + "## Before applying\n- Confirm the role is still open on the employer site.\n"
        + "- Review mandatory qualifications, work eligibility and location.\n"
        + "- Review the tailored DOCX against the original and the paragraph provenance file.\n"
        + "- Check contact identity and role again; no hiring-manager relationship is inferred.\n"
        + "- Open the job link and submit yourself. No application or outreach is sent by this project.\n\n"
        + '## Imported job description (untrusted source text)\n\n'+job['description'],encoding='utf-8')
    (folder/'outreach.md').write_text('# Draft only — manual review and send\n\n'+draft)
    (folder/'contacts.md').write_text('# Contact research\n\n'+contact_text)
    (folder/'job.json').write_text(json.dumps(dict(job),indent=2,ensure_ascii=False))
    return str(folder.relative_to(root))
