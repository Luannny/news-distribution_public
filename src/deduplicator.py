from __future__ import annotations

import re
from urllib.parse import urlparse
from difflib import SequenceMatcher

from .news_collector import NewsCandidate
from .article_access import allowed_source
from .news_policy import CATEGORIES


def filter_and_deduplicate(candidates: list[NewsCandidate]) -> list[NewsCandidate]:
    filtered = [item for item in candidates if _passes_basic_filter(item)]
    deduped: list[NewsCandidate] = []
    seen_urls: set[str] = set()
    seen_titles: list[str] = []

    for item in sorted(filtered, key=lambda candidate: candidate.published_at, reverse=True):
        normalized_url = item.url.split("?")[0].rstrip("/")
        normalized_title = _normalize_title(item.title)
        if not normalized_title or normalized_url in seen_urls:
            continue
        if any(_is_similar(normalized_title, existing) for existing in seen_titles):
            continue
        deduped.append(item)
        seen_urls.add(normalized_url)
        seen_titles.append(normalized_title)

    return deduped


def _passes_basic_filter(item: NewsCandidate) -> bool:
    text = f"{item.title} {item.summary}".lower()
    if not item.title or not item.url or item.category not in CATEGORIES or not allowed_source(item.url, item.source):
        return False
    if "/live/" in urlparse(item.url).path:
        return False
    # Sports and fashion are first-class sections. Do not require finance/AI keywords.
    noise = ("gaming patch", "changelog", "release notes", "minor update", "shop now", "best deals", "stocks to buy", "seeking full-time", "seeking part-time", "internship", "sponsored content", "find fashion jobs", "job vacancies", "apply now")
    return not any(_contains_term(text, keyword) for keyword in noise)


def _normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", " ", title)
    return " ".join(title.split())


def _is_similar(left: str, right: str) -> bool:
    return SequenceMatcher(None, left, right).ratio() >= 0.82


def _contains_term(text: str, term: str) -> bool:
    if not term.isascii():
        return term in text
    pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None
