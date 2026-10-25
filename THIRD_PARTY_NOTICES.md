# Third-party attribution

The public LinkedIn guest-page discovery workflow was adapted from [ashutoshgh/ai-job-search-india](https://github.com/ashutoshgh/ai-job-search-india), `.agents/skills/linkedin-search`, pinned at commit `36b4874c8658eef971bff921b41fd5b3a68f94ed`. That fork credits the upstream ai-job-search project.

Original copyright: **Copyright (c) 2026 Mads Lorentzen**. The MIT license is reproduced in `third_party/ai-job-search-LICENSE.txt`.

This project ports the endpoint/parsing approach into Python and adds a standard-library HTML parser, independent request budgets, daily caching, a stop-on-block circuit, resume-derived queries, factual DOCX/SQLite/Streamlit integration and tests. It does not execute the repository's agent instructions, use Bun, or bundle its application automation/LaTeX workflows.

Public unauthenticated availability is not official API approval. The upstream skill explicitly warns about LinkedIn's terms. No login, proxies, CAPTCHA solving or block bypass is implemented.
