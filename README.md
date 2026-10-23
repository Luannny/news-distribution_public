# Daily Chinese News Brief

See [中文配置说明](README.zh-CN.md) for the Gemini + Gmail setup.

Collects news from the previous 24 hours, uses Gemini to select at most 10 high-signal stories and write a Chinese briefing, includes VIX with its data date and source, and sends via Gmail SMTP.

Required GitHub Secrets: `GEMINI_API_KEY`, `EMAIL_USER`, `EMAIL_PASSWORD`, `EMAIL_TO`. Default model: `gemini-3.5-flash-lite`; optional override: `GEMINI_MODEL`. The daily workflow uses Google's official OpenAI-compatible endpoint and never reads the legacy OpenAI key.

Daily schedule: 00:00 UTC / 08:00 Asia/Shanghai; actual delivery can be delayed. Manual runs preview without sending by default. Download the `daily-news-preview` artifact to review the HTML.

For local use, install requirements, copy `.env.example` to `.env`, fill it privately, then run `python -m src.main --dry-run`. Run `python -m src.main` to send. AI service errors fail the task rather than sending a heuristic substitute. No-key local previews are explicitly marked as tests.

Never commit credentials. Summaries use headlines and snippets, not full articles; inference must be identified, unsupported details omitted. Free-tier access depends on Google account eligibility and quotas; enabling paid billing can incur charges.
