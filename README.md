# paper-brief

每天自动跑一次:抓 arxiv + HuggingFace Papers + 你关注的作者的最新论文 → 用 LLM(默认 DeepSeek-chat,任意 OpenAI 兼容模型可换)给你个性化打分 + 一句话 TLDR + 一句话 "为什么和你的研究相关" → 渲染成静态网站,推到 GitHub Pages。

## What you get

- 一个 `https://TonyLeng1314.github.io/paper-brief/` 站点。
- 每天一个 `posts/YYYY-MM-DD.md`,按相关性分数倒序。
- 全部 self-hosted、零运维(GitHub Actions cron + GitHub Pages)。

## Architecture

```
GitHub Action (cron 00:00 UTC = 08:00 +08)
  └─ scripts/fetch_papers.py
      ├─ sources.py         (arxiv / HF Papers / Semantic Scholar)
      ├─ filter.py          (keyword + author 预筛,省 LLM token)
      ├─ annotate.py        (OpenAI 兼容 API — DeepSeek 默认,system 自动缓存)
      └─ render.py          (写 docs/posts/YYYY-MM-DD.md)
  └─ git commit + push
  └─ mkdocs build --strict
  └─ deploy to GitHub Pages
```

## Setup (one-time)

1. **Create the repo**: `paper-brief` (Public)。把这个目录推上去。
2. **Add secrets**: GitHub → Settings → Secrets and variables → Actions → New repository secret
   - `OPENAI_API_KEY` — 你的 LLM 提供商的 API key(DeepSeek 官方 key 或中转站的 key)。
   - `OPENAI_BASE_URL` —(可选)只在走中转站时填,例如 `https://www.micuapi.ai/v1`。走官方 DeepSeek 留空即可,默认 `https://api.deepseek.com/v1`。
3. **Enable Pages**: Settings → Pages → Source: `GitHub Actions`。
4. **Edit your taste**:
   - `research_profile.md` —— 你是谁、你在研究什么、什么算 "relevant"。这段会被 LLM 缓存(每天 cache 命中,省钱)。
   - `config.yaml` —— 关键词、关注作者、过滤阈值、每天最多几篇。
5. **Trigger the first run**: Actions → "Daily paper brief" → Run workflow。
6. 等 1-2 分钟。打开 `https://<YOUR_USERNAME>.github.io/paper-brief/`。

## Tuning

- 漏掉好文章 → `config.yaml`:`filter.mode: loose`、降低 `min_score`、加关键词。
- 太多噪音 → `filter.mode: strict`、提高 `min_score`、`max_papers_per_day` 调小。
- LLM 评分跑偏 → 改 `research_profile.md` 里的 "VERY relevant / NOT relevant" 区段,描述越具体越好(写出 "我在解决什么具体子问题")。

## Cost

- arxiv / HF Papers / Semantic Scholar:免费。
- LLM:默认 `deepseek-chat`(input ¥1/M、output ¥2/M 量级),每天 ~30-50 篇候选,粗估 ¥0.05-0.2 / 天。DeepSeek 后端会自动缓存稳定的 system 前缀(`research_profile.md`),复跑命中率高。
- GitHub Actions:Public repo 免费额度足够。

## Local dev

```bash
pip install -r requirements.txt

# Dry run, no LLM, just see what gets pre-filtered:
python scripts/fetch_papers.py --config config.yaml --skip-llm

# Full run (needs OPENAI_API_KEY in env; optionally OPENAI_BASE_URL for proxy):
export OPENAI_API_KEY=sk-...
# export OPENAI_BASE_URL=https://www.micuapi.ai/v1   # 只在走中转站时填
python scripts/fetch_papers.py --config config.yaml

# Preview the site:
mkdocs serve
```

## Files

| File | What it does |
|---|---|
| `config.yaml` | All knobs: keywords, authors, thresholds, LLM model. |
| `research_profile.md` | Long-form description of you, cached as LLM system prompt. |
| `scripts/sources.py` | Pull papers from arxiv / HF Papers / Semantic Scholar. |
| `scripts/filter.py` | Cheap keyword + author pre-filter. |
| `scripts/annotate.py` | OpenAI 兼容 API(默认 DeepSeek)→ TLDR + why + score。 |
| `scripts/render.py` | Write daily markdown + regenerate index. |
| `scripts/fetch_papers.py` | Orchestrator. |
| `.github/workflows/daily.yml` | The daily cron. |
| `mkdocs.yml` | Site theme + nav. |
| `docs/` | The site source (commit-tracked). |
