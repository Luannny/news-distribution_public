# 每日中文新闻邮件（Gemini + Gmail）

每天北京时间08:00由 GitHub Actions 启动，完成采集、筛选和生成后发送；实际送达可能延迟。

## 新闻内容

- 过去24小时的 AI、科技、重要公司和宏观经济新闻。
- 最多10条，宁缺毋滥。
- 中文标题、事件摘要、为什么重要、来源链接。
- 事实来自标题与摘要片段；推测须明确标识，不补写无依据的信息。
- 保留 VIX、数据日期、来源及简短解释；无法获取时说明不可用。

## 必填的 GitHub Secrets

打开 https://github.com/Luannny/news-distribution_public/settings/secrets/actions

| Name | Secret 填写内容 |
|---|---|
| GEMINI_API_KEY | Google AI Studio 的 Gemini 密钥 |
| EMAIL_USER | 发件 Gmail 完整地址 |
| EMAIL_PASSWORD | Gmail 应用专用密码 |
| EMAIL_TO | 收件邮箱 |

邮箱测试邮件已由用户确认收到。迁移后工作流只读取 GEMINI_API_KEY，不读取原 OPENAI_API_KEY。三个邮箱 Secret 无需重建。

Gemini 密钥页面：https://aistudio.google.com/api-keys 。密码和密钥只填写在 GitHub Secrets，不要提交到代码或发到聊天中。

## 先预览，再发送

1. 仓库 Actions → Daily News Brief → Run workflow。
2. 不勾选“发送邮件”：只生成预览，不发送。
3. 成功后下载该次运行的 daily-news-preview 文件，解压并打开 HTML。
4. 确认内容后，手动运行时勾选“发送邮件”可发一份实际简报。
5. 定时任务默认每天北京时间08:00自动发送。GitHub 调度可能延迟；连续60天无仓库活动的公开项目，定时任务可能被自动停用，请留意 Actions 状态。

## 模型与费用

默认 Gemini 模型为 gemini-3.5-flash-lite，可用 GEMINI_MODEL Secret 覆盖。代码使用 Google 官方兼容接口，实际请求发送到 generativelanguage.googleapis.com；依赖包名称中的 openai 不代表调用 OpenAI 服务。

Google 当前为该模型提供有上限的免费额度；以自己的 AI Studio 免费层状态、地区资格、配额为准。不要为了测试而开通付费结算。免费额度耗尽或接口异常时任务报错，不自动换到付费模型或 OpenAI，不发送未经 AI 处理的替代简报。若自行为项目开启结算，调用可能产生费用。

官方价格：https://ai.google.dev/gemini-api/docs/pricing
官方配额：https://ai.google.dev/gemini-api/docs/rate-limits

## 暂停发送

Actions → Daily News Brief → 右上角菜单 → Disable workflow。

## 本地运行（可选）

复制 .env.example 为 .env，并自行填写。先运行 python -m src.main --dry-run；真正发送使用 python -m src.main。无密钥的本地预览仅为规则筛选测试，不能视为实际 AI 中文新闻结果。云端预览严格要求 Gemini 密钥。
