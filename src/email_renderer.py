from __future__ import annotations

from datetime import date
from html import escape
from urllib.parse import urlparse

from .summarizer import BriefContent
from .vix import VixSnapshot


def render_email_html(brief_date: date, vix: VixSnapshot, content: BriefContent) -> str:
    vix_value = f"{vix.value:.2f}" if vix.value is not None else "N/A"
    vix_data_note = (
        f'<p style="font-size:13px;line-height:1.6;margin:8px 0 0;color:#6b7280;">数据日期：{escape(vix.as_of)} · 来源：{escape(vix.source)}</p>'
        if vix.as_of else ""
    )
    stories_html = "\n".join(
        _render_story(index, story) for index, story in enumerate(content.stories, start=1)
    )
    if not stories_html:
        stories_html = """
    <p style="font-size:16px;line-height:1.7;margin:0;color:#374151;">今日没有达到重要性门槛的新闻。</p>"""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>每日重要新闻简报 - {brief_date.isoformat()}</title>
</head>
<body style="margin:0;background:#eef1f5;color:#111827;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;">
  <main style="max-width:720px;margin:0 auto;padding:18px;background:#ffffff;">
    <header style="padding:8px 0 18px;border-bottom:3px solid #111827;">
      <h1 style="font-size:30px;line-height:1.18;margin:0 0 8px;font-weight:800;letter-spacing:0;">每日重要新闻简报</h1>
      <p style="font-size:15px;margin:0;color:#4b5563;">日期：{brief_date.isoformat()}</p>
    </header>

    <section style="padding:22px 0 18px;border-bottom:1px solid #d1d5db;">
      <h2 style="font-size:21px;line-height:1.3;margin:0 0 12px;font-weight:750;">市场温度</h2>
      <p style="font-size:20px;line-height:1.35;margin:0 0 8px;"><strong>VIX:</strong> {vix_value}</p>
      <p style="font-size:16px;line-height:1.7;margin:0;color:#374151;">{escape(vix.interpretation)}</p>
      {vix_data_note}
    </section>

    <section style="padding:22px 0 18px;border-bottom:1px solid #d1d5db;">
      <h2 style="font-size:21px;line-height:1.3;margin:0 0 12px;font-weight:750;">今日摘要</h2>
      <p style="font-size:16px;line-height:1.75;margin:0;color:#1f2937;">{escape(content.trend_summary)}</p>
    </section>

    <section style="padding:24px 0 4px;">
      <h2 style="font-size:23px;line-height:1.25;margin:0 0 16px;font-weight:800;">重要新闻</h2>
    {stories_html}
    </section>

    <footer style="border-top:1px solid #d1d5db;margin:26px 0 0;padding:16px 0 4px;">
      <p style="font-size:13px;line-height:1.6;color:#6b7280;margin:0;">本简报由 AI 自动生成，仅包含过去24小时内的重要新闻。</p>
    </footer>
  </main>
</body>
</html>"""


def render_subject(brief_date: date) -> str:
    return f"每日重要新闻简报 - {brief_date.isoformat()}"


def _render_story(index: int, story) -> str:
    source_label = escape(story.source or _source_label(story.url))
    link_label = escape(_source_label(story.url))
    return f"""
      <article style="margin:0 0 18px;padding:18px 16px;border:1px solid #d1d5db;border-left:5px solid #2563eb;background:#fbfcfe;border-radius:6px;">
        <p style="font-size:13px;line-height:1.4;margin:0 0 8px;color:#6b7280;font-weight:700;text-transform:uppercase;">新闻 {index} / 重要性 {story.importance_score}/10</p>
        <h3 style="font-size:20px;line-height:1.35;margin:0 0 10px;font-weight:780;color:#111827;">{index}. {escape(story.title)}</h3>
        <p style="font-size:14px;line-height:1.5;margin:0 0 14px;color:#6b7280;">来源：{source_label}</p>

        <div style="margin:0 0 12px;">
          <p style="font-size:14px;line-height:1.4;margin:0 0 4px;color:#111827;font-weight:700;">发生了什么（来源报道）</p>
          <p style="font-size:16px;line-height:1.72;margin:0;color:#1f2937;">{escape(story.summary)}</p>
        </div>

        <div style="margin:0 0 14px;">
          <p style="font-size:14px;line-height:1.4;margin:0 0 4px;color:#111827;font-weight:700;">为什么重要（分析与观察）</p>
          <p style="font-size:16px;line-height:1.72;margin:0;color:#1f2937;">{escape(story.why_it_matters)}</p>
        </div>

        <p style="font-size:15px;line-height:1.5;margin:0;"><a href="{escape(story.url)}" style="color:#2563eb;text-decoration:none;font-weight:700;">阅读原文（{link_label}）</a></p>
      </article>"""


def _source_label(url: str) -> str:
    host = urlparse(url).netloc.replace("www.", "")
    return host or "原文链接"
