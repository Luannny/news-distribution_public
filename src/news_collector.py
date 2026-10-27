from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlparse

import feedparser
import requests

from .news_policy import CATEGORIES, RSS_FEEDS


@dataclass(frozen=True)
class NewsCandidate:
    title: str
    url: str
    source: str
    published_at: datetime
    summary: str = ""
    category: str = "科技"
    access_checked_at: str = ""


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def classify_category(url: str, title: str, fallback: str = "政治") -> str:
    path = urlparse(url).path.lower()
    text = title.lower()
    if any(part in path for part in ("/sport", "/football", "/basketball", "/tennis")):
        return "体育"
    if any(part in path for part in ("/fashion", "/style")):
        return "时尚"
    if "/technology" in path and re.search(r'\b(ipo|initial public offering|stock market|valuation|earnings|buyouts?|layoffs?|job cuts|fundraising|quarterly profit)\b', text):
        return "经济"
    if any(part in path for part in ("/technology", "/science", "/tech/")):
        return "科技"
    if any(part in path for part in ("/business", "/economy", "/economics")):
        return "经济"
    if fallback != "政治":
        return fallback
    if re.search(r'\b(world cup|championship|olympic|grand slam|nba|fifa|world series|football|basketball|tennis|marathon)\b', text):
        return "体育"
    if re.search(r'\b(inflation|interest rate|gdp|economy|trade deal|earnings|tariffs|unemployment|stock market)\b', text):
        return "经济"
    if re.search(r'\b(artificial intelligence|semiconductor|cyberattack|ai model|robotics|quantum|technology)\b', text):
        return "科技"
    return fallback


def collect_news(hours: int = 24, limit_per_source: int = 40) -> list[NewsCandidate]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    with ThreadPoolExecutor(max_workers=8) as executor:
        batches = list(executor.map(lambda feed: _collect_feed(feed, since, now, limit_per_source), RSS_FEEDS))
    candidates = [item for batch in batches for item in batch]
    candidates.extend(_collect_fashionunited(since, now))
    result = [item for item in candidates if since <= item.published_at <= now]
    print("Fresh feed candidates:", {c: sum(x.category == c for x in result) for c in CATEGORIES})
    return result


def _fetch_rss_entries(url: str) -> list:
    try:
        response = requests.get(url, headers={"User-Agent": "DailyNewsBrief/2.0 (personal RSS reader)"}, timeout=15)
        response.raise_for_status()
        return list(feedparser.parse(response.content).entries)
    except (requests.RequestException, ValueError):
        return []


def _collect_feed(feed, since, now, limit):
    category, source, url = feed
    items = []
    # Feeds can be in editorial rather than date order; inspect before truncating.
    for entry in _fetch_rss_entries(url):
        published = _parse_feed_datetime(entry.get("published") or entry.get("updated") or entry.get("dc_date"))
        if not published or not since <= published <= now:
            continue
        title = _clean_text(entry.get("title", ""))
        link = entry.get("link", "")
        items.append(NewsCandidate(
            title=title, url=link, source=source, published_at=published,
            summary=_clean_text(entry.get("summary", "")),
            category=classify_category(link, title, category or "政治"),
        ))
    return sorted(items, key=lambda x: x.published_at, reverse=True)[:limit]


class _FashionLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            url = urljoin("https://fashionunited.com", href)
            if re.match(r'https://fashionunited.com/news/(fashion|people)/[^/]+/\d+', url):
                self.links.append(url)


def _collect_fashionunited(since, now):
    # The publisher exposes dated article links in its public section pages.
    links = []
    for section in ("fashion", "people"):
        try:
            response = requests.get(f"https://fashionunited.com/news/{section}", timeout=12)
            response.raise_for_status()
            page = _FashionLinks()
            page.feed(response.text)
            links.extend(page.links)
        except requests.RequestException:
            continue
    links = list(dict.fromkeys(links))[:24]

    def collect(url):
        from .article_access import HEADERS, inspect_public_article, json_objects
        try:
            response = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=False)
            if response.status_code != 200:
                return None
            readable, page = inspect_public_article(response.text)
            if not readable:
                return None
            articles = [obj for obj in json_objects(page.jsonld) if any(
                kind in str(obj.get("@type", "")) for kind in ("NewsArticle", "Article")
            ) and obj.get("datePublished")]
            if not articles:
                return None
            article = articles[0]
            published = _parse_feed_datetime(article["datePublished"])
            if not published or not since <= published <= now:
                return None
            return NewsCandidate(
                title=str(article.get("headline") or page.metadata.get("og:title", "")),
                url=url, source="FashionUnited", published_at=published,
                summary=str(article.get("description") or page.metadata.get("og:description", "")),
                category="时尚", access_checked_at=datetime.now(timezone.utc).isoformat(),
            )
        except (requests.RequestException, ValueError, TypeError):
            return None
    with ThreadPoolExecutor(max_workers=6) as executor:
        return [item for item in executor.map(collect, links) if item is not None]


def _is_major_fed_release(title: str) -> bool:
    text = title.lower()
    if "minutes" in text:
        return False
    return any(
        term in text
        for term in (
            "fomc statement",
            "monetary policy report",
            "emergency",
            "liquidity facility",
            "federal funds rate",
            "discount rate",
        )
    )


def _is_major_bls_release(release_name: str, title: str) -> bool:
    text = title.lower()
    if release_name == "Employment Situation":
        payroll_change = _extract_number(
            text,
            r"payroll employment .*? by ([\d,]+)",
        )
        return (
            payroll_change is not None
            and payroll_change >= 200_000
        ) or any(
            term in text
            for term in (
                "payroll employment declines",
                "payroll employment decreases",
                "unemployment rate rises",
                "unemployment rate increases",
            )
        )

    monthly_change = _extract_number(
        text,
        r"(?:rises|increases|advances|falls|declines|decreases) ([\d.]+)%",
    )
    if monthly_change is None:
        return False
    if any(term in text for term in ("falls", "declines", "decreases")):
        return True
    threshold = 0.4 if release_name == "Consumer Price Index" else 0.5
    return monthly_change >= threshold


def _extract_number(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _parse_feed_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_gdelt_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _clean_text(value: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(value)
    text = unescape(" ".join(parser.parts))
    return " ".join(text.replace("\n", " ").split())


def _split_google_title(title: str) -> tuple[str, str]:
    if " - " not in title:
        return title, "Google News"
    story_title, source = title.rsplit(" - ", 1)
    return story_title.strip() or title, source.strip() or "Google News"


def candidates_to_dicts(candidates):
    return [{**asdict(item), "published_at": item.published_at.isoformat()} for item in candidates]
