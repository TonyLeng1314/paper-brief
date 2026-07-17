"""Top-level orchestrator: fetch → prescore → filter → annotate → deep-read → render."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
from pathlib import Path

import yaml

from annotate import ModelUnavailableError, annotate_papers
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
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _rendered_paper_key(item: dict) -> str:
    if item.get("key"):
        return str(item["key"])
    if item.get("arxiv_id"):
        return f"arxiv:{item['arxiv_id']}"
    title = str(item.get("title", "")).lower()
    return f"title:{re.sub(r'[^a-z0-9]+', '', title)}"


def load_seen(path: Path, posts_dir: Path) -> dict[str, str]:
    """Load reviewed paper keys and seed them from existing rendered posts."""
    seen: dict[str, str] = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            papers = payload.get("papers", payload) if isinstance(payload, dict) else payload
            if isinstance(papers, dict):
                seen.update({str(k): str(v) for k, v in papers.items()})
            elif isinstance(papers, list):
                seen.update({str(k): "unknown" for k in papers})
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not load seen-paper state %s: %s", path, exc)

    for post_path in posts_dir.glob("*.json"):
        try:
            post = json.loads(post_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        date = str(post.get("date", post_path.stem))
        for item in post.get("papers", []):
            key = _rendered_paper_key(item)
            if key not in {"title:", "arxiv:"}:
                seen.setdefault(key, date)
    return seen


def save_seen(path: Path, seen: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "papers": dict(sorted(seen.items()))}
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp_path.replace(path)


def select_by_bucket(
    items: list[tuple],
    min_score: int,
    max_papers: int,
    quotas: dict,
) -> list[tuple]:
    """Apply bucket quotas, then backfill unused capacity by reading priority."""
    bucket_order = {"direct": 0, "adjacent": 1, "explore": 2}
    eligible = [item for item in items if item[1].score >= min_score]
    eligible.sort(
        key=lambda item: (
            -item[1].score,
            -max(item[1].domain_fit, item[1].transfer_value, item[1].novelty),
            -item[0].score,
        )
    )

    selected: list[tuple] = []
    selected_keys: set[str] = set()
    for bucket in bucket_order:
        quota = max(0, int(quotas.get(bucket, max_papers)))
        for item in eligible:
            if len(selected) >= max_papers or quota <= 0:
                break
            if item[1].bucket != bucket or item[1].key in selected_keys:
                continue
            selected.append(item)
            selected_keys.add(item[1].key)
            quota -= 1

    for item in eligible:
        if len(selected) >= max_papers:
            break
        if item[1].key not in selected_keys:
            selected.append(item)
            selected_keys.add(item[1].key)

    selected.sort(
        key=lambda item: (
            bucket_order.get(item[1].bucket, 1),
            -item[1].score,
            -item[0].score,
        )
    )
    return selected


def gather(cfg: dict, date: dt.date | None = None) -> list[Paper]:
    papers: list[Paper] = []
    sources = cfg.get("sources", {})

    if sources.get("arxiv", {}).get("enabled", True):
        cats = sources["arxiv"].get("categories", ["cs.LG"])
        m = sources["arxiv"].get("max_per_category", 50)
        log.info("Fetching arxiv: %s (%d each)", cats, m)
        papers.extend(fetch_arxiv(cats, m))

    if sources.get("huggingface_papers", {}).get("enabled", True):
        log.info("Fetching HuggingFace Papers")
        papers.extend(fetch_huggingface_papers(date))

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

    gathered = gather(cfg, today)
    if not gathered:
        log.warning("No papers fetched. Nothing to render.")
        return 0

    filter_cfg = cfg.get("filter", {})
    seen_path = Path(filter_cfg.get("seen_path", "src/data/seen_papers.json"))
    seen = load_seen(seen_path, Path(args.data_dir))
    papers = [paper for paper in gathered if paper.key() not in seen]
    log.info(
        "Cross-day dedup: fetched=%d previously_reviewed=%d new=%d",
        len(gathered),
        len(gathered) - len(papers),
        len(papers),
    )
    if not papers:
        log.info("No unseen papers today; leaving the existing briefs unchanged.")
        return 0

    kw = cfg.get("keywords", {})
    prescored = prescore(
        papers,
        high=kw.get("high_priority", []),
        medium=kw.get("medium_priority", []),
        cross=kw.get("cross_domain", []),
        tracked_authors=cfg.get("authors", []),
    )
    mode = filter_cfg.get("mode", "strict")
    cap = filter_cfg.get("llm_cap", 40)
    explore_fraction = filter_cfg.get("explore_fraction", 0.25)
    candidates = select_for_llm(
        prescored, mode=mode, cap=cap, explore_fraction=explore_fraction
    )
    log.info("LLM candidates: %d (mode=%s, cap=%d)", len(candidates), mode, cap)
    if not candidates:
        log.info("No papers passed candidate selection; no brief written.")
        return 0

    annotations = {}
    if cfg.get("llm", {}).get("enabled", True) and not args.skip_llm:
        profile_path = Path(
            args.profile or cfg.get("llm", {}).get("research_profile_path", "research_profile.md")
        )
        if not profile_path.exists():
            log.error("Research profile not found: %s", profile_path)
            return 2
        profile = profile_path.read_text(encoding="utf-8")
        llm_cfg = cfg.get("llm", {})
        triage_model = llm_cfg.get("triage_model") or llm_cfg.get(
            "model", "deepseek-v4-flash"
        )
        batch_size = llm_cfg.get("batch_size", 10)
        triage_thinking = bool(llm_cfg.get("triage_thinking", False))
        try:
            annotations = annotate_papers(
                [c.paper for c in candidates],
                profile,
                model=triage_model,
                batch_size=batch_size,
                thinking=triage_thinking,
            )
        except ModelUnavailableError as exc:
            log.error("%s", exc)
            return 3
        log.info("Annotated %d papers", len(annotations))
        if not annotations:
            log.error(
                "All LLM annotations failed for %d candidates; refusing to publish an empty brief.",
                len(candidates),
            )
            return 3

        review_date = today.isoformat()
        seen.update({key: review_date for key in annotations})
        save_seen(seen_path, seen)
    else:
        from annotate import Annotation

        profile = ""
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

    min_score = filter_cfg.get("min_score", 5)
    max_papers = filter_cfg.get("max_papers_per_day", 10)
    quotas = filter_cfg.get("bucket_quotas", {})
    kept = select_by_bucket(items, min_score, max_papers, quotas)
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
        llm_cfg = cfg.get("llm", {})
        deep_model = llm_cfg.get("deep_read_model") or llm_cfg.get(
            "model", "deepseek-v4-flash"
        )
        deep_thinking = bool(llm_cfg.get("deep_read_thinking", True))
        try:
            deep_annotations = deep_annotate_papers(
                [ps.paper for ps, _ in kept],
                profile,
                model=deep_model,
                cache_dir=Path(args.cache_dir),
                thinking=deep_thinking,
            )
        except ModelUnavailableError as exc:
            log.error("%s", exc)
            return 3
        log.info("Deep-annotated %d/%d papers", len(deep_annotations), len(kept))

    fp = render_day(
        today,
        kept,
        deep_annotations,
        Path(args.data_dir),
        reviewed=len(items),
        min_score=min_score,
        funnel={
            "fetched": len(gathered),
            "unseen": len(papers),
            "llm_candidates": len(candidates),
            "annotated": len(annotations),
        },
    )
    log.info("Wrote %s", fp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
