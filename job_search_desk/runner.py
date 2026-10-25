import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
from .core import ROOT, LOG, setup_logging, load_config, db, save_job, event, now, dedupe
from .sources import fetch, read_alert, read_import
from .resume import read_facts
from .scoring import score
from .packets import packet, organize_packets
from .digest import send_digest
from .mailbox import ingest_imap
from .profile import sync_profile, refresh_scores
from .discovery import plan, search, verify_himalayas
from .linkedin_public import enrich_leads


@contextmanager
def run_lock(root):
    (root/'data').mkdir(exist_ok=True)
    with (root/'data/run.lock').open('w') as handle:
        try:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another run is already in progress') from None
        try:
            yield
        finally:
            fcntl.flock(handle,fcntl.LOCK_UN)


def run(root=ROOT, dry_run=False, allow_email=True, refresh_sources=True, alerts_only=False):
    os.umask(0o077)
    root = Path(root)
    setup_logging(root)
    with run_lock(root):
        cfg = load_config(root)
        con = db(root)
        try:
            facts = read_facts(root/cfg['resume'])
            cfg,changed = sync_profile(root,cfg,facts)
            if changed:
                event(con,'profile','Search roles, skills, seniority and candidate name updated from resume')
            refresh_scores(root,cfg,facts)
            organize_packets(root,con)
            cfg['llm']['_stats'] = {'attempted':0,'used':0,'fallback':0}
            jobs, failures = [], 0
            if dry_run:
                jobs = read_import(root/'examples/jobs.json')
                for j in jobs:
                    j['source'] = 'synthetic-demo'
                cfg['llm'] = {'provider':'none'}
            elif refresh_sources:
                for spec in ([] if alerts_only else plan(cfg)):
                    if spec['provider']=='linkedin_public' and cfg.get('_linkedin_paused'):
                        continue
                    try:
                        found = search(root,spec,cfg)
                        jobs.extend(found)
                        if spec['provider']=='linkedin_public':
                            for reason in cfg.pop('_linkedin_detail_errors',[]):
                                failures += 1
                                event(con,'source_error','LinkedIn description unavailable; card retained as a lead: '+reason)
                        if spec['provider']=='linkedin_public' and cfg.get('_linkedin_paused'):
                            failures += 1
                            event(con,'source_error',cfg.get('_linkedin_pause_reason','LinkedIn paused after a block; cards retained as leads'))
                        if spec['provider']=='adzuna':
                            fingerprint=con.execute("SELECT value FROM metadata WHERE key='search_fingerprint'").fetchone()[0]
                            con.execute("INSERT OR REPLACE INTO metadata VALUES('adzuna_checked_fingerprint',?)",(fingerprint,))
                            con.commit()
                        event(con,'search_ok',f"{spec['provider']}: {spec['query']} / {spec['location']}: {len(found)} records")
                    except Exception as exc:
                        failures += 1
                        if spec['provider']=='linkedin_public':
                            from .linkedin_public import AccessBlocked
                            if isinstance(exc,AccessBlocked):
                                cfg['_linkedin_paused']=True
                                event(con,'source_error',str(exc))
                        event(con,'source_error',f"{spec['provider']}: {spec['query']} / {spec['location']}: {type(exc).__name__}; check Discovery settings and credentials")
                try:
                    count = ingest_imap(root,cfg.get('alerts_imap',{}))
                    if count:
                        event(con,'alert_mailbox',f'{count} recent messages saved for local ingestion')
                except Exception as exc:
                    failures += 1
                    event(con,'source_error',f'IMAP alerts: {type(exc).__name__}; mailbox left unchanged')
                for source in ([] if alerts_only else cfg['sources']):
                    if not source.get('enabled',True):
                        continue
                    try:
                        found = fetch(source)
                        jobs.extend(found)
                        event(con,'source_ok',f"{source['type']}:{source.get('board',source.get('company','feed'))}: {len(found)} jobs")
                    except Exception as exc:
                        failures += 1
                        # Do not log remote response bodies, URLs with tokens or personal data.
                        event(con,'source_error',f"{source['type']}:{source.get('company','feed')}: {type(exc).__name__}")
                        LOG.warning('Source failed: %s (%s)',source['type'],type(exc).__name__)
                for sub, pattern, reader in [('imports','*.json',read_import),('inbox','*.eml',read_alert)]:
                    for path in sorted((root/'data'/sub).glob(pattern)):
                        digest = hashlib.sha256(path.read_bytes()).hexdigest()
                        if con.execute('SELECT 1 FROM imports WHERE hash=?',(digest,)).fetchone():
                            continue
                        try:
                            imported = reader(path)
                            for j in imported:
                                save_job(con,j,score(j,facts,cfg))
                            con.execute('INSERT INTO imports VALUES(?,?)',(digest,now()))
                            con.commit()
                            event(con,'import',f'{sub}: {len(imported)} records')
                        except Exception as exc:
                            failures += 1
                            event(con,'import_error',f'{sub}: {type(exc).__name__}; inspect input file')
            inserted = 0
            for j in jobs:
                try:
                    _, fresh = save_job(con,j,score(j,facts,cfg))
                    inserted += int(fresh)
                except Exception as exc:
                    failures += 1
                    event(con,'job_error',type(exc).__name__)
            # Re-score all stored jobs after config or resume changes, including prior imports.
            for row in con.execute('SELECT * FROM jobs').fetchall():
                save_job(con,dict(row),score(dict(row),facts,cfg))
            prepared = 0
            budget = [max(0,min(20,int(cfg['llm'].get('max_calls_per_run',0))))]
            hidden = dedupe(con,root)
            if refresh_sources and not alerts_only and not dry_run:
                completed,closed,errors = enrich_leads(root,con,cfg)
                failures += errors
                if completed or closed or errors:
                    event(con,'leads_enriched',f'LinkedIn leads completed with full descriptions: {completed}; closed: {closed}; unavailable: {errors}')
                if cfg.get('_linkedin_paused'):
                    event(con,'source_error',cfg.get('_linkedin_pause_reason','LinkedIn paused; remaining leads kept'))
                hidden = dedupe(con,root)
            rows = con.execute('''SELECT * FROM jobs WHERE score>=? AND needs_review=0 AND duplicate_of IS NULL
              AND status NOT IN ('dismissed','applied','closed') ORDER BY score DESC,first_seen DESC LIMIT ?''',
              (cfg['min_score'],max(0,min(100,int(cfg['max_packets_per_run']))))).fetchall()
            for row in ([] if alerts_only else rows):
                try:
                    if row['source']=='himalayas' and not dry_run:
                        con.execute('UPDATE jobs SET artifact=NULL WHERE id=?',(row['id'],))
                        con.commit()
                        if not verify_himalayas(root,row):
                            con.execute("UPDATE jobs SET expires=? WHERE id=?",(now(),row['id']))
                            con.commit()
                            from .profile import prune_expired
                            prune_expired(root,con)
                            event(con,'source_closed','Expired/closed Himalayas listing removed')
                            continue
                    folder = packet(root,row,facts,cfg,budget)
                    con.execute('UPDATE jobs SET artifact=? WHERE id=?',(folder,row['id']))
                    con.commit()
                    prepared += 1
                except Exception as exc:
                    failures += 1
                    event(con,'packet_error',f"{row['id']}: {type(exc).__name__}")
            all_rows=con.execute('SELECT * FROM jobs').fetchall()
            relevant=sum(bool(json.loads(r['explanation']).get('role_aligned')) for r in all_rows)
            eligible=sum(bool(json.loads(r['explanation']).get('role_aligned')) and bool(json.loads(r['explanation']).get('location_eligible')) for r in all_rows)
            result = {'role_matches':relevant,'role_and_location_matches':eligible,'discovered_records':len(jobs),'new_feed_records':inserted,
                      'prepared':prepared,'duplicates_hidden':hidden,'failures':failures,'alert_leads':sum(bool(r['needs_review']) for r in all_rows),
                      'ai':dict(cfg['llm'].get('_stats',{})),
                      'email':send_digest(con,cfg,root) if allow_email and not dry_run else 'not sent'}
            event(con,'run',json.dumps(result))
            LOG.info('Run completed: %s',json.dumps(result))
            return result
        finally:
            con.close()


