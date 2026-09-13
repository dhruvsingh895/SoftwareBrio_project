"""Regression cases for gaps found while auditing the assignment rubric."""

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx2
import pytest

from company_intel import search_fallback
from company_intel.cleaner import CleanPage, build_context, clean_html, detect_block, shrink_context
from company_intel.config import Settings
from company_intel.crawler import DomainCrawler
from company_intel.extractor import Extractor, UsageLedger, api_retry, retryable, retry_wait, validate_evidence
from company_intel.nvidia import NvidiaAPIError, NvidiaClient
from company_intel.retry_policy import retry_after_seconds
from company_intel.schema import CompanyFacts, TeamMember
from company_intel.search_fallback import LinkedInSearch
from company_intel.urls import canonical_url, url_key


def team_page():
    return clean_html("""<html><body><main><h1>Leadership</h1>
      <article><h2>Ada Lovelace</h2><p>CEO/Co-Founder</p>
        <p>Ada works with Grace Hopper to build tools for developers.</p>
        <a href="https://linkedin.com/in/ada-lovelace">Connect with Ada</a></article>
      <article><h2>Grace Hopper</h2><p>CTO/Co-Founder</p><p>Grace leads engineering.</p>
        <a href="https://linkedin.com/in/grace-hopper">Connect with Grace</a></article>
    </main></body></html>""", "https://acme.com/team")


def test_profile_cards_survive_budgeting_and_cannot_be_swapped():
    page = team_page()
    assert len(page.profile_evidence) == 2
    context = build_context([page, CleanPage("https://acme.com/", "Home", "API tools. " * 4000)], 3000)
    context = shrink_context(context, 1800)
    assert "PAGE: https://acme.com/\n" in context
    assert "CEO/Co-Founder" in context and "CTO/Co-Founder" in context
    facts = CompanyFacts(company_overview="Acme builds API tools. Developers use them.",
        target_audience="Developers", contact_points=[], confidence_score=0.9,
        leadership=[TeamMember(name="Grace Hopper", role="CTO/Co-Founder",
                               linkedin_url="https://www.linkedin.com/in/ada-lovelace", source="site")])
    errors = []
    result = validate_evidence(facts, context, errors, page.profile_evidence)
    assert result.leadership[0].linkedin_url == "https://www.linkedin.com/in/grace-hopper"
    assert any("unassociated" in error for error in errors)
    facts.leadership[0].role = "CEO/Co-Founder"
    assert not validate_evidence(facts, context, [], page.profile_evidence).leadership


def test_no_association_inferred_from_aggregate_grid_or_url_slug():
    page = clean_html("""<html><body><main><h1>Team</h1><p>Ada Lovelace, CEO.</p>
      <p>Grace Hopper, CTO.</p><div><a href="https://linkedin.com/in/ada-lovelace">Profile</a>
      <a href="https://linkedin.com/in/grace-hopper">Profile</a></div></main></body></html>""", "https://acme.com/team")
    assert page.profile_evidence == []


def test_customer_quote_and_investors_do_not_become_company_leadership():
    page = clean_html('''<html><body><main><h1>About Acme</h1>
      <p>Acme builds developer tools for software teams that need reliable APIs.</p>
      <div><p>"My biggest regret is not having used Acme from the beginning."</p>
      <p>Jakob Example, Co-founder &amp; Tech Lead, Customer Corp</p></div>
      <section><h2>Our investors</h2><p>Grace Example, Founder of Different Inc.</p></section>
      <section><h2>Our team</h2><h3>Ada Lovelace</h3><p>CEO of Acme</p></section>
      </main></body></html>''', "https://acme.com/company")
    assert "Ada Lovelace" in page.text and "CEO of Acme" in page.text
    assert "Jakob Example" not in page.text and "Grace Example" not in page.text
    assert len(page.excluded_sections) == 2
    context = build_context([page], 2000)
    facts = CompanyFacts(company_overview="Acme builds developer tools. Software teams use them.",
        target_audience="Developers", contact_points=[], confidence_score=0.8,
        leadership=[TeamMember(name="Jakob Example", role="Co-founder & Tech Lead", source="site")])
    assert not validate_evidence(facts, context, []).leadership


def test_budget_reduction_retains_signals_from_every_page():
    pages = [CleanPage(f"https://acme.com/{path}", path, "Readable marketing words " * 5000,
                       emails=[f"{path}@acme.com"]) for path in ("team", "about", "contact", "pricing")]
    context = shrink_context(build_context(pages, 12000), 2400)
    assert len(context) <= 2400
    for page in pages:
        assert f"PAGE: {page.url}" in context and page.emails[0] in context


