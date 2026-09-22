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
from annotate import (
    Annotation,
    QuotaExhaustedError,
    is_model_unavailable_error,
    is_quota_error,
)
from fetch_papers import ArxivFeedError, gather, load_seen, save_seen, select_by_bucket
from filter import PreScore, prescore, select_for_llm
from render import render_day
from sources import ArxivFetch, Paper, build_topic_query, topic_lanes_from_config


def paper(name: str, arxiv_id: str | None = None, abstract: str = "") -> Paper:
    return Paper(
        title=name,
        authors=[],
        abstract=abstract,
        arxiv_id=arxiv_id,
        url="https://example.com",
        source="arxiv",
        published=dt.date(2026, 7, 17),
    )


class KeywordMatchingTests(unittest.TestCase):
    def test_hyphenated_and_plural_forms_match_spaced_keywords(self) -> None:
        p = paper("A Vision-Language-Action survey", abstract="We study world models.")
        scored = prescore([p], high=["vision language action", "world model"],
                          medium=[], cross=[], tracked_authors=[])[0]

        self.assertIn("H:vision language action", scored.hits)
        self.assertIn("H:world model", scored.hits)

    def test_left_boundary_blocks_mid_word_acronym_hits(self) -> None:
        p = paper("Nonvla tricks and memorization", abstract="")
        scored = prescore([p], high=["VLA"], medium=[], cross=[], tracked_authors=[])[0]

        self.assertEqual(scored.hits, [])

    def test_keyword_cannot_start_inside_a_hyphenated_compound(self) -> None:
        # "feed-forward" folds to "feed forward", which used to hand the
        # motor-control term "forward model" to 3D reconstruction papers.
        decoy = paper("A feed-forward model for 3D reconstruction", abstract="")
        real = paper("Cerebellar forward models in reaching", abstract="")
        scored = prescore(
            [decoy, real], high=[], medium=["forward model"], cross=[], tracked_authors=[]
        )

        self.assertEqual(scored[0].hits, [])
        self.assertIn("M:forward model", scored[1].hits)

    def test_keyword_may_still_end_across_a_hyphen(self) -> None:
        p = paper("Scaling world-models for control", abstract="")
        scored = prescore([p], high=["world model"], medium=[], cross=[],
                          tracked_authors=[])[0]

        self.assertIn("H:world model", scored.hits)

    def test_one_high_priority_hit_outranks_a_stack_of_generic_ones(self) -> None:
        on_topic = paper("A VLA policy", abstract="")
        generic = paper(
            "Generic ML",
            abstract="planning memory uncertainty representation learning",
        )
        scored = prescore(
            [on_topic, generic],
            high=["VLA"],
            medium=[],
            cross=["planning", "memory", "uncertainty", "representation learning"],
            tracked_authors=[],
        )

        self.assertGreater(scored[0].score, scored[1].score)


