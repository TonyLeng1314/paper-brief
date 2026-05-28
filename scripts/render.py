"""Render annotated papers to JSON for the Astro site."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from annotate import Annotation
from deep_annotate import DeepAnnotation
from filter import PreScore


def render_day(
    date: dt.date,
    kept: list[tuple[PreScore, Annotation]],
    deep_annotations: dict[str, DeepAnnotation],
    out_dir: Path,
    reviewed: int,
    min_score: int,
) -> Path:
    """Write src/data/posts/YYYY-MM-DD.json and return its path.

    `kept` must already be filtered (score >= min_score) and sorted.
    `deep_annotations` is keyed by paper.key(); missing entries → no `deep`
    field on that paper.
    """
    papers: list[dict] = []
    for i, (ps, a) in enumerate(kept, 1):
        entry: dict = {
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
        deep = deep_annotations.get(ps.paper.key())
        if deep:
            d = deep.to_dict()
            d.pop("key", None)
            entry["deep"] = d
        papers.append(entry)

    payload = {
        "date": date.isoformat(),
        "kept": len(kept),
        "reviewed": reviewed,
        "min_score": min_score,
        "papers": papers,
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
