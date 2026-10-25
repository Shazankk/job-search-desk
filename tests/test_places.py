import re

import pytest

from hr_agent import places


ADZUNA={
    'United Kingdom':'gb','United States':'us','Austria':'at','Australia':'au',
    'Belgium':'be','Brazil':'br','Canada':'ca','Switzerland':'ch','Germany':'de',
    'Spain':'es','France':'fr','India':'in','Italy':'it','Mexico':'mx',
    'Netherlands':'nl','New Zealand':'nz','Poland':'pl','Singapore':'sg',
    'South Africa':'za',
}
CITY_ROWS=[row.split('|') for row in places._CITY_DATA.strip().splitlines()]
CITY_LABELS=[f'{city}, {country}' for city,country,aliases in CITY_ROWS]


@pytest.mark.parametrize('text,expected',[
    ('PUNE','Pune, India'),
    (' pune ','Pune, India'),
    ('Pune, India','Pune, India'),
    ('pune maharashtra','Pune, India'),
    ('Pune, MH, India','Pune, India'),
    ('pune maharashtra india','Pune, India'),
    ('bangalore','Bengaluru, India'),
    ('NYC','New York, United States'),
    ('london uk','London, United Kingdom'),
    ('London, United Kingdom','London, United Kingdom'),
    ('uk','United Kingdom'),
    ('usa','United States'),
    ('germany','Germany'),
    ('Smalltown, Germany','Smalltown, Germany'),
    ('London, Canada','London, Canada'),
    ('gurgaon','Gurugram, India'),
    ('bombay','Mumbai, India'),
    ('madras','Chennai, India'),
    ('calcutta','Kolkata, India'),
    ('sf','San Francisco, United States'),
    ('san francisco bay area','San Francisco, United States'),
    ('washington dc','Washington, United States'),
    ('dc','Washington, United States'),
    ('saigon','Ho Chi Minh City, Vietnam'),
])
def test_contract_examples(text,expected):
    assert places.resolve(text)==expected
    assert places.resolve(places.resolve(text))==expected


@pytest.mark.parametrize('label',CITY_LABELS)
def test_all_city_labels_are_idempotent(label):
    assert places.resolve(label)==label
    assert places.resolve(places.resolve(label))==label
    assert places.country_of(label)==label.rsplit(', ',1)[1]
    assert places.match_terms(label)


@pytest.mark.parametrize('city,country,aliases',CITY_ROWS)
def test_all_city_names_and_aliases_with_explicit_country(city,country,aliases):
    label=f'{city}, {country}'
    for name in [city]+[a for a in aliases.split(';') if a]:
        assert places.resolve(f'{name.upper()}, {country.upper()}')==label
        assert places.resolve(f'  {name.lower()} , {country}  ')==label
        assert places.resolve(f'{name}, {places.COUNTRIES[country]["iso2"]}')==label


@pytest.mark.parametrize('country',sorted(places.COUNTRIES))
def test_all_countries_and_aliases(country):
    info=places.COUNTRIES[country]
    for name in [country,info['iso2']]+info['aliases']:
        assert places.resolve('  '+name.upper()+'  ')==country
        assert places.country_of(name)==country
        assert places.country_info(name) is info
        assert places.country_terms(name)==places.country_terms(country)
        assert places.match_terms(name)==places.country_terms(country)
    assert places.resolve(places.resolve(country))==country


