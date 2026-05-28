"""Stage-2 deep annotation: read the PDF full text, produce structured summary.

Runs only on papers that passed stage-1 (`a.score >= min_score`, top
`max_papers_per_day`). One LLM call per paper, cached to disk at
`cache/deep/{arxiv_id}.json` for forever-reuse.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
from pathlib import Path
from typing import Any

import openai

from deep_read import _safe_id, fetch_pdf_text
from sources import Paper

log = logging.getLogger(__name__)


DEEP_INSTRUCTIONS = """You will receive ONE paper as JSON with: key / title / abstract / full_text.
full_text is the paper's PDF body (may be truncated, may contain extraction noise).

Read it carefully, then output ONE JSON object (no array, no markdown fences,
no prose) with these EXACT keys, all values in CHINESE 中文 (keep technical
English jargon: VLA / JEPA / SE(3) / LoRA / LIBERO / RoboTwin / DINOv2 / etc):

{
  "problem":            "1-2 句:这篇论文要解决什么核心问题",
  "method":             "2-4 句:核心算法 / 架构 / 训练目标。具体到模块名",
  "key_contributions":  ["贡献 1 (一句)", "贡献 2", ...]  // 2-4 条
  "sim_benchmarks":     ["LIBERO", "RoboTwin", ...]      // 用到的仿真/bench; 没有则 []
  "real_robot":         "真机设置:机器人型号 + 任务 + 数据规模。没做实验则填 '未做真机实验'",
  "datasets":           "预训练/主训练数据(OXE / DROID / Ego4D 等)。没说则 '未说明'",
  "compute":            "训练算力 / 模型规模(参数量 / GPU·days)。没说则 '未说明'",
  "results_headline":   "一句话:主要数值结果与 baseline 对比的关键数字",
  "baselines":          ["baseline 方法 1", "baseline 方法 2", ...]
  "limitations":        "1-2 句:作者承认或可读出的局限",
  "code_release":       "开源情况:github URL / 仅 inference / 未开源 / 论文未提",
  "relevance_detail":   "结合 system 里的研究者 profile,这篇论文跟他研究的具体连接。指到具体 section/table/ablation,不要说空话",
  "followup":           "如果值得深读,看哪节 / 表 / 附录。1 句"
}

