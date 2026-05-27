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
system message above.

You will receive a JSON array of papers. For EACH paper, output an object with:
- "key": the paper's dedup key (echo back exactly what was given)
- "title_zh": Chinese translation of the paper title. Keep technical English
  acronyms (JEPA / VLA / SE(3) / LoRA / VLM / DINOv2 / VICReg / SIGReg 等) as English.
  Method names with colons stay: e.g. "UWM-JEPA:在信念空间中想象的预测世界模型".
- "tldr": ONE sentence in CHINESE summarizing what the paper actually does.
- "why": ONE sentence in CHINESE naming the SPECIFIC open question from the
  researcher's profile that this paper could inform. If the connection is weak,
  start with "弱信号:". Be concrete. Bad: "和你的 SSL 工作相关"。
  Good: "在 I-JEPA 式 setup 里 ablate 了 predictor depth,正是你 V3 还没扫过的变量"。
  Technical terms keep English.
- "score": integer 0-10, following the relevance tiers in the profile.

IMPORTANT: title_zh, tldr, why MUST be in Chinese (中文). Technical jargon stays English.

Output ONLY a JSON array, no preamble, no markdown fences. Schema:
[{"key": "...", "title_zh": "...", "tldr": "...", "why": "...", "score": 7}, ...]
"""


@dataclasses.dataclass
class Annotation:
    key: str
    tldr: str
    why: str
    score: int
    title_zh: str = ""


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
    model: str = "deepseek-chat",
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
        "You are an expert research assistant who helps a VLA researcher triage "
        "their daily paper firehose. Below is their long-form research profile. "
        "It will not change between requests in this session — use it as the "
        "ground truth for what 'relevant' means.\n\n"
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
            try:
                score = int(it.get("score", 0))
            except (TypeError, ValueError):
                score = 0
            out[k] = Annotation(
                key=k,
                tldr=str(it.get("tldr", "")).strip(),
                why=str(it.get("why", "")).strip(),
                score=max(0, min(10, score)),
                title_zh=str(it.get("title_zh", "")).strip(),
            )

    return out