class ArxivSourceTests(unittest.TestCase):
    def test_topic_query_combines_categories_and_terms(self) -> None:
        query = build_topic_query(["cs.LG", "cs.CV"], ["world model", "VLA"])

        self.assertEqual(
            query, '(cat:cs.LG OR cat:cs.CV) AND (abs:"world model" OR abs:"VLA")'
        )

    def test_each_lane_keeps_its_own_categories(self) -> None:
        lanes = topic_lanes_from_config(
            {
                "topic_categories": ["cs.LG"],
                "topic_lanes": [
                    {"name": "embodied", "categories": ["cs.CV"], "terms": ["VLA"]},
                    {"name": "neuro", "categories": ["q-bio.NC"], "terms": ["replay"]},
                    {"name": "inherits", "terms": ["JEPA"]},
                    {"name": "empty", "categories": ["cs.AI"], "terms": []},
                ],
            }
        )

        self.assertEqual([l.name for l in lanes], ["embodied", "neuro", "inherits"])
        self.assertEqual(lanes[1].categories, ["q-bio.NC"])
        self.assertEqual(lanes[2].categories, ["cs.LG"])

    def test_flat_topic_config_still_works(self) -> None:
        lanes = topic_lanes_from_config(
            {"topic_categories": ["cs.LG"], "topic_terms": ["world model"]}
        )

        self.assertEqual(len(lanes), 1)
        self.assertEqual(lanes[0].terms, ["world model"])

    def test_total_arxiv_failure_aborts_instead_of_publishing(self) -> None:
        cfg = {
            "sources": {
                "arxiv": {"enabled": True, "categories": ["cs.RO"], "required": True},
                "huggingface_papers": {"enabled": False},
                "semantic_scholar_authors": {"enabled": False},
            }
        }
        broken = ArxivFetch(papers=[], attempted=3, failed=["cs.RO", "t1", "t2"])

        with patch("fetch_papers.fetch_arxiv", return_value=broken):
            with self.assertRaises(ArxivFeedError):
                gather(cfg)

    def test_partial_arxiv_failure_still_publishes(self) -> None:
        cfg = {
            "sources": {
                "arxiv": {"enabled": True, "categories": ["cs.RO"], "required": True},
                "huggingface_papers": {"enabled": False},
                "semantic_scholar_authors": {"enabled": False},
            }
        }
        partial = ArxivFetch(
            papers=[paper("Survived", "2607.00007")], attempted=3, failed=["t2"]
        )

        with (
            patch("fetch_papers.fetch_arxiv", return_value=partial),
            patch("fetch_papers.enrich_arxiv_metadata"),
        ):
            self.assertEqual(len(gather(cfg)), 1)


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

    def test_weak_signal_lane_survives_a_flood_of_core_papers(self) -> None:
        # A busy VLA day: 200 high-scoring core papers against a handful of
        # neuroscience ones that only ever hit medium keywords.
        core = [PreScore(paper(f"vla-{i}"), 20.0, ["H:VLA"]) for i in range(200)]
        neuro = [
            PreScore(paper(f"neuro-{i}"), 2.0, ["M:predictive coding"])
            for i in range(20)
        ]

        selected = select_for_llm(
            core + neuro,
            mode="broad",
            cap=10,
            explore_fraction=0.0,
            adjacent_fraction=0.3,
        )

        self.assertEqual(len(selected), 10)
        self.assertEqual(sum("neuro" in item.paper.title for item in selected), 3)

    def test_unused_weak_signal_slots_go_back_to_the_core_lane(self) -> None:
        core = [PreScore(paper(f"vla-{i}"), 20.0, ["H:VLA"]) for i in range(20)]
        neuro = [PreScore(paper("neuro-0"), 2.0, ["M:motor control"])]

        selected = select_for_llm(
            core + neuro,
            mode="broad",
            cap=10,
            explore_fraction=0.0,
            adjacent_fraction=0.3,
        )

        self.assertEqual(len(selected), 10)
        self.assertEqual(sum("neuro" in item.paper.title for item in selected), 1)

    def test_tracked_author_hits_rank_in_the_core_lane(self) -> None:
        core = [PreScore(paper(f"vla-{i}"), 20.0, ["H:VLA"]) for i in range(20)]
        tracked = PreScore(paper("by-a-tracked-author"), 5.0, ["A:Yann LeCun"])
        neuro = [
            PreScore(paper(f"neuro-{i}"), 2.0, ["M:motor control"]) for i in range(10)
        ]

        selected = select_for_llm(
            core + [tracked] + neuro,
            mode="broad",
            cap=10,
            explore_fraction=0.0,
            adjacent_fraction=0.5,
        )

        # A tracked author is a strong signal, so it competes in core (and here
        # loses to 20 higher-scoring papers) rather than eating a reserved
        # weak-signal slot that neuroscience work depends on.
        self.assertNotIn(tracked, selected)
        self.assertEqual(sum("neuro" in item.paper.title for item in selected), 5)

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

    def test_core_field_leads_without_starving_the_inspiration_lanes(self) -> None:
        config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        quotas = config["filter"]["bucket_quotas"]

        # `direct` is the largest single lane...
        self.assertGreater(quotas["direct"], quotas["adjacent"])
        self.assertGreater(quotas["adjacent"], quotas["explore"])
        # ...but adjacent + explore stay a substantial share; they are where
        # cross-field inspiration (neuroscience especially) lands.
        self.assertGreaterEqual(
            quotas["adjacent"] + quotas["explore"],
            config["filter"]["max_papers_per_day"] // 2,
        )

    def test_large_categories_are_searched_by_topic_not_by_recency(self) -> None:
        config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        arxiv_cfg = config["sources"]["arxiv"]
        lanes = topic_lanes_from_config(arxiv_cfg)
        searched = {c for lane in lanes for c in lane.categories}

        # Recency sampling of cs.CV/cs.LG only sees the last couple of hours.
        for firehose_only in ("cs.CV", "cs.LG"):
            self.assertNotIn(firehose_only, arxiv_cfg["categories"])
            self.assertIn(firehose_only, searched)
        self.assertTrue(lanes)
        self.assertTrue(arxiv_cfg["required"])

    def test_neuroscience_is_searched_where_neuroscience_is_posted(self) -> None:
        config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        lanes = {l.name: l for l in topic_lanes_from_config(config["sources"]["arxiv"])}
        medium = {t.lower() for t in config["keywords"]["medium_priority"]}

        self.assertIn("neuro", lanes)
        # Loose terms like "replay" only work when a narrow category filters for
        # them; mixed into the CS categories they return RL replay buffers.
        self.assertEqual(lanes["neuro"].categories, ["q-bio.NC"])
        self.assertIn("replay", [t.lower() for t in lanes["neuro"].terms])
        self.assertNotIn(
            "replay",
            [t.lower() for t in lanes["neuro-in-ml"].terms],
            "loose term leaked into a lane with no category filter",
        )

        for term in ("predictive coding", "active inference", "grid cells"):
            self.assertIn(term, [t.lower() for t in lanes["neuro"].terms])
            self.assertIn(term, medium, f"{term} missing from ranking keywords")

        # Fetching neuroscience is not enough: without a reserved share of the
        # candidate pool it is ranked out by high-priority VLA papers long before
        # the LLM ever sees it.
        self.assertGreater(config["filter"]["adjacent_fraction"], 0)

    def test_profile_and_prompt_both_ask_for_cross_field_inspiration(self) -> None:
        profile = (ROOT / "research_profile.md").read_text(encoding="utf-8").lower()

        self.assertIn("neuroscience", profile)
        self.assertIn("predictive coding", profile)
        self.assertIn("neuroscience", annotate_module.ANNOTATION_INSTRUCTIONS.lower())

    def test_each_keyword_belongs_to_exactly_one_weight_tier(self) -> None:
        config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        kw = config["keywords"]
        tiers = {
            name: [t.lower() for t in kw[name]]
            for name in ("high_priority", "medium_priority", "cross_domain")
        }

        for name, terms in tiers.items():
            self.assertEqual(
                len(terms), len(set(terms)), f"duplicate term within {name}"
            )
        # A term in two tiers silently sums both weights, so the tiers stop
        # meaning what the comments say they mean.
        for a, b in (
            ("high_priority", "medium_priority"),
            ("high_priority", "cross_domain"),
            ("medium_priority", "cross_domain"),
        ):
            self.assertEqual(
                set(tiers[a]) & set(tiers[b]), set(), f"{a} and {b} share terms"
            )

    def test_unroutable_model_errors_are_fatal(self) -> None:
        error = RuntimeError(
            "No available channel for model deepseek-v3.2 "
            "(code: model_not_found)"
        )
        self.assertTrue(is_model_unavailable_error(error))
        self.assertFalse(is_model_unavailable_error(TimeoutError("request timed out")))

    def test_out_of_credit_is_told_apart_from_rate_limiting(self) -> None:
        self.assertTrue(is_quota_error(RuntimeError("Error code: 402 - insufficient_quota")))
        self.assertTrue(is_quota_error(RuntimeError("账户余额不足，请充值")))
        self.assertFalse(is_quota_error(RuntimeError("429 rate_limit_exceeded, retry later")))


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


