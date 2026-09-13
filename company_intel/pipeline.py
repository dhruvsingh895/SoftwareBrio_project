"""Batch orchestration and atomic, inspectable JSON/evidence artifacts."""

import asyncio
import json
import logging
import os
import platform
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from anthropic import AsyncAnthropic
from playwright.async_api import async_playwright

from .cleaner import build_context
from .config import Settings
from .crawler import CrawlResult, DomainCrawler
from .extractor import Extractor, UsageLedger
from .schema import CompanyIntel
from .nvidia import NvidiaClient
from .search_fallback import LinkedInSearch
from .urls import domain_slug, normalize_domain

log = logging.getLogger(__name__)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: Path, value) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


@dataclass
class Outcome:
    record: CompanyIntel
    status: str = "pending"
    crawl: CrawlResult | None = None
    context: str = ""
    ledger: UsageLedger = field(default_factory=UsageLedger)
    search_audit: list[dict] = field(default_factory=list)


async def process_domain(value: str, browser, client, settings: Settings, search, setup_error: str | None = None) -> Outcome:
    outcome = Outcome(CompanyIntel.empty(value))
    extractor = Extractor(client, settings, outcome.ledger) if client else None
    try:
        domain = normalize_domain(value)
        outcome.record.domain = domain
        if setup_error:
            outcome.record.crawl_errors.append(setup_error)
        if browser is None:
            outcome.status = "browser_failed"
            return outcome
        crawler = DomainCrawler(browser, domain, settings)
        # Set before entering: failures in setup/cleanup still preserve collected evidence.
        outcome.crawl = crawler.result
        async with crawler:
            await crawler.fetch_page(f"https://{domain}/")
            if settings.agentic and extractor:
                try:
                    await extractor.navigate(crawler)
                except Exception as exc:
                    crawler.error(f"agentic navigation: {type(exc).__name__}: {str(exc)[:300]}; continuing deterministic crawl")
            await crawler.crawl_remaining()
        outcome.context = build_context(crawler.result.pages, settings.context_tokens)
        if not crawler.result.pages:
            outcome.record.crawl_errors.append("No usable pages; extraction skipped")
            outcome.status = "crawl_failed"
        elif settings.crawl_only:
            outcome.record.crawl_errors.append("Crawl-only mode; LLM extraction not performed")
            outcome.status = "crawl_only"
        elif extractor is None:
            key_name = "NVIDIA_API_KEY" if settings.provider == "nvidia" else "ANTHROPIC_API_KEY"
            outcome.record.crawl_errors.append(f"{key_name} is not configured; LLM extraction not performed")
            outcome.status = "missing_api_key"
        else:
            cards = [card for page in crawler.result.pages for card in page.profile_evidence]
            facts = await extractor.extract(domain, outcome.context, outcome.record.crawl_errors, cards)
            for key in type(facts).model_fields:
                setattr(outcome.record, key, getattr(facts, key))
            outcome.status = "completed" if facts.company_overview else "insufficient_evidence"
            if settings.linkedin_search and search:
                for index, person in enumerate(outcome.record.leadership[:5]):
                    if not person.linkedin_url:
                        outcome.record.leadership[index] = await search.lookup(
                            person, domain.split(".")[0], outcome.record.crawl_errors, outcome.search_audit,
                        )
    except Exception as exc:
        message = f"domain failure: {type(exc).__name__}: {str(exc)[:500]}"
        outcome.record.crawl_errors.append(message)
        outcome.status = "failed"
        log.exception("[%s] Domain failed; batch continues", value)
    finally:
        if outcome.crawl:
            outcome.record.pages_crawled = [p.url for p in outcome.crawl.pages]
            outcome.record.crawl_errors.extend(outcome.crawl.errors)
            if not outcome.context:
                outcome.context = build_context(outcome.crawl.pages, settings.context_tokens)
        if extractor and extractor.context_sent:
            outcome.context = extractor.context_sent
        outcome.record.crawl_errors = list(dict.fromkeys(outcome.record.crawl_errors))
        outcome.record.token_usage = outcome.ledger.tokens()
        outcome.record.estimated_cost_usd = outcome.ledger.cost(settings)
        log.info("[%s] %s | pages=%d | input=%d output=%d | $%.6f | confidence=%.2f",
                 outcome.record.domain, outcome.status, len(outcome.record.pages_crawled),
                 outcome.ledger.input_tokens, outcome.ledger.output_tokens,
                 outcome.record.estimated_cost_usd, outcome.record.confidence_score)
    return outcome


def save_outcome(outcome: Outcome, settings: Settings) -> None:
    slug = domain_slug(outcome.record.domain)
    atomic_json(settings.output_dir / f"{slug}.json", outcome.record.model_dump())
    evidence = settings.output_dir / "evidence" / slug
    atomic_text(evidence / "context.txt", outcome.context)
    atomic_json(evidence / "crawl.json", {
        "status": outcome.status,
        "attempted_urls": outcome.crawl.attempted if outcome.crawl else [],
        "robots": outcome.crawl.robots if outcome.crawl else {},
        "pages": [asdict(page) for page in outcome.crawl.pages] if outcome.crawl else [],
        "llm_calls": outcome.ledger.calls,
        "linkedin_search": outcome.search_audit,
        "navigation_steps": outcome.crawl.navigation if outcome.crawl else [],
        "context_note": "Exact final evidence sent if an extraction call was attempted; otherwise locally budgeted clean text.",
    })


