from __future__ import annotations

import base64
import io
import json
import os
from textwrap import dedent
import time
from typing import TYPE_CHECKING, Dict, List, Optional
import debugpy
import numpy as np
from openai import BadRequestError, OpenAI
from PIL import Image

import Helper

ENABLE_SIGLIP_REGION_REPAIR = (
    False  # whether to attempt region assignment repair for SigLIP validation errors
)

# for detection only: conservative, reduce false target detections
DETECTION_TEMPERATURE = 0.1
DETECTION_TOP_P = 0.9
DETECTION_TOP_K = 40
DETECTION_PRESENCE_PENALTY = 0.0
OPEN_VOCAB_SCORE_THRESHOLD = (
    0.3  # the threshold for considering an open-vocab detection valid.
)

# for graph generation: still stable, but allows non-uniform probabilities
GRAPH_TEMPERATURE = 0.4
GRAPH_TOP_P = 0.8
GRAPH_TOP_K = 20
GRAPH_PRESENCE_PENALTY = 0.5

MIN_P = 0.0
REPETITION_PENALTY = 1.0

DETECTION_MAX_NEW_TOKENS = 512
GRAPH_MAX_NEW_TOKENS = 8192

if TYPE_CHECKING:
    from semantic_persistence import HypothesisGraph


class SigLIPRegionValidationError(RuntimeError):
    pass


