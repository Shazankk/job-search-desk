"""Offline country and city lookup for job locations."""
import re
import unicodedata


COUNTRIES={
    'India': {'iso2':'IN','aliases':['bharat'],'adzuna':'in','utc':[5.5]},
    'United States': {'iso2':'US','aliases':['usa','us','united states of america','america'],'adzuna':'us','utc':[-5,-6,-7,-8,-9,-10]},
    'United Kingdom': {'iso2':'GB','aliases':['uk','great britain','britain','england','scotland','wales','northern ireland'],'adzuna':'gb','utc':[0]},
    'Canada': {'iso2':'CA','aliases':[],'adzuna':'ca','utc':[-3.5,-4,-5,-6,-7,-8]},
    'Germany': {'iso2':'DE','aliases':['deutschland'],'adzuna':'de','utc':[1]},
    'France': {'iso2':'FR','aliases':[],'adzuna':'fr','utc':[1]},
    'Spain': {'iso2':'ES','aliases':['españa'],'adzuna':'es','utc':[0,1]},
    'Italy': {'iso2':'IT','aliases':['italia'],'adzuna':'it','utc':[1]},
    'Netherlands': {'iso2':'NL','aliases':['holland','the netherlands'],'adzuna':'nl','utc':[1]},
    'Belgium': {'iso2':'BE','aliases':['belgique','belgië'],'adzuna':'be','utc':[1]},
    'Austria': {'iso2':'AT','aliases':['österreich'],'adzuna':'at','utc':[1]},
    'Switzerland': {'iso2':'CH','aliases':['schweiz','suisse','svizzera'],'adzuna':'ch','utc':[1]},
    'Poland': {'iso2':'PL','aliases':['polska'],'adzuna':'pl','utc':[1]},
    'Portugal': {'iso2':'PT','aliases':[],'adzuna':None,'utc':[-1,0]},
    'Ireland': {'iso2':'IE','aliases':['republic of ireland','eire'],'adzuna':None,'utc':[0]},
    'Sweden': {'iso2':'SE','aliases':['sverige'],'adzuna':None,'utc':[1]},
    'Norway': {'iso2':'NO','aliases':['norge'],'adzuna':None,'utc':[1]},
    'Denmark': {'iso2':'DK','aliases':['danmark'],'adzuna':None,'utc':[1]},
    'Finland': {'iso2':'FI','aliases':['suomi'],'adzuna':None,'utc':[2]},
    'Iceland': {'iso2':'IS','aliases':[],'adzuna':None,'utc':[0]},
    'Czechia': {'iso2':'CZ','aliases':['czech republic'],'adzuna':None,'utc':[1]},
    'Slovakia': {'iso2':'SK','aliases':['slovak republic'],'adzuna':None,'utc':[1]},
    'Hungary': {'iso2':'HU','aliases':['magyarország'],'adzuna':None,'utc':[1]},
    'Romania': {'iso2':'RO','aliases':[],'adzuna':None,'utc':[2]},
    'Bulgaria': {'iso2':'BG','aliases':[],'adzuna':None,'utc':[2]},
    'Greece': {'iso2':'GR','aliases':['hellas'],'adzuna':None,'utc':[2]},
    'Croatia': {'iso2':'HR','aliases':['hrvatska'],'adzuna':None,'utc':[1]},
    'Slovenia': {'iso2':'SI','aliases':[],'adzuna':None,'utc':[1]},
    'Serbia': {'iso2':'RS','aliases':[],'adzuna':None,'utc':[1]},
    'Estonia': {'iso2':'EE','aliases':['eesti'],'adzuna':None,'utc':[2]},
    'Latvia': {'iso2':'LV','aliases':[],'adzuna':None,'utc':[2]},
    'Lithuania': {'iso2':'LT','aliases':['lietuva'],'adzuna':None,'utc':[2]},
    'Ukraine': {'iso2':'UA','aliases':[],'adzuna':None,'utc':[2]},
    'Turkey': {'iso2':'TR','aliases':['türkiye','turkiye'],'adzuna':None,'utc':[3]},
    'Russia': {'iso2':'RU','aliases':['russian federation'],'adzuna':None,'utc':[2,3,4,5,6,7,8,9,10,11,12]},
    'Georgia': {'iso2':'GE','aliases':['sakartvelo'],'adzuna':None,'utc':[4]},
    'Armenia': {'iso2':'AM','aliases':[],'adzuna':None,'utc':[4]},
    'Azerbaijan': {'iso2':'AZ','aliases':[],'adzuna':None,'utc':[4]},
    'United Arab Emirates': {'iso2':'AE','aliases':['uae','emirates'],'adzuna':None,'utc':[4]},
    'Saudi Arabia': {'iso2':'SA','aliases':['ksa'],'adzuna':None,'utc':[3]},
    'Qatar': {'iso2':'QA','aliases':[],'adzuna':None,'utc':[3]},
    'Bahrain': {'iso2':'BH','aliases':[],'adzuna':None,'utc':[3]},
    'Kuwait': {'iso2':'KW','aliases':[],'adzuna':None,'utc':[3]},
    'Oman': {'iso2':'OM','aliases':[],'adzuna':None,'utc':[4]},
    'Israel': {'iso2':'IL','aliases':[],'adzuna':None,'utc':[2]},
    'Jordan': {'iso2':'JO','aliases':[],'adzuna':None,'utc':[3]},
    'Lebanon': {'iso2':'LB','aliases':[],'adzuna':None,'utc':[2]},
    'Egypt': {'iso2':'EG','aliases':[],'adzuna':None,'utc':[2]},
    'Morocco': {'iso2':'MA','aliases':['maroc'],'adzuna':None,'utc':[1]},
    'Tunisia': {'iso2':'TN','aliases':[],'adzuna':None,'utc':[1]},
    'Algeria': {'iso2':'DZ','aliases':[],'adzuna':None,'utc':[1]},
    'South Africa': {'iso2':'ZA','aliases':['rsa'],'adzuna':'za','utc':[2]},
    'Nigeria': {'iso2':'NG','aliases':[],'adzuna':None,'utc':[1]},
    'Kenya': {'iso2':'KE','aliases':[],'adzuna':None,'utc':[3]},
    'Ghana': {'iso2':'GH','aliases':[],'adzuna':None,'utc':[0]},
    'Ethiopia': {'iso2':'ET','aliases':[],'adzuna':None,'utc':[3]},
    'Tanzania': {'iso2':'TZ','aliases':[],'adzuna':None,'utc':[3]},
    'Uganda': {'iso2':'UG','aliases':[],'adzuna':None,'utc':[3]},
    'Rwanda': {'iso2':'RW','aliases':[],'adzuna':None,'utc':[2]},
    'Senegal': {'iso2':'SN','aliases':[],'adzuna':None,'utc':[0]},
    'Mauritius': {'iso2':'MU','aliases':[],'adzuna':None,'utc':[4]},
    'Australia': {'iso2':'AU','aliases':['aus'],'adzuna':'au','utc':[8,8.75,9.5,10,10.5]},
    'New Zealand': {'iso2':'NZ','aliases':['aotearoa'],'adzuna':'nz','utc':[12,12.75]},
    'Singapore': {'iso2':'SG','aliases':[],'adzuna':'sg','utc':[8]},
    'Malaysia': {'iso2':'MY','aliases':[],'adzuna':None,'utc':[8]},
    'Indonesia': {'iso2':'ID','aliases':[],'adzuna':None,'utc':[7,8,9]},
    'Thailand': {'iso2':'TH','aliases':[],'adzuna':None,'utc':[7]},
    'Vietnam': {'iso2':'VN','aliases':['viet nam'],'adzuna':None,'utc':[7]},
    'Philippines': {'iso2':'PH','aliases':['the philippines'],'adzuna':None,'utc':[8]},
    'Japan': {'iso2':'JP','aliases':['nippon','nihon'],'adzuna':None,'utc':[9]},
    'South Korea': {'iso2':'KR','aliases':['korea','republic of korea'],'adzuna':None,'utc':[9]},
    'China': {'iso2':'CN','aliases':['prc','peoples republic of china',"people's republic of china"],'adzuna':None,'utc':[8]},
    'Taiwan': {'iso2':'TW','aliases':[],'adzuna':None,'utc':[8]},
    'Hong Kong': {'iso2':'HK','aliases':['hong kong sar'],'adzuna':None,'utc':[8]},
    'Pakistan': {'iso2':'PK','aliases':[],'adzuna':None,'utc':[5]},
    'Bangladesh': {'iso2':'BD','aliases':[],'adzuna':None,'utc':[6]},
    'Sri Lanka': {'iso2':'LK','aliases':['ceylon'],'adzuna':None,'utc':[5.5]},
    'Nepal': {'iso2':'NP','aliases':[],'adzuna':None,'utc':[5.75]},
    'Kazakhstan': {'iso2':'KZ','aliases':[],'adzuna':None,'utc':[5]},
    'Uzbekistan': {'iso2':'UZ','aliases':[],'adzuna':None,'utc':[5]},
    'Cambodia': {'iso2':'KH','aliases':[],'adzuna':None,'utc':[7]},
    'Myanmar': {'iso2':'MM','aliases':['burma'],'adzuna':None,'utc':[6.5]},
    'Brazil': {'iso2':'BR','aliases':['brasil'],'adzuna':'br','utc':[-2,-3,-4,-5]},
    'Mexico': {'iso2':'MX','aliases':['méxico'],'adzuna':'mx','utc':[-5,-6,-7,-8]},
    'Argentina': {'iso2':'AR','aliases':[],'adzuna':None,'utc':[-3]},
    'Chile': {'iso2':'CL','aliases':[],'adzuna':None,'utc':[-6,-4,-3]},
    'Colombia': {'iso2':'CO','aliases':[],'adzuna':None,'utc':[-5]},
    'Peru': {'iso2':'PE','aliases':['perú'],'adzuna':None,'utc':[-5]},
    'Uruguay': {'iso2':'UY','aliases':[],'adzuna':None,'utc':[-3]},
    'Ecuador': {'iso2':'EC','aliases':[],'adzuna':None,'utc':[-6,-5]},
    'Costa Rica': {'iso2':'CR','aliases':[],'adzuna':None,'utc':[-6]},
    'Panama': {'iso2':'PA','aliases':['panamá'],'adzuna':None,'utc':[-5]},
    'Dominican Republic': {'iso2':'DO','aliases':[],'adzuna':None,'utc':[-4]},
    'Jamaica': {'iso2':'JM','aliases':[],'adzuna':None,'utc':[-5]},
    'Trinidad and Tobago': {'iso2':'TT','aliases':['trinidad & tobago'],'adzuna':None,'utc':[-4]},
    'Fiji': {'iso2':'FJ','aliases':[],'adzuna':None,'utc':[12]},
    'Papua New Guinea': {'iso2':'PG','aliases':['png'],'adzuna':None,'utc':[10,11]},
}

