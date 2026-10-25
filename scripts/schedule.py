"""Install one per-user LaunchAgent, with absolute paths and XML-safe escaping."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hr_agent.core import ROOT, load_config

LABEL = 'local.hr-search.daily'


def plist(root, cfg):
    return {'Label':LABEL,'ProgramArguments':[str(root/'.venv/bin/python'),'-m','hr_agent.runner','run'],
            'WorkingDirectory':str(root),
            'StartCalendarInterval':{'Hour':int(cfg['schedule']['hour']),'Minute':int(cfg['schedule']['minute'])},
            'RunAtLoad':False,'ProcessType':'Background','Umask':0o077,
            'StandardOutPath':str(root/'logs/scheduled.stdout.log'),
            'StandardErrorPath':str(root/'logs/scheduled.stderr.log')}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action',choices=['install','uninstall','print'])
    args = p.parse_args()
    cfg = load_config()
    raw = plistlib.dumps(plist(ROOT,cfg))
    if args.action == 'print':
        print(raw.decode())
        return
    if sys.platform != 'darwin':
        raise SystemExit('launchd installation requires macOS')
    target = Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    domain = f'gui/{os.getuid()}'
    if args.action == 'uninstall':
        subprocess.run(['/bin/launchctl','bootout',domain+'/'+LABEL],capture_output=True)
        target.unlink(missing_ok=True)
        print('Daily schedule removed. Local job data retained.')
        return
    (ROOT/'logs').mkdir(exist_ok=True,mode=0o700)
    target.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['/bin/launchctl','bootout',domain+'/'+LABEL],capture_output=True)
    target.write_bytes(raw)
    target.chmod(0o600)
    result = subprocess.run(['/bin/launchctl','bootstrap',domain,str(target)],capture_output=True,text=True)
    if result.returncode:
        print('Could not load schedule. Check macOS background-item permissions and path access.')
        raise SystemExit(result.returncode)
    print(f"Daily run installed for {cfg['schedule']['hour']:02d}:{cfg['schedule']['minute']:02d} in this Mac's local timezone.")
    print('Keep this folder in place. Reinstall the schedule after moving it. The Mac must be logged in; sleeping runs are deferred until wake.')


if __name__ == '__main__':
    main()
