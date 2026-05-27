"""Render annotated papers to JSON for the Astro site."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from annotate import Annotation
from filter import PreScore


def render_day(
    date: dt.date,
    items: list[tuple[PreScore, Annotation]],
    out_dir: Path,
    min_score: int = 5,
    max_papers: int = 10,
) -> Path:
    """Write src/data/posts/YYYY-MM-DD.json and return its path."""
    items = sorted(items, key=lambda x: (-x[1].score, -x[0].score))
    kept = [(ps, a) for ps, a in items if a.score >= min_score][:max_papers]

    payload = {
        "date": date.isoformat(),
        "kept": len(kept),
        "reviewed": len(items),
        "min_score": min_score,
        "papers": [
            {
                "rank": i,
                "title": ps.paper.title,
                "title_zh": a.title_zh,
                "score": a.score,
                "authors": ps.paper.authors,
                "source": ps.paper.source,
                "arxiv_id": ps.paper.arxiv_id,
                "url": ps.paper.url,
                "published": ps.paper.published.isoformat() if ps.paper.published else None,
                "tldr": a.tldr,
                "why": a.why,
                "hits": ps.hits,
            }
            for i, (ps, a) in enumerate(kept, 1)
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    fp = out_dir / f"{date.isoformat()}.json"
    fp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return fp


def update_index(*_args, **_kwargs) -> None:
    """No-op: the Astro index.astro enumerates the content collection itself."""
    return None