# Offsets cover the named countries and integral regions, excluding dependencies.
_CITY_DATA="""
Pune|India|poona
Bengaluru|India|bangalore
Mumbai|India|bombay
Chennai|India|madras
Kolkata|India|calcutta
Gurugram|India|gurgaon
Delhi|India|new delhi
Hyderabad|India|
Noida|India|
Navi Mumbai|India|new bombay
Thane|India|
Ahmedabad|India|ahmedabad city
Kochi|India|cochin
Coimbatore|India|
Indore|India|
Jaipur|India|
Chandigarh|India|
Nagpur|India|
Lucknow|India|
Bhubaneswar|India|bhubaneshwar
Mysuru|India|mysore
Visakhapatnam|India|vizag
Vadodara|India|baroda
Surat|India|
Nashik|India|nasik
Bhopal|India|
Patna|India|
Ranchi|India|
Raipur|India|
Guwahati|India|gauhati
Thiruvananthapuram|India|trivandrum
Kozhikode|India|calicut
Thrissur|India|trichur
Mangaluru|India|mangalore
Madurai|India|
Tiruchirappalli|India|trichy;tiruchi
Salem|India|
Vijayawada|India|
Guntur|India|
Warangal|India|
Tirupati|India|
Rajahmundry|India|rajamahendravaram
Kanpur|India|cawnpore
Agra|India|
Varanasi|India|benares;banaras
Prayagraj|India|allahabad
Meerut|India|
Ghaziabad|India|
Faridabad|India|
Greater Noida|India|
Dehradun|India|
Haridwar|India|
Shimla|India|simla
Mohali|India|sahibzada ajit singh nagar
Panchkula|India|
Ludhiana|India|
Amritsar|India|
Jalandhar|India|
Jodhpur|India|
Udaipur|India|
Kota|India|
Ajmer|India|
Rajkot|India|
Gandhinagar|India|
Jamnagar|India|
Chhatrapati Sambhajinagar|India|aurangabad
Kolhapur|India|
Solapur|India|
Jabalpur|India|
Gwalior|India|
Ujjain|India|
Jamshedpur|India|
Dhanbad|India|
Bokaro Steel City|India|bokaro
Durgapur|India|
Siliguri|India|
Howrah|India|haora
Asansol|India|
Cuttack|India|
Rourkela|India|
Shillong|India|
Imphal|India|
Agartala|India|
Aizawl|India|
Gangtok|India|
Panaji|India|panjim
Margao|India|madgaon
Belagavi|India|belgaum
Hubballi|India|hubli
Dharwad|India|
Davanagere|India|davangere
Tumakuru|India|tumkur
Hosur|India|
Vellore|India|
Tiruppur|India|tirupur
Erode|India|
Puducherry|India|pondicherry
New York|United States|nyc;new york city
San Francisco|United States|sf;san francisco bay area
Washington|United States|washington dc;washington d.c.;dc
Los Angeles|United States|la
Chicago|United States|
Boston|United States|
Seattle|United States|
Austin|United States|
Dallas|United States|
Houston|United States|
Atlanta|United States|
Denver|United States|
San Diego|United States|
San Jose|United States|
Phoenix|United States|
Philadelphia|United States|philly
Miami|United States|
Orlando|United States|
Tampa|United States|
Charlotte|United States|
Raleigh|United States|
Durham|United States|
Pittsburgh|United States|
Detroit|United States|
Minneapolis|United States|
Portland|United States|
Salt Lake City|United States|slc
Las Vegas|United States|vegas
Sacramento|United States|
Oakland|United States|
Sunnyvale|United States|
Mountain View|United States|
Palo Alto|United States|
Santa Clara|United States|
Cupertino|United States|
Fremont|United States|
Irvine|United States|
Bellevue|United States|
Redmond|United States|
Columbus|United States|
Cincinnati|United States|
Cleveland|United States|
Indianapolis|United States|
Nashville|United States|
Memphis|United States|
Kansas City|United States|
St. Louis|United States|saint louis
Milwaukee|United States|
Madison|United States|
Baltimore|United States|
Richmond|United States|
Arlington|United States|
Newark|United States|
Jersey City|United States|
Buffalo|United States|
Rochester|United States|
Albany|United States|
Hartford|United States|
Providence|United States|
New Haven|United States|
Boulder|United States|
Colorado Springs|United States|
Albuquerque|United States|
Tucson|United States|
Omaha|United States|
Des Moines|United States|
Oklahoma City|United States|okc
Tulsa|United States|
Huntsville|United States|
Jacksonville|United States|
Fort Lauderdale|United States|ft lauderdale
Honolulu|United States|
Anchorage|United States|
London|United Kingdom|
Cambridge|United Kingdom|
Manchester|United Kingdom|
Birmingham|United Kingdom|brum
Birmingham|United States|
Bristol|United Kingdom|
Leeds|United Kingdom|
Liverpool|United Kingdom|
Edinburgh|United Kingdom|
Glasgow|United Kingdom|
Aberdeen|United Kingdom|
Dundee|United Kingdom|
Newcastle upon Tyne|United Kingdom|newcastle
Nottingham|United Kingdom|
Sheffield|United Kingdom|
Leicester|United Kingdom|
Coventry|United Kingdom|
Oxford|United Kingdom|
Reading|United Kingdom|
Slough|United Kingdom|
Milton Keynes|United Kingdom|
Southampton|United Kingdom|
Portsmouth|United Kingdom|
Brighton|United Kingdom|brighton and hove
Bournemouth|United Kingdom|
Exeter|United Kingdom|
Cardiff|United Kingdom|
Swansea|United Kingdom|
Belfast|United Kingdom|
York|United Kingdom|
Bath|United Kingdom|
Derby|United Kingdom|
Norwich|United Kingdom|
Ipswich|United Kingdom|
Peterborough|United Kingdom|
Swindon|United Kingdom|
Cheltenham|United Kingdom|
Guildford|United Kingdom|
Watford|United Kingdom|
Luton|United Kingdom|
Cambridge|United States|
Toronto|Canada|gta;greater toronto area
Vancouver|Canada|
Montreal|Canada|montréal
Ottawa|Canada|
Calgary|Canada|
Edmonton|Canada|
Winnipeg|Canada|
Quebec City|Canada|québec;quebec
Halifax|Canada|
Victoria|Canada|
Waterloo|Canada|
Kitchener|Canada|
Mississauga|Canada|
Brampton|Canada|
Hamilton|Canada|
London|Canada|
Saskatoon|Canada|
Regina|Canada|
St. John's|Canada|saint john's;st johns
Fredericton|Canada|
Berlin|Germany|
Munich|Germany|münchen;muenchen
Hamburg|Germany|
Frankfurt|Germany|frankfurt am main
Cologne|Germany|köln;koeln
Düsseldorf|Germany|dusseldorf;duesseldorf
Stuttgart|Germany|
Dresden|Germany|
Leipzig|Germany|
Bonn|Germany|
Dortmund|Germany|
Essen|Germany|
Nuremberg|Germany|nürnberg;nuernberg
Hanover|Germany|hannover
Karlsruhe|Germany|
Mannheim|Germany|
Heidelberg|Germany|
Aachen|Germany|
Freiburg|Germany|freiburg im breisgau
Wiesbaden|Germany|
Paris|France|
Lyon|France|
Marseille|France|
Toulouse|France|
Bordeaux|France|
Lille|France|
Nantes|France|
Nice|France|
Strasbourg|France|
Rennes|France|
Montpellier|France|
Grenoble|France|
Madrid|Spain|
Barcelona|Spain|
Valencia|Spain|
Seville|Spain|sevilla
Bilbao|Spain|
Málaga|Spain|malaga
Zaragoza|Spain|
Alicante|Spain|
Palma|Spain|palma de mallorca
Las Palmas de Gran Canaria|Spain|las palmas
Rome|Italy|roma
Milan|Italy|milano
Turin|Italy|torino
Naples|Italy|napoli
Bologna|Italy|
Florence|Italy|firenze
Genoa|Italy|genova
Padua|Italy|padova
Verona|Italy|
Bari|Italy|
Amsterdam|Netherlands|
Rotterdam|Netherlands|
The Hague|Netherlands|den haag;s gravenhage
Utrecht|Netherlands|
Eindhoven|Netherlands|
Groningen|Netherlands|
Delft|Netherlands|
Leiden|Netherlands|
Brussels|Belgium|bruxelles;brussel
Antwerp|Belgium|antwerpen
Ghent|Belgium|gent
Leuven|Belgium|louvain
Liège|Belgium|liege
Vienna|Austria|wien
Graz|Austria|
Linz|Austria|
Salzburg|Austria|
Innsbruck|Austria|
Zurich|Switzerland|zürich;zuerich
Geneva|Switzerland|genève;geneve
Basel|Switzerland|basle
Bern|Switzerland|berne
Lausanne|Switzerland|
Lugano|Switzerland|
Warsaw|Poland|warszawa
Kraków|Poland|krakow;cracow
Wrocław|Poland|wroclaw
Gdańsk|Poland|gdansk
Poznań|Poland|poznan
Łódź|Poland|lodz
Katowice|Poland|
Lisbon|Portugal|lisboa
Porto|Portugal|oporto
Braga|Portugal|
Coimbra|Portugal|
Funchal|Portugal|
Dublin|Ireland|
Cork|Ireland|
Galway|Ireland|
Limerick|Ireland|
Waterford|Ireland|
Stockholm|Sweden|
Gothenburg|Sweden|göteborg;goteborg
Malmö|Sweden|malmo
Uppsala|Sweden|
Lund|Sweden|
Oslo|Norway|
Bergen|Norway|
Trondheim|Norway|
Stavanger|Norway|
Copenhagen|Denmark|københavn;kobenhavn
Aarhus|Denmark|århus
Odense|Denmark|
Aalborg|Denmark|
Helsinki|Finland|helsingfors
Espoo|Finland|
Tampere|Finland|
Turku|Finland|
Oulu|Finland|
Reykjavík|Iceland|reykjavik
Prague|Czechia|praha
Brno|Czechia|
Ostrava|Czechia|
Plzeň|Czechia|plzen;pilsen
Bratislava|Slovakia|
Košice|Slovakia|kosice
Budapest|Hungary|
Debrecen|Hungary|
Szeged|Hungary|
Bucharest|Romania|bucuresti;bucurești
Cluj-Napoca|Romania|cluj
Timișoara|Romania|timisoara
Iași|Romania|iasi
Sofia|Bulgaria|
Plovdiv|Bulgaria|
Varna|Bulgaria|
Athens|Greece|athina
Thessaloniki|Greece|salonika
Patras|Greece|
Zagreb|Croatia|
Split|Croatia|
Rijeka|Croatia|
Ljubljana|Slovenia|
Maribor|Slovenia|
Belgrade|Serbia|beograd
Novi Sad|Serbia|
Tallinn|Estonia|
Tartu|Estonia|
Riga|Latvia|
Vilnius|Lithuania|
Kaunas|Lithuania|
Kyiv|Ukraine|kiev
Lviv|Ukraine|lvov
Odesa|Ukraine|odessa
Kharkiv|Ukraine|kharkov
Dnipro|Ukraine|dnepropetrovsk
Istanbul|Turkey|constantinople
Ankara|Turkey|
İzmir|Turkey|izmir
Bursa|Turkey|
Antalya|Turkey|
Moscow|Russia|moskva
Saint Petersburg|Russia|st petersburg;leningrad
Novosibirsk|Russia|
Yekaterinburg|Russia|ekaterinburg
Kazan|Russia|
Nizhny Novgorod|Russia|
Vladivostok|Russia|
Tbilisi|Georgia|
Batumi|Georgia|
Yerevan|Armenia|
Baku|Azerbaijan|
Dubai|United Arab Emirates|dubayy
Abu Dhabi|United Arab Emirates|
Sharjah|United Arab Emirates|
Ajman|United Arab Emirates|
Ras Al Khaimah|United Arab Emirates|
Riyadh|Saudi Arabia|
Jeddah|Saudi Arabia|jidda
Dammam|Saudi Arabia|
Khobar|Saudi Arabia|al khobar
Mecca|Saudi Arabia|makkah
Medina|Saudi Arabia|madinah
Doha|Qatar|
Manama|Bahrain|
Kuwait City|Kuwait|
Muscat|Oman|
Salalah|Oman|
Tel Aviv|Israel|tel aviv yafo
Jerusalem|Israel|
Haifa|Israel|
Beersheba|Israel|beer sheva
Amman|Jordan|
Irbid|Jordan|
Beirut|Lebanon|
Cairo|Egypt|
Alexandria|Egypt|
Giza|Egypt|
Casablanca|Morocco|
Rabat|Morocco|
Marrakesh|Morocco|marrakech
Tangier|Morocco|tanger
Tunis|Tunisia|
Sfax|Tunisia|
Sousse|Tunisia|
Algiers|Algeria|alger
Oran|Algeria|
Johannesburg|South Africa|joburg;jo burg;jozi
Cape Town|South Africa|capetown
Pretoria|South Africa|
Durban|South Africa|
Gqeberha|South Africa|port elizabeth
Bloemfontein|South Africa|
Stellenbosch|South Africa|
Lagos|Nigeria|
Abuja|Nigeria|
Ibadan|Nigeria|
Port Harcourt|Nigeria|
Kano|Nigeria|
Nairobi|Kenya|
Mombasa|Kenya|
Kisumu|Kenya|
Accra|Ghana|
Kumasi|Ghana|
Addis Ababa|Ethiopia|addis abeba
Dar es Salaam|Tanzania|
Arusha|Tanzania|
Dodoma|Tanzania|
Kampala|Uganda|
Entebbe|Uganda|
Kigali|Rwanda|
Dakar|Senegal|
Port Louis|Mauritius|
Ebene|Mauritius|ébène
Sydney|Australia|
Melbourne|Australia|
Brisbane|Australia|
Perth|Australia|
Adelaide|Australia|
Canberra|Australia|
Gold Coast|Australia|
Newcastle|Australia|
Hobart|Australia|
Darwin|Australia|
Wollongong|Australia|
Geelong|Australia|
Auckland|New Zealand|
Wellington|New Zealand|
Christchurch|New Zealand|
Hamilton|New Zealand|
Dunedin|New Zealand|
Tauranga|New Zealand|
Queenstown|New Zealand|
Singapore|Singapore|singapore city
Kuala Lumpur|Malaysia|kl
George Town|Malaysia|georgetown;penang
Johor Bahru|Malaysia|jb;johor baru
Cyberjaya|Malaysia|
Petaling Jaya|Malaysia|pj
Shah Alam|Malaysia|
Kuching|Malaysia|
Kota Kinabalu|Malaysia|
Jakarta|Indonesia|djakarta
Bandung|Indonesia|
Surabaya|Indonesia|
Medan|Indonesia|
Yogyakarta|Indonesia|jogjakarta;jogja
Denpasar|Indonesia|
Semarang|Indonesia|
Makassar|Indonesia|
Batam|Indonesia|
Bangkok|Thailand|krung thep
Chiang Mai|Thailand|
Phuket|Thailand|
Pattaya|Thailand|
Hanoi|Vietnam|ha noi
Ho Chi Minh City|Vietnam|saigon;hcmc;ho chi minh
Da Nang|Vietnam|danang
Hai Phong|Vietnam|haiphong
Can Tho|Vietnam|
Manila|Philippines|metro manila
Makati|Philippines|
Taguig|Philippines|bonifacio global city;bgc
Quezon City|Philippines|qc
Cebu City|Philippines|cebu
Davao City|Philippines|davao
Pasig|Philippines|
Tokyo|Japan|tokio
Osaka|Japan|
Kyoto|Japan|
Yokohama|Japan|
Nagoya|Japan|
Fukuoka|Japan|
Sapporo|Japan|
Kobe|Japan|
Sendai|Japan|
Hiroshima|Japan|
Seoul|South Korea|
Busan|South Korea|pusan
Incheon|South Korea|inchon
Daejeon|South Korea|
Daegu|South Korea|taegu
Suwon|South Korea|
Seongnam|South Korea|pangyo
Beijing|China|peking
Shanghai|China|
Shenzhen|China|
Guangzhou|China|canton
Hangzhou|China|
Chengdu|China|
Wuhan|China|
Nanjing|China|nanking
Suzhou|China|
Tianjin|China|tientsin
Chongqing|China|chungking
Xi'an|China|xian
Xiamen|China|amoy
Qingdao|China|tsingtao
Dalian|China|
Taipei|Taiwan|taipei city
New Taipei|Taiwan|new taipei city
Hsinchu|Taiwan|
Taichung|Taiwan|
Kaohsiung|Taiwan|
Tainan|Taiwan|
Hong Kong|Hong Kong|
Karachi|Pakistan|
Lahore|Pakistan|
Islamabad|Pakistan|
Rawalpindi|Pakistan|
Faisalabad|Pakistan|
Peshawar|Pakistan|
Dhaka|Bangladesh|dacca
Chattogram|Bangladesh|chittagong
Sylhet|Bangladesh|
Khulna|Bangladesh|
Colombo|Sri Lanka|
Kandy|Sri Lanka|
Galle|Sri Lanka|
Kathmandu|Nepal|katmandu
Pokhara|Nepal|
Lalitpur|Nepal|patan
Almaty|Kazakhstan|alma ata
Astana|Kazakhstan|nur sultan;nur-sultan
Shymkent|Kazakhstan|
Tashkent|Uzbekistan|
Samarkand|Uzbekistan|
Phnom Penh|Cambodia|
Siem Reap|Cambodia|
Yangon|Myanmar|rangoon
Mandalay|Myanmar|
Naypyidaw|Myanmar|nay pyi taw
São Paulo|Brazil|sao paulo
Rio de Janeiro|Brazil|rio
Brasília|Brazil|brasilia
Belo Horizonte|Brazil|bh
Curitiba|Brazil|
Porto Alegre|Brazil|
Recife|Brazil|
Fortaleza|Brazil|
Salvador|Brazil|
Florianópolis|Brazil|florianopolis
Campinas|Brazil|
São José dos Campos|Brazil|sao jose dos campos
Manaus|Brazil|
Mexico City|Mexico|ciudad de mexico;cdmx;mexico df
Guadalajara|Mexico|
Monterrey|Mexico|
Puebla|Mexico|
Querétaro|Mexico|queretaro
Tijuana|Mexico|
Mérida|Mexico|merida
León|Mexico|leon
Cancún|Mexico|cancun
Buenos Aires|Argentina|capital federal;caba
Córdoba|Argentina|cordoba
Rosario|Argentina|
Mendoza|Argentina|
La Plata|Argentina|
Santiago|Chile|santiago de chile
Valparaíso|Chile|valparaiso
Concepción|Chile|concepcion
Antofagasta|Chile|
Bogotá|Colombia|bogota
Medellín|Colombia|medellin
Cali|Colombia|
Barranquilla|Colombia|
Cartagena|Colombia|
Lima|Peru|
Arequipa|Peru|
Trujillo|Peru|
Cusco|Peru|cuzco
Montevideo|Uruguay|
Punta del Este|Uruguay|
Quito|Ecuador|
Guayaquil|Ecuador|
Cuenca|Ecuador|
San José|Costa Rica|san jose
Heredia|Costa Rica|
Alajuela|Costa Rica|
Panama City|Panama|ciudad de panama
Santo Domingo|Dominican Republic|
Santiago de los Caballeros|Dominican Republic|
Kingston|Jamaica|
Montego Bay|Jamaica|
Port of Spain|Trinidad and Tobago|
San Fernando|Trinidad and Tobago|
Suva|Fiji|
Nadi|Fiji|
Port Moresby|Papua New Guinea|
Lae|Papua New Guinea|
"""


