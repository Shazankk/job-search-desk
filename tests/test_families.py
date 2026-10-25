import pytest
from hr_agent.discovery import FAMILY_QUERIES
from hr_agent.profile import FAMILIES, infer_profile, title_families


@pytest.mark.parametrize('family,title,experience',[
    ('healthcare','Registered Nurse','Provided patient assessment and medication administration.'),
    ('education','Teacher','Delivered classroom teaching and lesson planning.'),
    ('legal','Legal Counsel','Handled litigation and legal drafting.'),
    ('engineering','Mechanical Engineer','Performed mechanical design and finite element analysis.'),
])
def test_new_family_inferred(family,title,experience):
    facts=['ALEX EXAMPLE',title,'Pune, India','PROFESSIONAL EXPERIENCE',experience]
    assert infer_profile(facts)['search_profile']['families']==[family]


@pytest.mark.parametrize('family,title',[
    (family,title)
    for family in ('healthcare','education','legal','engineering')
    for title in FAMILIES[family]['titles']
])
def test_new_family_titles_inferred(family,title):
    facts=['ALEX EXAMPLE',title,'Pune, India','PROFESSIONAL EXPERIENCE']
    assert infer_profile(facts)['search_profile']['families']==[family]


def test_hr_compliance_does_not_add_legal():
    facts=['ALEX EXAMPLE','HR Manager','Pune, India','PROFESSIONAL EXPERIENCE',
           'Managed human resources, payroll and talent acquisition.',
           'Maintained compliance with labour law and labor law.']
    assert infer_profile(facts)['search_profile']['families']==['hr']


def test_software_does_not_add_engineering():
    facts=['ALEX EXAMPLE','Senior Software Engineer | Backend Engineer','Pune, India',
           'TECHNICAL SKILLS','Python, Django, React, Docker, Kubernetes, pytest',
           'PROFESSIONAL EXPERIENCE',
           'Built distributed systems and REST APIs using system design and automated testing.',
           'Performed root cause analysis and maintained software quality control.']
    assert infer_profile(facts)['search_profile']['families']==['software']


@pytest.mark.parametrize('family',['healthcare','education','legal','engineering'])
def test_new_family_search_queries(family):
    assert 2<=len(FAMILY_QUERIES[family])<=3
    assert all(isinstance(query,str) and query.strip() for query in FAMILY_QUERIES[family])


@pytest.mark.parametrize('title,family',[
    ('Staff Nurse','healthcare'),
    ('Mechanical Engineer','engineering'),
])
def test_title_families(title,family):
    assert family in title_families(title)
