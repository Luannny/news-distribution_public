from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and send a daily Chinese news briefing.")
    parser.add_argument("--dry-run", action="store_true", help="Generate a local HTML preview without sending email.")
    parser.add_argument("--preview-path", default="daily_news_preview.html", help="Path for dry-run HTML preview.")
    parser.add_argument("--hours", type=int, default=24, help="Lookback window in hours.")
    args = parser.parse_args()

    load_dotenv()
    from .ai_client import get_ai_settings

    settings = get_ai_settings()
    if not args.dry_run or os.getenv("REQUIRE_AI", "").lower() == "true":
        settings.require_key()
    print(f"AI provider: {settings.provider}; model: {settings.model}; key configured: {bool(settings.api_key)}")

    from .deduplicator import filter_and_deduplicate
    from .email_renderer import render_email_html, render_subject
    from .email_sender import send_email
    from .news_collector import collect_news
    from .ranker import rank_candidates
    from .summarizer import summarize_ranked_stories
    from .vix import get_vix_snapshot

    today = datetime.now().date()
    candidates = collect_news(hours=args.hours)
    filtered = filter_and_deduplicate(candidates)
    ranked = rank_candidates(filtered, max_stories=10)
    brief = summarize_ranked_stories(ranked)
    vix = get_vix_snapshot()
    subject = render_subject(today)
    html = render_email_html(today, vix, brief)

    if args.dry_run:
        preview_path = Path(args.preview_path)
        preview_path.write_text(html, encoding="utf-8")
        print(f"Dry run complete: {preview_path.resolve()}")
        print(f"Subject: {subject}")
        print(f"Candidates collected: {len(candidates)}")
        print(f"Candidates after filtering/deduplication: {len(filtered)}")
        print(f"Stories selected: {len(brief.stories)}")
        return

    send_email(subject, html)
    print(f"Sent: {subject}")


if __name__ == "__main__":
    main()
