"""DOM cleaning and high-value signals. HTML never leaves this module's boundary."""

import html as html_lib
import json
import re
from dataclasses import dataclass, field
from urllib.parse import unquote

import trafilatura
from lxml import html

from .urls import priority

EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", re.ASCII)
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/(?:in|company)/[\w-]+", re.I)
TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")


@dataclass
class CleanPage:
    url: str
    title: str
    text: str
    emails: list[str] = field(default_factory=list)
    linkedin_urls: list[str] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)
    profile_evidence: list[dict] = field(default_factory=list)
    excluded_sections: list[dict[str, str]] = field(default_factory=list)


def plain(value: str) -> str:
    return TAG_RE.sub("", html_lib.unescape(value)).replace("\x00", "")


def profile_cards(tree) -> list[dict]:
    """Preserve a profile's nearest small DOM container, never a whole team grid.

    Headings identify the subject; biography mentions alone cannot associate a
    different person's name with this LinkedIn URL.
    """
    cards: dict[str, dict] = {}
    for anchor in tree.xpath("//a[contains(@href, 'linkedin.com/in/')]"):
        match = LINKEDIN_RE.search(anchor.get("href", ""))
        if not match:
            continue
        profile = "https://www.linkedin.com/" + match.group().split("linkedin.com/", 1)[1]
        for parent in list(anchor.iterancestors())[:6]:
            if parent.tag in {"body", "html", "main"}:
                break
            urls = {m.group().split("linkedin.com/", 1)[1] for node in parent.xpath(".//a[@href]")
                    if (m := LINKEDIN_RE.search(node.get("href", ""))) and "/in/" in m.group()}
            if len(urls) != 1:
                break
            headings = [plain(" ".join(n.itertext())).strip() for n in parent.xpath(".//h1|.//h2|.//h3|.//h4|.//h5|.//h6")]
            snippet = re.sub(r"\s+", " ", plain(" ".join(parent.itertext()))).strip()
            if headings and len(headings) <= 3 and 25 <= len(snippet) <= 2500:
                cards.setdefault(profile, {"linkedin_url": profile, "headings": headings,
                                           "text": snippet[:400]})
                break
    return list(cards.values())[:30]


def drop_non_team_sections(tree) -> list[dict[str, str]]:
    """Remove explicit investor sections and attributed quotations before extraction.

    Article extraction can lose the employer in a testimonial attribution. Keeping
    such a person's name/title while dropping that employer creates false leaders.
    This filter is deliberately DOM based, with no company-specific names.
    """
    removed = []

    def drop(node, reason: str) -> None:
        if node.getparent() is not None and node.tag not in {"main", "body", "html"}:
            removed.append({"reason": reason, "text": plain(" ".join(node.itertext()))[:2000]})
            node.drop_tree()

    for node in tree.xpath("//*[@class or @id]"):
        label = (node.get("class", "") + " " + node.get("id", "")).lower()
        if "testimonial" in label:
            drop(node, "testimonial container")
    for node in tree.xpath("//p|//q|//blockquote"):
        text = plain(" ".join(node.itertext())).strip()
        quoted = node.tag in {"q", "blockquote"} or (text.startswith(('"', '\u201c')) and text.endswith(('"', '\u201d')))
        parent = node.getparent()
        if not quoted or len(text) < 25 or parent is None:
            continue
        content = plain(" ".join(parent.itertext())).strip()
        has_title = re.search(r"\b(?:CEO|CTO|CFO|founder|co-founder|director|lead|head of|VP)\b", content, re.I)
        if (has_title and len(content) <= 1800 and len(content) > len(text) + 10
                and not parent.xpath(".//h1|.//h2|.//h3|.//h4|.//h5|.//h6")):
            drop(parent, "attributed quotation; affiliation may be external")
    for heading in tree.xpath("//h1|//h2|//h3|//h4|//h5|//h6"):
        if tree is not heading and tree not in heading.iterancestors():
            continue
        if not re.fullmatch(r"(?:our |individual |angel )?investors", " ".join(heading.itertext()).strip(), re.I):
            continue
        selected = None
        for parent in list(heading.iterancestors())[:7]:
            if parent.tag in {"main", "body", "html"}:
                break
            content = " ".join(parent.itertext()).strip()
            section = parent.tag == "section" or "section" in parent.get("class", "").lower()
            if section and len(content) <= 16000 and "investor" in content[:150].lower():
                selected = parent
                break
            # Subordinate headings may be investor names; peer headings delimit sections.
            headings = [" ".join(n.itertext()).strip() for n in parent.xpath(".//h1|.//h2|.//h3|.//h4|.//h5|.//h6")
                        if n.tag <= heading.tag]
            if any("investor" not in value.lower() for value in headings):
                break
            if len(" ".join(parent.itertext())) > 16000:
                break
            selected = parent
        if selected is not None:
            drop(selected, "investor listing")
    return removed[:30]


def extract_signals(raw_html: str) -> tuple[list[str], list[str]]:
    # Exclude executable/hidden application payloads, but retain footer and mailto evidence.
    tree = html.fromstring(raw_html)
    for node in tree.xpath("//script|//style|//svg|//noscript|//template"):
        node.drop_tree()
    source = unquote(html_lib.unescape(html.tostring(tree, encoding="unicode")))
    emails = sorted({m.group().strip(".").lower() for m in EMAIL_RE.finditer(source)
                     if not m.group().lower().endswith((".png", ".jpg", ".webp", ".svg"))})
    profiles = sorted({"https://www." + re.sub(r"^.*?linkedin\.com/", "linkedin.com/", m.group(), flags=re.I)
                       for m in LINKEDIN_RE.finditer(source)})
    return emails[:100], profiles[:100]


