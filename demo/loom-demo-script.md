**Autonomous Lead Enrichment Agent — recording guide and narration**

Aim for 2 minutes 45 seconds of finished video. Read only the quoted narration aloud; the other text tells you what to show. This is a terminal application, so demonstrate the editor, terminal, and JSON results.

**Prepare before recording**

1. Open `C:\Users\2k22a\OneDrive\Desktop\pr` in your editor. Expand the `company_intel` package in the file explorer. Make the code and terminal text large enough to read.
2. Have these files ready in tabs:
   - `C:\Users\2k22a\OneDrive\Desktop\pr\domains.json`
   - `C:\Users\2k22a\OneDrive\Desktop\pr\company_intel\cleaner.py` — the `clean_html` function, around line 132.
   - `C:\Users\2k22a\OneDrive\Desktop\pr\company_intel\schema.py` — the `CompanyFacts` model.
   - `C:\Users\2k22a\OneDrive\Desktop\pr\README.md`
3. Close the real `.env` tab and this chat before sharing your screen, so your API key stays off camera. If demonstrating environment setup, show only `C:\Users\2k22a\OneDrive\Desktop\pr\.env.example`.
4. Record your editor window with microphone audio. A webcam is optional. Avoid spending video time on dependency installation; this local environment is already configured.
5. Run the commands below once as a rehearsal. The last verified three-domain run took about 2 minutes 33 seconds, and live timing can vary. During the recording, pause only the screen recording while waiting, or trim that waiting segment afterward. Keep the terminal process running. State that you are skipping the wait.

**Commands to prepare**

At the start of the demonstration, use PowerShell:

```powershell
cd "C:\Users\2k22a\OneDrive\Desktop\pr"
.\.venv\Scripts\python.exe main.py --provider nvidia --free-tier-only --domains-file domains.json --output-dir output/demo
```

This uses the configured NVIDIA key and browser. It writes a fresh demonstration batch under `C:\Users\2k22a\OneDrive\Desktop\pr\output\demo`; rerunning the same command replaces that batch's artifacts. The existing verified local batch remains available under `C:\Users\2k22a\OneDrive\Desktop\pr\output\local`.

After the process finishes and the PowerShell prompt returns:

```powershell
.\.venv\Scripts\python.exe verify_outputs.py output/demo
Get-Content .\output\demo\summary.md
```

The verifier checks saved results without another API call. It expects a completed, populated batch; a failed verification needs inspection rather than being presented as success.

Open the fresh combined result in your editor:

`C:\Users\2k22a\OneDrive\Desktop\pr\output\demo\output.json`

If you prefer Notepad:

```powershell
notepad .\output\demo\output.json
```

**0:00–0:20 — introduce the problem and inputs**

Show the project explorer and the three domains in `C:\Users\2k22a\OneDrive\Desktop\pr\domains.json`.

> Hi, I'm [your name]. This is my Autonomous Lead Enrichment Agent. It takes company domains, browses their public websites, and turns the available evidence into structured company intelligence. I'll demonstrate it using the three assignment targets: Postman, Supabase, and Vapi.

**0:20–0:45 — start the actual pipeline**

Switch to the terminal, execute the main command above, and briefly show the first crawl logs.

> I'm starting the pipeline from the terminal with this JSON input file. The command explicitly selects NVIDIA and enables the free-tier-only guard. The companies are processed concurrently, and the results will be saved in this run's output directory.

**0:45–1:15 — explain the architecture and cleaning**

With the crawl running, point to the package modules in the explorer. Open `C:\Users\2k22a\OneDrive\Desktop\pr\company_intel\cleaner.py` at `clean_html`.

> The code separates crawling, cleaning, extraction, and orchestration. Playwright renders JavaScript pages and discovers relevant links, including about, team, contact, and pricing pages. The cleaner removes scripts, styles, SVGs, and navigation boilerplate. It retains useful text and contact signals, then builds a bounded context so the LLM doesn't receive raw HTML trees.

**1:15–1:40 — show the schema and explain resilience**

Open `C:\Users\2k22a\OneDrive\Desktop\pr\company_intel\schema.py` at `CompanyFacts`. Point to the fields and confidence bounds. Do not try to read every function on screen.

> Pydantic defines the output contract: a two-sentence overview, target audience, public emails, leadership details, and confidence between zero and one. Extraction validates the schema and checks entity evidence. Timeouts, missing pages, bot blockers, and provider errors are handled with bounded retries and per-domain failure isolation.

If the crawl is still running, say this before pausing the recording or cutting the wait:

> I'll skip the waiting time and resume when extraction finishes.

Do not stop the pipeline. Resume with its actual completion logs visible.

**1:40–2:15 — demonstrate the final JSON**

Open `C:\Users\2k22a\OneDrive\Desktop\pr\output\demo\output.json`. Show the Postman record first, scrolling through the overview, audience, contacts, leadership, and confidence. Briefly show that Supabase and Vapi also have records.

> Here is the combined JSON for the three companies. Each record contains the requested business information, alongside source pages, crawl errors, and token usage. LinkedIn profiles are included when supported by the evidence. Missing information stays empty, and confidence reflects evidence completeness. Keeping the crawl evidence makes the extracted details easier to inspect.

**2:15–2:45 — validate, show accounting, and close**

Return to the terminal. Run the verifier and summary commands above. Only use the success sentence below if verification passes. Finish by showing the README setup and run instructions.

> The saved-output verifier passes these records, checking the schema, entity evidence, page limits, and token totals. The summary records usage and estimated cost per domain. The zero-dollar estimate uses the configured NVIDIA free-tier rates. The project includes modular Python code, dependencies, tests, setup instructions, and a three-company sample output. Thank you.

**Rehearsal and accuracy notes**

- Narration is approximately 290 words, including the sentence about skipping the wait. Rehearse at a comfortable pace and keep the finished recording under three minutes. The timestamps are editing targets, not a promise about API response time.
- Playwright runs headlessly: terminal crawl logs and saved page evidence demonstrate the browser work; a visible browser window is not expected.
- You can briefly show the cleaned evidence at `C:\Users\2k22a\OneDrive\Desktop\pr\output\demo\evidence\postman_com\context.txt` if there is time. Show it instead of adding another long explanation.
- The default demonstration uses deterministic link discovery. The project also supports optional LLM tool-driven navigation through `--agentic`; do not describe the default run as using that option.
- Optional LinkedIn search can be blocked. Do not claim that search always finds profiles or that missing public information was recovered.
- The saved test report at `C:\Users\2k22a\OneDrive\Desktop\pr\verification\tests.xml` records 67 tests with zero failures, errors, or skips. This is an existing test result, separate from the saved-output check performed during the demo.
- A zero-dollar estimate is tied to the configured free-tier accounting; do not describe the service as unlimited or guarantee permanent free access.
- If the fresh run is partial or fails, show its status honestly. You may switch to `C:\Users\2k22a\OneDrive\Desktop\pr\output\local\output.json`, saying: “This live attempt hit an external issue. Here is the output from an earlier successful run of the same three domains.” Use `output/local` in the verifier command too. Do not present earlier results as the new run.
- The previously verified local batch completed all three domains: Postman crawled 6 pages, Supabase 6, and Vapi 4. It recorded 7,766 input tokens, 766 output tokens, and $0 estimated API cost. A new demonstration may produce different values; narrate what is actually on screen.
- Show a GitHub page only after you have confirmed your push succeeded. This script does not assume the remote repository has been populated.
