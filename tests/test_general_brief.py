import json
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from src.article_access import allowed_source, inspect_public_article, verify_candidate
from src.deduplicator import filter_and_deduplicate
from src.news_collector import NewsCandidate, _collect_feed, classify_category
from src.news_policy import CATEGORIES
from src.ranker import RankedStory, _diversify_ranked_stories, prioritize_candidates


def candidate(category, index=0):
    return NewsCandidate(
        title=("National team wins championship final" if category == "体育" else "Fashion designers adopt recycled fabric standard") + str(index),
        url=f"https://www.theguardian.com/{category}/{index}", source="The Guardian",
        published_at=datetime.now(timezone.utc), category=category,
    )


def story(category, index, score=8, title=None):
    return RankedStory(
        title=title or f"{category} different event {index}",
        url=f"https://www.theguardian.com/{category}/{index}", source="The Guardian",
        published_at=datetime.now(timezone.utc).isoformat(), importance_score=score,
        reason="重大进展", category=category,
    )


class BalancedSectionsTests(unittest.TestCase):
    def test_sports_and_fashion_survive_without_finance_keywords(self):
        sports = candidate("体育")
        fashion = candidate("时尚")
        self.assertEqual(len(filter_and_deduplicate([sports, fashion])), 2)

    def test_finance_flood_cannot_take_over_model_input(self):
        candidates = [candidate("经济", i) for i in range(200)]
        candidates += [candidate(c, i) for c in CATEGORIES if c != "经济" for i in range(20)]
        counts = Counter(x.category for x in prioritize_candidates(candidates, limit=75))
        self.assertEqual(counts, {c: 15 for c in CATEGORIES})

    def test_ten_stories_cover_five_fields_even_when_finance_scores_higher(self):
        titles = {
            "政治": ["Parliament approves nationwide voting reform", "Governments sign border ceasefire treaty"],
            "经济": ["Central bank changes benchmark interest rates", "Manufacturers receive new export tariffs"],
            "体育": ["Runner breaks long standing marathon record", "National team wins world championship final"],
            "科技": ["Researchers develop new quantum processor", "Messaging platform fixes major security breach"],
            "时尚": ["Luxury house appoints a new creative director", "Textile makers introduce recycled fabric standard"],
        }
        items = [story(c, i, 10 if c == "经济" else 7, title=title) for c, names in titles.items() for i, title in enumerate(names)]
        selected = _diversify_ranked_stories(items, 10)
        self.assertEqual(Counter(s.category for s in selected), {c: 2 for c in CATEGORIES})

    def test_missing_section_never_filled_by_unlimited_finance(self):
        items = [story("经济", i, title=f"经济不同主体{'ABCDEF'[i]}事件") for i in range(6)]
        selected = _diversify_ranked_stories(items, 10)
        self.assertLessEqual(len(selected), 3)

    def test_same_event_cannot_fill_two_sections(self):
        a = story("经济", 1, title="Large company completes historic merger")
        b = story("科技", 1, title="Large company completes historic merger")
        self.assertEqual(len(_diversify_ranked_stories([a, b], 10)), 1)

    def test_low_quality_stories_do_not_fill_quotas(self):
        self.assertEqual(_diversify_ranked_stories([story("体育", 1, score=3)], 10), [])

    def test_feed_category_is_corrected_for_cross_posted_technology_article(self):
        self.assertEqual(classify_category("https://www.theguardian.com/technology/2026/oct/27/ai", "AI announcement", "经济"), "科技")


class FreeArticleTests(unittest.TestCase):
    def test_paid_and_opaque_sources_are_rejected(self):
        for url in ("https://www.bloomberg.com/news/article", "https://markets.bloomberg.com/article", "https://www.ft.com/content/test", "https://news.google.com/rss/articles/encoded"):
            self.assertFalse(allowed_source(url))
        self.assertFalse(allowed_source("https://www.theguardian.com/world/story", "Bloomberg"))
        self.assertFalse(allowed_source("https://theguardian.com.example.org/story"))

    def test_jsonld_subscription_flag_rejects_even_if_html_contains_long_teaser(self):
        text = '<p>' + 'A long article excerpt. ' * 100 + '</p>'
        for flag in (False, "false"):
            html = text + '<script type="application/ld+json">' + json.dumps({"@type": "NewsArticle", "isAccessibleForFree": flag}) + '</script>'
            self.assertFalse(inspect_public_article(html)[0])

    def test_donation_banner_does_not_reject_a_free_article(self):
        html = '<p>Support independent journalism with a voluntary donation.</p><p>' + 'Substantial publicly readable article text. ' * 35 + '</p>'
        self.assertTrue(inspect_public_article(html)[0])

    def test_explicit_login_or_subscription_gate_is_rejected(self):
        html = '<p>' + 'Substantial introductory text. ' * 40 + '</p><p>Subscribe to continue reading this article in full.</p>'
        self.assertFalse(inspect_public_article(html)[0])

    @patch("src.article_access.requests.get")
    def test_redirect_to_paid_site_is_not_followed(self, get):
        get.return_value = Mock(status_code=302, headers={"Location": "https://www.bloomberg.com/news/test"})
        self.assertIsNone(verify_candidate(candidate("经济")))
        self.assertEqual(get.call_count, 1)

    @patch("src.article_access.requests.get")
    def test_unavailable_article_is_excluded(self, get):
        get.return_value = Mock(status_code=403, headers={"Content-Type": "text/html"})
        self.assertIsNone(verify_candidate(candidate("体育")))


class FreshnessTests(unittest.TestCase):
    @patch("src.news_collector._fetch_rss_entries")
    def test_old_and_future_items_cannot_fill_daily_quota(self, entries):
        now = datetime.now(timezone.utc)
        entries.return_value = [{"title": "Fresh sports result", "link": "https://www.theguardian.com/sport/fresh", "published": (now-timedelta(hours=1)).isoformat()}, {"title": "Old result", "link": "https://www.theguardian.com/sport/old", "published": (now-timedelta(days=2)).isoformat(), "updated": now.isoformat()}, {"title": "Future result", "link": "https://www.theguardian.com/sport/future", "published": (now+timedelta(hours=1)).isoformat()}]
        items = _collect_feed(("体育", "The Guardian", "feed"), now-timedelta(hours=24), now, 50)
        self.assertEqual([x.title for x in items], ["Fresh sports result"])


if __name__ == "__main__":
    unittest.main()
