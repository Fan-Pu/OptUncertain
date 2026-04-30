from __future__ import annotations

import base64
import io
import json
import os
from textwrap import dedent
from typing import TYPE_CHECKING, Dict, List, Optional
import debugpy
import numpy as np
from openai import BadRequestError, OpenAI
from PIL import Image

if TYPE_CHECKING:
    from semantic_persistence import HypothesisGraph


class MLLMClient:
    def __init__(
        self,
        model_name: str = "",  # read from config
        base_url: str = "https://router.huggingface.co/v1",
        api_key_env: str = "HF_TOKEN",
        max_new_tokens: int = -1,  # read from config
        request_timeout: float = 120.0,
        save_debug_images: bool = True,
        read_saved_raw_outputs: bool = False,
        raw_output_dir: str = "mllm_raw_outputs",
    ):
        self.model_name = model_name
        self.base_url = base_url
        self.max_new_tokens = int(max_new_tokens)
        self.request_timeout = float(request_timeout)
        self.save_debug_images = bool(save_debug_images)
        self.read_saved_raw_outputs = bool(read_saved_raw_outputs)
        self.raw_output_dir = str(raw_output_dir)
        self.semantic_raw_output_index = 0

        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                "Environment variable %s is required for the Hugging Face router API."
                % api_key_env
            )

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=api_key,
            timeout=self.request_timeout,
        )

    @staticmethod
    def _strip_code_fences(raw_text: str) -> str:
        """Strip markdown code fences from the raw text if they exist."""
        raw_text = raw_text.strip()
        if "```" not in raw_text:
            return raw_text
        lines = raw_text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()

    @staticmethod
    def _message_to_text(message_content) -> str:
        if isinstance(message_content, str):
            return message_content
        if isinstance(message_content, list):
            chunks = []
            for item in message_content:
                if isinstance(item, dict) and item.get("type") == "text":
                    chunks.append(str(item.get("text", "")))
            return "\n".join(chunk for chunk in chunks if chunk).strip()
        return str(message_content or "")

    @staticmethod
    def _parse_json_strict(raw_text: str) -> Dict[str, object]:
        raw_text = raw_text.strip()

        if not raw_text.startswith("{") or not raw_text.endswith("}"):
            raise ValueError(
                "The model output is not a pure JSON object. "
                "It must start with '{' and end with '}'."
            )

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "The model output is not valid JSON: %s" % str(exc)
            ) from exc

        if not isinstance(parsed, dict):
            raise ValueError("The model output must be a JSON object.")

        return parsed

    @staticmethod
    def _image_to_data_url(image_bytes: bytes) -> str:
        """Convert JPEG bytes to a data URL."""
        if not isinstance(image_bytes, bytes):
            raise TypeError("_image_to_data_url expects JPEG bytes.")

        encoded = base64.b64encode(image_bytes).decode("ascii")
        return "data:image/jpeg;base64,%s" % encoded

    def _request_completion(self, messages) -> str:
        self._print_request_size_report(messages)

        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                # Best practical reproducibility settings
                temperature=0.0,
                top_p=1.0,
                seed=42,
                max_tokens=self.max_new_tokens,
                # JSON-only output
                response_format={"type": "json_object"},
                reasoning_effort="none",  # try "minimal" if "none" is rejected
            )

            print("usage:", completion.usage)
            print("model:", completion.model)
            print(
                "system_fingerprint:", getattr(completion, "system_fingerprint", None)
            )
            print("finish_reason:", completion.choices[0].finish_reason)

        except BadRequestError as exc:
            message = str(exc)
            if "model_not_found" in message or "does not exist" in message:
                raise RuntimeError(
                    "The configured Hugging Face router model was not found. "
                    "Resolved model='%s'." % self.model_name
                ) from exc
            raise

        return self._message_to_text(completion.choices[0].message.content)

    def _semantic_raw_output_path(self, step_index: int) -> str:
        return os.path.join(
            getattr(self, "raw_output_dir", "mllm_raw_outputs"),
            "semantic_step_%04d.json" % int(step_index),
        )

    def _read_semantic_raw_output(self, step_index: int) -> str:
        with open(
            self._semantic_raw_output_path(step_index),
            "r",
            encoding="utf-8",
        ) as file_handle:
            return file_handle.read()

    def _check_semantic_raw_output_exists(self, step_index: int) -> bool:
        return os.path.exists(self._semantic_raw_output_path(step_index))

    def _write_semantic_raw_output(self, step_index: int, decoded: str) -> None:
        raw_output_dir = getattr(self, "raw_output_dir", "mllm_raw_outputs")
        os.makedirs(raw_output_dir, exist_ok=True)
        with open(
            self._semantic_raw_output_path(step_index),
            "w",
            encoding="utf-8",
        ) as file_handle:
            file_handle.write(decoded)

    def _build_instruction(
        self,
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        graph_summary: Dict[str, object],
    ) -> tuple[str, str]:
        """Build a token-reduced prompt for multi-agent, multi-target graph hypotheses.

        The rules and restrictions are kept, but repeated wording is merged.
        """

        target_records = sorted(
            [
                {
                    "target_id": str(target["target_id"]),
                    "description": str(target["description"]),
                }
                for target in targets
            ],
            key=lambda item: item["target_id"],
        )

        target_ids = [item["target_id"] for item in target_records]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("Target ids must be unique.")

        agent_context = []
        for image_index, observation in enumerate(agent_observations):
            visible_viewpoints = [
                {
                    "viewpoint_index": int(item["viewpoint_index"]),
                    "distance": float(item["distance"]),
                }
                for item in observation["visible_viewpoints"]
            ]
            agent_context.append(
                {
                    "agent_id": str(observation["agent_id"]),
                    "image_index": image_index,
                    "current_viewpoint_index": int(
                        observation["current_viewpoint_index"]
                    ),
                    "visible_viewpoints": visible_viewpoints,
                }
            )

        target_prob_template = {target_id: 0.01 for target_id in target_ids}
        current_viewpoint_detection_template = {
            target_id: 0.0 for target_id in target_ids
        }

        example_agent_id = agent_context[0]["agent_id"] if agent_context else "agent0"
        example_current_viewpoint_id = (
            agent_context[0]["current_viewpoint_index"] if agent_context else 10
        )
        example_visible_viewpoint_id = (
            agent_context[0]["visible_viewpoints"][0]["viewpoint_index"]
            if agent_context and agent_context[0]["visible_viewpoints"]
            else 13
        )

        schema = {
            "agents": [
                {
                    "agent_id": example_agent_id,
                    "current_region_node_id": 100,
                }
            ],
            "visible_region_nodes": [
                {
                    "id": 100,
                    "label": "bright kitchen area near dining table",
                    "exist_prob": 1.0,
                    "target_probs": target_prob_template,
                }
            ],
            "invisible_region_nodes": [
                {
                    "id": 102,
                    "label": "narrow hallway area beyond doorway near kitchen",
                    "exist_prob": 0.6,
                    "target_probs": target_prob_template,
                }
            ],
            "viewpoint_target_probs": [
                {
                    "id": example_current_viewpoint_id,
                    "target_probs": current_viewpoint_detection_template,
                },
                {
                    "id": example_visible_viewpoint_id,
                    "target_probs": target_prob_template,
                },
            ],
            "viewpoint_node_assigns": [
                {
                    "region_node_id": 100,
                    "assigned_viewpoint_node_indices": [
                        example_current_viewpoint_id,
                        example_visible_viewpoint_id,
                    ],
                }
            ],
            "new_edges": [
                {
                    "i": example_visible_viewpoint_id,
                    "j": 102,
                    "edge_type": "VZ",
                    "exist_prob": 0.6,
                    "dist": 2.5,
                }
            ],
            "edge_distance_variances": {
                "viewpoint_viewpoint": 1.0,
                "viewpoint_region": 4.0,
            },
            "detections": [
                {
                    "agent_id": example_agent_id,
                    "target_indices": target_ids,
                    "founds": [False for _ in target_ids],
                }
            ],
        }

        field_descriptions = {
            "agents": "One item per agent.",
            "agents[].agent_id": "Must match an input agent id exactly.",
            "agents[].current_region_node_id": (
                "Region id containing the agent current viewpoint. It must appear in "
                "visible_region_nodes. If this region already exists, reuse its id and "
                "label and still include it."
            ),
            "visible_region_nodes": (
                "Visible semantic regions directly supported by current panoramas. "
                "Include every current semantic region. Reuse existing region ids and "
                "labels when the observed place matches the graph summary. Do not "
                "duplicate the same physical area."
            ),
            "visible_region_nodes[].id": (
                "Integer region id. Use a new id only for a new physical region."
            ),
            "visible_region_nodes[].label": (
                "Room or area label only, not an object name. Include appearance cue, "
                "area type, and physical relative location cue, such as near doorway, "
                "beside window, beyond hallway, adjacent to kitchen, or at the end of "
                "the room. Do not mention agent ids or names."
            ),
            "visible_region_nodes[].exist_prob": (
                "Existence probability in (0, 1]. Use 1.0 only for a region containing "
                "a current viewpoint."
            ),
            "visible_region_nodes[].target_probs": (
                "Unnormalized target-location scores keyed by every target_id. Values "
                "must be in (0, 1]. Do not use 0.0. Use target descriptions to make "
                "target-specific scores when evidence differs. Equal scores are allowed "
                "only when evidence is equally weak."
            ),
            "invisible_region_nodes": (
                "Unseen but layout-supported semantic regions. Infer 1 to 2 when there "
                "is plausible unseen space, such as beyond a doorway, opening, corridor, "
                "wall boundary, or occlusion. Return [] only when no plausible unseen "
                "region is supported."
            ),
            "invisible_region_nodes[].id": (
                "Integer region id. Use a new id only if the region is not represented "
                "in the graph summary."
            ),
            "invisible_region_nodes[].label": (
                "Room or area label only, not an object name. Include appearance cue, "
                "area type, and physical relative location cue. Do not mention agent ids "
                "or names."
            ),
            "invisible_region_nodes[].exist_prob": (
                "Existence probability in (0, 1]. Use lower values for weak layout cues."
            ),
            "invisible_region_nodes[].target_probs": (
                "Unnormalized target-location scores keyed by every target_id. Values "
                "must be in (0, 1]. Do not use 0.0."
            ),
            "viewpoint_target_probs": (
                "Target-location scores for every distinct current viewpoint and visible "
                "neighboring viewpoint in the current step. Current viewpoint entries are "
                "binary direct-detection evidence. Visible-neighbor entries are soft "
                "prior scores."
            ),
            "viewpoint_target_probs[].id": (
                "Integer viewpoint id. It must be either a current viewpoint or a visible "
                "neighboring viewpoint from the observation context."
            ),
            "viewpoint_target_probs[].target_probs": (
                "Dictionary keyed by every target_id. For a current viewpoint, use 1.0 "
                "if the target is directly detected there, otherwise 0.0. This binary "
                "rule applies only to current viewpoints. For visible neighboring "
                "viewpoints that are not current, use soft scores in (0, 1] and do not "
                "use 0.0."
            ),
            "viewpoint_node_assigns": (
                "Region-centered viewpoint assignments for the current step. Every "
                "current viewpoint and every distinct visible neighboring viewpoint must "
                "appear exactly once. Reuse fixed non-current assignments from the graph "
                "summary and avoid conflicts."
            ),
            "viewpoint_node_assigns[].region_node_id": (
                "Region id containing the assigned viewpoints. If it is a current_region_node_id, "
                "it must be listed in visible_region_nodes."
            ),
            "viewpoint_node_assigns[].assigned_viewpoint_node_indices": (
                "Integer viewpoint ids assigned to this region. Current viewpoints must "
                "be assigned to their agents' current_region_node_id."
            ),
            "new_edges": (
                "Uncertain hypothesis edges. Use legal VV or VZ edges only. If an "
                "invisible region is returned, add at least one nearby VZ edge unless all "
                "possible edges violate the rules. Use low exist_prob for weak edges."
            ),
            "new_edges[].i": (
                "One endpoint id. It may be a viewpoint or region. For VV, it must be an "
                "unvisited viewpoint."
            ),
            "new_edges[].j": (
                "Other endpoint id. Never region-region. For VV, it must be an unvisited "
                "viewpoint. Because edges are undirected, do not output both directions."
            ),
            "new_edges[].edge_type": "Use VV only for a hypothesized direct connection between two unvisited non-current viewpoint nodes with clear layout evidence. Use VZ for a viewpoint-region edge.",
            "new_edges[].exist_prob": "Edge existence probability in (0, 1].",
            "new_edges[].dist": (
                "Estimated distance in meters. For VZ, this is surrogate approach effort, "
                "not literal executable motion."
            ),
            "edge_distance_variances": (
                "Step-level variances for MLLM-generated distances. Must contain exactly "
                "viewpoint_viewpoint and viewpoint_region."
            ),
            "edge_distance_variances.viewpoint_viewpoint": (
                "Positive variance for ungrounded VV distance estimates."
            ),
            "edge_distance_variances.viewpoint_region": (
                "Positive variance for VZ surrogate distance estimates."
            ),
            "detections": (
                "Direct visual detections only. One item per agent. Do not set true from "
                "semantic guess or target-location probability."
            ),
            "detections[].agent_id": "Must match an input agent id exactly.",
            "detections[].target_indices": "Every target_id exactly once. Order must match founds.",
            "detections[].founds": (
                "JSON booleans. founds[k] is true only if target_indices[k] is directly "
                "visible in that agent panorama."
            ),
        }

        def round_json_value(value):
            if isinstance(value, bool) or value is None:
                return value
            if isinstance(value, float):
                return round(value, 4)
            if isinstance(value, list):
                return [round_json_value(item) for item in value]
            if isinstance(value, dict):
                return {
                    key: round_json_value(item)
                    for key, item in value.items()
                    if key
                    not in {
                        "targets",
                        "current_observation_context",
                    }
                }
            return value

        prompt_graph_summary = round_json_value(graph_summary)

        # Viewpoint labels are usually long scan ids and do not help the MLLM.
        # Region labels are kept because they carry semantic meaning.
        for node in prompt_graph_summary.get("nodes", []):
            if node.get("type") == "viewpoint":
                node.pop("label", None)

        system_message = dedent(
            """
            You are an indoor hypothesis-graph proposal module for cooperative many-agent, many-target navigation. Analyze one annotated RGB panorama per agent and the compact shared graph summary. Propose an uncertain graph update for downstream optimization. Do not select robot actions or produce a final map.

            The graph has viewpoint nodes for executable robot poses and region nodes for semantic zones. Use the provided agent ids, target_ids, viewpoint ids, and region ids exactly. Use target_id in target_probs and detections[].target_indices. Use target descriptions only to understand the targets.

            Return exactly one valid JSON object matching the user schema. Do not output markdown, code fences, comments, text outside JSON, extra top-level keys, trailing commas, or non-JSON booleans.

            Required top-level keys:
            agents, visible_region_nodes, invisible_region_nodes, viewpoint_target_probs, viewpoint_node_assigns, new_edges, edge_distance_variances, detections.

            Core rules:
            - The per-agent observation context is the source of truth for current agent locations, even if the compact graph summary has older node status values.
            - agents has one item per agent. current_region_node_id is the region containing the agent current viewpoint and must appear in visible_region_nodes. Reuse existing region ids and labels when matched.
            - visible_region_nodes are directly supported by current panoramas. invisible_region_nodes are unseen but layout-supported adjacent regions. Use at most 5 current-step region nodes total.
            - Region labels must be room or area labels, not object names. Include appearance cue, area type, and physical relative location cue. Do not mention agent ids or names. Avoid generic labels unless they include both appearance and relative location cues.
            - Region target_probs and non-current viewpoint target_probs must contain every target_id with values in (0, 1]. Current viewpoint target_probs are binary direct-detection evidence: 1.0 if directly detected there, otherwise 0.0.
            - Use target descriptions to make target-specific scores when evidence differs. Equal scores are allowed only when evidence is equally weak or when current-viewpoint binary evidence gives the same value.
            - viewpoint_target_probs must include every current agent viewpoint and every distinct visible neighboring viewpoint.
            - viewpoint_node_assigns must use region_node_id and assigned_viewpoint_node_indices. Every current viewpoint and every distinct visible neighboring viewpoint must appear exactly once. Current viewpoints must be assigned to their agents' current_region_node_id. Reuse fixed non-current assignments from the graph summary.
            - new_edges may contain only VV or VZ edges. Never use region-region edges. Do not add edges between a current viewpoint and its visible neighboring viewpoints, because those local edges are already provided by the navigation system. Do not add an edge between a viewpoint and its assigned region.
            - A VV edge may be proposed only between two unvisited non-current viewpoint nodes when the current panoramas provide clear layout evidence that they are directly connected, such as the same open room area, a continuous corridor, or an unobstructed doorway. Do not infer a VV edge only because both viewpoints are visible from the same current viewpoint. If evidence is weak but plausible, use low exist_prob. If evidence is unclear, omit the VV edge.
            - A VZ edge should connect a viewpoint to a semantic region with no assigned viewpoints.
            """
        ).strip()

        user_message = (
            dedent(
                """
                Shared target set:
                {targets_json}

                Compact shared graph summary:
                {graph_summary_json}

                Per-agent observation context:
                {agent_context_json}

                Current-step interpretation note:
                - The observation context is the source of truth for current agent locations.
                - If a current viewpoint already appears in the graph summary, still treat it as current and grounded for this step.
                - If a current region already appears in the graph summary, reuse its id and label and still include it in visible_region_nodes.

                Output schema example. Use keys and value types only. Do not copy example values unless supported:
                {schema_json}

                Field descriptions:
                {field_descriptions_json}

                Current step request:
                - Identify each agent current semantic region.
                - Include every current viewpoint and every distinct visible neighboring viewpoint exactly once in viewpoint_node_assigns.
                - Include every current viewpoint and every distinct visible neighboring viewpoint in viewpoint_target_probs.
                - For current viewpoint target_probs, use binary direct-detection evidence consistent with detections.
                - For visible neighboring viewpoint target_probs, use soft positive target-location scores.
                - Estimate region target_probs using target_id keys and target descriptions.
                - Report direct detections using target_indices and founds.
                - Propose only legal uncertain edges supported by observation and graph context.
                - Propose VV edges only when two unvisited non-current viewpoints are directly connected by clear layout evidence; do not add VV edges only because they are both visible from the same current viewpoint.
                - Return compact JSON only.
                """
            )
            .strip()
            .format(
                targets_json=json.dumps(target_records, indent=2, sort_keys=True),
                graph_summary_json=json.dumps(
                    prompt_graph_summary, indent=2, sort_keys=True
                ),
                agent_context_json=json.dumps(agent_context, indent=2, sort_keys=True),
                schema_json=json.dumps(schema, indent=2, sort_keys=True),
                field_descriptions_json=json.dumps(
                    field_descriptions, indent=2, sort_keys=True
                ),
            )
        )

        return system_message, user_message

    def _validate_payload(
        self,
        payload: Dict[str, object],
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
    ) -> None:
        required_top_level_keys = {
            "agents",
            "detections",
            "visible_region_nodes",
            "invisible_region_nodes",
            "viewpoint_target_probs",
            "viewpoint_node_assigns",
            "new_edges",
            "edge_distance_variances",
        }

        if not isinstance(payload, dict):
            raise TypeError("payload must be a dictionary.")

        extra_top_level_keys = set(payload).difference(required_top_level_keys)
        if extra_top_level_keys:
            raise KeyError(
                "Unexpected top-level keys: %s" % sorted(extra_top_level_keys)
            )

        missing_top_level_keys = required_top_level_keys.difference(payload)
        if missing_top_level_keys:
            raise KeyError(
                "Missing top-level keys: %s" % sorted(missing_top_level_keys)
            )

        def require_list(value, context: str) -> list:
            if not isinstance(value, list):
                raise TypeError("%s must be a list." % context)
            return value

        def require_dict(value, context: str) -> dict:
            if not isinstance(value, dict):
                raise TypeError("%s must be a dictionary." % context)
            return value

        def is_number(value) -> bool:
            return isinstance(value, (int, float)) and not isinstance(value, bool)

        def validate_probability(value, context: str) -> None:
            if not is_number(value):
                raise TypeError("%s must be numeric." % context)
            if not (0.0 < float(value) <= 1.0):
                raise ValueError("%s=%s is outside (0, 1]." % (context, value))

        def validate_binary_probability(value, context: str) -> None:
            if not is_number(value):
                raise TypeError("%s must be numeric." % context)
            if float(value) not in {0.0, 1.0}:
                raise ValueError(
                    "%s=%s must be binary, either 0.0 or 1.0." % (context, value)
                )

        def validate_positive_number(value, context: str) -> None:
            if not is_number(value):
                raise TypeError("%s must be numeric." % context)
            if float(value) <= 0.0:
                raise ValueError("%s=%s must be positive." % (context, value))

        observation_by_agent = {
            str(observation["agent_id"]): observation
            for observation in agent_observations
        }
        expected_agent_ids = set(observation_by_agent)

        target_ids = {str(target["target_id"]) for target in targets}
        if len(target_ids) != len(targets):
            raise ValueError("Target ids must be unique.")

        agents = require_list(payload["agents"], "agents")
        detections = require_list(payload["detections"], "detections")
        visible_region_nodes = require_list(
            payload["visible_region_nodes"], "visible_region_nodes"
        )
        invisible_region_nodes = require_list(
            payload["invisible_region_nodes"], "invisible_region_nodes"
        )
        viewpoint_target_probs = require_list(
            payload["viewpoint_target_probs"], "viewpoint_target_probs"
        )
        viewpoint_node_assigns = require_list(
            payload["viewpoint_node_assigns"], "viewpoint_node_assigns"
        )
        new_edges = require_list(payload["new_edges"], "new_edges")
        edge_distance_variances = require_dict(
            payload["edge_distance_variances"], "edge_distance_variances"
        )

        returned_agent_ids = set()
        agent_current_region = {}

        for agent_info in agents:
            agent_info = require_dict(agent_info, "agents[] item")

            expected_keys = {"agent_id", "current_region_node_id"}
            if set(agent_info) != expected_keys:
                raise KeyError(
                    "Each agents[] item must contain exactly %s, got %s."
                    % (sorted(expected_keys), sorted(agent_info))
                )

            agent_id = str(agent_info["agent_id"])
            returned_agent_ids.add(agent_id)
            agent_current_region[agent_id] = int(agent_info["current_region_node_id"])

        if returned_agent_ids != expected_agent_ids:
            raise ValueError(
                "Returned agent ids %s do not match expected agent ids %s."
                % (sorted(returned_agent_ids), sorted(expected_agent_ids))
            )

        # ------------------------------------------------------------------
        # Validate detections first, because current-viewpoint target_probs must
        # match direct detection evidence.
        # ------------------------------------------------------------------
        detection_by_agent = {}
        returned_detection_agent_ids = set()

        for detection in detections:
            detection = require_dict(detection, "detections[] item")

            expected_keys = {"agent_id", "target_indices", "founds"}
            if set(detection) != expected_keys:
                raise KeyError(
                    "Detection item keys %s do not match expected keys %s."
                    % (sorted(detection), sorted(expected_keys))
                )

            agent_id = str(detection["agent_id"])
            if agent_id not in expected_agent_ids:
                raise ValueError("Detection uses unknown agent id %s." % agent_id)

            if agent_id in returned_detection_agent_ids:
                raise ValueError("Duplicated detection item for agent %s." % agent_id)
            returned_detection_agent_ids.add(agent_id)

            target_indices = require_list(
                detection["target_indices"],
                "detections[].target_indices",
            )
            founds = require_list(
                detection["founds"],
                "detections[].founds",
            )

            returned_target_ids = {str(target_id) for target_id in target_indices}
            if returned_target_ids != target_ids:
                raise ValueError(
                    "Detection target_indices %s do not match expected target ids %s."
                    % (sorted(returned_target_ids), sorted(target_ids))
                )

            if len(target_indices) != len(founds):
                raise ValueError(
                    "detections[].target_indices and detections[].founds must have "
                    "the same length for agent %s." % agent_id
                )

            if len(target_indices) != len(returned_target_ids):
                raise ValueError(
                    "detections[].target_indices contains duplicated target ids for "
                    "agent %s." % agent_id
                )

            detection_by_agent[agent_id] = {}
            for target_id, found in zip(target_indices, founds):
                if not isinstance(found, bool):
                    raise TypeError(
                        "All detections[].founds values must be JSON booleans."
                    )
                detection_by_agent[agent_id][str(target_id)] = bool(found)

        if returned_detection_agent_ids != expected_agent_ids:
            raise ValueError(
                "Returned detection agent ids %s do not match expected agent ids %s."
                % (sorted(returned_detection_agent_ids), sorted(expected_agent_ids))
            )

        current_viewpoint_ids = {
            int(observation["current_viewpoint_index"])
            for observation in agent_observations
        }

        visible_viewpoint_ids = set()
        for observation in agent_observations:
            for item in observation["visible_viewpoints"]:
                visible_viewpoint_ids.add(int(item["viewpoint_index"]))

        all_current_step_viewpoint_ids = current_viewpoint_ids | visible_viewpoint_ids

        current_viewpoint_detection = {}
        for observation in agent_observations:
            agent_id = str(observation["agent_id"])
            current_viewpoint_id = int(observation["current_viewpoint_index"])
            agent_detection = detection_by_agent[agent_id]

            if current_viewpoint_id in current_viewpoint_detection:
                if current_viewpoint_detection[current_viewpoint_id] != agent_detection:
                    raise ValueError(
                        "Current viewpoint %s is shared by multiple agents with "
                        "inconsistent detection results." % current_viewpoint_id
                    )

            current_viewpoint_detection[current_viewpoint_id] = agent_detection

        def validate_target_probs_positive(
            target_probs: Dict[str, object],
            context: str,
        ) -> None:
            target_probs = require_dict(target_probs, context + ".target_probs")

            returned_target_ids = {str(key) for key in target_probs}
            if returned_target_ids != target_ids:
                raise ValueError(
                    "%s target_probs keys %s do not match expected target ids %s."
                    % (context, sorted(returned_target_ids), sorted(target_ids))
                )

            for target_id, value in target_probs.items():
                validate_probability(
                    value,
                    "%s.target_probs[%s]" % (context, target_id),
                )

        def validate_target_probs_current_viewpoint(
            viewpoint_id: int,
            target_probs: Dict[str, object],
            context: str,
        ) -> None:
            target_probs = require_dict(target_probs, context + ".target_probs")

            returned_target_ids = {str(key) for key in target_probs}
            if returned_target_ids != target_ids:
                raise ValueError(
                    "%s target_probs keys %s do not match expected target ids %s."
                    % (context, sorted(returned_target_ids), sorted(target_ids))
                )

            expected_detection = current_viewpoint_detection[viewpoint_id]

            for target_id, value in target_probs.items():
                validate_binary_probability(
                    value,
                    "%s.target_probs[%s]" % (context, target_id),
                )

                expected_value = 1.0 if expected_detection[str(target_id)] else 0.0
                if float(value) != expected_value:
                    raise ValueError(
                        "%s.target_probs[%s]=%s does not match direct detection. "
                        "Expected %.1f for current viewpoint %s."
                        % (context, target_id, value, expected_value, viewpoint_id)
                    )

        def validate_region_label(label: str, context: str) -> None:
            normalized_label = " ".join(label.lower().split())

            if "agent" in normalized_label:
                raise ValueError(
                    "%s label must not mention agent ids or agent names: %s"
                    % (context, label)
                )

        visible_region_ids = set()
        invisible_region_ids = set()

        total_region_count = len(visible_region_nodes) + len(invisible_region_nodes)
        if total_region_count > 5:
            raise ValueError(
                "At most 5 current-step semantic regions are allowed, got %s."
                % total_region_count
            )

        for region_key, region_list, region_id_set in (
            ("visible_region_nodes", visible_region_nodes, visible_region_ids),
            ("invisible_region_nodes", invisible_region_nodes, invisible_region_ids),
        ):
            for region in region_list:
                region = require_dict(region, "%s[] item" % region_key)

                expected_keys = {"id", "label", "exist_prob", "target_probs"}
                if set(region) != expected_keys:
                    raise KeyError(
                        "%s item keys %s do not match expected keys %s."
                        % (region_key, sorted(region), sorted(expected_keys))
                    )

                region_id = int(region["id"])
                if region_id in region_id_set:
                    raise ValueError(
                        "Duplicated region id %s in %s." % (region_id, region_key)
                    )
                region_id_set.add(region_id)

                if not isinstance(region["label"], str) or not region["label"].strip():
                    raise ValueError(
                        "%s region %s has an empty label." % (region_key, region_id)
                    )

                validate_region_label(
                    str(region["label"]).strip(),
                    "%s region %s" % (region_key, region_id),
                )

                validate_probability(
                    region["exist_prob"],
                    "%s region %s exist_prob" % (region_key, region_id),
                )

                validate_target_probs_positive(
                    region["target_probs"],
                    "%s region %s" % (region_key, region_id),
                )

        if visible_region_ids & invisible_region_ids:
            raise ValueError(
                "Region ids cannot appear in both visible_region_nodes and "
                "invisible_region_nodes: %s"
                % sorted(visible_region_ids & invisible_region_ids)
            )

        all_region_ids = visible_region_ids | invisible_region_ids

        for agent_id, current_region_node_id in agent_current_region.items():
            if current_region_node_id not in visible_region_ids:
                raise ValueError(
                    "Agent %s has current_region_node_id %s, but this id is not "
                    "included in visible_region_nodes."
                    % (agent_id, current_region_node_id)
                )

        # ------------------------------------------------------------------
        # Validate viewpoint_target_probs under the revised rule:
        # current viewpoints use binary detection evidence, while visible
        # neighboring viewpoints use soft positive scores.
        # ------------------------------------------------------------------
        returned_viewpoint_prob_ids = set()

        for item in viewpoint_target_probs:
            item = require_dict(item, "viewpoint_target_probs[] item")

            expected_keys = {"id", "target_probs"}
            if set(item) != expected_keys:
                raise KeyError(
                    "Each viewpoint_target_probs item must contain exactly %s, got %s."
                    % (sorted(expected_keys), sorted(item))
                )

            viewpoint_id = int(item["id"])

            if viewpoint_id not in all_current_step_viewpoint_ids:
                raise ValueError(
                    "viewpoint_target_probs id %s is not a current viewpoint or "
                    "visible neighboring viewpoint." % viewpoint_id
                )

            if viewpoint_id in returned_viewpoint_prob_ids:
                raise ValueError(
                    "Duplicated viewpoint_target_probs id %s." % viewpoint_id
                )
            returned_viewpoint_prob_ids.add(viewpoint_id)

            if viewpoint_id in current_viewpoint_ids:
                validate_target_probs_current_viewpoint(
                    viewpoint_id,
                    item["target_probs"],
                    "current viewpoint %s" % viewpoint_id,
                )
            else:
                validate_target_probs_positive(
                    item["target_probs"],
                    "visible neighboring viewpoint %s" % viewpoint_id,
                )

        if returned_viewpoint_prob_ids != all_current_step_viewpoint_ids:
            raise ValueError(
                "Returned viewpoint_target_probs ids %s do not match expected "
                "current-step viewpoint ids %s."
                % (
                    sorted(returned_viewpoint_prob_ids),
                    sorted(all_current_step_viewpoint_ids),
                )
            )

        # ------------------------------------------------------------------
        # Validate viewpoint assignments.
        # ------------------------------------------------------------------
        assigned_viewpoint_to_region = {}

        for item in viewpoint_node_assigns:
            item = require_dict(item, "viewpoint_node_assigns[] item")

            expected_keys = {"region_node_id", "assigned_viewpoint_node_indices"}
            if set(item) != expected_keys:
                raise KeyError(
                    "Each viewpoint_node_assigns item must contain exactly %s, got %s."
                    % (sorted(expected_keys), sorted(item))
                )

            region_node_id = int(item["region_node_id"])
            if region_node_id not in all_region_ids:
                raise ValueError(
                    "viewpoint_node_assigns uses unknown region_node_id %s."
                    % region_node_id
                )

            assigned_ids = require_list(
                item["assigned_viewpoint_node_indices"],
                "assigned_viewpoint_node_indices",
            )

            for viewpoint_id_raw in assigned_ids:
                viewpoint_id = int(viewpoint_id_raw)

                if viewpoint_id not in all_current_step_viewpoint_ids:
                    raise ValueError(
                        "Assigned viewpoint id %s is not a current viewpoint or "
                        "visible neighboring viewpoint." % viewpoint_id
                    )

                if viewpoint_id in assigned_viewpoint_to_region:
                    raise ValueError(
                        "Viewpoint id %s appears in more than one "
                        "assigned_viewpoint_node_indices list." % viewpoint_id
                    )

                assigned_viewpoint_to_region[viewpoint_id] = region_node_id

        returned_assignment_viewpoint_ids = set(assigned_viewpoint_to_region)

        if returned_assignment_viewpoint_ids != all_current_step_viewpoint_ids:
            raise ValueError(
                "Returned assigned viewpoint ids %s do not match expected ids %s."
                % (
                    sorted(returned_assignment_viewpoint_ids),
                    sorted(all_current_step_viewpoint_ids),
                )
            )

        for observation in agent_observations:
            agent_id = str(observation["agent_id"])
            current_viewpoint_id = int(observation["current_viewpoint_index"])
            agent_region_id = agent_current_region[agent_id]
            assigned_region_id = assigned_viewpoint_to_region.get(current_viewpoint_id)

            if assigned_region_id != agent_region_id:
                raise ValueError(
                    "Agent %s current viewpoint %s is assigned to region %s, "
                    "but its current_region_node_id is %s."
                    % (
                        agent_id,
                        current_viewpoint_id,
                        assigned_region_id,
                        agent_region_id,
                    )
                )

        region_to_assigned_viewpoints = {}
        for viewpoint_id, region_id in assigned_viewpoint_to_region.items():
            region_to_assigned_viewpoints.setdefault(region_id, set()).add(viewpoint_id)

        expected_variance_keys = {"viewpoint_viewpoint", "viewpoint_region"}
        if set(edge_distance_variances) != expected_variance_keys:
            raise KeyError(
                "edge_distance_variances must contain exactly %s, got %s."
                % (sorted(expected_variance_keys), sorted(edge_distance_variances))
            )

        for key, value in edge_distance_variances.items():
            validate_positive_number(
                value,
                "edge_distance_variances.%s" % key,
            )

        # ------------------------------------------------------------------
        # Validate new_edges.
        # ------------------------------------------------------------------
        for edge in new_edges:
            edge = require_dict(edge, "new_edges[] item")

            expected_keys = {"i", "j", "edge_type", "exist_prob", "dist"}
            if set(edge) != expected_keys:
                raise KeyError(
                    "new_edges item keys %s do not match expected keys %s."
                    % (sorted(edge), sorted(expected_keys))
                )

            i = int(edge["i"])
            j = int(edge["j"])
            edge_type = str(edge["edge_type"])

            if edge_type not in {"VV", "VZ"}:
                raise ValueError(
                    "Invalid edge_type %s. Expected 'VV' or 'VZ'." % edge_type
                )

            validate_probability(edge["exist_prob"], "new_edges[].exist_prob")
            validate_positive_number(edge["dist"], "new_edges[].dist")

            i_is_viewpoint = i in all_current_step_viewpoint_ids
            j_is_viewpoint = j in all_current_step_viewpoint_ids
            i_is_region = i in all_region_ids
            j_is_region = j in all_region_ids

            if edge_type == "VV":
                if not (i_is_viewpoint and j_is_viewpoint):
                    raise ValueError(
                        "VV edge (%s, %s) must connect two viewpoint nodes." % (i, j)
                    )
                if i == j:
                    raise ValueError(
                        "VV edge cannot be a self-edge: (%s, %s)." % (i, j)
                    )
                if i in current_viewpoint_ids or j in current_viewpoint_ids:
                    raise ValueError(
                        "VV edge (%s, %s) cannot use a current viewpoint." % (i, j)
                    )

            if edge_type == "VZ":
                valid_vz = (i_is_viewpoint and j_is_region) or (
                    i_is_region and j_is_viewpoint
                )
                if not valid_vz:
                    raise ValueError(
                        "VZ edge (%s, %s) must connect one viewpoint node and one "
                        "region node." % (i, j)
                    )

                viewpoint_id = i if i_is_viewpoint else j
                region_id = i if i_is_region else j

                assigned_region_id = assigned_viewpoint_to_region.get(viewpoint_id)
                if assigned_region_id == region_id:
                    raise ValueError(
                        "VZ edge (%s, %s) cannot connect a viewpoint to its assigned "
                        "region." % (i, j)
                    )

                if region_to_assigned_viewpoints.get(region_id):
                    raise ValueError(
                        "VZ edge (%s, %s) connects to region %s, but that region "
                        "already has assigned viewpoints %s."
                        % (
                            i,
                            j,
                            region_id,
                            sorted(region_to_assigned_viewpoints[region_id]),
                        )
                    )

    def propose_semantic_nodes(
        self,
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        graph: HypothesisGraph,
    ) -> Dict[str, object]:
        if self.save_debug_images:
            for image_index, observation in enumerate(agent_observations):
                panorama_image = observation["annotated_panorama"]
                if panorama_image.dtype != np.uint8:
                    panorama_image = panorama_image.astype(np.uint8)
                Image.fromarray(panorama_image).save(
                    "debug_agent_panorama_%s.png" % image_index
                )

        graph_summary = graph.get_mllm_summary()
        system_message, user_message = self._build_instruction(
            agent_observations=agent_observations,
            targets=targets,
            graph_summary=graph_summary,
        )

        # Resize panorama arrays to reduce input size while preserving visible neighboring viewpoint cues
        for observation in agent_observations:
            observation["annotated_panorama"] = self._resize_panorama_array(
                observation["annotated_panorama"],
                max_width=1280,
                quality=95,
            )
            with open(
                "debug_resized_agent_panorama_%s.jpg" % observation["agent_id"],
                "wb",
            ) as f:
                f.write(observation["annotated_panorama"])

        user_content = [{"type": "text", "text": user_message}]
        for observation in agent_observations:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": self._image_to_data_url(
                            observation["annotated_panorama"]
                        )
                    },
                }
            )

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_content},
        ]

        step_index = getattr(self, "semantic_raw_output_index", 0)
        # if the setting is enabled, read the saved raw outputs
        if getattr(
            self, "read_saved_raw_outputs", False
        ) and self._check_semantic_raw_output_exists(step_index):
            print(f"Reading saved raw output for step {step_index}")
            decoded = self._read_semantic_raw_output(step_index)
        else:
            print(f"Requesting completion for step {step_index}")
            decoded = self._request_completion(messages)
            # write raw output before parsing to preserve original text for debugging
            self._write_semantic_raw_output(step_index, decoded)
        self.semantic_raw_output_index = step_index + 1

        # decoded = '{\n  "agents": [\n    {\n      "agent_id": "agent0",\n      "current_region_node_id": 100\n    },\n    {\n      "agent_id": "agent1",\n      "current_region_node_id": 101\n    }\n  ],\n  "detections": [\n    {\n      "agent_id": "agent0",\n      "founds": [\n        false,\n        false\n      ],\n      "target_indices": [\n        "0",\n        "1"\n      ]\n    },\n    {\n      "agent_id": "agent1",\n      "founds": [\n        false,\n        false\n      ],\n      "target_indices": [\n        "0",\n        "1"\n      ]\n    }\n  ],\n  "edge_distance_variances": {\n    "viewpoint_region": 3.5,\n    "viewpoint_viewpoint": 1.5\n  },\n  "invisible_region_nodes": [\n    {\n      "exist_prob": 0.7,\n      "id": 102,\n      "label": "dimly lit bedroom area beyond doorway",\n      "target_probs": {\n        "0": 0.1,\n        "1": 0.1\n      }\n    }\n  ],\n  "new_edges": [\n    {\n      "dist": 3.0,\n      "edge_type": "VZ",\n      "exist_prob": 0.7,\n      "i": 40,\n      "j": 102\n    }\n  ],\n  "viewpoint_node_assigns": [\n    {\n      "assigned_viewpoint_node_indices": [\n        0,\n        16,\n        21\n      ],\n      "region_node_id": 100\n    },\n    {\n      "assigned_viewpoint_node_indices": [\n        9,\n        18,\n        40,\n        41\n      ],\n      "region_node_id": 101\n    }\n  ],\n  "viewpoint_target_probs": [\n    {\n      "id": 0,\n      "target_probs": {\n        "0": 0.0,\n        "1": 0.0\n      }\n    },\n    {\n      "id": 16,\n      "target_probs": {\n        "0": 0.2,\n        "1": 0.2\n      }\n    },\n    {\n      "id": 21,\n      "target_probs": {\n        "0": 0.1,\n        "1": 0.1\n      }\n    },\n    {\n      "id": 9,\n      "target_probs": {\n        "0": 0.0,\n        "1": 0.0\n      }\n    },\n    {\n      "id": 18,\n      "target_probs": {\n        "0": 0.3,\n        "1": 0.3\n      }\n    },\n    {\n      "id": 40,\n      "target_probs": {\n        "0": 0.1,\n        "1": 0.1\n      }\n    },\n    {\n      "id": 41,\n      "target_probs": {\n        "0": 0.1,\n        "1": 0.1\n      }\n    }\n  ],\n  "visible_region_nodes": [\n    {\n      "exist_prob": 1.0,\n      "id": 100,\n      "label": "bright living area with sofa and window",\n      "target_probs": {\n        "0": 0.1,\n        "1": 0.1\n      }\n    },\n    {\n      "exist_prob": 1.0,\n      "id": 101,\n      "label": "darker lounge area with seating",\n      "target_probs": {\n        "0": 0.2,\n        "1": 0.2\n      }\n    }\n  ]\n}'

        raw = self._strip_code_fences(decoded)

        payload = self._extract_json_object(raw)
        if payload is None:
            raise ValueError("Failed to parse joint MLLM JSON output")

        debugpy.breakpoint()  # Set a breakpoint here to inspect the raw payload before validation

        self._validate_payload(payload, agent_observations, targets)
        return payload

    @staticmethod
    def _resize_panorama_array(
        image: np.ndarray,
        max_width: int = 1280,
        quality: int = 75,
    ) -> bytes:
        """Resize and JPEG-compress a panorama image.

        The returned value is JPEG bytes, not a NumPy array.
        """
        if image.dtype != np.uint8:
            image = image.astype(np.uint8)

        pil_image = Image.fromarray(image).convert("RGB")

        if pil_image.width > max_width:
            new_height = int(pil_image.height * max_width / pil_image.width)
            pil_image = pil_image.resize(
                (max_width, new_height),
                Image.Resampling.LANCZOS,
            )

        buffer = io.BytesIO()
        pil_image.save(
            buffer,
            format="JPEG",
            quality=quality,
            optimize=True,
        )

        return buffer.getvalue()

    @staticmethod
    def _extract_json_object(raw_text: str) -> Optional[Dict[str, object]]:
        """
        Extract and parse one JSON object from the model output.

        Normal case:
        - The model returns a pure JSON object.

        Fallback case:
        - The model accidentally adds text before or after the JSON object.
        - This function finds the first valid JSON object and parses it.

        Returns:
            A parsed Python dictionary if successful.
            None if no valid JSON object can be extracted.
        """
        if raw_text is None:
            return None

        text = str(raw_text).strip()
        text = MLLMClient._strip_code_fences(text).strip()

        if not text:
            return None

        # First try the strict path.
        # This should work when response_format={"type": "json_object"} is respected.
        try:
            return MLLMClient._parse_json_strict(text)
        except ValueError:
            pass

        # Fallback: try to parse a JSON object starting from each "{".
        # json.JSONDecoder handles nested objects and braces inside strings correctly.
        decoder = json.JSONDecoder()

        for start_index, char in enumerate(text):
            if char != "{":
                continue

            candidate_text = text[start_index:]

            try:
                parsed, end_index = decoder.raw_decode(candidate_text)
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict):
                return parsed

        return None

    @staticmethod
    def _format_bytes(num_bytes: int) -> str:
        value = float(num_bytes)
        for unit in ["B", "KB", "MB", "GB"]:
            if value < 1024.0 or unit == "GB":
                return f"{value:.2f} {unit}"
            value /= 1024.0
        return f"{num_bytes} B"

    def _print_request_size_report(self, messages) -> None:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 42,
            "max_tokens": self.max_new_tokens,
            "response_format": {"type": "json_object"},
        }

        payload_text = json.dumps(payload, ensure_ascii=False)
        total_bytes = len(payload_text.encode("utf-8"))

        print("\n========== MLLM request size report ==========")
        print(f"Total JSON payload size: {self._format_bytes(total_bytes)}")

        for message_index, message in enumerate(messages):
            role = message.get("role", "unknown")
            content = message.get("content", "")

            if isinstance(content, str):
                size = len(content.encode("utf-8"))
                print(
                    f"message[{message_index}] role={role}, "
                    f"text size={self._format_bytes(size)}"
                )

            elif isinstance(content, list):
                print(
                    f"message[{message_index}] role={role}, "
                    f"content items={len(content)}"
                )

                for item_index, item in enumerate(content):
                    item_type = item.get("type")

                    if item_type == "text":
                        text = item.get("text", "")
                        size = len(text.encode("utf-8"))
                        print(
                            f"  item[{item_index}] text size="
                            f"{self._format_bytes(size)}"
                        )

                    elif item_type == "image_url":
                        url = item.get("image_url", {}).get("url", "")
                        data_url_size = len(url.encode("utf-8"))

                        if "," in url:
                            base64_part = url.split(",", 1)[1]
                            approximate_raw_image_size = int(len(base64_part) * 3 / 4)
                        else:
                            approximate_raw_image_size = 0

                        print(
                            f"  item[{item_index}] image data-url size="
                            f"{self._format_bytes(data_url_size)}, "
                            f"approx raw image size="
                            f"{self._format_bytes(approximate_raw_image_size)}"
                        )

        print("=============================================\n")
