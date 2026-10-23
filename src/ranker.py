from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .ai_client import create_ai_client, get_ai_settings
from .news_collector import NewsCandidate


@dataclass(frozen=True)
class RankedStory:
    title: str
    url: str
    source: str
    published_at: str
    importance_score: int
    reason: str
    summary_seed: str = ""


SYSTEM_PROMPT = """You rank news for a high-signal daily Chinese briefing.
Prefer omission over inclusion. Select only genuinely important developments from the last 24 hours.
Prioritize AI and technology, AI-related industries, major global company events, stock markets and business, major macroeconomic events, and exceptionally important global events.
Include China-US or other political developments only when they have a direct and substantial technology, economic, market, trade, or security impact. Do not let routine political coverage dominate the briefing.
For company stories, favor consequential earnings surprises, guidance changes, major products, acquisitions, leadership changes, regulatory actions, production disruptions, or strategic shifts at widely followed companies in any country.
Exclude minor feature updates, technical changelogs, routine announcements, entertainment, sports, and celebrity news unless historically significant.
Exclude stock-picking advice, predictions, listicles, routine market recaps, weekly calendars, and articles whose main purpose is telling readers what to buy.
Require a concrete new event: an announcement, filing, transaction, earnings release, product launch, official data release, or policy decision. A recently published analysis of an ongoing trend is not itself a new event.
Exclude generic industry comparisons, competitiveness commentary, expert forecasts, investment outlooks, and commentary by former officials. Prefer original reporting and official releases over aggregators. Do not select a weak story just to fill a category.
Return strict JSON only."""

OPENAI_CANDIDATE_LIMIT = 50

HIGH_SIGNAL_TERMS = {
    "nvidia": 10,
    "rtx spark": 10,
    "ai pc": 9,
    "personal ai": 8,
    "personal computer": 7,
    "microsoft": 6,
    "openai": 9,
    "anthropic": 8,
    "deepmind": 7,
    "google": 5,
    "meta": 5,
    "xai": 5,
    "artificial intelligence": 8,
    "agentic ai": 8,
    "ai agent": 8,
    "semiconductor": 8,
    "chip": 7,
    "gpu": 7,
    "accelerator": 6,
    "hbm": 6,
    "tsmc": 7,
    "asml": 7,
    "arm": 5,
    "intel": 5,
    "amd": 5,
    "apple": 6,
    "amazon": 5,
    "berkshire": 5,
    "boeing": 5,
    "china": 4,
    "costco": 4,
    "consumer price index": 7,
    "cpi": 7,
    "earnings": 7,
    "entity list": 6,
    "export control": 6,
    "guidance": 7,
    "ipo": 4,
    "market cap": 6,
    "markets": 5,
    "net income": 6,
    "profit": 6,
    "revenue": 6,
    "salesforce": 4,
    "sanction": 6,
    "stock market": 6,
    "stocks": 5,
    "tariff": 6,
    "tesla": 6,
    "united states": 4,
    "u.s.": 4,
    "us-china": 6,
    "china-us": 6,
    "huawei": 7,
    "alibaba": 6,
    "tencent": 6,
    "byd": 6,
    "pdd": 5,
    "jd.com": 5,
    "xiaomi": 5,
    "federal reserve": 8,
    "fed": 6,
    "fomc": 8,
    "inflation": 7,
    "interest rate": 7,
    "rate cut": 8,
    "rate hike": 8,
    "treasury": 6,
    "gdp": 6,
    "recession": 7,
    "payroll employment": 7,
    "producer price index": 6,
    "ppi": 6,
    "unemployment rate": 7,
}

MAJOR_EVENT_TERMS = {
    "launch": 5,
    "unveil": 5,
    "announce": 4,
    "partnership": 4,
    "acquisition": 7,
    "buyback": 6,
    "dividend": 5,
    "merger": 7,
    "ipo": 4,
    "earnings": 7,
    "guidance": 7,
    "forecast": 4,
    "misses estimates": 6,
    "raises forecast": 6,
    "beats estimates": 6,
    "shares rise": 5,
    "shares fall": 5,
    "stock jumps": 5,
    "stock falls": 5,
    "ban": 4,
    "probe": 4,
    "investigation": 5,
    "lawsuit": 4,
    "regulation": 5,
    "approval": 4,
    "deal": 4,
    "investment": 4,
}