def summary_table(rows: list[dict], cost: float) -> str:
    header = "| Domain | Status | Pages | Input tokens | Output tokens | Cost USD | Confidence |"
    lines = [header, "|---|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        safe_domain = row['domain'].replace('|', '\\|').replace('\n', ' ')
        lines.append(f"| {safe_domain} | {row['status']} | {row['pages_crawled']} | "
                     f"{row['input_tokens']} | {row['output_tokens']} | "
                     f"{row['estimated_cost_usd']:.6f} | {row['confidence_score']:.2f} |")
    lines.append(f"\nTotal estimated LLM cost: ${cost:.6f}")
    return "\n".join(lines) + "\n"


async def run_batch(domains: list[str], settings: Settings) -> dict:
    if settings.free_tier_only and (settings.provider != "nvidia" or settings.input_price != 0 or settings.output_price != 0):
        raise ValueError("Free-tier-only runs must use NVIDIA hosted prototyping and zero token rates")
    started = datetime.now(timezone.utc)
    semaphore = asyncio.Semaphore(settings.concurrency)
    client = None
    browser = None
    playwright = None
    setup_error = None
    try:
        key_name = "NVIDIA_API_KEY" if settings.provider == "nvidia" else "ANTHROPIC_API_KEY"
        if os.getenv(key_name) and not settings.crawl_only:
            try:
                # SDK retries disabled so exactly one retry policy owns API attempts.
                client = (NvidiaClient(api_key=os.environ[key_name]) if settings.provider == "nvidia" else
                          AsyncAnthropic(api_key=os.environ[key_name], max_retries=0, timeout=60))
            except Exception as exc:
                setup_error = f"LLM client setup: {type(exc).__name__}: {str(exc)[:250]}"
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=True)
        except Exception as exc:
            setup_error = f"browser setup: {type(exc).__name__}: {str(exc)[:500]}"
            log.error(setup_error)
        search = LinkedInSearch(browser, settings) if browser and settings.linkedin_search else None

        async def safe(value: str) -> Outcome:
            async with semaphore:
                try:
                    outcome = await process_domain(value, browser, client, settings, search, setup_error)
                except Exception as exc:
                    # Last boundary: even a bug in process_domain/finally cannot break siblings.
                    outcome = Outcome(CompanyIntel.empty(value, [f"unhandled domain error: {type(exc).__name__}: {str(exc)[:300]}"]), "failed")
                try:
                    await asyncio.to_thread(save_outcome, outcome, settings)
                except Exception as exc:
                    outcome.record.crawl_errors.append(f"artifact write failed: {type(exc).__name__}: {str(exc)[:200]}")
                    outcome.status = "write_failed"
                    log.error("[%s] Artifact write failed; record retained in summary", value)
                return outcome

        # Normalize duplicate valid domains once; malformed entries still receive failure records.
        unique: dict[str, str] = {}
        for value in domains:
            try:
                key = normalize_domain(value)
            except ValueError:
                key = value
            unique.setdefault(key, value)
        outcomes = await asyncio.gather(*(safe(value) for value in unique.values()))
    finally:
        for resource in (browser, client):
            if resource:
                try:
                    await resource.close()
                except Exception as exc:
                    log.warning("Cleanup failed: %s", type(exc).__name__)
        if playwright:
            try:
                await playwright.stop()
            except Exception as exc:
                log.warning("Playwright shutdown failed: %s", type(exc).__name__)
    rows = [{"domain": o.record.domain, "status": o.status, "pages_crawled": len(o.record.pages_crawled),
             **o.ledger.tokens(), "estimated_cost_usd": o.record.estimated_cost_usd,
             "confidence_score": o.record.confidence_score} for o in outcomes]
    total = round(sum(o.record.estimated_cost_usd for o in outcomes), 8)
    summary = {
        "started_at": started.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(), "model": settings.model,
        "provider": settings.provider,
        "free_tier_only": settings.free_tier_only,
        "input_budget_method": ("conservative UTF-8 payload bytes + 1024 template allowance" if settings.provider == "nvidia"
                                else "Anthropic count_tokens endpoint"),
        "pricing": {"input_usd_per_token": settings.input_price, "output_usd_per_token": settings.output_price,
                    "basis": settings.pricing_basis,
                    "source": ("https://docs.api.nvidia.com/nim/docs/product" if settings.provider == "nvidia"
                               else "https://platform.claude.com/docs/en/about-claude/pricing"), "verified_date": "2026-09-13"},
        "mode": "crawl_only" if settings.crawl_only else "agentic" if settings.agentic else "deterministic",
        "complete": all(o.status == "completed" for o in outcomes),
        "domains": rows, "total_input_tokens": sum(o.ledger.input_tokens for o in outcomes),
        "total_output_tokens": sum(o.ledger.output_tokens for o in outcomes),
        "total_estimated_cost_usd": total, "records": [o.record.model_dump() for o in outcomes],
    }
    await asyncio.to_thread(atomic_json, settings.output_dir / "output.json", summary["records"])
    await asyncio.to_thread(atomic_json, settings.output_dir / "summary.json", summary)
    table = summary_table(rows, total)
    await asyncio.to_thread(atomic_text, settings.output_dir / "summary.md", table)
    log.info("\n%s", table)
    return summary
