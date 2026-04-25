from __future__ import annotations

import base64
from doctest import debug
import io
import json
import os
from textwrap import dedent
from typing import Dict, List

import debugpy
import numpy as np
from openai import BadRequestError, OpenAI
from PIL import Image


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
        target_map = {
            str(target["id"]): str(target["description"]) for target in targets
        }
        debugpy.breakpoint()  # Set a breakpoint here to inspect the input data before building the instruction
        agent_context = []
        for image_index, observation in enumerate(agent_observations):
            agent_context.append(
                {
                    "agent_id": str(observation["agent_id"]),
                    "image_index": image_index,
                    "current_viewpoint_index": int(
                        observation["current_viewpoint_index"]
                    ),
                    "visible_viewpoints": [
                        {
                            "viewpoint_index": int(item["viewpoint_index"]),
                            "distance": float(item["distance"]),
                        }
                        for item in observation["visible_viewpoints"]
                    ],
                    "valid_strip_indices": [
                        0,
                        int(len(observation["horizon_depths"])) - 1,
                    ],
                }
            )

        system_message = dedent(
            """
            You are an indoor scene-graph proposal module for cooperative many-agent, many-target navigation.

            Return compact JSON only.
            Do not output markdown or any explanation.

            Use the provided agent ids and target ids exactly.
            Node ids and viewpoint ids must be integers.
            Probabilities and distances must be numeric values, not strings.
            Use JSON booleans for found.

            Each input image is one annotated panorama for one agent.
            Image i corresponds to the agent whose context has image_index = i.
            Text numbers in a panorama indicate visible neighboring viewpoints.
            The same text number can appear multiple times and always refers to the same viewpoint.

            Region labels must be room or area labels only, not object names.
            Each region label must include:
            1. a characteristic or appearance cue,
            2. the room or area type,
            3. a relative location cue.

            Good examples:
            - modern living room area with curved sofa near kitchen bar
            - open dining and kitchen area with stools beside living room
            - minimalist bedroom area with large bed near hallway

            Bad examples:
            - living room area
            - kitchen area
            - bedroom area

            Do not generate too many region nodes.
            A maximum of 5 new region nodes total may be proposed at each step.
            When a region is revisited, reuse the previous region id and label.

            No region-to-region arcs are allowed.
            Do not propose arcs between an agent's current viewpoint and its visible neighboring viewpoints.
            Do not propose an arc between a viewpoint node and its assigned region node.
            Every visible neighboring viewpoint must be assigned to exactly one region node.

            For every agent:
            - current_region_node must be the region containing the agent's current viewpoint.
            - viewpoint_target_probs must contain one item for every visible neighboring viewpoint.
            - viewpoint_node_assigns must contain one item for every visible neighboring viewpoint.
            - detections must contain one item for every target id.

            Every target_probs dictionary must contain every target id.
            If a target is not directly observed in the panorama, set found=false, confidence=0.0, strip_index=-1.
            If a target is found, strip_index must be one of the valid strip indices for that agent.
            If multiple strips contain the target, use the strip where the target is most centered.
            """
        ).strip()

        target_prob_template = {target_id: 0.0 for target_id in sorted(target_map)}
        detection_template = [
            {
                "target_id": target_id,
                "found": False,
                "confidence": 0.0,
                "strip_index": -1,
            }
            for target_id in sorted(target_map)
        ]
        schema = {
            "agents": [
                {
                    "agent_id": "agent0",
                    "current_region_node": {
                        "id": 100,
                        "label": "bright kitchen area near dining table",
                        "exist_prob": 1.0,
                        "target_probs": target_prob_template,
                    },
                    "viewpoint_target_probs": [
                        {
                            "id": 13,
                            "target_probs": target_prob_template,
                        }
                    ],
                    "viewpoint_node_assigns": [
                        {"id": 13, "assign_region_node_id": 100}
                    ],
                    "detections": detection_template,
                }
            ],
            "new_visible_region_nodes": [
                {
                    "id": 101,
                    "label": "open dining area beside kitchen bar",
                    "exist_prob": 0.7,
                    "target_probs": target_prob_template,
                }
            ],
            "new_invisible_region_nodes": [
                {
                    "id": 100,
                    "label": "bright kitchen area near dining table",
                    "exist_prob": 0.6,
                    "target_probs": target_prob_template,
                }
            ],
            "new_arcs": [{"i": 13, "j": 101, "exist_prob": 0.6, "dist": 2.5}],
        }

        user_message = (
            dedent(
                """
            Shared target set:
            {targets_json}

            Shared graph summary:
            {graph_summary_json}

            Per-agent observation context:
            {agent_context_json}

            Grounding rules:
            - a region node is grounded if any viewpoint is assigned to that region
            - a viewpoint node is grounded if it has been visited by an agent
            - an arc is grounded if both endpoint nodes are grounded

            Generation priority:
            1. identify the current region for each agent
            2. identify distinct visible regions
            3. infer hidden adjacent regions only when strong layout cues exist
            4. assign each visible neighboring viewpoint to one region
            5. estimate target probabilities and direct target detections
            6. generate legal arcs supported by observation, assignments, and graph context

            Output JSON with exactly this top-level schema:
            {schema_json}

            Additional rules:
            - Use the visible neighboring viewpoint ids exactly as provided in each agent context.
            - current_region_node is the region node assigned to the agent's current viewpoint.
            - new_visible_region_nodes are new region nodes supported by the current panorama observations.
            - new_invisible_region_nodes are plausible new region nodes not directly visible now but strongly suggested by layout cues.
            - new_arcs may connect viewpoint-region or viewpoint-viewpoint, but never region-region.
            - Only generate arcs supported by the current observations and graph context.
            - Do not generate arcs between a current viewpoint and its visible neighboring viewpoints.
            - Do not generate an arc between a viewpoint node and its assigned region node.
            - For each target detection, strip_index must be -1 if found is false.
            - If found is true, strip_index must be a valid strip index for that agent.
            - Keep ids consistent with the shared graph summary whenever a node already exists.
            - Reuse old region ids when the current evidence matches an existing region.
            - Do not leave new_visible_region_nodes, new_invisible_region_nodes, or new_arcs empty by default if there is reasonable supporting evidence.
            """
            )
            .strip()
            .format(
                targets_json=json.dumps(target_map, indent=2, sort_keys=True),
                graph_summary_json=json.dumps(graph_summary, indent=2, sort_keys=True),
                agent_context_json=json.dumps(agent_context, indent=2, sort_keys=True),
                schema_json=json.dumps(schema, indent=2, sort_keys=True),
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

        target_ids = {str(target["id"]) for target in targets}
        for agent_info in payload["agents"]:
            agent_id = str(agent_info["agent_id"])
            observation = observation_by_agent[agent_id]
            for key in (
                "current_region_node",
                "viewpoint_target_probs",
                "viewpoint_node_assigns",
                "detections",
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

            returned_detection_ids = {
                str(item["target_id"]) for item in agent_info["detections"]
            }
            if returned_detection_ids != target_ids:
                raise ValueError(
                    "Agent %s returned detections for %s, expected %s"
                    % (
                        agent_id,
                        sorted(returned_detection_ids),
                        sorted(target_ids),
                    )
                )
            max_strip_index = int(len(observation["horizon_depths"])) - 1
            for detection in agent_info["detections"]:
                if not bool(detection["found"]):
                    if int(detection["strip_index"]) != -1:
                        raise ValueError(
                            "Agent %s target %s must use strip_index=-1 when found=false"
                            % (agent_id, detection["target_id"])
                        )
                    continue
                strip_index = int(detection["strip_index"])
                if strip_index < 0 or strip_index > max_strip_index:
                    raise ValueError(
                        "Agent %s target %s uses invalid strip_index %s"
                        % (agent_id, detection["target_id"], strip_index)
                    )

    def propose_semantic_nodes(
        self,
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        graph,
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
