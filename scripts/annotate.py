"""LLM annotation: per-paper TLDR + personalized 'why relevant' + score.

Uses Anthropic prompt caching: the research profile is stable across days, so we
cache it in the system prompt and only the paper batch varies per request.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import re
from typing import Any

import anthropic

from sources import Paper

log = logging.getLogger(__name__)

ANNOTATION_INSTRUCTIONS = """You are scoring and annotating papers for the researcher whose profile is in the
cached system context above.

You will receive a JSON array of papers. For EACH paper, output an object with:
- "key": the paper's dedup key (echo back exactly what was given)
- "tldr": one sentence, what the paper actually does
- "why": one sentence naming the SPECIFIC open question from the researcher's profile
  that this paper could inform. If the connection is weak, start with "weak signal:".
  Be concrete. Bad: "relevant to your SSL work". Good: "ablates predictor depth in
  I-JEPA-style setups, exactly the variable you have not swept in V3 yet."
- "score": integer 0-10, following the relevance tiers in the profile.

Output ONLY a JSON array, no preamble, no markdown fences. Schema:
[{"key": "...", "tldr": "...", "why": "...", "score": 7}, ...]
"""


@dataclasses.dataclass
class Annotation:
    key: str
    tldr: str
    why: str
    score: int


def _paper_to_dict(p: Paper) -> dict[str, Any]:
    return {
        "key": p.key(),
        "title": p.title,
        "authors": p.authors[:6],  # don't blow tokens on 50-author lists
        "abstract": p.abstract[:2000],  # cap to avoid runaway prompts
        "source": p.source,
        "arxiv_id": p.arxiv_id,
    }


def _extract_json_array(text: str) -> list[dict]:
    """Tolerant JSON-array extraction in case the model adds stray prose."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if not m:
        raise ValueError(f"Could not extract JSON array from model output:\n{text[:500]}")
    return json.loads(m.group(0))


def annotate_papers(
    papers: list[Paper],
    research_profile: str,
    model: str = "claude-sonnet-4-6",
    api_key: str | None = None,
    batch_size: int = 5,
) -> dict[str, Annotation]:
    """Annotate papers in small batches; returns mapping {paper.key() -> Annotation}.

    Research profile is cached via cache_control so daily reruns hit the cache.
    """
    if not papers:
        return {}

    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    client = anthropic.Anthropic(
        api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
        base_url=base_url if base_url else None,
    )

    system_blocks = [
        {
            "type": "text",
            "text": "You are an expert research assistant who helps a VLA researcher "
            "triage their daily paper firehose. Below is their long-form research profile. "
            "It will not change between requests in this session — use it as the ground "
            "truth for what 'relevant' means.\n\n"
            "===== RESEARCHER PROFILE =====\n" + research_profile.strip(),
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": ANNOTATION_INSTRUCTIONS,
        },
    ]

    out: dict[str, Annotation] = {}
    by_key = {p.key(): p for p in papers}

    for i in range(0, len(papers), batch_size):
        batch = papers[i : i + batch_size]
        batch_payload = json.dumps([_paper_to_dict(p) for p in batch], ensure_ascii=False)

        try:
            resp = client.messages.create(
                model=model,
                max_tokens=4000,
                system=system_blocks,
                messages=[
                    {
                        "role": "user",
                        "content": f"Annotate the following {len(batch)} papers:\n\n{batch_payload}",
                    }
                ],
            )
        except Exception as e:
            log.error("LLM call failed for batch %d-%d: %s", i, i + len(batch), e)
            continue

        usage = getattr(resp, "usage", None)
        if usage:
            log.info(
                "batch %d: input=%d cache_read=%d cache_write=%d output=%d",
                i // batch_size,
                getattr(usage, "input_tokens", 0),
                getattr(usage, "cache_read_input_tokens", 0),
                getattr(usage, "cache_creation_input_tokens", 0),
                getattr(usage, "output_tokens", 0),
            )

        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        try:
            items = _extract_json_array(text)
        except (ValueError, json.JSONDecodeError) as e:
            log.warning("Could not parse batch %d: %s", i // batch_size, e)
            continue

        for it in items:
            k = it.get("key")
            if not k or k not in by_key:
                continue
            try:
                score = int(it.get("score", 0))
            except (TypeError, ValueError):
                score = 0
            out[k] = Annotation(
                key=k,
                tldr=str(it.get("tldr", "")).strip(),
                why=str(it.get("why", "")).strip(),
                score=max(0, min(10, score)),
            )

    return out
