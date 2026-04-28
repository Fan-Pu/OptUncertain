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
    ):
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                "Environment variable %s is required for the Hugging Face router API."
                % api_key_env
            )

        self.model_name = model_name
        self.base_url = base_url
        self.max_new_tokens = int(max_new_tokens)
        self.request_timeout = float(request_timeout)
        self.save_debug_images = bool(save_debug_images)
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=api_key,
            timeout=self.request_timeout,
        )

    @staticmethod
    def _strip_code_fences(raw_text: str) -> str:
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

    def _build_instruction(
        self,
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        graph_summary: Dict[str, object],
    ) -> tuple[str, str]:
        """Build a concise prompt for multi-agent multi-target graph hypotheses.

        Stable task rules are placed in the system message. The user message contains
        step-specific data, a compact schema example, field descriptions, and a
        short request. This avoids repeating long rule blocks in both messages.
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
                    "id": example_visible_viewpoint_id,
                    "target_probs": target_prob_template,
                }
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
            "agents": (
                "A list with one output item per agent. Each item summarizes the "
                "MLLM interpretation of that agent's current panorama."
            ),
            "agents[].agent_id": (
                "The agent id. It must exactly match one of the provided agent ids."
            ),
            "agents[].current_region_node_id": (
                "The integer id of the semantic region containing this agent's current "
                "viewpoint. This is the proximal semantic zone for the agent. Since the "
                "agent is physically located at the current viewpoint, this region is "
                "grounded by the observation. The id must refer to a region node listed "
                "in visible_region_nodes. If the region already exists in the shared graph "
                "summary, reuse the existing id and label, but still include it in "
                "visible_region_nodes."
            ),
            "visible_region_nodes": (
                "Semantic regions directly supported by the current panoramas. This list "
                "must include the current semantic region for every agent. It may include "
                "newly proposed visible regions and reused existing regions. Reuse an "
                "existing region id and label when the observed place matches a region "
                "already in the shared graph summary. If the region node exist in the shared graph summary, skip it."
            ),
            "visible_region_nodes[].id": (
                "The integer id of a visible semantic region. Use a new id only when the "
                "region is not already represented in the shared graph summary. Reuse an "
                "existing id when the observation matches an existing region."
            ),
            "visible_region_nodes[].label": (
                "A descriptive room or area label. It must not be an object name. It "
                "must include an appearance cue, a room or area type, and a physical relative "
                "location cue, such as near the doorway, beside the window, beyond the hallway, "
                "adjacent to the kitchen, or at the end of the room. Do not mention agent ids "
                "or agent names such as agent0 or agent1."
            ),
            "visible_region_nodes[].exist_prob": (
                "The estimated probability that this visible semantic region exists. Use "
                "1.0 only for a region that contains an agent's current viewpoint, because "
                "that region is grounded by the agent's physical location. For other visible "
                "regions, provide a probability in (0, 1] based on visual and layout evidence."
            ),
            "visible_region_nodes[].target_probs": (
                "A dictionary from every target_id to the initial target-location "
                "score for this visible semantic region. Although this field is named "
                "target_probs, the values are unnormalized prior scores in (0, 1]. "
                "Include all target_ids as keys. Do not use 0.0. These scores will be "
                "normalized downstream on the semantic-zone layer. Use the target descriptions to "
                "make target-specific scores when the scene gives semantic evidence. Do not "
                "assign identical scores to all targets unless the evidence is equally weak."
            ),
            "invisible_region_nodes": (
                "Hypothesized unseen semantic regions that may exist beyond the currently visible area. "
                "The model should actively infer 1 to 2 invisible regions even when evidence is weak "
                "or ambiguous, such as possible space beyond a doorway, wall boundary, opening, "
                "corridor direction, occlusion, or layout continuation. Use low exist_prob for weak "
                "hypotheses. Return [] only when generating an invisible region would clearly violate "
                "the scene layout."
            ),
            "invisible_region_nodes[].id": (
                "The integer id of an inferred invisible semantic region. Use a new id only "
                "when this region is not already represented in the shared graph summary."
            ),
            "invisible_region_nodes[].label": (
                "A descriptive room or area label for the inferred region. It must not be "
                "an object name. It must include an appearance cue, a room or area type, "
                "and a physical relative location cue, such as beyond the doorway, past the hallway, "
                "behind the wall opening, or adjacent to the visible room. Do not mention agent ids "
                "or agent names such as agent0 or agent1."
            ),
            "invisible_region_nodes[].exist_prob": (
                "The estimated probability that this inferred semantic region exists. Use "
                "lower values than directly visible regions unless the layout evidence is "
                "very strong."
            ),
            "invisible_region_nodes[].target_probs": (
                "A dictionary from every target_id to the initial target-location "
                "score for this visible semantic region. Although this field is named "
                "target_probs, the values are unnormalized prior scores in (0, 1]. "
                "Include all target_ids as keys. Do not use 0.0. These scores will be "
                "normalized downstream on the semantic-zone layer."
            ),
            "viewpoint_target_probs": (
                "A top-level list of target-location scores for visible neighboring viewpoint "
                "nodes in the current step. It must include each distinct visible neighboring "
                "viewpoint across all agents. It must not include any agent's current viewpoint, "
                "because current viewpoints are grounded and are updated from direct visual evidence."
            ),
            "viewpoint_target_probs[].id": (
                "The integer id of a visible neighboring viewpoint from the per-agent "
                "observation context. It must not be an agent's current viewpoint."
            ),
            "viewpoint_target_probs[].target_probs": (
                "A dictionary from every target_id to the initial target-location "
                "score for this visible neighboring viewpoint node. Although this field is named "
                "target_probs, the values are unnormalized prior scores in (0, 1]. "
                "Include all target_ids as keys. Do not use 0.0. These scores will be "
                "normalized downstream on the viewpoint layer. Do not use identical scores "
                "for all targets unless the visual and semantic evidence is equally weak."
            ),
            "viewpoint_node_assigns": (
                "A top-level list of region-to-viewpoint assignments for viewpoint nodes in "
                "the current step. Each item groups the viewpoint nodes assigned to one "
                "semantic region. Each viewpoint node that needs a current-step assignment "
                "must appear in exactly one assigned_viewpoint_node_indices list. If the same "
                "viewpoint is observed by multiple agents, include it only once and keep the "
                "assignment consistent."
            ),
            "viewpoint_node_assigns[].region_node_id": (
                "The integer id of the semantic region that contains the assigned viewpoint "
                "nodes. This region may be an existing region from the shared graph summary "
                "or a region returned in visible_region_nodes. If this region is an agent's "
                "current_region_node_id, it must be included in visible_region_nodes."
            ),
            "viewpoint_node_assigns[].assigned_viewpoint_node_indices": (
                "A list of integer viewpoint node ids assigned to this semantic region. Each "
                "viewpoint id must be either an agent's current viewpoint or a visible "
                "neighboring viewpoint from the per-agent observation context. Skip thoes viewpoint nodes "
                "that are already in the shared graph summary. A current "
                "viewpoint must be assigned to the current_region_node_id of the corresponding agent."
            ),
            "new_edges": (
                "Uncertain hypothesis edges for downstream optimization. The model should actively "
                "propose legal candidate edges, even when the evidence is weak. If an invisible_region_node "
                "is returned, propose at least one viewpoint_region edge from a nearby visible neighboring "
                "viewpoint to that invisible region. Use low exist_prob for weak hypotheses. "
                "Return [] only when every possible edge would violate the edge rules."
            ),
            "new_edges[].i": (
                "The integer id of one endpoint node. The endpoint may be a viewpoint node "
                "or a semantic region node. For a viewpoint_viewpoint edge, this endpoint "
                "must be an unvisited viewpoint node."
            ),
            "new_edges[].j": (
                "The integer id of the other endpoint node. The edge may connect "
                "viewpoint-viewpoint or viewpoint-region, but never region-region. For a "
                "viewpoint_viewpoint edge, this endpoint must be an unvisited viewpoint node. "
                "Because the edge is undirected, if edge {i,j} is included, the reverse {j,i} "
                "should not be included."
            ),
            "new_edges[].edge_type": (
                "The edge type. Use VV only for an edge between two unvisited "
                "viewpoint nodes. Use VZ for an edge between a viewpoint node "
                "and a semantic region node."
            ),
            "new_edges[].exist_prob": (
                "The estimated probability that this edge exists, in (0, 1]."
            ),
            "new_edges[].dist": (
                "The estimated travel distance in meters. For viewpoint-viewpoint edges, "
                "this is a hypothesized motion distance between two unvisited viewpoint nodes. "
                "For viewpoint-region edges, this is a surrogate approaching effort, not a "
                "literal executable motion."
            ),
            "edge_distance_variances": (
                "Step-level type variance values provided by the MLLM for MLLM-generated "
                "distance estimates in the current output. These correspond to the paper's "
                "variance parameters for ungrounded viewpoint-viewpoint edges and "
                "viewpoint-region edges."
            ),
            "edge_distance_variances.viewpoint_viewpoint": (
                "A positive numeric variance for the initial distance estimates of "
                "ungrounded viewpoint-viewpoint edges."
            ),
            "edge_distance_variances.viewpoint_region": (
                "A positive numeric variance for the initial surrogate distance estimates "
                "of viewpoint-region edges."
            ),
            "detections": (
                "A top-level list of direct target-detection results. It must contain one "
                "item per agent. This field reports direct visual detection only. Do not "
                "set a found value to true based only on semantic guess or target-location "
                "probability."
            ),
            "detections[].agent_id": (
                "The agent id for this detection result. It must exactly match one of the "
                "provided agent ids."
            ),
            "detections[].target_indices": (
                "A list of target ids for this agent's detection result. It must contain "
                "every target_id from the shared target set exactly once. The order must "
                "match the order of detections[].founds."
            ),
            "detections[].founds": (
                "A list of JSON booleans. founds[k] gives the direct detection result for "
                "target_indices[k]. Use true only if that target is directly visible in "
                "the panorama of the corresponding agent. Use false if the target is not "
                "directly visible."
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
                        "agent_current_vp_ids",
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
            You are an indoor hypothesis-graph proposal module for cooperative many-agent, many-target navigation.

            Analyze one annotated RGB panorama per agent and the compact shared graph summary.
            Propose an uncertain graph update for downstream optimization.
            Do not select robot actions and do not produce a final map.

            The graph has two layers:
            - viewpoint nodes are executable robot poses.
            - region nodes are semantic zones such as a kitchen area, hallway area, or bedroom area.

            Use the provided agent ids, target_ids, viewpoint ids, and region ids exactly.
            Use target_id as the key in target_probs and as the value in detections[].target_indices.
            Use target descriptions only to understand what the targets are.

            Return exactly one valid JSON object matching the schema in the user message.
            Do not output markdown, code fences, comments, or text outside JSON.
            Do not create extra top-level keys.
            Use JSON booleans true and false only.

            Required top-level keys:
            agents, visible_region_nodes, invisible_region_nodes, viewpoint_target_probs,
            viewpoint_node_assigns, new_edges, edge_distance_variances, detections.

            Output rules:
            - agents must contain one item per agent.
            - current_region_node_id is the semantic region containing the agent's current viewpoint.
            - Every current_region_node_id must appear in visible_region_nodes.
            - visible_region_nodes are directly supported by the current panoramas.
            - invisible_region_nodes are unseen but layout-supported adjacent regions. Return [] only when no plausible unseen region is supported.
            - Region labels must be room or area labels, not object names. Include an appearance cue, area type, and physical relative location cue, such as near doorway, beside window, beyond hallway, adjacent to kitchen, or at the end of the room.
            - Do not mention agent ids or agent names in region labels. For example, do not write near agent0 or near agent1. Use physical cues such as near doorway, beside bed, beyond bedroom doorway, or adjacent to hallway instead.
            - Do not use generic labels such as "living area with seating" or "bedroom area with bed" unless a relative location cue and an appearance cue are also included.
            - Use at most 5 current-step region nodes in total.
            - target_probs must contain every target_id, with numeric values in (0, 1]. Values do not need to sum to one.
            - Use the target descriptions to create target-specific target_probs. Do not give all targets the same target_probs unless visual and semantic evidence is equally weak for all targets.
            - viewpoint_target_probs must include only current-step visible neighboring viewpoints that need new target scores. Never include current agent viewpoints in viewpoint_target_probs.
            - viewpoint_node_assigns must use the region-centered format with region_node_id and assigned_viewpoint_node_indices.
            - Each current-step viewpoint that needs assignment must appear in exactly one assigned_viewpoint_node_indices list.
            - Current agent viewpoints must be assigned to their agents' current_region_node_id.
            - If a viewpoint or region already exists in the shared graph summary, reuse its existing assignment or region id unless the current observation grounds a previously ungrounded current viewpoint.
            - new_edges may contain only VV or VZ edges. Region-region edges are not allowed.
            - Do not add edges between a current viewpoint and its visible neighboring viewpoints. Those local edges are already provided by the navigation system.
            - Do not add an edge between a viewpoint and its assigned region.
            - A VZ edge should connect a viewpoint to a semantic region with no assigned viewpoints.
            - edge_distance_variances must contain exactly viewpoint_viewpoint and viewpoint_region, both positive.
            - detections must contain exactly one item per agent, using target_indices and founds.
            - Set founds[k]=true only when target_indices[k] is directly visible in that agent's panorama.
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

                Output schema example. Use the keys and value types, but do not copy example values unless supported by the current step:
                {schema_json}

                Field descriptions. Use this as the authoritative reference for each output field:
                {field_descriptions_json}

                Current step request:
                - Identify each agent's current semantic region.
                - Assign all current-step viewpoints that need assignment.
                - Estimate target-location scores using target_id keys.
                - In viewpoint_target_probs, include only visible neighboring viewpoints, not current agent viewpoints.
                - Make region labels specific by including an appearance cue, area type, and physical relative location cue.
                - Do not mention agent ids or agent names in region labels.
                - Use target descriptions to make target-specific target_probs when semantic evidence differs.
                - Avoid identical target_probs for all targets unless evidence is equally weak.
                - Report direct detections using target_indices and founds.
                - Propose legal uncertain edges only when supported by observations and graph context.
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

        if returned_agent_ids != expected_agent_ids:
            raise ValueError(
                "Returned agent ids %s do not match expected agent ids %s."
                % (sorted(returned_agent_ids), sorted(expected_agent_ids))
            )

        def validate_target_probs(
            target_probs: Dict[str, object], context: str
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

        def validate_region_label(label: str, context: str) -> None:
            normalized_label = " ".join(label.lower().split())

            if "agent" in normalized_label:
                raise ValueError(
                    "%s label must not mention agent ids or agent names: %s"
                    % (context, label)
                )

            relative_terms = (
                "near",
                "beside",
                "beyond",
                "adjacent",
                "next to",
                "behind",
                "in front of",
                "at the end",
                "along",
                "past",
                "by",
                "around",
                "across",
                "through",
            )
            if not any(term in normalized_label for term in relative_terms):
                raise ValueError(
                    "%s label must include a physical relative location cue, "
                    "such as near doorway, beside window, beyond hallway, "
                    "or adjacent to kitchen: %s" % (context, label)
                )

        visible_region_ids = set()
        invisible_region_ids = set()

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

                validate_target_probs(
                    region["target_probs"],
                    "%s region %s" % (region_key, region_id),
                )

        all_region_ids = visible_region_ids | invisible_region_ids

        for agent_info in agents:
            agent_id = str(agent_info["agent_id"])
            current_region_node_id = int(agent_info["current_region_node_id"])

            if current_region_node_id not in visible_region_ids:
                raise ValueError(
                    "Agent %s has current_region_node_id %s, but this id is not "
                    "included in visible_region_nodes."
                    % (agent_id, current_region_node_id)
                )

        current_viewpoint_ids = {
            int(observation["current_viewpoint_index"])
            for observation in agent_observations
        }

        visible_viewpoint_ids = set()
        for observation in agent_observations:
            for item in observation["visible_viewpoints"]:
                visible_viewpoint_ids.add(int(item["viewpoint_index"]))

        # viewpoint_target_probs must exclude agents' current viewpoints.
        # It should contain only visible neighboring viewpoints.
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
            if viewpoint_id in returned_viewpoint_prob_ids:
                raise ValueError(
                    "Duplicated viewpoint_target_probs id %s." % viewpoint_id
                )
            returned_viewpoint_prob_ids.add(viewpoint_id)

            validate_target_probs(
                item["target_probs"],
                "viewpoint %s" % viewpoint_id,
            )

        if returned_viewpoint_prob_ids != visible_viewpoint_ids:
            raise ValueError(
                "Returned viewpoint_target_probs ids %s do not match expected "
                "visible viewpoint ids %s."
                % (sorted(returned_viewpoint_prob_ids), sorted(visible_viewpoint_ids))
            )

        expected_assignment_viewpoint_ids = (
            current_viewpoint_ids | visible_viewpoint_ids
        )
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

                if viewpoint_id in assigned_viewpoint_to_region:
                    raise ValueError(
                        "Viewpoint id %s appears in more than one "
                        "assigned_viewpoint_node_indices list." % viewpoint_id
                    )

                assigned_viewpoint_to_region[viewpoint_id] = region_node_id

        returned_assignment_viewpoint_ids = set(assigned_viewpoint_to_region)

        if returned_assignment_viewpoint_ids != expected_assignment_viewpoint_ids:
            raise ValueError(
                "Returned assigned viewpoint ids %s do not match expected ids %s."
                % (
                    sorted(returned_assignment_viewpoint_ids),
                    sorted(expected_assignment_viewpoint_ids),
                )
            )

        for observation in agent_observations:
            agent_id = str(observation["agent_id"])
            current_viewpoint_id = int(observation["current_viewpoint_index"])

            agent_region_id = None
            for agent_info in agents:
                if str(agent_info["agent_id"]) == agent_id:
                    agent_region_id = int(agent_info["current_region_node_id"])
                    break

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

        all_viewpoint_ids = current_viewpoint_ids | visible_viewpoint_ids

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

            i_is_viewpoint = i in all_viewpoint_ids
            j_is_viewpoint = j in all_viewpoint_ids
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

            if edge_type == "VZ":
                valid_vz = (i_is_viewpoint and j_is_region) or (
                    i_is_region and j_is_viewpoint
                )
                if not valid_vz:
                    raise ValueError(
                        "VZ edge (%s, %s) must connect one viewpoint node and one "
                        "region node." % (i, j)
                    )

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

            for found in founds:
                if not isinstance(found, bool):
                    raise TypeError(
                        "All detections[].founds values must be JSON booleans."
                    )

        if returned_detection_agent_ids != expected_agent_ids:
            raise ValueError(
                "Returned detection agent ids %s do not match expected agent ids %s."
                % (sorted(returned_detection_agent_ids), sorted(expected_agent_ids))
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

        # decoded = self._request_completion(messages)
        # raw = self._strip_code_fences(decoded)

        raw = '{\n  "agents": [\n    {\n      "agent_id": "agent0",\n      "current_region_node_id": 100\n    },\n    {\n      "agent_id": "agent1",\n      "current_region_node_id": 101\n    }\n  ],\n  "detections": [\n    {\n      "agent_id": "agent0",\n      "founds": [\n        false,\n        false\n      ],\n      "target_indices": [\n        "0",\n        "1"\n      ]\n    },\n    {\n      "agent_id": "agent1",\n      "founds": [\n        false,\n        false\n      ],\n      "target_indices": [\n        "0",\n        "1"\n      ]\n    }\n  ],\n  "edge_distance_variances": {\n    "viewpoint_region": 4.0,\n    "viewpoint_viewpoint": 1.0\n  },\n  "invisible_region_nodes": [\n    {\n      "exist_prob": 0.5,\n      "id": 102,\n      "label": "dimly lit hallway area beyond the bedroom doorway",\n      "target_probs": {\n        "0": 0.05,\n        "1": 0.05\n      }\n    }\n  ],\n  "new_edges": [\n    {\n      "dist": 3.0,\n      "edge_type": "VZ",\n      "exist_prob": 0.5,\n      "i": 40,\n      "j": 102\n    }\n  ],\n  "viewpoint_node_assigns": [\n    {\n      "assigned_viewpoint_node_indices": [\n        0,\n        16,\n        21\n      ],\n      "region_node_id": 100\n    },\n    {\n      "assigned_viewpoint_node_indices": [\n        9,\n        18,\n        40,\n        41\n      ],\n      "region_node_id": 101\n    }\n  ],\n  "viewpoint_target_probs": [\n    {\n      "id": 16,\n      "target_probs": {\n        "0": 0.1,\n        "1": 0.1\n      }\n    },\n    {\n      "id": 21,\n      "target_probs": {\n        "0": 0.1,\n        "1": 0.1\n      }\n    },\n    {\n      "id": 18,\n      "target_probs": {\n        "0": 0.05,\n        "1": 0.05\n      }\n    },\n    {\n      "id": 40,\n      "target_probs": {\n        "0": 0.05,\n        "1": 0.05\n      }\n    },\n    {\n      "id": 41,\n      "target_probs": {\n        "0": 0.05,\n        "1": 0.05\n      }\n    }\n  ],\n  "visible_region_nodes": [\n    {\n      "exist_prob": 1.0,\n      "id": 100,\n      "label": "brightly lit living area near the television",\n      "target_probs": {\n        "0": 0.1,\n        "1": 0.1\n      }\n    },\n    {\n      "exist_prob": 1.0,\n      "id": 101,\n      "label": "darker bedroom area beside the bed",\n      "target_probs": {\n        "0": 0.05,\n        "1": 0.05\n      }\n    }\n  ]\n}'

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
