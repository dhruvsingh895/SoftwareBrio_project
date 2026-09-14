# Final assignment audit — 2026-09-14

**Verdict: the requested project implementation and submission deliverables are complete and pass the checks below.**
Eligibility is recorded from the candidate's explicit confirmation. This audit verifies the assignment
and the observed runs; it does not assign an employer's rubric score or promise complete data from every website.

## Requirement-by-requirement result

| Requirement | Result | Evidence |
| --- | --- | --- |
| Entry-level eligibility | Confirmed by candidate | User confirmed eligibility and the 2026 B.Tech Artificial Intelligence and Machine Learning batch. Recorded in `submission-email.md`. |
| 40% manual operations screening answer | Complete | User's explicit **Yes** appears beside the full screening question in `submission-email.md`. |
| Python pipeline taking a list of domains | Pass | `domains.json`, CLI `--domains` and `--domains-file`; the exact three required targets were run again for the screen recording. |
| Homepage and relevant subpage discovery | Pass | `crawler.py` / `urls.py`: homepage first, refreshed ranked links, heuristic about/team/company/contact/pricing paths and bounded pagination. |
| JavaScript-rendered content | Pass | Headless Playwright Chromium; live site rendering and real-browser JavaScript fixtures in the 67-test suite. |
| Clean context instead of raw HTML trees | Pass | `cleaner.py`: lxml/trafilatura cleaning, script/style/SVG/navigation removal, text deduplication, contact/profile evidence and bounded context. Captured `context.txt` files validate. |
| Strict LLM extraction | Pass | Pydantic-derived forced function schema, local strict validation and evidence checks in `schema.py` / `extractor.py`. |
| Exactly two-sentence company overview | Pass | Extraction validation and saved-output verification for all three recorded companies. |
| Target audience / ICP | Pass | Required `target_audience` field populated in the recorded outputs. |
| Public email contacts | Pass | Literal site-supported contacts in `contact_points`; unsupported values are removed. |
| Leadership names, roles and discoverable LinkedIn URLs | Pass | Required leadership schema, nearby name/role evidence and DOM profile associations. Postman has three supported founder profiles. Missing information remains empty/null. |
| Confidence between 0.0 and 1.0 | Pass | Pydantic bounds, finite values and evidence-completeness ceiling. |
| 404s, bot blockers, timeouts and missing elements | Pass | Per-page error handling, bounded retries/fallback waits and recorded live errors; browser fixtures exercise missing/blocked pages. |
| One failed company must not stop the batch | Pass | Per-domain exception boundaries and artifact persistence; mixed-success full-batch fixture and the real earlier HTTP-500 attempt in `output/video-demo/`. |
| GitHub repository with modular code | Complete | [Repository](https://github.com/dhruvsingh895/SoftwareBrio_project), package modules, tests and documentation. |
| Dependency file | Complete | Pinned `requirements.txt`, `requirements-dev.txt` and installable `pyproject.toml`. |
| README for environment variables and local execution | Complete | `.env.example`, setup commands, required API variable, browser installation, CLI examples and practical limits. The real `.env` is Git-ignored. |
| Sample output for the three domains | Complete | Root `output.json` matches the original verified three-company run; the new recording's output is `output/screen-demo-final/output.json`. |
| 2–3 minute screen recording | Complete | `demo/company-intel-screen-recording.mp4`: 167.52 seconds, 1920×1080, real browser screen capture of project files, Python CLI execution and resulting JSON; synthetic narration and captions. Only the idle wait is removed. |

## Optional features

| Feature | Result | Evidence / limit |
| --- | --- | --- |
| Search for missing LinkedIn URLs | Implemented | DuckDuckGo HTML lookup with name/company matching, ambiguity checks and audit logs. Live search may be blocked; it does not bypass challenges. Success/failure/ambiguity behavior is fixture-tested. |
| Dynamic agent navigation | Implemented and verified | Custom bounded `list_links` / `fetch_page` loop; saved live run in `output-agentic/`. The main recording uses deterministic discovery. |
| Token and cost tracking | Pass | Actual response usage, including repair/navigation calls, with per-domain and aggregate estimates. The recorded run used NVIDIA free-tier-only mode with $0 configured rates. |

## Final verification

- **67 tests passed**, with no failures, errors or skips. Fresh report: `verification/tests-latest.xml`.
- `pip check` passed with no broken requirements.
- Original three-company output, optional agentic output and previous demo output all revalidated.
- Fresh recorded batch and saved-output verifier both exited with code **0**.
- New run's schema, two-sentence overview, literal entity evidence, profile associations, page caps and token totals pass: `verification/screen-output-checks.json`.
- MP4 fully decodes with H.264/AAC, has 37 caption cues and passes audio-level/duration checks: `demo/screen-recording-checks.json`.
- Source/output files were visually inspected in the final encoded video. The demo workspace prevents `.env` access and checks its viewport before starting a run.
- The original v1.1.1 application code and previously built wheel are unchanged by this final audit. New code is confined to optional recording tools.

### Run shown in the submitted screen recording

| Domain | Status | Pages | Input tokens | Output tokens | Confidence |
| --- | --- | ---: | ---: | ---: | ---: |
| postman.com | completed | 6 | 2760 | 365 | 0.90 |
| supabase.com | completed | 6 | 2326 | 245 | 0.70 |
| vapi.ai | completed | 4 | 2684 | 144 | 0.60 |

Total: **7,770 input tokens**, **754 output tokens**, **$0 estimated API cost**.
The estimate uses configured NVIDIA free-tier rates; it is not an unlimited-quota or production-hosting claim.

## Gaps resolved in this final pass

1. Added the candidate's eligibility confirmation to the submission draft while retaining the explicit operations answer.
2. Replaced the primary submission link with an actual screen recording. The earlier rendered explanatory video remains supplementary.
3. Corrected stale audit text that said no video existed and refreshed the README's demo and latest-output links.
4. Fixed scrolling and viewport containment in the optional recording workspace, then retook the video and validated the real run again.

## Files to submit

- Repository: [SoftwareBrio_project](https://github.com/dhruvsingh895/SoftwareBrio_project)
- Sample: [`output.json`](output.json)
- Recording: [`demo/company-intel-screen-recording.mp4`](demo/company-intel-screen-recording.mp4)
- Email/form wording: [`submission-email.md`](submission-email.md), including eligibility and **Yes** to manual operations.

Public-site coverage remains evidence-limited: Vapi's collected pages did not support leadership names,
and Supabase's optional profile search was blocked. Those missing values are retained. Python 3.14.2 on
Windows was exercised; other operating systems/Python versions were not newly tested in this audit.