class MLLMClient:
    def __init__(
        self,
        graph_model_name: str = "",  # read from config
        detection_model_name: str = "",  # read from config
        graph_base_url: str = "",
        detection_base_url: str = "",
        graph_api_key_env: str = "",
        detection_api_key_env: str = "",
        request_timeout: float = 120.0,
        save_debug_images: bool = True,
        read_saved_raw_outputs: bool = False,
        raw_output_dir: str = "mllm_raw_outputs",
        raw_debug_dir: str = "mllm_debug_outputs",
        max_validation_retries: int = 2,
        open_vocab_detector=None,
    ):
        self.graph_model_name = graph_model_name
        self.detection_model_name = detection_model_name
        self.graph_base_url = str(graph_base_url)
        self.detection_base_url = str(detection_base_url)
        self.request_timeout = float(request_timeout)
        self.save_debug_images = bool(save_debug_images)
        self.read_saved_raw_outputs = bool(read_saved_raw_outputs)
        self.raw_output_dir = str(raw_output_dir)
        self.raw_debug_dir = str(raw_debug_dir)
        self.max_validation_retries = max(0, int(max_validation_retries))
        self.semantic_raw_output_index = 1
        self.found_target_trace = []
        self.graph_api_key_env = str(graph_api_key_env)
        self.detection_api_key_env = str(detection_api_key_env)
        self.open_vocab_detector = open_vocab_detector
        self.last_open_vocab_verification_trace = None

        self.graph_client = self._create_openai_client(
            base_url=self.graph_base_url,
            api_key_env=self.graph_api_key_env,
            router_name="graph",
        )
        self.detection_client = self._create_openai_client(
            base_url=self.detection_base_url,
            api_key_env=self.detection_api_key_env,
            router_name="detection",
        )
        self.client = self.graph_client

    def _create_openai_client(
        self,
        base_url: str,
        api_key_env: str,
        router_name: str,
    ):
        api_key = os.environ.get(api_key_env)
        if not api_key:
            if self.read_saved_raw_outputs:
                return None
            raise RuntimeError(
                "Environment variable %s is required for the %s MLLM API."
                % (api_key_env, router_name)
            )

        return OpenAI(
            base_url=base_url,
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

    def _request_completion(
        self, messages, model_name: str, request_type: str = "graph"
    ) -> str:
        if request_type == "detection":
            client = self.detection_client
            api_key_env = self.detection_api_key_env
            router_name = "detection"
        else:
            client = self.graph_client
            api_key_env = self.graph_api_key_env
            router_name = "graph"

        if client is None:
            raise RuntimeError(
                "No %s MLLM API client is available. A saved raw output file was "
                "missing or invalid, so the code tried to request the MLLM, but "
                "environment variable %s is not set." % (router_name, api_key_env)
            )

        if request_type == "detection":
            temperature = DETECTION_TEMPERATURE
            top_p = DETECTION_TOP_P
            top_k = DETECTION_TOP_K
            presence_penalty = DETECTION_PRESENCE_PENALTY
            max_tokens = DETECTION_MAX_NEW_TOKENS
        else:
            temperature = GRAPH_TEMPERATURE
            top_p = GRAPH_TOP_P
            top_k = GRAPH_TOP_K
            presence_penalty = GRAPH_PRESENCE_PENALTY
            max_tokens = GRAPH_MAX_NEW_TOKENS

        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                presence_penalty=presence_penalty,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                extra_body={
                    "top_k": top_k,
                    "min_p": MIN_P,
                    "repetition_penalty": REPETITION_PENALTY,
                },
            )

            print("usage:", completion.usage)
            print("model:", completion.model)
            print("finish_reason:", completion.choices[0].finish_reason)
            print()

        except BadRequestError as exc:
            message = str(exc)

            if "chat_template_kwargs" in message or "enable_thinking" in message:
                raise RuntimeError(
                    "The current provider did not accept thinking-mode parameters. "
                    "For Qwen/Qwen3-VL-30B-A3B-Instruct, remove enable_thinking. "
                    "Use a Thinking-version model only if the provider explicitly supports it."
                ) from exc

            if "model_not_found" in message or "does not exist" in message:
                raise RuntimeError(
                    "The configured model was not found. Resolved model='%s'."
                    % model_name
                ) from exc

            raise

        return self._message_to_text(completion.choices[0].message.content)

    def _semantic_raw_output_path(self, step_index: int) -> str:
        return os.path.join(
            getattr(self, "raw_output_dir", "mllm_raw_outputs"),
            "semantic_step_%04d.json" % int(step_index),
        )

    def _semantic_attempt_error_raw_output_path(
        self, step_index: int, attempt_index: int
    ) -> str:
        return os.path.join(
            getattr(self, "raw_output_dir", "mllm_raw_outputs"),
            "semantic_step_%04d_attempt_%02d_error.txt"
            % (int(step_index), int(attempt_index)),
        )

    def _user_message_raw_output_path(self, step_index: int) -> str:
        return os.path.join(
            getattr(self, "raw_output_dir", "mllm_raw_outputs"),
            "user_message_step_%04d.txt" % int(step_index),
        )

    def _detection_raw_output_path(self, step_index: int) -> str:
        return os.path.join(
            getattr(self, "raw_output_dir", "mllm_raw_outputs"),
            "detection_step_%04d.json" % int(step_index),
        )

    def _open_vocab_verification_raw_output_path(self, step_index: int) -> str:
        return os.path.join(
            getattr(self, "raw_output_dir", "mllm_raw_outputs"),
            "open_vocab_verification_step_%04d.json" % int(step_index),
        )

    def _observation_image_path(self, step_index: int, agent_id: str) -> str:
        return os.path.join(
            getattr(self, "raw_debug_dir", "mllm_debug_outputs"),
            "observation_step_%04d_agent_%s.jpg" % (int(step_index), str(agent_id)),
        )

    @staticmethod
    def _build_validation_retry_user_message(
        user_message: str,
        validation_errors: List[str],
        attempt_index: int,
        max_validation_retries: int,
    ) -> str:
        """Append accumulated validation feedback to the original user message."""
        if not validation_errors:
            error_list = "No validation error details were captured."
        else:
            error_list = "\n".join(
                "%d. %s" % (index + 1, error)
                for index, error in enumerate(validation_errors)
            )

        feedback = dedent("""
            Validation feedback for retry {attempt_index} of {max_validation_retries}:
            The previous JSON output failed validation.

            All validation errors observed so far:
            {error_list}

            Return a corrected complete JSON object only.
            Do not explain the errors.
            Keep the same schema and all original rules.
            Fix all listed validation errors at the same time.

            If an error mentions missing required newly observed visible neighboring viewpoint ids, add exactly those ids to viewpoint_target_probs.
            If an error mentions expected assigned viewpoint ids, use exactly that expected id list for viewpoint_node_assigns.
            Do not include viewpoint ids outside the expected assigned viewpoint id list.
            """).strip()

        return (
            user_message
            + "\n\n"
            + feedback.format(
                attempt_index=int(attempt_index),
                max_validation_retries=int(max_validation_retries),
                error_list=error_list,
            )
        )

    def _build_detection_instruction(
        self,
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
    ) -> tuple[str, str]:
        """Build a short prompt for direct visual target detection only."""
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

        agent_records = [
            {
                "agent_id": str(observation["agent_id"]),
                "image_index": image_index,
                "current_viewpoint_index": int(observation["current_viewpoint_index"]),
            }
            for image_index, observation in enumerate(agent_observations)
        ]

        system_message = dedent("""
            You are doing strict direct visual target detection from indoor panorama images.
            Return exactly one JSON object and nothing else.

            Match the exact target object identity, not a broad object category.
            The target description may contain object type, color, size, shape, material, location, or context. Use all visible parts of the description when deciding whether the target is present.

            Do not report a visually similar or semantically related object as the target.
            Do not report a target only because the room type or nearby objects suggest it may exist there.
            If the visible evidence is not enough to distinguish the target from a similar non-target object, do not report it.

            When uncertain, prefer false negative over false positive.
        """).strip()

        user_message = (
            dedent("""
                Active targets:
                {targets_json}

                Agent-image mapping:
                {agents_json}

                Task:
                Inspect each panorama image carefully. For each agent, find active targets that are directly visible and visually match the exact target descriptions.

                Detection rule:
                - Report a target only when the exact target object itself is visible and recognizable.
                - The visible object must match the target description at the object-type level, not only at a broad semantic level.
                - Use all visible descriptive cues in the target description, including object type, color, size, shape, material, and location when available.
                - Do not report a visually similar, functionally related, or contextually related non-target object.
                - Partly visible targets can be reported only if the visible part contains enough target-specific evidence.
                - If multiple object identities are plausible for the same visible object, do not report it.
                - If the object is absent, too blurry, too small, heavily occluded, or visually ambiguous, do not report it.
                - When uncertain, prefer not reporting the target.

                Output rules:
                - Return exactly one JSON object.
                - If no active target is visible in any image, return exactly:
                  {{"detections":[]}}
                - Include only agents that detect at least one target.
                - Each agent may appear at most once.
                - Only use active target_ids from the list above.
                - Do not include completed, unlisted, or not-found targets.
                - Do not include an agent-target pair if the detected object could reasonably be a different object type than the target description.

                Required format:
                {{
                  "detections": [
                    {{
                      "agent_id": "agent0",
                      "found_target_indices": ["0"],
                      "target_center_xs": [0.52]
                    }}
                  ]
                }}

                target_center_xs:
                - Use the normalized horizontal center of the visible target in the full panorama.
                - The value must be in [0.0, 1.0].
                - The order must match found_target_indices.
                """)
            .strip()
            .format(
                targets_json=json.dumps(target_records, indent=2, sort_keys=True),
                agents_json=json.dumps(agent_records, indent=2, sort_keys=True),
            )
        )

        return system_message, user_message

    def _validate_detection_payload(
        self,
        payload: Dict[str, object],
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
    ) -> List[Dict[str, object]]:
        """Validate and normalize the detection-only MLLM output."""
        if not isinstance(payload, dict):
            raise TypeError("Detection payload must be a dictionary.")

        if set(payload) != {"detections"}:
            raise KeyError(
                "Detection payload must contain exactly ['detections'], got %s."
                % sorted(payload)
            )

        detections = payload["detections"]
        if not isinstance(detections, list):
            raise TypeError("detections must be a list.")

        expected_agent_ids = {
            str(observation["agent_id"]) for observation in agent_observations
        }
        target_ids = {str(target["target_id"]) for target in targets}

        normalized_detections = []
        returned_agent_ids = set()

        for detection in detections:
            if not isinstance(detection, dict):
                raise TypeError("Each detection item must be a dictionary.")

            expected_keys = {
                "agent_id",
                "found_target_indices",
                "target_center_xs",
            }
            if set(detection) != expected_keys:
                raise KeyError(
                    "Each detection item must contain exactly %s, got %s."
                    % (sorted(expected_keys), sorted(detection))
                )

            agent_id = str(detection["agent_id"])
            if agent_id not in expected_agent_ids:
                raise ValueError("Detection uses unknown agent id %s." % agent_id)
            if agent_id in returned_agent_ids:
                raise ValueError("Duplicated detection item for agent %s." % agent_id)
            returned_agent_ids.add(agent_id)

            found_target_indices = detection["found_target_indices"]
            target_center_xs = detection["target_center_xs"]

            if not isinstance(found_target_indices, list):
                raise TypeError("detections[].found_target_indices must be a list.")
            if not isinstance(target_center_xs, list):
                raise TypeError("detections[].target_center_xs must be a list.")

            if len(found_target_indices) != len(target_center_xs):
                raise ValueError(
                    "detections[].found_target_indices and "
                    "detections[].target_center_xs must have the same length for "
                    "agent %s." % agent_id
                )
            if not found_target_indices:
                raise ValueError(
                    "Detection item for agent %s must include at least one found "
                    "target." % agent_id
                )

            returned_target_ids = {str(target_id) for target_id in found_target_indices}
            unknown_target_ids = returned_target_ids.difference(target_ids)
            if unknown_target_ids:
                raise ValueError(
                    "Detection found_target_indices contains inactive target ids %s."
                    % sorted(unknown_target_ids)
                )
            if len(found_target_indices) != len(returned_target_ids):
                raise ValueError(
                    "detections[].found_target_indices contains duplicated target "
                    "ids for agent %s." % agent_id
                )

            normalized_found_target_indices = []
            normalized_target_center_xs = []
            for target_id, target_center_x in zip(
                found_target_indices,
                target_center_xs,
            ):
                if not isinstance(target_center_x, (int, float)) or isinstance(
                    target_center_x, bool
                ):
                    raise TypeError("target_center_xs values must be numbers.")
                if not (0.0 <= float(target_center_x) <= 1.0):
                    raise ValueError("target_center_xs values must be in [0.0, 1.0].")
                normalized_found_target_indices.append(str(target_id))
                normalized_target_center_xs.append(float(target_center_x))

            normalized_detections.append(
                {
                    "agent_id": agent_id,
                    "found_target_indices": normalized_found_target_indices,
                    "target_center_xs": normalized_target_center_xs,
                }
            )

        return sorted(normalized_detections, key=lambda item: item["agent_id"])

    @staticmethod
    def _build_dense_graph_detections(
        detections: List[Dict[str, object]],
        agent_observations: List[Dict[str, object]],
        target_ids: List[str],
    ) -> List[Dict[str, object]]:
        ordered_target_ids = [str(target_id) for target_id in target_ids]
        found_target_ids_by_agent = {
            str(observation["agent_id"]): set() for observation in agent_observations
        }

        for detection in detections:
            agent_id = str(detection["agent_id"])
            found_target_ids_by_agent[agent_id] = {
                str(target_id) for target_id in detection["found_target_indices"]
            }

        dense_detections = []
        for observation in agent_observations:
            agent_id = str(observation["agent_id"])
            found_target_ids = found_target_ids_by_agent[agent_id]
            dense_detections.append(
                {
                    "agent_id": agent_id,
                    "target_indices": list(ordered_target_ids),
                    "founds": [
                        target_id in found_target_ids
                        for target_id in ordered_target_ids
                    ],
                }
            )

        return dense_detections

    @staticmethod
    def _filter_targets_by_found_state(
        targets: List[Dict[str, object]],
        target_found: Dict[str, bool],
    ) -> List[Dict[str, object]]:
        return [
            target
            for target in targets
            if not bool(target_found.get(str(target["target_id"]), False))
        ]

    @staticmethod
    def _found_targets_from_detections(
        detections: List[Dict[str, object]],
        agent_observations: List[Dict[str, object]],
    ) -> Dict[str, List[Dict[str, object]]]:
        found_targets_by_id: Dict[str, List[Dict[str, object]]] = {}
        agent_observation_by_id = {
            str(observation["agent_id"]): observation
            for observation in agent_observations
        }

        for detection in detections:
            agent_id = str(detection["agent_id"])
            found_target_indices = detection["found_target_indices"]
            target_center_xs = detection["target_center_xs"]

            for item_index, target_id in enumerate(found_target_indices):
                target_id = str(target_id)

                target_center_x = target_center_xs[item_index]
                target_center_x = float(target_center_x)
                target_heading = Helper.panorama_center_x_to_heading(
                    target_center_x,
                    agent_observation_by_id[agent_id]["horizon_headings"],
                )

                found_targets_by_id.setdefault(target_id, []).append(
                    {
                        "target_id": target_id,
                        "agent_id": agent_id,
                        "target_center_x": target_center_x,
                        "target_heading": target_heading,
                    }
                )

        return found_targets_by_id

    @staticmethod
    def _filter_detections_to_target_ids(
        detections: List[Dict[str, object]],
        target_ids: List[str],
    ) -> List[Dict[str, object]]:
        target_id_set = {str(target_id) for target_id in target_ids}
        filtered_detections = []

        for detection in detections:
            found_target_indices = []
            target_center_xs = []

            for item_index, target_id in enumerate(detection["found_target_indices"]):
                target_id = str(target_id)
                if target_id not in target_id_set:
                    continue

                found_target_indices.append(target_id)
                target_center_xs.append(detection["target_center_xs"][item_index])

            if found_target_indices:
                filtered_detections.append(
                    {
                        "agent_id": str(detection["agent_id"]),
                        "found_target_indices": found_target_indices,
                        "target_center_xs": target_center_xs,
                    }
                )

        return filtered_detections

    @staticmethod
    def _sanitize_graph_summary_for_target_ids(
        graph_summary: Dict[str, object],
        target_ids: List[str],
    ) -> Dict[str, object]:
        target_id_set = {str(target_id) for target_id in target_ids}
        sanitized = json.loads(json.dumps(graph_summary))

        if isinstance(sanitized.get("targets"), list):
            sanitized["targets"] = [
                target
                for target in sanitized["targets"]
                if isinstance(target, dict)
                and str(target.get("target_id")) in target_id_set
            ]

        if isinstance(sanitized.get("target_found"), dict):
            sanitized["target_found"] = {
                str(target_id): bool(found)
                for target_id, found in sanitized["target_found"].items()
                if str(target_id) in target_id_set
            }

        for node in sanitized.get("nodes", []):
            if not isinstance(node, dict):
                continue

            target_probs = node.get("target_probs")
            if not isinstance(target_probs, dict):
                continue

            node["target_probs"] = {
                str(target_id): value
                for target_id, value in target_probs.items()
                if str(target_id) in target_id_set
            }

        return sanitized

    @staticmethod
    def _build_detection_retry_user_message(
        user_message: str,
        validation_error: str,
        attempt_index: int,
        max_validation_retries: int,
    ) -> str:
        feedback = dedent("""
            Detection output failed validation on retry {attempt_index} of {max_validation_retries}.
            Error: {validation_error}

            Return a corrected complete JSON object only. Keep the same detection schema.
            """).strip()

        return (
            user_message
            + "\n\n"
            + feedback.format(
                attempt_index=int(attempt_index),
                max_validation_retries=int(max_validation_retries),
                validation_error=str(validation_error),
            )
        )

    def _detect_targets(
        self,
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        image_content: List[Dict[str, object]],
        step_index: int,
    ) -> List[Dict[str, object]]:
        """Run a short detection-only MLLM call before graph generation."""
        system_message, user_message = self._build_detection_instruction(
            agent_observations=agent_observations,
            targets=targets,
        )

        max_validation_retries = getattr(self, "max_validation_retries", 0)
        last_error = None

        if getattr(self, "read_saved_raw_outputs", False):
            decoded = self._read_detection_raw_output(step_index)
            if decoded is not None:
                print(f"Reading saved detection raw output for step {step_index}")
                try:
                    raw = self._strip_code_fences(decoded)
                    payload = self._extract_json_object(raw)
                    if payload is None:
                        raise ValueError("Failed to parse detection JSON output")
                    return self._validate_detection_payload(
                        payload=payload,
                        agent_observations=agent_observations,
                        targets=targets,
                    )
                except Exception as exc:
                    print(
                        "Saved detection raw output for step %s is invalid. "
                        "Requesting MLLM instead. Error: %s" % (step_index, str(exc))
                    )
            else:
                print(
                    "Saved detection raw output for step %s was not found. "
                    "Requesting MLLM instead." % step_index
                )

        for attempt_index in range(max_validation_retries + 1):
            if attempt_index == 0:
                attempt_user_message = user_message
            else:
                attempt_user_message = self._build_detection_retry_user_message(
                    user_message=user_message,
                    validation_error=str(last_error),
                    attempt_index=attempt_index,
                    max_validation_retries=max_validation_retries,
                )

            user_content = [{"type": "text", "text": attempt_user_message}]
            user_content.extend(image_content)

            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_content},
            ]

            decoded = self._request_completion(
                messages=messages,
                model_name=getattr(self, "detection_model_name", ""),
                request_type="detection",
            )

            try:
                raw = self._strip_code_fences(decoded)
                payload = self._extract_json_object(raw)
                if payload is None:
                    raise ValueError("Failed to parse detection JSON output")
                detections = self._validate_detection_payload(
                    payload=payload,
                    agent_observations=agent_observations,
                    targets=targets,
                )
                self._write_detection_raw_output(step_index, decoded)
                return detections
            except Exception as exc:
                last_error = exc
                if attempt_index >= max_validation_retries:
                    raise ValueError(
                        "Detection output failed validation after %s attempt(s). "
                        "Last error: %s" % (max_validation_retries + 1, str(last_error))
                    ) from exc
                print(
                    "Detection output validation failed on attempt %s of %s: %s"
                    % (
                        attempt_index + 1,
                        max_validation_retries + 1,
                        str(last_error),
                    )
                )
                debugpy.breakpoint()

        raise RuntimeError("Unexpected detection retry loop exit.")

    def _verify_detections_with_open_vocab(
        self,
        detections: List[Dict[str, object]],
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        step_index: int,
    ) -> List[Dict[str, object]]:
        detector = self.open_vocab_detector
        agent_observation_by_id = {
            str(observation["agent_id"]): observation
            for observation in agent_observations
        }
        target_description_by_id = {
            str(target["target_id"]): str(target["description"]) for target in targets
        }

        verified_detections = []
        trace = {
            "step_index": int(step_index),
            "checks": [],
        }

        for detection in detections:
            agent_id = str(detection["agent_id"])
            claimed_target_ids = [
                str(target_id) for target_id in detection["found_target_indices"]
            ]
            target_center_xs = [
                float(target_center_x)
                for target_center_x in detection["target_center_xs"]
            ]
            text_queries = [
                target_description_by_id[target_id] for target_id in claimed_target_ids
            ]

            open_vocab_results = detector.score_queries(
                image=agent_observation_by_id[agent_id]["annotated_panorama"],
                text_queries=text_queries,
            )

            results_by_query_index = {}
            for result in open_vocab_results:
                if "label_index" in result:
                    query_index = int(result["label_index"])
                else:
                    query_index = text_queries.index(str(result["query"]))
                results_by_query_index[query_index] = result

            verified_target_ids = []
            verified_target_center_xs = []

            for query_index, target_id in enumerate(claimed_target_ids):
                open_vocab_result = results_by_query_index[query_index]
                open_vocab_matches = open_vocab_result["open_vocab_detections"]
                score = float(open_vocab_result["score"])
                score_threshold = float(open_vocab_result["score_threshold"])
                accepted = score >= score_threshold

                trace["checks"].append(
                    {
                        "agent_id": agent_id,
                        "target_id": target_id,
                        "description": target_description_by_id[target_id],
                        "score": score,
                        "score_threshold": score_threshold,
                        "accepted": accepted,
                        "open_vocab_detections": open_vocab_matches,
                    }
                )

                if accepted:
                    verified_target_ids.append(target_id)
                    verified_target_center_xs.append(target_center_xs[query_index])

            if verified_target_ids:
                verified_detections.append(
                    {
                        "agent_id": agent_id,
                        "found_target_indices": verified_target_ids,
                        "target_center_xs": verified_target_center_xs,
                    }
                )

        self.last_open_vocab_verification_trace = trace
        self._write_open_vocab_verification_trace(step_index, trace)

        return verified_detections

    def _build_instruction(
        self,
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        graph_summary: Dict[str, object],
        fixed_detections: List[Dict[str, object]],
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

        graph_viewpoint_to_region_for_prompt = {}
        if isinstance(graph_summary.get("viewpoint_to_region"), dict):
            graph_viewpoint_to_region_for_prompt = {
                int(viewpoint_id): int(region_id)
                for viewpoint_id, region_id in graph_summary[
                    "viewpoint_to_region"
                ].items()
            }

        graph_region_label_by_id_for_prompt = {}
        for node in graph_summary.get("nodes", []):
            if not isinstance(node, dict):
                continue
            if node.get("type") == "region":
                graph_region_label_by_id_for_prompt[int(node["id"])] = str(
                    node.get("label", "")
                ).strip()

        region_start_id = int(len(Helper.viewpoint_vp_label_by_index))

        existing_region_ids = sorted(graph_region_label_by_id_for_prompt)

        invalid_existing_region_ids = [
            region_id
            for region_id in existing_region_ids
            if int(region_id) < region_start_id
        ]
        if invalid_existing_region_ids:
            raise ValueError(
                "Graph summary contains region ids below region_start_id=%s: %s. "
                "This indicates region-viewpoint id collision in saved graph state."
                % (region_start_id, invalid_existing_region_ids)
            )

        next_new_region_id = region_start_id
        if existing_region_ids:
            next_new_region_id = max(region_start_id, max(existing_region_ids) + 1)

        graph_viewpoint_status_by_id_for_prompt = {}
        graph_viewpoint_node_ids_for_prompt = set()
        for node in graph_summary.get("nodes", []):
            if not isinstance(node, dict):
                continue
            if node.get("type") == "viewpoint":
                viewpoint_id = int(node["id"])
                graph_viewpoint_node_ids_for_prompt.add(viewpoint_id)
                graph_viewpoint_status_by_id_for_prompt[viewpoint_id] = {
                    "prior_grounded": bool(node.get("grounded", 0)),
                    "prior_visit_times": int(node.get("node_visit_times", 0)),
                }

        agent_context = []
        for image_index, observation in enumerate(agent_observations):
            visible_viewpoints = []

            for item in observation["visible_viewpoints"]:
                visible_vp_id = int(item["viewpoint_index"])
                visible_region_id = graph_viewpoint_to_region_for_prompt.get(
                    visible_vp_id
                )
                visible_status = graph_viewpoint_status_by_id_for_prompt.get(
                    visible_vp_id, {}
                )

                visible_viewpoints.append(
                    {
                        "viewpoint_index": visible_vp_id,
                        "distance": float(item["distance"]),
                        "xy": item.get("xy"),
                        "prior_assigned_region_id": visible_region_id,
                        "prior_assigned_region_label": (
                            graph_region_label_by_id_for_prompt.get(visible_region_id)
                            if visible_region_id is not None
                            else None
                        ),
                        "prior_grounded": bool(
                            visible_status.get("prior_grounded", False)
                        ),
                        "prior_visit_times": int(
                            visible_status.get("prior_visit_times", 0)
                        ),
                    }
                )

            current_viewpoint_id = int(observation["current_viewpoint_index"])
            prior_assigned_region_id = graph_viewpoint_to_region_for_prompt.get(
                current_viewpoint_id
            )
            current_status = graph_viewpoint_status_by_id_for_prompt.get(
                current_viewpoint_id, {}
            )

            agent_context.append(
                {
                    "agent_id": str(observation["agent_id"]),
                    "image_index": image_index,
                    "current_viewpoint_index": current_viewpoint_id,
                    "current_xy": observation.get("current_xy"),
                    "prior_assigned_region_id": prior_assigned_region_id,
                    "prior_assigned_region_label": (
                        graph_region_label_by_id_for_prompt.get(
                            prior_assigned_region_id
                        )
                        if prior_assigned_region_id is not None
                        else None
                    ),
                    "prior_grounded": bool(current_status.get("prior_grounded", False)),
                    "prior_visit_times": int(
                        current_status.get("prior_visit_times", 0)
                    ),
                    "visible_viewpoints": visible_viewpoints,
                }
            )

        current_viewpoint_ids_for_prompt = {
            int(observation["current_viewpoint_index"])
            for observation in agent_observations
        }

        visible_viewpoint_ids_for_prompt = {
            int(item["viewpoint_index"])
            for observation in agent_observations
            for item in observation.get("visible_viewpoints", [])
        }

        current_step_allowed_viewpoint_ids = sorted(
            current_viewpoint_ids_for_prompt | visible_viewpoint_ids_for_prompt
        )

        new_visible_neighbor_assignment_viewpoint_ids_for_prompt = sorted(
            visible_viewpoint_ids_for_prompt
            - current_viewpoint_ids_for_prompt
            - graph_viewpoint_node_ids_for_prompt
        )

        first_reached_current_viewpoint_ids_for_prompt = sorted(
            viewpoint_id
            for viewpoint_id in current_viewpoint_ids_for_prompt
            if (
                viewpoint_id not in graph_viewpoint_node_ids_for_prompt
                or not bool(
                    graph_viewpoint_status_by_id_for_prompt.get(viewpoint_id, {}).get(
                        "prior_grounded", False
                    )
                )
                or int(
                    graph_viewpoint_status_by_id_for_prompt.get(viewpoint_id, {}).get(
                        "prior_visit_times", 0
                    )
                )
                <= 0
            )
        )

        assignment_required_viewpoint_ids_for_prompt = sorted(
            set(new_visible_neighbor_assignment_viewpoint_ids_for_prompt)
            | set(first_reached_current_viewpoint_ids_for_prompt)
        )

        assignment_not_required_current_step_viewpoint_ids_for_prompt = sorted(
            set(current_step_allowed_viewpoint_ids)
            - set(assignment_required_viewpoint_ids_for_prompt)
        )

        visible_neighbor_viewpoint_ids_for_prompt = (
            visible_viewpoint_ids_for_prompt - current_viewpoint_ids_for_prompt
        )

        required_viewpoint_target_prob_ids_for_prompt = sorted(
            visible_neighbor_viewpoint_ids_for_prompt
            - graph_viewpoint_node_ids_for_prompt
        )
        optional_viewpoint_target_prob_ids_for_prompt = sorted(
            visible_neighbor_viewpoint_ids_for_prompt
            & graph_viewpoint_node_ids_for_prompt
        )

        required_viewpoint_target_probs_skeleton = [
            {"id": viewpoint_id}
            for viewpoint_id in required_viewpoint_target_prob_ids_for_prompt
        ]

        target_prob_template = {
            target_id: min(round(0.2 + 0.15 * index, 2), 0.9)
            for index, target_id in enumerate(target_ids)
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

        example_current_region_id = next_new_region_id
        example_adjacent_region_id = next_new_region_id + 1
        example_invisible_region_id = next_new_region_id + 2
        schema = {
            "agents": [
                {
                    "agent_id": example_agent_id,
                    "current_region_node_id": example_current_region_id,
                    "observed_region_node_ids": [
                        example_current_region_id,
                        example_adjacent_region_id,
                    ],
                }
            ],
            "current_viewpoints_reassignment": [
                {
                    "viewpoint_id": example_current_viewpoint_id,
                    "new_assigned_region_id": example_adjacent_region_id,
                }
            ],
            "visible_region_nodes": [
                {
                    "id": example_current_region_id,
                    "label": "bright kitchen area near dining table",
                    "exist_prob": 1.0,
                    "target_probs": target_prob_template,
                },
                {
                    "id": example_adjacent_region_id,
                    "label": "adjacent hallway visible through doorway",
                    "exist_prob": 0.7,
                    "target_probs": target_prob_template,
                },
            ],
            "invisible_region_nodes": [
                {
                    "id": example_invisible_region_id,
                    "label": "unseen hallway area beyond closed doorway",
                    "exist_prob": 0.6,
                    "target_probs": target_prob_template,
                }
            ],
            "viewpoint_target_probs": [
                {
                    "id": example_visible_viewpoint_id,
                    "target_probs": target_prob_template,
                },
            ],
            "viewpoint_node_assigns": [
                {
                    "region_node_id": example_current_region_id,
                    "assigned_viewpoint_node_indices": [
                        example_current_viewpoint_id,
                        example_visible_viewpoint_id,
                    ],
                }
            ],
            "new_edges": [
                {
                    "i": example_visible_viewpoint_id,
                    "j": example_invisible_region_id,
                    "edge_type": "VZ",
                    "exist_prob": 0.6,
                    "dist": 2.5,
                }
            ],
            "edge_distance_variances": {
                "viewpoint_viewpoint": 1.0,
                "viewpoint_region": 4.0,
            },
        }

        field_descriptions = {
            "agents": "One item per agent.",
            "agents[].agent_id": "Must match an input agent id exactly.",
            "agents[].current_region_node_id": (
                "Region id containing the agent current viewpoint. It must appear in "
                "visible_region_nodes. If this region already exists, reuse its id and "
                "label and still include it."
            ),
            "agents[].observed_region_node_ids": (
                "Nonempty list of visible_region_nodes ids whose regions are visually "
                "observed in this agent's panorama image. Include the current_region_node_id "
                "and any adjacent visible region labels observed in this same panorama. "
                "Do not include graph-summary-only or invisible region ids."
            ),
            "current_viewpoints_reassignment": (
                "Explicit region reassignment events for current viewpoints only. "
                "Return an empty list if every current viewpoint prior region assignment "
                "still matches the current panorama, or if the current viewpoint has no "
                "prior region assignment. Include one item only when a current viewpoint "
                "previously had a graph_summary.viewpoint_to_region assignment and the "
                "current panorama supports a different final region assignment."
            ),
            "current_viewpoints_reassignment[].viewpoint_id": (
                "Integer viewpoint id. It must be one of the current agent viewpoints."
            ),
            "current_viewpoints_reassignment[].new_assigned_region_id": (
                "Final region id assigned to this current viewpoint after checking the "
                "current panorama. It must match the corresponding "
                "agents[].current_region_node_id. If this current viewpoint requires "
                "region assignment in this step and appears in viewpoint_node_assigns, "
                "it must also match there. It must appear in visible_region_nodes. "
                "If this is a newly proposed region id, its full region record must be "
                "included in visible_region_nodes."
            ),
            "visible_region_nodes": (
                "Current regions and any semantic area visually observable in current "
                "panoramas, even if only partially visible through a doorway, opening, "
                "or corridor. Reuse matching existing region ids."
            ),
            "visible_region_nodes[].id": (
                "Integer region id. Region ids must be >= region_start_id. "
                "Use a new id only for a new physical region. If the same physical area "
                "already exists in the graph summary or in the current visible_region_nodes, "
                "reuse the existing region id."
            ),
            "visible_region_nodes[].label": (
                "Room or area label only, not an object name. The label must describe one "
                "spatially coherent area. Do not merge adjacent rooms or areas separated by "
                "a doorway, wall, opening, or clear boundary. Avoid mixed labels such as "
                "'living and bedroom area' or 'kitchen and hallway area'. Include appearance "
                "cue, area type, and physical relative location cue, such as near doorway, "
                "beside window, beyond hallway, adjacent to kitchen, or at the end of the room. "
                "Do not mention agent ids or names."
            ),
            "visible_region_nodes[].exist_prob": (
                "Existence probability in (0, 1]. Use 1.0 only for a region containing "
                "a current viewpoint."
            ),
            "visible_region_nodes[].target_probs": (
                "Unnormalized target-location scores keyed by every active target_id. "
                "Values must be in (0, 1]. Do not use 0.0. Use active target "
                "descriptions to make target-specific scores when evidence differs. "
                "Equal scores are allowed only when evidence is equally weak."
            ),
            "invisible_region_nodes": (
                "Completely unseen semantic regions inferred only from layout cues. "
                "Do not include partially visible areas. Invisible regions must have "
                "no assigned viewpoints."
            ),
            "invisible_region_nodes[].id": (
                "Integer region id. Region ids must be >= region_start_id. "
                "Use a new id only if the region is not represented in the graph summary."
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
                "Unnormalized target-location scores keyed by every active target_id. "
                "Values must be in (0, 1]. Do not use 0.0."
            ),
            "viewpoint_target_probs": (
                "Target-location scores only for non-current visible neighboring "
                "viewpoint ids. Include every newly observed visible neighboring "
                "viewpoint that does not appear as a viewpoint node in the graph "
                "summary. Previously observed visible neighboring viewpoints may "
                "be omitted unless the current observation supports updating them. "
                "Do not include current viewpoint ids."
            ),
            "viewpoint_target_probs[].id": (
                "Integer viewpoint id. It must be a non-current visible neighboring "
                "viewpoint from the observation context. Do not include current viewpoint ids."
            ),
            "viewpoint_target_probs[].target_probs": (
                "Dictionary keyed by every active target_id. Use soft scores in (0, 1]. "
                "Do not use 0.0 here because current viewpoints are not included in this object."
            ),
            "viewpoint_node_assigns": (
                "Incremental region-centered assignments for viewpoint ids requiring "
                "region assignment in this step. This set includes visible neighboring "
                "viewpoints that appear in the current observation but do not already "
                "exist as viewpoint nodes in graph_summary, and current agent viewpoints "
                "that are physically reached for the first time. The assigned viewpoint "
                "ids across all items must be exactly this required assignment id set, "
                "no more and no fewer. If no viewpoint id requires assignment, return an "
                "empty list. Other current-step viewpoints keep their previous "
                "graph_summary viewpoint-to-region assignments unless a current viewpoint "
                "is explicitly listed in current_viewpoints_reassignment."
            ),
            "viewpoint_node_assigns[].region_node_id": (
                "Region id containing the assigned viewpoints. If it is a current_region_node_id, "
                "it must be listed in visible_region_nodes."
            ),
            "viewpoint_node_assigns[].assigned_viewpoint_node_indices": (
                "Integer viewpoint ids requiring region assignment in this step. Do not "
                "include other current-step viewpoint ids."
            ),
            "new_edges": (
                "Uncertain hypothesis edges. Use legal VV or VZ edges only. "
                "For VV edges, include plausible directly traversable local connections "
                "between unvisited non-current viewpoints. The evidence may be uncertain, "
                "but the connection should not cross an apparent obstacle, large furniture, "
                "wall, blocked passage, or other visible barrier. Two viewpoints being in "
                "the same room or same semantic region is not sufficient by itself. Use lower "
                "exist_prob for weaker but still traversable hypotheses. "
                "A VZ edge may connect a viewpoint to any semantic region with no assigned "
                "viewpoints, whether the region is visible or invisible. Do not add a VZ edge "
                "to a region with assigned viewpoints or to the viewpoint's assigned region."
            ),
            "new_edges[].i": (
                "One endpoint id. It may be a viewpoint or region. For VV, it must be an "
                "unvisited viewpoint."
            ),
            "new_edges[].j": (
                "Other endpoint id. Never region-region. For VV, it must be an unvisited "
                "viewpoint. Because edges are undirected, do not output both directions."
            ),
            "new_edges[].edge_type": (
                "Use VV for a plausible hypothesized directly traversable local connection "
                "between two unvisited non-current viewpoint nodes. The connection does not "
                "need to be certain, but it should appear physically passable from the "
                "panorama and graph context. Do not propose a VV edge if a bed, sofa, table, "
                "counter, wall, closed partition, or other visible obstacle appears to block "
                "direct local movement between the viewpoints. Shared room membership alone "
                "is not enough. Use lower exist_prob when the connection is weakly supported. "
                "Use VZ for a viewpoint-region edge."
            ),
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

        prompt_graph_summary = round_json_value(
            self._sanitize_graph_summary_for_target_ids(
                graph_summary=graph_summary,
                target_ids=target_ids,
            )
        )

        # Viewpoint labels are usually long scan ids and do not help the MLLM.
        # Region labels are kept because they carry semantic meaning.
        for node in prompt_graph_summary.get("nodes", []):
            if node.get("type") == "viewpoint":
                node.pop("label", None)

        system_message = dedent("""
            You are an indoor hypothesis-graph proposal module for cooperative many-agent, many-target navigation. Analyze one annotated RGB panorama per agent and the compact shared graph summary. Propose an uncertain graph update for downstream optimization. Do not select robot actions or produce a final map.

            The graph has viewpoint nodes for executable robot poses and region nodes for semantic zones. Use the provided agent ids, active target_ids, and viewpoint ids exactly. Reuse provided region ids exactly when a matching region already exists. For newly proposed regions, assign new integer region ids that do not conflict with existing ids. Use active target_id in target_probs. Use active target descriptions only to understand the remaining targets. Found targets are complete and must not appear in target_probs or existence hypotheses.

            Return exactly one valid JSON object matching the user schema. Do not output markdown, code fences, comments, text outside JSON, extra top-level keys, trailing commas, or non-JSON booleans.

            Required top-level keys:
            agents, current_viewpoints_reassignment, visible_region_nodes, invisible_region_nodes, viewpoint_target_probs, viewpoint_node_assigns, new_edges, edge_distance_variances.

            Core rules:
            - The per-agent observation context is the source of truth for current agent locations, even if the compact graph summary has older node status values.
            - In each panorama, the current viewpoint means the camera location that generated the panorama. It is not drawn as a red numbered marker.
            - Red numbered markers are non-current visible neighboring viewpoints only.
            - Do not infer the current viewpoint's region from a red numbered marker. Red numbered markers should be used only for assigning non-current visible neighboring viewpoints.
            - agents has one item per agent. current_region_node_id is the region containing the agent current viewpoint and must appear in visible_region_nodes. Reuse existing region ids and labels when matched.
            - agents[].observed_region_node_ids is the nonempty set of visible_region_nodes ids observed in that same agent panorama. It must include agents[].current_region_node_id and must not include invisible or graph-summary-only region ids.
            - For each current viewpoint with a prior_assigned_region_id in the per-agent observation context, compare prior_assigned_region_label against the visual evidence around the panorama camera location, not around a red numbered marker. The prior assignment is a semantic hypothesis from earlier steps, not ground truth.
            - If the prior region assignment still matches the current panorama, keep the original region assignment and do not include that viewpoint in current_viewpoints_reassignment.
            - If the prior region assignment does not match the current panorama, assign the current viewpoint to the region that best matches the current observation and include exactly one item in current_viewpoints_reassignment.
            - current_viewpoints_reassignment must contain only true region changes for current viewpoints. Return [] when no current viewpoint requires reassignment.
            - For each current_viewpoints_reassignment item, new_assigned_region_id must equal the final region assignment used in agents[].current_region_node_id. If the reassigned current viewpoint requires region assignment in this step and appears in viewpoint_node_assigns, it must also match there.
            - If new_assigned_region_id is a newly proposed region, include the complete region node record in visible_region_nodes.
            - visible_region_nodes include current regions and any adjacent area that is visually observable in current panoramas, even if only partially visible through a doorway, opening, or corridor.
            - Before creating a new visible_region_node, compare it with existing visible_region_nodes and graph-summary region nodes. If the same physical area is already represented, reuse that existing region id and label. Do not create two region nodes for the same hallway, corridor, bathroom, bedroom, or room only because the wording is slightly different across panoramas.
            - invisible_region_nodes include only completely unseen regions inferred from layout cues. If any part of a region is visible, it is not invisible.
            - Do not assign viewpoints to invisible_region_nodes. A region with assigned viewpoints must be in visible_region_nodes.
            - A region id must appear in only one of visible_region_nodes or invisible_region_nodes.
            - Region labels must be room or area labels, not object names. Include appearance cue, area type, and physical relative location cue. Do not mention agent ids or names. Avoid generic labels unless they include both appearance and relative location cues.
            - Detections are handled by a separate detection step outside this graph MLLM call. Do not output detections.
            - Region target_probs and returned non-current visible-neighbor viewpoint target_probs must contain every active target_id with values in (0, 1]. Do not generate target_probs for current viewpoints.
            - Use active target descriptions to make target-specific scores when evidence differs. Equal scores are allowed only when evidence is equally weak.
            - viewpoint_target_probs must include every newly observed non-current visible neighboring viewpoint that is absent from compact shared graph summary nodes. Previously observed visible neighboring viewpoints may be omitted; include one only when the current observation supports updating its target existence probability. Exclude current agent viewpoints.
            - viewpoint_node_assigns must use region_node_id and assigned_viewpoint_node_indices. It is incremental and must include exactly the viewpoint ids requiring region assignment in this step. This set includes new visible neighboring viewpoints and first-reached current viewpoints. Do not include other current-step viewpoints. Other current-step viewpoints keep their previous graph_summary assignment unless a current viewpoint is explicitly listed in current_viewpoints_reassignment.
            - For non-current visible neighboring viewpoints, use prior_assigned_region_id only as historical context, not as a fixed assignment.
            - Assign each non-current visible neighboring viewpoint by jointly considering its marker location in the panorama, xy-based floor-plan distance from current_xy, visible_viewpoints[].distance, and whether a clear spatial boundary separates it from the current viewpoint.
            - If a non-current visible neighboring viewpoint is close to the current viewpoint and no doorway, wall, corridor boundary, room boundary, or transition area separates them, prefer the current viewpoint's final region.
            - If a non-current visible neighboring viewpoint is farther away, or if its marker is across a clear spatial boundary, assign it to the semantic region that physically contains its marker.
            - Do not assign a non-current visible neighboring viewpoint to an adjacent area only because that area is visible in the panorama. Assign it to that adjacent area only when its red marker lies inside that area, or when distance and spatial context strongly support that assignment.
            - new_edges may contain only VV or VZ edges. Never use region-region edges. Do not add edges between a current viewpoint and its visible neighboring viewpoints, because those local edges are already provided by the navigation system. Do not add an edge between a viewpoint and its assigned region.
            - A VV edge may be proposed only between two viewpoint nodes that satisfy all of the following conditions: both are non-current viewpoints and both are marked as unvisited according to the compact shared graph summary. The MLLM may hypothesize a direct local connection when it is spatially plausible and appears directly traversable from the current panoramas and graph context. The evidence does not need to be certain, but the proposed connection should not cross an apparent obstacle, large furniture, wall, blocked passage, closed partition, or other visible barrier. Two viewpoints being visible from the same current viewpoint, or belonging to the same semantic region, is not sufficient by itself. Use lower exist_prob when the support is weak but the local connection still appears passable. If visit-state information is unavailable for a candidate viewpoint, treat the candidate as not eligible for a new VV edge unless the user message explicitly identifies it as unvisited.
            - A VZ edge connects a viewpoint to a semantic region with no assigned viewpoints. The region may be visible or invisible. Do not add a VZ edge to a region with assigned viewpoints or between a viewpoint and its assigned region.
            - If a viewpoint is listed under a region in viewpoint_node_assigns, do not create a VZ edge between that viewpoint and that region. The assignment already represents the viewpoint-region relation.
            - Do not merge multiple rooms or areas into one region label. A region must describe one spatially coherent area only.
            - If a panorama shows multiple areas separated by a doorway, wall, large opening, or clear boundary, represent them as separate region nodes when they contain current or visible viewpoints.
            - The current_region_node_id for an agent must describe the area physically containing the agent's current viewpoint, not every area visible from that viewpoint.
            - A visible adjacent room seen through a doorway should not be merged with the current room. If needed, create or reuse a separate visible_region_node for that adjacent room.
            - Region labels must not use mixed labels such as "living and bedroom area", "kitchen and hallway area", or "bedroom/living area".
            """).strip()

        user_message = (
            dedent("""
                Active target set:
                {targets_json}

                Compact shared graph summary:
                {graph_summary_json}

                Per-agent observation context:
                {agent_context_json}
                
                Panorama direction note:
                - The annotated panorama image may include vertical guide lines and degree labels such as 0 deg, 120 deg, and 240 deg.
                - These degree labels indicate viewing direction along the horizontal panorama.
                - Areas that appear near the far left and far right edges may be close in viewing direction because the panorama wraps around.
                - Use the degree labels only as directional cues in the panorama image. Use current_xy and visible_viewpoints[].xy for physical floor-plan distance.
                
                Coordinate meaning note:
                - current_xy is the 2D floor-plan coordinate of the current viewpoint, which is the panorama camera location.
                - visible_viewpoints[].xy is the 2D floor-plan coordinate of that visible neighboring viewpoint.
                - All xy coordinates use the same floor-plan coordinate system and are approximately measured in meters.
                - Use the Euclidean distance between current_xy and visible_viewpoints[].xy as the floor-plan distance. A larger value means the two viewpoints are farther apart on the floor plan.
                - The visible_viewpoints[].distance value is an additional local distance from the current viewpoint to that visible neighboring viewpoint in the observation context.
                - Do not put two viewpoints into the same semantic region only because their room labels look similar. If their xy coordinates indicate that they are far apart or located in different physical areas, assign them to different region nodes.
                
                Strict allowed-id rule:
                - viewpoint_node_assigns is incremental.
                - viewpoint_node_assigns must contain exactly the Viewpoint ids requiring region assignment in this step, no more and no fewer.
                - If there are no such viewpoint ids, return "viewpoint_node_assigns": [].
                - Do not include viewpoint ids listed under Current-step viewpoint ids not requiring region assignment in this step.
                - Previously observed viewpoints keep their previous graph_summary viewpoint-to-region assignment by default.
                - If a previously observed current viewpoint should move to a different region, report that change only in current_viewpoints_reassignment.
                - viewpoint_target_probs must contain every required newly observed non-current visible neighboring viewpoint id below.
                - viewpoint_target_probs may also contain optional previously observed non-current visible neighboring viewpoint ids below when the current observation supports updating them.
                - Do not include current viewpoint ids in viewpoint_target_probs.
                - Do not include any other viewpoint id in viewpoint_node_assigns or viewpoint_target_probs, even if that id appears in compact shared graph summary, nodes, edges, region assigned_viewpoint_ids, or viewpoint_to_region.
                - Compact graph summary assignments are historical context. Do not copy full old region assigned_viewpoint_ids into current-step assignments.
                - Region ids must be >= {region_start_id}.
                - New region ids must start from {next_new_region_id}.
                - Existing region ids in the graph summary may be reused.
                - Never use a viewpoint id as a region id.

                Current-step allowed viewpoint ids:
                {current_step_allowed_viewpoint_ids_json}
                
                Viewpoint ids requiring region assignment in this step:
                {assignment_required_viewpoint_ids_json}

                These ids include:
                - visible neighboring viewpoints that appear in the current observation but do not already exist as viewpoint nodes in graph_summary;
                - current agent viewpoints that are physically reached for the first time.

                Current-step viewpoint ids not requiring region assignment in this step:
                {assignment_not_required_current_step_viewpoint_ids_json}
                
                Required newly observed viewpoint_target_probs id skeleton:
                {required_viewpoint_target_probs_skeleton_json}

                Optional previously observed viewpoint_target_probs ids:
                {optional_viewpoint_target_prob_ids_json}

                Viewpoint target probability rule:
                - You must output one viewpoint_target_probs item for every id in this skeleton.
                - You may additionally output viewpoint_target_probs items for optional ids only when the current observation supports updating that viewpoint.
                - These ids are non-current visible neighboring viewpoints only.
                - Use positive but meaningful target-location scores in (0, 1]. Avoid uniform scores unless the visual evidence is truly the same.
                - Do not include current viewpoint ids.
                - Do not delete any skeleton item.
                
                Target probability rule:
                - Do not copy default values from the schema or examples.
                - Assign target_probs based on room type, visible objects, and spatial context.
                - Bathroom-related targets should be higher in bathroom regions/viewpoints than in bedroom, lounge, hallway, or kitchen areas.
                - Use different scores when evidence differs.
                - Use low values such as 0.01 only when the target is very unlikely there.
                
                All non-current visible neighboring viewpoint ids:
                {visible_neighbor_viewpoint_ids_json}

                Current-step interpretation note:
                - The observation context is the source of truth for current agent locations.
                - If a current viewpoint already appears in the graph summary, still treat it as current and grounded for this step.
                - If a current viewpoint has prior_assigned_region_id and prior_assigned_region_label in the observation context, treat them as earlier semantic hypotheses that must be checked against the current panorama.
                - If the selected physical region for the current viewpoint already appears in the graph summary, reuse that region id and label and still include it in visible_region_nodes.
                
                Output schema example. Use keys and value types only. Do not copy example values unless supported:
                {schema_json}

                Field descriptions:
                {field_descriptions_json}

                Current step request:
                - For each agent, treat the current viewpoint as the camera location that generated the panorama. The current viewpoint is not drawn as a red numbered marker.
                - Decide which semantic region encloses the panorama camera location.
                - Red numbered markers are non-current visible neighboring viewpoints only.
                - Do not assign a current viewpoint to a region only because a red neighboring marker appears inside that region.
                - Do not assign a current viewpoint to a region only because that region is visible nearby, through a doorway, or at the side of the panorama.
                - If a current viewpoint has prior_assigned_region_id, compare the prior_assigned_region_label with the local visual evidence around the panorama camera location.
                - If the prior region label does not match the local area around the panorama camera location, reassign the current viewpoint to the best matching existing visible region when possible.
                - If no existing region matches the local area around the panorama camera location, create a new visible_region_node.
                - For each agent, list every visible region id observed in that agent's panorama in agents[].observed_region_node_ids. Include the selected current region id and adjacent visible regions seen through openings, doors, or corridors.
                - If a current viewpoint is reassigned, update agents[].current_region_node_id and current_viewpoints_reassignment consistently. Only include the current viewpoint in viewpoint_node_assigns if it is listed under Viewpoint ids requiring region assignment in this step.
                - After choosing the final region for each current viewpoint, assign each non-current visible neighboring viewpoint by jointly considering its red marker location, its xy-based floor-plan distance from current_xy, its visible_viewpoints[].distance value, and whether a clear spatial boundary separates it from the current viewpoint.
                - Use prior_assigned_region_id and graph_summary.viewpoint_to_region only as historical context for non-current visible neighboring viewpoints, not as fixed assignments.
                - If a non-current visible neighboring viewpoint is close to the current viewpoint and no doorway, wall, corridor boundary, room boundary, or transition area separates them, prefer the current viewpoint's final region.
                - If a non-current visible neighboring viewpoint is farther away, or if its red marker is across a clear spatial boundary, assign it to the semantic region that physically contains that red marker.
                - Do not assign a non-current visible neighboring viewpoint to an adjacent area only because that area is visible in the panorama. Assign it to that adjacent area only when its red marker lies inside that area, or when distance and spatial context strongly support that assignment.
                - Propose invisible_region_nodes only for completely unseen areas inferred from layout cues.
                - Treat partially visible adjacent areas as visible_region_nodes, not invisible_region_nodes.
                - Propose only legal VV and VZ edges using the new_edges rules in Core rules and Field descriptions.
                - Return compact JSON only.
                """)
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
                current_step_allowed_viewpoint_ids_json=json.dumps(
                    current_step_allowed_viewpoint_ids, indent=2
                ),
                assignment_required_viewpoint_ids_json=json.dumps(
                    assignment_required_viewpoint_ids_for_prompt, indent=2
                ),
                assignment_not_required_current_step_viewpoint_ids_json=json.dumps(
                    assignment_not_required_current_step_viewpoint_ids_for_prompt,
                    indent=2,
                ),
                visible_neighbor_viewpoint_ids_json=json.dumps(
                    sorted(visible_neighbor_viewpoint_ids_for_prompt), indent=2
                ),
                required_viewpoint_target_probs_skeleton_json=json.dumps(
                    required_viewpoint_target_probs_skeleton, indent=2, sort_keys=True
                ),
                optional_viewpoint_target_prob_ids_json=json.dumps(
                    optional_viewpoint_target_prob_ids_for_prompt, indent=2
                ),
                region_start_id=region_start_id,
                next_new_region_id=next_new_region_id,
            )
        )

        return system_message, user_message

    def propose_semantic_nodes(
        self,
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        graph: HypothesisGraph,
        scorer,
    ) -> Optional[Dict[str, object]]:
        graph_summary = graph.get_mllm_summary()
        active_detection_targets = self._filter_targets_by_found_state(
            targets=targets,
            target_found=getattr(graph, "target_found", {}),
        )

        if not active_detection_targets:
            return None

        step_index = getattr(self, "semantic_raw_output_index", 1)

        # Resize panorama arrays once. The resized images are used by both the
        # detection-only call and the graph-generation call.
        for observation in agent_observations:
            observation["annotated_panorama"] = self._resize_panorama_array(
                observation["annotated_panorama"],
                max_width=1280,
                quality=85,
            )
            self._write_observation_image(
                step_index=step_index,
                agent_id=str(observation["agent_id"]),
                image_bytes=observation["annotated_panorama"],
            )
            # print agent's current location
            print(
                "Agent %s current viewpoint: %s"
                % (observation["agent_id"], observation["current_viewpoint_index"])
            )

        image_content = []
        for image_index, observation in enumerate(agent_observations):
            image_content.append(
                {
                    "type": "text",
                    "text": (
                        "Image index %s. Agent %s. Current viewpoint %s."
                        % (
                            image_index,
                            observation["agent_id"],
                            observation["current_viewpoint_index"],
                        )
                    ),
                }
            )
            image_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": self._image_to_data_url(
                            observation["annotated_panorama"]
                        )
                    },
                }
            )

        # Run the detection step first to get localized detections for the active targets. These detections are used as fixed evidence in the graph generation step, so we separate them to ensure they are not revised by the graph MLLM call.
        localized_detections = self._detect_targets(
            agent_observations=agent_observations,
            targets=active_detection_targets,
            image_content=image_content,
            step_index=step_index,
        )
        if self.open_vocab_detector is not None:
            localized_detections = self._verify_detections_with_open_vocab(
                detections=localized_detections,
                agent_observations=agent_observations,
                targets=active_detection_targets,
                step_index=step_index,
            )
        self.last_direct_detections = localized_detections
        newly_found_targets_by_id = self._found_targets_from_detections(
            localized_detections,
            agent_observations,
        )

        # Append newly found targets to the found_target_trace. This trace keeps a chronological record of when each target was first detected as found, along with the associated agent and localization information at that step.
        for target_id, detections in newly_found_targets_by_id.items():
            for detection in detections:
                self.found_target_trace.append(
                    {
                        "step_index": step_index,
                        "target_id": target_id,
                        "agent_id": detection["agent_id"],
                        "target_center_x": detection["target_center_x"],
                        "target_heading": detection["target_heading"],
                    }
                )

        # Given detections in localized_detections, graph generation should focus on the remaining unfound targets, so we exclude newly found targets from the graph update step. This also prevents confusion from changing target statuses between the detection and graph steps.
        graph_targets = [
            target
            for target in active_detection_targets
            if str(target["target_id"]) not in set(newly_found_targets_by_id)
        ]

        # Filter the localized detections to include only the target_ids that are still active for graph generation. This ensures that the graph generation step receives a consistent view of the remaining unfound targets, without any confusion from targets that were just found in the detection step.
        graph_detections = self._filter_detections_to_target_ids(
            detections=localized_detections,
            target_ids=[str(target["target_id"]) for target in graph_targets],
        )
        fixed_detections = self._build_dense_graph_detections(
            detections=graph_detections,
            agent_observations=agent_observations,
            target_ids=[str(target["target_id"]) for target in graph_targets],
        )

        if not graph_targets:
            self.semantic_raw_output_index = step_index + 1
            return None

        system_message, user_message = self._build_instruction(
            agent_observations=agent_observations,
            targets=graph_targets,
            graph_summary=graph_summary,
            fixed_detections=fixed_detections,
        )

        max_validation_retries = getattr(self, "max_validation_retries", 0)
        validation_errors: List[str] = []

        # read local raw output if enabled, otherwise request MLLM completion directly
        if getattr(self, "read_saved_raw_outputs", False):
            decoded = self._read_semantic_raw_output(step_index)
            if decoded is not None:
                print(f"Reading saved raw output for step {step_index}")
                try:
                    raw = self._strip_code_fences(decoded)
                    payload = self._extract_json_object(raw)
                    if payload is None:
                        raise ValueError("Failed to parse joint MLLM JSON output")
                    payload = self._validate_payload(
                        payload=payload,
                        agent_observations=agent_observations,
                        targets=graph_targets,
                        graph_summary=graph_summary,
                        fixed_detections=fixed_detections,
                        scorer=scorer,
                        semantic_payload_contract="saved_materialized",
                    )
                    self._write_semantic_raw_output(
                        step_index,
                        json.dumps(payload, indent=2, sort_keys=True),
                    )
                    self.semantic_raw_output_index = step_index + 1
                    self._write_user_message(step_index, user_message)
                    return payload
                except SigLIPRegionValidationError:
                    raise
                except Exception as exc:
                    validation_errors.append(str(exc))
                    print(
                        "Saved semantic raw output for step %s is invalid. "
                        "Requesting MLLM instead. Error: %s" % (step_index, str(exc))
                    )
            else:
                print(
                    "Saved semantic raw output for step %s was not found. "
                    "Requesting MLLM instead." % step_index
                )

        last_error = None
        had_saved_validation_errors = bool(validation_errors)

        for attempt_index in range(max_validation_retries + 1):
            if attempt_index == 0 and not validation_errors:
                attempt_user_message = user_message
            else:
                feedback_attempt_index = attempt_index
                feedback_max_retries = max_validation_retries
                if had_saved_validation_errors:
                    feedback_attempt_index = attempt_index + 1
                    feedback_max_retries = max_validation_retries + 1

                attempt_user_message = self._build_validation_retry_user_message(
                    user_message=user_message,
                    validation_errors=validation_errors,
                    attempt_index=feedback_attempt_index,
                    max_validation_retries=feedback_max_retries,
                )

            user_content = [{"type": "text", "text": attempt_user_message}]
            user_content.extend(image_content)

            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_content},
            ]

            print(
                "Requesting graph MLLM completion for step %s, attempt %s of %s"
                % (step_index, attempt_index + 1, max_validation_retries + 1)
            )
            request_start_time = time.time()
            decoded = self._request_completion(
                messages=messages,
                model_name=getattr(self, "graph_model_name", ""),
                request_type="graph",
            )
            print(
                "MLLM completion request for step %s attempt %s took %.2f seconds"
                % (step_index, attempt_index + 1, time.time() - request_start_time)
            )
            debugpy.breakpoint()  # Debug if the MLLM completion is being requested and received correctly.
            try:
                raw = self._strip_code_fences(decoded)
                payload = self._extract_json_object(raw)
                if payload is None:
                    raise ValueError("Failed to parse joint MLLM JSON output")

                payload = self._validate_payload(
                    payload=payload,
                    agent_observations=agent_observations,
                    targets=graph_targets,
                    graph_summary=graph_summary,
                    fixed_detections=fixed_detections,
                    scorer=scorer,
                    semantic_payload_contract="graph_mllm",
                )

                self._write_semantic_raw_output(
                    step_index,
                    json.dumps(payload, indent=2, sort_keys=True),
                )
                self._write_user_message(step_index, user_message)

                self.semantic_raw_output_index = step_index + 1
                return payload

            except SigLIPRegionValidationError:
                self._write_semantic_attempt_error_raw_output(
                    step_index=step_index,
                    attempt_index=attempt_index,
                    decoded=decoded,
                )
                self.semantic_raw_output_index = step_index + 1
                raise

            except Exception as exc:
                last_error = exc
                validation_errors.append(str(exc))
                self._write_semantic_attempt_error_raw_output(
                    step_index=step_index,
                    attempt_index=attempt_index,
                    decoded=decoded,
                )

                if attempt_index >= max_validation_retries:
                    self.semantic_raw_output_index = step_index + 1
                    raise ValueError(
                        "MLLM output failed validation after %s full graph "
                        "attempt(s). Last error: %s"
                        % (max_validation_retries + 1, str(last_error))
                    ) from exc

                print(
                    "Graph MLLM output validation failed on attempt %s of %s: %s"
                    % (
                        attempt_index + 1,
                        max_validation_retries + 1,
                        str(last_error),
                    )
                )

        raise RuntimeError("Unexpected graph MLLM retry loop exit.")

    @staticmethod
    def _read_text_file_if_exists(path: str) -> Optional[str]:
        if not os.path.exists(path):
            return None

        with open(path, "r", encoding="utf-8") as file_handle:
            return file_handle.read()

    def _read_semantic_raw_output(self, step_index: int) -> Optional[str]:
        return self._read_text_file_if_exists(
            self._semantic_raw_output_path(step_index)
        )

    def _read_detection_raw_output(
        self, step_index: int
    ) -> Optional[str]:  # Debug if the detection raw output is being read.
        return self._read_text_file_if_exists(
            self._detection_raw_output_path(step_index)
        )

    def _write_semantic_raw_output(self, step_index: int, decoded: str) -> None:
        raw_output_dir = getattr(self, "raw_output_dir", "mllm_raw_outputs")
        os.makedirs(raw_output_dir, exist_ok=True)

        with open(
            self._semantic_raw_output_path(step_index),
            "w",
            encoding="utf-8",
        ) as file_handle:
            file_handle.write(decoded)

    def _write_semantic_attempt_error_raw_output(
        self, step_index: int, attempt_index: int, decoded: str
    ) -> None:
        raw_output_dir = getattr(self, "raw_output_dir", "mllm_raw_outputs")
        os.makedirs(raw_output_dir, exist_ok=True)

        with open(
            self._semantic_attempt_error_raw_output_path(step_index, attempt_index),
            "w",
            encoding="utf-8",
        ) as file_handle:
            file_handle.write(decoded)

    def _write_user_message(self, step_index: int, message: str) -> None:
        raw_output_dir = getattr(self, "raw_output_dir", "mllm_raw_outputs")
        os.makedirs(raw_output_dir, exist_ok=True)

        with open(
            self._user_message_raw_output_path(step_index),
            "w",
            encoding="utf-8",
        ) as file_handle:
            file_handle.write(message)

    def _write_detection_raw_output(self, step_index: int, decoded: str) -> None:
        raw_output_dir = getattr(self, "raw_output_dir", "mllm_raw_outputs")
        os.makedirs(raw_output_dir, exist_ok=True)

        with open(
            self._detection_raw_output_path(step_index),
            "w",
            encoding="utf-8",
        ) as file_handle:
            file_handle.write(decoded)

    def _write_open_vocab_verification_trace(
        self,
        step_index: int,
        trace: Dict[str, object],
    ) -> None:
        raw_output_dir = getattr(self, "raw_output_dir", "mllm_raw_outputs")
        os.makedirs(raw_output_dir, exist_ok=True)

        with open(
            self._open_vocab_verification_raw_output_path(step_index),
            "w",
            encoding="utf-8",
        ) as file_handle:
            json.dump(trace, file_handle, indent=2, sort_keys=True)

    def _write_observation_image(
        self,
        step_index: int,
        agent_id: str,
        image_bytes: bytes,
    ) -> None:
        raw_output_dir = getattr(self, "raw_output_dir")
        os.makedirs(raw_output_dir, exist_ok=True)
        raw_debug_dir = getattr(self, "raw_debug_dir")
        os.makedirs(raw_debug_dir, exist_ok=True)

        with open(
            self._observation_image_path(step_index, agent_id),
            "wb",
        ) as file_handle:
            file_handle.write(image_bytes)

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

    def _print_request_size_report(self, messages, model_name: str) -> None:
        payload = {
            "model": model_name,
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

    def _validate_payload(
        self,
        payload: Dict[str, object],
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        graph_summary: Optional[Dict[str, object]] = None,
        fixed_detections: Optional[List[Dict[str, object]]] = None,
        scorer=None,
        semantic_payload_contract: str = "graph_mllm",
    ) -> Dict[str, object]:
        if semantic_payload_contract not in {"graph_mllm", "saved_materialized"}:
            raise ValueError(
                "Unknown semantic payload contract: %s" % semantic_payload_contract
            )

        if semantic_payload_contract == "graph_mllm":
            required_top_level_keys = {
                "agents",
                "current_viewpoints_reassignment",
                "visible_region_nodes",
                "invisible_region_nodes",
                "viewpoint_target_probs",
                "viewpoint_node_assigns",
                "new_edges",
                "edge_distance_variances",
            }
        else:
            required_top_level_keys = {
                "agents",
                "current_viewpoints_reassignment",
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
        ordered_target_ids = [str(target["target_id"]) for target in targets]
        if len(target_ids) != len(targets):
            raise ValueError("Target ids must be unique.")

        agents = require_list(payload["agents"], "agents")
        current_viewpoints_reassignment = require_list(
            payload["current_viewpoints_reassignment"],
            "current_viewpoints_reassignment",
        )
        if semantic_payload_contract == "graph_mllm":
            detections = fixed_detections or []
        else:
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
        agent_observed_region_ids = {}

        for agent_info in agents:
            agent_info = require_dict(agent_info, "agents[] item")

            expected_keys = {
                "agent_id",
                "current_region_node_id",
                "observed_region_node_ids",
            }
            if set(agent_info) != expected_keys:
                raise KeyError(
                    "Each agents[] item must contain exactly %s, got %s."
                    % (sorted(expected_keys), sorted(agent_info))
                )

            agent_id = str(agent_info["agent_id"])
            returned_agent_ids.add(agent_id)
            agent_current_region[agent_id] = int(agent_info["current_region_node_id"])
            observed_region_ids = require_list(
                agent_info["observed_region_node_ids"],
                "agents[].observed_region_node_ids",
            )
            if not observed_region_ids:
                raise ValueError(
                    "Agent %s observed_region_node_ids must be nonempty." % agent_id
                )

            normalized_observed_region_ids = []
            seen_observed_region_ids = set()
            for region_id_raw in observed_region_ids:
                region_id = int(region_id_raw)
                if region_id in seen_observed_region_ids:
                    raise ValueError(
                        "Agent %s observed_region_node_ids contains duplicated "
                        "region id %s." % (agent_id, region_id)
                    )
                seen_observed_region_ids.add(region_id)
                normalized_observed_region_ids.append(region_id)

            agent_info["observed_region_node_ids"] = normalized_observed_region_ids
            agent_observed_region_ids[agent_id] = normalized_observed_region_ids

        if returned_agent_ids != expected_agent_ids:
            raise ValueError(
                "Returned agent ids %s do not match expected agent ids %s."
                % (sorted(returned_agent_ids), sorted(expected_agent_ids))
            )

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

        if fixed_detections is not None:
            fixed_detection_by_agent = {}
            for fixed_detection in fixed_detections:
                fixed_agent_id = str(fixed_detection["agent_id"])
                fixed_target_indices = fixed_detection["target_indices"]
                fixed_founds = fixed_detection["founds"]

                fixed_detection_by_agent[fixed_agent_id] = {
                    str(target_id): bool(found)
                    for target_id, found in zip(fixed_target_indices, fixed_founds)
                }

            if set(fixed_detection_by_agent) != expected_agent_ids:
                raise ValueError(
                    "Fixed detection agent ids %s do not match expected agent ids %s."
                    % (sorted(fixed_detection_by_agent), sorted(expected_agent_ids))
                )

            for agent_id in sorted(expected_agent_ids):
                if detection_by_agent[agent_id] != fixed_detection_by_agent[agent_id]:
                    raise ValueError(
                        "Graph output detections for agent %s do not match fixed "
                        "detections. Got %s, expected %s."
                        % (
                            agent_id,
                            detection_by_agent[agent_id],
                            fixed_detection_by_agent[agent_id],
                        )
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

        graph_viewpoint_to_region = {}
        graph_region_records = {}
        graph_viewpoint_node_ids = set()

        if graph_summary is not None:
            if isinstance(graph_summary.get("viewpoint_to_region"), dict):
                for viewpoint_id_raw, region_id_raw in graph_summary[
                    "viewpoint_to_region"
                ].items():
                    graph_viewpoint_to_region[int(viewpoint_id_raw)] = int(
                        region_id_raw
                    )

            for node in graph_summary.get("nodes", []):
                if not isinstance(node, dict):
                    continue

                node_type = node.get("type")
                node_id = int(node["id"])

                if node_type == "viewpoint":
                    graph_viewpoint_node_ids.add(node_id)

                elif node_type == "region":
                    graph_region_records[node_id] = node

                    for viewpoint_id_raw in (
                        node.get("assigned_viewpoint_ids", []) or []
                    ):
                        graph_viewpoint_to_region.setdefault(
                            int(viewpoint_id_raw), node_id
                        )

        graph_viewpoint_status_by_id = {}

        if isinstance(graph_summary, dict):
            for node in graph_summary.get("nodes", []):
                if not isinstance(node, dict):
                    continue

                if node.get("type") == "viewpoint":
                    viewpoint_id = int(node["id"])
                    graph_viewpoint_node_ids.add(viewpoint_id)
                    graph_viewpoint_status_by_id[viewpoint_id] = {
                        "prior_grounded": bool(node.get("grounded", 0)),
                        "prior_visit_times": int(node.get("node_visit_times", 0)),
                    }

        new_visible_neighbor_assignment_viewpoint_ids = (
            visible_viewpoint_ids - current_viewpoint_ids - graph_viewpoint_node_ids
        )

        first_reached_current_viewpoint_ids = set()
        for viewpoint_id in current_viewpoint_ids:
            status = graph_viewpoint_status_by_id.get(viewpoint_id, {})
            prior_grounded = bool(status.get("prior_grounded", False))
            prior_visit_times = int(status.get("prior_visit_times", 0))

            if (
                viewpoint_id not in graph_viewpoint_node_ids
                or not prior_grounded
                or prior_visit_times <= 0
            ):
                first_reached_current_viewpoint_ids.add(viewpoint_id)

        assignment_required_viewpoint_ids = (
            new_visible_neighbor_assignment_viewpoint_ids
            | first_reached_current_viewpoint_ids
        )

        if semantic_payload_contract == "graph_mllm":
            expected_assignment_viewpoint_ids = assignment_required_viewpoint_ids
        else:
            expected_assignment_viewpoint_ids = all_current_step_viewpoint_ids

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

        def validate_region_label(label: str, context: str) -> None:
            normalized_label = " ".join(label.lower().split())

            if "agent" in normalized_label:
                raise ValueError(
                    "%s label must not mention agent ids or agent names: %s"
                    % (context, label)
                )

        def make_region_record_from_graph(region_id: int) -> Dict[str, object]:
            graph_region = graph_region_records.get(region_id)
            if graph_region is None:
                raise ValueError(
                    "Cannot restore fixed assignment to region %s because this "
                    "region is missing from graph_summary.nodes." % region_id
                )

            label = str(graph_region.get("label", "")).strip()
            if not label:
                raise ValueError(
                    "Cannot restore fixed assignment to region %s because the "
                    "graph summary has no region label." % region_id
                )

            target_probs = graph_region.get("target_probs", {})
            if not isinstance(target_probs, dict):
                target_probs = {}

            restored_target_probs = {}
            for target_id in target_ids:
                value = target_probs.get(target_id, 0.01)
                if not is_number(value) or not (0.0 < float(value) <= 1.0):
                    value = 0.01
                restored_target_probs[target_id] = float(value)

            exist_prob = graph_region.get("exist_prob", 1.0)
            if not is_number(exist_prob) or not (0.0 < float(exist_prob) <= 1.0):
                exist_prob = 1.0

            return {
                "id": int(region_id),
                "label": label,
                "exist_prob": float(exist_prob),
                "target_probs": restored_target_probs,
            }

        visible_region_ids = set()
        invisible_region_ids = set()

        for region_key, region_list, region_id_set in (
            ("visible_region_nodes", visible_region_nodes, visible_region_ids),
            (
                "invisible_region_nodes",
                invisible_region_nodes,
                invisible_region_ids,
            ),
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

        visible_region_label_by_id = {
            int(region["id"]): str(region["label"]).strip()
            for region in visible_region_nodes
        }

        def refresh_visible_region_label_by_id() -> None:
            visible_region_label_by_id.clear()
            visible_region_label_by_id.update(
                {
                    int(region["id"]): str(region["label"]).strip()
                    for region in visible_region_nodes
                }
            )

        def ensure_region_record_is_visible(region_id: int) -> bool:
            """Make a referenced region available as a visible region if possible.

            This is used for local repair when agents[].observed_region_node_ids
            references a region that is not currently listed in visible_region_nodes.
            """
            region_id = int(region_id)

            if region_id in visible_region_ids:
                refresh_visible_region_label_by_id()
                return True

            # If the MLLM placed an observed region in invisible_region_nodes, move it
            # to visible_region_nodes because observed_region_node_ids means the region
            # is visible in the current panorama.
            if region_id in invisible_region_ids:
                for region in list(invisible_region_nodes):
                    if int(region["id"]) != region_id:
                        continue

                    invisible_region_nodes.remove(region)
                    invisible_region_ids.remove(region_id)
                    visible_region_nodes.append(region)
                    visible_region_ids.add(region_id)
                    refresh_visible_region_label_by_id()

                    print(
                        "Moved region %s from invisible_region_nodes to "
                        "visible_region_nodes because it appears in "
                        "observed_region_node_ids." % region_id
                    )
                    return True

            # If the region exists in the prior graph summary, restore its full
            # region record locally instead of asking the MLLM to repair it.
            if region_id in graph_region_records:
                visible_region_nodes.append(make_region_record_from_graph(region_id))
                visible_region_ids.add(region_id)
                refresh_visible_region_label_by_id()

                print(
                    "Restored graph-summary region %s into visible_region_nodes "
                    "because it appears in observed_region_node_ids." % region_id
                )
                return True

            return False

        for agent_info in agents:
            agent_id = str(agent_info["agent_id"])
            current_region_id = int(agent_current_region[agent_id])
            observed_region_ids = list(agent_observed_region_ids[agent_id])

            # Local repair: current_region_node_id must always be included.
            if current_region_id not in observed_region_ids:
                observed_region_ids = [current_region_id] + observed_region_ids
                print(
                    "Added current_region_node_id %s to agent %s "
                    "observed_region_node_ids." % (current_region_id, agent_id)
                )

            cleaned_observed_region_ids = []
            removed_unknown_region_ids = []

            for region_id_raw in observed_region_ids:
                region_id = int(region_id_raw)

                if region_id in visible_region_ids or ensure_region_record_is_visible(
                    region_id
                ):
                    if region_id not in cleaned_observed_region_ids:
                        cleaned_observed_region_ids.append(region_id)
                    continue

                # If the missing region is the current region, this is not safely
                # repairable because the current viewpoint would have no visible
                # region label for SIGLIP validation.
                if region_id == current_region_id:
                    raise ValueError(
                        "Agent %s has current_region_node_id %s, but this region "
                        "is not in visible_region_nodes, invisible_region_nodes, "
                        "or graph_summary.nodes. It cannot be repaired locally."
                        % (agent_id, region_id)
                    )

                # If it is only an extra observed adjacent region, remove it.
                # Without a region record, there is no label to score and no safe
                # semantic content to restore.
                removed_unknown_region_ids.append(region_id)

            if current_region_id not in cleaned_observed_region_ids:
                raise ValueError(
                    "Agent %s current_region_node_id %s is not included in repaired "
                    "observed_region_node_ids %s."
                    % (agent_id, current_region_id, cleaned_observed_region_ids)
                )

            if removed_unknown_region_ids:
                print(
                    "Removed unknown observed region ids %s from agent %s because "
                    "they have no visible, invisible, or graph-summary region record."
                    % (removed_unknown_region_ids, agent_id)
                )

            agent_info["observed_region_node_ids"] = cleaned_observed_region_ids
            agent_observed_region_ids[agent_id] = cleaned_observed_region_ids

        siglip_current_region_by_viewpoint = {}

        if scorer is not None and ENABLE_SIGLIP_REGION_REPAIR:
            siglip_assignment_records = []
            for agent_info in agents:
                agent_id = str(agent_info["agent_id"])
                observation = observation_by_agent[agent_id]
                current_viewpoint_id = int(observation["current_viewpoint_index"])
                if "raw_panorama" not in observation:
                    raise SigLIPRegionValidationError(
                        "Observation for agent %s has no raw_panorama for SIGLIP "
                        "current-viewpoint region validation." % agent_id
                    )
                raw_panorama = observation["raw_panorama"]
                if raw_panorama is None:
                    raise SigLIPRegionValidationError(
                        "Observation for agent %s has no raw_panorama for SIGLIP "
                        "current-viewpoint region validation." % agent_id
                    )

                selected_region_id = None
                selected_score = None
                for region_id in sorted(agent_observed_region_ids[agent_id]):
                    try:
                        score = float(
                            scorer.score_images_text(
                                [raw_panorama],
                                visible_region_label_by_id[region_id],
                            )
                        )
                    except Exception as exc:
                        raise SigLIPRegionValidationError(
                            "SIGLIP scorer failed for current viewpoint %s and "
                            "region %s." % (current_viewpoint_id, region_id)
                        ) from exc
                    if (
                        selected_score is None
                        or score > selected_score
                        or (
                            score == selected_score
                            and region_id < int(selected_region_id)
                        )
                    ):
                        selected_region_id = region_id
                        selected_score = score

                if (
                    current_viewpoint_id in siglip_current_region_by_viewpoint
                    and siglip_current_region_by_viewpoint[current_viewpoint_id]
                    != selected_region_id
                ):
                    raise SigLIPRegionValidationError(
                        "Current viewpoint %s is shared by multiple agents with "
                        "different SIGLIP region selections: %s and %s."
                        % (
                            current_viewpoint_id,
                            siglip_current_region_by_viewpoint[current_viewpoint_id],
                            selected_region_id,
                        )
                    )

                siglip_current_region_by_viewpoint[current_viewpoint_id] = int(
                    selected_region_id
                )
                agent_info["current_region_node_id"] = int(selected_region_id)
                agent_current_region[agent_id] = int(selected_region_id)
                siglip_assignment_records.append(
                    {
                        "agent_id": agent_id,
                        "viewpoint_id": current_viewpoint_id,
                        "region_id": int(selected_region_id),
                        "label": visible_region_label_by_id[selected_region_id],
                        "score": float(selected_score),
                    }
                )

            print("SIGLIP current-viewpoint region selections:")
            for record in siglip_assignment_records:
                print(
                    "  Agent %(agent_id)s viewpoint %(viewpoint_id)s -> region "
                    "%(region_id)s (%(label)s), score %(score)s." % record
                )

        if visible_region_ids & invisible_region_ids:
            raise ValueError(
                "Region ids cannot appear in both visible_region_nodes and "
                "invisible_region_nodes: %s"
                % sorted(visible_region_ids & invisible_region_ids)
            )

        all_region_ids = visible_region_ids | invisible_region_ids

        region_start_id = int(len(Helper.viewpoint_vp_label_by_index))
        all_region_ids_for_namespace_check = set(visible_region_ids) | set(
            invisible_region_ids
        )
        invalid_region_ids = sorted(
            region_id
            for region_id in all_region_ids_for_namespace_check
            if int(region_id) < region_start_id
        )
        if invalid_region_ids:
            raise ValueError(
                "Region ids must be >= region_start_id=%s, but got %s. "
                "These ids overlap with the offline-map viewpoint id range."
                % (region_start_id, invalid_region_ids)
            )

        invalid_graph_region_ids = sorted(
            region_id
            for region_id in graph_region_records
            if int(region_id) < region_start_id
        )
        if invalid_graph_region_ids:
            raise ValueError(
                "Graph summary contains region ids below region_start_id=%s: %s. "
                "This saved graph state is invalid because region ids overlap "
                "with viewpoint ids." % (region_start_id, invalid_graph_region_ids)
            )

        for agent_id, current_region_node_id in agent_current_region.items():
            if current_region_node_id not in visible_region_ids:
                raise ValueError(
                    "Agent %s has current_region_node_id %s, but this id is not "
                    "included in visible_region_nodes."
                    % (agent_id, current_region_node_id)
                )

        expected_mllm_viewpoint_prob_ids = visible_viewpoint_ids - current_viewpoint_ids
        required_mllm_viewpoint_prob_ids = (
            expected_mllm_viewpoint_prob_ids - graph_viewpoint_node_ids
        )
        returned_viewpoint_prob_ids = set()
        normalized_visible_viewpoint_target_probs = []

        for item in viewpoint_target_probs:
            item = require_dict(item, "viewpoint_target_probs[] item")

            expected_keys = {"id", "target_probs"}
            if set(item) != expected_keys:
                raise KeyError(
                    "Each viewpoint_target_probs item must contain exactly %s, got %s."
                    % (sorted(expected_keys), sorted(item))
                )

            viewpoint_id = int(item["id"])

            if viewpoint_id in current_viewpoint_ids:
                raise ValueError(
                    "viewpoint_target_probs id %s is a current viewpoint. "
                    "Current viewpoint target probabilities are fixed from direct "
                    "detections and must not be returned by the graph MLLM."
                    % viewpoint_id
                )

            if viewpoint_id not in expected_mllm_viewpoint_prob_ids:
                raise ValueError(
                    "viewpoint_target_probs id %s is not a non-current visible "
                    "neighboring viewpoint." % viewpoint_id
                )

            if viewpoint_id in returned_viewpoint_prob_ids:
                raise ValueError(
                    "Duplicated viewpoint_target_probs id %s." % viewpoint_id
                )

            returned_viewpoint_prob_ids.add(viewpoint_id)

            validate_target_probs_positive(
                item["target_probs"],
                "visible neighboring viewpoint %s" % viewpoint_id,
            )

            normalized_visible_viewpoint_target_probs.append(
                {
                    "id": viewpoint_id,
                    "target_probs": {
                        target_id: float(item["target_probs"][target_id])
                        for target_id in ordered_target_ids
                    },
                }
            )

        missing_required_viewpoint_prob_ids = (
            required_mllm_viewpoint_prob_ids - returned_viewpoint_prob_ids
        )
        if missing_required_viewpoint_prob_ids:
            raise ValueError(
                "Missing required newly observed visible neighboring "
                "viewpoint_target_probs ids %s. Returned ids were %s."
                % (
                    sorted(missing_required_viewpoint_prob_ids),
                    sorted(returned_viewpoint_prob_ids),
                )
            )

        payload["viewpoint_target_probs"] = normalized_visible_viewpoint_target_probs
        viewpoint_target_probs = payload["viewpoint_target_probs"]

        # Build a one-to-one viewpoint-to-region map. If the MLLM assigns the
        # same viewpoint to multiple regions, correct this locally instead of
        # failing validation and re-querying the MLLM. The correction chooses the
        # candidate region whose current agent viewpoint is closest to the shared
        # visible viewpoint. This handles cases such as viewpoint 32 being visible
        # from both viewpoint 16 and viewpoint 20.
        nearest_current_region_by_viewpoint = {}
        for observation in agent_observations:
            agent_id = str(observation["agent_id"])
            current_viewpoint_id = int(observation["current_viewpoint_index"])
            current_region_id = agent_current_region[agent_id]

            for visible_item in observation.get("visible_viewpoints", []):
                viewpoint_id = int(visible_item["viewpoint_index"])

                try:
                    distance = float(visible_item.get("distance", float("inf")))
                except (TypeError, ValueError):
                    distance = float("inf")

                previous_candidate = nearest_current_region_by_viewpoint.get(
                    viewpoint_id
                )
                candidate = {
                    "distance": distance,
                    "current_viewpoint_id": current_viewpoint_id,
                    "region_id": current_region_id,
                }

                if previous_candidate is None:
                    nearest_current_region_by_viewpoint[viewpoint_id] = candidate
                    continue

                previous_key = (
                    float(previous_candidate["distance"]),
                    int(previous_candidate["current_viewpoint_id"]),
                    int(previous_candidate["region_id"]),
                )
                candidate_key = (
                    distance,
                    current_viewpoint_id,
                    current_region_id,
                )

                if candidate_key < previous_key:
                    nearest_current_region_by_viewpoint[viewpoint_id] = candidate

        def choose_region_for_duplicated_assignment(
            viewpoint_id: int,
            candidate_region_ids: List[int],
        ) -> int:
            unique_candidate_region_ids = []
            for region_id in candidate_region_ids:
                if region_id not in unique_candidate_region_ids:
                    unique_candidate_region_ids.append(region_id)

            if len(unique_candidate_region_ids) == 1:
                return unique_candidate_region_ids[0]

            raise ValueError(
                "Viewpoint %s is assigned to multiple regions %s. "
                "The MLLM output must assign each current-step viewpoint to exactly one region."
                % (viewpoint_id, unique_candidate_region_ids)
            )

        assignment_candidates_by_viewpoint = {}
        assignment_region_order = []

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

            if region_node_id not in assignment_region_order:
                assignment_region_order.append(region_node_id)

            assigned_ids = require_list(
                item["assigned_viewpoint_node_indices"],
                "assigned_viewpoint_node_indices",
            )

            seen_ids_in_this_region = set()
            for viewpoint_id_raw in assigned_ids:
                viewpoint_id = int(viewpoint_id_raw)

                if viewpoint_id not in expected_assignment_viewpoint_ids:
                    raise ValueError(
                        "Assigned viewpoint id %s is not expected in viewpoint_node_assigns. "
                        "For graph_mllm output, viewpoint_node_assigns must include only viewpoint "
                        "ids requiring region assignment in this step." % viewpoint_id
                    )

                if viewpoint_id in seen_ids_in_this_region:
                    continue
                seen_ids_in_this_region.add(viewpoint_id)

                assignment_candidates_by_viewpoint.setdefault(viewpoint_id, []).append(
                    region_node_id
                )

        for viewpoint_id, region_id in sorted(
            siglip_current_region_by_viewpoint.items()
        ):
            assignment_candidates_by_viewpoint[int(viewpoint_id)] = [int(region_id)]
            if int(region_id) not in assignment_region_order:
                assignment_region_order.append(int(region_id))

        returned_assignment_viewpoint_ids = set(assignment_candidates_by_viewpoint)

        def ensure_visible_region_available(region_id: int) -> bool:
            """Ensure a region can receive assigned viewpoints."""
            nonlocal all_region_ids

            repaired = ensure_region_record_is_visible(region_id)
            all_region_ids = visible_region_ids | invisible_region_ids
            return repaired

        def choose_region_for_missing_assignment(viewpoint_id: int) -> int:
            """Choose a local repair region for a missing viewpoint assignment."""
            viewpoint_id = int(viewpoint_id)

            # Current viewpoints must stay in their agent current regions.
            if viewpoint_id in current_viewpoint_ids:
                candidate_region_ids = []
                for observation in agent_observations:
                    if int(observation["current_viewpoint_index"]) != viewpoint_id:
                        continue
                    agent_id = str(observation["agent_id"])
                    candidate_region_ids.append(agent_current_region[agent_id])

                for region_id in candidate_region_ids:
                    if ensure_visible_region_available(region_id):
                        return int(region_id)

            # Otherwise, attach the missing visible viewpoint to the region of the
            # closest current agent viewpoint that observes it. This fixes cases
            # such as missing viewpoint 15 by assigning it to agent1's current
            # region 107 when viewpoint 15 is visible from agent1.
            nearest_candidate = nearest_current_region_by_viewpoint.get(viewpoint_id)
            if nearest_candidate is not None:
                nearest_region_id = int(nearest_candidate["region_id"])
                if ensure_visible_region_available(nearest_region_id):
                    return nearest_region_id

            # Final deterministic fallback: use the smallest visible current
            # agent region. This should rarely be used because every expected id
            # is either current or visible from some current viewpoint.
            fallback_region_ids = sorted(
                {
                    int(region_id)
                    for region_id in agent_current_region.values()
                    if int(region_id) in visible_region_ids
                }
            )
            if fallback_region_ids:
                return fallback_region_ids[0]

            raise ValueError(
                "Cannot locally repair missing assignment for viewpoint %s because "
                "no valid visible region can be selected." % viewpoint_id
            )

        missing_assignment_viewpoint_ids = sorted(
            expected_assignment_viewpoint_ids - returned_assignment_viewpoint_ids
        )
        if missing_assignment_viewpoint_ids:
            repaired_missing_assignments = []
            for viewpoint_id in missing_assignment_viewpoint_ids:
                repaired_region_id = choose_region_for_missing_assignment(viewpoint_id)
                assignment_candidates_by_viewpoint.setdefault(viewpoint_id, []).append(
                    repaired_region_id
                )
                if repaired_region_id not in assignment_region_order:
                    assignment_region_order.append(repaired_region_id)

                nearest_candidate = nearest_current_region_by_viewpoint.get(
                    viewpoint_id
                )
                repaired_missing_assignments.append(
                    {
                        "viewpoint_id": int(viewpoint_id),
                        "assigned_region_id": int(repaired_region_id),
                        "nearest_current_viewpoint_id": (
                            int(nearest_candidate["current_viewpoint_id"])
                            if nearest_candidate is not None
                            else None
                        ),
                        "nearest_distance": (
                            float(nearest_candidate["distance"])
                            if nearest_candidate is not None
                            else None
                        ),
                    }
                )

            print("Corrected missing viewpoint assignments:")
            for repair_record in repaired_missing_assignments:
                if repair_record["nearest_current_viewpoint_id"] is None:
                    print(
                        "  Viewpoint %s assigned to region %s."
                        % (
                            repair_record["viewpoint_id"],
                            repair_record["assigned_region_id"],
                        )
                    )
                else:
                    print(
                        "  Viewpoint %s assigned to region %s. Nearest current "
                        "viewpoint: %s at distance %s."
                        % (
                            repair_record["viewpoint_id"],
                            repair_record["assigned_region_id"],
                            repair_record["nearest_current_viewpoint_id"],
                            repair_record["nearest_distance"],
                        )
                    )

            returned_assignment_viewpoint_ids = set(assignment_candidates_by_viewpoint)

        extra_assignment_viewpoint_ids = sorted(
            returned_assignment_viewpoint_ids - expected_assignment_viewpoint_ids
        )
        if extra_assignment_viewpoint_ids:
            raise ValueError(
                "Returned assigned viewpoint ids %s contain ids outside expected ids %s."
                % (
                    extra_assignment_viewpoint_ids,
                    sorted(expected_assignment_viewpoint_ids),
                )
            )

        if returned_assignment_viewpoint_ids != expected_assignment_viewpoint_ids:
            raise ValueError(
                "Returned assigned viewpoint ids %s do not match expected ids %s."
                % (
                    sorted(returned_assignment_viewpoint_ids),
                    sorted(expected_assignment_viewpoint_ids),
                )
            )

        assigned_viewpoint_to_region = {}
        deduplicated_assignments = []

        for viewpoint_id in sorted(assignment_candidates_by_viewpoint):
            candidate_region_ids = assignment_candidates_by_viewpoint[viewpoint_id]
            chosen_region_id = choose_region_for_duplicated_assignment(
                viewpoint_id=viewpoint_id,
                candidate_region_ids=candidate_region_ids,
            )
            assigned_viewpoint_to_region[viewpoint_id] = chosen_region_id

            removed_region_ids = [
                region_id
                for region_id in candidate_region_ids
                if region_id != chosen_region_id
            ]
            if removed_region_ids:
                nearest_candidate = nearest_current_region_by_viewpoint.get(
                    viewpoint_id
                )
                deduplicated_assignments.append(
                    {
                        "viewpoint_id": viewpoint_id,
                        "kept_region_id": chosen_region_id,
                        "removed_region_ids": sorted(set(removed_region_ids)),
                        "nearest_current_viewpoint_id": (
                            int(nearest_candidate["current_viewpoint_id"])
                            if nearest_candidate is not None
                            else None
                        ),
                        "nearest_distance": (
                            float(nearest_candidate["distance"])
                            if nearest_candidate is not None
                            else None
                        ),
                    }
                )

        reassigned_current_viewpoint_to_region = {}

        for item in current_viewpoints_reassignment:
            item = require_dict(
                item,
                "current_viewpoints_reassignment[] item",
            )

            expected_keys = {"viewpoint_id", "new_assigned_region_id"}
            if set(item) != expected_keys:
                raise KeyError(
                    "Each current_viewpoints_reassignment item must contain exactly "
                    "%s, got %s." % (sorted(expected_keys), sorted(item))
                )

            viewpoint_id = int(item["viewpoint_id"])
            new_region_id = int(item["new_assigned_region_id"])

            if viewpoint_id not in current_viewpoint_ids:
                raise ValueError(
                    "current_viewpoints_reassignment viewpoint_id %s is not a "
                    "current viewpoint." % viewpoint_id
                )

            if new_region_id not in visible_region_ids:
                raise ValueError(
                    "current_viewpoints_reassignment new_assigned_region_id %s must "
                    "appear in visible_region_nodes." % new_region_id
                )

            reassigned_current_viewpoint_to_region[viewpoint_id] = new_region_id

        # check current-viewpoint final assignment
        for observation in agent_observations:
            agent_id = str(observation["agent_id"])
            current_viewpoint_id = int(observation["current_viewpoint_index"])
            agent_region_id = agent_current_region[agent_id]

            if current_viewpoint_id in expected_assignment_viewpoint_ids:
                assigned_region_id = assigned_viewpoint_to_region.get(
                    current_viewpoint_id
                )
            else:
                assigned_region_id = reassigned_current_viewpoint_to_region.get(
                    current_viewpoint_id,
                    graph_viewpoint_to_region.get(current_viewpoint_id),
                )

            if assigned_region_id != agent_region_id:
                raise ValueError(
                    "Agent %s current viewpoint %s has effective assigned region %s, "
                    "but its current_region_node_id is %s. If this current viewpoint "
                    "should move from its prior region to a new region, use "
                    "current_viewpoints_reassignment."
                    % (
                        agent_id,
                        current_viewpoint_id,
                        assigned_region_id,
                        agent_region_id,
                    )
                )

        # The MLLM may omit or misstate current-viewpoint reassignment events.
        # Validate only the event shape, then recompute the canonical event list
        # from the final SIGLIP-normalized current assignments.
        seen_reassignment_viewpoints = set()
        for item in current_viewpoints_reassignment:
            item = require_dict(
                item,
                "current_viewpoints_reassignment[] item",
            )

            expected_keys = {"viewpoint_id", "new_assigned_region_id"}
            if set(item) != expected_keys:
                raise KeyError(
                    "Each current_viewpoints_reassignment item must contain exactly "
                    "%s, got %s." % (sorted(expected_keys), sorted(item))
                )

            viewpoint_id = int(item["viewpoint_id"])
            int(item["new_assigned_region_id"])

            if viewpoint_id not in current_viewpoint_ids:
                raise ValueError(
                    "current_viewpoints_reassignment viewpoint_id %s is not a "
                    "current viewpoint." % viewpoint_id
                )

            if viewpoint_id in seen_reassignment_viewpoints:
                raise ValueError(
                    "Duplicated current_viewpoints_reassignment item for viewpoint %s."
                    % viewpoint_id
                )
            seen_reassignment_viewpoints.add(viewpoint_id)

        expected_reassignment_by_viewpoint = {}
        for current_viewpoint_id in sorted(current_viewpoint_ids):
            old_region_id = graph_viewpoint_to_region.get(current_viewpoint_id)
            if current_viewpoint_id in expected_assignment_viewpoint_ids:
                new_region_id = assigned_viewpoint_to_region.get(current_viewpoint_id)
            else:
                new_region_id = agent_current_region[
                    next(
                        str(observation["agent_id"])
                        for observation in agent_observations
                        if int(observation["current_viewpoint_index"])
                        == current_viewpoint_id
                    )
                ]

            if old_region_id is not None and new_region_id != old_region_id:
                expected_reassignment_by_viewpoint[current_viewpoint_id] = new_region_id

        returned_reassignment_by_viewpoint = expected_reassignment_by_viewpoint

        if returned_reassignment_by_viewpoint:
            print("Current viewpoint region reassignments:")
            for viewpoint_id, new_region_id in sorted(
                returned_reassignment_by_viewpoint.items()
            ):
                old_region_id = graph_viewpoint_to_region.get(viewpoint_id)
                print(
                    "  Viewpoint %s reassigned from old region %s to new region %s."
                    % (viewpoint_id, old_region_id, new_region_id)
                )

        if deduplicated_assignments:
            print("Corrected duplicated viewpoint assignments:")
            for correction in deduplicated_assignments:
                print(
                    "  Viewpoint %(viewpoint_id)s kept in region %(kept_region_id)s "
                    "and removed from regions %(removed_region_ids)s. "
                    "Nearest current viewpoint: %(nearest_current_viewpoint_id)s "
                    "at distance %(nearest_distance)s." % correction
                )

        region_to_assigned_viewpoints = {}
        for viewpoint_id, region_id in assigned_viewpoint_to_region.items():
            region_to_assigned_viewpoints.setdefault(region_id, set()).add(viewpoint_id)

        payload["current_viewpoints_reassignment"] = [
            {
                "viewpoint_id": int(viewpoint_id),
                "new_assigned_region_id": int(region_id),
            }
            for viewpoint_id, region_id in sorted(
                returned_reassignment_by_viewpoint.items()
            )
        ]
        payload["visible_region_nodes"] = visible_region_nodes
        payload["invisible_region_nodes"] = invisible_region_nodes
        payload["viewpoint_node_assigns"] = [
            {
                "region_node_id": int(region_id),
                "assigned_viewpoint_node_indices": sorted(viewpoint_ids),
            }
            for region_id, viewpoint_ids in sorted(
                region_to_assigned_viewpoints.items()
            )
        ]

        region_to_all_assigned_viewpoints = {
            region_id: set(viewpoint_ids)
            for region_id, viewpoint_ids in region_to_assigned_viewpoints.items()
        }

        if graph_summary is not None:
            for node in graph_summary.get("nodes", []):
                if node.get("type") != "region":
                    continue

                region_id = int(node["id"])
                assigned_viewpoint_ids = node.get("assigned_viewpoint_ids", []) or []

                for viewpoint_id_raw in assigned_viewpoint_ids:
                    region_to_all_assigned_viewpoints.setdefault(region_id, set()).add(
                        int(viewpoint_id_raw)
                    )

        for region_id in invisible_region_ids:
            assigned_viewpoints = region_to_all_assigned_viewpoints.get(
                region_id, set()
            )
            if assigned_viewpoints:
                raise ValueError(
                    "Invisible region %s cannot have assigned viewpoints %s. "
                    "A region with assigned viewpoints must be in visible_region_nodes."
                    % (region_id, sorted(assigned_viewpoints))
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

        cleaned_new_edges = []
        removed_new_edges = []

        region_exist_prob_by_id = {}
        for region in visible_region_nodes + invisible_region_nodes:
            if not isinstance(region, dict):
                continue
            try:
                region_id = int(region["id"])
            except (KeyError, TypeError, ValueError):
                continue
            region_exist_prob = region.get("exist_prob")
            if is_number(region_exist_prob) and 0.0 < float(region_exist_prob) <= 1.0:
                region_exist_prob_by_id[region_id] = float(region_exist_prob)

        for edge_index, edge in enumerate(new_edges):
            edge = require_dict(edge, "new_edges[] item")

            expected_keys = {"i", "j", "edge_type", "exist_prob", "dist"}

            # Local correction for a common small schema error: the MLLM creates
            # a valid edge object but forgets exist_prob. Add only the missing
            # value instead of failing validation and triggering any retry.
            if "exist_prob" not in edge and {"i", "j", "edge_type", "dist"}.issubset(
                edge
            ):
                inferred_exist_prob = 0.5
                edge_type_for_default = str(edge.get("edge_type", "")).strip().upper()

                if edge_type_for_default == "VZ":
                    endpoint_ids = []
                    for endpoint_key in ("i", "j"):
                        try:
                            endpoint_ids.append(int(edge[endpoint_key]))
                        except (KeyError, TypeError, ValueError):
                            pass

                    for endpoint_id in endpoint_ids:
                        if endpoint_id in region_exist_prob_by_id:
                            inferred_exist_prob = region_exist_prob_by_id[endpoint_id]
                            break

                edge["exist_prob"] = float(inferred_exist_prob)
                print(
                    "Corrected new_edges[%s] by adding missing exist_prob=%.4f."
                    % (edge_index, inferred_exist_prob)
                )

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

            if edge_type == "VZ":
                i_is_region = int(i) >= region_start_id
                j_is_region = int(j) >= region_start_id

                if i_is_region == j_is_region:
                    raise ValueError(
                        "VZ edge (%s, %s) must connect one viewpoint id "
                        "below region_start_id=%s and one region id greater "
                        "than or equal to region_start_id." % (i, j, region_start_id)
                    )

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

                cleaned_new_edges.append(edge)
                continue

            if edge_type == "VZ":
                valid_vz = (i_is_viewpoint and j_is_region) or (
                    i_is_region and j_is_viewpoint
                )
                if not valid_vz:
                    removed_new_edges.append(
                        {
                            "edge": edge,
                            "reason": (
                                "VZ edge (%s, %s) does not connect exactly one "
                                "current-step viewpoint node and one region node."
                                % (i, j)
                            ),
                        }
                    )
                    continue

                viewpoint_id = i if i_is_viewpoint else j
                region_id = i if i_is_region else j

                assigned_region_id = assigned_viewpoint_to_region.get(viewpoint_id)
                if assigned_region_id == region_id:
                    removed_new_edges.append(
                        {
                            "edge": edge,
                            "reason": (
                                "VZ edge connects viewpoint %s to its assigned "
                                "region %s." % (viewpoint_id, region_id)
                            ),
                        }
                    )
                    continue

                assigned_viewpoints = region_to_all_assigned_viewpoints.get(
                    region_id, set()
                )
                if assigned_viewpoints:
                    removed_new_edges.append(
                        {
                            "edge": edge,
                            "reason": (
                                "VZ edge connects to region %s, which already has "
                                "assigned viewpoints %s."
                                % (region_id, sorted(assigned_viewpoints))
                            ),
                        }
                    )
                    continue

                cleaned_new_edges.append(edge)

        if removed_new_edges:
            print(
                "Removed %s invalid VZ edge(s) during payload validation."
                % len(removed_new_edges)
            )
            for item in removed_new_edges:
                print("  Removed edge %s. Reason: %s" % (item["edge"], item["reason"]))

        payload["new_edges"] = cleaned_new_edges

        if semantic_payload_contract == "graph_mllm":
            payload["detections"] = json.loads(json.dumps(fixed_detections or []))

        return payload
