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


# A high-priority term is worth more than any stack of generic ones: three
# medium hits used to outrank a real "VLA" hit, which pushed generic ML papers
# into the core slice ahead of on-topic work.
WEIGHT_HIGH = 5.0
WEIGHT_MEDIUM = 1.0
WEIGHT_CROSS = 0.5
WEIGHT_AUTHOR = 5.0

# Hyphens/underscores/slashes are folded so the config can write
# "vision language action" and still match "Vision-Language-Action". They fold to
# a marker rather than to a space: a keyword may end across one ("world model"
# matches "world-model") but may not START inside one. Without that asymmetry
# "forward model" matches "feed-forward model", which put four feed-forward 3D
# reconstruction papers into the neuroscience lane.
_JOIN = "\x00"
_SEPARATORS = re.compile(r"[-_/]+")
_TOKEN_GAP = re.compile(rf"[\s{_JOIN}]+")


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", _SEPARATORS.sub(_JOIN, s.lower())).strip()


def _hit(text: str, term: str) -> bool:
    """Match `term` at a word start, with a free right edge.

    The left boundary stops "VLA" matching inside "NVLA" and "forward model"
    matching inside "feed-forward model"; leaving the right edge open keeps
    plurals and suffixes ("world models", "VLA-Adapter") matching.
    """
    tokens = [t for t in _TOKEN_GAP.split(_normalize(term)) if t]
    if not tokens:
        return False
    pattern = _TOKEN_GAP.pattern.join(re.escape(t) for t in tokens)
    return re.search(rf"(?<![a-z0-9{_JOIN}]){pattern}", text) is not None


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
                score += WEIGHT_HIGH
        for term in medium:
            if _hit(text, term):
                hits.append(f"M:{term}")
                score += WEIGHT_MEDIUM
        for term in cross:
            if _hit(text, term):
                hits.append(f"C:{term}")
                score += WEIGHT_CROSS

        author_hits = [a for a in p.authors if a.lower() in tracked_lower]
        if author_hits:
            hits.append(f"A:{','.join(author_hits)}")
            score += WEIGHT_AUTHOR

        # HF Papers list is curated, give a small bump.
        if p.source == "hf_papers":
            hits.append("S:hf_curated")
            score += 1.0
        # S2 author feed already filtered on tracked authors, bump too.
        if p.source == "semantic_scholar":
            score += 1.0

        out.append(PreScore(paper=p, score=score, hits=hits))
    return out


def candidate_lane(candidate: PreScore) -> str:
    """Which discovery lane a prescored paper competes in.

    Mirrors the bucket taxonomy the LLM later assigns, but decided from keyword
    hits alone so it can be used before any LLM call.
    """
    if any(h.startswith(("H:", "A:")) for h in candidate.hits):
        return "core"
    if candidate.score >= 0.5:
        return "adjacent"
    return "explore"


def select_for_llm(
    prescored: list[PreScore],
    mode: str = "strict",
    cap: int = 40,
    explore_fraction: float = 0.25,
    adjacent_fraction: float = 0.0,
) -> list[PreScore]:
    """Pick the top candidates that are worth spending LLM tokens on.

    strict: require score >= WEIGHT_HIGH (at least one high-priority hit).
    loose:  require score > 0  (any signal).
    broad:  split the budget across three lanes so one loud topic cannot crowd
            out the others:
              core     — has a high-priority keyword or a tracked author
              adjacent — weaker signal only (medium/cross keywords)
              explore  — no configured signal at all

            A global ranking by prescore would hand the whole budget to the core
            lane on any busy day: a VLA paper scores 10-25 while a neuroscience
            paper scores 1-3, so the cross-field reading this brief exists to
            surface would never reach the LLM. Unused slots in any lane flow to
            the others, so a quiet day still fills the cap.
    """
    cap = max(0, cap)

    def sort_key(candidate: PreScore) -> tuple:
        published = candidate.paper.published
        published_ord = published.toordinal() if published else 0
        return (-candidate.score, -published_ord, candidate.paper.title.lower())

    ranked = sorted(prescored, key=sort_key)
    if mode == "strict":
        return [c for c in ranked if c.score >= WEIGHT_HIGH][:cap]
    if mode == "loose":
        return [c for c in ranked if c.score >= 0.5][:cap]
    if mode != "broad":
        raise ValueError(f"Unknown filter mode: {mode}")

    core: list[PreScore] = []
    adjacent: list[PreScore] = []
    un_signaled: list[PreScore] = []
    by_lane = {"core": core, "adjacent": adjacent, "explore": un_signaled}
    for candidate in ranked:
        by_lane[candidate_lane(candidate)].append(candidate)

    # Stable hashing gives the exploration slice topical variety while keeping
    # reruns reproducible. Cross-day dedup advances through the remaining pool.
    un_signaled.sort(
        key=lambda candidate: hashlib.sha256(
            candidate.paper.key().encode("utf-8")
        ).digest()
    )

    def clamp(fraction: float) -> float:
        return max(0.0, min(1.0, fraction))

    explore_slots = min(len(un_signaled), round(cap * clamp(explore_fraction)))
    adjacent_slots = min(len(adjacent), round(cap * clamp(adjacent_fraction)))
    core_slots = max(0, cap - explore_slots - adjacent_slots)

    lanes = [(core, core_slots), (adjacent, adjacent_slots), (un_signaled, explore_slots)]
    selected: list[PreScore] = []
    taken = {id(lane): 0 for lane, _ in lanes}
    for lane, slots in lanes:
        picked = lane[:slots]
        taken[id(lane)] = len(picked)
        selected.extend(picked)

    # Backfill: a lane that could not fill its slots donates them, core first.
    for lane, _ in lanes:
        if len(selected) >= cap:
            break
        start = taken[id(lane)]
        selected.extend(lane[start : start + cap - len(selected)])
    return selected
