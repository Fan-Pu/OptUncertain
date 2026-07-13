import csv
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

import Helper
from benchmark_methods.mllm_direct import (
    DirectActionValidationError,
    MLLMDirectPolicy,
)
from benchmark_methods.vlfm_g import (
    SemanticScoreCache,
    SemanticScoreConflictError,
    VLFMGPolicy,
    angular_confidence,
    fuse_vlfm_value,
)
from run_benchmark_sweep import (
    _configured_batch,
    _run_calibration_oracles,
    _select_beta,
    _validate_sample_manifest,
)
from scripts.run_benchmark_smoke import build_smoke_scenario


class _FakeActionClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.read_saved_raw_outputs = False
        self.calls = []

    def request_action_completion(self, messages):
        self.calls.append(messages)
        return self.responses.pop(0)


class _FakeSemanticScorer:
    def score_images(self, images, targets, prompt_template):
        scores = {}
        audit = []
        for image_index, _image in enumerate(images):
            for target in targets:
                target_id = str(target["target_id"])
                score = 0.8 - 0.1 * image_index
                scores[(image_index, target_id)] = score
                audit.append(
                    {
                        "image_index": image_index,
                        "image_sha256": "hash_%s" % image_index,
                        "target_id": target_id,
                        "score": score,
                    }
                )
        return scores, audit


def _vlfm_config(tmp_path: Path):
    return {
        "beta": 0.25,
        "alpha": 1.0,
        "wait_utility": -2.0,
        "unreachable_utility": -1000000.0,
        "target_prompt_template": "Seems like {description} ahead.",
    }


