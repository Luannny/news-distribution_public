"""Check ordinary public article pages, without login or paywall bypasses."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

from .news_collector import NewsCandidate
from .news_policy import ALLOWED_DOMAINS, BLOCKED_DOMAINS, BLOCKED_SOURCE_NAMES, CATEGORIES, host_matches

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DailyNewsBrief/2.0; personal RSS reader)"}


def allowed_source(url: str, source: str = "") -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return False
    if any(host_matches(host, domain) for domain in BLOCKED_DOMAINS):
        return False
    if any(name in source.lower() for name in BLOCKED_SOURCE_NAMES):
        return False
    return any(host_matches(host, domain) for domain in ALLOWED_DOMAINS)


class ArticlePage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paragraphs = []
        self.metadata = {}
        self.jsonld = []
        self._p = None
        self._script = None
        self._ignored = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("style", "noscript"):
            self._ignored += 1
        if tag == "script":
            self._ignored += 1
            if attrs.get("type", "").lower() == "application/ld+json":
                self._script = []
        if tag == "meta":
            self.metadata[attrs.get("property", attrs.get("name", ""))] = attrs.get("content", "")
        if tag == "p" and not self._ignored:
            self._p = []

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)
        if self._p is not None and not self._ignored:
            self._p.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            if self._script is not None:
                try:
                    self.jsonld.append(json.loads("".join(self._script)))
                except (ValueError, TypeError):
                    pass
                self._script = None
            self._ignored = max(0, self._ignored - 1)
        elif tag in ("style", "noscript"):
            self._ignored = max(0, self._ignored - 1)
        if tag == "p" and self._p is not None:
            text = " ".join(" ".join(self._p).split())
            if len(text) >= 50:
                self.paragraphs.append(text)
            self._p = None


def json_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from json_objects(child)


def inspect_public_article(html: str) -> tuple[bool, ArticlePage]:
    page = ArticlePage()
    page.feed(html)
    objects = list(json_objects(page.jsonld))
    if any(str(obj.get("isAccessibleForFree", "")).lower() == "false" for obj in objects):
        return False, page
    # Explicit access gates only; donation/supporter banners are not paywalls.
    gates = (
        "subscribe to continue reading", "subscription required to read",
        "this content is for subscribers only", "register to continue reading",
        "sign in to continue reading", "this story is for members only",
        "this article is for members only", "subscribe to unlock this article",
    )
    visible = " ".join(page.paragraphs).lower()
    if any(gate in visible for gate in gates):
        return False, page
    if re.search(r'<title[^>]*>\s*(?:access denied|just a moment|robot or human|verify you)', html, re.I):
        return False, page
    return len(" ".join(page.paragraphs)) >= 800, page


def verify_candidate(item: NewsCandidate) -> NewsCandidate | None:
    if not allowed_source(item.url, item.source):
        return None
    if item.access_checked_at:
        try:
            checked = datetime.fromisoformat(item.access_checked_at)
            age = (datetime.now(timezone.utc) - checked).total_seconds()
            if 0 <= age < 300:
                return item
        except (ValueError, TypeError):
            pass
    try:
        # Validate each redirect before following it, rather than fetching unknown hosts.
        url = item.url
        from urllib.parse import urljoin
        for _ in range(4):
            response = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=False)
            if response.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers.get("Location", ""))
                if not allowed_source(url, item.source):
                    return None
                continue
            break
        else:
            return None
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return None
        readable, page = inspect_public_article(response.text)
        if not readable:
            return None
    except (requests.RequestException, ValueError):
        return None
    # Use only a publisher-provided description as extra evidence; navigation and
    # donation paragraphs must never become news facts.
    description = page.metadata.get("og:description") or page.metadata.get("description")
    return replace(
        item, url=url, summary=(description or item.summary)[:1000],
        access_checked_at=datetime.now(timezone.utc).isoformat(),
    )


def verify_readable_candidates(candidates: list[NewsCandidate], per_category: int = 18) -> list[NewsCandidate]:
    # Bounded and balanced: finance cannot consume the entire checking budget.
    pool = []
    for category in CATEGORIES:
        members = [item for item in candidates if item.category == category]
        pool.extend(members[:per_category])
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(verify_candidate, pool))
    verified = [item for item in results if item is not None]
    print("Readable original links:", {c: sum(x.category == c for x in verified) for c in CATEGORIES})
    return verified
