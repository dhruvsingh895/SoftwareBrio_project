# Live run report

The final pipeline rendered all three requested companies using async headless Playwright Chromium and
extracted their records through live NVIDIA calls. **All records pass the Pydantic contract, two-sentence
overview validation, entity-evidence checks and per-domain token reconciliation.** Only NVIDIA's free hosted
prototyping tier was used for inference; no paid provider was called.

- Started: 2026-09-13T18:08:34.690206+00:00
- Finished: 2026-09-13T18:10:53.984345+00:00
- Python: 3.14.2 on Windows
- Browser: Playwright 1.62.0, bundled Chromium 151.0.7922.34
- Command: `python main.py --provider nvidia --free-tier-only --domains postman.com supabase.com vapi.ai --output-dir output`
- Model: `nvidia/nemotron-3-super-120b-a12b`
- Tests: **67 passed**, no failures or skips; `verification/tests.xml`.
- Build: version 1.1.1 wheel built, installed, and console command verified from outside the source directory.
- Dependency consistency: `pip check` passed.

| Domain | Status | Pages | Input tokens | Output tokens | Cost USD | Confidence |
|---|---|---:|---:|---:|---:|---:|
| postman.com | completed | 6 | 2760 | 357 | 0.000000 | 0.90 |
| supabase.com | completed | 6 | 2322 | 239 | 0.000000 | 0.70 |
| vapi.ai | completed | 4 | 2678 | 142 | 0.000000 | 0.60 |

Total estimated LLM cost: $0.000000


Postman has three founders, their published titles, three associated LinkedIn URLs and four public contact emails.
Supabase has five public email contacts and a named general counsel supported by its Contact Us page.
Vapi has a recruiting email; its collected pages did not establish leadership names/roles.
Supabase's optional profile lookup encountered a search-provider bot challenge and remained null.
The exact search status, query, page evidence and excluded testimonial/investor sections are saved under
`output/evidence/`. Missing values preserve these evidence limitations.

Real HTTP 404s, a navigation timeout/retry, networkidle-to-DOMContentLoaded fallbacks and page JavaScript
errors were handled without cancelling sibling domains. Details are in the logs and individual records.

## Optional agentic run

An additional Postman run with `--agentic --agent-steps 4` completed. It made 4 navigation
model calls plus extraction, retaining the crawler guards. Actual selected tools/results are in
`output-agentic/evidence/postman_com/crawl.json` under `navigation_steps`.

| Domain | Status | Pages | Input tokens | Output tokens | Cost USD | Confidence |
|---|---|---:|---:|---:|---:|---:|
| postman.com | completed | 6 | 8901 | 532 | 0.000000 | 0.90 |

Total estimated LLM cost: $0.000000


Across these final saved runs: 16661 input tokens,
1270 output tokens and $0 estimated API cost.
Usage counters come from actual NVIDIA responses. Earlier audit runs and compatibility probes were separate
free-tier verification calls and are not included in these final-run totals.

