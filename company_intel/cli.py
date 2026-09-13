"""CLI entry point: python main.py --domains postman.com supabase.com vapi.ai."""

import argparse
import asyncio
import json
import logging
import math
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from company_intel.config import (
    DEFAULT_MODEL, NVIDIA_DEFAULT_MODEL, INPUT_PRICE_PER_TOKEN, OUTPUT_PRICE_PER_TOKEN,
    NVIDIA_INPUT_PRICE_PER_TOKEN, NVIDIA_OUTPUT_PRICE_PER_TOKEN, Settings,
)
from company_intel.pipeline import run_batch


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Crawl public company websites and extract evidence-supported intelligence.")
    result.add_argument("--domains", nargs="+", default=[])
    result.add_argument("--domains-file", type=Path, help="JSON array of domains (combined with --domains)")
    result.add_argument("--output-dir", type=Path, default=Path("output"))
    result.add_argument("--env-file", type=Path, default=Path.cwd() / ".env")
    result.add_argument("--provider", choices=("auto", "anthropic", "nvidia"), default="auto")
    result.add_argument("--free-tier-only", action="store_true", help="Restrict inference to NVIDIA hosted prototyping, with zero token rates and no paid fallback")
    result.add_argument("--model", help="Provider-specific model ID; defaults to Haiku 4.5 or Nemotron 3 Super")
    result.add_argument("--concurrency", type=int, default=3)
    result.add_argument("--max-pages", type=int, choices=range(1, 9), default=8)
    result.add_argument("--timeout-ms", type=int, default=15000)
    result.add_argument("--delay", type=float, default=1.0, help="Minimum seconds between same-domain navigations")
    result.add_argument("--context-tokens", type=int, default=12000, help="Input token budget including schema and prompt; NVIDIA uses a conservative local bound")
    result.add_argument("--agentic", action="store_true")
    result.add_argument("--agent-steps", type=int, choices=range(3, 6), default=4)
    result.add_argument("--no-linkedin-search", action="store_true")
    result.add_argument("--crawl-only", action="store_true")
    result.add_argument("--input-price-per-million", type=float)
    result.add_argument("--output-price-per-million", type=float)
    return result


def main() -> int:
    arg_parser = parser()
    args = arg_parser.parse_args()
    domains = list(args.domains)
    if args.domains_file:
        try:
            supplied = json.loads(args.domains_file.read_text(encoding="utf-8-sig"))
            if not isinstance(supplied, list) or not all(isinstance(x, str) for x in supplied):
                raise ValueError("domains file must be a JSON array of strings")
            domains.extend(supplied)
        except (OSError, ValueError) as exc:
            arg_parser.error(str(exc))
    if not domains:
        arg_parser.error("Provide --domains or --domains-file")
    if args.concurrency < 1 or args.timeout_ms < 1000 or args.context_tokens < 2000:
        arg_parser.error("concurrency >= 1, timeout-ms >= 1000 and context-tokens >= 2000 are required")
    if not math.isfinite(args.delay) or args.delay < 0.1:
        arg_parser.error("delay must be finite and at least 0.1 seconds")
    prices = (args.input_price_per_million, args.output_price_per_million)
    if any(p is not None and (not math.isfinite(p) or p < 0) for p in prices):
        arg_parser.error("Prices must be finite and nonnegative")
    load_dotenv(args.env_file, override=False)
    provider = args.provider
    if provider == "auto":
        provider = "nvidia" if args.free_tier_only or os.getenv("NVIDIA_API_KEY") else "anthropic"
    if args.free_tier_only and (provider != "nvidia" or any(p not in (None, 0) for p in prices)):
        arg_parser.error("--free-tier-only requires NVIDIA hosted prototyping with zero token rates")
    model = args.model or (NVIDIA_DEFAULT_MODEL if provider == "nvidia" else DEFAULT_MODEL)
    if provider == "anthropic" and model != DEFAULT_MODEL and any(p is None for p in prices):
        arg_parser.error("For a different Anthropic model, specify both price-per-million flags")
    if (prices[0] is None) != (prices[1] is None):
        arg_parser.error("Provide both price-per-million flags together")
    default_input = NVIDIA_INPUT_PRICE_PER_TOKEN if provider == "nvidia" else INPUT_PRICE_PER_TOKEN
    default_output = NVIDIA_OUTPUT_PRICE_PER_TOKEN if provider == "nvidia" else OUTPUT_PRICE_PER_TOKEN
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", handlers=[
        logging.StreamHandler(), logging.FileHandler(args.output_dir / "run.log", mode="w", encoding="utf-8"),
    ])
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    settings = Settings(
        output_dir=args.output_dir, provider=provider, model=model, concurrency=args.concurrency,
        free_tier_only=args.free_tier_only,
        max_pages=args.max_pages, timeout_ms=args.timeout_ms, delay_seconds=args.delay,
        context_tokens=args.context_tokens, agentic=args.agentic, agent_steps=args.agent_steps,
        linkedin_search=not args.no_linkedin_search, crawl_only=args.crawl_only,
        input_price=prices[0] / 1_000_000 if prices[0] is not None else default_input,
        output_price=prices[1] / 1_000_000 if prices[1] is not None else default_output,
        pricing_basis=("User-configured token rates" if prices[0] is not None else
                       "NVIDIA Developer Program free hosted prototyping access; excludes production hosting" if provider == "nvidia" else
                       "Anthropic standard uncached token rates"),
    )
    try:
        summary = asyncio.run(run_batch(domains, settings))
        # Artifacts are always written first. Automation can detect partial/failed batches.
        return 0 if summary["complete"] or (args.crawl_only and all(r["status"] == "crawl_only" for r in summary["domains"])) else 2
    except KeyboardInterrupt:
        logging.warning("Interrupted by user")
        return 130
    except Exception:
        logging.exception("Batch-level infrastructure failure")
        return 1


if __name__ == "__main__":
    sys.exit(main())