def clean_html(raw_html: str, url: str) -> CleanPage:
    tree = html.fromstring(raw_html)
    title = plain(" ".join(tree.xpath("//title/text()")))[:300]
    links = [{"url": node.get("href", ""), "text": plain(" ".join(node.itertext()))[:200],
              "rel": node.get("rel", "")}
             for node in tree.xpath("//a[@href]")]
    emails, profiles = extract_signals(raw_html)
    for node in tree.xpath(
        "//script|//style|//svg|//nav|//footer|//noscript|//template|//iframe|//form|//pre|//code|"
        "//*[@role='navigation' or @role='contentinfo' or @role='banner' or @hidden or @aria-hidden='true']"
    ):
        if node.getparent() is not None:
            node.drop_tree()
    excluded = drop_non_team_sections(tree)
    sanitized = html.tostring(tree, encoding="unicode")
    cards = profile_cards(tree)
    text = trafilatura.extract(
        sanitized, output_format="txt", include_comments=False, include_tables=True,
        include_links=False, favor_recall=True, deduplicate=True,
    ) or ""
    # Short Contact/Team pages often lack article structure; still use sanitized DOM only.
    if len(text.strip()) < 120:
        text = "\n".join(t.strip() for t in tree.xpath("//body//text()") if t.strip())
    # Article extractors often omit headings, which can contain the only leadership names.
    headings = [" ".join(node.itertext()).strip() for node in tree.xpath("//h1|//h2|//h3|//h4|//h5|//h6")]
    missing_headings = [heading for heading in headings if heading and heading not in text]
    if missing_headings:
        text = "\n".join(missing_headings) + "\n" + text
    seen: set[str] = set()
    lines: list[str] = []
    for line in plain(text).splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        key = line.casefold()
        if line and key not in seen:
            seen.add(key)
            lines.append(line)
    return CleanPage(url, title, "\n".join(lines), emails, profiles, links, cards, excluded)


def shrink_context(context: str, char_budget: int) -> str:
    """Allocate body space across pages while retaining complete signal headers.

    Repeated provider budget checks must not discard every page at the tail.
    Very small budgets retain whole headers in priority order, never broken cards.
    """
    if len(context) <= char_budget:
        return context
    blocks = re.split(r"\n\n(?=PAGE: )", context)
    if not all("\nTEXT:\n" in b for b in blocks):
        return context[:char_budget]
    selected: list[tuple[str, str]] = []
    available = max(0, char_budget)
    for block in blocks:
        header, body = block.split("\nTEXT:\n", 1)
        header += "\nTEXT:\n"
        if len(header) + 2 <= available:
            selected.append((header, body))
            available -= len(header) + 2
    result = []
    for index, (header, body) in enumerate(selected):
        allowance = available // (len(selected) - index)
        trimmed = body[:allowance]
        # Avoid cutting a long word mid-token, without discarding short headings.
        if len(body) > allowance and " " in trimmed[-80:]:
            trimmed = trimmed.rsplit(" ", 1)[0]
        result.append(header + trimmed)
        available -= len(trimmed)
    return "\n\n".join(result)[:char_budget]


def build_context(pages: list[CleanPage], token_budget: int) -> str:
    """Approximate 3 chars/token locally; extractor applies provider counting before calls."""
    char_budget = max(0, token_budget * 3)
    blocks: list[str] = []
    seen: set[str] = set()
    for page in sorted(pages, key=lambda p: priority(p.url), reverse=True):
        signals = "\n".join([
            "Emails observed on this page: " + ", ".join(page.emails),
            "LinkedIn URLs observed on this page (not proof of person/profile association): " + ", ".join(page.linkedin_urls),
            *["PROFILE CARD: " + json.dumps(card, ensure_ascii=False) for card in page.profile_evidence],
        ])
        header = f"PAGE: {page.url}\nTITLE: {page.title}\n{signals}\nTEXT:\n"
        # Preserve meaningful short headings/names; deduplicate longer boilerplate across pages.
        lines = []
        for line in page.text.splitlines():
            key = line.casefold()
            if len(line) < 50 or key not in seen:
                lines.append(line)
                seen.add(key)
        # Spread the budget: long marketing pages cannot consume the entire context.
        block = header + "\n".join(lines)[:9000]
        blocks.append(block)
    return shrink_context(plain("\n\n".join(blocks)), char_budget)


def detect_block(raw_html: str, status: int) -> str | None:
    if status in (401, 403, 429):
        return f"access blocked (HTTP {status})"
    tree = html.fromstring(raw_html)
    for node in tree.xpath("//script|//style|//svg"):
        node.drop_tree()
    title = " ".join(tree.xpath("//title/text()")).lower()
    visible = " ".join(tree.itertext()).lower()
    if any(s in title for s in ("access denied", "just a moment", "captcha", "attention required")):
        return "bot challenge detected"
    if re.search(r"\b404\b|page not found|page doesn't exist", title):
        return "soft 404 page detected"
    if len(visible) < 8_000 and any(s in visible for s in (
        "verify you are human", "complete the captcha", "unusual traffic",
        "access denied", "checking your browser", "enable javascript and cookies to continue",
        "unfortunately, bots use duckduckgo too", "select all squares containing a duck",
    )):
        return "bot challenge detected"
    return None
