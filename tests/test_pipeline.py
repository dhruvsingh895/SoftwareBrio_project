import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from company_intel import pipeline
from company_intel.cleaner import CleanPage
from company_intel.config import Settings
from company_intel.crawler import CrawlResult
from company_intel.pipeline import Outcome, process_domain, run_batch
from company_intel.schema import CompanyIntel


class StubCrawler:
    def __init__(self, browser, domain, settings):
        self.domain = domain
        self.result = CrawlResult(domain)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def fetch_page(self, url):
        if self.domain == "empty.com":
            self.result.errors.append("HTTP 404")
            return None
        page = CleanPage(url, "Company", "Ada Lovelace\nCEO\nWe make API tools. " * 10)
        self.result.pages.append(page)
        return page

    async def crawl_remaining(self):
        return self.result


async def test_all_pages_fail_emits_exact_empty_schema(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "DomainCrawler", StubCrawler)
    outcome = await process_domain("empty.com", object(), None, Settings(output_dir=tmp_path), None)
    assert outcome.status == "crawl_failed"
    assert outcome.record.company_overview == ""
    assert outcome.record.confidence_score == 0
    assert "HTTP 404" in outcome.record.crawl_errors
    CompanyIntel.model_validate(outcome.record.model_dump())


async def test_missing_key_keeps_live_crawl_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "DomainCrawler", StubCrawler)
    outcome = await process_domain("good.com", object(), None, Settings(output_dir=tmp_path), None)
    assert outcome.status == "missing_api_key"
    assert outcome.record.pages_crawled == ["https://good.com/"]
    assert outcome.record.token_usage == {"input_tokens": 0, "output_tokens": 0}
    assert "Ada Lovelace" in outcome.context


async def test_batch_isolates_unhandled_domain_failure_and_writes_all_records(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    browser = SimpleNamespace(close=AsyncMock())
    playwright = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)), stop=AsyncMock())
    monkeypatch.setattr(pipeline, "async_playwright", lambda: SimpleNamespace(start=AsyncMock(return_value=playwright)))

    async def process(value, *args):
        if value == "broken.com":
            raise RuntimeError("injected domain failure")
        return Outcome(CompanyIntel.empty(value), "completed")

    monkeypatch.setattr(pipeline, "process_domain", process)
    summary = await run_batch(["good.com", "broken.com", "later.com"], Settings(output_dir=tmp_path))
    assert [r["status"] for r in summary["domains"]] == ["completed", "failed", "completed"]
    assert summary["complete"] is False
    for domain in ("good", "broken", "later"):
        CompanyIntel.model_validate_json((tmp_path / f"{domain}_com.json").read_text())
    assert len(json.loads((tmp_path / "summary.json").read_text())["records"]) == 3
    assert json.loads((tmp_path / "output.json").read_text()) == summary["records"]
    assert (tmp_path / "summary.md").is_file()


async def test_failure_after_llm_response_keeps_billed_tokens_and_pages(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "DomainCrawler", StubCrawler)
    data = {"company_overview": "Invalid one sentence.", "target_audience": "Developers",
            "contact_points": [], "leadership": [], "confidence_score": 0.4}
    response = SimpleNamespace(id="msg_bad", stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=111, output_tokens=22),
        content=[SimpleNamespace(type="tool_use", name="emit_company_intel", input=data)])
    client = SimpleNamespace(messages=SimpleNamespace(count_tokens=AsyncMock(return_value=SimpleNamespace(input_tokens=800)),
                                                       create=AsyncMock(return_value=response)))
    outcome = await process_domain("good.com", object(), client, Settings(output_dir=tmp_path), None)
    assert outcome.status == "failed"
    assert outcome.record.pages_crawled == ["https://good.com/"]
    assert outcome.record.token_usage == {"input_tokens": 222, "output_tokens": 44}
    assert outcome.record.estimated_cost_usd > 0
    assert outcome.record.confidence_score == 0