class BenchmarkMethodTests(unittest.TestCase):
    def test_calibration_oracles_use_batch_detectable_viewpoints(self):
        calibration_manifest = {
            "batch_id": "batch_test",
            "case_order": ["scan_a_case_0001"],
            "cases": {
                "scan_a_case_0001": {
                    "test_case": "scan_a_case_0001",
                    "scan_id": "scan_a",
                    "agents": [
                        {
                            "id": "agent0",
                            "start_viewpoint_id": "start",
                            "heading": 0.0,
                            "elevation": 0.0,
                        }
                    ],
                    "targets": [
                        {"target_id": "target_a", "description": "target"}
                    ],
                }
            },
        }
        batch_config = {
            "scans": [
                {
                    "scan_id": "scan_a",
                    "targets": [
                        {
                            "target_id": "target_a",
                            "description": "target",
                            "detectable_viewpoint_ids": ["vp1", "vp2"],
                        }
                    ],
                }
            ]
        }

        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            with patch("run_benchmark_sweep.run_oracle") as run_oracle_mock:
                run_oracle_mock.return_value = {"status": "completed"}
                _run_calibration_oracles(
                    calibration_manifest,
                    batch_config,
                    Path(temp_dir),
                )

        scenario = run_oracle_mock.call_args.kwargs["test_case"]
        self.assertEqual(
            scenario["targets"][0]["detectable_viewpoint_ids"],
            ["vp1", "vp2"],
        )

    def test_full_panorama_local_actions_use_deduplicated_markers(self):
        marker_candidates = [
            {
                "viewpoint_id": "vp40",
                "viewpoint_index": 40,
                "distance": 1.5,
                "heading": 2.75,
                "rel_heading": 0.7,
                "rel_elevation": 0.1,
                "horizon_index": 6,
                "xy": [3.0, 4.0],
            },
            {
                "viewpoint_id": "vp40",
                "viewpoint_index": 40,
                "distance": 1.5,
                "heading": 2.8,
                "rel_heading": 0.05,
                "rel_elevation": 0.0,
                "horizon_index": 7,
                "xy": [3.0, 4.0],
            },
            {
                "viewpoint_id": "vp12",
                "viewpoint_index": 12,
                "distance": 2.25,
                "heading": 7.0,
                "rel_heading": 0.0,
                "rel_elevation": 0.0,
                "horizon_index": 0,
                "xy": [1.0, 2.0],
            },
        ]

        actions = Helper._local_actions_from_marker_candidates(marker_candidates)

        self.assertEqual(
            [action["viewpoint_index"] for action in actions],
            [12, 40],
        )
        self.assertEqual(
            actions[0],
            {
                "viewpoint_id": "vp12",
                "viewpoint_index": 12,
                "distance": 2.25,
                "bearing": 7.0 % (2.0 * math.pi),
                "xy": [1.0, 2.0],
            },
        )
        self.assertEqual(
            actions[1],
            {
                "viewpoint_id": "vp40",
                "viewpoint_index": 40,
                "distance": 1.5,
                "bearing": 2.8,
                "xy": [3.0, 4.0],
            },
        )

    def test_angular_confidence_and_fusion(self):
        self.assertAlmostEqual(angular_confidence(0.0, math.pi / 2.0), 1.0)
        self.assertAlmostEqual(
            angular_confidence(math.pi / 4.0, math.pi / 2.0), 0.0, places=12
        )
        self.assertEqual(angular_confidence(math.pi / 2.0, math.pi / 2.0), 0.0)
        value, confidence = fuse_vlfm_value(0.2, 0.5, 0.8, 1.0)
        self.assertAlmostEqual(value, 0.6)
        self.assertAlmostEqual(confidence, (0.25 + 1.0) / 1.5)

    def test_semantic_cache_conflict_raises(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            cache = SemanticScoreCache(temp_dir)
            record = {
                "model_name": "model",
                "model_revision": "revision",
                "prompt_version": "v1",
                "image_sha256": "hash",
                "target_description": "target",
                "score": 0.4,
            }
            cache.append(record)
            cache.append(record)
            with self.assertRaises(SemanticScoreConflictError):
                cache.append({**record, "score": 0.5})

    def test_direct_parse_and_rotating_order(self):
        parsed = MLLMDirectPolicy.parse_and_validate(
            '{"next_viewpoint_id":"2","promising_target_ids":["0"]}',
            allowed_ids=["1", "2"],
            active_target_ids=["0"],
        )
        self.assertEqual(parsed["next_viewpoint_id"], "2")
        self.assertEqual(
            MLLMDirectPolicy.rotating_order(["agent0", "agent1"], 2),
            ["agent1", "agent0"],
        )
        with self.assertRaises(DirectActionValidationError):
            MLLMDirectPolicy.parse_and_validate(
                '{"next_viewpoint_id":"WAIT","promising_target_ids":[]}',
                allowed_ids=["vp1"],
                active_target_ids=["0"],
            )

    def test_direct_repairs_once_and_reserves(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            client = _FakeActionClient(
                [
                    '{"next_viewpoint_id":"bad","promising_target_ids":[]}',
                    '{"next_viewpoint_id":"1","promising_target_ids":["0"]}',
                ]
            )
            policy = MLLMDirectPolicy(
                client=client,
                config={
                    "include_one_step_distances": True,
                    "max_validation_retries": 1,
                },
                raw_output_dir=str(Path(temp_dir) / "raw"),
                debug_output_dir=str(Path(temp_dir) / "debug"),
            )
            observation = {
                "agent_id": "agent0",
                "current_viewpoint_id": "vp0",
                "current_viewpoint_index": 0,
                "start_state": SimpleNamespace(heading=0.0),
                "annotated_panorama": np.zeros((8, 16, 3), dtype=np.uint8),
                "local_actions": [
                    {
                        "viewpoint_id": "vp1",
                        "viewpoint_index": 1,
                        "distance": 1.2,
                        "bearing": 0.5,
                        "xy": [0.0, 0.0],
                    }
                ],
            }
            result = policy.select_actions(
                step_index=1,
                agent_observations=[observation],
                active_targets=[{"target_id": "0", "description": "cup"}],
            )
            self.assertEqual(len(client.calls), 2)
            self.assertIn(
                'ALLOWED_SHORT_VIEWPOINT_IDS:\n["1"]',
                client.calls[0][1]["content"][0]["text"],
            )
            self.assertNotIn(
                "vp1",
                client.calls[0][1]["content"][0]["text"],
            )
            repair_prompt = client.calls[1][1]["content"][0]["text"]
            self.assertIn('next_viewpoint_id to exactly one ID from: ["1"]', repair_prompt)
            self.assertIn('only from: ["0"]', repair_prompt)
            self.assertIn(
                "Do not put viewpoint IDs in promising_target_ids",
                repair_prompt,
            )
            self.assertEqual(result["actions"][0]["next_viewpoint_id"], "vp1")
            self.assertTrue(
                (Path(temp_dir) / "raw" / "direct_action_step_0001_agent_agent0.json").exists()
            )

    def test_direct_prompt_uses_short_ids_for_actions_and_reservations(self):
        policy = MLLMDirectPolicy(
            client=_FakeActionClient([]),
            config={
                "include_one_step_distances": True,
                "max_validation_retries": 1,
            },
            raw_output_dir="unused_raw",
            debug_output_dir="unused_debug",
        )
        prompt = policy._user_message(
            active_targets=[{"target_id": "0", "description": "cup"}],
            allowed_actions=[
                {
                    "viewpoint_id": "long-stable-viewpoint-id",
                    "viewpoint_index": 5,
                    "distance": 1.25,
                }
            ],
            reserved_ids=["4"],
        )
        self.assertIn('ALLOWED_SHORT_VIEWPOINT_IDS:\n["5"]', prompt)
        self.assertIn(
            'SHORT_VIEWPOINT_IDS_RESERVED_BY_OTHER_AGENTS_THIS_ROUND:\n["4"]',
            prompt,
        )
        self.assertIn('"5": 1.25', prompt)
        self.assertNotIn("long-stable-viewpoint-id", prompt)

    def test_full_panorama_action_reaches_direct_and_vlfm_consumers(self):
        from tempfile import TemporaryDirectory

        actions = Helper._local_actions_from_marker_candidates(
            [
                {
                    "viewpoint_id": "vp40",
                    "viewpoint_index": 40,
                    "distance": 1.5,
                    "heading": 2.75,
                    "rel_heading": 0.0,
                    "rel_elevation": 0.0,
                    "horizon_index": 7,
                    "xy": [3.0, 4.0],
                }
            ]
        )
        observation = {
            "agent_id": "agent1",
            "current_viewpoint_id": "vp11",
            "current_viewpoint_index": 11,
            "start_state": SimpleNamespace(heading=0.0),
            "annotated_panorama": np.zeros((8, 16, 3), dtype=np.uint8),
            "local_actions": actions,
        }

        with TemporaryDirectory() as temp_dir:
            direct = MLLMDirectPolicy(
                client=_FakeActionClient(
                    [
                        '{"next_viewpoint_id":"40",'
                        '"promising_target_ids":["0"]}'
                    ]
                ),
                config={
                    "include_one_step_distances": True,
                    "max_validation_retries": 1,
                },
                raw_output_dir=str(Path(temp_dir) / "raw"),
                debug_output_dir=str(Path(temp_dir) / "direct_debug"),
            )
            direct_result = direct.select_actions(
                step_index=1,
                agent_observations=[observation],
                active_targets=[{"target_id": "0", "description": "cup"}],
            )
            self.assertFalse(direct_result["actions"][0]["wait"])
            self.assertEqual(
                direct_result["actions"][0]["next_viewpoint_id"],
                "vp40",
            )

            vlfm = VLFMGPolicy(
                _vlfm_config(Path(temp_dir)),
                debug_output_dir=str(Path(temp_dir) / "vlfm_debug"),
                scorer=_FakeSemanticScorer(),
            )
            vlfm._update_grounded_graph([observation])
            self.assertEqual(vlfm.adjacency["vp11"]["vp40"], 1.5)
            self.assertEqual(vlfm.frontier_nodes(), ["vp40"])

    def test_wait_executes_zero_index(self):
        location = SimpleNamespace(viewpointId="vp0")
        state = SimpleNamespace(
            heading=0.0,
            location=location,
            navigableLocations=[location],
        )

        class FakeSim:
            def __init__(self):
                self.actions = []

            def getState(self):
                return [state]

            def makeAction(self, *args):
                self.actions.append(args)

        sim = FakeSim()
        Helper.execute_individual_first_hops(
            sims=[sim],
            move_specs=[
                {
                    "wait": True,
                    "target_heading": 0.0,
                    "target_viewpoint_id": "vp0",
                }
            ],
            render=False,
        )
        self.assertEqual(sim.actions[-1][0], [0])

    def test_grounded_frontier_uses_local_actions_only(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            policy = VLFMGPolicy(
                _vlfm_config(Path(temp_dir)),
                debug_output_dir=temp_dir,
                scorer=_FakeSemanticScorer(),
            )
            policy._update_grounded_graph(
                [
                    {
                        "agent_id": "agent0",
                        "current_viewpoint_id": "vp0",
                        "current_viewpoint_index": 0,
                        "local_actions": [
                            {
                                "viewpoint_id": "vp1",
                                "viewpoint_index": 1,
                                "distance": 1.0,
                            }
                        ],
                    }
                ]
            )
            self.assertEqual(policy.frontier_nodes(), ["vp1"])
            self.assertEqual(set(policy.adjacency), {"vp0", "vp1"})

    @unittest.skipUnless(importlib.util.find_spec("scipy"), "scipy is not installed")
    def test_vlfm_selects_grounded_first_hop_with_mock_scorer(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            policy = VLFMGPolicy(
                _vlfm_config(Path(temp_dir)),
                debug_output_dir=temp_dir,
                scorer=_FakeSemanticScorer(),
            )
            observation = {
                "agent_id": "agent0",
                "current_viewpoint_id": "vp0",
                "current_viewpoint_index": 0,
                "start_state": SimpleNamespace(heading=0.0),
                "local_actions": [
                    {
                        "viewpoint_id": "vp1",
                        "viewpoint_index": 1,
                        "distance": 1.0,
                        "bearing": 0.0,
                        "xy": [1.0, 0.0],
                    }
                ],
                "semantic_crops": [
                    {
                        "crop_index": 0,
                        "source_horizon_index": 0,
                        "center_heading": 0.0,
                        "horizontal_fov": math.pi / 2.0,
                        "image": np.zeros((8, 8, 3), dtype=np.uint8),
                    }
                ],
            }
            result = policy.select_actions(
                step_index=1,
                agent_observations=[observation],
                active_targets=[{"target_id": "0", "description": "cup"}],
            )
            self.assertFalse(result["terminal"])
            self.assertEqual(result["actions"][0]["next_viewpoint_id"], "vp1")
            self.assertEqual(result["actions"][0]["assigned_frontier_id"], "vp1")
            self.assertTrue(Path(result["log_path"]).exists())

    @unittest.skipUnless(importlib.util.find_spec("scipy"), "scipy is not installed")
    def test_first_hop_conflict_repairs_to_wait(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            policy = VLFMGPolicy(
                _vlfm_config(Path(temp_dir)),
                debug_output_dir=temp_dir,
                scorer=_FakeSemanticScorer(),
            )
            policy.adjacency = {
                "a": {"c": 1.0},
                "b": {"c": 1.0},
                "c": {"a": 1.0, "b": 1.0, "f1": 1.0, "f2": 1.0},
                "f1": {"c": 1.0},
                "f2": {"c": 1.0},
            }
            observations = [
                {"agent_id": "agent0", "current_viewpoint_id": "a"},
                {"agent_id": "agent1", "current_viewpoint_id": "b"},
            ]
            decisions, _log = policy._assign(
                observations=observations,
                frontiers=["f1", "f2"],
                normalized_values={"f1": 1.0, "f2": 0.5},
            )
            real_hops = [
                decision["first_hop"]
                for decision in decisions.values()
                if decision["first_hop"] is not None
            ]
            self.assertEqual(len(real_hops), len(set(real_hops)))
            self.assertEqual(
                sum(decision["frontier_id"] is None for decision in decisions.values()),
                1,
            )

    def test_vlfm_module_has_no_oracle_import(self):
        source = Path("benchmark_methods/vlfm_g.py").read_text(encoding="utf-8")
        self.assertNotIn("route_plotter", source)
        self.assertNotIn("detectable_viewpoint_ids", source)
        self.assertNotIn("connectivity", source)
        self.assertIn("use_fast=False", source)

    def test_exact_manifest_validation(self):
        case = {
            "scan_id": "scan",
            "agents": [{"id": "agent0"}],
            "targets": [{"target_id": "0"}],
            "max_steps": 30,
        }
        source = {"case_order": ["case1"], "cases": {"case1": case}}
        sample = {"case_order": ["case1"], "cases": {"case1": dict(case)}}
        _validate_sample_manifest(sample, source)
        sample["cases"]["case1"] = {**case, "max_steps": 29}
        with self.assertRaises(ValueError):
            _validate_sample_manifest(sample, source)

    def test_mllm_direct_batch_uses_flex_without_changing_graph_model_entry(self):
        default_config = json.loads(
            Path("config/default_config.json").read_text(encoding="utf-8")
        )
        batch_config = json.loads(
            Path("scenarios/batch_test.json").read_text(encoding="utf-8")
        )

        configured = _configured_batch(
            method="mllm_direct",
            batch_config=batch_config,
            default_config=default_config,
        )

        self.assertEqual(configured["mllm"]["graph_service_tier"], "flex")
        gpt_entry = next(
            model
            for model in default_config["batch_sweep"]["graph_models"]
            if model["label"] == "GPT54Medium"
        )
        self.assertIsNone(gpt_entry["graph_service_tier"])

    def test_beta_selection_order(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "method_metrics.csv"
            fields = [
                "method",
                "team_ppl_total",
                "progress",
                "verified_success_rate",
                "mean_total_distance",
            ]
            with open(path, "w", encoding="utf-8", newline="") as file_handle:
                writer = csv.DictWriter(file_handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow(
                    {
                        "method": "beta0",
                        "team_ppl_total": 0.2,
                        "progress": 0.5,
                        "verified_success_rate": 0.1,
                        "mean_total_distance": 20.0,
                    }
                )
                writer.writerow(
                    {
                        "method": "beta1",
                        "team_ppl_total": 0.3,
                        "progress": 0.4,
                        "verified_success_rate": 0.1,
                        "mean_total_distance": 30.0,
                    }
                )
            selected, ranked = _select_beta(
                path,
                {"beta0": 0.0, "beta1": 1.0},
            )
            self.assertEqual(selected, 1.0)
            self.assertEqual(ranked[0]["method"], "beta1")

    def test_smoke_scenario_is_isolated_and_step_limited(self):
        default_config = json.loads(Path("config/default_config.json").read_text())
        batch_config = json.loads(Path("scenarios/batch_test.json").read_text())
        scenario = build_smoke_scenario(
            method="vlfm_g",
            case_id="JF19kD82Mey_case_0006",
            max_steps=1,
            beta=0.25,
            default_config=default_config,
            batch_config=batch_config,
        )
        self.assertEqual(scenario["max_steps"], 1)
        self.assertEqual(scenario["benchmark"]["method"], "vlfm_g")
        self.assertEqual(scenario["benchmark"]["vlfm_g"]["beta"], 0.25)
        self.assertIn("smoke_VLFMG", scenario["mllm"]["debug_output_dir"])


if __name__ == "__main__":
    unittest.main()
