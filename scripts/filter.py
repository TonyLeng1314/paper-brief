"""Cheap keyword pre-filter — runs before LLM annotation to cap token cost."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sources import Paper


@dataclass
class PreScore:
    """Heuristic score from keyword/author hits, before LLM sees the paper."""
    paper: Paper
    score: float
    hits: list[str]


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower())


def _hit(text: str, term: str) -> bool:
    """Case-insensitive substring match with word boundary for short terms."""
    t = term.lower().strip()
    if len(t) <= 4:
        return re.search(rf"\b{re.escape(t)}\b", text) is not None
    return t in text


def prescore(
    papers: list[Paper],
    high: list[str],
    medium: list[str],
    cross: list[str],
    tracked_authors: list[str],
) -> list[PreScore]:
    """Score each paper by keyword/author hits in title + abstract."""
    tracked_lower = {a.lower() for a in tracked_authors}
    out: list[PreScore] = []
    for p in papers:
        text = _normalize(f"{p.title}\n{p.abstract}")
        hits: list[str] = []
        score = 0.0

        for term in high:
            if _hit(text, term):
                hits.append(f"H:{term}")
                score += 3.0
        for term in medium:
            if _hit(text, term):
                hits.append(f"M:{term}")
                score += 1.5
        for term in cross:
            if _hit(text, term):
                hits.append(f"C:{term}")
                score += 1.0

        author_hits = [a for a in p.authors if a.lower() in tracked_lower]
        if author_hits:
            hits.append(f"A:{','.join(author_hits)}")
            score += 4.0

        # HF Papers list is curated, give a small bump.
        if p.source == "hf_papers":
            hits.append("S:hf_curated")
            score += 1.0
        # S2 author feed already filtered on tracked authors, bump too.
        if p.source == "semantic_scholar":
            score += 1.0

        out.append(PreScore(paper=p, score=score, hits=hits))
    return out


def select_for_llm(
    prescored: list[PreScore],
    mode: str = "strict",
    cap: int = 40,
    explore_fraction: float = 0.25,
) -> list[PreScore]:
    """Pick the top candidates that are worth spending LLM tokens on.

    strict: require score >= 3 (at least one high-priority OR two medium hits).
    loose:  require score > 0  (any signal).
    broad:  keywords rank the core slice, while a reserved exploration slice
            admits papers with no configured keyword signal.
    """
    cap = max(0, cap)

    def sort_key(candidate: PreScore) -> tuple:
        published = candidate.paper.published
        published_ord = published.toordinal() if published else 0
        return (-candidate.score, -published_ord, candidate.paper.title.lower())

    ranked = sorted(prescored, key=sort_key)
    if mode == "strict":
        return [c for c in ranked if c.score >= 3.0][:cap]
    if mode == "loose":
        return [c for c in ranked if c.score >= 0.5][:cap]
    if mode != "broad":
        raise ValueError(f"Unknown filter mode: {mode}")

    signaled = [c for c in ranked if c.score >= 0.5]
    un_signaled = [c for c in ranked if c.score < 0.5]
    # Stable hashing gives the exploration slice topical variety while keeping
    # reruns reproducible. Cross-day dedup advances through the remaining pool.
    un_signaled.sort(
        key=lambda candidate: hashlib.sha256(
            candidate.paper.key().encode("utf-8")
        ).digest()
    )
    fraction = max(0.0, min(1.0, explore_fraction))
    explore_slots = min(len(un_signaled), round(cap * fraction))
    core_slots = cap - explore_slots

    selected = signaled[:core_slots]
    selected.extend(un_signaled[: cap - len(selected)])
    if len(selected) < cap:
        selected.extend(signaled[core_slots : core_slots + cap - len(selected)])
    return selected
