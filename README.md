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
  │   ├─ filter.py          (关键词排序 + broad exploration 候选)
  │   ├─ annotate.py        (DeepSeek V4 Flash 分桶评分:direct / adjacent / explore)
  │   └─ render.py          (写 src/data/posts/YYYY-MM-DD.json)
  ├─ git commit + push
  └─ Node: npm ci && npm run build  (Astro → dist/)
       └─ deploy to GitHub Pages

Site-only Action (push: src / public / Astro config)
  └─ Node: npm install && npm run build
       └─ deploy to GitHub Pages (不抓论文,不调用 LLM)
```

Python 数据管道和 Astro 站完全解耦:Python 只产 JSON,Astro 通过 Content Collection 读 JSON 渲染。

## Setup (one-time)

1. **Create the repo**: `paper-brief` (Public)。把这个目录推上去。
2. **Add secrets**: GitHub → Settings → Secrets and variables → Actions → New repository secret
   - `OPENAI_API_KEY` — 你的 LLM 提供商的 API key(DeepSeek 官方 key 或中转站的 key)。
   - `OPENAI_BASE_URL` —(可选)走官方 DeepSeek 时删除该 secret 或设为 `https://api.deepseek.com`;只有使用中转站时才填写中转地址。
3. **Enable Pages**: Settings → Pages → Source: `GitHub Actions`。
4. **Edit your taste**:
   - `research_profile.md` —— 你是谁、你在研究什么、什么算 "relevant"。这段会被 LLM 缓存。
   - `config.yaml` —— 关键词、关注作者、三类配额、阈值和模型。
5. **Trigger the first run**: Actions → "Daily paper brief" → Run workflow。
6. 等 2-3 分钟。打开 `https://<YOUR_USERNAME>.github.io/paper-brief/`。

## Tuning

- 默认 `filter.mode: broad`:关键词只负责排序,并保留一部分零关键词探索候选。
- 漏掉好文章 → 提高 `explore_fraction` / `llm_cap`,或降低 `min_score`。
- 太多噪音 → 提高 `min_score`,或调小 `max_papers_per_day` 和各 `bucket_quotas`。
- 范围跑偏 → 改 `research_profile.md` 的稳定兴趣与 discovery policy,不要把当前项目写成唯一标准。
- 已成功评审的论文记录在 `src/data/seen_papers.json`,不会跨天重复消耗调用额度。

## Cost

- arxiv / HF Papers / Semantic Scholar:免费。
- LLM:初筛和深读默认官方 `deepseek-v4-flash`;初筛关闭 thinking,全文深读开启 thinking。broad 模式最多初筛 180 篇,实际费用取决于当日新论文数。
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
| `scripts/filter.py` | Keyword-ranked candidate selection with a reserved exploration slice. |
| `scripts/annotate.py` | DeepSeek V4 Flash → TLDR + reading value + bucket + multi-axis scores. |
| `scripts/render.py` | Write daily JSON to `src/data/posts/`. |
| `scripts/fetch_papers.py` | Orchestrator. |
| `src/data/seen_papers.json` | Persistent keys for cross-day deduplication (generated automatically). |
| `astro.config.mjs` | Astro 配置:站点 base path、build format。 |
| `src/content.config.ts` | Astro Content Collection 的 Zod schema。 |
| `src/data/posts/*.json` | Python 写、Astro 读的数据源。 |
| `src/layouts/Base.astro` | 全局布局、顶栏与临时配色面板。 |
| `src/components/` | Hero / PaperCard / PostCard / SearchBox。 |
| `src/pages/index.astro` | 首页(全屏 hero + post grid)。 |
| `src/pages/posts/[date].astro` | 单日页(paper 列表)。 |
| `src/styles/global.css` | 全局阅读样式与四套主题变量。 |
| `src/scripts/theme.ts` | 主题切换、强调色和 session 状态。 |
| `.github/workflows/daily.yml` | The daily cron(Python fetch + Astro build)。 |
| `.github/workflows/deploy-site.yml` | Push 版式代码后只构建并部署网站。 |