LOW_SIGNAL_TERMS = {
    "best strategy": -7,
    "buckle up": -4,
    "column": -4,
    "dow jones futures": -6,
    "opinion": -5,
    "prediction": -7,
    "review": -4,
    "reviewed": -4,
    "rumor": -4,
    "rumour": -4,
    "recap": -4,
    "reads": -3,
    "live updates": -4,
    "watch": -3,
    "how to": -5,
    "here's what": -4,
    "what to know": -3,
    "newsletter": -3,
    "ask us": -5,
    "avoid the": -4,
    "available on": -4,
    "mythmaking": -4,
    "poised to": -4,
    "q&a": -5,
    "severe thunderstorm": -8,
    "show": -3,
    "stocks jump": -3,
    "stocks poised": -7,
    "stock will soar": -8,
    "stocks to buy": -8,
    "stock to buy": -8,
    "stock market today": -7,
    "3 stocks": -6,
    "transcript": -6,
    "what latest data": -3,
    "week in focus": -7,
    "what to do": -6,
    "is he right": -6,
}

SOURCE_WEIGHTS = {
    "reuters.com": 5,
    "apnews.com": 5,
    "bloomberg.com": 5,
    "wsj.com": 5,
    "ft.com": 5,
    "cnbc.com": 4,
    "axios.com": 4,
    "theinformation.com": 4,
    "nvidianews.nvidia.com": 5,
    "investor.nvidia.com": 4,
    "scmp.com": 4,
    "nikkei.com": 4,
    "caixin.com": 4,
    "aol.com": -5,
    "cryptobriefing.com": -5,
    "econotimes.com": -4,
    "fool.com": -7,
    "seekingalpha.com": -5,
    "techtimes.com": -4,
}

SOURCE_NAME_WEIGHTS = {
    "reuters": 5,
    "associated press": 5,
    "ap": 5,
    "bloomberg": 5,
    "bloomberg.com": 5,
    "wall street journal": 5,
    "wsj": 5,
    "financial times": 5,
    "ft": 5,
    "cnbc": 4,
    "axios": 4,
    "the information": 4,
    "nvidia newsroom": 5,
    "nvidia": 4,
    "south china morning post": 4,
    "nikkei asia": 4,
    "caixin": 4,
    "binance": -5,
    "bitget": -5,
    "aol.com": -5,
    "crypto briefing": -5,
    "investor's business daily": -4,
    "seeking alpha": -5,
    "the motley fool": -6,
    "federal reserve": 6,
    "u.s. bureau of labor statistics": 6,
}

MAJOR_COMPANY_TERMS = {
    "abb",
    "abbvie",
    "adobe",
    "adidas",
    "aia",
    "airbus",
    "airbnb",
    "alibaba",
    "alphabet",
    "amgen",
    "analog devices",
    "amazon",
    "amd",
    "american express",
    "ant group",
    "apple",
    "applied materials",
    "asml",
    "astrazeneca",
    "at&t",
    "axa",
    "bank of america",
    "barclays",
    "baidu",
    "bayer",
    "berkshire",
    "bhp",
    "blackrock",
    "blackstone",
    "boeing",
    "booking holdings",
    "bp",
    "broadcom",
    "bristol myers",
    "byd",
    "cadence",
    "carrefour",
    "catl",
    "caterpillar",
    "chevron",
    "china mobile",
    "china telecom",
    "china unicom",
    "cisco",
    "citigroup",
    "coca-cola",
    "comcast",
    "conocophillips",
    "costco",
    "cvs",
    "danaher",
    "deere",
    "deutsche bank",
    "disney",
    "eli lilly",
    "equinor",
    "estee lauder",
    "exxon",
    "fedex",
    "ferrari",
    "ford",
    "foxconn",
    "freeport-mcmoran",
    "general electric",
    "general motors",
    "gilead",
    "glencore",
    "goldman sachs",
    "gsk",
    "h&m",
    "google",
    "hdfc bank",
    "hermes",
    "hitachi",
    "home depot",
    "honda",
    "hsbc",
    "huawei",
    "hyundai",
    "ibm",
    "icbc",
    "inditex",
    "intel",
    "intuit",
    "j&j",
    "jd.com",
    "john deere",
    "johnson & johnson",
    "jpmorgan",
    "kkr",
    "kia",
    "kla",
    "kweichow moutai",
    "l'oreal",
    "lam research",
    "li auto",
    "lockheed martin",
    "lowe's",
    "lululemon",
    "lvmh",
    "mastercard",
    "mcdonald's",
    "medtronic",
    "meituan",
    "mercedes-benz",
    "merck",
    "meta",
    "micron",
    "microsoft",
    "mitsubishi",
    "moderna",
    "morgan stanley",
    "mufg",
    "nestle",
    "netflix",
    "netease",
    "nio",
    "nintendo",
    "novo nordisk",
    "novartis",
    "nxp",
    "nvidia",
    "oracle",
    "palantir",
    "paramount",
    "paypal",
    "pepsico",
    "petrochina",
    "pfizer",
    "pinduoduo",
    "ping an",
    "procter & gamble",
    "qualcomm",
    "regeneron",
    "reliance",
    "rio tinto",
    "rolls-royce",
    "roche",
    "rtx",
    "samsung",
    "santander",
    "sanofi",
    "sap se",
    "saudi aramco",
    "schneider electric",
    "shell plc",
    "siemens",
    "shopify",
    "smfg",
    "smic",
    "snowflake",
    "spotify",
    "softbank",
    "sony",
    "starbucks",
    "stellantis",
    "stripe inc",
    "synopsys",
    "taiwan semiconductor",
    "target corp",
    "target corporation",
    "tencent",
    "tesla",
    "texas instruments",
    "thermo fisher",
    "t-mobile",
    "toyota",
    "trip.com",
    "tsmc",
    "uber",
    "ubs",
    "unilever",
    "union pacific",
    "unitedhealth",
    "ups",
    "vale",
    "verizon",
    "visa inc",
    "volkswagen",
    "walmart",
    "walgreens",
    "warner bros discovery",
    "wells fargo",
    "xiaomi",
    "xpeng",
}