@pytest.mark.parametrize('text,expected',[
    ('P.U.N.E.!!!','Pune, India'),
    ('\tPune\n Maharashtra\t IN ','Pune, India'),
    ('Pune (MH), India','Pune, India'),
    ('new-york, U.S.A.','New York, United States'),
    ('N.Y.C.','New York, United States'),
    ('London / U.K.','London, United Kingdom'),
    ('London; Ontario; Canada','London, Canada'),
    ('cambridge, massachusetts, usa','Cambridge, United States'),
    ('Ho-Chi-Minh-City, Viet Nam','Ho Chi Minh City, Vietnam'),
    ('sao paulo','São Paulo, Brazil'),
    ('SÃO PAULO','São Paulo, Brazil'),
    ('ZURICH','Zurich, Switzerland'),
    ('münchen','Munich, Germany'),
    ('wroclaw','Wrocław, Poland'),
    ('lodz','Łódź, Poland'),
    ('københavn','Copenhagen, Denmark'),
    ('st johns, canada',"St. John's, Canada"),
    ('Xi’an','Xi\'an, China'),
    ('Mexico City','Mexico City, Mexico'),
    ('Panama City','Panama City, Panama'),
    ('Port of Spain','Port of Spain, Trinidad and Tobago'),
    ('India, Pune','Pune, India'),
])
def test_normalization_and_country_boundaries(text,expected):
    assert places.resolve(text)==expected


@pytest.mark.parametrize('text,expected',[
    ('London','London, United Kingdom'),
    ('London, CA','London, Canada'),
    ('Cambridge','Cambridge, United Kingdom'),
    ('Cambridge US','Cambridge, United States'),
    ('Birmingham','Birmingham, United Kingdom'),
    ('Birmingham, USA','Birmingham, United States'),
    ('Hamilton','Hamilton, Canada'),
    ('Hamilton NZ','Hamilton, New Zealand'),
    ('San Jose','San Jose, United States'),
    ('San Jose, Costa Rica','San José, Costa Rica'),
    ('Newcastle','Newcastle upon Tyne, United Kingdom'),
    ('Newcastle, Australia','Newcastle, Australia'),
])
def test_ambiguous_names(text,expected):
    assert places.resolve(text)==expected


@pytest.mark.parametrize('text,expected',[
    ('smalltown, germany','Smalltown, Germany'),
    ('little village de','Little Village, Germany'),
    ('  little   village , Deutschland  ','Little   Village, Germany'),
    ('small-town, France','Small-Town, France'),
    ('unknown city UAE','Unknown City, United Arab Emirates'),
    ('xy, Germany','Xy, Germany'),
    ('Pune, Germany','Pune, Germany'),
])
def test_unknown_city_with_known_country(text,expected):
    assert places.resolve(text)==expected
    assert places.resolve(expected)==expected
    assert places.country_of(text)==expected.rsplit(', ',1)[1]
    assert places.match_terms(text)


@pytest.mark.parametrize('text',[
    '', '   ', '!!!', 'Atlantis', 'Smalltown', 'smalltown, wakanda',
    'londonish', 'notpune', 'nycity', 'germanyish', 'suburb of nowhere',
])
def test_unknown_text(text):
    assert places.resolve(text) is None
    assert places.country_of(text) is None
    assert places.match_terms(text)==[]
    assert places.country_info(text) is None
    assert places.country_terms(text)==[]


@pytest.mark.parametrize('label',CITY_LABELS+sorted(places.COUNTRIES))
def test_match_terms_are_lowercase_nonempty_unique_and_not_two_letter_codes(label):
    terms=places.match_terms(label)
    assert terms
    assert terms==list(dict.fromkeys(terms))
    assert all(term==term.lower() for term in terms)
    assert all(not re.fullmatch(r'[a-z]{2}',term) for term in terms)
    canonical=label.rsplit(', ',1)[0] if label not in places.COUNTRIES else label
    assert canonical.lower() in terms


@pytest.mark.parametrize('city,country,aliases',CITY_ROWS)
def test_match_terms_include_city_aliases(city,country,aliases):
    terms=places.match_terms(f'{city}, {country}')
    for alias in aliases.split(';'):
        if alias and not re.fullmatch(r'[a-z]{2}',alias):
            assert alias.lower() in terms


