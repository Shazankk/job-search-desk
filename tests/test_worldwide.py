import json
from hr_agent.core import load_config
from hr_agent.discovery import plan, himalayas_job
from hr_agent.portals import search_links
from hr_agent.scoring import location_fit, work_mode


def cfg(places=('Pune, India',), modes=('onsite','hybrid','remote'), home='India'):
    return {'locations':list(places),'work_modes':list(modes),'home_country':home}


def fit(location, config, description=''):
    return location_fit({'location':location,'description':description},config)


def test_old_config_migrates_to_places_and_work_modes(root):
    path = root/'config/settings.json'
    c = json.loads(path.read_text())
    for key in ('work_modes','home_country'):
        c.pop(key,None)
    c.update(locations=['PUNE','bangalore'],remote_india=False)
    path.write_text(json.dumps(c))
    loaded = load_config(root)
    assert loaded['locations'] == ['Pune, India','Bengaluru, India']
    assert loaded['work_modes'] == ['onsite','hybrid'] and loaded['home_country'] == 'India'
    assert 'remote_india' not in json.loads(path.read_text())


def test_city_aliases_and_arrangements():
    c = cfg(['Bengaluru, India','London, United Kingdom'])
    assert fit('Bangalore Urban, Karnataka, India',c)[0] == 2
    assert fit('London, England, United Kingdom (Hybrid)',c)[0] == 2
    assert work_mode({'location':'London (Hybrid)'}) == 'hybrid'
    assert work_mode({'location':'London','description':'This is a fully remote role.'}) == 'remote'
    assert work_mode({'location':'London','description':'Our remote teams collaborate.'}) is None
    points, _, warnings = fit('London, United Kingdom (On-site)',cfg(['London, United Kingdom'],['remote','hybrid'],'United Kingdom'))
    assert points == 0.5 and 'you chose Hybrid / Remote only' in warnings[0]


def test_remote_needs_your_country_or_worldwide():
    c = cfg(['Berlin, Germany'],home='Germany')
    assert fit('Remote, Germany',c)[0] == 2
    assert fit('Remote - Worldwide',c)[0] == 2
    assert fit('Remote, United States only',c)[0] == 0.5
    assert fit('Remote',c)[0] == 0.5
    assert fit('Remote, Germany',cfg(['Berlin, Germany'],['onsite'],'Germany'))[0] == 0.5
    assert fit('Paris, France',c)[0] == 0


def test_country_wide_place_matches_any_city():
    assert fit('Munich, Bavaria, Germany',cfg(['Germany'],home='Germany'))[0] == 2


def test_sources_follow_the_users_country():
    c = {**cfg(['London, United Kingdom','Pune, India'],home='United Kingdom'),'target_titles':['Data Analyst'],
         'search_profile':{'families':['data']},
         'discovery':{'max_queries':1,'himalayas':{'enabled':True},'adzuna':{'enabled':True},'naukri_sitemap':{'enabled':True},
                      'linkedin_public':{'enabled':True,'max_searches_per_run':3}}}
    specs = plan(c)
    assert {s['location'] for s in specs if s['provider']=='naukri_sitemap'} == {'Pune, India'}
    assert [s['country'] for s in specs if s['provider']=='himalayas'] == ['United Kingdom']
    assert {(s['location'],s['country_code']) for s in specs if s['provider']=='adzuna'} == {('London, United Kingdom','gb'),('Pune, India','in')}
    remote = [s for s in specs if s.get('remote')]
    assert remote and remote[0]['location'] == 'United Kingdom'
    links = search_links(c)
    assert not [l for l in links if l['portal']=='Naukri' and 'London' in l['location']]
    assert any(l['portal']=='LinkedIn' and l['location']=='Remote, United Kingdom' for l in links)


def test_himalayas_eligibility_uses_home_country():
    item = {'title':'Analyst','companyName':'Example','guid':'https://himalayas.app/companies/example/jobs/analyst',
            'applicationLink':'https://example.com/apply','description':'Analyse data for the team. '*10,
            'locationRestrictions':['United Kingdom'],'timezoneRestrictions':[0]}
    uk = himalayas_job(item,'United Kingdom')
    assert uk['eligibility'] == 'confirmed' and uk['location'] == 'Remote, United Kingdom'
    assert himalayas_job(item,'India')['eligibility'] == 'excluded'


def test_dashboard_recognises_places_and_saves_work_arrangements(root,monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    import hr_agent.core as core
    original=core.load_config
    monkeypatch.setattr(core,'ROOT',root)
    monkeypatch.setattr(core,'load_config',lambda *args:original(args[0] if args else root))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'dashboard.py'),default_timeout=20).run()
    app.session_state['section']='Resume & settings'
    app.run()
    next(w for w in app.text_input if w.label.startswith('Cities or countries')).input('PUNE, london uk, Smallville').run()
    assert any('Pune, India · London, United Kingdom' in c.value for c in app.caption)
    next(w for w in app.button if w.label=='Save search preferences').click().run()
    assert any('Choose a country' in e.value for e in app.error)  # unknown town blocks saving
    next(w for w in app.selectbox if 'Smallville' in w.label).select('United States').run()
    next(w for w in app.button_group if w.label.startswith('Work arrangements')).set_value(['hybrid','remote'])
    next(w for w in app.button if w.label=='Save search preferences').click().run()
    assert not app.exception
    saved=json.loads((root/'config/settings.json').read_text())
    assert saved['locations']==['Pune, India','London, United Kingdom','Smallville, United States']
    assert saved['work_modes']==['hybrid','remote'] and saved['home_country']=='India'
