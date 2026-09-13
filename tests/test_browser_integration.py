"""Real Chromium against fulfilled network fixtures; no public websites/API keys required."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
import json

import httpx2
from playwright.async_api import async_playwright

from company_intel import pipeline
from company_intel.config import Settings
from company_intel.crawler import DomainCrawler
from company_intel.nvidia import NvidiaClient
from company_intel.schema import CompanyIntel


async def test_rendered_dom_http_failures_robots_and_success_share_browser(monkeypatch):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        async with DomainCrawler(browser, "example.com", Settings(delay_seconds=0.01, timeout_ms=2000)) as crawler:
            crawler.hosts.allowed = AsyncMock(return_value=True)
            robots_response = SimpleNamespace(status=200, headers={}, dispose=AsyncMock(),
                text=AsyncMock(return_value="User-agent: *\nDisallow: /private"))
            monkeypatch.setattr(crawler.context.request, "get", AsyncMock(return_value=robots_response))
            original_guard = crawler._route
            requested = []

            async def fixture_route(route):
                async def serve():
                    url = route.request.url
                    requested.append(url)
                    if url.endswith("/missing"):
                        await route.fulfill(status=404, content_type="text/html", body="<h1>Missing</h1>")
                    elif url.endswith("/blocked"):
                        await route.fulfill(status=403, content_type="text/html", body="<h1>Access denied</h1>")
                    else:
                        await route.fulfill(status=200, content_type="text/html", body="""<html><body>
                        <nav>Navigation boilerplate</nav><main id="app"></main><footer>Footer boilerplate</footer>
                        <script>setTimeout(() => { document.querySelector('#app').innerHTML =
                        '<h1>Ada Lovelace</h1><p>CEO</p><p>Acme builds developer tools that help software teams '
                        + 'design, test and ship reliable APIs. Our platform supports teams of all sizes.</p>'
                        + '<a href="/team">Our team</a>'; }, 40);</script></body></html>""")

                await original_guard(SimpleNamespace(request=route.request, abort=route.abort, continue_=serve))

            crawler._route = fixture_route
            assert await crawler.fetch_page("/private") is None
            assert await crawler.fetch_page("/missing") is None
            assert await crawler.fetch_page("/blocked") is None
            page = await crawler.fetch_page("/")
            assert page is not None and "Ada Lovelace" in page.text
            assert "Navigation boilerplate" not in page.text
            assert "Footer boilerplate" not in page.text
            assert not any(url.endswith("/private") for url in requested)
            assert sum(url.endswith("/blocked") for url in requested) == 1
            assert any("HTTP error 404" in error for error in crawler.result.errors)
            assert "https://example.com/team" in crawler.candidates()
        await browser.close()


async def test_complete_batch_renders_extracts_and_saves_around_blocked_domain(monkeypatch, tmp_path):
    """Exercise the entire batch, Chromium, strict adapter and file outputs together."""
    class FixtureCrawler(DomainCrawler):
        async def __aenter__(self):
            await super().__aenter__()
            self.hosts.allowed = AsyncMock(return_value=True)
            robots = SimpleNamespace(status=200, headers={}, dispose=AsyncMock(),
                                     text=AsyncMock(return_value="User-agent: *\nAllow: /"))
            monkeypatch.setattr(self.context.request, "get", AsyncMock(return_value=robots))
            original = self._route

            async def route_guard(route):
                async def serve():
                    if self.domain == "blocked.example.com":
                        await route.fulfill(status=403, content_type="text/html", body="<h1>Access denied</h1>")
                    else:
                        await route.fulfill(status=200, content_type="text/html", body='''<html><body>
                          <nav>Ignore navigation</nav><main id="app"></main><script>
                          setTimeout(() => { document.querySelector('#app').innerHTML =
                            '<h1>Acme API tools</h1><p>Acme builds API tools. Developers use them.</p>' +
                            '<p>Engineering teams use our platform to design, test, and publish reliable APIs.</p>' +
                            '<p>sales@acme.com</p>'; }, 40);</script></body></html>''')

                await original(SimpleNamespace(request=route.request, abort=route.abort, continue_=serve))
            self._route = route_guard
            return self

    async def inference(request):
        payload = json.loads(request.content)
        assert "Acme builds API tools." in payload["messages"][1]["content"]
        assert "<script>" not in payload["messages"][1]["content"]
        facts = {"company_overview": "Acme builds API tools. Developers use them.", "target_audience": "Developers",
                 "contact_points": [{"type": "sales", "email": "sales@acme.com"}],
                 "leadership": [], "confidence_score": 0.7}
        return httpx2.Response(200, json={"id": "fixture-inference", "usage": {"prompt_tokens": 700, "completion_tokens": 100},
            "choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [{"id": "fixture-tool",
                "function": {"name": "emit_company_intel", "arguments": json.dumps(facts)}}]}}]})

    monkeypatch.setattr(pipeline, "DomainCrawler", FixtureCrawler)
    monkeypatch.setenv("NVIDIA_API_KEY", "fixture-key")
    monkeypatch.setattr(pipeline, "NvidiaClient", lambda api_key: NvidiaClient(api_key, transport=httpx2.MockTransport(inference)))
    settings = Settings(provider="nvidia", model="fixture-model", free_tier_only=True, input_price=0, output_price=0,
                        max_pages=2, delay_seconds=0.01, linkedin_search=False, timeout_ms=2000, output_dir=tmp_path)
    summary = await pipeline.run_batch(["good.example.com", "blocked.example.com", "later.example.com"], settings)
    assert [row["status"] for row in summary["domains"]] == ["completed", "crawl_failed", "completed"]
    assert summary["total_input_tokens"] == 1400 and summary["total_output_tokens"] == 200
    assert summary["complete"] is False
    for record in summary["records"]:
        slug = record["domain"].replace(".", "_")
        validated = CompanyIntel.model_validate_json((tmp_path / f"{slug}.json").read_text())
        assert validated.model_dump() == record
        assert (tmp_path / "evidence" / slug / "crawl.json").exists()
    assert summary["records"][1]["confidence_score"] == 0.0