BUSINESS_EVENT_TERMS = {
    "acquisition",
    "antitrust",
    "bankruptcy",
    "beats estimates",
    "buyback",
    "ceo",
    "chief executive",
    "contract",
    "cuts forecast",
    "cyberattack",
    "data breach",
    "debt crisis",
    "deliveries",
    "delivers",
    "dividend",
    "divestiture",
    "drug approval",
    "earnings",
    "factory",
    "falls after",
    "forecast",
    "guidance",
    "ipo",
    "job cuts",
    "lawsuit",
    "layoff",
    "merger",
    "misses estimates",
    "outlook",
    "plant",
    "profit",
    "production halt",
    "raises forecast",
    "recall",
    "regulatory approval",
    "restructuring",
    "revenue",
    "sales",
    "shares fall",
    "shares rise",
    "shipment",
    "spin off",
    "stock falls",
    "stock jumps",
    "strike",
    "supply chain",
    "trial results",
}


def rank_candidates(
    candidates: list[NewsCandidate],
    max_stories: int = 10,
    model: str | None = None,
) -> list[RankedStory]:
    if not candidates:
        return []

    settings = get_ai_settings()
    if not settings.api_key:
        return _heuristic_rank(candidates, max_stories)

    client = create_ai_client(settings)
    selected_model = model or settings.model
    prioritized_candidates = prioritize_candidates(candidates, limit=OPENAI_CANDIDATE_LIMIT)
    compact_candidates = [
        {
            "id": index,
            "title": item.title,
            "source": item.source,
            "published_at": item.published_at.isoformat(),
            "url": item.url,
            "snippet": item.summary[:240],
        }
        for index, item in enumerate(prioritized_candidates)
    ]
    response = client.chat.completions.create(
        model=selected_model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Score and rank these candidate stories. Return JSON with key 'stories'. "
                    "Each story must include id, importance_score from 1 to 10, and reason in Simplified Chinese. "
                    f"Return at most {max_stories} stories and omit weak stories.\n\n"
                    f"{json.dumps(compact_candidates, ensure_ascii=False)}"
                ),
            },
        ],
    )
    payload = json.loads(response.choices[0].message.content or "{}")
    stories = payload.get("stories", [])
    ranked: list[RankedStory] = []
    for story in stories:
        try:
            candidate_id = int(story["id"])
            if candidate_id < 0:
                continue
            candidate = prioritized_candidates[candidate_id]
            score = max(1, min(10, int(story.get("importance_score", 1))))
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        ranked.append(
            RankedStory(
                title=candidate.title,
                url=candidate.url,
                source=candidate.source,
                published_at=candidate.published_at.isoformat(),
                importance_score=score,
                reason=str(story.get("reason", "")),
                summary_seed=candidate.summary,
            )
        )

    return _diversify_ranked_stories(ranked, max_stories=max_stories)


def prioritize_candidates(
    candidates: list[NewsCandidate],
    limit: int = OPENAI_CANDIDATE_LIMIT,
) -> list[NewsCandidate]:
    return sorted(candidates, key=_priority_sort_key, reverse=True)[:limit]


def _priority_sort_key(candidate: NewsCandidate) -> tuple[int, str]:
    return (_priority_score(candidate), candidate.published_at.isoformat())


