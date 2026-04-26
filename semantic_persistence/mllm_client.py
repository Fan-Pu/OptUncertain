from __future__ import annotations

import base64
from doctest import debug
import io
import json
import os
from textwrap import dedent
from typing import TYPE_CHECKING, Dict, List
import cv2

import debugpy
import numpy as np
from openai import BadRequestError, OpenAI
from PIL import Image

if TYPE_CHECKING:
    from semantic_persistence import HypothesisGraph


class MLLMClient:
    def __init__(
        self,
        model_name: str = "meta-llama/Llama-4-Maverick-17B-128E-Instruct:cheapest",
        base_url: str = "https://router.huggingface.co/v1",
        api_key_env: str = "HF_TOKEN",
        max_new_tokens: int = 2000,
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
    def _extract_json_object(candidate_raw: str):
        try:
            parsed = json.loads(candidate_raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        for start_index in range(len(candidate_raw)):
            if candidate_raw[start_index] != "{":
                continue
            for end_index in range(len(candidate_raw), start_index, -1):
                if candidate_raw[end_index - 1] != "}":
                    continue
                candidate = candidate_raw[start_index:end_index]
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    continue
        return None

    @staticmethod
    def _image_to_data_url(image) -> str:
        if isinstance(image, np.ndarray):
            if image.dtype != np.uint8:
                image = image.astype(np.uint8)
            pil_image = Image.fromarray(image)
        else:
            pil_image = image
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return "data:image/png;base64,%s" % encoded

    def _request_completion(self, messages) -> str:
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.0,
                top_p=0.9,
                max_tokens=self.max_new_tokens,
            )
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
        """Build the MLLM instruction prompt for multi-agent multi-target graph hypothesis generation."""

        target_names = [str(target["description"]) for target in targets]

        if len(target_names) != len(set(target_names)):
            raise ValueError(
                "Target descriptions must be unique because each description is used "
                "as the target name and id."
            )

        agent_context = []

        for image_index, observation in enumerate(agent_observations):
            agent_id = str(observation["agent_id"])
            current_viewpoint_index = int(observation["current_viewpoint_index"])

            visible_viewpoints = [
                {
                    "viewpoint_index": int(item["viewpoint_index"]),
                    "distance": float(item["distance"]),
                }
                for item in observation["visible_viewpoints"]
            ]

            agent_context.append(
                {
                    "agent_id": agent_id,
                    "image_index": image_index,
                    "current_viewpoint_index": current_viewpoint_index,
                    "visible_viewpoints": visible_viewpoints,
                }
            )

        target_prob_template = {
            target_name: 0.01 for target_name in sorted(target_names)
        }

        example_agent_id = (
            agent_context[0]["agent_id"] if len(agent_context) > 0 else "agent0"
        )

        example_current_viewpoint_id = (
            agent_context[0]["current_viewpoint_index"]
            if len(agent_context) > 0
            else 10
        )

        example_visible_viewpoint_id = (
            agent_context[0]["visible_viewpoints"][0]["viewpoint_index"]
            if len(agent_context) > 0
            and len(agent_context[0]["visible_viewpoints"]) > 0
            else 13
        )

        detection_template = [
            {
                "agent_id": example_agent_id,
                "target": target_name,
                "found": False,
            }
            for target_name in sorted(target_names)
        ]

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
                    "target_probs": target_prob_template,
                },
                {
                    "id": example_visible_viewpoint_id,
                    "target_probs": target_prob_template,
                },
            ],
            "viewpoint_node_assigns": [
                {
                    "viewpoint_id": example_current_viewpoint_id,
                    "assign_region_node_id": 100,
                },
                {
                    "viewpoint_id": example_visible_viewpoint_id,
                    "assign_region_node_id": 100,
                },
            ],
            "new_edges": [
                {
                    "i": example_visible_viewpoint_id,
                    "j": 102,
                    "edge_type": "viewpoint_region",
                    "exist_prob": 0.6,
                    "dist": 2.5,
                }
            ],
            "edge_distance_variances": {
                "viewpoint_viewpoint": 1.0,
                "viewpoint_region": 4.0,
            },
            "detections": detection_template,
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
                "already in the shared graph summary."
            ),
            "visible_region_nodes[].id": (
                "The integer id of a visible semantic region. Use a new id only when the "
                "region is not already represented in the shared graph summary. Reuse an "
                "existing id when the observation matches an existing region."
            ),
            "visible_region_nodes[].label": (
                "A descriptive room or area label. It must not be an object name. It "
                "should include an appearance cue, a room or area type, and a relative "
                "location cue."
            ),
            "visible_region_nodes[].exist_prob": (
                "The estimated probability that this visible semantic region exists. Use "
                "1.0 only for a region that contains an agent's current viewpoint, because "
                "that region is grounded by the agent's physical location. For other visible "
                "regions, provide a probability in (0, 1] based on visual and layout evidence."
            ),
            "visible_region_nodes[].target_probs": (
                "A dictionary from every target description to the initial target-location "
                "score for this visible semantic region. The target description is used "
                "directly as the target name and id. Although this field is named "
                "target_probs, the values are unnormalized prior scores in (0, 1]. Include "
                "all target descriptions as keys. Do not use 0.0. These scores will be "
                "normalized downstream on the semantic-zone layer."
            ),
            "invisible_region_nodes": (
                "Semantic regions that are not directly visible but are strongly suggested "
                "by layout cues, such as a doorway, corridor continuation, or partial room "
                "opening. Do not create invisible regions without clear support."
            ),
            "invisible_region_nodes[].id": (
                "The integer id of an inferred invisible semantic region. Use a new id only "
                "when this region is not already represented in the shared graph summary."
            ),
            "invisible_region_nodes[].label": (
                "A descriptive room or area label for the inferred region. It must not be "
                "an object name. It should include an appearance cue, a room or area type, "
                "and a relative location cue."
            ),
            "invisible_region_nodes[].exist_prob": (
                "The estimated probability that this inferred semantic region exists. Use "
                "lower values than directly visible regions unless the layout evidence is "
                "very strong."
            ),
            "invisible_region_nodes[].target_probs": (
                "A dictionary from every target description to the initial target-location "
                "score for this inferred semantic region. The target description is used "
                "directly as the target name and id. Although this field is named "
                "target_probs, the values are unnormalized prior scores in (0, 1]. Include "
                "all target descriptions as keys. Do not use 0.0. These scores will be "
                "normalized downstream on the semantic-zone layer."
            ),
            "viewpoint_target_probs": (
                "A top-level list of target-location scores for viewpoint nodes in the current "
                "step. It must include each distinct current viewpoint and each distinct visible "
                "neighboring viewpoint across all agents."
            ),
            "viewpoint_target_probs[].id": (
                "The integer id of a viewpoint node. It must be either an agent's current "
                "viewpoint or a visible neighboring viewpoint from the per-agent observation "
                "context."
            ),
            "viewpoint_target_probs[].target_probs": (
                "A dictionary from every target description to the initial target-location "
                "score for this viewpoint node. The target description is used directly as "
                "the target name and id. Although this field is named target_probs, the "
                "values are unnormalized prior scores in (0, 1]. Include all target "
                "descriptions as keys. Do not use 0.0. These scores will be normalized "
                "downstream on the viewpoint layer."
            ),
            "viewpoint_node_assigns": (
                "A top-level list of viewpoint-to-region assignments for viewpoint nodes in "
                "the current step. It must contain exactly one assignment for each distinct "
                "current viewpoint and each distinct visible neighboring viewpoint across all "
                "agents. If the same viewpoint is observed by multiple agents, include it only "
                "once and keep the assignment consistent."
            ),
            "viewpoint_node_assigns[].viewpoint_id": (
                "The integer id of a viewpoint node. It must be either an agent's current "
                "viewpoint or a visible neighboring viewpoint from the per-agent observation "
                "context."
            ),
            "viewpoint_node_assigns[].assign_region_node_id": (
                "The integer id of the semantic region that physically contains this viewpoint. "
                "This region may be an existing region from the shared graph summary or a "
                "region returned in visible_region_nodes. A current viewpoint must be assigned "
                "to the current_region_node_id of the corresponding agent, and that "
                "current_region_node_id must be included in visible_region_nodes."
            ),
            "new_edges": (
                "Candidate undirected hypothesis-graph edges proposed from the current "
                "observation and graph context. Each item represents one non-directional edge "
                "{i,j}. Directed arcs are introduced later only by the optimization model."
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
                "The edge type. Use viewpoint_viewpoint only for an edge between two unvisited "
                "viewpoint nodes. Use viewpoint_region for an edge between a viewpoint node "
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
                "A top-level list of direct target-detection results. This field reports "
                "direct visual detection only. Do not set found=true based only on semantic "
                "guess or target-location probability."
            ),
            "detections[].agent_id": (
                "The agent id for this detection result. It must exactly match one of the "
                "provided agent ids."
            ),
            "detections[].target": (
                "The target description for this detection result. The target description is "
                "used directly as the target name and id. It must exactly match one of the "
                "provided target descriptions."
            ),
            "detections[].found": (
                "Use true only if the target is directly visible in the panorama of the "
                "corresponding agent. Use false if the target is not directly visible."
            ),
        }

        system_message = dedent(
            """
            You are an indoor hypothesis-graph proposal module for cooperative many-agent, many-target navigation.

            Your task is to analyze one annotated panorama per agent and the accumulated graph summary.
            You must propose uncertain graph hypotheses for downstream optimization.
            You are not directly selecting robot actions.
            You are not producing a final map.
            Your output is an uncertain hypothesis graph update.

            The graph has two spatial layers.

            The semantic layer contains region nodes.
            A region node represents a room or area, such as a kitchen area, hallway area, or bedroom area.
            Region nodes provide high-level semantic information but are not directly executable robot poses.

            The viewpoint layer contains viewpoint nodes.
            A viewpoint node represents a feasible robot pose.
            Current viewpoint nodes and visible neighboring viewpoint nodes are provided by the navigation system.
            The current viewpoint and visible neighboring viewpoints together form the current-step viewpoint set.

            A viewpoint assignment links a viewpoint node to the semantic region that physically contains it.
            Every current viewpoint and every visible neighboring viewpoint must be assigned to exactly one semantic region.

            Use the provided agent ids and target descriptions exactly.
            Each target description is used directly as the target name and id.
            Node ids and viewpoint ids must be integers.
            Existence probabilities and edge-existence probabilities must be numeric values in (0, 1], not strings.
            Every target_probs value must be a positive numeric value in (0, 1], not a string.
            Distances and variances must be positive numeric values, not strings.
            Use JSON booleans for found.
            Return compact JSON only.
            Do not output markdown.
            Do not output explanations outside JSON.

            Each input image is one annotated panorama for one agent.
            Image i corresponds to the agent whose context has image_index = i.
            Text numbers in a panorama indicate visible neighboring viewpoints.
            The same text number can appear multiple times and always refers to the same viewpoint.

            The MLLM input does not include depth images.
            The current implementation provides annotated RGB panoramas and known local distances.
            Depth information and local action-space distances are handled by the navigation system.
            Do not assume, infer, or request depth images.
            Do not infer local distances between a current viewpoint and its visible neighboring viewpoints; those distances are already provided.

            Region-label rules:
            - Region labels must be room or area labels only.
            - Region labels must not be object names.
            - Each region label must include an appearance cue, a room or area type, and a relative location cue.

            Good region-label examples:
            - modern living room area with curved sofa near kitchen bar
            - open dining and kitchen area with stools beside living room
            - minimalist bedroom area with large bed near hallway

            Bad region-label examples:
            - living room area
            - kitchen area
            - bedroom area
            - sofa
            - table

            Region-generation rules:
            - Do not generate too many region nodes.
            - A maximum of 5 current-step semantic regions total may be returned at each step.
            - When a region is revisited, reuse the previous region id and label from the shared graph summary.
            - Only propose a new region when the evidence suggests a different physical area.
            - Do not duplicate two region nodes that refer to the same physical area.

            Target-probability rules:
            - Every target_probs dictionary must contain every target description as a key.
            - Each target description is used directly as the target name and id.
            - Although this field is named target_probs, the values are unnormalized initial target-location scores.
            - Every target_probs value must be strictly larger than 0 and no larger than 1.
            - Do not output 0.0 for any target_probs value.
            - Estimate target-location scores separately for each target description.
            - Target-location scores are initial hypotheses for downstream Bayesian graph updating.
            - The scores do not need to sum to one in the MLLM output.
            - The downstream graph update will normalize target-location probabilities separately on the viewpoint layer and the semantic-region layer.
            - A target can have low but positive probability in a semantically plausible region even when it is not directly detected.
            - Direct detection and target-location probability are different fields.
            - Set detections[].found=true only when the target is directly visible.

            Detection rules:
            - For every agent, detections must contain one item for every target description.
            - Each detection item must contain exactly agent_id, target, and found.
            - detections[].target must be one of the provided target descriptions.
            - Do not output target_id in detections.
            - Set found=true only when the target is directly visible in the panorama of the corresponding agent.
            - Set found=false when the target is not directly visible.
            - Do not set found=true based only on semantic plausibility or target-location probability.

            Edge rules:
            - Use new_edges for undirected hypothesis-graph edges.
            - No region-to-region edges are allowed.
            - new_edges may contain viewpoint-viewpoint edges or viewpoint-region edges.
            - A viewpoint-viewpoint edge proposed by the MLLM must connect two unvisited viewpoint nodes only.
            - Do not propose a viewpoint-viewpoint edge if either endpoint is an agent's current viewpoint or any grounded or visited viewpoint indicated by the shared graph summary.
            - Do not propose edges between an agent's current viewpoint and its visible neighboring viewpoints.
            Those local action-space connections are already provided and verified by the navigation system.
            - Do not propose an edge between a viewpoint node and its assigned region node.
            The assignment already represents this relation.
            - A viewpoint-region edge should only be used for a semantic region with no assigned viewpoint nodes.
            Its distance is a surrogate approaching effort, not a literal executable motion.
            - A viewpoint-viewpoint edge should only be proposed when layout evidence suggests a possible connection between two unvisited viewpoint nodes that is not already provided as a current local action-space edge.
            - Return an empty new_edges list when no legal edge is supported by the observation and graph context.
            - Do not add edges only to make the list non-empty.

            Edge-variance rules:
            - edge_distance_variances.viewpoint_viewpoint is the step-level initial variance for MLLM-generated ungrounded viewpoint-viewpoint distance estimates.
            - edge_distance_variances.viewpoint_region is the step-level initial variance for MLLM-generated viewpoint-region surrogate distance estimates.
            - These values are provided by the MLLM for the current graph update.
            - Use larger variance when the distance estimate is more uncertain.
            - Use smaller variance only when visual layout evidence gives a clear distance cue.

            Agent-level completeness rules:
            - For every agent, agents[] must contain one item.
            - For every agent, current_region_node_id must be the region containing the agent's current viewpoint.
            - Every current_region_node_id must refer to a region node included in visible_region_nodes.
            - viewpoint_target_probs must contain one item for every distinct current viewpoint and every distinct visible neighboring viewpoint across all agents.
            - viewpoint_node_assigns must contain one item for every distinct current viewpoint and every distinct visible neighboring viewpoint across all agents.
            - detections must contain one item for every agent and every target description.
            """
        ).strip()

        user_message = (
            dedent(
                """
                Shared target set:
                {targets_json}

                Shared graph summary:
                {graph_summary_json}

                Per-agent observation context:
                {agent_context_json}

                Meaning of the current input:
                - The shared target set gives all targets that the agent team needs to find.
                - Each target description is used directly as the target name and id.
                - The shared graph summary is the accumulated graph context from previous steps.
                - Each agent observation gives the image index, current viewpoint, and visible neighboring viewpoints.
                - Visible neighboring viewpoints are feasible next viewpoints observed from the current panorama.
                - Distances attached to visible neighboring viewpoints are known local distances from the current viewpoint.
                - No depth images are passed to the MLLM.

                Grounding rules:
                - A viewpoint node is grounded if it has been visited by an agent.
                - The current viewpoint of each agent is grounded.
                - A semantic region node is grounded if at least one grounded viewpoint is assigned to that region.
                - A local viewpoint-viewpoint connection from a current viewpoint to a visible neighboring viewpoint is already physically supported by the navigation system.
                - MLLM-generated viewpoint-viewpoint edges between unvisited viewpoints remain uncertain hypotheses.
                - MLLM-generated viewpoint-region edges remain uncertain hypotheses and are not literal executable motions.

                Multi-agent interpretation:
                - Each agent has its own current viewpoint and panorama.
                - The output must contain one agents[] item per input agent.
                - Different agents may be in the same semantic region. In that case, reuse the same region id.
                - Different agents may observe overlapping regions or viewpoints. In that case, keep ids consistent.
                - Do not create duplicate region nodes for the same physical region.

                Multi-target interpretation:
                - Each target description represents one object or task target.
                - Each target description is used directly as the target name and id.
                - All target_probs dictionaries must contain every target description as a key.
                - Estimate target-location scores for each target description independently.
                - Direct detections must also be reported independently for each target description and each agent.
                - Do not output target_id anywhere.

                Viewpoint-assignment interpretation:
                - Assign every current viewpoint and every visible neighboring viewpoint to exactly one semantic region.
                - If a viewpoint already exists in the shared graph summary and already has an assignment, keep that assignment unless the viewpoint is now an agent's current viewpoint.
                - If a viewpoint is now an agent's current viewpoint, assign it to that agent's current_region_node_id.
                - If a viewpoint is newly observed, initialize its assignment based on the current panorama and graph context.

                Generation priority:
                1. Identify the current semantic region for each agent.
                2. Identify distinct visible semantic regions across all agent panoramas.
                3. Infer hidden adjacent regions only when strong layout cues exist.
                4. Assign every current viewpoint and every visible neighboring viewpoint to exactly one semantic region.
                5. Estimate target-location scores for every target description at returned region and viewpoint nodes.
                6. Report direct target detections for every agent and every target description.
                7. Generate legal candidate edges supported by observation, assignments, and graph context.
                8. Provide step-level initial distance variances for MLLM-generated edge-distance estimates.

                Output JSON with exactly this top-level schema:
                {schema_json}

                Field descriptions:
                {field_descriptions_json}

                Additional output rules:
                - Use the current viewpoint ids and visible neighboring viewpoint ids exactly as provided in each agent context.
                - Use each target description exactly as provided in the shared target set.
                - Use target descriptions as keys in every target_probs dictionary.
                - Do not output target_id anywhere.
                - current_region_node_id is the region node assigned to the agent's current viewpoint.
                - Every current_region_node_id must be included in visible_region_nodes. If it matches an existing region in the shared graph summary, reuse the existing id and label but still include it in visible_region_nodes.
                - visible_region_nodes are semantic regions directly supported by current panorama observations.
                - invisible_region_nodes are plausible semantic regions not directly visible now but strongly suggested by layout cues.
                - Every target_probs value must be strictly larger than 0 and no larger than 1.
                - Do not output 0.0 for any target_probs value.
                - new_edges may connect viewpoint-region or viewpoint-viewpoint, but never region-region.
                - A viewpoint-viewpoint edge in new_edges must connect two unvisited viewpoint nodes only.
                - Do not generate a viewpoint-viewpoint edge if either endpoint is an agent's current viewpoint or any grounded or visited viewpoint indicated by the shared graph summary.
                - Only generate new_edges supported by the current observations and graph context.
                - Do not generate edges between a current viewpoint and its visible neighboring viewpoints.
                - Do not generate an edge between a viewpoint node and its assigned region node.
                - Return new_edges as an empty list when no legal edge is supported.
                - Each detection item must contain exactly agent_id, target, and found.
                - Each detection target value must exactly match one provided target description.
                - Do not include confidence, target_id, strip_index, or any strip-related field in detections.
                - Keep ids consistent with the shared graph summary whenever a node already exists.
                - Reuse old region ids when the current evidence matches an existing region.
                - Do not copy the example entries in the schema.
                - Include only entries supported by the current observations or the shared graph summary.
                - The current semantic region for each agent must be included or reused consistently.
                """
            )
            .strip()
            .format(
                targets_json=json.dumps(sorted(target_names), indent=2, sort_keys=True),
                graph_summary_json=json.dumps(graph_summary, indent=2, sort_keys=True),
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
            "new_visible_region_nodes",
            "new_invisible_region_nodes",
            "new_arcs",
        }
        missing_top_level_keys = required_top_level_keys.difference(payload)
        if missing_top_level_keys:
            raise KeyError(
                "Missing top-level keys: %s" % sorted(missing_top_level_keys)
            )

        observation_by_agent = {
            str(observation["agent_id"]): observation
            for observation in agent_observations
        }
        expected_agent_ids = set(observation_by_agent)
        returned_agent_ids = {
            str(agent_info["agent_id"]) for agent_info in payload["agents"]
        }
        if returned_agent_ids != expected_agent_ids:
            raise ValueError(
                "Returned agent ids %s do not match expected agent ids %s"
                % (sorted(returned_agent_ids), sorted(expected_agent_ids))
            )

        target_descriptions = {str(target["description"]) for target in targets}
        for agent_info in payload["agents"]:
            agent_id = str(agent_info["agent_id"])
            observation = observation_by_agent[agent_id]
            for key in (
                "current_region_node",
                "viewpoint_target_probs",
                "viewpoint_node_assigns",
            ):
                if key not in agent_info:
                    raise KeyError("Missing key '%s' for agent %s" % (key, agent_id))

            expected_viewpoint_ids = {
                int(item["viewpoint_index"])
                for item in observation["visible_viewpoints"]
            }
            returned_viewpoint_prob_ids = {
                int(item["id"]) for item in agent_info["viewpoint_target_probs"]
            }
            returned_assignment_ids = {
                int(item["id"]) for item in agent_info["viewpoint_node_assigns"]
            }
            if returned_viewpoint_prob_ids != expected_viewpoint_ids:
                raise ValueError(
                    "Agent %s returned viewpoint_target_probs for %s, expected %s"
                    % (
                        agent_id,
                        sorted(returned_viewpoint_prob_ids),
                        sorted(expected_viewpoint_ids),
                    )
                )
            if returned_assignment_ids != expected_viewpoint_ids:
                raise ValueError(
                    "Agent %s returned viewpoint assignments for %s, expected %s"
                    % (
                        agent_id,
                        sorted(returned_assignment_ids),
                        sorted(expected_viewpoint_ids),
                    )
                )

        detection_keys = {"agent_id", "target", "found"}
        returned_detection_pairs = set()
        for detection in payload["detections"]:
            if set(detection) != detection_keys:
                raise KeyError(
                    "Detection item keys %s do not match expected keys %s"
                    % (sorted(detection), sorted(detection_keys))
                )
            agent_id = str(detection["agent_id"])
            if agent_id not in expected_agent_ids:
                raise ValueError("Detection uses unknown agent id %s" % agent_id)
            target_description = str(detection["target"])
            if target_description not in target_descriptions:
                raise ValueError(
                    "Detection target %s is not in expected targets %s"
                    % (target_description, sorted(target_descriptions))
                )
            returned_detection_pairs.add((agent_id, target_description))

        expected_detection_pairs = {
            (agent_id, target_description)
            for agent_id in expected_agent_ids
            for target_description in target_descriptions
        }
        if returned_detection_pairs != expected_detection_pairs:
            raise ValueError(
                "Returned detection pairs %s do not match expected pairs %s"
                % (
                    sorted(returned_detection_pairs),
                    sorted(expected_detection_pairs),
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
            if self.save_debug_images:
                cv2.imwrite(
                    "debug_agent_%s_panorama.png" % observation["agent_id"],
                    observation["annotated_panorama"],
                )

        debugpy.breakpoint()  # Set a breakpoint here to inspect the system and user messages before sending the request

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_content},
        ]

        debugpy.breakpoint()  # Set a breakpoint here to inspect the messages before sending the request
        decoded = self._request_completion(messages)
        raw = self._strip_code_fences(decoded)
        payload = self._extract_json_object(raw)
        if payload is None:
            raise ValueError("Failed to parse joint MLLM JSON output")
        self._validate_payload(payload, agent_observations, targets)
        return payload

    def _build_distance_instruction(self, target_object: str) -> str:
        return (
            'Target object: "%s". '
            "Two aligned images are provided: RGB first, depth second. "
            "The target is definitely present in the RGB image. "
            "Use RGB to localize the target and the depth image to estimate metric distance. "
            "Depth conversion rule: distance_m = pixel_value / 4000.0 using the last depth channel or the single channel image. "
            'Return JSON only with exactly one key: {"distance_m": 2.37}.'
            % target_object
        )

    def estimate_target_distance(
        self,
        rgb_image: np.ndarray,
        depth_image: np.ndarray,
        target_object: str,
    ) -> Dict[str, float]:
        if rgb_image.dtype != np.uint8:
            rgb_image = rgb_image.astype(np.uint8)
        if depth_image.ndim == 3:
            depth_image = depth_image[:, :, -1]
        if depth_image.dtype == np.float32 or depth_image.dtype == np.float64:
            depth_image = np.clip(depth_image * 4000.0, 0, 65535).astype(np.uint16)
        elif depth_image.dtype != np.uint16:
            depth_image = depth_image.astype(np.uint16)

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": self._build_distance_instruction(target_object),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": self._image_to_data_url(rgb_image)},
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": self._image_to_data_url(
                                Image.fromarray(depth_image, mode="I;16")
                            )
                        },
                    },
                ],
            }
        ]
        decoded = self._request_completion(messages)
        raw = self._strip_code_fences(decoded)
        payload = self._extract_json_object(raw)
        if payload is None:
            raise ValueError("Failed to parse distance JSON output")
        if "distance_m" not in payload:
            raise KeyError("distance_m is missing from distance JSON output")
        return {"distance_m": float(payload["distance_m"])}