def demo_root(root):
    """A physically separate database/output tree. Demo cannot pollute real job history."""
    dest = root/'examples/demo-output'
    (dest/'config').mkdir(parents=True,exist_ok=True)
    (dest/'examples').mkdir(exist_ok=True)
    cfg = load_config(root)
    if cfg.get('search_profile',{}).get('families')==['hr']:
        shutil.copy2(root/'examples/jobs.json',dest/'examples/jobs.json')
    else:
        title=(cfg.get('target_titles') or ['Custom role'])[0]
        if cfg.get('target_seniority')=='senior' and not any(word in title.lower() for word in ('senior','head','director','lead')):
            title='Senior '+title
        skills=list(dict.fromkeys(p for values in cfg.get('search_profile',{}).get('detected_skills',{}).values() for p in values))[:25]
        description='Synthetic example, not a real vacancy. We are seeking a '+title+' with experience in '+', '.join(skills)+'. This description exists only to demonstrate matching against your source resume.'
        city=cfg['locations'][0]
        demo=[{'title':title,'company':'DEMO ONLY — Profile Match','location':city,'url':'https://example.com/demo/profile-one','description':description},
              {'title':title,'company':'DEMO ONLY — Second Profile Match','location':'Remote, '+cfg['home_country'] if cfg.get('home_country') and 'remote' in cfg.get('work_modes',[]) else city,'url':'https://example.com/demo/profile-two','description':description},
              {'title':'Unrelated Vacancy','company':'DEMO ONLY — Field Check','location':city,'url':'https://example.com/demo/unrelated','description':'Synthetic unrelated role, included to demonstrate the career-field mismatch cap. This is not a real vacancy.'},
              {'title':title,'company':'DEMO ONLY — Location Check','location':'Unconfirmed location','url':'https://example.com/demo/location','description':description}]
        (dest/'examples/jobs.json').write_text(json.dumps(demo,indent=2))
    original = root/cfg['resume']
    (dest/'data/resumes').mkdir(parents=True,exist_ok=True)
    shutil.copy2(original,dest/'data/resumes'/original.name)
    cfg['resume'] = 'data/resumes/'+original.name
    cfg['email']['enabled'] = False
    cfg['llm'] = {'provider':'none'}
    cfg['sources'] = []
    (dest/'config/settings.json').write_text(json.dumps(cfg,indent=2))
    return dest


def main():
    p = argparse.ArgumentParser(description='Local HR job discovery; never auto-applies')
    p.add_argument('command',choices=['run','prepare','alerts','demo','check'])
    p.add_argument('--no-email',action='store_true')
    args = p.parse_args()
    try:
        if args.command == 'check':
            c = load_config()
            facts = read_facts(ROOT/c['resume'])
            c,_ = sync_profile(ROOT,c,facts)
            print(f'Configuration OK. {len(facts)} factual resume paragraphs. No network or email used.')
            return
        root = demo_root(ROOT) if args.command == 'demo' else ROOT
        print(json.dumps(run(root,dry_run=args.command=='demo',allow_email=not args.no_email and args.command!='prepare',refresh_sources=args.command!='prepare',alerts_only=args.command=='alerts'),indent=2))
    except Exception as exc:
        setup_logging()
        LOG.error('Run aborted (%s); check configuration/resume/dependencies',type(exc).__name__)
        print(f'Could not complete: {type(exc).__name__}. Check configuration, resume and logs/agent.log.')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
