"""Cheap keyword pre-filter — runs before LLM annotation to cap token cost."""
from __future__ import annotations

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
) -> list[PreScore]:
    """Pick the top candidates that are worth spending LLM tokens on.

    strict: require score >= 3 (at least one high-priority OR two medium hits).
    loose:  require score > 0  (any signal).
    """
    threshold = 3.0 if mode == "strict" else 0.5
    candidates = [c for c in prescored if c.score >= threshold]
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:cap]
