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

if TYPE_CHECKING:
    from semantic_persistence import HypothesisGraph


class MLLMClient:
    def __init__(
        self,
        graph_model_name: str = "",  # read from config
        detection_model_name: str = "",  # read from config
        base_url: str = "https://router.huggingface.co/v1",
        api_key_env: str = "HF_TOKEN",
        max_new_tokens: int = -1,  # read from config
        request_timeout: float = 120.0,
        save_debug_images: bool = True,
        read_saved_raw_outputs: bool = False,
        raw_output_dir: str = "mllm_raw_outputs",
        raw_debug_dir: str = "mllm_debug_outputs",
        max_validation_retries: int = 2,
    ):
        self.graph_model_name = graph_model_name
        self.detection_model_name = detection_model_name
        self.base_url = base_url
        self.max_new_tokens = int(max_new_tokens)
        self.request_timeout = float(request_timeout)
        self.save_debug_images = bool(save_debug_images)
        self.read_saved_raw_outputs = bool(read_saved_raw_outputs)
        self.raw_output_dir = str(raw_output_dir)
        self.raw_debug_dir = str(raw_debug_dir)
        self.max_validation_retries = max(0, int(max_validation_retries))
        self.semantic_raw_output_index = 0
        self.found_target_trace = []
        self.api_key_env = str(api_key_env)

        api_key = os.environ.get(api_key_env)
        if not api_key:
            if self.read_saved_raw_outputs:
                self.client = None
                return
            else:
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

    def _request_completion(self, messages, model_name: str) -> str:
        if self.client is None:
            raise RuntimeError(
                "No MLLM API client is available. A saved raw output file was "
                "missing or invalid, so the code tried to request the MLLM, but "
                "environment variable %s is not set." % self.api_key_env
            )

        self._print_request_size_report(messages=messages, model_name=model_name)

        try:
            completion = self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.0,
                top_p=1.0,
                seed=42,
                max_tokens=self.max_new_tokens,
                response_format={"type": "json_object"},
            )

            print("usage:", completion.usage)
            print("model:", completion.model)
            print(
                "system_fingerprint:", getattr(completion, "system_fingerprint", None)
            )
            print("finish_reason:", completion.choices[0].finish_reason)

        except BadRequestError as exc:
            message = str(exc)

            if "chat_template_kwargs" in message or "enable_thinking" in message:
                raise RuntimeError(
                    "The current Hugging Face router provider did not accept "
                    "'%s' thinking-mode parameters. Try a provider that supports "
                    "'%s' chat_template_kwargs, or run '%s' through vLLM with "
                    "--reasoning-parser '%s'."
                    % (
                        model_name,
                        model_name,
                        model_name,
                        model_name,
                    )
                ) from exc

            if "model_not_found" in message or "does not exist" in message:
                raise RuntimeError(
                    "The configured Hugging Face router model was not found. "
                    "Resolved model='%s'." % model_name
                ) from exc

            raise

        return self._message_to_text(completion.choices[0].message.content)

    def _semantic_raw_output_path(self, step_index: int) -> str:
        return os.path.join(
            getattr(self, "raw_output_dir", "mllm_raw_outputs"),
            "semantic_step_%04d.json" % int(step_index),
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

            If an error mentions expected current-step viewpoint ids, use exactly that expected id list for both viewpoint_target_probs and viewpoint_node_assigns. Do not include old viewpoint ids copied from compact shared graph summary.
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
            You are doing only direct visual target detection from indoor panorama images.
            Return exactly one JSON object and nothing else.
            Do not infer a target from room type. Report a target only when the target object itself is visible in the image.
            Only evaluate the active targets listed in the user message. Do not include completed or unlisted target ids.
            """).strip()

        user_message = (
            dedent("""
                Active targets:
                {targets_json}

                Agent-image mapping:
                {agents_json}

                Task:
                For each agent image, inspect the entire panorama and identify which active targets are directly visible anywhere in that image.

                A target can be small, off-center, partly far away, or near a viewpoint marker.
                Only report a target when the target object itself is directly visible with sufficient confidence.
                Do not report targets that are absent, occluded beyond recognition, or too ambiguous.

                Output rules:
                - In "detections", include only agents that find at least one active target.
                - If an agent finds no active targets, do not include that agent in "detections".
                - Each agent may appear at most once in "detections".
                - If an agent finds multiple active targets, list all of them in "found_target_indices".
                - A target may appear for multiple agents if it is visible in multiple panorama images.
                - Only use active target_ids from the list above.
                - Do not return completed, unlisted, or not-found target_ids.
                - If no active targets are found in any panorama image, return:
                {{
                    "detections": []
                }}

                Return JSON only in this exact structure:
                {{
                "detections": [
                    {{
                    "agent_id": "agent0",
                    "found_target_indices": ["0", "3"],
                    "target_center_xs": [0.10, 0.72]
                    }}
                ]
                }}

                target_center_xs:
                - For each found target, return the normalized horizontal center of that visible target object in the full panorama image.
                - The value must be between 0.0 and 1.0, where 0.0 is the left edge and 1.0 is the right edge of the image.
                - The order of "target_center_xs" must exactly match the order of "found_target_indices".
                - "target_center_xs" must have the same number of entries as "found_target_indices".
                - Since only found targets are included, do not return null values.
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

        agent_context = []
        for image_index, observation in enumerate(agent_observations):
            visible_viewpoints = [
                {
                    "viewpoint_index": int(item["viewpoint_index"]),
                    "distance": float(item["distance"]),
                }
                for item in observation["visible_viewpoints"]
            ]
            current_viewpoint_id = int(observation["current_viewpoint_index"])
            prior_assigned_region_id = graph_viewpoint_to_region_for_prompt.get(
                current_viewpoint_id
            )
            agent_context.append(
                {
                    "agent_id": str(observation["agent_id"]),
                    "image_index": image_index,
                    "current_viewpoint_index": current_viewpoint_id,
                    "prior_assigned_region_id": prior_assigned_region_id,
                    "prior_assigned_region_label": (
                        graph_region_label_by_id_for_prompt.get(
                            prior_assigned_region_id
                        )
                        if prior_assigned_region_id is not None
                        else None
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
            "current_viewpoints_reassignment": [
                {
                    "viewpoint_id": example_current_viewpoint_id,
                    "new_assigned_region_id": 101,
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
                    "id": 900,
                    "label": "unseen hallway area beyond closed doorway",
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
                    "j": 900,
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
                "current panorama. It must match the region used for this viewpoint in "
                "viewpoint_node_assigns and the corresponding "
                "agents[].current_region_node_id. It must appear in visible_region_nodes. "
                "If this is a newly proposed region id, its full region record must be "
                "included in visible_region_nodes."
            ),
            "visible_region_nodes": (
                "Current regions and any semantic area visually observable in current "
                "panoramas, even if only partially visible through a doorway, opening, "
                "or corridor. Reuse matching existing region ids."
            ),
            "visible_region_nodes[].id": (
                "Integer region id. Use a new id only for a new physical region."
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
                "Unnormalized target-location scores keyed by every active target_id. "
                "Values must be in (0, 1]. Do not use 0.0."
            ),
            "viewpoint_target_probs": (
                "Target-location scores for exactly the Current-step allowed viewpoint ids. "
                "This set includes every current viewpoint and every distinct visible "
                "neighboring viewpoint from the per-agent observation context. Do not include "
                "any other viewpoint id, even if it appears in compact shared graph summary, "
                "nodes, edges, region assigned_viewpoint_ids, or viewpoint_to_region. Current "
                "viewpoint entries are binary direct-detection evidence. Visible-neighbor "
                "entries are soft prior scores."
            ),
            "viewpoint_target_probs[].id": (
                "Integer viewpoint id. It must be either a current viewpoint or a visible "
                "neighboring viewpoint from the observation context."
            ),
            "viewpoint_target_probs[].target_probs": (
                "Dictionary keyed by every active target_id. For a current viewpoint, "
                "use 1.0 if the active target is directly detected there, otherwise "
                "0.0. This binary rule applies only to current viewpoints. For visible "
                "neighboring viewpoints that are not current, use soft scores in "
                "(0, 1] and do not use 0.0."
            ),
            "viewpoint_node_assigns": (
                "Region-centered viewpoint assignments for the current step. The assigned "
                "viewpoint ids across all items must be exactly the Current-step allowed "
                "viewpoint ids, no more and no fewer. Do not include any other viewpoint id, "
                "even if it appears in compact shared graph summary, nodes, edges, region "
                "assigned_viewpoint_ids, or viewpoint_to_region. Current viewpoints must be "
                "assigned to their agents' current_region_node_id, inferred from the current "
                "panorama. If a current viewpoint already has an old "
                "graph_summary.viewpoint_to_region assignment, treat it only as prior "
                "information, not as a fixed rule. For non-current visible neighboring "
                "viewpoints already listed in graph_summary.viewpoint_to_region, reuse that "
                "fixed region assignment exactly."
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
            "detections": (
                "Copy the fixed direct detections from the separate detection step exactly. "
                "Do not revise founds during graph generation. Found and completed "
                "targets are omitted."
            ),
            "detections[].agent_id": "Must match an input agent id exactly.",
            "detections[].target_indices": (
                "Every active target_id exactly once. Do not include found, completed, "
                "or unlisted target ids. Order must match founds."
            ),
            "detections[].founds": (
                "JSON booleans copied exactly from the fixed direct detections. "
                "Order must match target_indices."
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

            The graph has viewpoint nodes for executable robot poses and region nodes for semantic zones. Use the provided agent ids, active target_ids, and viewpoint ids exactly. Reuse provided region ids exactly when a matching region already exists. For newly proposed regions, assign new integer region ids that do not conflict with existing ids. Use active target_id in target_probs and detections[].target_indices. Use active target descriptions only to understand the remaining targets. Found targets are complete and must not appear in target_probs, detections[].target_indices, or existence hypotheses.

            Return exactly one valid JSON object matching the user schema. Do not output markdown, code fences, comments, text outside JSON, extra top-level keys, trailing commas, or non-JSON booleans.

            Required top-level keys:
            agents, current_viewpoints_reassignment, visible_region_nodes, invisible_region_nodes, viewpoint_target_probs, viewpoint_node_assigns, new_edges, edge_distance_variances, detections.

            Core rules:
            - The per-agent observation context is the source of truth for current agent locations, even if the compact graph summary has older node status values.
            - agents has one item per agent. current_region_node_id is the region containing the agent current viewpoint and must appear in visible_region_nodes. Reuse existing region ids and labels when matched.
            - For each current viewpoint with a prior_assigned_region_id in the per-agent observation context, compare prior_assigned_region_label against the current panorama. The prior assignment is a semantic hypothesis from earlier steps, not ground truth.
            - If the prior region assignment still matches the current panorama, keep the original region assignment and do not include that viewpoint in current_viewpoints_reassignment.
            - If the prior region assignment does not match the current panorama, assign the current viewpoint to the region that best matches the current observation and include exactly one item in current_viewpoints_reassignment.
            - current_viewpoints_reassignment must contain only true region changes for current viewpoints. Return [] when no current viewpoint requires reassignment.
            - For each current_viewpoints_reassignment item, new_assigned_region_id must equal the final region assignment used in agents[].current_region_node_id and viewpoint_node_assigns.
            - If new_assigned_region_id is a newly proposed region, include the complete region node record in visible_region_nodes.
            - visible_region_nodes include current regions and any adjacent area that is visually observable in current panoramas, even if only partially visible through a doorway, opening, or corridor.
            - invisible_region_nodes include only completely unseen regions inferred from layout cues. If any part of a region is visible, it is not invisible.
            - Do not assign viewpoints to invisible_region_nodes. A region with assigned viewpoints must be in visible_region_nodes.
            - A region id must appear in only one of visible_region_nodes or invisible_region_nodes.
            - Use at most 5 current-step region nodes total.
            - Region labels must be room or area labels, not object names. Include appearance cue, area type, and physical relative location cue. Do not mention agent ids or names. Avoid generic labels unless they include both appearance and relative location cues.
            - Detections are fixed by a separate detection step. The fixed direct detections provided here already exclude found and completed targets. Copy them exactly from the fixed direct detections in the user message. 
            - Region target_probs and non-current viewpoint target_probs must contain every active target_id with values in (0, 1]. Current viewpoint target_probs are binary direct-detection evidence: 1.0 if fixed detections mark the active target as found for that agent, otherwise 0.0.
            - Use active target descriptions to make target-specific scores when evidence differs. Equal scores are allowed only when evidence is equally weak or when current-viewpoint binary evidence gives the same value.
            - viewpoint_target_probs must include every current agent viewpoint and every distinct visible neighboring viewpoint.
            - viewpoint_node_assigns must use region_node_id and assigned_viewpoint_node_indices. Every current viewpoint and every distinct visible neighboring viewpoint must appear exactly once. Current viewpoints must be assigned to their agents' current_region_node_id based on the current panorama. If a current viewpoint has an old graph_summary.viewpoint_to_region assignment, use it only as prior information, not as a fixed assignment. Reuse the old region only if it still matches the current panorama; otherwise reuse another matching existing region or create a new visible_region_node. For non-current visible neighboring viewpoints already listed in graph_summary.viewpoint_to_region, reuse the fixed region assignment exactly.
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
                
                Strict allowed-id rule:
                - viewpoint_node_assigns must contain exactly the Current-step allowed viewpoint ids above, no more and no fewer.
                - viewpoint_target_probs must contain exactly the Current-step allowed viewpoint ids above, no more and no fewer.
                - Do not include any other viewpoint id in viewpoint_node_assigns or viewpoint_target_probs, even if that id appears in compact shared graph summary, nodes, edges, region assigned_viewpoint_ids, or viewpoint_to_region.
                - Compact graph summary assignments are historical context. Do not copy full old region assigned_viewpoint_ids into current-step assignments.

                Current-step allowed viewpoint ids:
                {current_step_allowed_viewpoint_ids_json}

                Fixed direct detections from the separate detection step:
                {fixed_detections_json}

                Current-step interpretation note:
                - The observation context is the source of truth for current agent locations.
                - If a current viewpoint already appears in the graph summary, still treat it as current and grounded for this step.
                - If a current viewpoint has prior_assigned_region_id and prior_assigned_region_label in the observation context, treat them as earlier semantic hypotheses that must be checked against the current panorama.
                - If a current region already appears in the graph summary, reuse its id and label and still include it in visible_region_nodes.

                Output schema example. Use keys and value types only. Do not copy example values unless supported:
                {schema_json}

                Field descriptions:
                {field_descriptions_json}

                Current step request:
                - Identify each agent current semantic region.
                - For each current viewpoint with prior_assigned_region_id, check whether prior_assigned_region_label still matches the current panorama.
                - If the prior region label still matches, keep the assignment and do not include that viewpoint in current_viewpoints_reassignment.
                - If the prior region label does not match, assign the viewpoint to the better-matching region and add one current_viewpoints_reassignment item.
                - If a reassigned region is newly proposed, include its full region node record in visible_region_nodes.
                - Include exactly the Current-step allowed viewpoint ids in viewpoint_node_assigns, no more and no fewer.
                - Include exactly the Current-step allowed viewpoint ids in viewpoint_target_probs, no more and no fewer.
                - Do not copy old viewpoint ids from graph_summary region assigned_viewpoint_ids.
                - For current viewpoint target_probs, use binary direct-detection evidence consistent with detections.
                - For visible neighboring viewpoint target_probs, use soft positive target-location scores.
                - Estimate region target_probs using active target_id keys and active target descriptions.
                - Do not include found or completed targets in target_probs, detections, or existence hypotheses.
                - Copy the fixed direct detections exactly into detections. Do not change founds.
                - Propose invisible_region_nodes only for completely unseen areas inferred from layout cues.
                - Treat partially visible adjacent areas as visible_region_nodes, not invisible_region_nodes.
                - Propose only legal uncertain edges supported by observation and graph context.
                - Propose VZ edges only to semantic regions with no assigned viewpoints; the region may be visible or invisible.
                - Propose VV edges between two unvisited non-current viewpoints only when a directly traversable local connection is spatially plausible from the observation and graph context. The support may be uncertain, so use lower exist_prob for weak but meaningful hypotheses. Do not propose a VV edge across an apparent obstacle, large furniture, wall, blocked passage, or closed partition. Same-room or same-region membership alone is not enough.
                - Keep graph_summary.viewpoint_to_region assignments only for non-current visible neighboring viewpoints. For current viewpoints, infer the best matching region from the current panorama and allow old assignments to be corrected.
                - Return compact JSON only.
                """)
            .strip()
            .format(
                targets_json=json.dumps(target_records, indent=2, sort_keys=True),
                graph_summary_json=json.dumps(
                    prompt_graph_summary, indent=2, sort_keys=True
                ),
                agent_context_json=json.dumps(agent_context, indent=2, sort_keys=True),
                fixed_detections_json=json.dumps(
                    fixed_detections, indent=2, sort_keys=True
                ),
                schema_json=json.dumps(schema, indent=2, sort_keys=True),
                field_descriptions_json=json.dumps(
                    field_descriptions, indent=2, sort_keys=True
                ),
                current_step_allowed_viewpoint_ids_json=json.dumps(
                    current_step_allowed_viewpoint_ids, indent=2
                ),
            )
        )

        return system_message, user_message

    def propose_semantic_nodes(
        self,
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        graph: HypothesisGraph,
    ) -> Optional[Dict[str, object]]:
        if self.save_debug_images:
            for image_index, observation in enumerate(agent_observations):
                panorama_image = observation["annotated_panorama"]
                if panorama_image.dtype != np.uint8:
                    panorama_image = panorama_image.astype(np.uint8)
                Image.fromarray(panorama_image).save(
                    "debug_agent_panorama_%s.png" % image_index
                )

        graph_summary = graph.get_mllm_summary()
        active_detection_targets = self._filter_targets_by_found_state(
            targets=targets,
            target_found=getattr(graph, "target_found", {}),
        )

        if not active_detection_targets:
            return None

        step_index = getattr(self, "semantic_raw_output_index", 0)

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

        debugpy.breakpoint()  # Debug before requesting MLLM completion.

        max_validation_retries = getattr(self, "max_validation_retries", 0)
        validation_errors: List[str] = []
        last_error = None

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
                    )
                    self.semantic_raw_output_index = step_index + 1
                    self._write_user_message(step_index, user_message)
                    return payload
                except Exception as exc:
                    print(
                        "Saved semantic raw output for step %s is invalid. "
                        "Requesting MLLM instead. Error: %s" % (step_index, str(exc))
                    )
            else:
                print(
                    "Saved semantic raw output for step %s was not found. "
                    "Requesting MLLM instead." % step_index
                )

        # request MLLM completion with retries for validation failures
        for attempt_index in range(max_validation_retries + 1):
            if attempt_index == 0:
                attempt_user_message = user_message
            else:
                attempt_user_message = self._build_validation_retry_user_message(
                    user_message=user_message,
                    validation_errors=validation_errors,
                    attempt_index=attempt_index,
                    max_validation_retries=max_validation_retries,
                )

            user_content = [{"type": "text", "text": attempt_user_message}]
            user_content.extend(image_content)

            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_content},
            ]

            if attempt_index == 0:
                print(f"Requesting completion for step {step_index}")
            else:
                print(
                    "Retrying MLLM completion for step %s after validation "
                    "failure, attempt %s of %s"
                    % (step_index, attempt_index, max_validation_retries)
                )
            request_start_time = time.time()
            decoded = self._request_completion(
                messages=messages,
                model_name=getattr(self, "graph_model_name", ""),
            )
            # print the running time (s) for requesting completion
            print(
                "MLLM completion request for step %s took %.2f seconds"
                % (step_index, time.time() - request_start_time)
            )

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
                )

                # Save only the accepted raw output as the final log for this step.
                # If a retry succeeds, it overwrites the failed attempt under the
                # normal step filename, without a retry suffix.
                self._write_semantic_raw_output(
                    step_index,
                    json.dumps(payload, indent=2, sort_keys=True),
                )
                self._write_user_message(step_index, attempt_user_message)

                self.semantic_raw_output_index = step_index + 1
                return payload

            except Exception as exc:
                last_error = exc
                error_message = str(exc)

                if error_message not in validation_errors:
                    validation_errors.append(error_message)

                if attempt_index >= max_validation_retries:
                    self.semantic_raw_output_index = step_index + 1
                    accumulated_errors_text = "\n".join(
                        "%d. %s" % (index + 1, error)
                        for index, error in enumerate(validation_errors)
                    )
                    raise ValueError(
                        "MLLM output failed validation after %s attempt(s). "
                        "Accumulated validation errors:\n%s"
                        % (
                            max_validation_retries + 1,
                            accumulated_errors_text,
                        )
                    ) from exc

                print(
                    "MLLM output validation failed on attempt %s of %s: %s"
                    % (
                        attempt_index + 1,
                        max_validation_retries + 1,
                        str(last_error),
                    )
                )
                debugpy.breakpoint()

        debugpy.breakpoint()  # Debug if the retry loop exits unexpectedly.

        raise RuntimeError("Unexpected retry loop exit.")

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
    ) -> Dict[str, object]:
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

        def validate_zero_one_probability(value, context: str) -> None:
            if not is_number(value):
                raise TypeError("%s must be numeric." % context)
            if not (0.0 <= float(value) <= 1.0):
                raise ValueError("%s=%s is outside [0, 1]." % (context, value))

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

        def is_grounded_value(value) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value) != 0.0
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes"}
            return False

        observation_by_agent = {
            str(observation["agent_id"]): observation
            for observation in agent_observations
        }
        expected_agent_ids = set(observation_by_agent)

        target_ids = {str(target["target_id"]) for target in targets}
        if len(target_ids) != len(targets):
            raise ValueError("Target ids must be unique.")

        agents = require_list(payload["agents"], "agents")
        current_viewpoints_reassignment = require_list(
            payload["current_viewpoints_reassignment"],
            "current_viewpoints_reassignment",
        )
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
        previously_visited_viewpoint_ids = set()

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
                    grounded = is_grounded_value(node.get("grounded", 0))

                    try:
                        visit_times = int(node.get("node_visit_times", 0) or 0)
                    except (TypeError, ValueError):
                        visit_times = 0

                    if grounded or visit_times > 0:
                        previously_visited_viewpoint_ids.add(node_id)

                elif node_type == "region":
                    graph_region_records[node_id] = node

                    for viewpoint_id_raw in (
                        node.get("assigned_viewpoint_ids", []) or []
                    ):
                        graph_viewpoint_to_region.setdefault(
                            int(viewpoint_id_raw), node_id
                        )

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

        def validate_target_probs_allow_zero(
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
                validate_zero_one_probability(
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

        total_region_count = len(visible_region_nodes) + len(invisible_region_nodes)
        if total_region_count > 5:
            raise ValueError(
                "At most 5 current-step semantic regions are allowed, got %s."
                % total_region_count
            )

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
                debugpy.breakpoint()  # Debug invalid viewpoint_id in viewpoint_target_probs.
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
            elif viewpoint_id in previously_visited_viewpoint_ids:
                validate_target_probs_allow_zero(
                    item["target_probs"],
                    "previously visited visible neighboring viewpoint %s"
                    % viewpoint_id,
                )
            else:
                validate_target_probs_positive(
                    item["target_probs"],
                    "unvisited visible neighboring viewpoint %s" % viewpoint_id,
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

        # Fix visible neighboring viewpoint assignments when the graph summary
        # already gives a fixed viewpoint_to_region mapping. Current viewpoints
        # are not overwritten because the observation context remains the source
        # of truth for current agent locations.
        corrected_assignments = []
        for viewpoint_id in sorted(all_current_step_viewpoint_ids):
            if viewpoint_id in current_viewpoint_ids:
                continue

            fixed_region_id = graph_viewpoint_to_region.get(viewpoint_id)
            if fixed_region_id is None:
                continue

            old_region_id = assigned_viewpoint_to_region.get(viewpoint_id)
            if old_region_id == fixed_region_id:
                continue

            if fixed_region_id in invisible_region_ids:
                for region in list(invisible_region_nodes):
                    if int(region["id"]) == fixed_region_id:
                        invisible_region_nodes.remove(region)
                        invisible_region_ids.remove(fixed_region_id)
                        visible_region_nodes.append(region)
                        visible_region_ids.add(fixed_region_id)
                        break

            if fixed_region_id not in visible_region_ids:
                restored_region = make_region_record_from_graph(fixed_region_id)
                visible_region_nodes.append(restored_region)
                visible_region_ids.add(fixed_region_id)

            all_region_ids = visible_region_ids | invisible_region_ids
            assigned_viewpoint_to_region[viewpoint_id] = fixed_region_id
            corrected_assignments.append((viewpoint_id, old_region_id, fixed_region_id))

        # check for current-viewpoint old-assignment correction
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

        # Validate explicit current-viewpoint region reassignment events. The
        # final current-viewpoint assignments are still represented by agents and
        # viewpoint_node_assigns. This object records only true changes from an
        # existing graph_summary.viewpoint_to_region assignment.
        returned_reassignment_by_viewpoint = {}
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

            if viewpoint_id in returned_reassignment_by_viewpoint:
                raise ValueError(
                    "Duplicated current_viewpoints_reassignment item for viewpoint %s."
                    % viewpoint_id
                )

            old_region_id = graph_viewpoint_to_region.get(viewpoint_id)
            if old_region_id is None:
                raise ValueError(
                    "current_viewpoints_reassignment includes viewpoint %s, but this "
                    "viewpoint has no prior graph_summary.viewpoint_to_region assignment."
                    % viewpoint_id
                )

            if new_region_id == old_region_id:
                raise ValueError(
                    "current_viewpoints_reassignment includes viewpoint %s, but "
                    "new_assigned_region_id %s is identical to its old region assignment."
                    % (viewpoint_id, new_region_id)
                )

            if new_region_id not in visible_region_ids:
                raise ValueError(
                    "current_viewpoints_reassignment uses new_assigned_region_id %s "
                    "for viewpoint %s, but this region is not in visible_region_nodes."
                    % (new_region_id, viewpoint_id)
                )

            final_assigned_region_id = assigned_viewpoint_to_region.get(viewpoint_id)
            if new_region_id != final_assigned_region_id:
                raise ValueError(
                    "current_viewpoints_reassignment says viewpoint %s is reassigned "
                    "to region %s, but viewpoint_node_assigns assigns it to region %s."
                    % (viewpoint_id, new_region_id, final_assigned_region_id)
                )

            returned_reassignment_by_viewpoint[viewpoint_id] = new_region_id

        expected_reassignment_by_viewpoint = {}
        for current_viewpoint_id in sorted(current_viewpoint_ids):
            old_region_id = graph_viewpoint_to_region.get(current_viewpoint_id)
            new_region_id = assigned_viewpoint_to_region.get(current_viewpoint_id)

            if old_region_id is not None and new_region_id != old_region_id:
                expected_reassignment_by_viewpoint[current_viewpoint_id] = new_region_id

        if returned_reassignment_by_viewpoint != expected_reassignment_by_viewpoint:
            raise ValueError(
                "current_viewpoints_reassignment does not match the actual current-"
                "viewpoint region assignment changes. Got %s, expected %s."
                % (
                    returned_reassignment_by_viewpoint,
                    expected_reassignment_by_viewpoint,
                )
            )

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

        if len(visible_region_nodes) + len(invisible_region_nodes) > 5:
            raise ValueError(
                "Fixed assignment correction requires %s current-step regions, "
                "which exceeds the maximum of 5."
                % (len(visible_region_nodes) + len(invisible_region_nodes))
            )

        if corrected_assignments:
            print("Corrected fixed non-current viewpoint assignments:")
            for (
                viewpoint_id,
                old_region_id,
                fixed_region_id,
            ) in corrected_assignments:
                print(
                    "  Viewpoint %s reassigned from region %s to fixed region %s."
                    % (viewpoint_id, old_region_id, fixed_region_id)
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

                cleaned_new_edges.append(edge)
                continue

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

        return payload
