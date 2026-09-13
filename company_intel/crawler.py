"""Playwright-only fetching with bounded navigation, robots checks, and pacing."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from playwright.async_api import Browser, BrowserContext, Page, Route, TimeoutError as PlaywrightTimeout

from .cleaner import CleanPage, clean_html, detect_block
from .config import ROBOTS_AGENT, USER_AGENT, Settings
from .urls import HEURISTIC_PATHS, KEYWORDS, PublicHosts, canonical_url, priority, url_key

log = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    domain: str
    pages: list[CleanPage] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    attempted: list[str] = field(default_factory=list)
    robots: dict[str, dict] = field(default_factory=dict)
    navigation: list[dict] = field(default_factory=list)


class DomainCrawler:
    def __init__(self, browser: Browser, domain: str, settings: Settings):
        self.browser = browser
        self.domain = domain
        self.settings = settings
        self.result = CrawlResult(domain)
        self.context: BrowserContext | None = None
        self.hosts = PublicHosts()
        self._robots: dict[str, RobotFileParser] = {}
        self._last_request = 0.0
        self._delay = settings.delay_seconds
        self._pace_lock = asyncio.Lock()
        self._attempted: set[str] = set()
        self._successful: set[str] = set()
        self._links: list[dict[str, str]] = []

    def error(self, message: str) -> None:
        if message not in self.result.errors:
            self.result.errors.append(message)
            log.warning("[%s] %s", self.domain, message)

    async def __aenter__(self) -> "DomainCrawler":
        self.context = await self.browser.new_context(
            user_agent=USER_AGENT, viewport={"width": 1440, "height": 1000},
            locale="en-US", service_workers="block", accept_downloads=False,
        )
        self.context.set_default_timeout(self.settings.timeout_ms)
        return self

    async def __aexit__(self, *_args) -> None:
        if self.context:
            await self.context.close()

    async def pace(self) -> None:
        async with self._pace_lock:
            wait = self._delay - (time.monotonic() - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()

    async def robots_allowed(self, url: str) -> bool:
        """robots.txt itself is the bootstrap request. Unknown/unavailable policy fails closed."""
        origin = "https://" + (urlsplit(url).hostname or "")
        if origin not in self._robots:
            parser = RobotFileParser(origin + "/robots.txt")
            # Cache a deny-all policy immediately; errors cannot accidentally enable a crawl.
            parser.parse(["User-agent: *", "Disallow: /"])
            self._robots[origin] = parser
            metadata: dict = {"url": origin + "/robots.txt", "status": None, "policy": "deny"}
            self.result.robots[origin] = metadata
            try:
                assert self.context is not None
                target = metadata["url"]
                for _ in range(6):
                    if not await self.hosts.allowed(target):
                        raise ValueError("robots destination is not a reachable public host")
                    await self.pace()
                    response = await self.context.request.get(
                        target, timeout=self.settings.timeout_ms, max_redirects=0,
                    )
                    try:
                        status = response.status
                        metadata["status"] = status
                        if status in (301, 302, 303, 307, 308):
                            target = urljoin(target, response.headers.get("location", ""))
                            if not canonical_url(target, self.domain):
                                raise ValueError("robots redirect leaves the domain or HTTPS")
                            continue
                        if status in (404, 410):
                            parser = RobotFileParser(origin + "/robots.txt")
                            parser.parse(["User-agent: *", "Allow: /"])
                            self._robots[origin] = parser
                            metadata["policy"] = "allow (robots missing)"
                        elif status == 200:
                            body = await response.text()
                            if len(body) > 512_000 or "<html" in body.lower():
                                raise ValueError("robots response is HTML or exceeds 512KB")
                            parser = RobotFileParser(origin + "/robots.txt")
                            parser.parse(body.splitlines())
                            self._robots[origin] = parser
                            metadata.update(policy="parsed", text=body)
                            crawl_delay = parser.crawl_delay(ROBOTS_AGENT)
                            request_rate = parser.request_rate(ROBOTS_AGENT)
                            if crawl_delay:
                                self._delay = max(self._delay, float(crawl_delay))
                            if request_rate and request_rate.requests:
                                self._delay = max(self._delay, request_rate.seconds / request_rate.requests)
                        else:
                            self.error(f"robots: HTTP {status} for {target}; fail closed")
                        break
                    finally:
                        await response.dispose()
                else:
                    self.error(f"robots: too many redirects for {origin}; fail closed")
            except Exception as exc:
                self.error(f"robots: {type(exc).__name__}: {str(exc)[:300]}; fail closed")
        return self._robots[origin].can_fetch(ROBOTS_AGENT, url)

    async def _route(self, route: Route) -> None:
        request = route.request
        try:
            if request.resource_type in ("image", "media", "font"):
                await route.abort()
                return
            if not await self.hosts.allowed(request.url):
                await route.abort()
                return
            if request.is_navigation_request():
                # Includes HTTP redirects and JS-triggered navigation, before destination fetch.
                if request.frame != request.frame.page.main_frame:
                    await route.abort()
                    return
                target = canonical_url(request.url, self.domain)
                if not target or not await self.robots_allowed(request.url):
                    self.error(f"navigation blocked by scope/robots: {request.url[:300]}")
                    await route.abort()
                    return
                await self.pace()
            await route.continue_()
        except Exception as exc:
            self.error(f"request guard: {type(exc).__name__}: {str(exc)[:150]}")
            try:
                await route.abort()
            except Exception:
                pass

    async def _navigate(self, page: Page, url: str) -> int | None:
        statuses: list[int] = []

        def track(response) -> None:
            if response.request.is_navigation_request() and response.frame == page.main_frame:
                statuses.append(response.status)

        page.on("response", track)
        for attempt in range(2):
            statuses.clear()
            timeout = self.settings.timeout_ms * (attempt + 1)
            try:
                response = await page.goto(url, wait_until="networkidle", timeout=timeout)
                return response.status if response else (statuses[-1] if statuses else None)
            except PlaywrightTimeout:
                # Reuse a document already received; do not needlessly request it again.
                if statuses:
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=timeout)
                        self.error(f"{url}: networkidle timeout; used domcontentloaded fallback")
                        return statuses[-1]
                    except PlaywrightTimeout:
                        pass
                self.error(f"{url}: navigation timeout on attempt {attempt + 1}")
                if attempt == 1:
                    return None
        return None

    async def fetch_page(self, value: str) -> CleanPage | None:
        url = canonical_url(value, self.domain)
        if not url:
            self.error(f"out-of-scope URL skipped: {value[:200]}")
            return None
        key = url_key(url)
        if key in self._successful:
            return next((p for p in self.result.pages if url_key(p.url) == key), None)
        if key in self._attempted or len(self.result.attempted) >= self.settings.max_pages:
            return None
        self._attempted.add(key)
        self.result.attempted.append(url)
        page = None
        try:
            if not await self.robots_allowed(url):
                self.error(f"robots disallows {url}")
                return None
            assert self.context is not None
            page = await self.context.new_page()
            await page.route("**/*", self._route)
            js_errors: list[str] = []
            page.on("pageerror", lambda exc: js_errors.append(str(exc)[:180]))
            log.info("[%s] Fetch %s (%d/%d)", self.domain, url,
                     len(self.result.attempted), self.settings.max_pages)
            status = await self._navigate(page, url)
            if status is None:
                return None
            if status >= 400:
                label = "bot/access block" if status in (401, 403, 429) else "HTTP error"
                self.error(f"{url}: {label} {status}; skipped")
                return None
            if status >= 300:
                self.error(f"{url}: unresolved HTTP redirect {status}; skipped")
                return None
            # Give client hydration a small bounded window after DOMContentLoaded fallback.
            await page.wait_for_timeout(500)
            final_url = canonical_url(page.url, self.domain)
            if not final_url or not await self.robots_allowed(page.url):
                self.error(f"{url}: final URL out of scope or disallowed")
                return None
            if url_key(final_url) in self._successful:
                return None
            raw_html = await page.content()
            if len(raw_html) > 8_000_000:
                self.error(f"{url}: rendered DOM exceeds 8MB limit")
                return None
            blocked = detect_block(raw_html, status)
            if blocked:
                self.error(f"{url}: {blocked}; skipped")
                return None
            cleaned = await asyncio.to_thread(clean_html, raw_html, final_url)
            # Retain homepage link discovery even when the readable body is near-empty.
            self._links.extend({**link, "url": urljoin(final_url, link["url"]), "source": final_url}
                               for link in cleaned.links)
            for message in js_errors[:3]:
                self.error(f"{url}: page JavaScript error: {message}")
            if len(cleaned.text.strip()) < self.settings.min_text_chars:
                self.error(f"{url}: empty/near-empty text ({len(cleaned.text)} chars); skipped")
                return None
            self._successful.update((key, url_key(final_url)))
            self.result.pages.append(cleaned)
            return cleaned
        except Exception as exc:
            self.error(f"{url}: {type(exc).__name__}: {str(exc)[:400]}")
            return None
        finally:
            if page:
                try:
                    await page.close()
                except Exception as exc:
                    self.error(f"page close: {type(exc).__name__}")

    def list_links(self) -> list[dict[str, str]]:
        base = self.result.pages[0].url if self.result.pages else f"https://{self.domain}/"
        found: dict[str, dict[str, str]] = {}
        for link in self._links:
            url = canonical_url(link["url"], self.domain, base)
            if not url or url_key(url) in self._attempted:
                continue
            relevant = any(k in urlsplit(url).path.lower() or k in link["text"].lower() for k in KEYWORDS)
            next_page = "next" in link.get("rel", "").split() and priority(link.get("source", "")) >= 30
            if relevant or next_page:
                old = found.get(url_key(url))
                if old is None or priority(url, link["text"]) > priority(url, old["text"]):
                    found[url_key(url)] = {"url": url, "text": link["text"], "discovery": "link"}
        return sorted(found.values(), key=lambda x: priority(x["url"], x["text"]), reverse=True)[:60]

    def candidates(self) -> list[str]:
        links = [x["url"] for x in self.list_links()]
        base = self.result.pages[0].url if self.result.pages else f"https://{self.domain}/"
        heuristics = [urljoin(base, path) for path in HEURISTIC_PATHS]
        # Reserve two attempts for heuristic paths; discovered deep About pages go first.
        remaining = self.settings.max_pages - len(self.result.attempted)
        ordered = links[:max(0, remaining - 2)] + heuristics + links[max(0, remaining - 2):]
        unique: dict[str, str] = {}
        for url in ordered:
            if url_key(url) not in self._attempted:
                unique.setdefault(url_key(url), url)
        return list(unique.values())

    async def crawl_remaining(self) -> CrawlResult:
        while len(self.result.attempted) < self.settings.max_pages:
            candidates = self.candidates()
            if not candidates:
                break
            # A fetched About page may reveal a Team page or the next directory page.
            before = len(self.result.attempted)
            await self.fetch_page(candidates[0])
            if len(self.result.attempted) == before:
                break
        return self.result
