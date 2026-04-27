from __future__ import annotations

import base64
from doctest import debug
import io
import json
import os
from textwrap import dedent
from typing import TYPE_CHECKING, Dict, List, Optional
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
    def _image_to_data_url(
        image,
        max_size=(1280, 640),
        quality: int = 75,
    ) -> str:
        if isinstance(image, np.ndarray):
            if image.dtype != np.uint8:
                image = image.astype(np.uint8)
            pil_image = Image.fromarray(image)
        else:
            pil_image = image

        pil_image = pil_image.convert("RGB")

        # Keep aspect ratio while limiting the maximum size.
        pil_image.thumbnail(max_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        pil_image.save(
            buffer,
            format="JPEG",
            quality=quality,
            optimize=True,
        )

        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
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
        """Build the MLLM instruction prompt for multi-agent multi-target graph hypothesis generation."""

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

        target_prob_template = {target_id: 0.01 for target_id in target_ids}

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
                "target_id": target_id,
                "found": False,
            }
            for target_id in target_ids
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
                    "exist_prob": 0.9,
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
                    "edge_type": "VZ",
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
                "already in the shared graph summary. If the region node exist in the shared graph summary, skip it."
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
                "A dictionary from every target_id to the initial target-location "
                "score for this visible semantic region. Although this field is named "
                "target_probs, the values are unnormalized prior scores in (0, 1]. "
                "Include all target_ids as keys. Do not use 0.0. These scores will be "
                "normalized downstream on the semantic-zone layer."
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
                "an object name. It should include an appearance cue, a room or area type, "
                "and a relative location cue."
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
                "A top-level list of target-location scores for viewpoint nodes in the current "
                "step. It must include each distinct current viewpoint and each distinct visible "
                "neighboring viewpoint across all agents. Do not include viewpoints that are agents' current viewpoints."
            ),
            "viewpoint_target_probs[].id": (
                "The integer id of a viewpoint node. It must be either an agent's current "
                "viewpoint or a visible neighboring viewpoint from the per-agent observation "
                "context."
            ),
            "viewpoint_target_probs[].target_probs": (
                "A dictionary from every target_id to the initial target-location "
                "score for this visible semantic region. Although this field is named "
                "target_probs, the values are unnormalized prior scores in (0, 1]. "
                "Include all target_ids as keys. Do not use 0.0. These scores will be "
                "normalized downstream on the semantic-zone layer."
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
                "A top-level list of direct target-detection results. This field reports "
                "direct visual detection only. Do not set found=true based only on semantic "
                "guess or target-location probability."
            ),
            "detections[].agent_id": (
                "The agent id for this detection result. It must exactly match one of the "
                "provided agent ids."
            ),
            "detections[].target": (
                "The target id for this detection result. It must exactly match one of the "
                "provided target_ids in the shared target set."
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

            Use the provided agent ids and target_ids exactly.
            Each target has a target_id and a description.
            Use target_id as the identifier in target_probs and detections.
            Use description only to understand what the target is.
            Node ids and viewpoint ids must be integers.
            Existence probabilities and edge-existence probabilities must be numeric values in (0, 1], not strings.
            Every target_probs value must be a positive numeric value in (0, 1], not a string.
            Distances and variances must be positive numeric values, not strings.
            Use JSON booleans for found.
            Return exactly one valid JSON object.
            The first character of your response must be {.
            The last character of your response must be }.
            Do not output markdown.
            Do not output code fences.
            Do not output comments.
            Do not output explanations outside JSON.
            Do not output restart text such as "Wait", "Let me restart", or "I must follow JSON strictly".
            Do not use trailing commas.
            Do not use non-JSON booleans. Use true and false only.
            Do not use Python values such as True, False, or None.
            Do not use thinking mode.

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
            - Every target_probs dictionary must contain every target_id as a key.
            - Use target_id as the key, not the target description.
            - Although this field is named target_probs, the values are unnormalized initial target-location scores.
            - Every target_probs value must be strictly larger than 0 and no larger than 1.
            - Do not output 0.0 for any target_probs value.
            - Estimate target-location scores separately for each target_id by using its description.
            - Target-location scores are initial hypotheses for downstream Bayesian graph updating.
            - The scores do not need to sum to one in the MLLM output.
            - The downstream graph update will normalize target-location probabilities separately on the viewpoint layer and the semantic-region layer.
            - A target can have low but positive probability in a semantically plausible region even when it is not directly detected.
            - Direct detection and target-location probability are different fields.
            - Set detections[].found=true only when the target is directly visible.

            Detection rules:
            - For every agent, detections must contain one item for every target_id.
            - Each detection item must contain exactly agent_id, target_id, and found.
            - detections[].target_id must be one of the provided target_ids.
            - Do not output target or target_name in detections.
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
            - Prefer non-empty new_edges. Weak but legal hypothesis edges are useful.
            - Use low exist_prob for weak edges instead of omitting them.
            - Return [] only when all possible candidate edges violate the edge rules.

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
            - viewpoint_target_probs must contain one item for every distinct current viewpoint and every distinct visible neighboring viewpoint across all agents. If the viewpoint exist in the shared graph summary, skip it.
            - viewpoint_node_assigns must contain one item for every distinct visible neighboring viewpoint across all agents. If the viewpoint exist in the shared graph summary, skip it.
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
                - Each target has a target_id and a description.
                - Use target_id as the identifier in target_probs and detections.
                - Use description only to understand what the target is.
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
                - Each target has a target_id and a description.
                - Use target_id as the identifier in target_probs and detections.
                - Use the description only to understand the object or task target.
                - All target_probs dictionaries must contain every target_id as a key.
                - Estimate target-location scores for each target_id independently.
                - Direct detections must also be reported independently for each target_id and each agent.
                - Do not output target or target_name in detections.

                Viewpoint-assignment interpretation:
                - Assign every current viewpoint and every visible neighboring viewpoint to exactly one semantic region.
                - If a viewpoint already exists in the shared graph summary and already has an assignment, keep that assignment unless it was previously ungrounded and is now an agent's current viewpoint.
                - If a viewpoint is now an agent's current viewpoint, assign it to that agent's current_region_node_id.
                - If a viewpoint is newly observed, initialize its assignment based on the current panorama and graph context.

                Generation priority:
                1. Identify the current semantic region for each agent.
                2. Identify distinct visible semantic regions across all agent panoramas.
                3. Hypothesize 1 to 2 invisible adjacent regions when the layout may imply unseen space, even if the cue is weak.
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
                - Use each target_id exactly as provided in the shared target set.
                - Use target_ids as keys in every target_probs dictionary.
                - Use target_id, not target or target_name, in detections.
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
                - Each detection item must contain exactly agent_id, target_id, and found.
                - Each detection target_id value must exactly match one provided target_id.
                - Do not include confidence, target, target_name, strip_index, or any strip-related field in detections.
                - Keep ids consistent with the shared graph summary whenever a node already exists.
                - Reuse old region ids when the current evidence matches an existing region.
                - Do not copy the example entries in the schema.
                - Include only entries supported by the current observations or the shared graph summary.
                - The current semantic region for each agent must be included or reused consistently.
                """
            )
            .strip()
            .format(
                targets_json=json.dumps(target_records, indent=2, sort_keys=True),
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
            "visible_region_nodes",
            "invisible_region_nodes",
            "viewpoint_target_probs",
            "viewpoint_node_assigns",
            "new_edges",
            "edge_distance_variances",
        }

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

        visible_region_ids = {
            int(region["id"]) for region in payload["visible_region_nodes"]
        }

        for agent_info in payload["agents"]:
            if set(agent_info) != {"agent_id", "current_region_node_id"}:
                raise KeyError(
                    "Each agents[] item must contain exactly agent_id and current_region_node_id."
                )

            current_region_node_id = int(agent_info["current_region_node_id"])
            if current_region_node_id not in visible_region_ids:
                raise ValueError(
                    "current_region_node_id %s is not included in visible_region_nodes."
                    % current_region_node_id
                )

        expected_viewpoint_ids = set()
        for observation in agent_observations:
            for item in observation["visible_viewpoints"]:
                expected_viewpoint_ids.add(int(item["viewpoint_index"]))

        returned_viewpoint_prob_ids = {
            int(item["id"]) for item in payload["viewpoint_target_probs"]
        }
        if returned_viewpoint_prob_ids != expected_viewpoint_ids:
            raise ValueError(
                "Returned viewpoint_target_probs ids %s do not match expected ids %s"
                % (sorted(returned_viewpoint_prob_ids), sorted(expected_viewpoint_ids))
            )

        returned_assignment_ids = {
            int(item["viewpoint_id"]) for item in payload["viewpoint_node_assigns"]
        }
        if returned_assignment_ids != expected_viewpoint_ids:
            raise ValueError(
                "Returned viewpoint_node_assigns ids %s do not match expected ids %s"
                % (sorted(returned_assignment_ids), sorted(expected_viewpoint_ids))
            )

        def validate_target_probs(
            target_probs: Dict[str, object], context: str
        ) -> None:
            if set(target_probs) != target_descriptions:
                raise ValueError(
                    "%s target_probs keys %s do not match expected targets %s"
                    % (context, sorted(target_probs), sorted(target_descriptions))
                )

            for target_name, value in target_probs.items():
                if not isinstance(value, (int, float)):
                    raise TypeError(
                        "%s target_probs[%s] must be numeric." % (context, target_name)
                    )
                if not (0.0 < float(value) <= 1.0):
                    raise ValueError(
                        "%s target_probs[%s]=%s is outside (0, 1]."
                        % (context, target_name, value)
                    )

        for region_key in ("visible_region_nodes", "invisible_region_nodes"):
            for region in payload[region_key]:
                required_region_keys = {"id", "label", "exist_prob", "target_probs"}
                if set(region) != required_region_keys:
                    raise KeyError(
                        "%s item keys %s do not match expected keys %s"
                        % (region_key, sorted(region), sorted(required_region_keys))
                    )

                exist_prob = region["exist_prob"]
                if not isinstance(exist_prob, (int, float)):
                    raise TypeError("%s exist_prob must be numeric." % region_key)
                if not (0.0 < float(exist_prob) <= 1.0):
                    raise ValueError("%s exist_prob must be in (0, 1]." % region_key)

                validate_target_probs(
                    region["target_probs"],
                    "%s region %s" % (region_key, region["id"]),
                )

        for item in payload["viewpoint_target_probs"]:
            if set(item) != {"id", "target_probs"}:
                raise KeyError(
                    "Each viewpoint_target_probs item must contain exactly id and target_probs."
                )
            validate_target_probs(
                item["target_probs"],
                "viewpoint %s" % item["id"],
            )

        for item in payload["viewpoint_node_assigns"]:
            expected_keys = {"viewpoint_id", "assign_region_node_id"}
            if set(item) != expected_keys:
                raise KeyError(
                    "Each viewpoint_node_assigns item must contain exactly %s."
                    % sorted(expected_keys)
                )

        variances = payload["edge_distance_variances"]
        if set(variances) != {"viewpoint_viewpoint", "viewpoint_region"}:
            raise KeyError(
                "edge_distance_variances must contain exactly viewpoint_viewpoint and viewpoint_region."
            )

        for key, value in variances.items():
            if not isinstance(value, (int, float)):
                raise TypeError("edge_distance_variances.%s must be numeric." % key)
            if float(value) <= 0.0:
                raise ValueError("edge_distance_variances.%s must be positive." % key)

        for edge in payload["new_edges"]:
            required_edge_keys = {"i", "j", "edge_type", "exist_prob", "dist"}
            if set(edge) != required_edge_keys:
                raise KeyError(
                    "new_edges item keys %s do not match expected keys %s"
                    % (sorted(edge), sorted(required_edge_keys))
                )

            if edge["edge_type"] not in {"viewpoint_viewpoint", "viewpoint_region"}:
                raise ValueError("Invalid edge_type: %s" % edge["edge_type"])

            if not isinstance(edge["exist_prob"], (int, float)):
                raise TypeError("new_edges[].exist_prob must be numeric.")
            if not (0.0 < float(edge["exist_prob"]) <= 1.0):
                raise ValueError("new_edges[].exist_prob must be in (0, 1].")

            if not isinstance(edge["dist"], (int, float)):
                raise TypeError("new_edges[].dist must be numeric.")
            if float(edge["dist"]) <= 0.0:
                raise ValueError("new_edges[].dist must be positive.")

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

            if not isinstance(detection["found"], bool):
                raise TypeError("detections[].found must be a JSON boolean.")

            returned_detection_pairs.add((agent_id, target_description))

        expected_detection_pairs = {
            (agent_id, target_description)
            for agent_id in expected_agent_ids
            for target_description in target_descriptions
        }

        if returned_detection_pairs != expected_detection_pairs:
            raise ValueError(
                "Returned detection pairs %s do not match expected pairs %s"
                % (sorted(returned_detection_pairs), sorted(expected_detection_pairs))
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

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_content},
        ]

        debugpy.breakpoint()  # Set a breakpoint here to inspect the messages before sending the request

        # decoded = self._request_completion(messages)
        # raw = self._strip_code_fences(decoded)
        raw = '{\n  "agents": [\n    {\n      "agent_id": "agent0",\n      "current_region_node_id": 100\n    },\n    {\n      "agent_id": "agent1",\n      "current_region_node_id": 101\n    }\n  ],\n  "detections": [\n    {\n      "agent_id": "agent0",\n      "found": false,\n      "target": "glass on the dining table"\n    },\n    {\n      "agent_id": "agent0",\n      "found": false,\n      "target": "green plant on the table"\n    },\n    {\n      "agent_id": "agent1",\n      "found": false,\n      "target": "glass on the dining table"\n    },\n    {\n      "agent_id": "agent1",\n      "found": false,\n      "target": "green plant on the table"\n    }\n  ],\n  "edge_distance_variances": {\n    "viewpoint_region": 4.0,\n    "viewpoint_viewpoint": 1.0\n  },\n  "invisible_region_nodes": [\n    {\n      "exist_prob": 0.5,\n      "id": 102,\n      "label": "dimly lit corridor area beyond the bedroom door",\n      "target_probs": {\n        "glass on the dining table": 0.01,\n        "green plant on the table": 0.01\n      }\n    }\n  ],\n  "new_edges": [\n    {\n      "dist": 3.0,\n      "edge_type": "viewpoint_region",\n      "exist_prob": 0.5,\n      "i": 16,\n      "j": 102\n    },\n    {\n      "dist": 2.0,\n      "edge_type": "viewpoint_viewpoint",\n      "exist_prob": 0.3,\n      "i": 16,\n      "j": 18\n    }\n  ],\n  "viewpoint_node_assigns": [\n    {\n      "assign_region_node_id": 100,\n      "viewpoint_id": 0\n    },\n    {\n      "assign_region_node_id": 100,\n      "viewpoint_id": 21\n    },\n    {\n      "assign_region_node_id": 101,\n      "viewpoint_id": 16\n    },\n    {\n      "assign_region_node_id": 101,\n      "viewpoint_id": 9\n    },\n    {\n      "assign_region_node_id": 101,\n      "viewpoint_id": 18\n    },\n    {\n      "assign_region_node_id": 101,\n      "viewpoint_id": 40\n    },\n    {\n      "assign_region_node_id": 101,\n      "viewpoint_id": 41\n    }\n  ],\n  "viewpoint_target_probs": [\n    {\n      "id": 16,\n      "target_probs": {\n        "glass on the dining table": 0.01,\n        "green plant on the table": 0.01\n      }\n    },\n    {\n      "id": 21,\n      "target_probs": {\n        "glass on the dining table": 0.1,\n        "green plant on the table": 0.1\n      }\n    },\n    {\n      "id": 18,\n      "target_probs": {\n        "glass on the dining table": 0.01,\n        "green plant on the table": 0.01\n      }\n    },\n    {\n      "id": 40,\n      "target_probs": {\n        "glass on the dining table": 0.01,\n        "green plant on the table": 0.01\n      }\n    },\n    {\n      "id": 41,\n      "target_probs": {\n        "glass on the dining table": 0.01,\n        "green plant on the table": 0.01\n      }\n    }\n  ],\n  "visible_region_nodes": [\n    {\n      "exist_prob": 1.0,\n      "id": 100,\n      "label": "modern living room area with curved sofa near dining bar",\n      "target_probs": {\n        "glass on the dining table": 0.2,\n        "green plant on the table": 0.2\n      }\n    },\n    {\n      "exist_prob": 1.0,\n      "id": 101,\n      "label": "minimalist bedroom area with grey tufted walls near hallway",\n      "target_probs": {\n        "glass on the dining table": 0.01,\n        "green plant on the table": 0.01\n      }\n    }\n  ]\n}'

        payload = self._extract_json_object(raw)
        if payload is None:
            raise ValueError("Failed to parse joint MLLM JSON output")
        self._validate_payload(payload, agent_observations, targets)
        debugpy.breakpoint()  # Set a breakpoint here to inspect the MLLM response payload after parsing and validation
        return payload

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
