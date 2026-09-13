# Company intelligence pipeline

Python 3.11+ project that renders public websites in headless Chromium, extracts clean text, and produces company records through a strict Pydantic-derived tool schema. Each domain produces JSON even if crawling or extraction fails. The batch also saves a summary, cost table, log and cleaned evidence.

Supports **NVIDIA API Catalog** and Anthropic. The supplied live run uses NVIDIA's free Developer Program prototyping tier. See `RUN_REPORT.md` for results, `AUDIT_REPORT.md` for the rubric audit, and `output/summary.json` for actual usage. The submitter is recording the walkthrough separately.

## Submission sample

[`output.json`](output.json) contains the three company records from the verified live run on 2026-09-13:
`postman.com`, `supabase.com`, and `vapi.ai`. It is a JSON array extracted unchanged from the run's
`output/summary.json` records, including missing values, crawl errors and actual token usage.
[`domains.json`](domains.json) contains the input array.

Every new run also writes the combined records to `<output-dir>/output.json`, alongside the individual company
files and detailed summary. For example, the command below generates a fresh combined `output/output.json`:

```text
python main.py --provider nvidia --free-tier-only --domains-file domains.json --output-dir output
```

## Setup and free-tier run

From the project directory on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
```

Configure `NVIDIA_API_KEY` locally in `.env` or the launch environment. No actual key is bundled. Environment variables take precedence over `.env` in the current working directory; `--env-file PATH` selects another file. On Linux/macOS use `.venv/bin/python`; Linux may need `python -m playwright install --with-deps chromium`.

With the virtual environment activated:

```text
python main.py --provider nvidia --free-tier-only --domains postman.com supabase.com vapi.ai --output-dir output/
python main.py --provider nvidia --free-tier-only --domains-file domains.json --output-dir output/
python main.py --provider nvidia --free-tier-only --domains postman.com --agentic --agent-steps 4 --output-dir output-agentic/
python main.py --domains postman.com supabase.com vapi.ai --crawl-only --output-dir crawl-output/
```

`domains.json` is a JSON array such as `["postman.com", "supabase.com", "vapi.ai"]`. Both input options can be combined. Valid domains are normalized and deduplicated; malformed inputs still yield failure records with safe filenames. Inputs must be public HTTPS domains, optionally prefixed with `www.`.

Optional Anthropic support uses `ANTHROPIC_API_KEY`. `--provider auto` prefers NVIDIA when its key exists, otherwise Anthropic. **With `--free-tier-only`, automatic selection always selects NVIDIA; Anthropic and nonzero rates are rejected before any network operations.** An absent key, quota limit, unavailable model or provider failure never triggers a paid-provider fallback.

| Flag | Default | Meaning |
|---|---:|---|
| `--provider` | auto | NVIDIA or Anthropic, without runtime provider fallback |
| `--free-tier-only` | off | Restrict inference to NVIDIA hosted prototyping and zero token rates |
| `--model` | provider-specific | Nemotron 3 Super or Haiku 4.5 |
| `--concurrency` | 3 | Concurrent domains |
| `--max-pages` | 8 | Unique attempted page URLs, including failed/disallowed attempts |
| `--timeout-ms` | 15000 | Initial page/robots timeout |
| `--delay` | 1.0 | Minimum seconds between same-domain navigations |
| `--context-tokens` | 12000 | Input budget including prompt and schema |
| `--agentic` | off | Add bounded LLM navigation before deterministic fallback |
| `--agent-steps` | 4 | Maximum navigation model calls; 3–5 |
| `--no-linkedin-search` | off | Disable optional DuckDuckGo HTML profile lookup |
| `--crawl-only` | off | Collect evidence without inference |

Exit codes: `0` = all extractions complete, or usable pages for every domain in explicit crawl-only mode; `2` = incomplete/partial batch after saving artifacts; `1` = infrastructure failure; `130` = interruption. Missing keys do not prevent crawling. All-pages-failed records keep empty intelligence and confidence 0.0.

## Modules and outputs

```text
company_intel/
  __init__.py
  cli.py              # Installed command and argument validation
  __main__.py         # python -m company_intel
  retry_policy.py     # Shared HTTP Retry-After parsing
  config.py           # Limits, user agent, model defaults and editable prices
  schema.py           # CompanyIntel, CompanyFacts, Contact and TeamMember
  urls.py             # URL normalization, public-host checks and priorities
  crawler.py          # Async Playwright, robots, discovery, pacing and retries
  cleaner.py          # Sanitized DOM -> text, email/LinkedIn signals
  extractor.py        # Tool schema, evidence validation, usage and agentic loop
  nvidia.py           # Async NVIDIA wire adapter and schema/message conversion
  search_fallback.py  # Optional evidence-checked LinkedIn search
  pipeline.py         # Concurrent orchestration, failure isolation, atomic outputs
