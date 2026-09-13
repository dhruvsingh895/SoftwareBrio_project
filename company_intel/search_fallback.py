"""Optional, conservative DuckDuckGo HTML lookup. No LinkedIn pages are fetched."""

import asyncio
import re
from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote, urlsplit

from lxml import html

from .cleaner import detect_block, plain
from .config import Settings
from .crawler import DomainCrawler
from .extractor import literal_in
from .schema import TeamMember


class LinkedInSearch:
    def __init__(self, browser, settings: Settings):
        self.browser = browser
        self.settings = settings
        # Shared by domains: never bombard the search provider concurrently.
        self.lock = asyncio.Lock()
        self.disabled_reason: str | None = None
        self.last_search = 0.0

    async def lookup(self, person: TeamMember, company: str, errors: list[str], audit: list[dict]) -> TeamMember:
        async with self.lock:
            query = f'"{person.name}" "{company}" site:linkedin.com/in'
            target = "https://html.duckduckgo.com/html/?q=" + quote(query)
            entry = {"name": person.name, "query": query, "search_url": target,
                     "checked_at": datetime.now(timezone.utc).isoformat(),
                     "status": "pending", "candidates": []}
            audit.append(entry)
            if self.disabled_reason:
                errors.append(f"LinkedIn search skipped: {self.disabled_reason}")
                entry.update(status="skipped", reason=self.disabled_reason)
                return person
            try:
                settings = replace(self.settings, delay_seconds=max(2.0, self.settings.delay_seconds))
                async with DomainCrawler(self.browser, "html.duckduckgo.com", settings) as crawler:
                    if not await crawler.robots_allowed(target):
                        self.disabled_reason = "DuckDuckGo robots disallows search or policy unavailable"
                        errors.append(f"LinkedIn search: {self.disabled_reason}")
                        entry.update(status="robots_blocked", reason=self.disabled_reason)
                        return person
                    page = await crawler.context.new_page()

                    async def guard(route):
                        request = route.request
                        if request.resource_type in ("image", "media", "font") or not await crawler.hosts.allowed(request.url):
                            await route.abort()
                        elif request.is_navigation_request():
                            if urlsplit(request.url).hostname != "html.duckduckgo.com" or not await crawler.robots_allowed(request.url):
                                await route.abort()
                            else:
                                await crawler.pace()
                                await route.continue_()
                        else:
                            await route.continue_()

                    await page.route("**/*", guard)
                    loop = asyncio.get_running_loop()
                    await asyncio.sleep(max(0, 2.0 - (loop.time() - self.last_search)))
                    self.last_search = loop.time()
                    status = await crawler._navigate(page, target)
                    entry["http_status"] = status
                    raw_html = await page.content()
                    if status is None or status >= 400 or detect_block(raw_html, status):
                        self.disabled_reason = "search provider unavailable or bot-blocked"
                        errors.append(f"LinkedIn search: {self.disabled_reason}")
                        entry.update(status="blocked", reason=self.disabled_reason)
                        return person
                    tree = html.fromstring(raw_html)
                    # Require a single distinct profile with explicit name AND company evidence.
                    matches: dict[str, str] = {}
                    for result in tree.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' result ')]"):
                        snippet = re.sub(r"\s+", " ", plain(" ".join(result.itertext()))).strip()[:1500]
                        for node in result.xpath(".//a[@href]"):
                            link = node.get("href", "")
                            if "uddg=" in link:
                                link = parse_qs(urlsplit(link).query).get("uddg", [""])[0]
                            parts = urlsplit(link)
                            if (parts.scheme != "https" or parts.username or parts.password or
                                not re.fullmatch(r"(?:[a-z]{2,3}\.)?linkedin\.com", parts.hostname or "") or
                                not re.fullmatch(r"/in/[\w-]+/?", parts.path)):
                                continue
                            link = "https://www.linkedin.com" + parts.path.rstrip("/")
                            qualified = literal_in(person.name, snippet) and literal_in(company, snippet)
                            candidate = {"linkedin_url": link, "snippet": snippet, "name_company_match": qualified}
                            if candidate not in entry["candidates"] and len(entry["candidates"]) < 20:
                                entry["candidates"].append(candidate)
                            if qualified:
                                matches.setdefault(link, snippet)
                    if len(matches) == 1:
                        link, snippet = next(iter(matches.items()))
                        entry.update(status="matched", linkedin_url=link, snippet=snippet)
                        return person.model_copy(update={"linkedin_url": link, "source": "search"})
                    entry["status"] = "ambiguous" if matches else "no_match"
                    errors.append(f"LinkedIn search: no unambiguous profile for {person.name}")
            except Exception as exc:
                reason = f"{type(exc).__name__}: {str(exc)[:200]}"
                entry.update(status="failed", reason=reason)
                errors.append(f"LinkedIn search: {reason}")
            return person
