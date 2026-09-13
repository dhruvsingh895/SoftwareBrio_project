"""Canonical public HTTPS URLs and crawl priorities."""

import asyncio
import hashlib
import ipaddress
import re
import socket
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

KEYWORDS = ("leadership", "team", "about", "company", "contact", "pricing", "careers", "press", "media")
HEURISTIC_PATHS = ("/about", "/about-us", "/company", "/team", "/leadership", "/contact", "/pricing")


def normalize_domain(value: str) -> str:
    value = value.strip()
    parts = urlsplit(value if "://" in value else "https://" + value)
    if parts.scheme != "https" or parts.username or parts.password:
        raise ValueError("Use a public domain or an HTTPS homepage without credentials")
    if parts.port not in (None, 443) or parts.query or parts.fragment or parts.path not in ("", "/"):
        raise ValueError("Expected a domain, not a port, subpage, query, or fragment")
    host = (parts.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
    if host.startswith("www."):
        host = host[4:]
    if len(host) > 253 or "." not in host:
        raise ValueError("Expected a fully qualified public domain")
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x) for x in host.split(".")):
        raise ValueError("Invalid domain name")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP address inputs are not supported")
    return host


def canonical_url(value: str, domain: str, base: str | None = None) -> str | None:
    try:
        parts = urlsplit(urljoin(base or f"https://{domain}/", value))
        if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
            return None
        host = (parts.hostname or "").lower().rstrip(".")
        if host not in (domain, "www." + domain):
            return None
        path = re.sub(r"/{2,}", "/", parts.path or "/")
        if re.search(r"\.(?:pdf|zip|png|jpe?g|webp|svg|xml|json|css|js|mp4)$", path, re.I):
            return None
        if re.search(r"(?:^|/)(?:logout|signout|delete|unsubscribe)(?:/|$)", unquote(path), re.I):
            return None
        # Only bounded page-number pagination; unknown/action parameters stay out.
        query = parse_qsl(parts.query, keep_blank_values=True)
        if query and (len(query) != 1 or query[0][0] != "page" or
                      not re.fullmatch(r"[1-9][0-9]?", query[0][1]) or int(query[0][1]) > 20):
            return None
        return urlunsplit(("https", host, path.rstrip("/") or "/", urlencode(query), ""))
    except ValueError:
        return None


def url_key(url: str) -> str:
    parts = urlsplit(url)
    return ((parts.hostname or "").removeprefix("www.") + (parts.path.rstrip("/") or "/")
            + ("?" + parts.query if parts.query else ""))


def priority(url: str, anchor: str = "") -> int:
    path = urlsplit(url).path.lower()
    weights = {"leadership": 100, "team": 95, "about": 90, "company": 80,
               "press": 85, "media": 85, "contact": 75, "pricing": 40, "careers": 30}
    score = max((v for k, v in weights.items() if k in path), default=0)
    score = max(score, max((v - 15 for k, v in weights.items() if k in anchor.lower()), default=0))
    if path in ("", "/"):
        return 55
    # Product pages about customer teams are not company leadership pages.
    if path.startswith(("/solutions/", "/use-cases/", "/product/")):
        score = min(score, 20)
    if any(x in path for x in ("/blog/", "/docs/", "/customers/", "/events/", "/legal/")):
        score -= 45
    # Prefer the default/English pages within a small crawl budget.
    if re.match(r"^/(?:[a-z]{2}|[a-z]{2}-[a-z]{2})/", path) and not path.startswith(("/en/", "/en-us/")):
        score -= 60
    return score


def domain_slug(value: str) -> str:
    if re.fullmatch(r"[a-z0-9.-]+", value):
        return value.replace(".", "_")
    return "invalid_" + hashlib.sha256(value.encode()).hexdigest()[:12]


class PublicHosts:
    """Reject local/private destinations, including redirects and browser subresources."""

    def __init__(self) -> None:
        self.cache: dict[str, bool] = {}

    async def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme not in ("https", "http") or not host or parts.port not in (None, 80, 443):
            return False
        if host not in self.cache:
            try:
                addresses = await asyncio.wait_for(
                    asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM), 8
                )
                self.cache[host] = bool(addresses) and all(
                    ipaddress.ip_address(a[4][0]).is_global for a in addresses
                )
            except (OSError, ValueError, TimeoutError):
                self.cache[host] = False
        return self.cache[host]
