# v1.4 — first public release

- Add worldwide places with offline country/city resolution and On-site, Hybrid and Remote choices; remote searches use your country.
- Recognise four more career families: healthcare, education, legal and engineering.
- Show a skills-gap panel for matching jobs in the Jobs tab.
- Make LinkedIn public search opt-in and off by default.
- Include a fictional sample resume for trying the app.
- Keep the selected tab open after saving settings or uploading a resume.
- Organise documents into dated folders using the day each job was first found.
- Restart the dashboard cleanly when its launcher is opened again.
- Publish public setup, source, validation and contribution guides, an MIT licence and an offline test workflow.
- Add a logo, browser-tab and home-screen icons, a link-preview image and a project website with a Mac download.
- Show each job's score as a points table with reasons, with skills, evidence, description and documents in tabs; brand theme for the dashboard.
- Rename the code package from `hr_agent` to `job_search_desk`; saved Keychain keys and older schedules are still recognised.

# v1.3 — Naukri leads, lead completion, honest scores, duplicates

- Read Naukri's published per-city job sitemaps (allowed for generic clients by its robots.txt) and keep senior-fit listings by title and experience range. Naukri's search API requires reCAPTCHA and its pages need JavaScript, so descriptions are pasted from the listing.
- Fetch full LinkedIn descriptions for saved leads, including links from LinkedIn alert emails, within the run budget; close leads whose listing is gone.
- Add one LinkedIn remote-India search when remote work is enabled; raise bounded defaults to 5 searches, 15 descriptions and 50 requests/day.
- Parse resume skill lists without splitting inside brackets or keeping labels; listed skills are evidence, not scoring groups (except for careers without a catalogue). Existing configs migrate once without losing edited titles.
- Score experience fit (role's stated years vs resume) and sector mismatch; thin descriptions can no longer earn full skill credit. Each deduction is explained in the brief.
- Hide reposts and cross-source copies of the same job; remove an untouched duplicate packet.
- File packets as `artifacts/<date first found>/Company - Title [id]`; older layouts are moved on the next run; contact-search links use your own city and career.
- Tests block all real network access.
- `OPEN_DASHBOARD.command` restarts cleanly: it closes any Job Search Desk dashboard already running (this or an older folder), never other apps, and moves to the next free port if another app holds 8501. Adds `STOP_DASHBOARD.command`; the old-project import closes dashboards itself.
- Saving or uploading no longer jumps back to the Jobs tab: the tab bar keeps its selection across reruns.

# v1.2 — public LinkedIn discovery

- Adapt the MIT ai-job-search-india public guest search/detail workflow into Python, with attribution/license.
- Add resume-derived LinkedIn role/city discovery and full-description packet preparation without login or paid API.
- Show enable/disable controls, request/description budgets, exact query plan and terms/reliability warning in the dashboard.
- Cache for 24 hours, enforce daily limits/spacing, stop on access blocks without retries or bypass, preserve partial leads.
- Preserve the resume/config synchronization, general-career scoring, alert inbox, Keychain credentials, optional Adzuna and AI, and migration fixes from v1.1.
- Validate real Pune HR search and factual DOCX packets; add parser, cache, block, budget and pipeline regressions.

# v1.1

- Rebuilds search identity, roles, career fields, seniority and skill settings on a resume change; refreshes the visible configuration immediately.
- Removes HR-only scoring and immediately rescores stored jobs, hiding outdated documents.
- Adds role-driven free remote-India discovery, optional Adzuna city queries, transparent query plans, source-cost/setup choices and measured source contribution.
- Makes the old four-employer watchlist optional instead of presenting its 294 raw postings as candidate matches.
- Adds a LinkedIn/Naukri-first alert workflow: native search links, email setup in the frontend, a separate leads inbox, full-description promotion and lead-aware digests.
- Adds secure dashboard credential fields and AI connection testing, usage/fallback counts and a clearly labelled documents-folder action.
- Adds saved-job preparation without discovery, alert-only checking and an old-project import helper.
- Documents unsupported integrations and source limits; retains no auto-apply, no auto-outreach and factual paragraph preservation.
