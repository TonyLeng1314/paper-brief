# paper-brief

每天自动跑一次:抓 arxiv + HuggingFace Papers + 你关注的作者的最新论文 → 用 LLM(默认 DeepSeek,任意 OpenAI 兼容模型可换)给你个性化打分 + 一句话 TLDR + 一句话 "为什么和你的研究相关" → Astro 静态站推到 GitHub Pages,赛博朋克皮肤。

## What you get

- 一个 `https://TonyLeng1314.github.io/paper-brief/` 站点。
- 每天一个 `src/data/posts/YYYY-MM-DD.json`,Astro 编译成 `/posts/YYYY-MM-DD/` 静态页。
- 全部 self-hosted、零运维(GitHub Actions cron + GitHub Pages)。

## Architecture

```
GitHub Action (cron 00:00 UTC = 08:00 +08)
  ├─ Python: scripts/fetch_papers.py
  │   ├─ sources.py         (arxiv / HF Papers / Semantic Scholar)
  │   ├─ filter.py          (keyword + author 预筛,省 LLM token)
  │   ├─ annotate.py        (OpenAI 兼容 API — DeepSeek 默认,system 自动缓存)
  │   └─ render.py          (写 src/data/posts/YYYY-MM-DD.json)
  ├─ git commit + push
  └─ Node: npm ci && npm run build  (Astro → dist/)
       └─ deploy to GitHub Pages
```

Python 数据管道和 Astro 站完全解耦:Python 只产 JSON,Astro 通过 Content Collection 读 JSON 渲染。

## Setup (one-time)

1. **Create the repo**: `paper-brief` (Public)。把这个目录推上去。
2. **Add secrets**: GitHub → Settings → Secrets and variables → Actions → New repository secret
   - `OPENAI_API_KEY` — 你的 LLM 提供商的 API key(DeepSeek 官方 key 或中转站的 key)。
   - `OPENAI_BASE_URL` —(可选)只在走中转站时填,例如 `https://www.micuapi.ai/v1`。走官方 DeepSeek 留空即可,默认 `https://api.deepseek.com/v1`。
3. **Enable Pages**: Settings → Pages → Source: `GitHub Actions`。
4. **Edit your taste**:
   - `research_profile.md` —— 你是谁、你在研究什么、什么算 "relevant"。这段会被 LLM 缓存。
   - `config.yaml` —— 关键词、关注作者、过滤阈值、每天最多几篇。
5. **Trigger the first run**: Actions → "Daily paper brief" → Run workflow。
6. 等 2-3 分钟。打开 `https://<YOUR_USERNAME>.github.io/paper-brief/`。

## Tuning

- 漏掉好文章 → `config.yaml`:`filter.mode: loose`、降低 `min_score`、加关键词。
- 太多噪音 → `filter.mode: strict`、提高 `min_score`、`max_papers_per_day` 调小。
- LLM 评分跑偏 → 改 `research_profile.md` 里的 "VERY relevant / NOT relevant" 区段,越具体越好。

## Cost

- arxiv / HF Papers / Semantic Scholar:免费。
- LLM:默认 `deepseek-v4-pro`,每天 ~30-50 篇候选,粗估 ¥0.05-0.2 / 天。
- GitHub Actions:Public repo 免费额度足够。

## Local dev

Python 端(LLM 调试 / pre-filter dry run):

```bash
pip install -r requirements.txt

# Dry run, no LLM, just see what gets pre-filtered:
python scripts/fetch_papers.py --config config.yaml --skip-llm --data-dir /tmp/preview-posts

# Full run (needs OPENAI_API_KEY in env; optionally OPENAI_BASE_URL for proxy):
export OPENAI_API_KEY=sk-...
# export OPENAI_BASE_URL=https://www.micuapi.ai/v1   # 只在走中转站时填
python scripts/fetch_papers.py --config config.yaml --data-dir src/data/posts
```

Astro 端(站点 UI 调试):

```bash
npm install     # 首次
npm run dev     # localhost:4321/paper-brief/
npm run build   # dist/
```

不在本机装 Node 也可以 —— push 上去用 Action 跑,完整一轮 ~2 分钟。

## Files

| File | What it does |
|---|---|
| `config.yaml` | All knobs: keywords, authors, thresholds, LLM model. |
| `research_profile.md` | Long-form description of you, cached as LLM system prompt. |
| `scripts/sources.py` | Pull papers from arxiv / HF Papers / Semantic Scholar. |
| `scripts/filter.py` | Cheap keyword + author pre-filter. |
| `scripts/annotate.py` | OpenAI 兼容 API(默认 DeepSeek)→ TLDR + why + score。 |
| `scripts/render.py` | Write daily JSON to `src/data/posts/`. |
| `scripts/fetch_papers.py` | Orchestrator. |
| `astro.config.mjs` | Astro 配置:站点 base path、build format。 |
| `src/content.config.ts` | Astro Content Collection 的 Zod schema。 |
| `src/data/posts/*.json` | Python 写、Astro 读的数据源。 |
| `src/layouts/Base.astro` | 全局布局:topbar + main + cyber-fx 特效层。 |
| `src/components/` | Hero / PaperCard / PostCard / CyberFx。 |
| `src/pages/index.astro` | 首页(全屏 hero + post grid)。 |
| `src/pages/posts/[date].astro` | 单日页(paper 列表)。 |
| `src/styles/global.css` | 整套 Cyberpunk 样式 + keyframes。 |
| `src/scripts/cursor.ts` | spotlight 跟鼠标 + DOM meteor 生成 + IntersectionObserver stagger。 |
| `.github/workflows/daily.yml` | The daily cron(Python fetch + Astro build)。 |
