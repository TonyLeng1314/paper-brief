# paper-brief

每天自动跑一次:抓 arxiv + HuggingFace Papers + 你关注的作者的最新论文 → 用 Claude 给你个性化打分 + 一句话 TLDR + 一句话 "为什么和你的研究相关" → 渲染成静态网站,推到 GitHub Pages。

## What you get

- 一个 `https://<YOUR_USERNAME>.github.io/paper-brief/` 站点。
- 每天一个 `posts/YYYY-MM-DD.md`,按相关性分数倒序。
- 全部 self-hosted、零运维(GitHub Actions cron + GitHub Pages)。

## Architecture

```
GitHub Action (cron 00:00 UTC = 08:00 +08)
  └─ scripts/fetch_papers.py
      ├─ sources.py         (arxiv / HF Papers / Semantic Scholar)
      ├─ filter.py          (keyword + author 预筛,省 LLM token)
      ├─ annotate.py        (Claude API + prompt caching for research_profile)
      └─ render.py          (写 docs/posts/YYYY-MM-DD.md)
  └─ git commit + push
  └─ mkdocs build --strict
  └─ deploy to GitHub Pages
```

## Setup (one-time)

1. **Create the repo**: `paper-brief` (Public)。把这个目录推上去。
2. **Add secret**: GitHub → Settings → Secrets and variables → Actions → New repository secret
   - Name: `ANTHROPIC_API_KEY`
   - Value: 你的 key
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
- Claude API:`claude-sonnet-4-6`,每天 ~30-50 篇候选,batched + prompt-cached,粗估 < $0.05 / 天。
- GitHub Actions:Public repo 免费额度足够。

## Local dev

```bash
pip install -r requirements.txt

# Dry run, no LLM, just see what gets pre-filtered:
python scripts/fetch_papers.py --config config.yaml --skip-llm

# Full run (needs ANTHROPIC_API_KEY in env):
export ANTHROPIC_API_KEY=sk-ant-...
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
| `scripts/annotate.py` | Claude API w/ prompt caching → TLDR + why + score. |
| `scripts/render.py` | Write daily markdown + regenerate index. |
| `scripts/fetch_papers.py` | Orchestrator. |
| `.github/workflows/daily.yml` | The daily cron. |
| `mkdocs.yml` | Site theme + nav. |
| `docs/` | The site source (commit-tracked). |