def _norm(text):
    text=unicodedata.normalize('NFKD',text.casefold())
    text=''.join(c for c in text if not unicodedata.combining(c))
    text=text.translate(str.maketrans({'ł':'l','ø':'o','đ':'d','ð':'d','þ':'th','æ':'ae','œ':'oe'}))
    text=re.sub(r"[.'’]",'',text)
    return ' '.join(re.findall(r'[^\W_]+',text))


_COUNTRY_INDEX={}
for _country,_info in COUNTRIES.items():
    for _name in [_country,_info['iso2']]+_info['aliases']:
        _COUNTRY_INDEX[_norm(_name)]=_country

_CITIES={}
_CITY_INDEX={}
for _row in _CITY_DATA.strip().splitlines():
    _city,_country,_aliases=_row.split('|')
    _label=f'{_city}, {_country}'
    _terms=[_city]+[a for a in _aliases.split(';') if a]
    _CITIES[_label]=_terms
    for _term in _terms:
        _labels=_CITY_INDEX.setdefault(_norm(_term),[])
        if _label not in _labels:_labels.append(_label)


def _split_country(text):
    words=list(re.finditer(r'[^\W_]+',text))
    for word in words:
        country=_COUNTRY_INDEX.get(_norm(text[word.start():]))
        if country:
            return text[:word.start()].strip(' ,;|/():-'),country
    for word in reversed(words):
        country=_COUNTRY_INDEX.get(_norm(text[:word.end()]))
        if country:
            return text[word.end():].strip(' ,;|/():-'),country
    return text,None