def test_match_terms_examples():
    assert places.match_terms('Bengaluru, India')==['bengaluru','bangalore']
    assert 'nyc' in places.match_terms('New York, United States')
    assert 'new york city' in places.match_terms('New York, United States')
    assert 'san francisco bay area' in places.match_terms('sf')
    assert 'sf' not in places.match_terms('sf')
    assert 'dc' not in places.match_terms('Washington, United States')
    assert 'washington dc' in places.match_terms('Washington, United States')
    assert places.match_terms('Smalltown, Germany')==['smalltown']
    assert places.country_terms('uk')==[
        'united kingdom','great britain','britain','england','scotland','wales',
        'northern ireland',
    ]
    assert places.country_terms('usa')==[
        'united states','usa','united states of america','america',
    ]
    assert places.country_info(' Bharat ') is places.COUNTRIES['India']
    assert places.country_info('u.a.e.') is places.COUNTRIES['United Arab Emirates']


def test_country_data_integrity():
    assert len(places.COUNTRIES)>=70
    codes=[info['iso2'] for info in places.COUNTRIES.values()]
    assert len(codes)==len(set(codes))
    assert all(re.fullmatch('[A-Z]{2}',code) for code in codes)
    for country,info in places.COUNTRIES.items():
        assert set(info)=={'iso2','aliases','adzuna','utc'}
        assert isinstance(info['aliases'],list)
        assert all(isinstance(alias,str) and alias for alias in info['aliases'])
        assert info['adzuna']==ADZUNA.get(country)
        assert info['utc'] and isinstance(info['utc'],list)
        assert len(info['utc'])==len(set(info['utc']))
        assert all(isinstance(offset,(int,float)) and -12<=offset<=14 for offset in info['utc'])
        for name in [country,info['iso2']]+info['aliases']:
            assert places._COUNTRY_INDEX[places._norm(name)]==country


def test_city_data_integrity():
    assert len(CITY_ROWS)>=400
    assert len(CITY_LABELS)==len(set(CITY_LABELS))
    assert len(places._CITIES)==len(CITY_ROWS)
    assert {country for city,country,aliases in CITY_ROWS}==set(places.COUNTRIES)
    for city,country,aliases in CITY_ROWS:
        assert city and city==city.strip()
        assert country in places.COUNTRIES
        assert ',' not in city
        assert len(places._norm(city))>2
        for name in [city]+[a for a in aliases.split(';') if a]:
            assert name==name.strip()
            labels=places._CITY_INDEX[places._norm(name)]
            assert f'{city}, {country}' in labels
            assert len([label for label in labels if label.endswith(', '+country)])==1


@pytest.mark.parametrize('country,iso2,utc',[
    ('India','IN',[5.5]),
    ('United Kingdom','GB',[0]),
    ('United States','US',[-5,-6,-7,-8,-9,-10]),
    ('Canada','CA',[-3.5,-4,-5,-6,-7,-8]),
    ('Australia','AU',[8,8.75,9.5,10,10.5]),
    ('New Zealand','NZ',[12,12.75]),
    ('Nepal','NP',[5.75]),
    ('Myanmar','MM',[6.5]),
    ('Germany','DE',[1]),
    ('United Arab Emirates','AE',[4]),
    ('South Africa','ZA',[2]),
    ('Brazil','BR',[-2,-3,-4,-5]),
    ('Kazakhstan','KZ',[5]),
    ('Jordan','JO',[3]),
    ('Spain','ES',[0,1]),
    ('Portugal','PT',[-1,0]),
])
def test_country_codes_and_standard_offsets(country,iso2,utc):
    info=places.country_info(country)
    assert info['iso2']==iso2
    assert info['utc']==utc


def test_required_indian_cities():
    for city in ['Pune','Hyderabad','Noida','Navi Mumbai','Thane','Ahmedabad',
                 'Kochi','Coimbatore','Indore','Jaipur','Chandigarh','Nagpur',
                 'Lucknow','Bhubaneswar','Mysuru','Visakhapatnam','Vadodara',
                 'Surat','Nashik']:
        assert places.resolve(city.upper())==f'{city}, India'


def test_countries_dropdown_is_sorted_and_independent():
    names=places.countries()
    assert names==sorted(places.COUNTRIES)
    names.clear()
    assert places.countries()==sorted(places.COUNTRIES)