Rules:
- 全部用中文写。English 技术术语保留原文。
- 数字要具体(SR 86→91,而不是"有提升")。
- relevance_detail 不许写"和你的研究有关"这种废话,要指出具体连接点。
- 找不到对应信息时,字段写 "论文未明确说明" 而不是瞎编。
- Output **ONLY** the JSON object. No preamble. No markdown.
"""


@dataclasses.dataclass
class DeepAnnotation:
    key: str
    problem: str = ""
    method: str = ""
    key_contributions: list[str] = dataclasses.field(default_factory=list)
    sim_benchmarks: list[str] = dataclasses.field(default_factory=list)
    real_robot: str = ""
    datasets: str = ""
    compute: str = ""
    results_headline: str = ""
    baselines: list[str] = dataclasses.field(default_factory=list)
    limitations: str = ""
    code_release: str = ""
    relevance_detail: str = ""
    followup: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _extract_json_object(text: str) -> dict:
    """Tolerant JSON-object extraction (the deep prompt asks for an object, not array)."""
    import re

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"Could not extract JSON object from model output:\n{text[:500]}")
    return json.loads(m.group(0))


def _cache_path(arxiv_id: str, cache_dir: Path) -> Path:
    return cache_dir / "deep" / f"{_safe_id(arxiv_id)}.json"


def _load_cached(arxiv_id: str, cache_dir: Path) -> dict | None:
    fp = _cache_path(arxiv_id, cache_dir)
    if not fp.exists():
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("deep cache read failed for %s: %s", arxiv_id, e)
        return None


def _save_cached(arxiv_id: str, data: dict, cache_dir: Path) -> None:
    fp = _cache_path(arxiv_id, cache_dir)
    try:
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        log.warning("deep cache write failed for %s: %s", arxiv_id, e)


def _ann_from_dict(key: str, d: dict) -> DeepAnnotation:
    def s(field: str) -> str:
        v = d.get(field, "")
        return str(v).strip() if v is not None else ""

    def lst(field: str) -> list[str]:
        v = d.get(field) or []
        if isinstance(v, str):
            v = [v]
        return [str(x).strip() for x in v if str(x).strip()]

    return DeepAnnotation(
        key=key,
        problem=s("problem"),
        method=s("method"),
        key_contributions=lst("key_contributions"),
        sim_benchmarks=lst("sim_benchmarks"),
        real_robot=s("real_robot"),
        datasets=s("datasets"),
        compute=s("compute"),
        results_headline=s("results_headline"),
        baselines=lst("baselines"),
        limitations=s("limitations"),
        code_release=s("code_release"),
        relevance_detail=s("relevance_detail"),
        followup=s("followup"),
    )


def deep_annotate_papers(
    papers: list[Paper],
    research_profile: str,
    model: str = "deepseek-chat",
    api_key: str | None = None,
    cache_dir: Path = Path("cache"),
) -> dict[str, DeepAnnotation]:
    """For each paper with an arxiv_id: fetch PDF, full-text annotate, cache.

    Sequential. Per-paper failures swallowed — caller still gets a (possibly
    empty) mapping and renders the day's JSON regardless.
    """
    if not papers:
        return {}

    base_url = os.environ.get("OPENAI_BASE_URL") or "https://api.deepseek.com/v1"
    client = openai.OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url,
        timeout=180.0,
        max_retries=2,
    )
    system_prompt = (
        "You are an expert research assistant who reads the FULL TEXT of an "
        "arxiv paper and produces a structured Chinese summary tailored to the "
        "researcher whose profile is below. The profile will not change between "
        "requests — use it as ground truth for what 'relevant' means.\n\n"
        "===== RESEARCHER PROFILE =====\n"
        + research_profile.strip()
        + "\n\n"
        + DEEP_INSTRUCTIONS
    )

    out: dict[str, DeepAnnotation] = {}

    for i, p in enumerate(papers):
        if not p.arxiv_id:
            log.info("[deep %d/%d] %s — no arxiv_id, skip", i + 1, len(papers), p.title[:60])
            continue

        cached = _load_cached(p.arxiv_id, cache_dir)
        if cached:
            log.info("[deep %d/%d] %s — cache hit", i + 1, len(papers), p.arxiv_id)
            out[p.key()] = _ann_from_dict(p.key(), cached)
            continue

        log.info("[deep %d/%d] %s — fetching PDF", i + 1, len(papers), p.arxiv_id)
        full_text = fetch_pdf_text(p.arxiv_id, cache_dir)
        if not full_text:
            log.warning("[deep %d/%d] %s — no full text, skip", i + 1, len(papers), p.arxiv_id)
            continue

        user_payload = json.dumps(
            {
                "key": p.key(),
                "title": p.title,
                "abstract": p.abstract[:2000],
                "full_text": full_text,
            },
            ensure_ascii=False,
        )

        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=8000,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_payload},
                ],
            )
        except Exception as e:
            log.error("[deep %d/%d] %s — LLM call failed: %s",
                      i + 1, len(papers), p.arxiv_id, e)
            continue

        usage = getattr(resp, "usage", None)
        if usage:
            log.info(
                "[deep %d/%d] %s — prompt=%d completion=%d",
                i + 1, len(papers), p.arxiv_id,
                getattr(usage, "prompt_tokens", 0),
                getattr(usage, "completion_tokens", 0),
            )

        text = resp.choices[0].message.content or ""
        try:
            data = _extract_json_object(text)
        except (ValueError, json.JSONDecodeError) as e:
            log.warning("[deep %d/%d] %s — JSON parse failed: %s",
                        i + 1, len(papers), p.arxiv_id, e)
            continue

        ann = _ann_from_dict(p.key(), data)
        out[p.key()] = ann
        _save_cached(p.arxiv_id, ann.to_dict(), cache_dir)

    return out
