from __future__ import annotations

import hashlib
import heapq
import json
import math
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image


SEMANTIC_PROMPT_VERSION = "vlfm_g_target_prompt_v1"


class SemanticScoreConflictError(ValueError):
    pass


def _wrapped_angle(value: float) -> float:
    return (float(value) + math.pi) % (2.0 * math.pi) - math.pi


def angular_confidence(delta_angle: float, horizontal_fov: float) -> float:
    half_fov = float(horizontal_fov) / 2.0
    delta = abs(_wrapped_angle(delta_angle))
    if half_fov <= 0.0:
        raise ValueError("horizontal_fov must be positive.")
    if delta > half_fov:
        return 0.0
    return math.cos((delta / half_fov) * (math.pi / 2.0)) ** 2


def fuse_vlfm_value(
    previous_value: float,
    previous_confidence: float,
    observed_value: float,
    observed_confidence: float,
) -> Tuple[float, float]:
    denominator = float(previous_confidence) + float(observed_confidence)
    if denominator <= 0.0:
        raise ValueError("VLFM fusion requires positive total confidence.")
    value = (
        float(previous_confidence) * float(previous_value)
        + float(observed_confidence) * float(observed_value)
    ) / denominator
    confidence = (
        float(previous_confidence) ** 2 + float(observed_confidence) ** 2
    ) / denominator
    return value, confidence


class SemanticScoreCache:
    KEY_FIELDS = (
        "model_name",
        "model_revision",
        "prompt_version",
        "image_sha256",
        "target_description",
    )

    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.path = self.cache_dir / "scores.jsonl"
        self._scores: Dict[Tuple[str, ...], float] = {}
        if self.path.exists():
            for line_number, line in enumerate(
                self.path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if not line.strip():
                    continue
                record = json.loads(line)
                self._insert(record, source="line %s" % line_number)

    @classmethod
    def _key(cls, record: Dict[str, object]) -> Tuple[str, ...]:
        missing = [field for field in cls.KEY_FIELDS if field not in record]
        if missing:
            raise KeyError("Semantic cache record is missing %s." % missing)
        return tuple(str(record[field]) for field in cls.KEY_FIELDS)

    def _insert(self, record: Dict[str, object], source: str) -> bool:
        key = self._key(record)
        score = float(record["score"])
        if key in self._scores:
            if self._scores[key] != score:
                raise SemanticScoreConflictError(
                    "Contradictory semantic score cache entry at %s for key %s."
                    % (source, key)
                )
            return False
        self._scores[key] = score
        return True

    def lookup(self, record: Dict[str, object]) -> float | None:
        return self._scores.get(self._key(record))

    def append(self, record: Dict[str, object]) -> None:
        if not self._insert(record, source="append"):
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(record, sort_keys=True) + "\n")
            file_handle.flush()


