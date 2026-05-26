"""Render annotated papers to MkDocs markdown."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from annotate import Annotation
from filter import PreScore
from sources import Paper


def _fmt_authors(authors: list[str], k: int = 5) -> str:
    if not authors:
        return "_作者未知_"
    if len(authors) <= k:
        return ", ".join(authors)
    return ", ".join(authors[:k]) + f", … (+{len(authors)-k})"


def render_day(
    date: dt.date,
    items: list[tuple[PreScore, Annotation]],
    out_dir: Path,
    min_score: int = 5,
    max_papers: int = 10,
) -> Path:
    """Write docs/posts/YYYY-MM-DD.md and return its path."""
    items = sorted(items, key=lambda x: (-x[1].score, -x[0].score))
    kept = [(ps, a) for ps, a in items if a.score >= min_score][:max_papers]

    out_dir.mkdir(parents=True, exist_ok=True)
    fp = out_dir / f"{date.isoformat()}.md"

    lines: list[str] = []
    lines.append(f"# {date.isoformat()}")
    lines.append("")
    if not kept:
        lines.append(
            f"_今日没有论文达到 score >= {min_score} 的标准。"
            f"(共审阅 {len(items)} 篇候选。)_"
        )
        fp.write_text("\n".join(lines), encoding="utf-8")
        return fp

    lines.append(
        f"_今日推送 {len(kept)} 篇 / 共审阅 {len(items)} 篇候选(score >= {min_score})。_"
    )
    lines.append("")
    for i, (ps, a) in enumerate(kept, 1):
        p: Paper = ps.paper
        lines.append('<div class="paper-card" markdown="1">')
        lines.append("")
        zh = a.title_zh.strip()
        if zh:
            lines.append(f"## {i}. {zh}  ·  **{a.score}/10**")
            lines.append("")
            lines.append(f'<p class="title-en">{p.title}</p>')
        else:
            lines.append(f"## {i}. {p.title}  ·  **{a.score}/10**")
        lines.append("")
        lines.append(f"**作者:** {_fmt_authors(p.authors)}  ")
        meta = [f"来源: `{p.source}`"]
        if p.arxiv_id:
            meta.append(f"arxiv: [`{p.arxiv_id}`]({p.url})")
        else:
            meta.append(f"[原文链接]({p.url})")
        if p.published:
            meta.append(f"发布时间: {p.published.isoformat()}")
        lines.append("  ·  ".join(meta))
        lines.append("")
        lines.append(f"**摘要.** {a.tldr}")
        lines.append("")
        lines.append(f"**为什么相关.** {a.why}")
        lines.append("")
        if ps.hits:
            lines.append(f"<sub>命中信号: {' · '.join(ps.hits)}</sub>")
            lines.append("")
        lines.append("</div>")
        lines.append("")

    fp.write_text("\n".join(lines), encoding="utf-8")
    return fp


def update_index(docs_dir: Path) -> None:
    """Regenerate docs/index.md listing the most recent posts."""
    posts_dir = docs_dir / "posts"
    posts = sorted(posts_dir.glob("*.md"), reverse=True) if posts_dir.exists() else []

    lines: list[str] = ["# 论文速递", "", "_每日个性化 arxiv 论文筛选与推送。_", ""]
    if not posts:
        lines.append("_暂无内容 — 首次抓取尚未完成。_")
    else:
        lines.append("## 近期")
        lines.append("")
        for fp in posts[:30]:
            date = fp.stem
            lines.append(f"- [{date}](posts/{fp.name})")
    (docs_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")
