"""Reader preferences: keep five sections balanced, with free original links."""

CATEGORIES = ("政治", "经济", "体育", "科技", "时尚")
TARGET_PER_CATEGORY = 2
MAX_PER_CATEGORY = 3
MAX_STORIES = 10
MIN_IMPORTANCE = 6
AI_CANDIDATE_LIMIT = 75

# Direct publisher feeds; no opaque Google News links or paid news aggregators.
RSS_FEEDS = (
    ("政治", "The Guardian", "https://www.theguardian.com/world/rss"),
    ("经济", "The Guardian", "https://www.theguardian.com/business/rss"),
    ("体育", "The Guardian", "https://www.theguardian.com/sport/rss"),
    ("科技", "The Guardian", "https://www.theguardian.com/technology/rss"),
    ("时尚", "The Guardian", "https://www.theguardian.com/fashion/rss"),
    ("", "Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("", "DW", "https://rss.dw.com/rdf/rss-en-all"),
    ("时尚", "Fashionista", "https://fashionista.com/.rss/full/"),
    ("科技", "MIT News", "https://news.mit.edu/rss/topic/artificial-intelligence2"),
)

ALLOWED_DOMAINS = (
    "theguardian.com", "aljazeera.com", "dw.com", "fashionista.com",
    "fashionunited.com", "news.mit.edu", "federalreserve.gov", "bls.gov",
)
BLOCKED_DOMAINS = (
    "bloomberg.com", "wsj.com", "ft.com", "nytimes.com", "reuters.com",
    "washingtonpost.com", "scmp.com", "theinformation.com", "businessoffashion.com",
    "wwd.com", "vogue.com", "voguebusiness.com", "forbes.com", "economist.com",
)
BLOCKED_SOURCE_NAMES = (
    "bloomberg", "彭博", "wall street journal", "financial times", "纽约时报",
    "new york times", "south china morning post", "scmp", "forbes", "wsj", "wwd",
)


def host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)
