"""Import local inputs/configuration and a consistent SQLite snapshot from v1."""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from job_search_desk.core import ROOT, load_config
from job_search_desk.profile import atomic_config, sync_profile, refresh_scores
from job_search_desk.resume import read_facts
from job_search_desk.runner import run_lock


def import_previous(old,root=ROOT):
    old=Path(old).resolve();root=Path(root).resolve()
    if old==root:
        raise ValueError('Choose the older folder, not this folder')
    cfg=json.loads((old/'config/settings.json').read_text())
    resume=(old/cfg['resume']).resolve()
    if not resume.is_relative_to(old/'data/resumes') or not resume.is_file():
        raise ValueError('The old resume must be inside its data/resumes folder')
    read_facts(resume)
    with run_lock(root):
        # Validate and snapshot before replacing destination files. Original stays untouched.
        with tempfile.TemporaryDirectory(prefix='import-',dir=root/'data') as scratch:
            staged=Path(scratch)
            for name in ('resumes','inbox','imports','contacts'):
                directory=old/'data'/name
                if not directory.exists():continue
                target=staged/name;target.mkdir()
                for p in directory.iterdir():
                    if p.is_file() and not p.is_symlink() and p.suffix.lower() in ('.docx','.txt','.eml','.json'):
                        shutil.copy2(p,target/p.name)
            if (old/'data/jobs.sqlite').exists():
                source=sqlite3.connect((old/'data/jobs.sqlite').as_uri()+'?mode=ro',uri=True)
                dest=sqlite3.connect(staged/'jobs.sqlite')
                try:source.backup(dest)
                finally:dest.close();source.close()
            for key in ('llm','email','alerts_imap'):
                for secret_field in ('api_key','app_key','password'):
                    cfg.get(key,{}).pop(secret_field,None)
            cfg['resume']=str(resume.relative_to(old))
            for name in ('resumes','inbox','imports','contacts'):
                if (staged/name).exists():
                    shutil.copytree(staged/name,root/'data'/name,dirs_exist_ok=True)
            if (staged/'jobs.sqlite').exists():
                # Destination dashboard should be closed; do not mix a new DB with old WAL files.
                for suffix in ('','-wal','-shm'):
                    (root/'data'/('jobs.sqlite'+suffix)).unlink(missing_ok=True)
                shutil.copy2(staged/'jobs.sqlite',root/'data/jobs.sqlite')
            # Copying artifacts is unnecessary: all packets are rebuilt for the imported profile.
            atomic_config(root,cfg)
            cfg=load_config(root)  # fills new optional discovery settings for v1 installs
            facts=read_facts(root/cfg['resume'])
            cfg,_=sync_profile(root,cfg,facts)
            refresh_scores(root,cfg,facts)
            # Reparse original email files with the v1.1 portal-card parser.
            from job_search_desk.core import db
            con=db(root)
            con.execute('DELETE FROM imports')
            con.execute("DELETE FROM jobs WHERE source='email-alert' AND needs_review=1 AND status IN ('new','shortlisted')")
            con.commit();con.close()
            return cfg


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('folder',nargs='?')
    args=parser.parse_args()
    folder=args.folder
    if not folder:
        if sys.platform!='darwin':raise SystemExit('Supply the old project folder')
        result=subprocess.run(['/usr/bin/osascript','-e','POSIX path of (choose folder with prompt "Choose your OLD HR-Search-Agent folder. Its settings and data will be copied into this new project.")'],capture_output=True,text=True)
        if result.returncode:raise SystemExit('Import cancelled')
        folder=result.stdout.strip()
    try:
        cfg=import_previous(folder)
    except Exception as exc:
        raise SystemExit(f'Import did not complete ({type(exc).__name__}). Check the chosen folder. Your original folder is unchanged.')
    print('Imported candidate:',cfg['candidate_name'])
    print('Resume, search profile and saved-job scores updated. Reopen the dashboard and prepare saved jobs.')
    print('Existing Keychain secrets remain available. Install the daily schedule from the new folder to replace its old path.')


if __name__=='__main__':main()