def _reply(content: str, finish_reason: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(
        usage=None,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ],
    )


def _annotation_json(p: Paper) -> dict:
    return {
        "key": p.key(),
        "title_zh": "标题",
        "tldr": "摘要",
        "why": "阅读价值",
        "bucket": "direct",
        "domain_fit": 9,
        "transfer_value": 8,
        "novelty": 7,
        "score": 8,
    }


class BatchRecoveryTests(unittest.TestCase):
    """A bad reply must cost its own papers, not the whole batch."""

    def test_unparsable_batch_is_split_and_retried(self) -> None:
        papers = [paper(f"p{i}", f"2607.0000{i}") for i in range(4)]
        completions = Mock()

        def fake_create(**kwargs):
            body = kwargs["messages"][1]["content"]
            batch = [p for p in papers if p.key() in body]
            if len(batch) == len(papers):
                return _reply("I cannot comply.")  # whole-batch failure
            return _reply(json.dumps([_annotation_json(p) for p in batch],
                                     ensure_ascii=False))

        completions.create.side_effect = fake_create
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        with patch.object(annotate_module.openai, "OpenAI", return_value=client):
            result = annotate_module.annotate_papers(
                papers, "profile", api_key="test", batch_size=4
            )

        self.assertEqual(len(result), 4)

    def test_truncated_reply_keeps_whole_objects_and_retries_the_rest(self) -> None:
        papers = [paper(f"p{i}", f"2607.0001{i}") for i in range(4)]
        completions = Mock()
        calls: list[int] = []

        def fake_create(**kwargs):
            body = kwargs["messages"][1]["content"]
            batch = [p for p in papers if p.key() in body]
            calls.append(len(batch))
            payload = json.dumps([_annotation_json(p) for p in batch], ensure_ascii=False)
            if len(batch) == len(papers):
                # Cut mid-object, the way a max_tokens stop looks.
                cut = payload.index(papers[2].key()) - 10
                return _reply(payload[:cut], finish_reason="length")
            return _reply(payload)

        completions.create.side_effect = fake_create
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        with patch.object(annotate_module.openai, "OpenAI", return_value=client):
            result = annotate_module.annotate_papers(
                papers, "profile", api_key="test", batch_size=4
            )

        self.assertEqual(len(result), 4)
        self.assertGreater(len(calls), 1)

    def test_single_paper_failure_does_not_recurse_forever(self) -> None:
        papers = [paper("only", "2607.00099")]
        completions = Mock()
        completions.create.return_value = _reply("nope")
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        with patch.object(annotate_module.openai, "OpenAI", return_value=client):
            result = annotate_module.annotate_papers(
                papers, "profile", api_key="test", batch_size=1
            )

        self.assertEqual(result, {})
        self.assertEqual(completions.create.call_count, 1)

    def test_quota_exhaustion_aborts_the_run(self) -> None:
        papers = [paper(f"p{i}", f"2607.0002{i}") for i in range(4)]
        completions = Mock()
        completions.create.side_effect = RuntimeError(
            "Error code: 402 - {'message': 'Insufficient Balance'}"
        )
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        with patch.object(annotate_module.openai, "OpenAI", return_value=client):
            with self.assertRaises(QuotaExhaustedError):
                annotate_module.annotate_papers(
                    papers, "profile", api_key="test", batch_size=2
                )

        # Aborts on the first chunk instead of grinding through the rest.
        self.assertEqual(completions.create.call_count, 1)


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
