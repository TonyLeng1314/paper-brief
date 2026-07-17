"""LLM annotation: per-paper TLDR + personalized 'why relevant' + score.

Uses an OpenAI-compatible API (DeepSeek by default, routable through any proxy
that speaks the OpenAI chat-completions format).
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import re
from typing import Any

import openai

from sources import Paper

log = logging.getLogger(__name__)

ANNOTATION_INSTRUCTIONS = """You are scoring and annotating papers for the researcher whose profile is in the
system message above. Optimize for broad, high-quality discovery rather than
forcing every paper to support the researcher's current project.

You will receive a JSON array of papers. For EACH paper, output an object with:
- "key": the paper's dedup key (echo back exactly what was given)
- "title_zh": Chinese translation of the paper title. Keep technical English
  acronyms (JEPA / VLA / SE(3) / LoRA / VLM / DINOv2 / VICReg / SIGReg 等) as English.
  Method names with colons stay: e.g. "UWM-JEPA:在信念空间中想象的预测世界模型".
- "tldr": ONE sentence in CHINESE summarizing what the paper actually does.
- "why": ONE concrete sentence in CHINESE explaining why the paper is worth
  reading. The value may be direct utility, a transferable mechanism, or a new
  direction. Mention V3/LWv2 ONLY when there is a genuine specific connection.
  Do not force a current-project connection and do not default to "弱信号".
- "bucket": exactly one of "direct", "adjacent", or "explore", following the profile.
- "domain_fit": integer 0-10 for fit to the researcher's STABLE interests.
- "transfer_value": integer 0-10 for reusable method/evidence/tooling value.
- "novelty": integer 0-10 for horizon-expanding or assumption-challenging value.
- "score": integer 0-10 for overall reading priority. A high-novelty explore
  paper can score highly even without a direct current-project connection.

IMPORTANT: title_zh, tldr, why MUST be in Chinese (中文). Technical jargon stays English.

Output ONLY a JSON array, no preamble, no markdown fences. Schema:
[{"key":"...","title_zh":"...","tldr":"...","why":"...","bucket":"adjacent","domain_fit":6,"transfer_value":8,"novelty":7,"score":7}, ...]
"""


@dataclasses.dataclass
class Annotation:
    key: str
    tldr: str
    why: str
    score: int
    title_zh: str = ""
    bucket: str = "adjacent"
    domain_fit: int = 0
    transfer_value: int = 0
    novelty: int = 0


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
    model: str = "deepseek-v3.2",
    api_key: str | None = None,
    batch_size: int = 10,
) -> dict[str, Annotation]:
    """Annotate papers in small batches; returns mapping {paper.key() -> Annotation}.

    Reads OPENAI_API_KEY and (optionally) OPENAI_BASE_URL from the environment.
    DeepSeek auto-caches stable system-prompt prefixes, so daily reruns benefit
    automatically without any cache_control field.
    """
    if not papers:
        return {}

    base_url = os.environ.get("OPENAI_BASE_URL") or "https://api.deepseek.com/v1"
    client = openai.OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url,
        timeout=120.0,
        max_retries=2,
    )

    system_prompt = (
        "You are an expert research assistant curating a broad daily research "
        "brief for an embodied-intelligence researcher. Below is their long-form "
        "profile. Treat stable interests and the discovery policy as primary; "
        "the current project is only one optional lens.\n\n"
        "===== RESEARCHER PROFILE =====\n"
        + research_profile.strip()
        + "\n\n"
        + ANNOTATION_INSTRUCTIONS
    )

    out: dict[str, Annotation] = {}
    by_key = {p.key(): p for p in papers}

    for i in range(0, len(papers), batch_size):
        batch = papers[i : i + batch_size]
        batch_payload = json.dumps([_paper_to_dict(p) for p in batch], ensure_ascii=False)

        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=8000,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Annotate the following {len(batch)} papers:\n\n{batch_payload}",
                    },
                ],
            )
        except Exception as e:
            log.error("LLM call failed for batch %d-%d: %s", i, i + len(batch), e)
            continue

        usage = getattr(resp, "usage", None)
        if usage:
            log.info(
                "batch %d: prompt=%d completion=%d total=%d",
                i // batch_size,
                getattr(usage, "prompt_tokens", 0),
                getattr(usage, "completion_tokens", 0),
                getattr(usage, "total_tokens", 0),
            )

        text = resp.choices[0].message.content or ""
        try:
            items = _extract_json_array(text)
        except (ValueError, json.JSONDecodeError) as e:
            log.warning("Could not parse batch %d: %s", i // batch_size, e)
            continue

        for it in items:
            k = it.get("key")
            if not k or k not in by_key:
                continue

            def score_field(name: str) -> int:
                try:
                    value = int(it.get(name, 0))
                except (TypeError, ValueError):
                    value = 0
                return max(0, min(10, value))

            bucket = str(it.get("bucket", "adjacent")).strip().lower()
            if bucket not in {"direct", "adjacent", "explore"}:
                bucket = "adjacent"
            out[k] = Annotation(
                key=k,
                tldr=str(it.get("tldr", "")).strip(),
                why=str(it.get("why", "")).strip(),
                score=score_field("score"),
                title_zh=str(it.get("title_zh", "")).strip(),
                bucket=bucket,
                domain_fit=score_field("domain_fit"),
                transfer_value=score_field("transfer_value"),
                novelty=score_field("novelty"),
            )

    return out
