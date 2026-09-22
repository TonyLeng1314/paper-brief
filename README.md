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

- 默认 `filter.mode: broad`:关键词只负责排序,候选池按三条道分配名额,而不是一个全局排序。
- **arxiv 抓取分两路**:`sources.arxiv.categories` 是按时间倒序的 firehose,只放 `cs.RO`
  这类小而对口的分区;`cs.CV` / `cs.LG` 每天 500+ 篇,取"最新 N 篇"等于只看了最后
  两小时,所以它们放在 `topic_lanes` 里按关键词做定向检索。
  想扩大召回就往对应 lane 的 `terms` 加词,而不是调大 `max_per_category`。
- **每条 lane 自带 categories**,因为一个分区列表服务不了两个领域。把神经科学词丢进
  CS 分区里搜,100 篇里只有 2 篇真的是 `q-bio.NC` —— `replay` 会命中每一篇提到
  replay buffer 的 RL 论文,而 cs.AI 的日投稿量比 q-bio.NC 高两个数量级,真正的脑科学
  论文在按时间排序的结果页上根本排不进来;同样的词限定在 `q-bio.NC` 里搜是 78/100。
  所以 `neuro` lane 的词可以松(分区在替你过滤),`neuro-in-ml` lane 的词必须紧(没有
  分区兜底)。
- **候选池按道分配名额**:`explore_fraction` 留给零关键词论文,`adjacent_fraction` 留给
  只有弱信号(medium/cross,无 high 命中)的论文,剩下的归核心道。没有这个保留,
  VLA 高峰日的 180 个候选名额会被 10-25 分的论文占满,一篇 2 分的神经科学论文
  永远送不到 LLM 面前 —— 跨领域那条道就只存在于抓取阶段。某条道没占满时名额会回流。
  每次运行都会打印 `lanes: core=.. adjacent=.. explore=..`,`adjacent` 掉到 0 就是跨领域
  召回已经悄悄死了。
- 关键词权重在 `scripts/filter.py`:high 5.0 / medium 1.0 / cross 0.5。
  `medium_priority` 里不要放 `planning`、`memory` 这类通用词 —— 否则三个通用词命中
  会盖过一个真正的 `VLA` 命中,核心方向会被泛 ML 论文稀释。通用词放 `cross_domain`。
  一个词只能出现在一个层级里,写两遍会把权重悄悄相加。
  一词多义的词(`forward model` 在反问题里指正演算子,`internal model` 也指 IMC 控制)
  放 `cross_domain`,让它单独命中时抢不到相邻道的名额。
- 关键词匹配会把连字符折成空格,`vision language action` 同时匹配 `Vision-Language-Action`;
  左边界对齐,所以 `VLA` 不会命中 `NVLA`,`forward model` 也不会命中 `feed-forward model`,
  但右边界开放,复数和后缀(`world models`、`VLA-Adapter`)照常命中。
- 漏掉好文章 → 往 lane 的 `terms` / `high_priority` 加词,或提高 `llm_cap`、降低 `min_score`。
- 太多噪音 → 提高 `min_score`,或调小 `max_papers_per_day` 和各 `bucket_quotas`。
- 核心方向看得不够 → 调大 `bucket_quotas.direct`。它是硬上限,`direct` 卡在配额上时
  正好削掉的就是最该看的论文。
- 范围跑偏 → 改 `research_profile.md` 的核心领域与 discovery policy,不要把当前项目写成唯一标准。
- 已成功评审的论文记录在 `src/data/seen_papers.json`,不会跨天重复消耗调用额度。

## Failure modes

流水线宁可红着退出,也不发一份残缺的 brief —— 静默降级会把当天的残缺结果写进
`seen_papers.json`,那些论文以后再也不会被重新评审。

| 退出码 | 含义 | 处理 |
|---|---|---|
| 0 | 正常(含"今天没有新论文") | — |
| 2 | 找不到 `research_profile.md` | 检查 `llm.research_profile_path` |
| 3 | 模型不可路由,或全部标注失败 | 检查 `triage_model` / `OPENAI_BASE_URL` |
| 4 | arxiv 全部查询失败(通常是 HTTP 429) | 重跑 workflow;持续失败可临时设 `sources.arxiv.required: false` |
| 5 | LLM 账户余额 / 配额耗尽 | 充值后重跑,当天论文不会丢 |

- arxiv 对共享出口 IP(尤其 Actions runner)限流很凶,`sources.py` 会退避重试 4 次。
- 初筛响应解析失败或被 `max_tokens` 截断时,该 chunk 会被对半拆开重试,而不是整批丢弃。
- `SEMANTIC_SCHOLAR_API_KEY`(可选 secret)能让作者源真正出活;不配的话它基本一直 429。

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
| `scripts/sources.py` | Pull papers from arxiv (firehose + topic search) / HF Papers / Semantic Scholar. |
| `scripts/filter.py` | Keyword-ranked candidate selection with a reserved exploration slice. |
| `scripts/annotate.py` | DeepSeek V4 Flash → TLDR + reading value + bucket + multi-axis scores, with split-and-retry on bad batches. |
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
