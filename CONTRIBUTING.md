# Contributing to Job Search Desk

Help is welcome with job sources, career families, places, clearer documentation and Windows/Linux support.

## Set up development

Use Python 3.11 or newer. macOS is the validated platform; Windows and Linux are untested. The runner imports Unix-only `fcntl`, which needs an alternative on Windows.

```sh
git clone https://github.com/Shazankk/job-search-desk.git
cd job-search-desk
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

The activation command above is for a Unix shell. The application package is `hr_agent/`, a historical name. Start the dashboard with:

```sh
python -m streamlit run dashboard.py --server.address 127.0.0.1
```

Use the fictional sample resume and synthetic fixtures for development. Keep private resumes, job history, credentials, logs and prepared documents out of contributions.

## Keep tests offline

Run `python -m pytest tests -q` before submitting a change. GitHub Actions runs this command on macOS with Python 3.12.

Tests must never contact real job sites, mailboxes, SMTP servers or model APIs. `tests/conftest.py` blocks real network requests. Mock transports and source fetches; use synthetic fixtures. Add meaningful regression coverage when changing behaviour. Document live checks separately without private data or secrets.

## Add sources responsibly

For each new source, document its coverage, setup, terms and robots.txt review, including the review date and relevant links. A robots.txt allowance alone does not establish permission under a site's terms.

Use documented public APIs or permitted public feeds where possible. Do not add login scraping, account-cookie collection, CAPTCHA bypass or block bypass. Respect request limits and caching. Stop on access restrictions and show failures clearly instead of reporting zero jobs.

Preserve source attribution and application links. Keep unknown dates, locations and eligibility unknown. Do not turn a snippet into a fabricated full description. Test parsing, budgets, blocked access and failure handling with offline fixtures.

## Preserve factual resumes and explainable scores

Never add invented resume content. Tailoring may only reorder existing factual paragraphs within the supported boundaries. Preserve provenance checks and local fallback ordering. Optional paragraph ordering must require consent before sharing job text or resume paragraphs.

Keep scores explainable. Show evidence, deductions, gaps and uncertainty when changing a scoring rule. Do not describe scores as hiring odds or promise jobs, interviews or ATS ranking.

## Submit a focused change

Explain the problem, the resulting behaviour and how you tested it. Note any platform or live-service checks you could not perform. Update documentation when behaviour changes.

Write commits and contribution text in your own voice. Do not add AI attribution, assistant credits or vendor authorship trailers. Preserve required third-party licence notices. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
