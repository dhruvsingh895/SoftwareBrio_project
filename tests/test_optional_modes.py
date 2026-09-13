from types import SimpleNamespace
from unittest.mock import AsyncMock

from company_intel import search_fallback
from company_intel.cleaner import CleanPage
from company_intel.config import Settings
from company_intel.crawler import DomainCrawler
from company_intel.extractor import Extractor, UsageLedger
from company_intel.schema import TeamMember
from company_intel.search_fallback import LinkedInSearch


class Block:
    type = "tool_use"
    id = "tool_1"

    def __init__(self, name, arguments):
        self.name = name
        self.input = arguments

    def model_dump(self, **kwargs):
        return {"type": self.type, "id": self.id, "name": self.name, "input": self.input}


def tool_response(block):
    return SimpleNamespace(id="msg_nav", stop_reason="tool_use", content=[block],
                           usage=SimpleNamespace(input_tokens=50, output_tokens=10))


async def test_agentic_navigation_cannot_bypass_scope_and_counts_all_calls():
    crawler = DomainCrawler(None, "example.com", Settings())
    crawler.result.pages.append(CleanPage("https://example.com/", "Home", "We build developer tools. " * 10))
    messages = SimpleNamespace(count_tokens=AsyncMock(return_value=SimpleNamespace(input_tokens=1000)),
        create=AsyncMock(return_value=tool_response(Block("fetch_page", {"url": "https://evil.com/team"}))))
    ledger = UsageLedger()
    await Extractor(SimpleNamespace(messages=messages), Settings(agent_steps=3), ledger).navigate(crawler)
    assert messages.create.await_count == 3
    assert ledger.tokens() == {"input_tokens": 150, "output_tokens": 30}
    assert crawler.result.attempted == []
    assert any("out-of-scope" in error for error in crawler.result.errors)
    for call in messages.create.await_args_list:
        assert all(tool["strict"] for tool in call.kwargs["tools"])


async def test_agentic_stops_before_call_when_input_budget_is_exceeded():
    crawler = DomainCrawler(None, "example.com", Settings())
    messages = SimpleNamespace(count_tokens=AsyncMock(return_value=SimpleNamespace(input_tokens=15000)), create=AsyncMock())
    await Extractor(SimpleNamespace(messages=messages), Settings(), UsageLedger()).navigate(crawler)
    messages.create.assert_not_awaited()
    assert any("input budget" in error for error in crawler.result.errors)


class SearchCrawler:
    body = """<html><div class="result"><a href="https://www.linkedin.com/in/ada-lovelace">
        Ada Lovelace - CEO at Acme</a><p>Public professional profile at Acme</p></div></html>"""
    allowed = True

    def __init__(self, *args):
        page = SimpleNamespace(route=AsyncMock(), content=AsyncMock(return_value=self.body))
        self.context = SimpleNamespace(new_page=AsyncMock(return_value=page))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def robots_allowed(self, url):
        return self.allowed

    async def _navigate(self, page, target):
        return 200


async def test_search_attaches_profile_only_with_name_and_company_evidence(monkeypatch):
    monkeypatch.setattr(search_fallback, "DomainCrawler", SearchCrawler)
    person = TeamMember(name="Ada Lovelace", role="CEO", source="site")
    audit = []
    result = await LinkedInSearch(None, Settings()).lookup(person, "Acme", [], audit)
    assert result.linkedin_url == "https://www.linkedin.com/in/ada-lovelace"
    assert result.source == "search"
    assert "Ada Lovelace" in audit[0]["snippet"]


async def test_ambiguous_search_result_stays_null(monkeypatch):
    monkeypatch.setattr(search_fallback, "DomainCrawler", SearchCrawler)
    person = TeamMember(name="Ada Lovelace", role="CEO", source="site")
    errors = []
    result = await LinkedInSearch(None, Settings()).lookup(person, "OtherCompany", errors, [])
    assert result.linkedin_url is None and result.source == "site"
    assert any("no unambiguous" in error for error in errors)


async def test_search_robots_block_disables_later_searches(monkeypatch):
    monkeypatch.setattr(search_fallback, "DomainCrawler", SearchCrawler)
    monkeypatch.setattr(SearchCrawler, "allowed", False)
    search = LinkedInSearch(None, Settings())
    person = TeamMember(name="Ada Lovelace", role="CEO", source="site")
    errors = []
    assert await search.lookup(person, "Acme", errors, []) == person
    assert search.disabled_reason
    assert await search.lookup(person, "Acme", errors, []) == person
    assert "skipped" in errors[-1]
