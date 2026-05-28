"""Top-level orchestrator: fetch → prescore → filter → annotate → deep-read → render."""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

import yaml

from annotate import annotate_papers
from deep_annotate import deep_annotate_papers
from filter import prescore, select_for_llm
from render import render_day, update_index
from sources import (
    Paper,
    dedupe,
    enrich_arxiv_metadata,
    fetch_arxiv,
    fetch_huggingface_papers,
    fetch_semantic_scholar_authors,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def gather(cfg: dict) -> list[Paper]:
    papers: list[Paper] = []
    sources = cfg.get("sources", {})

    if sources.get("arxiv", {}).get("enabled", True):
        cats = sources["arxiv"].get("categories", ["cs.LG"])
        m = sources["arxiv"].get("max_per_category", 50)
        log.info("Fetching arxiv: %s (%d each)", cats, m)
        papers.extend(fetch_arxiv(cats, m))

    if sources.get("huggingface_papers", {}).get("enabled", True):
        log.info("Fetching HuggingFace Papers")
        papers.extend(fetch_huggingface_papers())

    if sources.get("semantic_scholar_authors", {}).get("enabled", True):
        names = cfg.get("authors", [])
        lookback = sources["semantic_scholar_authors"].get("lookback_days", 7)
        if names:
            log.info("Fetching S2 papers for %d authors", len(names))
            papers.extend(fetch_semantic_scholar_authors(names, lookback))

    log.info("Total before dedup: %d", len(papers))
    papers = dedupe(papers)
    log.info("After dedup: %d", len(papers))
    enrich_arxiv_metadata(papers)
    return papers


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--profile", default=None, help="Override research_profile_path.")
    ap.add_argument(
        "--data-dir",
        default="src/data/posts",
        help="Where to write the daily JSON. The Astro Content Collection points here.",
    )
    ap.add_argument("--date", default=None, help="YYYY-MM-DD; defaults to today UTC.")
    ap.add_argument(
        "--skip-llm",
        action="store_true",
        help="Dry run: render using prescore only, no LLM call. Implies --skip-deep.",
    )
    ap.add_argument(
        "--skip-deep",
        action="store_true",
        help="Skip stage-2 PDF deep-read; render only stage-1 annotations.",
    )
    ap.add_argument(
        "--cache-dir",
        default="cache",
        help="Directory for pdf_text/ and deep/ caches.",
    )
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    today = (
        dt.date.fromisoformat(args.date) if args.date else dt.datetime.utcnow().date()
    )

    papers = gather(cfg)
    if not papers:
        log.warning("No papers fetched. Nothing to render.")
        return 0

    kw = cfg.get("keywords", {})
    prescored = prescore(
        papers,
        high=kw.get("high_priority", []),
        medium=kw.get("medium_priority", []),
        cross=kw.get("cross_domain", []),
        tracked_authors=cfg.get("authors", []),
    )
    mode = cfg.get("filter", {}).get("mode", "strict")
    cap = cfg.get("filter", {}).get("llm_cap", 40)
    candidates = select_for_llm(prescored, mode=mode, cap=cap)
    log.info("LLM candidates: %d (mode=%s, cap=%d)", len(candidates), mode, cap)

    annotations = {}
    if cfg.get("llm", {}).get("enabled", True) and not args.skip_llm:
        profile_path = Path(
            args.profile or cfg.get("llm", {}).get("research_profile_path", "research_profile.md")
        )
        if not profile_path.exists():
            log.error("Research profile not found: %s", profile_path)
            return 2
        profile = profile_path.read_text()
        model = cfg.get("llm", {}).get("model", "claude-sonnet-4-6")
        batch_size = cfg.get("llm", {}).get("batch_size", 10)
        annotations = annotate_papers(
            [c.paper for c in candidates], profile, model=model, batch_size=batch_size
        )
        log.info("Annotated %d papers", len(annotations))
    else:
        from annotate import Annotation

        profile = ""
        model = cfg.get("llm", {}).get("model", "deepseek-chat")
        for c in candidates:
            annotations[c.paper.key()] = Annotation(
                key=c.paper.key(),
                tldr="(LLM disabled — dry run)",
                why="signals: " + " ".join(c.hits),
                score=min(10, int(c.score)),
            )

    items = [
        (c, annotations[c.paper.key()])
        for c in candidates
        if c.paper.key() in annotations
    ]

    min_score = cfg.get("filter", {}).get("min_score", 5)
    max_papers = cfg.get("filter", {}).get("max_papers_per_day", 10)

    items.sort(key=lambda x: (-x[1].score, -x[0].score))
    kept = [(ps, a) for ps, a in items if a.score >= min_score][:max_papers]
    log.info("Kept after min_score=%d / cap=%d: %d papers",
             min_score, max_papers, len(kept))

    deep_annotations = {}
    if (
        cfg.get("llm", {}).get("enabled", True)
        and not args.skip_llm
        and not args.skip_deep
        and kept
    ):
        log.info("Deep-reading %d papers (PDF + LLM)…", len(kept))
        deep_annotations = deep_annotate_papers(
            [ps.paper for ps, _ in kept],
            profile,
            model=model,
            cache_dir=Path(args.cache_dir),
        )
        log.info("Deep-annotated %d/%d papers", len(deep_annotations), len(kept))

    fp = render_day(
        today,
        kept,
        deep_annotations,
        Path(args.data_dir),
        reviewed=len(items),
        min_score=min_score,
    )
    log.info("Wrote %s", fp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
