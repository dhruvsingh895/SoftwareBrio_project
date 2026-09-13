from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeout

from company_intel.config import Settings
from company_intel.crawler import DomainCrawler
from company_intel.urls import canonical_url, normalize_domain


@pytest.mark.parametrize("domain", ["127.0.0.1", "localhost", "https://example.com:444", "https://x:y@example.com", "https://example.com/about"])
def test_reject_invalid_inputs(domain):
    with pytest.raises(ValueError):
        normalize_domain(domain)


def test_canonicalization_restricts_scope_and_query_actions():
    assert normalize_domain("HTTPS://WWW.Example.com/") == "example.com"
    assert canonical_url("/about/#people", "example.com") == "https://example.com/about"
    assert canonical_url("https://example.com.evil.com/about", "example.com") is None
    assert canonical_url("/contact?delete=1", "example.com") is None
    assert canonical_url("/logout", "example.com") is None
    assert canonical_url("http://example.com/team", "example.com") is None


def crawler_with_robots(status=200, body="User-agent: *\nDisallow: /private\nCrawl-delay: 3"):
    crawler = DomainCrawler(None, "example.com", Settings(delay_seconds=0.01))
    response = SimpleNamespace(status=status, headers={}, text=AsyncMock(return_value=body), dispose=AsyncMock())
    crawler.context = SimpleNamespace(request=SimpleNamespace(get=AsyncMock(return_value=response)))
    crawler.hosts.allowed = AsyncMock(return_value=True)
    crawler.pace = AsyncMock()
    return crawler


async def test_robots_cached_disallowed_paths_are_never_fetched():
    crawler = crawler_with_robots()
    assert await crawler.robots_allowed("https://example.com/about")
    assert not await crawler.robots_allowed("https://example.com/private")
    assert await crawler.fetch_page("https://example.com/private") is None
    assert crawler.context.request.get.await_count == 1
    assert crawler._delay == 3
    assert any("robots disallows" in x for x in crawler.result.errors)


@pytest.mark.parametrize("status,allowed", [(404, True), (410, True), (403, False), (429, False), (503, False)])
async def test_robots_status_policy(status, allowed):
    crawler = crawler_with_robots(status)
    assert await crawler.robots_allowed("https://example.com/") is allowed


async def test_networkidle_fallback_reuses_document():
    crawler = crawler_with_robots()
    handlers = {}
    frame = object()

    async def goto(*args, **kwargs):
        handlers["response"](SimpleNamespace(status=200, frame=frame,
            request=SimpleNamespace(is_navigation_request=lambda: True)))
        raise PlaywrightTimeout("network busy")

    page = SimpleNamespace(main_frame=frame, on=lambda event, handler: handlers.update({event: handler}),
                           goto=AsyncMock(side_effect=goto), wait_for_load_state=AsyncMock())
    assert await crawler._navigate(page, "https://example.com/") == 200
    assert page.goto.await_count == 1
    page.wait_for_load_state.assert_awaited_once_with("domcontentloaded", timeout=15000)


async def test_navigation_timeout_retries_once_with_longer_timeout():
    crawler = crawler_with_robots()
    page = SimpleNamespace(on=lambda *args: None, goto=AsyncMock(side_effect=PlaywrightTimeout("timeout")))
    assert await crawler._navigate(page, "https://example.com/") is None
    assert [call.kwargs["timeout"] for call in page.goto.await_args_list] == [15000, 30000]


async def test_redirect_guard_blocks_disallowed_destination_before_fetch():
    crawler = crawler_with_robots()
    frame = SimpleNamespace()
    frame.page = SimpleNamespace(main_frame=frame)
    route = SimpleNamespace(request=SimpleNamespace(resource_type="document", url="https://example.com/private",
        is_navigation_request=lambda: True, frame=frame), abort=AsyncMock(), continue_=AsyncMock())
    await crawler._route(route)
    route.abort.assert_awaited_once()
    route.continue_.assert_not_awaited()


async def test_page_limit_and_dedup_apply_even_when_disallowed():
    crawler = crawler_with_robots(body="User-agent: *\nDisallow: /")
    crawler.settings = Settings(max_pages=2)
    for url in ("/about", "/about/", "/team", "/contact"):
        await crawler.fetch_page(url)
    assert len(crawler.result.attempted) == 2


def test_discovery_includes_deep_links_and_heuristics():
    crawler = crawler_with_robots()
    crawler._links = [{"url": "/company/about-acme/", "text": "About us"},
                      {"url": "https://other.com/team", "text": "Team"},
                      {"url": "/docs/", "text": "Documentation"}]
    candidates = crawler.candidates()
    assert candidates[0] == "https://example.com/company/about-acme"
    assert "https://example.com/about" in candidates
    assert not any("other.com" in x for x in candidates)
