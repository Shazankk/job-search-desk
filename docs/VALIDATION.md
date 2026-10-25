# Validation scope

## Automated checks

Run the offline suite from the project folder:

```sh
.venv/bin/python -m pytest tests -q
```

The suite contains approximately 2,960 tests, including parameterised place-resolution cases. It covers:

- Country and city names, aliases, capitals, ambiguous places and unknown towns with a country.
- Resume-derived career profiles, work arrangements and country-aware discovery plans.
- Scoring evidence, experience and sector deductions, location caps and skills gaps.
- Source parsing, caching, request budgets, access blocks and failure isolation.
- Alert parsing, lead completion, manual descriptions and duplicate handling.
- Factual DOCX paragraph preservation, provenance and dated document folders.
- Settings persistence, credential handling, digest logic, run locking and schedule configuration.

Tests use synthetic fixtures and mocked transports. `tests/conftest.py` blocks real network requests. Passing tests do not establish live service access, coverage or employment eligibility. GitHub Actions runs the suite on macOS with Python 3.12.

## Checks that need a live environment

- **LinkedIn:** opt-in search, description retrieval, saved-lead completion and current access restrictions. Its terms prohibit scraping; access can stop.
- **Naukri:** current terms and robots.txt, sitemap availability and usable leads for selected places in India. Full descriptions still need pasting.
- **Himalayas:** current API responses, availability checks and country/timezone eligibility metadata.
- **Adzuna:** a valid account/key, supported city queries, quotas and current coverage. Full descriptions still need pasting.
- **Mail:** real alert formats, read-only IMAP authentication and folder access; SMTP authentication and digest delivery to the configured address.
- **macOS:** fresh setup, Keychain access prompts, launchd installation, scheduled execution and sleep/wake behaviour.
- **Other systems:** Linux and Windows installation and execution. Both are untested; the runner's Unix-only `fcntl` import is a known Windows compatibility limit.
- **Optional paragraph ordering:** API model access, consent, billing and fallback behaviour with real credentials.

Record live checks without private resumes, credentials, mailbox contents or contact data. Verify listing availability and requirements before applying. No test result promises jobs, interviews, exhaustive listing coverage or ATS ranking.
