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
            You are a scene-graph proposal module for cooperative many-to-many vision-language navigation.

            Return JSON only.
            Do not return markdown.
            Do not explain your reasoning.

            Use the provided agent ids and target ids exactly.
            Each input image is a single annotated panorama for one agent.
            Image i always corresponds to the agent whose context says image_index = i.

            Region labels must describe room/area semantics, not object names.
            Region-region edges are forbidden.
            All ids must be integers.
            All probabilities and distances must be numeric.
            Use booleans for found.

            For every agent:
            - current_region_node must be the region containing the agent's current viewpoint.
            - viewpoint_target_probs must contain one item for every visible neighboring viewpoint.
            - viewpoint_node_assigns must contain one item for every visible neighboring viewpoint.
            - detections must contain one item for every target id.

            The only panorama images you receive are the annotated panoramas, exactly one per agent.
            """
        ).strip()

        schema = {
            "agents": [
                {
                    "agent_id": "agent0",
                    "current_region_node": {
                        "id": 100,
                        "label": "bright kitchen area near dining table",
                        "exist_prob": 1.0,
                        "target_probs": {
                            "plant": 0.3,
                            "glass": 0.1,
                        },
                    },
                    "viewpoint_target_probs": [
                        {
                            "id": 13,
                            "target_probs": {
                                "plant": 0.4,
                                "glass": 0.05,
                            },
                        }
                    ],
                    "viewpoint_node_assigns": [
                        {"id": 13, "assign_region_node_id": 100}
                    ],
                    "detections": [
                        {
                            "target_id": "plant",
                            "found": True,
                            "confidence": 0.91,
                            "strip_index": 7,
                        },
                        {
                            "target_id": "glass",
                            "found": False,
                            "confidence": 0.0,
                            "strip_index": -1,
                        },
                    ],
                }
            ],
            "new_visible_region_nodes": [
                {
                    "id": 101,
                    "label": "open dining area beside kitchen bar",
                    "exist_prob": 0.7,
                    "target_probs": {
                        "plant": 0.2,
                        "glass": 0.4,
                    },
                }
            ],
            "new_invisible_region_nodes": [],
            "new_arcs": [{"i": 13, "j": 101, "exist_prob": 0.6, "dist": 2.5}],
            "region_merges": [[101, 88]],
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

            Output JSON with exactly this top-level schema:
            {schema_json}

            Additional rules:
            - Use the visible neighboring viewpoint ids exactly as provided in each agent context.
            - For each target detection, strip_index must be -1 if found is false.
            - If found is true, strip_index must be a valid strip index for that agent.
            - Keep ids consistent with the shared graph summary whenever a node already exists.
            - Reuse old region ids when the current evidence matches an existing region.
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
            "region_merges",
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
