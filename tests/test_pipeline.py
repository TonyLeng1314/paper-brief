from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import annotate as annotate_module
import deep_annotate as deep_annotate_module
from annotate import Annotation, is_model_unavailable_error
from fetch_papers import load_seen, save_seen, select_by_bucket
from filter import PreScore, select_for_llm
from render import render_day
from sources import Paper


def paper(name: str, arxiv_id: str | None = None) -> Paper:
    return Paper(
        title=name,
        authors=[],
        abstract="",
        arxiv_id=arxiv_id,
        url="https://example.com",
        source="arxiv",
        published=dt.date(2026, 7, 17),
    )


class CandidateSelectionTests(unittest.TestCase):
    def test_broad_mode_reserves_zero_signal_exploration(self) -> None:
        signaled = [PreScore(paper(f"core-{i}"), 3.0, ["H:robot"]) for i in range(20)]
        un_signaled = [PreScore(paper(f"explore-{i}"), 0.0, []) for i in range(10)]

        selected = select_for_llm(
            signaled + un_signaled,
            mode="broad",
            cap=10,
            explore_fraction=0.3,
        )

        self.assertEqual(len(selected), 10)
        self.assertEqual(sum(item.score == 0 for item in selected), 3)

    def test_bucket_quotas_preserve_each_discovery_lane(self) -> None:
        items = []
        for bucket, count in (("direct", 5), ("adjacent", 5), ("explore", 5)):
            for index in range(count):
                p = paper(f"{bucket}-{index}")
                ps = PreScore(p, 1.0, [])
                annotation = Annotation(
                    key=p.key(),
                    tldr="tldr",
                    why="why",
                    score=8 - index,
                    bucket=bucket,
                    domain_fit=7,
                    transfer_value=7,
                    novelty=7,
                )
                items.append((ps, annotation))

        selected = select_by_bucket(
            items,
            min_score=4,
            max_papers=6,
            quotas={"direct": 2, "adjacent": 2, "explore": 2},
        )

        self.assertEqual(len(selected), 6)
        self.assertEqual([item[1].bucket for item in selected].count("direct"), 2)
        self.assertEqual([item[1].bucket for item in selected].count("adjacent"), 2)
        self.assertEqual([item[1].bucket for item in selected].count("explore"), 2)


class ConfigurationTests(unittest.TestCase):
    def test_broad_discovery_and_v4_flash_models_are_enabled(self) -> None:
        config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

        self.assertEqual(config["filter"]["mode"], "broad")
        self.assertGreater(config["filter"]["explore_fraction"], 0)
        self.assertEqual(
            sum(config["filter"]["bucket_quotas"].values()),
            config["filter"]["max_papers_per_day"],
        )
        self.assertEqual(config["llm"]["triage_model"], "deepseek-v4-flash")
        self.assertEqual(config["llm"]["deep_read_model"], "deepseek-v4-flash")
        self.assertFalse(config["llm"]["triage_thinking"])
        self.assertTrue(config["llm"]["deep_read_thinking"])

    def test_unroutable_model_errors_are_fatal(self) -> None:
        error = RuntimeError(
            "No available channel for model deepseek-v3.2 "
            "(code: model_not_found)"
        )
        self.assertTrue(is_model_unavailable_error(error))
        self.assertFalse(is_model_unavailable_error(TimeoutError("request timed out")))


class DeepSeekRequestTests(unittest.TestCase):
    def test_triage_disables_thinking_and_keeps_temperature(self) -> None:
        p = paper("Embodied world model", "2607.11111")
        response_content = json.dumps(
            [
                {
                    "key": p.key(),
                    "title_zh": "具身世界模型",
                    "tldr": "摘要",
                    "why": "阅读价值",
                    "bucket": "direct",
                    "domain_fit": 9,
                    "transfer_value": 8,
                    "novelty": 7,
                    "score": 8,
                }
            ],
            ensure_ascii=False,
        )
        completions = Mock()
        completions.create.return_value = SimpleNamespace(
            usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content=response_content))],
        )
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        with patch.object(annotate_module.openai, "OpenAI", return_value=client):
            result = annotate_module.annotate_papers(
                [p], "profile", api_key="test", thinking=False
            )

        request = completions.create.call_args.kwargs
        self.assertEqual(request["model"], "deepseek-v4-flash")
        self.assertEqual(request["extra_body"]["thinking"]["type"], "disabled")
        self.assertEqual(request["temperature"], 0.2)
        self.assertIn(p.key(), result)

    def test_deep_read_enables_thinking_without_temperature(self) -> None:
        p = paper("Embodied world model", "2607.22222")
        completions = Mock()
        completions.create.return_value = SimpleNamespace(
            usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
        )
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(deep_annotate_module.openai, "OpenAI", return_value=client),
                patch.object(
                    deep_annotate_module,
                    "fetch_pdf_text",
                    return_value="full paper text",
                ),
            ):
                deep_annotate_module.deep_annotate_papers(
                    [p], "profile", api_key="test", cache_dir=Path(tmp), thinking=True
                )

        request = completions.create.call_args.kwargs
        self.assertEqual(request["model"], "deepseek-v4-flash")
        self.assertEqual(request["extra_body"]["thinking"]["type"], "enabled")
        self.assertNotIn("temperature", request)


class SeenStateTests(unittest.TestCase):
    def test_existing_posts_seed_seen_state_and_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            posts = root / "posts"
            posts.mkdir()
            (posts / "2026-07-16.json").write_text(
                json.dumps(
                    {
                        "date": "2026-07-16",
                        "papers": [
                            {"arxiv_id": "2607.12345", "title": "Arxiv paper"},
                            {"arxiv_id": None, "title": "Title Only!"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            state_path = root / "seen.json"
            seen = load_seen(state_path, posts)
            self.assertEqual(seen["arxiv:2607.12345"], "2026-07-16")
            self.assertEqual(seen["title:titleonly"], "2026-07-16")

            seen["arxiv:2607.99999"] = "2026-07-17"
            save_seen(state_path, seen)
            reloaded = load_seen(state_path, root / "missing-posts")
            self.assertEqual(reloaded, seen)


class RenderTests(unittest.TestCase):
    def test_render_includes_discovery_metadata_and_funnel(self) -> None:
        p = paper("A useful world model", "2607.00001")
        ps = PreScore(p, 3.0, ["H:world model"])
        annotation = Annotation(
            key=p.key(),
            title_zh="一个有用的世界模型",
            tldr="摘要",
            why="阅读价值",
            score=8,
            bucket="direct",
            domain_fit=9,
            transfer_value=8,
            novelty=7,
        )

        with tempfile.TemporaryDirectory() as tmp:
            output = render_day(
                dt.date(2026, 7, 17),
                [(ps, annotation)],
                {},
                Path(tmp),
                reviewed=10,
                min_score=4,
                funnel={"fetched": 100, "unseen": 80, "llm_candidates": 50, "annotated": 50},
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["papers"][0]["key"], "arxiv:2607.00001")
        self.assertEqual(payload["papers"][0]["bucket"], "direct")
        self.assertEqual(payload["papers"][0]["novelty"], 7)
        self.assertEqual(payload["funnel"]["unseen"], 80)


if __name__ == "__main__":
    unittest.main()
