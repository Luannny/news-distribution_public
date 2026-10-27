# Daily Chinese General News Brief

[Chinese setup guide](README.zh-CN.md)

Politics, economy, sports, technology and fashion receive equal coverage. Target about ten stories from the last 24 hours, normally two per section, never more than three in one section or ten in total. Reject filler and duplicate events. Preserve dated VIX as a short supplement after the news.

Uses direct publisher feeds and public FashionUnited section pages. Excludes configured paywall publishers (including Bloomberg), opaque Google News links, inaccessible pages and explicit subscription/login gates. Access checks never log in or bypass paywalls. Availability may change later or differ by region.

Gemini ranks a balanced candidate pool; code enforces section quotas. Chinese summaries retain source attribution and labelled inference/observation.

Required GitHub Secrets: GEMINI_API_KEY, EMAIL_USER, EMAIL_PASSWORD, EMAIL_TO. No OpenAI key is read by the daily workflow. Schedule remains 00:00 UTC / 08:00 Asia/Shanghai; delivery may be delayed.

Manual runs preview without sending by default. Read the Chinese preview on the run Summary page, or download the daily-news-preview artifact (HTML, Markdown and a JSON source/access audit). Locally install requirements and use python -m src.main --dry-run. Never commit .env or credentials.