class BLIP2SemanticScorer:
    def __init__(self, config: Dict[str, object]) -> None:
        self.model_name = str(config["model_name"])
        self.model_revision = str(config["model_revision"])
        self.device = str(config.get("device", "cpu"))
        self.dtype_name = str(config.get("dtype", "float32"))
        if self.dtype_name != "float32":
            raise ValueError("VLFM-G dtype must be exactly float32.")
        self.cache = SemanticScoreCache(config["semantic_cache_dir"])
        self.model = None
        self.processor = None

    @staticmethod
    def image_hash(image: np.ndarray) -> str:
        digest = hashlib.sha256()
        digest.update(str(image.shape).encode("ascii"))
        digest.update(str(image.dtype).encode("ascii"))
        digest.update(np.ascontiguousarray(image).tobytes())
        return digest.hexdigest()

    def _load(self) -> None:
        if self.model is not None:
            return
        import torch
        from transformers import AutoProcessor, Blip2ForImageTextRetrieval

        self.processor = AutoProcessor.from_pretrained(
            self.model_name,
            revision=self.model_revision,
            use_fast=False,
        )
        self.model = Blip2ForImageTextRetrieval.from_pretrained(
            self.model_name,
            revision=self.model_revision,
            dtype=torch.float32,
            use_safetensors=True,
        )
        self.model.to(self.device)
        self.model.eval()

    def score_images(
        self,
        images: List[np.ndarray],
        targets: List[Dict[str, object]],
        prompt_template: str,
    ) -> Tuple[Dict[Tuple[int, str], float], List[Dict[str, object]]]:
        scores: Dict[Tuple[int, str], float] = {}
        audit = []
        sorted_targets = sorted(targets, key=lambda item: str(item["target_id"]))

        for image_index, image in enumerate(images):
            image_sha256 = self.image_hash(image)
            missing_targets = []
            records = {}
            for target in sorted_targets:
                target_id = str(target["target_id"])
                record = {
                    "model_name": self.model_name,
                    "model_revision": self.model_revision,
                    "prompt_version": SEMANTIC_PROMPT_VERSION,
                    "image_sha256": image_sha256,
                    "target_description": str(target["description"]),
                }
                records[target_id] = record
                cached = self.cache.lookup(record)
                if cached is None:
                    missing_targets.append(target)
                else:
                    scores[(image_index, target_id)] = float(cached)

            if missing_targets:
                self._load()
                import torch

                prompts = [
                    prompt_template.format(description=str(target["description"]))
                    for target in missing_targets
                ]
                inputs = self.processor(
                    images=Image.fromarray(image).convert("RGB"),
                    text=prompts,
                    return_tensors="pt",
                    padding=True,
                )
                prepared = {}
                for key, value in inputs.items():
                    if key == "pixel_values":
                        prepared[key] = value.to(self.device, dtype=torch.float32)
                    else:
                        prepared[key] = value.to(self.device)
                with torch.inference_mode():
                    output = self.model(
                        **prepared,
                        use_image_text_matching_head=False,
                    )
                logits = output.logits_per_image.detach().cpu().numpy()
                logits = np.asarray(logits, dtype=np.float64).reshape(1, -1)[0]
                if len(logits) != len(missing_targets):
                    raise ValueError(
                        "BLIP-2 returned %s scores for %s target prompts."
                        % (len(logits), len(missing_targets))
                    )
                for target, score_raw in zip(missing_targets, logits):
                    target_id = str(target["target_id"])
                    score = float(score_raw)
                    record = {**records[target_id], "score": score}
                    self.cache.append(record)
                    scores[(image_index, target_id)] = score

            for target in sorted_targets:
                target_id = str(target["target_id"])
                audit.append(
                    {
                        "image_index": image_index,
                        "image_sha256": image_sha256,
                        "target_id": target_id,
                        "score": scores[(image_index, target_id)],
                    }
                )

        return scores, audit


