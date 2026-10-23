from __future__ import annotations

import json
from dataclasses import dataclass

from .ai_client import create_ai_client, get_ai_settings
from .ranker import RankedStory


@dataclass(frozen=True)
class BriefStory:
    title: str
    url: str
    source: str
    importance_score: int
    summary: str
    why_it_matters: str


@dataclass(frozen=True)
class BriefContent:
    trend_summary: str
    stories: list[BriefStory]


SYSTEM_PROMPT = """你为一位时间有限、但希望真正理解事件的读者撰写高信息密度中文新闻简报。
所有面向读者的字段必须使用自然、准确的简体中文。

写作规则：
1. 先说具体事实，再做影响判断。保留输入中的公司、人名、数字、时间和政策动作。
2. 不要用空泛句子凑字数。避免“影响全球格局”“推动行业发展”“引发广泛关注”“显示出重要性”等没有具体对象和机制的表述。
3. summary 与 why_it_matters 不得重复。summary 回答“发生了什么”；why_it_matters 回答“影响谁、通过什么路径、接下来观察什么”。
4. 如果 evidence_level 为 headline_only，summary 只能写一句基于标题的事实，不得补充输入中没有的细节。
5. 可以做合理推断，但必须使用“若……则……”或“后续关键看……”明确标识，并紧扣输入事实。
6. 不得添加输入材料无法支持的数字、背景、因果关系或市场反应。
7. 来源标题或片段中的观点、预测和比较判断，必须归因于该来源或发言者，不能改写为已获证实的事实。前官员的观点不能写成现任政策制定者已采取的行动。
8. why_it_matters 是分析或后续观察，必须以“推测：若……”或“后续观察：”开头。不要使用“这表明……正在……”“这将……”引入材料未证实的断言。
9. trend_summary 只能概括本次新闻证据；如不足以支持共同趋势，就写“本次新闻主题分散，暂不归纳共同趋势。”，不得补充背景或预测。
10. 返回严格 JSON，不要输出 Markdown。"""


def summarize_ranked_stories(
    stories: list[RankedStory],
    model: str | None = None,
) -> BriefContent:
    if not stories:
        return BriefContent(trend_summary="过去24小时内未筛选出足够重要且可靠的新闻。", stories=[])

    settings = get_ai_settings()
    if not settings.api_key:
        return _heuristic_summarize(stories)

    client = create_ai_client(settings)
    selected_model = model or settings.model
    payload = [
        {
            "id": index,
            "title": story.title,
            "source": story.source,
            "url": story.url,
            "score": story.importance_score,
            "rank_reason": story.reason,
            "evidence_level": _evidence_level(story),
            "evidence": _usable_evidence(story)[:500],
        }
        for index, story in enumerate(stories)
    ]
    response = client.chat.completions.create(
        model=selected_model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "根据以下已筛选新闻生成中文简报。返回包含 trend_summary 和 stories 的 JSON。\n"
                    "trend_summary：2-3句，不逐条复述；只提炼最多3个共同趋势，并说明对市场或产业的具体含义。\n"
                    "每条 story 必须包含 id、chinese_title、summary、why_it_matters。\n"
                    "chinese_title：自然的中文新闻标题，保留关键主体和数字，不使用耸动措辞。\n"
                    "summary：有有效 evidence 时写1-2句；headline_only 时严格只写1句。第一句直接写谁做了什么以及关键结果。\n"
                    "why_it_matters：严格1句，以‘推测：若……则……’说明可能影响，或以‘后续观察：’提出具体待验证的问题；不要断言未获证实的行为或因果关系。\n"
                    "删除任何不提供新信息的句子。不要为了满足长度而扩写。\n\n"
                    f"{json.dumps(payload, ensure_ascii=False)}"
                ),
            },
        ],
    )
    data = json.loads(response.choices[0].message.content or "{}")
    story_by_id = {index: story for index, story in enumerate(stories)}
    brief_stories: list[BriefStory] = []
    seen_ids: set[int] = set()
    for item in data.get("stories", []):
        try:
            story_id = int(item["id"])
            story = story_by_id[story_id]
        except (KeyError, TypeError, ValueError):
            continue
        if story_id in seen_ids:
            continue
        if not str(item.get("summary", "")).strip() or not str(item.get("why_it_matters", "")).strip():
            raise ValueError("AI 返回的简报缺少事件摘要或重要性说明，请重新生成预览。")
        seen_ids.add(story_id)
        brief_stories.append(
            BriefStory(
                title=_reader_title(item, story),
                url=story.url,
                source=story.source,
                importance_score=story.importance_score,
                summary=str(item.get("summary", "")).strip(),
                why_it_matters=str(item.get("why_it_matters", story.reason)).strip(),
            )
        )
    if not brief_stories:
        raise ValueError("AI 未返回有效的新闻摘要，请重新生成预览。")
    return BriefContent(
        trend_summary=str(data.get("trend_summary", "")).strip(),
        stories=brief_stories,
    )


def _reader_title(item: dict, story: RankedStory) -> str:
    title = str(item.get("chinese_title") or item.get("title") or "").strip()
    return title or f"{story.source} 重要新闻"


def _usable_evidence(story: RankedStory) -> str:
    evidence = " ".join(story.summary_seed.split()).strip()
    if not evidence:
        return ""
    normalized_evidence = evidence.lower()
    normalized_title = " ".join(story.title.split()).lower()
    without_source = normalized_evidence.removesuffix(story.source.lower()).strip()
    if without_source == normalized_title or normalized_evidence == normalized_title:
        return ""
    return evidence


def _evidence_level(story: RankedStory) -> str:
    return "snippet" if _usable_evidence(story) else "headline_only"


def _heuristic_summarize(stories: list[RankedStory]) -> BriefContent:
    brief_stories = [
        BriefStory(
            title=story.title,
            url=story.url,
            source=story.source,
            importance_score=story.importance_score,
            summary=f"这条新闻来自 {story.source}。标题显示：{story.title}",
            why_it_matters=story.reason,
        )
        for story in stories
    ]
    return BriefContent(
        trend_summary="无 AI 密钥测试模式；以下内容仅用于检查采集、筛选和排版，尚未验证 AI 中文生成。",
        stories=brief_stories,
    )
