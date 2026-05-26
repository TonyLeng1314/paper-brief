"""Render annotated papers to MkDocs markdown."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from annotate import Annotation
from filter import PreScore
from sources import Paper


def _fmt_authors(authors: list[str], k: int = 5) -> str:
    if not authors:
        return "_authors unknown_"
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
    # Sort by LLM score desc, then prescore desc.
    items = sorted(items, key=lambda x: (-x[1].score, -x[0].score))
    kept = [(ps, a) for ps, a in items if a.score >= min_score][:max_papers]

    out_dir.mkdir(parents=True, exist_ok=True)
    fp = out_dir / f"{date.isoformat()}.md"

    lines: list[str] = []
    lines.append(f"# {date.isoformat()}")
    lines.append("")
    if not kept:
        lines.append(
            f"_No papers cleared the score>={min_score} bar today. "
            f"({len(items)} candidates seen.)_"
        )
        fp.write_text("\n".join(lines))
        return fp

    lines.append(
        f"_{len(kept)} of {len(items)} candidates kept (score >= {min_score})._"
    )
    lines.append("")
    for i, (ps, a) in enumerate(kept, 1):
        p: Paper = ps.paper
        lines.append(f"## {i}. {p.title}  ·  **{a.score}/10**")
        lines.append("")
        lines.append(f"**Authors:** {_fmt_authors(p.authors)}  ")
        meta = [f"source: `{p.source}`"]
        if p.arxiv_id:
            meta.append(f"arxiv: [`{p.arxiv_id}`]({p.url})")
        else:
            meta.append(f"[link]({p.url})")
        if p.published:
            meta.append(f"published: {p.published.isoformat()}")
        lines.append("  ·  ".join(meta))
        lines.append("")
        lines.append(f"**TLDR.** {a.tldr}")
        lines.append("")
        lines.append(f"**Why it matters.** {a.why}")
        lines.append("")
        if ps.hits:
            lines.append(f"<sub>signals: {' · '.join(ps.hits)}</sub>")
            lines.append("")
        lines.append("---")
        lines.append("")

    fp.write_text("\n".join(lines))
    return fp


def update_index(docs_dir: Path) -> None:
    """Regenerate docs/index.md listing the most recent posts."""
    posts_dir = docs_dir / "posts"
    posts = sorted(posts_dir.glob("*.md"), reverse=True) if posts_dir.exists() else []

    lines: list[str] = ["# Paper Brief", "", "_Daily personalized arxiv triage._", ""]
    if not posts:
        lines.append("_No briefs yet — first run is pending._")
    else:
        lines.append("## Recent")
        lines.append("")
        for fp in posts[:30]:
            date = fp.stem
            lines.append(f"- [{date}](posts/{fp.name})")
    (docs_dir / "index.md").write_text("\n".join(lines))