class VLFMGPolicy:
    def __init__(
        self,
        config: Dict[str, object],
        debug_output_dir: str,
        scorer=None,
    ) -> None:
        self.config = dict(config)
        self.alpha = float(config.get("alpha", 1.0))
        if "beta" not in config:
            raise KeyError("VLFM-G requires a frozen beta value.")
        self.beta = float(config["beta"])
        self.wait_utility = float(config.get("wait_utility", -2.0))
        self.unreachable_utility = float(
            config.get("unreachable_utility", -1000000.0)
        )
        self.prompt_template = str(config["target_prompt_template"])
        self.debug_output_dir = Path(debug_output_dir)
        self.scorer = scorer or BLIP2SemanticScorer(config)
        self.adjacency: Dict[str, Dict[str, float]] = {}
        self.node_indices: Dict[str, int] = {}
        self.visit_counts: Dict[str, int] = {}
        self.semantic_values: Dict[str, Dict[str, float]] = {}
        self.confidences: Dict[str, float] = {}

    def _update_grounded_graph(
        self,
        observations: List[Dict[str, object]],
    ) -> List[Dict[str, object]]:
        discrepancies = []
        for observation in sorted(
            observations, key=lambda item: str(item["agent_id"])
        ):
            current_id = str(observation["current_viewpoint_id"])
            self.node_indices[current_id] = int(
                observation["current_viewpoint_index"]
            )
            self.adjacency.setdefault(current_id, {})
            self.visit_counts[current_id] = self.visit_counts.get(current_id, 0) + 1
            for action in observation["local_actions"]:
                neighbor_id = str(action["viewpoint_id"])
                distance = float(action["distance"])
                if distance < 0.0:
                    raise ValueError("Grounded edge distances must be nonnegative.")
                self.node_indices[neighbor_id] = int(action["viewpoint_index"])
                self.adjacency.setdefault(neighbor_id, {})
                self.visit_counts.setdefault(neighbor_id, 0)
                previous = self.adjacency[current_id].get(neighbor_id)
                if previous is not None and previous != distance:
                    discrepancies.append(
                        {
                            "source": current_id,
                            "target": neighbor_id,
                            "previous_distance": previous,
                            "current_distance": distance,
                        }
                    )
                self.adjacency[current_id][neighbor_id] = distance
                self.adjacency[neighbor_id][current_id] = distance
        return discrepancies

    def frontier_nodes(self) -> List[str]:
        return sorted(
            node_id
            for node_id in self.adjacency
            if self.visit_counts.get(node_id, 0) == 0
            and any(
                self.visit_counts.get(neighbor_id, 0) > 0
                for neighbor_id in self.adjacency[node_id]
            )
        )

    def _save_crop(
        self,
        step_index: int,
        agent_id: str,
        crop: Dict[str, object],
    ) -> str:
        path = self.debug_output_dir / (
            "vlfm_crop_step_%04d_agent_%s_crop_%02d.jpg"
            % (int(step_index), str(agent_id), int(crop["crop_index"]))
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(crop["image"]).convert("RGB").save(
            path,
            format="JPEG",
            quality=95,
        )
        return str(path)

    def _update_semantic_values(
        self,
        step_index: int,
        observations: List[Dict[str, object]],
        active_targets: List[Dict[str, object]],
        frontiers: List[str],
    ) -> List[Dict[str, object]]:
        frontier_set = set(frontiers)
        evidence: Dict[str, List[Dict[str, object]]] = {
            frontier: [] for frontier in frontiers
        }
        score_audit = []

        for observation in sorted(
            observations, key=lambda item: str(item["agent_id"])
        ):
            agent_id = str(observation["agent_id"])
            crops = list(observation["semantic_crops"])
            if not crops:
                raise ValueError("VLFM-G requires native semantic crops.")
            images = [crop["image"] for crop in crops]
            crop_scores, raw_audit = self.scorer.score_images(
                images=images,
                targets=active_targets,
                prompt_template=self.prompt_template,
            )
            crop_paths = {
                int(crop["crop_index"]): self._save_crop(
                    step_index,
                    agent_id,
                    crop,
                )
                for crop in crops
            }
            for record in raw_audit:
                crop = crops[int(record["image_index"])]
                score_audit.append(
                    {
                        **record,
                        "agent_id": agent_id,
                        "crop_index": int(crop["crop_index"]),
                        "center_heading": float(crop["center_heading"]),
                        "horizontal_fov": float(crop["horizontal_fov"]),
                        "crop_path": crop_paths[int(crop["crop_index"])],
                    }
                )

            for action in observation["local_actions"]:
                frontier_id = str(action["viewpoint_id"])
                if frontier_id not in frontier_set:
                    continue
                bearing = float(action["bearing"])
                for image_index, crop in enumerate(crops):
                    confidence = angular_confidence(
                        bearing - float(crop["center_heading"]),
                        float(crop["horizontal_fov"]),
                    )
                    if confidence <= 0.0:
                        continue
                    evidence[frontier_id].append(
                        {
                            "agent_id": agent_id,
                            "crop_index": int(crop["crop_index"]),
                            "confidence": confidence,
                            "scores": {
                                str(target["target_id"]): float(
                                    crop_scores[
                                        (image_index, str(target["target_id"]))
                                    ]
                                )
                                for target in active_targets
                            },
                        }
                    )

        active_target_ids = [
            str(target["target_id"])
            for target in sorted(
                active_targets,
                key=lambda item: str(item["target_id"]),
            )
        ]
        for frontier_id in frontiers:
            frontier_evidence = evidence[frontier_id]
            if frontier_evidence:
                denominator = sum(
                    float(item["confidence"]) for item in frontier_evidence
                )
                observed_confidence = sum(
                    float(item["confidence"]) ** 2
                    for item in frontier_evidence
                ) / denominator
                observed_values = {
                    target_id: sum(
                        float(item["confidence"])
                        * float(item["scores"][target_id])
                        for item in frontier_evidence
                    )
                    / denominator
                    for target_id in active_target_ids
                }
                if frontier_id not in self.confidences:
                    self.confidences[frontier_id] = observed_confidence
                    self.semantic_values[frontier_id] = observed_values
                else:
                    previous_confidence = self.confidences[frontier_id]
                    new_confidence = None
                    for target_id in active_target_ids:
                        if target_id not in self.semantic_values[frontier_id]:
                            raise ValueError(
                                "Frontier %s has no historical value for target %s."
                                % (frontier_id, target_id)
                            )
                        fused_value, fused_confidence = fuse_vlfm_value(
                            self.semantic_values[frontier_id][target_id],
                            previous_confidence,
                            observed_values[target_id],
                            observed_confidence,
                        )
                        self.semantic_values[frontier_id][target_id] = fused_value
                        new_confidence = fused_confidence
                    self.confidences[frontier_id] = float(new_confidence)

            missing = [
                target_id
                for target_id in active_target_ids
                if target_id not in self.semantic_values.get(frontier_id, {})
            ]
            if missing:
                raise ValueError(
                    "Frontier %s has no semantic value for active targets %s."
                    % (frontier_id, missing)
                )

        return score_audit

    @staticmethod
    def normalize_frontier_values(
        values: Dict[str, float],
    ) -> Dict[str, float]:
        if not values:
            return {}
        minimum = min(values.values())
        maximum = max(values.values())
        if maximum == minimum:
            return {node_id: 0.5 for node_id in values}
        return {
            node_id: (float(value) - minimum) / (maximum - minimum + 1e-8)
            for node_id, value in values.items()
        }

    def _shortest_paths(
        self,
        source: str,
    ) -> Tuple[Dict[str, float], Dict[str, List[str]]]:
        distances = {str(source): 0.0}
        previous: Dict[str, str] = {}
        queue = [(0.0, str(source))]
        while queue:
            distance, node_id = heapq.heappop(queue)
            if distance != distances[node_id]:
                continue
            for neighbor_id, edge_distance in sorted(
                self.adjacency[node_id].items()
            ):
                candidate = distance + float(edge_distance)
                if candidate < distances.get(neighbor_id, math.inf):
                    distances[neighbor_id] = candidate
                    previous[neighbor_id] = node_id
                    heapq.heappush(queue, (candidate, neighbor_id))

        paths = {}
        for target_id in distances:
            path = [target_id]
            while path[-1] != str(source):
                path.append(previous[path[-1]])
            paths[target_id] = list(reversed(path))
        return distances, paths

    def _assign(
        self,
        observations: List[Dict[str, object]],
        frontiers: List[str],
        normalized_values: Dict[str, float],
    ) -> Tuple[Dict[str, Dict[str, object]], Dict[str, object]]:
        try:
            from scipy.optimize import linear_sum_assignment
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "VLFM-G requires scipy; install requirements-benchmarks.txt."
            ) from exc

        current_by_agent = {
            str(observation["agent_id"]): str(
                observation["current_viewpoint_id"]
            )
            for observation in observations
        }
        agents = sorted(current_by_agent)
        distances = {}
        paths = {}
        for agent_id in agents:
            source_distances, source_paths = self._shortest_paths(
                current_by_agent[agent_id]
            )
            for frontier_id in frontiers:
                distances[(agent_id, frontier_id)] = source_distances.get(
                    frontier_id, math.inf
                )
                paths[(agent_id, frontier_id)] = source_paths.get(frontier_id)

        finite_distances = [
            value for value in distances.values() if math.isfinite(value)
        ]
        maximum_distance = max(finite_distances, default=0.0)
        normalized_distances = {
            key: (
                value / (maximum_distance + 1e-8)
                if math.isfinite(value) and maximum_distance > 0.0
                else (0.0 if math.isfinite(value) else math.inf)
            )
            for key, value in distances.items()
        }
        utilities = {
            key: (
                self.alpha * normalized_values[key[1]]
                - self.beta * normalized_distances[key]
                if math.isfinite(normalized_distances[key])
                else self.unreachable_utility
            )
            for key in distances
        }

        remaining_agents = list(agents)
        available_frontiers = list(frontiers)
        reserved_first_hops = set()
        decisions: Dict[str, Dict[str, object]] = {}
        assignment_rounds = []

        while remaining_agents:
            dummy_ids = [
                "__WAIT_%s_%s" % (len(assignment_rounds), index)
                for index in range(len(remaining_agents))
            ]
            columns = available_frontiers + dummy_ids
            matrix = np.zeros((len(remaining_agents), len(columns)), dtype=float)
            for row_index, agent_id in enumerate(remaining_agents):
                for column_index, column_id in enumerate(columns):
                    if column_id in dummy_ids:
                        utility = self.wait_utility
                    else:
                        route = paths[(agent_id, column_id)]
                        utility = utilities[(agent_id, column_id)]
                        if route is None or route[1] in reserved_first_hops:
                            utility = self.unreachable_utility
                    utility -= 1e-8 * column_index + 1e-10 * row_index
                    matrix[row_index, column_index] = utility

            row_indices, column_indices = linear_sum_assignment(-matrix)
            tentative = []
            for row_index, column_index in zip(row_indices, column_indices):
                agent_id = remaining_agents[int(row_index)]
                column_id = columns[int(column_index)]
                if column_id in dummy_ids:
                    tentative.append(
                        {
                            "agent_id": agent_id,
                            "frontier_id": None,
                            "first_hop": None,
                            "utility": self.wait_utility,
                        }
                    )
                else:
                    route = paths[(agent_id, column_id)]
                    tentative.append(
                        {
                            "agent_id": agent_id,
                            "frontier_id": column_id,
                            "first_hop": route[1],
                            "utility": utilities[(agent_id, column_id)],
                        }
                    )

            groups: Dict[str, List[Dict[str, object]]] = {}
            for item in tentative:
                if item["first_hop"] is not None:
                    groups.setdefault(str(item["first_hop"]), []).append(item)
            losers = set()
            for items in groups.values():
                if len(items) <= 1:
                    continue
                winner = sorted(
                    items,
                    key=lambda item: (
                        -float(item["utility"]),
                        str(item["agent_id"]),
                    ),
                )[0]
                losers.update(
                    str(item["agent_id"])
                    for item in items
                    if item is not winner
                )

            fixed_this_round = []
            for item in tentative:
                agent_id = str(item["agent_id"])
                if agent_id in losers:
                    continue
                decisions[agent_id] = item
                fixed_this_round.append(item)
                if item["frontier_id"] is not None:
                    available_frontiers.remove(str(item["frontier_id"]))
                    reserved_first_hops.add(str(item["first_hop"]))

            if not fixed_this_round:
                raise RuntimeError("VLFM-G first-hop conflict repair made no progress.")
            assignment_rounds.append(
                {
                    "remaining_agents": list(remaining_agents),
                    "available_frontiers": list(columns),
                    "utility_matrix": matrix.tolist(),
                    "tentative": tentative,
                    "conflicting_agent_ids": sorted(losers),
                    "fixed": fixed_this_round,
                }
            )
            remaining_agents = sorted(losers)

        return decisions, {
            "distances": {
                "%s|%s" % key: (value if math.isfinite(value) else None)
                for key, value in distances.items()
            },
            "normalized_distances": {
                "%s|%s" % key: (value if math.isfinite(value) else None)
                for key, value in normalized_distances.items()
            },
            "utilities": {
                "%s|%s" % key: value for key, value in utilities.items()
            },
            "assignment_rounds": assignment_rounds,
        }

    def select_actions(
        self,
        step_index: int,
        agent_observations: List[Dict[str, object]],
        active_targets: List[Dict[str, object]],
    ) -> Dict[str, object]:
        started_at = time.time()
        discrepancies = self._update_grounded_graph(agent_observations)
        frontiers = self.frontier_nodes()
        if not frontiers:
            return {
                "terminal": True,
                "stop_reason": "vlfm_no_frontier",
                "actions": [],
            }

        score_audit = self._update_semantic_values(
            step_index=step_index,
            observations=agent_observations,
            active_targets=active_targets,
            frontiers=frontiers,
        )
        active_target_ids = {
            str(target["target_id"]) for target in active_targets
        }
        frontier_values = {
            frontier_id: max(
                value
                for target_id, value in self.semantic_values[frontier_id].items()
                if target_id in active_target_ids
            )
            for frontier_id in frontiers
        }
        normalized_values = self.normalize_frontier_values(frontier_values)
        assignments, assignment_log = self._assign(
            observations=agent_observations,
            frontiers=frontiers,
            normalized_values=normalized_values,
        )

        observation_by_agent = {
            str(observation["agent_id"]): observation
            for observation in agent_observations
        }
        actions = []
        for agent_id in sorted(assignments):
            assignment = assignments[agent_id]
            observation = observation_by_agent[agent_id]
            if assignment["frontier_id"] is None:
                actions.append(
                    {
                        "agent_id": agent_id,
                        "wait": True,
                        "next_viewpoint_id": str(
                            observation["current_viewpoint_id"]
                        ),
                        "next_viewpoint_index": int(
                            observation["current_viewpoint_index"]
                        ),
                        "target_heading": float(
                            observation["start_state"].heading
                        ),
                    }
                )
                continue
            first_hop = str(assignment["first_hop"])
            local_action = next(
                action
                for action in observation["local_actions"]
                if str(action["viewpoint_id"]) == first_hop
            )
            actions.append(
                {
                    "agent_id": agent_id,
                    "wait": False,
                    "next_viewpoint_id": first_hop,
                    "next_viewpoint_index": int(local_action["viewpoint_index"]),
                    "target_heading": float(local_action["bearing"]),
                    "assigned_frontier_id": str(assignment["frontier_id"]),
                }
            )

        log = {
            "method": "vlfm_g",
            "step_index": int(step_index),
            "beta": self.beta,
            "grounded_edges": [
                {
                    "source": source,
                    "target": target,
                    "distance": distance,
                }
                for source in sorted(self.adjacency)
                for target, distance in sorted(self.adjacency[source].items())
                if source < target
            ],
            "visit_counts": self.visit_counts,
            "frontiers": frontiers,
            "edge_distance_discrepancies": discrepancies,
            "raw_semantic_scores": score_audit,
            "semantic_values": self.semantic_values,
            "confidences": self.confidences,
            "frontier_values": frontier_values,
            "normalized_frontier_values": normalized_values,
            **assignment_log,
            "actions": actions,
            "runtime_seconds": time.time() - started_at,
        }
        log_path = self.debug_output_dir / (
            "vlfm_g_step_%04d.json" % int(step_index)
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            json.dumps(log, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return {
            "terminal": False,
            "actions": actions,
            "log_path": str(log_path),
        }
