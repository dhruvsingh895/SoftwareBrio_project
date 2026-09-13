"""Editable crawl limits, model defaults and provider token prices."""

from dataclasses import dataclass
from pathlib import Path

# https://platform.claude.com/docs/en/about-claude/pricing (checked 2026-09-13)
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
NVIDIA_DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"
# NVIDIA API Catalog developer-program prototyping access, not production hosting.
# https://docs.api.nvidia.com/nim/docs/product (checked 2026-09-13)
NVIDIA_INPUT_PRICE_PER_TOKEN = 0.0
NVIDIA_OUTPUT_PRICE_PER_TOKEN = 0.0
INPUT_PRICE_PER_TOKEN = 1.0 / 1_000_000
OUTPUT_PRICE_PER_TOKEN = 5.0 / 1_000_000
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 "
    "CompanyIntelBot/1.0"
)
ROBOTS_AGENT = "CompanyIntelBot"


@dataclass(frozen=True)
class Settings:
    output_dir: Path = Path("output")
    provider: str = "anthropic"
    model: str = DEFAULT_MODEL
    concurrency: int = 3
    max_pages: int = 8
    timeout_ms: int = 15_000
    delay_seconds: float = 1.0
    context_tokens: int = 12_000
    max_output_tokens: int = 3_000
    min_text_chars: int = 120
    agentic: bool = False
    agent_steps: int = 4
    linkedin_search: bool = True
    crawl_only: bool = False
    input_price: float = INPUT_PRICE_PER_TOKEN
    output_price: float = OUTPUT_PRICE_PER_TOKEN
    pricing_basis: str = "Anthropic standard uncached token rates"
    free_tier_only: bool = False