@pytest.mark.parametrize("query", ["page=0", "page=21", "page=-1", "page=2&delete=1", "page=2&page=3", "cursor=secret"])
def test_pagination_rejects_unbounded_or_action_queries(query):
    assert canonical_url("/team?" + query, "acme.com") is None


async def test_discovery_revisits_links_after_each_page_and_keeps_page_cap():
    crawler = DomainCrawler(None, "acme.com", Settings(max_pages=8))
    crawler._links = [{"url": "/about", "text": "About"}]

    async def fetch(url):
        crawler._attempted.add(url_key(url))
        crawler.result.attempted.append(url)
        if url.endswith("/about"):
            crawler._links.append({"url": "/team", "text": "Our Team"})
        if url.endswith("/team"):
            crawler._links.append({"url": "/team?page=2", "text": "Next", "rel": "next", "source": url})
        if "?page=" in url:
            number = int(url.rsplit("=", 1)[1])
            crawler._links.append({"url": f"/team?page={number + 1}", "text": "Next", "rel": "next", "source": url})

    crawler.fetch_page = fetch
    await crawler.crawl_remaining()
    assert crawler.result.attempted[:3] == ["https://acme.com/about", "https://acme.com/team", "https://acme.com/team?page=2"]
    assert len(crawler.result.attempted) == len(set(crawler.result.attempted)) == 8
    assert url_key("https://acme.com/team?page=2") != url_key("https://acme.com/team")


def test_soft404_and_search_challenge_are_not_company_evidence():
    assert detect_block("<title>404 - Page not found</title><p>Try again</p>", 200)
    assert detect_block("<title>DuckDuckGo</title><p>Unfortunately, bots use DuckDuckGo too.</p>", 202)
    assert detect_block("<title>API platform</title><p>Monitor your API's 404 responses.</p>", 200) is None


def test_retry_after_seconds_and_dates_honored_without_unbounded_waits():
    error = NvidiaAPIError(429, retry_after="25")
    state = SimpleNamespace(outcome=SimpleNamespace(exception=lambda: error), attempt_number=1)
    assert retry_wait(state) >= 25
    assert not retryable(NvidiaAPIError(429, retry_after="120"))
    when = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30), usegmt=True)
    assert 28 <= retry_after_seconds(when) <= 30
    assert retry_after_seconds("nonsense") is None


async def test_real_adapter_rate_limit_header_stops_early_retry():
    attempts = []

    async def handle(request):
        attempts.append(request)
        return httpx2.Response(429, headers={"retry-after": "120"}, json={"message": "Rate limit"})

    client = NvidiaClient("fixture-key", transport=httpx2.MockTransport(handle))
    try:
        with pytest.raises(NvidiaAPIError):
            await api_retry(client.create, model="fixture-model", messages=[], tools=[], system="Test",
                            tool_choice={"type": "auto"})
        assert len(attempts) == 1
    finally:
        await client.close()


class SearchFixture:
    body = ""

    def __init__(self, *args):
        page = SimpleNamespace(route=AsyncMock(), content=AsyncMock(return_value=self.body))
        self.context = SimpleNamespace(new_page=AsyncMock(return_value=page))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def robots_allowed(self, url):
        return True

    async def _navigate(self, page, target):
        return 200


async def test_search_logs_negative_results_and_rejects_two_matching_people(monkeypatch):
    monkeypatch.setattr(search_fallback, "DomainCrawler", SearchFixture)
    person = TeamMember(name="Ada Lovelace", role="CEO", source="site")
    audit = []
    monkeypatch.setattr(SearchFixture, "body", "<html><p>No results</p></html>")
    await LinkedInSearch(None, Settings()).lookup(person, "Acme", [], audit)
    assert audit[0]["status"] == "no_match" and audit[0]["query"]
    monkeypatch.setattr(SearchFixture, "body", """<html>
      <div class="result"><a href="https://www.linkedin.com/in/ada-one?trk=search">Ada Lovelace at Acme</a></div>
      <div class="result"><a href="https://www.linkedin.com/in/ada-two">Ada Lovelace at Acme</a></div></html>""")
    audit = []
    result = await LinkedInSearch(None, Settings()).lookup(person, "Acme", [], audit)
    assert result.linkedin_url is None and audit[0]["status"] == "ambiguous"
    assert len(audit[0]["candidates"]) == 2