def resolve(text):
    if not isinstance(text,str) or not _norm(text):return None
    name=_norm(text)
    if name in _COUNTRY_INDEX:return _COUNTRY_INDEX[name]
    if name in _CITY_INDEX:return _CITY_INDEX[name][0]
    city,country=_split_country(text.strip())
    words=_norm(city).split()
    for end in range(len(words),0,-1):
        labels=_CITY_INDEX.get(' '.join(words[:end]),[])
        for label in labels:
            if country is None or label.rsplit(', ',1)[1]==country:return label
    if country and city:return f'{city.title()}, {country}'
    return None


def country_of(label):
    resolved=resolve(label)
    return resolved.rsplit(', ',1)[-1] if resolved else None


def _terms(names):
    return list(dict.fromkeys(name.lower() for name in names if len(_norm(name))!=2))


def match_terms(label):
    resolved=resolve(label)
    if not resolved:return []
    if resolved in COUNTRIES:return country_terms(resolved)
    return _terms(_CITIES.get(resolved,[resolved.rsplit(', ',1)[0]])) or [resolved.lower()]


def country_terms(country):
    canonical=_COUNTRY_INDEX.get(_norm(country))
    if not canonical:return []
    return _terms([canonical]+COUNTRIES[canonical]['aliases'])


def country_info(country):
    canonical=_COUNTRY_INDEX.get(_norm(country))
    return COUNTRIES.get(canonical)


def countries():
    return sorted(COUNTRIES)
