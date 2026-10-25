# Optional public-web research prompt

Use this with any web-enabled assistant. It is a manual research aid, not a source integration or a scheduled search. It grants no access to restricted sites.

> Search public web indexes and public employer career pages for these role titles, places and work preferences: [paste current target roles and cities]. Apply no salary filter. For remote roles, check whether the stated country and timezone restrictions allow applications from the target country. Mark unclear eligibility as unknown.
>
> Include publicly indexed LinkedIn and Naukri vacancy URLs as leads. Do not log into, scrape or automate those portals, or bypass access restrictions. Never apply, contact anyone or create portal activity.
>
> Return only jobs with a cited source URL. Prefer a current primary employer posting where accessible. Separate complete descriptions you can lawfully read from search snippets. For snippets, say “lead: full description needed”. Do not invent jobs, companies, locations, dates, availability, qualifications or contacts. Keep missing details unknown. Do not assign a fit score from a snippet.
>
> Provide a concise table with role, employer, stated location and work arrangement, source URL, publication date if known, evidence available and missing details. For each complete listing, also provide a JSON object with title, company, location, url, description and published (an empty string when unknown), suitable for manual import into data/imports. Preserve the source's wording and distinguish publication dates from update dates.
>
> Do not change my resume or add claims to it. Do not put resume text, personal contact details, credentials or API keys into search queries.

A result can be stale. Verify the listing and description before importing or applying. Any subscription or API cost depends on the service you choose. Default discovery in Job Search Desk needs no such subscription.
