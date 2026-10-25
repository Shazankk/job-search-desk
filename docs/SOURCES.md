# Job sources and their limits

Discovery follows your resume's roles, chosen places and work arrangements. Worldwide place support does not mean every source covers every place. **Discovery sources** shows the query plan and source controls. No salary filter is applied.

Default sources need no account or key. LinkedIn is off by default; Adzuna, mail access and employer watchlists need separate setup. Source failures are reported separately from empty results. See [VALIDATION.md](VALIDATION.md) for the difference between offline coverage and live checks.

## Places and remote eligibility

An offline list recognises about 97 countries and 630 cities, with common aliases and case-insensitive input. Unknown towns need a country. Choose On-site, Hybrid and/or Remote. Remote queries use your country, rather than a fixed country for every search.

Country, timezone and description checks help filter remote listings. A matching location does not prove work authorisation or employer eligibility. Confirm those details yourself.

## LinkedIn public search: optional and off by default

Enable it explicitly in **Discovery sources**. It reads unauthenticated guest search pages and a bounded number of descriptions. It uses resume-derived role queries, places and work arrangements. It needs no account, login cookies or API key.

Default limits are 5 searches and up to 15 descriptions per run, 50 uncached requests per day, a 24-hour cache and at least 3 seconds between uncached requests. These are request budgets, not listing counts. Queries read a limited batch, not every matching vacancy. Unused description budget can complete saved LinkedIn leads, including links from alert emails. A listing returning 404 is marked closed.

This is unofficial. LinkedIn's published terms prohibit scraping. Public availability does not grant permission or guarantee continued access. The collector stops on access blocks or challenges and pauses for 24 hours. It does not log in, solve CAPTCHAs, use proxies or bypass blocks. Leads may still require a full description pasted manually.

The guest-search workflow is adapted from the MIT-licensed ai-job-search-india project. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

Reference: [LinkedIn's prohibition of scraping](https://www.linkedin.com/help/linkedin/answer/a1341387/prohibition-of-scraping-software?lang=en).

## Naukri: published sitemaps for places in India

The collector reads Naukri's published sitemap index and per-city job sitemaps, including shared other-city files where needed. The documented robots.txt review on 25 October 2026 found these paths allowed for generic clients. Rules can change; review them before changing or extending collection. A robots.txt allowance does not settle every question about terms of use.

Listing addresses supply title, employer, places, experience range and a date-bearing listing ID. The app filters target titles, experience overlap and recent dates. Defaults include at most 40 leads per run, a 24-hour cache, 2-second spacing and a 24-hour pause on restricted responses. Confirm details read from listing addresses yourself.

This source does not fetch full descriptions. Naukri's interactive search requires CAPTCHA handling and its listing pages need JavaScript. Open a lead and paste the full description, then prepare saved jobs. Collection stays within the published sitemaps; it does not bypass search or page restrictions.

References: [robots.txt](https://www.naukri.com/robots.txt), [sitemap index](https://www.naukri.com/sitemap/sitemap.xml), [terms](https://www.naukri.com/termsconditions).

## Himalayas: free remote jobs

The public API needs no account or key. Role-derived queries use your country, followed by local checks of country, timezone and description restrictions. It runs when Remote is selected. It does not provide local office-job coverage.

The adapter keeps source attribution and the original application link. Queries have bounded pages and a 24-hour cache. Before preparing a retained listing, a cached single-job availability check runs. Expired listings and their prepared documents are removed.

Public rate limits and metadata errors can affect results. Explicit eligibility conflicts are flagged for review. Source metadata is not independent proof that an employer accepts your application.

References: [API](https://himalayas.app/api), [terms](https://himalayas.app/terms).

## Adzuna: optional city search in 19 countries

The adapter uses role queries, selected cities and a configured radius in 19 supported countries. Country-level place recognition does not imply Adzuna support; only supported city/country combinations produce queries.

You need an app ID and API key. A free evaluation key is available; check current account terms and quotas. Use the masked dashboard fields for macOS Keychain or set `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` as environment variables. Missing access is reported as an error, not zero jobs.

Descriptions can be excerpts, so results remain leads until you paste a full description. Queries use bounded pages and a daily cache. No salary restriction is sent. Any displayed source contribution measures observed additional relevant leads, not a share of all vacancies or hiring odds.

References: [API overview](https://developer.adzuna.com/overview), [API schema](https://developer.adzuna.com/swagger/spec/test2.json), [terms](https://developer.adzuna.com/docs/terms_of_service).

## Your own job-alert emails

You can upload saved `.eml` files or enable read-only IMAP for a chosen folder. Alerts may come from any portal. Parsing depends on the message format; some need manual import or missing details filled in. Create portal alerts yourself and check their filters. The app does not create alerts on your behalf.

The leads inbox keeps incomplete postings separate from full-job scores. Open a listing, confirm title, employer and location, paste its description and use **Prepare saved jobs**. A later snippet does not replace an already completed description.

Sender labels and email links do not verify identity. Unsupported trackers or layouts may not parse. IMAP does not support every OAuth-only or administrator-restricted mailbox. Store `IMAP_PASSWORD` in Keychain or an environment variable.

## Employer watchlists and manual import

Public adapters support Greenhouse, Lever (global/EU), Ashby and employer RSS/Atom feeds. Supply known board or feed identifiers in advanced settings. Watchlists cover those employers only; they are not a city-wide or worldwide search service.

Example watchlist settings:

```json
[
  {"type":"greenhouse","board":"actual-token","company":"Employer","enabled":true},
  {"type":"lever","board":"actual-token","company":"Employer","region":"eu","enabled":true},
  {"type":"ashby","board":"actual-token","company":"Employer","enabled":true}
]
```

Use manual import for other permitted listings, with a source URL and full description. Keep unknown details unknown. Source update times are not treated as original publication dates. One failed watchlist response does not close all missing jobs.

References: [Greenhouse](https://docs.greenhouse.io/job-board.html), [Lever](https://github.com/lever/postings-api), [Ashby](https://developers.ashbyhq.com/docs/public-job-posting-api).

## Shared boundaries

Reposts and cross-source copies are hidden using approximate duplicate detection. Source text and contact details still need human review. No application, connection request or employer message is sent.

Optional OpenAI or Claude API paragraph ordering provides no extra job-source access. It only orders existing resume paragraphs, requires consent to share them with job text, and falls back to local ordering.

For manual public-web research, see [PUBLIC_RESEARCH_PROMPT.md](PUBLIC_RESEARCH_PROMPT.md). It supplies a prompt, not an additional integration or a promise of source access.