main.py
requirements.txt      # Pinned direct runtime dependencies
requirements-dev.txt  # Pinned test dependencies
requirements-lock.txt # Full tested environment, including tests
tests/
verification/
output/
  output.json          # Combined array for all domains in this run
  postman_com.json
  supabase_com.json
  vapi_ai.json
  summary.json
  summary.md
  run.log
  evidence/<domain>/
    context.txt
    crawl.json
```

The public record has exactly the requested `CompanyIntel` fields. Python owns domain, crawl metadata, usage and cost. `CompanyFacts` generates the remaining fields for the `emit_company_intel` tool. Both providers receive `strict: true`. NVIDIA receives equivalent inline definitions because its forced-tool compiler rejected the original Pydantic `$defs` references during verification.

Strict local Pydantic validation checks types, required fields, unknown fields and confidence bounds. Additional validation checks two-sentence overviews, literal email/name/role/profile evidence, duplicates and completeness-based confidence ceilings. One semantic/schema repair is allowed; its usage remains counted.

## Crawl and extraction behavior

1. Retrieve robots.txt through Playwright's API request context and parse with `urllib.robotparser`. Apex and www hostnames have separate policies. Missing robots (404/410) permits crawling; access/server errors, network failures, invalid redirects and HTML pretending to be robots fail closed. Honor crawl delay and request rate.
2. Fetch the HTTPS homepage first. Discover relevant anchors by URL/text keywords, recompute candidates after each fetched page, then add /about, /about-us, /company, /team, /leadership, /contact and /pricing. Prefer deep About/Team/Press pages and default-language pages, and reserve heuristic attempts. Follow discovered pagination with a single `page=1..20` parameter; all attempts still share the eight-page cap. Failed guesses count toward the cap.
3. Use async headless Chromium and a desktop user agent identifying CompanyIntelBot. Wait for networkidle; if a document arrived before timeout, use DOMContentLoaded on that document. A genuine navigation timeout gets one retry with twice the timeout. Check redirects before fetching. Exclude off-domain, non-HTTPS, local/private and action/unsupported-query document destinations. Disable image/media/font downloads and service workers while retaining scripts/styles for rendering.
4. Handle HTTP errors, soft 404s, visible CAPTCHA/access blocks, JS errors, empty text and parse errors per page. Challenge detection examines visible text/title rather than ordinary embedded CAPTCHA scripts. Challenges are skipped, never solved or bypassed.
5. Extract page.content(), strip scripts, styles, SVG, navigation, footer, forms and similar boilerplate with lxml, then extract text with trafilatura. Restore omitted headings to retain leadership names. Preserve small DOM profile cards to associate a heading's subject with its linked profile. Exclude attributed quotations, explicit testimonial containers, investor sections and code samples before article extraction; removed sections remain inspectable in the audit evidence. Independently recover email/mailto and LinkedIn signals, including footer contacts but excluding executable script payloads. Raw HTML is neither saved nor sent to inference.
6. Deduplicate long repeated paragraphs, prioritize valuable pages and bound the input. Budget reductions retain complete signal/profile headers and distribute remaining body space across pages, instead of repeatedly chopping off the last pages. All clean pages stay in crawl.json even when the final budget excludes some text. context.txt stores the actual final extraction evidence, or locally budgeted evidence if no extraction was attempted.
7. Record every returned generation's usage before validation, including navigation and repair calls. Transient connection/rate-limit/server failures have at most three exponential-backoff attempts. Honor Retry-After seconds/date headers up to 60 seconds; longer requested delays fail the domain rather than retrying prematurely. Authentication/access failures do not retry repeatedly. Website instructions are treated as untrusted data.

Each domain has isolated exception handling and its own usage ledger. Completed records are atomically saved immediately and included in the combined summary. One unhandled domain failure cannot cancel siblings.

## NVIDIA and free-tier accounting

Default NVIDIA model: `nvidia/nemotron-3-super-120b-a12b`. The fixed endpoint is `https://integrate.api.nvidia.com/v1/chat/completions`. The adapter uses asynchronous HTTP and named function calls for extraction; tool calls/results retain their IDs during navigation. Thinking is disabled for this model.