def _priority_score(candidate: NewsCandidate) -> int:
    text = f"{candidate.title} {candidate.summary}".lower()
    score = 0
    for term, weight in HIGH_SIGNAL_TERMS.items():
        if _contains_term(text, term):
            score += weight
    for term, weight in MAJOR_EVENT_TERMS.items():
        if _contains_term(text, term):
            score += weight
    for term, weight in LOW_SIGNAL_TERMS.items():
        if _contains_term(text, term):
            score += weight

    host = urlparse(candidate.url).netloc.lower().replace("www.", "")
    score += SOURCE_WEIGHTS.get(host, 0)
    source = candidate.source.lower()
    score += SOURCE_NAME_WEIGHTS.get(source, 0)
    if _has_major_company_business_event(text):
        score += 10
    return score


def _contains_term(text: str, term: str) -> bool:
    if not term.isascii():
        return term in text
    pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def _has_major_company_business_event(text: str) -> bool:
    has_company = any(_contains_term(text, company) for company in MAJOR_COMPANY_TERMS)
    if not has_company:
        return False
    return any(_contains_term(text, event) for event in BUSINESS_EVENT_TERMS)


def _diversify_ranked_stories(
    stories: list[RankedStory],
    max_stories: int,
) -> list[RankedStory]:
    selected: list[RankedStory] = []
    seen_topics: list[set[str]] = []
    for story in sorted(stories, key=lambda item: item.importance_score, reverse=True):
        topic_terms = _topic_terms(story.title)
        if topic_terms and any(_topic_overlap(topic_terms, existing) for existing in seen_topics):
            continue
        selected.append(story)
        seen_topics.append(topic_terms)
        if len(selected) >= max_stories:
            break
    return selected


def _topic_terms(title: str) -> set[str]:
    text = title.lower()
    signature = _topic_signature(text)
    if signature:
        return {signature}
    terms = {
        term
        for term in HIGH_SIGNAL_TERMS
        if HIGH_SIGNAL_TERMS[term] >= 6 and _contains_term(text, term)
    }
    normalized_words = re.findall(r"[a-z0-9]+", text)
    terms.update(
        word
        for word in normalized_words
        if len(word) >= 5 and word not in {"about", "after", "first", "latest", "major"}
    )
    return terms


def _topic_signature(text: str) -> str | None:
    if (
        ("fomc" in text or "federal reserve" in text or _contains_term(text, "fed"))
        and any(term in text for term in ("statement", "interest rate", "rates", "rate decision"))
    ):
        return "fomc-policy-decision"
    if "consumer price index" in text or _contains_term(text, "cpi"):
        return "us-cpi-release"
    if "producer price index" in text or _contains_term(text, "ppi"):
        return "us-ppi-release"
    if "payroll employment" in text or "jobs report" in text:
        return "us-employment-report"
    if (
        ("china" in text or "chinese" in text)
        and ("chip" in text or "semiconductor" in text or "nvidia" in text)
        and (
            "ban" in text
            or "export" in text
            or "shipment" in text
            or "shipments" in text
            or "control" in text
            or "loophole" in text
            or "restrict" in text
            or "limit" in text
            or "access" in text
            or "halt" in text
        )
    ):
        return "china-ai-chip-export-controls"
    if "nvidia" in text and ("personal computer" in text or "pc" in text or "ai agent" in text):
        return "nvidia-ai-pc"
    if "nvidia" in text and "tsmc" in text and ("fab" in text or "semiconductor" in text):
        return "nvidia-tsmc-ai-fabs"
    return None


def _topic_overlap(left: set[str], right: set[str]) -> bool:
    if len(left) == 1 and len(right) == 1 and next(iter(left)) == next(iter(right)):
        return True
    overlap = left & right
    if len(overlap) >= 2:
        return True
    return bool(overlap & {"nvidia", "huawei", "byd", "semiconductor", "chip", "gpu", "tariff", "sanction"})


def _heuristic_rank(candidates: list[NewsCandidate], max_stories: int) -> list[RankedStory]:
    ranked: list[RankedStory] = []
    for candidate in prioritize_candidates(candidates):
        score = 4 + _priority_score(candidate)
        if score < 5:
            continue
        ranked.append(
            RankedStory(
                title=candidate.title,
                url=candidate.url,
                source=candidate.source,
                published_at=candidate.published_at.isoformat(),
                importance_score=min(score, 8),
                reason="无 AI 密钥测试模式，仅按关键词估算重要性，尚未经过 AI 筛选。",
                summary_seed=candidate.summary,
            )
        )
    return _diversify_ranked_stories(ranked, max_stories=max_stories)
