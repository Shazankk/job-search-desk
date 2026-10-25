import json
from pathlib import Path
import shutil
import sys
import pytest
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from job_search_desk.core import ROOT


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests never reach real job sites; patch a source's fetch function instead."""
    def refuse(self, request, **kwargs):
        raise RuntimeError('Real network access in tests: '+request.url)
    monkeypatch.setattr(requests.sessions.Session,'send',refuse)


@pytest.fixture
def root(tmp_path):
    for name in ('config','examples','data/resumes','data/imports','data/inbox','data/contacts'):
        (tmp_path/name).mkdir(parents=True,exist_ok=True)
    for name in ('jobs.json','alert.eml'):
        shutil.copy2(ROOT/'examples'/name,tmp_path/'examples'/name)
    shutil.copy2(ROOT/'config/settings.example.json',tmp_path/'config/settings.example.json')
    shutil.copy2(ROOT/'examples/sample-resume.docx',tmp_path/'examples/sample-resume.docx')
    c = json.loads((ROOT/'config/settings.example.json').read_text())
    c['sources'] = []
    c['discovery'] = {}
    (tmp_path/'config/settings.json').write_text(json.dumps(c))
    return tmp_path