[NVIDIA's official FAQ](https://docs.api.nvidia.com/nim/docs/product) says Developer Program members have free hosted API access for prototyping. This development verification therefore uses editable **$0 input/output token rates**. Successful calls still record real `usage.prompt_tokens` and `usage.completion_tokens`. Zero estimated cost does not mean zero usage or a quote for production hosting. NVIDIA production licensing/infrastructure and free-tier quotas are separate.

`--free-tier-only` rejects incompatible provider/rate settings before the browser or API client starts. The code does not switch to paid inference when NVIDIA fails.

NVIDIA's hosted API has no documented token-count endpoint. The adapter conservatively budgets UTF-8 bytes of the full serialized request plus a 1,024-token template allowance. This can leave unused capacity, but avoids treating chars/4 as a measured count. The method is labeled in summary.json; usage counters always come from API responses. Token estimation does not make extra inference calls.

Anthropic's default Haiku 4.5 uses standard uncached $1/$5 per million input/output token rates, checked against [official pricing](https://platform.claude.com/docs/en/about-claude/pricing) on 2026-09-13, and its count_tokens endpoint for budgeting. Anthropic execution is prohibited by the free-tier guard. A different Anthropic model requires explicit rates; both price flags must be provided together.

```text
estimated_cost_usd = input_tokens * input_price_per_token
                   + output_tokens * output_price_per_token
```

The summary includes provider, model, pricing basis/source, input budget method, per-domain status and full records. Unknown usage hidden by network failures cannot be recovered locally. Browser expenses, taxes, production infrastructure and non-domain compatibility probes are outside the main batch's table.

## Optional navigation and LinkedIn lookup

`--agentic` exposes list_links and fetch_page. They call the same crawler, retaining robots, scope, pacing, deduplication and page limits. At most 3–5 model steps run. If the input budget is reached, deterministic discovery continues. Navigation usage is attributed to its domain, and selected tools/results are saved in `navigation_steps`.

For up to five leaders without a profile, DuckDuckGo HTML is queried with `"{name}" "{company}" site:linkedin.com/in`. Requests use Playwright, honor robots and are globally serialized. Attach a profile only when exactly one distinct candidate has both the full name and company in its snippet; normalize tracking parameters, mark source=search, and retain its snippet. Multiple matching profiles remain null. Every attempt is audited, including no-match, ambiguous, blocked, failed and skipped searches. Robots/access blocks are logged and stop further searches. No LinkedIn page is fetched, and no search API key is needed.

## Installable build

The source entry point remains `python main.py`. You can also run `python -m company_intel`.
Version 1.1.1 includes an installable wheel under `dist/`, with the `company-intel` console command:

```text
python -m pip install dist/company_intel_pipeline-1.1.1-py3-none-any.whl
company-intel --help
```

To rebuild from source: `python -m pip wheel . --no-deps --wheel-dir dist`.
Install Chromium separately as described above. The wheel contains application code; this source bundle includes tests and live evidence as well.

## Tests

```text
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pytest -q
python -m pip check
```

Tests cover DOM cleaning and heading retention; regex signals; token budgeting; tool schemas; evidence checks; validation-retry accounting; robots and redirect guards; URL scope; timeout fallback/retry; page caps; missing-key/all-pages-failed artifacts; batch isolation; NVIDIA response conversion, usage, error redaction and tool IDs; and free-tier enforcement. Real Chromium fixtures render JS and verify that 404/blocked pages do not prevent later success. A complete batch fixture exercises rendering, the NVIDIA adapter, extraction and saved records with a blocked domain between two successful companies. Regression cases cover profile swapping, retained evidence under shrinking budgets, newly discovered pagination, external quote/investor exclusion, search ambiguity/audit trails and Retry-After handling. Fake API responses test logic; real hosted runs and usage are reported separately.

In restricted environments, point PLAYWRIGHT_BROWSERS_PATH and TEMP/TMP to writable directories and use pytest --basetemp=PATH. The lock records tested Windows/Python 3.14.2 dependencies. Code targets 3.11+, but other environments were not exercised here.

## Known limitations

- Public sites and hosted models change. Login walls, challenges, missing pages, delayed hydration, closed shadow DOM and non-HTML content reduce coverage. Missing facts stay empty.
- urllib.robotparser is used as requested; advanced wildcard/end-anchor handling can differ from search engines. Only bounded page-number query links are supported; cursor/offset pagination and unavailable policies are skipped.
- DOM filters remove recognizable testimonials/investor sections. Names/roles must occur near each other in the same page, and site LinkedIn links need an unambiguous subject heading in a profile card. Unusual page structures may still be missed or misclassified; literal evidence does not prove current employment. A profile candidate is not verified ownership.
- The English sentence validator handles common abbreviations but can reject unusual punctuation. Confidence reflects evidence coverage, not a calibrated probability.
- NVIDIA's conservative token bound can omit evidence at very small budgets; generic sentence and DOM heuristics are not a semantic truth guarantee. HTTP acceptance alone does not prove every provider implements every schema keyword; records are independently validated.
- Public-host checks are not complete DNS-rebinding protection. Use an outbound proxy/network policy before exposing the CLI to untrusted remote users.
- Full disks, unwritable output roots, process interruption and machine failure can still prevent persistence. Atomic writes do not replace durable job infrastructure.