The $0 estimate follows [NVIDIA's published free Developer Program prototyping access](https://docs.api.nvidia.com/nim/docs/product),
not production hosting prices or unlimited quotas. The free-tier guard rejects paid-provider/nonzero-rate settings.
The key was held in process memory; that process has been closed. No key is included in source, logs or the archive.

## Artifact verification

Run `python verify_outputs.py` to recheck both saved runs without any API or browser calls. This checks
the schema, summaries, clean context, page limits, entity/profile evidence and token totals.
Machine-readable results: `verification/artifact-checks.json` and `verification/build-checks.json`.
These checks establish observed behavior, not a guarantee that changing websites will always publish every fact.
Search success is covered by fixtures; the live search was blocked.

## Resulting JSON records

```json
[
  {
    "company_overview": "Postman is an API platform for building and using APIs, simplifying each step of the API lifecycle and streamlining collaboration. The company was founded by Abhinav Asthana, Ankit Sobti, and Abhijit Kane, who still lead the company today.",
    "target_audience": "Developers and enterprises building, testing, managing, and distributing APIs and services.",
    "contact_points": [
      {
        "type": "general",
        "email": "info@postman.com"
      },
      {
        "type": "general",
        "email": "info-jp@postman.com"
      },
      {
        "type": "support",
        "email": "help@postman.com"
      },
      {
        "type": "recruiting",
        "email": "accommodations@postman.com"
      }
    ],
    "leadership": [
      {
        "name": "Abhinav Asthana",
        "role": "CEO/Co-Founder",
        "linkedin_url": "https://www.linkedin.com/in/abhinavasthana",
        "source": "site"
      },
      {
        "name": "Ankit Sobti",
        "role": "CTO/Co-Founder",
        "linkedin_url": "https://www.linkedin.com/in/ankit-sobti",
        "source": "site"
      },
      {
        "name": "Abhijit Kane",
        "role": "Product Architect/Co-Founder",
        "linkedin_url": "https://www.linkedin.com/in/abhijitkane",
        "source": "site"
      }
    ],
    "confidence_score": 0.9,
    "domain": "postman.com",
    "pages_crawled": [
      "https://www.postman.com/",
      "https://www.postman.com/company/about-postman",
      "https://www.postman.com/company/press-media",
      "https://www.postman.com/company/contact-sales",
      "https://www.postman.com/company/careers",
      "https://www.postman.com/company/contact-us"
    ],
    "crawl_errors": [
      "https://postman.com/: networkidle timeout; used domcontentloaded fallback",
      "https://www.postman.com/company/about-postman: networkidle timeout; used domcontentloaded fallback",
      "https://www.postman.com/company/press-media: networkidle timeout; used domcontentloaded fallback",
      "https://www.postman.com/company/contact-sales: networkidle timeout; used domcontentloaded fallback",
      "https://www.postman.com/company/careers: networkidle timeout; used domcontentloaded fallback",
      "https://www.postman.com/company/contact-us: networkidle timeout; used domcontentloaded fallback",
      "https://www.postman.com/about: networkidle timeout; used domcontentloaded fallback",
      "https://www.postman.com/about-us: networkidle timeout; used domcontentloaded fallback"
    ],
    "token_usage": {
      "input_tokens": 2760,
      "output_tokens": 357
    },
    "estimated_cost_usd": 0.0
  },
  {
    "company_overview": "Supabase is an open-source development platform that provides a Postgres database with authentication, data APIs, edge functions, realtime data, storage, and vector embeddings. It enables developers to build applications quickly and scale to millions of users.",
    "target_audience": "Developers and engineering teams building web and mobile applications who need scalable backend infrastructure.",
    "contact_points": [
      {
        "type": "privacy",
        "email": "privacy@supabase.com"
      },
      {
        "type": "abuse",
        "email": "abuse@supabase.com"
      },
      {
        "type": "security",
        "email": "security@supabase.com"
      },
      {
        "type": "events",
        "email": "help-events@supabase.com"
      },
      {
        "type": "legal",
        "email": "legal@supabase.com"
      }
    ],
    "leadership": [
      {
        "name": "Tracy Lane",
        "role": "General Counsel of Supabase, Inc.",
        "linkedin_url": null,
        "source": "site"
      }
    ],
    "confidence_score": 0.7,
    "domain": "supabase.com",
    "pages_crawled": [
      "https://supabase.com/",
      "https://supabase.com/company",
      "https://supabase.com/careers",
      "https://supabase.com/contact/sales",
      "https://supabase.com/contact-us",
      "https://supabase.com/support"
    ],
    "crawl_errors": [
      "LinkedIn search: search provider unavailable or bot-blocked",
      "https://supabase.com/contact/sales: navigation timeout on attempt 1",
      "https://supabase.com/about: HTTP error 404; skipped",
      "https://supabase.com/about-us: HTTP error 404; skipped"
    ],
    "token_usage": {
      "input_tokens": 2322,
      "output_tokens": 239
    },
    "estimated_cost_usd": 0.0
  },
  {
    "company_overview": "Vapi is a platform for building advanced voice AI agents, offering unified orchestration, real-time monitoring, and enterprise-grade configurability. It enables developers to build, test, and deploy voice agents quickly while providing infrastructure, integrations, and scalability for enterprise use cases.",
    "target_audience": "Developers and enterprises seeking to build and scale voice AI agents with reliability, security, and compliance features.",
    "contact_points": [
      {
        "type": "recruiting",
        "email": "talent@vapi.ai"
      }
    ],
    "leadership": [],
    "confidence_score": 0.6,
    "domain": "vapi.ai",
    "pages_crawled": [
      "https://vapi.ai/",
      "https://vapi.ai/sales",
      "https://vapi.ai/pricing",
      "https://vapi.ai/careers"
    ],
    "crawl_errors": [
      "https://vapi.ai/: page JavaScript error: propensity is not defined",
      "https://vapi.ai/: page JavaScript error: Minified React error #418; visit https://react.dev/errors/418?args[]=HTML&args[]= for the full message or use the non-minified dev environment for full errors and additional helpfu",
      "https://vapi.ai/sales: page JavaScript error: propensity is not defined",
      "https://vapi.ai/pricing: page JavaScript error: propensity is not defined",
      "https://vapi.ai/careers: page JavaScript error: propensity is not defined",
      "https://vapi.ai/about: HTTP error 404; skipped",
      "https://vapi.ai/about-us: HTTP error 404; skipped",
      "https://vapi.ai/company: HTTP error 404; skipped",
      "https://vapi.ai/team: HTTP error 404; skipped"
    ],
    "token_usage": {
      "input_tokens": 2678,
      "output_tokens": 142
    },
    "estimated_cost_usd": 0.0
  }
]
```
