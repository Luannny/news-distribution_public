import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
from openai import OpenAI

from src.ai_client import create_ai_client, get_ai_settings
from src.news_collector import NewsCandidate
from src.vix import VixSnapshot


class AIProviderTests(unittest.TestCase):
    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-google", "OPENAI_API_KEY": "test-old"}, clear=True)
    def test_gemini_default_uses_only_google_key_and_endpoint(self):
        settings = get_ai_settings()
        self.assertEqual(settings.provider, "gemini")
        self.assertEqual(settings.api_key, "test-google")
        self.assertEqual(settings.model, "gemini-3.5-flash-lite")
        self.assertNotIn("test-google", repr(settings))
        client = create_ai_client(settings)
        self.addCleanup(client.close)
        self.assertEqual(str(client.base_url), "https://generativelanguage.googleapis.com/v1beta/openai/")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-old"}, clear=True)
    def test_missing_google_key_never_falls_back_to_openai(self):
        with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
            create_ai_client(get_ai_settings())

    @patch.dict(os.environ, {"AI_PROVIDER": "invalid"}, clear=True)
    def test_unknown_provider_fails(self):
        with self.assertRaises(ValueError):
            get_ai_settings()

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-google", "GEMINI_MODEL": "gemini-custom"}, clear=True)
    def test_explicit_model_override(self):
        self.assertEqual(get_ai_settings().model, "gemini-custom")

    @patch.dict(os.environ, {"REQUIRE_AI": "true", "OPENAI_API_KEY": "test-old"}, clear=True)
    def test_cloud_preview_requires_gemini_key_before_collection(self):
        from src.main import main
        with patch("sys.argv", ["news", "--dry-run"]), patch("src.main.load_dotenv"), patch("src.news_collector.collect_news") as collect:
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                main()
            collect.assert_not_called()

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-google", "OPENAI_API_KEY": "test-old", "REQUIRE_AI": "true"}, clear=True)
    def test_google_ranking_and_chinese_preview_never_send_email(self):
        from src.main import main
        calls = []
        candidate = NewsCandidate(
            title="Nvidia announces new chip production",
            source="The Guardian",
            url="https://www.theguardian.com/technology/2026/oct/27/original-story",
            published_at=datetime.now(timezone.utc),
            summary="Nvidia said production of its new chip has started.",
        )

        def respond(request):
            self.assertEqual(request.url.host, "generativelanguage.googleapis.com")
            self.assertEqual(request.headers["authorization"], "Bearer test-google")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "gemini-3.5-flash-lite")
            calls.append(body)
            if len(calls) == 1:
                content = {"stories": [{"id": 0, "importance_score": 9, "reason": "芯片量产进展"}]}
            else:
                content = {"trend_summary": "芯片供给出现新进展。", "stories": [{
                    "id": 0, "chinese_title": "英伟达宣布新芯片开始量产", "summary": "英伟达表示新芯片已开始量产。",
                    "why_it_matters": "后续观察：实际交付能否满足客户需求。", "url": "https://example.com/invented-link",
                }]}
            return httpx.Response(200, json={"id": "test", "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)}, "finish_reason": "stop"}]})

        def make_client(**kwargs):
            return OpenAI(http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kwargs)

        with tempfile.TemporaryDirectory() as folder:
            preview = Path(folder) / "preview.html"
            with patch("sys.argv", ["news", "--dry-run", "--preview-path", str(preview)]), patch("src.main.load_dotenv"), patch("src.ai_client.OpenAI", side_effect=make_client), patch("src.news_collector.collect_news", return_value=[candidate]), patch("src.article_access.verify_readable_candidates", return_value=[candidate]), patch("src.vix.get_vix_snapshot", return_value=VixSnapshot(None, "测试不提供行情")), patch("src.email_sender.send_email") as send:
                main()
                send.assert_not_called()
            html = preview.read_text(encoding="utf-8")
            self.assertIn("英伟达宣布新芯片开始量产", html)
            self.assertIn(candidate.url, html)
            self.assertNotIn("invented-link", html)
            self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
