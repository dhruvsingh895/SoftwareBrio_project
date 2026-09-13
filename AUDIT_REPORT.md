# Assignment audit — 2026-09-14

**Verdict: the technical assignment requirements are implemented and pass the checks below.** The project was
corrected and rebuilt as version 1.1.1. The submitter is recording Loom separately, as requested; no video or
hosted link is claimed. This is a requirements audit, not an official rubric score or a guarantee of perfect
extraction across arbitrary websites.

| Requirement / rubric area | Status | Implementation and verification evidence |
|---|---|---|
| Domain-list input and three targets | Pass | CLI array/JSON input; postman.com, supabase.com and vapi.ai all completed in live `output/summary.json`. |
| Architecture / scraping — 30% | Pass | Async headless Playwright, separate contexts, concurrent domains, homepage-first browsing, ranked links refreshed after each page, heuristic paths, bounded page-number pagination and eight attempted URLs maximum. `crawler.py`, `urls.py`, crawl evidence and browser tests. |
| JavaScript-rendered content | Pass | Browser rendering, bounded waits and DOMContentLoaded fallback; Chromium fixtures populate content asynchronously with JavaScript. All live targets rendered successfully. |
| Preprocessing / token optimization | Pass | lxml sanitization, trafilatura text, boilerplate/code removal, testimonial/investor exclusion, DOM profile cards, paragraph deduplication and balanced budgeting. Exact clean evidence is saved in `context.txt`; no raw HTML tree is sent. |
| LLM / structured output — 25% | Pass | Strict Pydantic-derived function schema, forced extraction tool, local strict validation, exact two-sentence overview, ICP, public emails, names/roles, associated LinkedIn URLs and bounded confidence. Repair-call usage remains counted. |
| Error handling / resilience — 20% | Pass | HTTP/soft 404s, bot blockers, missing text, timeouts, API retries/Retry-After, robots/scope checks, domain exception boundaries and atomic records. A complete batch fixture puts a blocked domain between successful companies. |
| Code / documentation — 15% | Pass | Separate typed modules, pinned dependencies, setup/CLI/limitations documentation, 67 passing tests, repeatable output verification, installed wheel and console command. |
| Loom walkthrough — 10% | Submitter-owned | Excluded from this implementation task at the submitter's request. Record the completed project and live outputs separately. |
| Optional search | Implemented; live availability limited | Free DuckDuckGo HTML lookup, unique name/company matching and audit records for every outcome. Live Supabase lookup was bot-blocked; success/ambiguity/failure behavior is fixture-tested. |
| Optional agentic navigation | Pass | Bounded custom LLM tool loop with `list_links` / `fetch_page`, verified in a live Postman run. Actual tools/results and usage saved in `output-agentic/`. |
| Optional token/cost tracking | Pass | Actual provider usage, per-domain ledger and combined tables, including navigation and repairs. Final runs use only NVIDIA free-tier inference; $0 estimated API cost. |

## Defects corrected

1. Flat LinkedIn signal lists lost person/profile associations. Small DOM profile cards now retain subject
   headings and URLs; mismatched profiles are rejected. Postman's three published founder profiles are present.
2. Repeated tail truncation discarded useful later-page evidence. Complete signal headers are retained, with
   remaining body space distributed across pages before provider budget checks.
3. Discovery used one initial queue and rejected every query. Candidates now refresh after each fetch, preserve
   stronger anchor descriptions, prefer default-language pages, and permit bounded `page=1..20` pagination.
4. A sales testimonial author was misclassified as leadership after text extraction lost the external employer.
   Attributed quotations and explicit investor/testimonial containers are filtered before extraction; removed
   sections stay in the audit files. A regression test covers this observed failure.
5. Search recorded only successes and could accept the first of multiple plausible profiles. Every attempt now
   records status/candidates; multiple matching profiles remain null. Search challenges and soft 404s are detected.
6. API backoff ignored Retry-After. Seconds/date headers are now honored; requested waits over 60 seconds fail
   that domain rather than causing an early retry or an unbounded delay.
7. Packaging lacked an installed command. `python main.py`, `python -m company_intel` and installed
   `company-intel` now work. The version 1.1.1 wheel was built and installed successfully.

## Final checks and practical limits

- Submission update: root `output.json` contains the three unchanged records from the 2026-09-13 live run.
  Future runs write the combined array to `<output-dir>/output.json`; this export is regression-tested.

- **67 tests passed**, including real Chromium and a complete mixed-success batch through rendering,
  the NVIDIA adapter, extraction and artifact writing.
- All three live target records and the agentic record pass `python verify_outputs.py`.
- The wheel's application files match the reviewed source; `pip check` found no broken requirements.
- Postman has source-associated founder profiles. Supabase's general counsel has no verified LinkedIn match;
  Vapi's leadership remains empty because the collected pages did not support it. These are evidence limitations.
- Python 3.14.2/Windows was exercised; Python 3.11+ is the declared target. Other OS/Python versions were not run here.
- Confidence measures evidence coverage, not calibrated truth. DOM/sentence heuristics have limits; websites and
  search providers can change or block access. Operational limitations are documented in the README.

For submission, use the source ZIP, `RUN_REPORT.md`, the three JSON records, and your own walkthrough recording.
