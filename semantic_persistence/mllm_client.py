from __future__ import annotations

import base64
import io
import json
import os
import re
from textwrap import dedent
import time
from typing import TYPE_CHECKING, Dict, List, Optional
import debugpy
import numpy as np
from openai import APITimeoutError, BadRequestError, OpenAI
from PIL import Image

import Helper

# for detection only: conservative, reduce false target detections
DETECTION_TEMPERATURE = 0.1
DETECTION_TOP_P = 0.9
DETECTION_TOP_K = 40
DETECTION_PRESENCE_PENALTY = 0.0
# for graph generation: still stable, but allows non-uniform probabilities
GRAPH_TEMPERATURE = 0.7
GRAPH_TOP_P = 0.8
GRAPH_TOP_K = 20
GRAPH_PRESENCE_PENALTY = 1.5

MIN_P = 0.0
REPETITION_PENALTY = 1.0

DETECTION_MAX_NEW_TOKENS = 512
GRAPH_MAX_NEW_TOKENS = 32768
panorama_max_width_for_prompt = 1660

detect_thinking = False
graph_thinking = False

if TYPE_CHECKING:
    from semantic_persistence import HypothesisGraph


class SigLIPRegionValidationError(RuntimeError):
    pass


class GraphValidationError(ValueError):
    def __init__(
        self,
        category: str,
        message: str,
        details: Optional[Dict[str, object]] = None,
        retry_guidance: Optional[List[str]] = None,
    ):
        self.category = str(category)
        self.message = str(message)
        self.details = dict(details or {})
        self.retry_guidance = [str(item) for item in (retry_guidance or [])]
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = ["[%s] %s" % (self.category, self.message)]
        if self.details:
            parts.append(
                "Details: %s"
                % json.dumps(self.details, sort_keys=True, default=str)
            )
        if self.retry_guidance:
            parts.append("Retry guidance: %s" % " ".join(self.retry_guidance))
        return "\n".join(parts)


class MLLMRetryExhaustedError(RuntimeError):
    def __init__(
        self,
        stage: str,
        step_index: int,
        attempts: int,
        last_error: object,
    ):
        self.stage = str(stage)
        self.step_index = int(step_index)
        self.attempts = int(attempts)
        self.last_error = str(last_error)
        super().__init__(
            "%s MLLM output failed validation after %s attempt(s) at step %s. "
            "Last error: %s"
            % (self.stage, self.attempts, self.step_index, self.last_error)
        )


class MLLMProviderCreditError(RuntimeError):
    def __init__(
        self,
        stage: str,
        router: str,
        model: str,
        status_code: object,
        provider_code: object,
        provider_type: object,
        message: str,
        step_index: int | None = None,
    ):
        self.stage = str(stage)
        self.router = str(router)
        self.model = str(model)
        self.status_code = None if status_code is None else int(status_code)
        self.provider_code = None if provider_code is None else str(provider_code)
        self.provider_type = None if provider_type is None else str(provider_type)
        self.message = str(message)
        self.step_index = None if step_index is None else int(step_index)
        super().__init__(
            "%s MLLM provider credit failure for model %s: %s"
            % (self.stage, self.model, self.message)
        )


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
        max_request_timeout_retries: int = 1,
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
        self.max_request_timeout_retries = max(0, int(max_request_timeout_retries))
        self.semantic_raw_output_index = 1
        self.found_target_trace = []
        self.last_direct_detections = []
        self.graph_api_key_env = str(graph_api_key_env)
        self.detection_api_key_env = str(detection_api_key_env)
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

    @staticmethod
    def _api_error_body(exc) -> Dict[str, object]:
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            if isinstance(body.get("error"), dict):
                return body["error"]
            return body

        response = getattr(exc, "response", None)
        if response is not None:
            try:
                decoded = response.json()
            except Exception:
                decoded = None
            if isinstance(decoded, dict):
                if isinstance(decoded.get("error"), dict):
                    return decoded["error"]
                return decoded

        return {}

    @classmethod
    def _provider_credit_error_from_exception(
        cls,
        exc,
        stage: str,
        router: str,
        model: str,
    ) -> MLLMProviderCreditError | None:
        body = cls._api_error_body(exc)
        status_code = getattr(exc, "status_code", None)
        if status_code is None:
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)

        provider_code = body.get("code")
        provider_type = body.get("type")
        message = str(body.get("message") or exc)
        searchable = " ".join(
            str(item).lower()
            for item in (
                provider_code,
                provider_type,
                message,
            )
            if item is not None
        )
        credit_tokens = (
            "insufficient_quota",
            "insufficient_balance",
            "billing_hard_limit_reached",
            "balance_not_enough",
            "payment required",
            "quota",
            "balance",
            "billing",
            "credit",
        )

        if int(status_code or 0) != 402 and not any(
            token in searchable for token in credit_tokens
        ):
            return None

        return MLLMProviderCreditError(
            stage=stage,
            router=router,
            model=model,
            status_code=status_code,
            provider_code=provider_code,
            provider_type=provider_type,
            message=message,
        )

    def _request_completion(
        self,
        messages,
        model_name: str,
        request_type: str = "graph",
        thinking_mode: bool = False,
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

        request_kwargs = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "presence_penalty": presence_penalty,
            "max_tokens": max_tokens,
            "extra_body": {
                "top_k": top_k,
                "min_p": MIN_P,
                "repetition_penalty": REPETITION_PENALTY,
                "chat_template_kwargs": {
                    "enable_thinking": bool(thinking_mode),
                },
            },
        }

        if request_type == "detection":
            request_kwargs["tools"] = [self._detection_tool_definition()]
            request_kwargs["tool_choice"] = {
                "type": "function",
                "function": {"name": "report_target_detections"},
            }
            request_kwargs["parallel_tool_calls"] = False
        else:
            request_kwargs["response_format"] = {"type": "json_object"}

        try:
            completion = client.chat.completions.create(**request_kwargs)

            print("usage:", completion.usage)
            print("model:", completion.model)
            print("finish_reason:", completion.choices[0].finish_reason)
            print()

        except BadRequestError as exc:
            provider_credit_error = self._provider_credit_error_from_exception(
                exc=exc,
                stage=request_type,
                router=router_name,
                model=model_name,
            )
            if provider_credit_error is not None:
                raise provider_credit_error from exc

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

        except Exception as exc:
            provider_credit_error = self._provider_credit_error_from_exception(
                exc=exc,
                stage=request_type,
                router=router_name,
                model=model_name,
            )
            if provider_credit_error is not None:
                raise provider_credit_error from exc
            raise

        if request_type == "detection":
            return self._extract_detection_tool_arguments(completion)

        return self._message_to_text(completion.choices[0].message.content)

    @staticmethod
    def _detection_tool_definition() -> Dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": "report_target_detections",
                "description": (
                    "Report directly visible target detections for each panorama image."
                ),
                "strict": True,
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "detections": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "agent_id": {"type": "string"},
                                    "found_target_indices": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "target_center_xs": {
                                        "type": "array",
                                        "items": {"type": "number"},
                                    },
                                },
                                "required": [
                                    "agent_id",
                                    "found_target_indices",
                                    "target_center_xs",
                                ],
                            },
                        }
                    },
                    "required": ["detections"],
                },
            },
        }

    @staticmethod
    def _tool_call_attr(value, key: str):
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key)

    @classmethod
    def _extract_detection_tool_arguments(cls, completion) -> str:
        message = completion.choices[0].message
        tool_calls = cls._tool_call_attr(message, "tool_calls")

        if not tool_calls:
            raise ValueError("Detection model did not call report_target_detections.")
        if len(tool_calls) != 1:
            raise ValueError(
                "Detection model must call report_target_detections exactly once."
            )

        tool_call = tool_calls[0]
        if cls._tool_call_attr(tool_call, "type") != "function":
            raise ValueError("Detection tool call must have type 'function'.")

        function_call = cls._tool_call_attr(tool_call, "function")
        function_name = cls._tool_call_attr(function_call, "name")
        if function_name != "report_target_detections":
            raise ValueError(
                "Detection model called unexpected function %s." % function_name
            )

        arguments = cls._tool_call_attr(function_call, "arguments")
        if not isinstance(arguments, str) or not arguments.strip():
            raise ValueError("Detection tool call arguments must be a nonempty string.")

        return arguments

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

    def _detection_attempt_error_raw_output_path(
        self, step_index: int, attempt_index: int
    ) -> str:
        return os.path.join(
            getattr(self, "raw_output_dir", "mllm_raw_outputs"),
            "detection_step_%04d_attempt_%02d_error.txt"
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

    def _observation_image_path(self, step_index: int, agent_id: str) -> str:
        return os.path.join(
            getattr(self, "raw_debug_dir", "mllm_debug_outputs"),
            "observation_step_%04d_agent_%s.jpg" % (int(step_index), str(agent_id)),
        )

    @staticmethod
    def _required_semantic_top_level_keys(
        semantic_payload_contract: str,
    ) -> List[str]:
        common_top_level_keys = {
            "current_viewpoints_reassignment",
            "visible_region_nodes",
            "invisible_region_nodes",
            "viewpoint_node_assigns",
            "new_edges",
            "edge_distance_variances",
        }
        if semantic_payload_contract == "graph_mllm":
            required_top_level_keys = common_top_level_keys | {
                "region_target_scores",
                "viewpoint_target_scores",
            }
        else:
            required_top_level_keys = common_top_level_keys | {
                "viewpoint_target_probs",
                "viewpoint_target_score_basis",
            }
        return sorted(required_top_level_keys)

    @staticmethod
    def _format_graph_validation_errors_for_retry(
        validation_errors: List[object],
    ) -> str:
        if not validation_errors:
            return "No validation error details were captured."

        grouped_errors = {}
        seen_error_keys = set()
        for error in validation_errors:
            if isinstance(error, GraphValidationError):
                detail_key = json.dumps(error.details, sort_keys=True, default=str)
                error_key = (
                    error.category,
                    error.message,
                    detail_key,
                    tuple(error.retry_guidance),
                )
                if error_key in seen_error_keys:
                    continue
                seen_error_keys.add(error_key)
                grouped_errors.setdefault(error.category, []).append(error)
            else:
                error_text = str(error)
                error_key = ("unstructured", error_text)
                if error_key in seen_error_keys:
                    continue
                seen_error_keys.add(error_key)
                grouped_errors.setdefault("unstructured", []).append(error_text)

        sections = []
        for category in sorted(grouped_errors):
            sections.append("[%s]" % category)
            for index, error in enumerate(grouped_errors[category], start=1):
                if isinstance(error, GraphValidationError):
                    sections.append("%d. %s" % (index, error.message))
                    if error.details:
                        sections.append(
                            "   Details: %s"
                            % json.dumps(
                                error.details,
                                sort_keys=True,
                                default=str,
                            )
                        )
                    if error.retry_guidance:
                        sections.append("   Corrective guidance:")
                        for guidance in error.retry_guidance:
                            sections.append("   - %s" % guidance)
                else:
                    sections.append("%d. %s" % (index, error))
        return "\n".join(sections)

    @staticmethod
    def _payload_region_ids(payload: Dict[str, object]) -> List[int]:
        region_ids = set()
        for key in ("visible_region_nodes", "invisible_region_nodes"):
            for region in payload.get(key, []):
                if isinstance(region, dict) and "id" in region:
                    region_ids.add(int(region["id"]))
        return sorted(region_ids)

    @staticmethod
    def _graph_region_ids(graph_summary: Optional[Dict[str, object]]) -> List[int]:
        if graph_summary is None:
            return []
        return sorted(
            int(node["id"])
            for node in graph_summary.get("nodes", [])
            if isinstance(node, dict) and node.get("type") == "region"
        )

    @staticmethod
    def _returned_assignment_viewpoint_ids(payload: Dict[str, object]) -> List[int]:
        viewpoint_ids = set()
        for item in payload.get("viewpoint_node_assigns", []):
            if not isinstance(item, dict):
                continue
            for viewpoint_id in item.get("assigned_viewpoint_node_indices", []):
                viewpoint_ids.add(int(viewpoint_id))
        return sorted(viewpoint_ids)

    @staticmethod
    def _returned_viewpoint_target_ids(
        payload: Dict[str, object],
        semantic_payload_contract: str,
    ) -> List[int]:
        key = (
            "viewpoint_target_scores"
            if semantic_payload_contract == "graph_mllm"
            else "viewpoint_target_probs"
        )
        return sorted(
            int(item["id"])
            for item in payload.get(key, [])
            if isinstance(item, dict) and "id" in item
        )

    @staticmethod
    def _viewpoint_target_score_details(
        payload: Dict[str, object],
        graph_summary: Optional[Dict[str, object]],
        required_viewpoint_ids: List[int],
        target_id: str,
        semantic_payload_contract: str,
    ) -> Dict[str, object]:
        raw_scores_by_viewpoint = {
            int(viewpoint_id): {"raw_score": None}
            for viewpoint_id in required_viewpoint_ids
        }
        if graph_summary is not None:
            for node in graph_summary.get("nodes", []):
                if not isinstance(node, dict) or node.get("type") != "viewpoint":
                    continue
                viewpoint_id = int(node["id"])
                if viewpoint_id not in raw_scores_by_viewpoint:
                    continue
                raw_target_probs = node.get("raw_target_probs", {}) or {}
                if str(target_id) in raw_target_probs:
                    raw_scores_by_viewpoint[viewpoint_id]["raw_score"] = float(
                        raw_target_probs[str(target_id)]
                    )
                    raw_scores_by_viewpoint[viewpoint_id]["source"] = "prior"

        if semantic_payload_contract == "graph_mllm":
            for item in payload.get("viewpoint_target_scores", []):
                if not isinstance(item, dict) or "id" not in item:
                    continue
                viewpoint_id = int(item["id"])
                if viewpoint_id not in raw_scores_by_viewpoint:
                    continue
                target_scores = item.get("target_scores", {})
                if not isinstance(target_scores, dict) or str(target_id) not in target_scores:
                    continue
                score_record = target_scores[str(target_id)]
                if not isinstance(score_record, dict):
                    continue
                raw_scores_by_viewpoint[viewpoint_id] = {
                    "raw_score": score_record.get("raw_score"),
                    "evidence_strength": score_record.get("evidence_strength"),
                    "basis": score_record.get("basis"),
                    "source": "returned",
                }
        else:
            basis_by_viewpoint = {}
            for item in payload.get("viewpoint_target_score_basis", []):
                if not isinstance(item, dict) or "id" not in item:
                    continue
                score_basis = item.get("score_basis", {})
                if isinstance(score_basis, dict) and str(target_id) in score_basis:
                    basis_by_viewpoint[int(item["id"])] = score_basis[str(target_id)]

            for item in payload.get("viewpoint_target_probs", []):
                if not isinstance(item, dict) or "id" not in item:
                    continue
                viewpoint_id = int(item["id"])
                if viewpoint_id not in raw_scores_by_viewpoint:
                    continue
                source_key = (
                    "raw_target_probs"
                    if "raw_target_probs" in item
                    else "target_probs"
                )
                target_probs = item.get(source_key, {})
                if not isinstance(target_probs, dict) or str(target_id) not in target_probs:
                    continue
                raw_scores_by_viewpoint[viewpoint_id] = {
                    "raw_score": target_probs[str(target_id)],
                    "basis": basis_by_viewpoint.get(viewpoint_id),
                    "source": "returned",
                }

        return {
            str(viewpoint_id): raw_scores_by_viewpoint[viewpoint_id]
            for viewpoint_id in sorted(raw_scores_by_viewpoint)
        }

    def _graph_validation_error_from_exception(
        self,
        exc: Exception,
        payload: Dict[str, object],
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        graph_summary: Optional[Dict[str, object]],
        semantic_payload_contract: str,
    ) -> GraphValidationError:
        message = str(exc)
        target_ids = [str(target["target_id"]) for target in targets]
        target_descriptions = {
            str(target["target_id"]): str(target.get("description", ""))
            for target in targets
        }
        contract_sets = MLLMClient._graph_mllm_contract_sets(
            agent_observations=agent_observations,
            graph_summary=graph_summary,
        )
        region_start_id = int(len(Helper.viewpoint_vp_label_by_index))
        required_top_level_keys = MLLMClient._required_semantic_top_level_keys(
            semantic_payload_contract
        )
        base_details = {
            "error_type": exc.__class__.__name__,
            "semantic_payload_contract": semantic_payload_contract,
            "target_ids": target_ids,
        }

        if (
            "top-level keys" in message
            or message == "payload must be a dictionary."
        ):
            category = "top-level schema"
            details = dict(base_details)
            details.update(
                {
                    "required_top_level_keys": required_top_level_keys,
                    "returned_top_level_keys": (
                        sorted(payload) if isinstance(payload, dict) else None
                    ),
                }
            )
            guidance = [
                "Return exactly the required graph JSON top-level keys.",
                "Remove extra top-level keys and add every missing required top-level key.",
            ]
            return GraphValidationError(category, message, details, guidance)

        viewpoint_tokens = (
            "viewpoint_target_scores",
            "viewpoint_target_probs",
            "viewpoint_target_score_basis",
            "MLLM-updatable",
            "evidence_strength",
            "raw_score",
        )
        assignment_tokens = (
            "viewpoint_node_assigns",
            "assigned viewpoint",
            "assignment group",
            "current_viewpoints_reassignment",
            "Current viewpoint",
            "current viewpoint",
            "Derived current region",
        )
        region_score_tokens = (
            "region_target_scores",
            "Region target probabilities",
            "changed from assigned to unassigned",
        )
        edge_tokens = (
            "new_edges",
            "edge_distance_variances",
            "edge_type",
            "VV edge",
            "VZ edge",
            "self-edge",
        )
        region_node_tokens = (
            "visible_region_nodes",
            "invisible_region_nodes",
            "region id",
            "Region ids",
            "region ids",
            "Graph summary contains region ids",
            "target_probs keys",
            "exist_prob",
            "label",
        )

        if any(token in message for token in viewpoint_tokens):
            category = "viewpoint target scores"
            required_ids = sorted(contract_sets["required_mllm_viewpoint_prob_ids"])
            details = dict(base_details)
            details.update(
                {
                    "required_mllm_viewpoint_target_ids": required_ids,
                    "returned_viewpoint_target_ids": MLLMClient._returned_viewpoint_target_ids(
                        payload,
                        semantic_payload_contract,
                    ),
                    "detection_fixed_viewpoint_ids": sorted(
                        contract_sets["detection_fixed_viewpoint_ids"]
                    ),
                }
            )
            guidance = [
                "Use viewpoint_target_scores only for eligible MLLM-updatable viewpoint ids.",
                "Remove current, grounded, and previously visited detection-fixed viewpoint ids from viewpoint_target_scores.",
                "Each returned viewpoint-target score must contain exactly raw_score, evidence_strength, and basis.",
                "Use active target ids only, nonnegative raw_score values, and evidence_strength exactly one of low, medium, or high.",
            ]
            zero_sum_match = re.search(
                r"MLLM-updatable viewpoint_target_probs for target ([^ ]+) sum to ([^ .]+)",
                message,
            )
            if zero_sum_match:
                target_id = str(zero_sum_match.group(1))
                details.update(
                    {
                        "zero_sum_target_id": target_id,
                        "zero_sum_target_description": target_descriptions.get(
                            target_id
                        ),
                        "raw_scores_by_viewpoint": MLLMClient._viewpoint_target_score_details(
                            payload=payload,
                            graph_summary=graph_summary,
                            required_viewpoint_ids=required_ids,
                            target_id=target_id,
                            semantic_payload_contract=semantic_payload_contract,
                        ),
                    }
                )
                guidance.append(
                    "For the zero-sum target, rescore that target across all eligible viewpoints and give at least one eligible viewpoint a positive raw_score."
                )
                guidance.append(
                    "Do not assign 0.0 to every candidate only because none is a perfect match; use partial cues such as level, room/area, adjacency, marker location, and graph context for relative positive mass."
                )
            return GraphValidationError(category, message, details, guidance)

        if any(token in message for token in region_score_tokens):
            category = "region target scores"
            details = dict(base_details)
            details.update(
                {
                    "payload_region_ids": MLLMClient._payload_region_ids(payload),
                    "graph_region_ids": MLLMClient._graph_region_ids(graph_summary),
                    "region_start_id": region_start_id,
                }
            )
            guidance = [
                "Remove region_target_scores for regions with final assigned viewpoints.",
                "For prior assigned regions that became unassigned, add complete region_target_scores for every active target_id.",
                "Use region_target_scores only for known type-(2) regions with no final assigned viewpoints.",
                "For region zero-sum failures, assign positive raw target score mass to at least one known region for that target.",
            ]
            return GraphValidationError(category, message, details, guidance)

        if any(token in message for token in edge_tokens):
            category = "edges"
            details = dict(base_details)
            details.update(
                {
                    "current_step_viewpoint_ids": sorted(
                        contract_sets["current_viewpoint_ids"]
                        | contract_sets["visible_viewpoint_ids"]
                    ),
                    "current_viewpoint_ids": sorted(
                        contract_sets["current_viewpoint_ids"]
                    ),
                    "visible_viewpoint_ids": sorted(
                        contract_sets["visible_viewpoint_ids"]
                    ),
                    "payload_region_ids": MLLMClient._payload_region_ids(payload),
                    "graph_region_ids": MLLMClient._graph_region_ids(graph_summary),
                    "region_start_id": region_start_id,
                }
            )
            guidance = [
                "Drop illegal optional new_edges unless a legal replacement is directly supported.",
                "VV edges must connect two non-current ungrounded and unvisited current-step viewpoint nodes.",
                "VZ edges must connect exactly one current-step viewpoint id and one region id, and must not connect a viewpoint to its assigned region.",
                "Do not connect VZ edges to regions that already have assigned viewpoints.",
            ]
            return GraphValidationError(category, message, details, guidance)

        if any(token in message for token in assignment_tokens):
            category = "assignments"
            expected_ids = sorted(contract_sets["assignment_required_viewpoint_ids"])
            returned_ids = MLLMClient._returned_assignment_viewpoint_ids(payload)
            details = dict(base_details)
            details.update(
                {
                    "expected_assignment_viewpoint_ids": expected_ids,
                    "returned_assignment_viewpoint_ids": returned_ids,
                    "missing_assignment_viewpoint_ids": sorted(
                        set(expected_ids) - set(returned_ids)
                    ),
                    "extra_assignment_viewpoint_ids": sorted(
                        set(returned_ids) - set(expected_ids)
                    ),
                    "current_viewpoint_ids": sorted(
                        contract_sets["current_viewpoint_ids"]
                    ),
                    "visible_viewpoint_ids": sorted(
                        contract_sets["visible_viewpoint_ids"]
                    ),
                }
            )
            guidance = [
                "Make viewpoint_node_assigns contain exactly the expected assignment viewpoint ids.",
                "Remove ids outside the expected assignment list and add missing expected ids.",
                "Use current_viewpoints_reassignment only for true current-viewpoint region changes from graph_summary.",
                "If a current viewpoint appears in both assignment fields, both fields must name the same final region.",
            ]
            return GraphValidationError(category, message, details, guidance)

        if any(token in message for token in region_node_tokens):
            category = "region nodes"
            details = dict(base_details)
            details.update(
                {
                    "payload_region_ids": MLLMClient._payload_region_ids(payload),
                    "graph_region_ids": MLLMClient._graph_region_ids(graph_summary),
                    "region_start_id": region_start_id,
                }
            )
            guidance = [
                "New region node ids must be unique and greater than or equal to region_start_id.",
                "Do not re-emit existing graph_summary regions in visible_region_nodes or invisible_region_nodes.",
                "Each region node must contain exactly id, label, exist_prob, and target_probs.",
                "Region target_probs must contain every active target_id with values in [0, 1].",
                "Region labels must be nonempty area labels and must not mention agent ids.",
            ]
            return GraphValidationError(category, message, details, guidance)

        category = "numeric/key/type"
        details = dict(base_details)
        details.update({"required_top_level_keys": required_top_level_keys})
        guidance = [
            "Fix the exact JSON path named in the error.",
            "Use the exact required key set for that object.",
            "Use numeric values in the required range for probabilities, distances, variances, and raw scores.",
        ]
        return GraphValidationError(category, message, details, guidance)

    @staticmethod
    def _build_validation_retry_user_message(
        user_message: str,
        validation_errors: List[object],
        attempt_index: int,
        max_validation_retries: int,
    ) -> str:
        """Append accumulated validation feedback to the original user message."""
        error_list = MLLMClient._format_graph_validation_errors_for_retry(
            validation_errors
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

            Category-specific correction rules:
            - Top-level schema: return exactly the required graph schema keys.
            - Region nodes: fix ids, labels, existence probabilities, and complete active target_probs.
            - Viewpoint target scores: use only eligible MLLM-updatable ids, valid target ids, nonnegative raw_score, evidence_strength in low/medium/high, and nonempty basis.
            - Assignments: use exactly the expected assigned viewpoint id list for viewpoint_node_assigns.
            - Region target scores: remove scores for regions with final assigned viewpoints and add complete scores for every active target_id on prior assigned regions that became unassigned.
            - Edges: drop illegal optional new_edges unless a legal replacement is directly supported by the panorama and graph context.
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
            Call report_target_detections exactly once with arguments matching the required detection schema.
            Do not output markdown, code fences, comments, text outside the tool call, extra top-level keys, trailing commas, or non-JSON booleans.

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
                - Call report_target_detections exactly once.
                - The tool arguments must be exactly one JSON object with top-level key "detections".
                - If no active target is visible in any image, pass:
                  {{"detections":[]}}
                - Include only agents that detect at least one target.
                - Each agent may appear at most once.
                - Only use active target_ids from the list above.
                - Do not include completed, unlisted, or not-found targets.
                - Do not include an agent-target pair if the detected object could reasonably be a different object type than the target description.

                Required JSON object:
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
            if isinstance(target_probs, dict):
                node["target_probs"] = {
                    str(target_id): value
                    for target_id, value in target_probs.items()
                    if str(target_id) in target_id_set
                }

            raw_target_probs = node.get("raw_target_probs")
            if isinstance(raw_target_probs, dict):
                node["raw_target_probs"] = {
                    str(target_id): value
                    for target_id, value in raw_target_probs.items()
                    if str(target_id) in target_id_set
                }

        return sanitized

    @staticmethod
    def _project_saved_payload_to_target_ids(
        payload: Dict[str, object],
        target_ids: List[str],
    ) -> Dict[str, object]:
        target_id_set = {str(target_id) for target_id in target_ids}
        projected = json.loads(json.dumps(payload))

        def project_target_probs(record: Dict[str, object]) -> None:
            for key in ("target_probs", "raw_target_probs"):
                target_probs = record.get(key)
                if isinstance(target_probs, dict):
                    record[key] = {
                        str(target_id): value
                        for target_id, value in target_probs.items()
                        if str(target_id) in target_id_set
                    }

        for item in projected.get("viewpoint_target_probs", []):
            if isinstance(item, dict):
                project_target_probs(item)

        for item in projected.get("viewpoint_target_score_basis", []):
            if not isinstance(item, dict):
                continue

            score_basis = item.get("score_basis")
            if isinstance(score_basis, dict):
                item["score_basis"] = {
                    str(target_id): basis
                    for target_id, basis in score_basis.items()
                    if str(target_id) in target_id_set
                }

        for item in projected.get("viewpoint_target_scores", []):
            if not isinstance(item, dict):
                continue

            target_scores = item.get("target_scores")
            if isinstance(target_scores, dict):
                item["target_scores"] = {
                    str(target_id): score
                    for target_id, score in target_scores.items()
                    if str(target_id) in target_id_set
                }

        for item in projected.get("region_target_scores", []):
            if not isinstance(item, dict):
                continue

            target_scores = item.get("target_scores")
            if isinstance(target_scores, dict):
                item["target_scores"] = {
                    str(target_id): score
                    for target_id, score in target_scores.items()
                    if str(target_id) in target_id_set
                }

        for key in ("visible_region_nodes", "invisible_region_nodes"):
            for region in projected.get(key, []):
                if isinstance(region, dict):
                    project_target_probs(region)

        return projected

    @staticmethod
    def _graph_mllm_contract_sets(
        agent_observations: List[Dict[str, object]],
        graph_summary: Optional[Dict[str, object]] = None,
    ) -> Dict[str, set]:
        current_viewpoint_ids = {
            int(observation["current_viewpoint_index"])
            for observation in agent_observations
        }

        visible_viewpoint_ids = set()
        for observation in agent_observations:
            for item in observation["visible_viewpoints"]:
                visible_viewpoint_ids.add(int(item["viewpoint_index"]))

        graph_viewpoint_node_ids = set()
        graph_viewpoint_status_by_id = {}
        graph_viewpoint_to_region = {}

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
                if node_type == "viewpoint":
                    viewpoint_id = int(node["id"])
                    graph_viewpoint_node_ids.add(viewpoint_id)
                    graph_viewpoint_status_by_id[viewpoint_id] = {
                        "prior_grounded": bool(node.get("grounded", 0)),
                        "prior_visit_times": int(node.get("node_visit_times", 0)),
                    }
                elif node_type == "region":
                    region_id = int(node["id"])
                    for viewpoint_id_raw in (
                        node.get("assigned_viewpoint_ids", []) or []
                    ):
                        graph_viewpoint_to_region.setdefault(
                            int(viewpoint_id_raw), region_id
                        )

        current_viewpoint_ids_without_prior_region = {
            viewpoint_id
            for viewpoint_id in current_viewpoint_ids
            if viewpoint_id not in graph_viewpoint_to_region
        }

        new_visible_neighbor_assignment_viewpoint_ids = (
            visible_viewpoint_ids - current_viewpoint_ids - graph_viewpoint_node_ids
        )
        assignment_required_viewpoint_ids = (
            new_visible_neighbor_assignment_viewpoint_ids
            | current_viewpoint_ids_without_prior_region
        )

        detection_fixed_viewpoint_ids = set(current_viewpoint_ids)
        for viewpoint_id, status in graph_viewpoint_status_by_id.items():
            if (
                bool(status.get("prior_grounded", False))
                or int(status.get("prior_visit_times", 0)) > 0
            ):
                detection_fixed_viewpoint_ids.add(viewpoint_id)

        required_mllm_viewpoint_prob_ids = (
            graph_viewpoint_node_ids | visible_viewpoint_ids
        ) - detection_fixed_viewpoint_ids

        return {
            "current_viewpoint_ids": current_viewpoint_ids,
            "visible_viewpoint_ids": visible_viewpoint_ids,
            "graph_viewpoint_node_ids": graph_viewpoint_node_ids,
            "detection_fixed_viewpoint_ids": detection_fixed_viewpoint_ids,
            "required_mllm_viewpoint_prob_ids": required_mllm_viewpoint_prob_ids,
            "assignment_required_viewpoint_ids": assignment_required_viewpoint_ids,
        }

    @staticmethod
    def _project_saved_payload_to_graph_mllm_contract(
        payload: Dict[str, object],
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        graph_summary: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        target_ids = [str(target["target_id"]) for target in targets]
        target_id_set = set(target_ids)
        projected = MLLMClient._project_saved_payload_to_target_ids(
            payload=payload,
            target_ids=target_ids,
        )
        contract_sets = MLLMClient._graph_mllm_contract_sets(
            agent_observations=agent_observations,
            graph_summary=graph_summary,
        )
        required_mllm_viewpoint_prob_ids = contract_sets[
            "required_mllm_viewpoint_prob_ids"
        ]

        projected_viewpoint_target_probs = []
        for item in projected["viewpoint_target_probs"]:
            viewpoint_id = int(item["id"])
            if viewpoint_id not in required_mllm_viewpoint_prob_ids:
                continue

            source_key = (
                "raw_target_probs" if "raw_target_probs" in item else "target_probs"
            )
            raw_target_probs = {
                str(target_id): value
                for target_id, value in item[source_key].items()
                if str(target_id) in target_id_set
            }

            projected_viewpoint_target_probs.append(
                {
                    "id": viewpoint_id,
                    "target_probs": dict(raw_target_probs),
                    "raw_target_probs": raw_target_probs,
                }
            )

        projected["viewpoint_target_probs"] = projected_viewpoint_target_probs

        projected_viewpoint_target_score_basis = []
        for item in projected.get("viewpoint_target_score_basis", []):
            if not isinstance(item, dict):
                continue

            viewpoint_id = int(item["id"])
            if viewpoint_id not in required_mllm_viewpoint_prob_ids:
                continue

            projected_viewpoint_target_score_basis.append(item)

        projected["viewpoint_target_score_basis"] = (
            projected_viewpoint_target_score_basis
        )
        # Saved replay validates the materialized downstream payload shape. Hybrid
        # logs from live runs may still contain the live graph-MLLM score field.
        projected.pop("viewpoint_target_scores", None)
        return projected

    def _decode_saved_semantic_payload(
        self,
        decoded: str,
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        graph_summary: Optional[Dict[str, object]],
        scorer,
    ) -> tuple[Dict[str, object], List[str]]:
        raw = self._strip_code_fences(decoded)
        payload = self._parse_json_strict(raw)
        payload = self._project_saved_payload_to_graph_mllm_contract(
            payload=payload,
            agent_observations=agent_observations,
            targets=targets,
            graph_summary=graph_summary,
        )
        repair_messages = self._repair_graph_mllm_payload(
            payload=payload,
            agent_observations=agent_observations,
            targets=targets,
            graph_summary=graph_summary,
        )
        payload = self._validate_payload(
            payload=payload,
            agent_observations=agent_observations,
            targets=targets,
            graph_summary=graph_summary,
            scorer=scorer,
            semantic_payload_contract="saved_materialized",
        )
        return payload, repair_messages

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

            Call report_target_detections exactly once with corrected complete arguments. Keep the same detection schema.
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
                    payload = self._parse_json_strict(raw)
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

            decoded = None
            try:
                decoded = self._request_completion(
                    messages=messages,
                    model_name=getattr(self, "detection_model_name", ""),
                    request_type="detection",
                    thinking_mode=detect_thinking,
                )
                raw = self._strip_code_fences(decoded)
                payload = self._parse_json_strict(raw)
                detections = self._validate_detection_payload(
                    payload=payload,
                    agent_observations=agent_observations,
                    targets=targets,
                )
                self._write_detection_raw_output(step_index, decoded)
                return detections
            except MLLMProviderCreditError as exc:
                exc.step_index = int(step_index)
                self.semantic_raw_output_index = step_index + 1
                raise
            except Exception as exc:
                last_error = exc
                self._write_detection_attempt_error_raw_output(
                    step_index=step_index,
                    attempt_index=attempt_index,
                    decoded=decoded if decoded is not None else str(exc),
                )
                if attempt_index >= max_validation_retries:
                    self.semantic_raw_output_index = step_index + 1
                    raise MLLMRetryExhaustedError(
                        stage="detection",
                        step_index=step_index,
                        attempts=max_validation_retries + 1,
                        last_error=last_error,
                    ) from exc
                print(
                    "Detection output validation failed on attempt %s of %s: %s"
                    % (
                        attempt_index + 1,
                        max_validation_retries + 1,
                        str(last_error),
                    )
                )

        raise RuntimeError("Unexpected detection retry loop exit.")

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
                region_id = int(node["id"])
                graph_region_label_by_id_for_prompt[region_id] = str(
                    node.get("label", "")
                ).strip()
                for viewpoint_id_raw in node.get("assigned_viewpoint_ids", []) or []:
                    graph_viewpoint_to_region_for_prompt.setdefault(
                        int(viewpoint_id_raw), region_id
                    )

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
                    "prior_raw_target_probs": dict(
                        node.get("raw_target_probs", {}) or {}
                    ),
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

        current_viewpoint_ids_without_prior_region_for_prompt = sorted(
            viewpoint_id
            for viewpoint_id in current_viewpoint_ids_for_prompt
            if viewpoint_id not in graph_viewpoint_to_region_for_prompt
        )

        assignment_required_viewpoint_ids_for_prompt = sorted(
            set(new_visible_neighbor_assignment_viewpoint_ids_for_prompt)
            | set(current_viewpoint_ids_without_prior_region_for_prompt)
        )

        assignment_not_required_current_step_viewpoint_ids_for_prompt = sorted(
            set(current_step_allowed_viewpoint_ids)
            - set(assignment_required_viewpoint_ids_for_prompt)
        )

        visible_neighbor_viewpoint_ids_for_prompt = (
            visible_viewpoint_ids_for_prompt - current_viewpoint_ids_for_prompt
        )

        detection_fixed_viewpoint_ids_for_prompt = set(current_viewpoint_ids_for_prompt)
        for viewpoint_id, status in graph_viewpoint_status_by_id_for_prompt.items():
            if (
                bool(status.get("prior_grounded", False))
                or int(status.get("prior_visit_times", 0)) > 0
            ):
                detection_fixed_viewpoint_ids_for_prompt.add(viewpoint_id)

        mllm_updatable_viewpoint_ids_for_prompt = sorted(
            (graph_viewpoint_node_ids_for_prompt | visible_viewpoint_ids_for_prompt)
            - detection_fixed_viewpoint_ids_for_prompt
        )

        mllm_updatable_viewpoint_context_for_prompt = []
        for viewpoint_id in mllm_updatable_viewpoint_ids_for_prompt:
            status = graph_viewpoint_status_by_id_for_prompt.get(viewpoint_id, {})
            prior_raw_target_probs = status.get("prior_raw_target_probs") or {}
            mllm_updatable_viewpoint_context_for_prompt.append(
                {
                    "id": viewpoint_id,
                    "has_prior_raw_target_probs": all(
                        target_id in prior_raw_target_probs for target_id in target_ids
                    ),
                    "prior_raw_target_probs": {
                        target_id: float(
                            prior_raw_target_probs.get(
                                target_id,
                                0.0,
                            )
                        )
                        for target_id in target_ids
                    },
                }
            )

        required_viewpoint_target_probs_skeleton = [
            {"id": viewpoint_id}
            for viewpoint_id in mllm_updatable_viewpoint_ids_for_prompt
        ]

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
        example_target_probs_shape = {
            target_id: "<score in [0, 1] justified by evidence>"
            for target_id in target_ids
        }
        example_viewpoint_target_scores_shape = {
            target_id: {
                "raw_score": "<nonnegative raw score justified by evidence>",
                "evidence_strength": "<low|medium|high>",
                "basis": "<short clue explaining why raw_score follows from target text and visual/graph context>",
            }
            for target_id in target_ids
        }
        example_region_target_scores_shape = {
            target_id: "<nonnegative raw score justified by region-level evidence>"
            for target_id in target_ids
        }
        schema = {
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
                    "target_probs": example_target_probs_shape,
                },
                {
                    "id": example_adjacent_region_id,
                    "label": "adjacent hallway visible through doorway",
                    "exist_prob": 0.7,
                    "target_probs": example_target_probs_shape,
                },
            ],
            "invisible_region_nodes": [
                {
                    "id": example_invisible_region_id,
                    "label": "unseen hallway area beyond closed doorway",
                    "exist_prob": 0.6,
                    "target_probs": example_target_probs_shape,
                }
            ],
            "viewpoint_target_scores": [
                {
                    "id": example_visible_viewpoint_id,
                    "target_scores": example_viewpoint_target_scores_shape,
                },
            ],
            "region_target_scores": [
                {
                    "id": example_invisible_region_id,
                    "target_scores": example_region_target_scores_shape,
                }
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
                node.pop("target_probs", None)
                if int(node["id"]) in current_viewpoint_ids_for_prompt:
                    node.pop("raw_target_probs", None)
            else:
                node.pop("target_probs", None)
                if node.get("assigned_viewpoint_ids"):
                    node.pop("raw_target_probs", None)

        system_message = dedent("""
            You are an indoor hypothesis-graph proposal module for cooperative many-agent, many-target navigation. Analyze one annotated RGB panorama per agent and the compact shared graph summary. Propose an uncertain graph update for downstream optimization. Do not select robot actions or produce a final map.

            The graph has viewpoint nodes for executable robot poses and region nodes for semantic zones. Use the provided agent ids, active target_ids, and viewpoint ids exactly. Reuse provided region ids exactly when a matching region already exists. For newly proposed regions, assign new integer region ids that do not conflict with existing ids. Use active target_id in target_probs for newly proposed regions and every MLLM-updatable viewpoint id listed in the user message. Current viewpoint target probabilities are fixed from the previous detection step and must not be inferred. Found targets are complete and must not appear in target_probs or existence hypotheses.

            Return exactly one valid JSON object matching the user schema. Do not output markdown, code fences, comments, text outside JSON, extra top-level keys, trailing commas, or non-JSON booleans.

            Required top-level keys:
            current_viewpoints_reassignment, visible_region_nodes, invisible_region_nodes, viewpoint_target_scores, region_target_scores, viewpoint_node_assigns, new_edges, edge_distance_variances.

            Core rules:
            - The per-agent observation context is the source of truth for current agent locations, even if the compact graph summary has older node status values.
            - In each panorama, the current viewpoint means the camera location that generated the panorama. It is not drawn as a red numbered marker.
            - Red numbered markers are non-current visible neighboring viewpoints only.
            - Do not infer the current viewpoint's region from a red numbered marker. Red numbered markers should be used only for assigning non-current visible neighboring viewpoints.
            - For each current viewpoint with a prior_assigned_region_id in the per-agent observation context, compare prior_assigned_region_label against the visual evidence around the panorama camera location, not around a red numbered marker. The prior assignment is a semantic hypothesis from earlier steps, not ground truth.
            - If the prior region assignment still matches the current panorama, keep the original region assignment and do not include that viewpoint in current_viewpoints_reassignment.
            - If the prior region assignment does not match the current panorama, assign the current viewpoint to the region that best matches the current observation and include exactly one item in current_viewpoints_reassignment.
            - current_viewpoints_reassignment must contain only true region changes for current viewpoints. Return [] when no current viewpoint requires reassignment.
            - For each current_viewpoints_reassignment item, new_assigned_region_id must equal the final region used for that current viewpoint. If the reassigned current viewpoint appears in viewpoint_node_assigns, it must also match there.
            - If a current viewpoint appears in viewpoint_node_assigns, that assigned region is its final region. current_viewpoints_reassignment for that same viewpoint must match the viewpoint_node_assigns region exactly, or be omitted when the final region equals the prior graph_summary assignment.
            - Never assign the same current viewpoint to one region in viewpoint_node_assigns and a different region in current_viewpoints_reassignment.
            - If new_assigned_region_id is a newly proposed region, include the complete region node record in visible_region_nodes.
            - visible_region_nodes include only newly proposed visible regions: current regions or adjacent areas that are visually observable in current panoramas and are absent from the compact shared graph summary. Existing graph regions should be referenced by id, not re-emitted.
            - Before creating a new visible_region_node, compare it with existing visible_region_nodes and graph-summary region nodes. If the same physical area is already represented, reuse that existing region id and label. Do not create two region nodes for the same hallway, corridor, bathroom, bedroom, or room only because the wording is slightly different across panoramas.
            - invisible_region_nodes include only completely unseen regions inferred from layout cues. If any part of a region is visible, it is not invisible.
            - Do not assign viewpoints to invisible_region_nodes. A region with assigned viewpoints must be in visible_region_nodes.
            - A region id must appear in only one of visible_region_nodes or invisible_region_nodes.
            - Region labels must be room or area labels, not object names. Include appearance cue, area type, and physical relative location cue. Do not mention agent ids or names. Avoid generic labels unless they include both appearance and relative location cues.
            - Detections are handled by a separate detection step outside this graph MLLM call. Do not output detections.
            - Newly proposed region exist_prob is the initial semantic-zone existence hypothesis used while the region remains ungrounded. Newly proposed region target_probs must contain every active target_id with values in [0, 1]. These are initial raw region target scores for regions with no final assigned viewpoints.
            - region_target_scores is incremental for semantic regions with no final assigned viewpoints. Include only region-target raw scores that should change, except a region that loses all assigned viewpoints in this step must include every active target_id.
            - Do not include region_target_scores for any region that has final assigned viewpoints. Its raw region target score is computed locally as the mean of target_probs over assigned viewpoints.
            - viewpoint_target_scores is incremental. Include only MLLM-updatable viewpoint-target values whose raw hypothesis score should change because of the current observations.
            - Each viewpoint_target_scores target entry must contain raw_score, evidence_strength, and basis. evidence_strength must be exactly low, medium, or high.
            - Returned raw_score values are raw nonnegative scores; they do not need to sum to 1 because the validator materializes unchanged prior raw scores, repairs any raw_score/evidence_strength order mismatch, and then normalizes per target.
            - Before assigning target scores, parse each active target description into object identity, visible attributes, support surfaces, nearby objects, room or area cues, and relative-location cues. These constraints must come from the target text, not from fixed object-room mappings.
            - Use active target descriptions to make target-specific scores when evidence differs. Equal scores are allowed only when the evidence records are substantively indistinguishable.
            - viewpoint_target_scores must exclude current agent viewpoints and any viewpoint that has already been grounded or visited as a current viewpoint. These viewpoints are fixed by direct detection: if an unfound target was not detected there, its target probability at that viewpoint is 0 forever.
            - viewpoint_node_assigns must use region_node_id and assigned_viewpoint_node_indices. It is incremental and must include exactly the viewpoint ids requiring region assignment in this step. This set includes new visible neighboring viewpoints and first-reached current viewpoints. Do not include other current-step viewpoints. Other current-step viewpoints keep their previous graph_summary assignment unless a current viewpoint is explicitly listed in current_viewpoints_reassignment.
            - For non-current visible neighboring viewpoints, use prior_assigned_region_id only as historical context, not as a fixed assignment.
            - Assign each non-current visible neighboring viewpoint by jointly considering its marker location in the panorama, xy-based floor-plan distance from current_xy, visible_viewpoints[].distance, and whether a clear spatial boundary separates it from the current viewpoint.
            - If a non-current visible neighboring viewpoint is close to the current viewpoint and no doorway, wall, corridor boundary, room boundary, or transition area separates them, prefer the current viewpoint's final region.
            - If a non-current visible neighboring viewpoint is farther away, or if its marker is across a clear spatial boundary, assign it to the semantic region that physically contains its marker.
            - Do not assign a non-current visible neighboring viewpoint to an adjacent area only because that area is visible in the panorama. Assign it to that adjacent area only when its red marker lies inside that area, or when distance and spatial context strongly support that assignment.
            - new_edges may contain only VV or VZ edges. Never use region-region edges. Do not add edges between a current viewpoint and its visible neighboring viewpoints, because those local edges are already provided by the navigation system. Do not add an edge between a viewpoint and its assigned region.
            - For every new_edges item, exist_prob is the edge-existence probability conditioned on the existence of both endpoint nodes.
            - A VV edge may be proposed only between two viewpoint nodes that satisfy all of the following conditions: both are non-current viewpoints and both are marked as unvisited according to the compact shared graph summary. The MLLM may hypothesize a direct local connection when it is spatially plausible and appears directly traversable from the current panoramas and graph context. The evidence does not need to be certain, but the proposed connection should not cross an apparent obstacle, large furniture, wall, blocked passage, closed partition, or other visible barrier. Two viewpoints being visible from the same current viewpoint, or belonging to the same semantic region, is not sufficient by itself. Use lower conditional exist_prob when the support is weak but the local connection still appears passable. If visit-state information is unavailable for a candidate viewpoint, treat the candidate as not eligible for a new VV edge unless the user message explicitly identifies it as unvisited.
            - A VZ edge connects a viewpoint to a semantic region with no assigned viewpoints. The region may be visible or invisible. Do not add a VZ edge to a region with assigned viewpoints or between a viewpoint and its assigned region.
            - If a viewpoint is listed under a region in viewpoint_node_assigns, do not create a VZ edge between that viewpoint and that region. The assignment already represents the viewpoint-region relation.
            - Do not merge multiple rooms or areas into one region label. A region must describe one spatially coherent area only.
            - If a panorama shows multiple areas separated by a doorway, wall, large opening, or clear boundary, represent them as separate region nodes when they contain current or visible viewpoints.
            - Each current viewpoint's final region must describe the area physically containing the panorama camera location, not every area visible from that viewpoint.
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
                - If a current viewpoint appears in viewpoint_node_assigns, that assigned region is its final region. current_viewpoints_reassignment for that same viewpoint must match that region exactly, or be omitted when it is not a true change from graph_summary.viewpoint_to_region.
                - Never assign a current viewpoint to region A in viewpoint_node_assigns and region B in current_viewpoints_reassignment.
                - viewpoint_target_scores is optional and incremental for the MLLM-updatable viewpoint ids below.
                - region_target_scores is optional and incremental for existing or newly proposed regions with no final assigned viewpoints.
                - Do not include current, grounded, or previously visited viewpoint ids in viewpoint_target_scores. Their target probabilities are detection-fixed at 0 for unfound targets.
                - Existing non-current graph viewpoint ids keep prior_raw_target_probs unless current observations justify changing a specific viewpoint-target value.
                - Do not include any other viewpoint id in viewpoint_node_assigns or viewpoint_target_scores, even if that id appears in compact shared graph summary, region assigned_viewpoint_ids, or viewpoint_to_region.
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
                - current agent viewpoints with no prior graph_summary.viewpoint_to_region assignment.

                Current-step viewpoint ids not requiring region assignment in this step:
                {assignment_not_required_current_step_viewpoint_ids_json}
                
                MLLM-updatable viewpoint target-probability context:
                {mllm_updatable_viewpoint_context_json}

                Eligible viewpoint_target_scores update ids:
                {required_viewpoint_target_probs_skeleton_json}

                Viewpoint target probability rule:
                - You may output viewpoint_target_scores items only for ids in this list.
                - Omit an id or target_id when its prior_raw_target_probs value should remain unchanged.
                - For an eligible viewpoint where has_prior_raw_target_probs is false, output all active target_ids for that viewpoint.
                - Score the target likelihood at the candidate viewpoint, not only at the current camera location.
                - For each candidate viewpoint, use its red marker location when visible, nearby visible objects, assigned semantic region, xy distance, visible_viewpoints[].distance, prior_raw_target_probs, and compact graph summary.
                - Compare eligible viewpoint ids against each other for each active target_id before assigning changed scores.
                - Use meaningful nonnegative raw scores.
                - Avoid uniform scores unless the visual evidence and graph context are truly indistinguishable.
                - Do not include current, grounded, or previously visited viewpoint ids.

                Viewpoint target score-basis rule:
                - Each returned viewpoint-target score must be an object with exactly raw_score, evidence_strength, and basis.
                - evidence_strength must be exactly one of: low, medium, high.
                - For each target, derive the relevant object identity, visual attributes, support surfaces, nearby objects, room or area cues, and relative-location cues from the active target description.
                - For each returned viewpoint-target pair, fill basis with one short clue explaining why raw_score and evidence_strength follow from the target text, visible evidence, red-marker location, assigned semantic region, spatial context, and graph history.
                - basis must be a non-empty string.
                - Do not use fixed object-room associations or hardcoded target-specific mappings. Only use constraints implied by the active target text and current graph/visual evidence.
                
                Target probability rule:
                - viewpoint_target_scores raw_score values are raw target-location scores, not calibrated probabilities. The validator stores the repaired materialized values as raw_target_probs and normalizes target_probs per target across eligible viewpoint ids.
                - Region target_scores values are raw target-location scores for type-(2) regions: semantic regions with no final assigned viewpoints. The validator stores the materialized raw values as raw_target_probs.
                - Type-(1) regions, meaning regions with any final assigned viewpoints, compute raw region target scores locally as the mean of normalized target_probs over assigned viewpoints.
                - Region target_probs are normalized per target across the union of type-(1) and type-(2) regions.
                - Existing type-(2) regions keep prior raw_target_probs unless region_target_scores changes a value. Newly proposed type-(2) regions use their region target_probs as initial raw scores unless region_target_scores overrides them.
                - If a region loses all assigned viewpoints in this step and becomes type-(2), provide region_target_scores for every active target_id.
                - Do not copy default values from the schema or examples.
                - For each active target_id, compare all type-(2) regions and all eligible non-current viewpoint ids before assigning changed scores.
                - Assign higher scores to locations whose visible objects, room or area evidence, furniture, spatial context, and graph history better satisfy the constraints inferred from that active target description.
                - Do not repeatedly use default values such as 0.01, 0.05, 0.1, or 0.2.
                - Use different scores when evidence differs.
                - Equal scores are allowed only when the basis, assigned region, spatial context, and graph history are substantively indistinguishable.
                - For each active target_id, the sum of materialized raw scores across eligible viewpoint ids must be positive.
                - For each active target_id, the sum of materialized raw scores across all regions must be positive.
                
                All non-current visible neighboring viewpoint ids:
                {visible_neighbor_viewpoint_ids_json}

                Current-step interpretation note:
                - The observation context is the source of truth for current agent locations.
                - If a current viewpoint already appears in the graph summary, still treat it as current and grounded for this step.
                - If a current viewpoint has prior_assigned_region_id and prior_assigned_region_label in the observation context, treat them as earlier semantic hypotheses that must be checked against the current panorama.
                - If the selected physical region for the current viewpoint already appears in the graph summary, reuse that region id and label without re-emitting it in visible_region_nodes.
                
                Output shape example. It uses placeholder strings for score fields to avoid numeric templates. Return real numeric scores in the actual JSON.
                {schema_json}

                Current step request:
                - For each agent, treat the current viewpoint as the camera location that generated the panorama. The current viewpoint is not drawn as a red numbered marker.
                - Decide which semantic region encloses the panorama camera location.
                - Red numbered markers are non-current visible neighboring viewpoints only.
                - Do not assign a current viewpoint to a region only because a red neighboring marker appears inside that region.
                - Do not assign a current viewpoint to a region only because that region is visible nearby, through a doorway, or at the side of the panorama.
                - If a current viewpoint has prior_assigned_region_id, compare the prior_assigned_region_label with the local visual evidence around the panorama camera location.
                - If the prior region label does not match the local area around the panorama camera location, reassign the current viewpoint to the best matching existing visible region when possible.
                - If no existing region matches the local area around the panorama camera location, create a new visible_region_node.
                - Express final current-viewpoint regions only through viewpoint_node_assigns for current viewpoints requiring assignment, current_viewpoints_reassignment for changed prior assignments, or the existing graph_summary.viewpoint_to_region for unchanged prior assignments.
                - If a current viewpoint is reassigned, update current_viewpoints_reassignment consistently. Only include the current viewpoint in viewpoint_node_assigns if it is listed under Viewpoint ids requiring region assignment in this step.
                - After choosing the final region for each current viewpoint, assign each non-current visible neighboring viewpoint by jointly considering its red marker location, its xy-based floor-plan distance from current_xy, its visible_viewpoints[].distance value, and whether a clear spatial boundary separates it from the current viewpoint.
                - Use prior_assigned_region_id and graph_summary.viewpoint_to_region only as historical context for non-current visible neighboring viewpoints, not as fixed assignments.
                - If a non-current visible neighboring viewpoint is close to the current viewpoint and no doorway, wall, corridor boundary, room boundary, or transition area separates them, prefer the current viewpoint's final region.
                - If a non-current visible neighboring viewpoint is farther away, or if its red marker is across a clear spatial boundary, assign it to the semantic region that physically contains that red marker.
                - Do not assign a non-current visible neighboring viewpoint to an adjacent area only because that area is visible in the panorama. Assign it to that adjacent area only when its red marker lies inside that area, or when distance and spatial context strongly support that assignment.
                - Propose invisible_region_nodes only for completely unseen areas inferred from layout cues.
                - Treat partially visible adjacent areas as visible_region_nodes, not invisible_region_nodes.
                - Propose only legal VV and VZ edges using the new_edges rules in Core rules.
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
                mllm_updatable_viewpoint_context_json=json.dumps(
                    mllm_updatable_viewpoint_context_for_prompt,
                    indent=2,
                    sort_keys=True,
                ),
                required_viewpoint_target_probs_skeleton_json=json.dumps(
                    required_viewpoint_target_probs_skeleton, indent=2, sort_keys=True
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

        # Run detection before graph generation so found targets can be completed
        # and removed from the graph MLLM request.
        localized_detections = self._detect_targets(
            agent_observations=agent_observations,
            targets=active_detection_targets,
            image_content=image_content,
            step_index=step_index,
        )
        # print the detect model name
        print("Detection model used: %s" % self.detection_model_name)
        self.last_direct_detections = localized_detections
        newly_found_targets_by_id = self._found_targets_from_detections(
            localized_detections,
            agent_observations,
        )

        if len(newly_found_targets_by_id) > 0:
            print()
            print("Target finding status:")
            for target in active_detection_targets:
                target_id = str(target["target_id"])
                if target_id in newly_found_targets_by_id:
                    print(
                        "Target %s found at step %s with detections: %s"
                        % (target_id, step_index, newly_found_targets_by_id[target_id])
                    )
            print()

        if step_index >= 25:
            debugpy.breakpoint()

        # debugpy.breakpoint()

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

        # Graph generation should focus on remaining unfound targets only.
        graph_targets = [
            target
            for target in active_detection_targets
            if str(target["target_id"]) not in set(newly_found_targets_by_id)
        ]

        if not graph_targets:
            self.semantic_raw_output_index = step_index + 1
            return None

        system_message, user_message = self._build_instruction(
            agent_observations=agent_observations,
            targets=graph_targets,
            graph_summary=graph_summary,
        )

        max_validation_retries = getattr(self, "max_validation_retries", 0)
        validation_errors: List[object] = []

        # read local raw output if enabled, otherwise request MLLM completion directly
        if getattr(self, "read_saved_raw_outputs", False):
            decoded = self._read_semantic_raw_output(step_index)
            if decoded is not None:
                print(f"Reading saved raw output for step {step_index}")
                payload, repair_messages = self._decode_saved_semantic_payload(
                    decoded=decoded,
                    agent_observations=agent_observations,
                    targets=graph_targets,
                    graph_summary=graph_summary,
                    scorer=scorer,
                )
                if repair_messages:
                    print("Saved graph MLLM payload repair applied:")
                    for repair_message in repair_messages:
                        print("  - %s" % repair_message)

                self._write_semantic_raw_output(
                    step_index,
                    json.dumps(payload, indent=2, sort_keys=True),
                )
                self.semantic_raw_output_index = step_index + 1
                self._write_user_message(step_index, user_message)
                return payload
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
            max_request_timeout_retries = getattr(
                self, "max_request_timeout_retries", 0
            )
            decoded = None
            for timeout_attempt_index in range(max_request_timeout_retries + 1):
                request_start_time = time.time()
                try:
                    decoded = self._request_completion(
                        messages=messages,
                        model_name=getattr(self, "graph_model_name", ""),
                        request_type="graph",
                        thinking_mode=graph_thinking,
                    )
                except MLLMProviderCreditError as exc:
                    exc.step_index = int(step_index)
                    self.semantic_raw_output_index = step_index + 1
                    raise
                except APITimeoutError:
                    if timeout_attempt_index >= max_request_timeout_retries:
                        raise
                    print(
                        "Graph MLLM completion request for step %s attempt %s "
                        "timed out after %.2f seconds. Retrying timeout request "
                        "%s of %s."
                        % (
                            step_index,
                            attempt_index + 1,
                            time.time() - request_start_time,
                            timeout_attempt_index + 1,
                            max_request_timeout_retries,
                        )
                    )
                    continue

                print(
                    "MLLM completion request for step %s attempt %s took %.2f seconds"
                    % (
                        step_index,
                        attempt_index + 1,
                        time.time() - request_start_time,
                    )
                )
                break

            try:
                raw = self._strip_code_fences(decoded)
                payload = self._parse_json_strict(raw)
                repair_messages = self._repair_graph_mllm_payload(
                    payload=payload,
                    agent_observations=agent_observations,
                    targets=graph_targets,
                    graph_summary=graph_summary,
                )

                payload = self._validate_payload(
                    payload=payload,
                    agent_observations=agent_observations,
                    targets=graph_targets,
                    graph_summary=graph_summary,
                    scorer=scorer,
                    semantic_payload_contract="graph_mllm",
                )

                if repair_messages:
                    print("Graph MLLM payload repair applied:")
                    for repair_message in repair_messages:
                        print("  - %s" % repair_message)

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
                validation_errors.append(exc)
                self._write_semantic_attempt_error_raw_output(
                    step_index=step_index,
                    attempt_index=attempt_index,
                    decoded=decoded,
                )

                if attempt_index >= max_validation_retries:
                    self.semantic_raw_output_index = step_index + 1
                    raise MLLMRetryExhaustedError(
                        stage="graph",
                        step_index=step_index,
                        attempts=max_validation_retries + 1,
                        last_error=last_error,
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

    def _write_detection_attempt_error_raw_output(
        self, step_index: int, attempt_index: int, decoded: str
    ) -> None:
        raw_output_dir = getattr(self, "raw_output_dir", "mllm_raw_outputs")
        os.makedirs(raw_output_dir, exist_ok=True)

        with open(
            self._detection_attempt_error_raw_output_path(step_index, attempt_index),
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
    ) -> bytes:
        """Resize and JPEG-compress a panorama image.

        The returned value is JPEG bytes, not a NumPy array.
        """
        if image.dtype != np.uint8:
            image = image.astype(np.uint8)

        pil_image = Image.fromarray(image).convert("RGB")

        if pil_image.width > panorama_max_width_for_prompt:
            new_height = int(
                pil_image.height * panorama_max_width_for_prompt / pil_image.width
            )
            pil_image = pil_image.resize(
                (panorama_max_width_for_prompt, new_height),
                Image.Resampling.LANCZOS,
            )

        buffer = io.BytesIO()
        pil_image.save(
            buffer,
            format="JPEG",
            quality=100,
            optimize=True,
        )

        return buffer.getvalue()

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

    def _repair_graph_mllm_payload(
        self,
        payload: Dict[str, object],
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        graph_summary: Optional[Dict[str, object]] = None,
    ) -> List[str]:
        """Repair deterministic graph-MLLM bookkeeping mistakes in-place."""
        required_top_level_keys = {
            "current_viewpoints_reassignment",
            "visible_region_nodes",
            "invisible_region_nodes",
            "viewpoint_node_assigns",
            "new_edges",
            "edge_distance_variances",
        }

        if not isinstance(payload, dict):
            return []
        if not required_top_level_keys.issubset(payload):
            return []
        if not (
            "viewpoint_target_scores" in payload
            or (
                "viewpoint_target_probs" in payload
                and "viewpoint_target_score_basis" in payload
            )
        ):
            return []

        repairs = []
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
        graph_viewpoint_status_by_id = {}

        if isinstance(graph_summary, dict):
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

                node_id = int(node["id"])
                node_type = node.get("type")

                if node_type == "viewpoint":
                    graph_viewpoint_node_ids.add(node_id)
                    graph_viewpoint_status_by_id[node_id] = {
                        "prior_grounded": bool(node.get("grounded", 0)),
                        "prior_visit_times": int(node.get("node_visit_times", 0)),
                    }

                elif node_type == "region":
                    graph_region_records[node_id] = node
                    for viewpoint_id_raw in (
                        node.get("assigned_viewpoint_ids", []) or []
                    ):
                        graph_viewpoint_to_region.setdefault(
                            int(viewpoint_id_raw), node_id
                        )

        current_viewpoint_ids_without_prior_region = {
            viewpoint_id
            for viewpoint_id in current_viewpoint_ids
            if viewpoint_id not in graph_viewpoint_to_region
        }

        assignment_required_viewpoint_ids = (
            visible_viewpoint_ids - current_viewpoint_ids - graph_viewpoint_node_ids
        ) | current_viewpoint_ids_without_prior_region

        visible_region_nodes = payload["visible_region_nodes"]
        invisible_region_nodes = payload["invisible_region_nodes"]
        viewpoint_node_assigns = payload["viewpoint_node_assigns"]
        current_viewpoints_reassignment = payload["current_viewpoints_reassignment"]
        new_edges = payload["new_edges"]

        if not isinstance(visible_region_nodes, list):
            return repairs
        if not isinstance(invisible_region_nodes, list):
            return repairs
        if not isinstance(viewpoint_node_assigns, list):
            return repairs
        if not isinstance(current_viewpoints_reassignment, list):
            return repairs
        if not isinstance(new_edges, list):
            return repairs

        def region_ids_from(region_nodes: List[object]) -> set:
            region_ids = set()
            for region in region_nodes:
                if isinstance(region, dict) and "id" in region:
                    region_ids.add(int(region["id"]))
            return region_ids

        def materialize_graph_region(region_id: int) -> None:
            if region_id in graph_region_records:
                return

            visible_region_ids = region_ids_from(visible_region_nodes)
            invisible_region_ids = region_ids_from(invisible_region_nodes)

            if region_id in visible_region_ids:
                return

            if region_id in invisible_region_ids:
                for index, region in enumerate(list(invisible_region_nodes)):
                    if isinstance(region, dict) and int(region["id"]) == region_id:
                        visible_region_nodes.append(invisible_region_nodes.pop(index))
                        repairs.append(
                            "moved region %s from invisible to visible" % region_id
                        )
                        return

        assignment_candidates_by_viewpoint = {}
        assignment_regions_with_model_viewpoints = set()

        for item in viewpoint_node_assigns:
            if not isinstance(item, dict):
                continue
            if set(item) != {"region_node_id", "assigned_viewpoint_node_indices"}:
                continue

            region_id = int(item["region_node_id"])
            assigned_ids = item["assigned_viewpoint_node_indices"]
            if not isinstance(assigned_ids, list):
                continue

            for viewpoint_id_raw in assigned_ids:
                viewpoint_id = int(viewpoint_id_raw)
                if viewpoint_id in assignment_candidates_by_viewpoint:
                    continue

                assignment_candidates_by_viewpoint[viewpoint_id] = region_id
                assignment_regions_with_model_viewpoints.add(region_id)

        reassignment_by_viewpoint = {}
        for item in current_viewpoints_reassignment:
            if not isinstance(item, dict):
                continue
            if set(item) != {"viewpoint_id", "new_assigned_region_id"}:
                continue

            viewpoint_id = int(item["viewpoint_id"])
            new_region_id = int(item["new_assigned_region_id"])
            old_region_id = graph_viewpoint_to_region.get(viewpoint_id)

            if viewpoint_id not in current_viewpoint_ids:
                continue
            if old_region_id is not None and new_region_id == old_region_id:
                repairs.append(
                    "removed no-op current viewpoint reassignment for %s" % viewpoint_id
                )
                continue

            reassignment_by_viewpoint[viewpoint_id] = new_region_id
            materialize_graph_region(new_region_id)

        for viewpoint_id, region_id in sorted(
            assignment_candidates_by_viewpoint.items()
        ):
            if viewpoint_id not in current_viewpoint_ids:
                continue
            if viewpoint_id not in assignment_required_viewpoint_ids:
                continue
            if viewpoint_id not in reassignment_by_viewpoint:
                continue

            old_region_id = graph_viewpoint_to_region.get(viewpoint_id)
            if old_region_id is not None and region_id != old_region_id:
                if reassignment_by_viewpoint[viewpoint_id] != region_id:
                    reassignment_by_viewpoint[viewpoint_id] = region_id
                    repairs.append(
                        "aligned current viewpoint reassignment for %s to required assignment"
                        % viewpoint_id
                    )
                materialize_graph_region(region_id)
            else:
                del reassignment_by_viewpoint[viewpoint_id]
                repairs.append(
                    "removed contradictory current viewpoint reassignment for %s"
                    % viewpoint_id
                )

        removable_assignment_viewpoint_ids = set()
        for viewpoint_id, region_id in sorted(
            assignment_candidates_by_viewpoint.items()
        ):
            if viewpoint_id in assignment_required_viewpoint_ids:
                continue

            if viewpoint_id in current_viewpoint_ids:
                old_region_id = graph_viewpoint_to_region.get(viewpoint_id)
                if old_region_id is not None and region_id != old_region_id:
                    if viewpoint_id not in reassignment_by_viewpoint:
                        reassignment_by_viewpoint[viewpoint_id] = region_id
                        repairs.append(
                            "converted current viewpoint assignment for %s to reassignment"
                            % viewpoint_id
                        )
                    materialize_graph_region(region_id)
                    removable_assignment_viewpoint_ids.add(viewpoint_id)
                elif old_region_id is not None and region_id == old_region_id:
                    repairs.append(
                        "removed non-required old viewpoint assignment for %s"
                        % viewpoint_id
                    )
                    removable_assignment_viewpoint_ids.add(viewpoint_id)

            elif viewpoint_id in graph_viewpoint_to_region:
                repairs.append(
                    "removed non-required old viewpoint assignment for %s"
                    % viewpoint_id
                )
                removable_assignment_viewpoint_ids.add(viewpoint_id)

        for viewpoint_id, region_id in sorted(
            assignment_candidates_by_viewpoint.items()
        ):
            if viewpoint_id not in current_viewpoint_ids:
                continue

            old_region_id = graph_viewpoint_to_region.get(viewpoint_id)
            if old_region_id is None or region_id == old_region_id:
                continue
            if (
                viewpoint_id in reassignment_by_viewpoint
                and reassignment_by_viewpoint[viewpoint_id] != region_id
            ):
                reassignment_by_viewpoint[viewpoint_id] = region_id
                repairs.append(
                    "aligned current viewpoint reassignment for %s to required assignment"
                    % viewpoint_id
                )

            if viewpoint_id not in reassignment_by_viewpoint:
                reassignment_by_viewpoint[viewpoint_id] = region_id
                repairs.append(
                    "synthesized current viewpoint reassignment for %s" % viewpoint_id
                )
            materialize_graph_region(region_id)

        for region_id in sorted(assignment_regions_with_model_viewpoints):
            visible_region_ids = region_ids_from(visible_region_nodes)
            invisible_region_ids = region_ids_from(invisible_region_nodes)
            if region_id in invisible_region_ids or region_id in graph_region_records:
                materialize_graph_region(region_id)

        cleaned_assignments_by_region = {}
        repaired_viewpoint_node_assigns = []
        for item in viewpoint_node_assigns:
            if not isinstance(item, dict):
                repaired_viewpoint_node_assigns.append(item)
                continue
            if set(item) != {"region_node_id", "assigned_viewpoint_node_indices"}:
                repaired_viewpoint_node_assigns.append(item)
                continue

            region_id = int(item["region_node_id"])
            assigned_ids = item["assigned_viewpoint_node_indices"]
            if not isinstance(assigned_ids, list):
                repaired_viewpoint_node_assigns.append(item)
                continue

            repaired_assigned_ids = [
                int(viewpoint_id)
                for viewpoint_id in assigned_ids
                if int(viewpoint_id) not in removable_assignment_viewpoint_ids
            ]
            if not repaired_assigned_ids:
                continue

            repaired_viewpoint_node_assigns.append(
                {
                    "region_node_id": region_id,
                    "assigned_viewpoint_node_indices": repaired_assigned_ids,
                }
            )

            for viewpoint_id in repaired_assigned_ids:
                if viewpoint_id in assignment_required_viewpoint_ids:
                    cleaned_assignments_by_region.setdefault(region_id, set()).add(
                        viewpoint_id
                    )

        payload["current_viewpoints_reassignment"] = [
            {
                "viewpoint_id": viewpoint_id,
                "new_assigned_region_id": region_id,
            }
            for viewpoint_id, region_id in sorted(reassignment_by_viewpoint.items())
        ]
        payload["viewpoint_node_assigns"] = repaired_viewpoint_node_assigns

        visible_region_ids = region_ids_from(visible_region_nodes)
        invisible_region_ids = region_ids_from(invisible_region_nodes)
        all_region_ids = visible_region_ids | invisible_region_ids

        final_viewpoint_to_region = dict(graph_viewpoint_to_region)
        for region_id, viewpoint_ids in cleaned_assignments_by_region.items():
            for viewpoint_id in viewpoint_ids:
                final_viewpoint_to_region[viewpoint_id] = region_id
        for viewpoint_id, region_id in reassignment_by_viewpoint.items():
            final_viewpoint_to_region[viewpoint_id] = region_id

        region_to_all_assigned_viewpoints = {}
        for viewpoint_id, region_id in final_viewpoint_to_region.items():
            region_to_all_assigned_viewpoints.setdefault(region_id, set()).add(
                viewpoint_id
            )

        region_start_id = int(len(Helper.viewpoint_vp_label_by_index))
        cleaned_new_edges = []
        dropped_edges = 0

        for edge in new_edges:
            keep_edge = True
            if not isinstance(edge, dict):
                keep_edge = False
            elif set(edge) != {"i", "j", "edge_type", "exist_prob", "dist"}:
                keep_edge = False
            else:
                i = int(edge["i"])
                j = int(edge["j"])
                edge_type = str(edge["edge_type"])

                i_is_viewpoint = i in all_current_step_viewpoint_ids
                j_is_viewpoint = j in all_current_step_viewpoint_ids
                i_is_region = i in all_region_ids
                j_is_region = j in all_region_ids

                if i == j or edge_type not in {"VV", "VZ"}:
                    keep_edge = False
                elif edge_type == "VV":
                    i_status = graph_viewpoint_status_by_id.get(i)
                    j_status = graph_viewpoint_status_by_id.get(j)
                    keep_edge = (
                        i_is_viewpoint
                        and j_is_viewpoint
                        and i not in current_viewpoint_ids
                        and j not in current_viewpoint_ids
                        and i_status is not None
                        and j_status is not None
                        and not bool(i_status.get("prior_grounded", False))
                        and not bool(j_status.get("prior_grounded", False))
                        and int(i_status.get("prior_visit_times", 0)) == 0
                        and int(j_status.get("prior_visit_times", 0)) == 0
                    )
                else:
                    endpoint_i_is_region_namespace = int(i) >= region_start_id
                    endpoint_j_is_region_namespace = int(j) >= region_start_id
                    if endpoint_i_is_region_namespace == endpoint_j_is_region_namespace:
                        keep_edge = False
                    else:
                        valid_vz = (i_is_viewpoint and j_is_region) or (
                            i_is_region and j_is_viewpoint
                        )
                        if not valid_vz:
                            keep_edge = False
                        else:
                            viewpoint_id = i if i_is_viewpoint else j
                            region_id = i if i_is_region else j
                            keep_edge = final_viewpoint_to_region.get(
                                viewpoint_id
                            ) != region_id and not region_to_all_assigned_viewpoints.get(
                                region_id
                            )

            if keep_edge:
                cleaned_new_edges.append(edge)
            else:
                dropped_edges += 1

        if dropped_edges:
            repairs.append("dropped %s illegal optional new_edges" % dropped_edges)
        payload["new_edges"] = cleaned_new_edges

        return repairs

    def _validate_payload(
        self,
        payload: Dict[str, object],
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        graph_summary: Optional[Dict[str, object]] = None,
        scorer=None,
        semantic_payload_contract: str = "graph_mllm",
    ) -> Dict[str, object]:
        try:
            return self._validate_payload_impl(
                payload=payload,
                agent_observations=agent_observations,
                targets=targets,
                graph_summary=graph_summary,
                scorer=scorer,
                semantic_payload_contract=semantic_payload_contract,
            )
        except SigLIPRegionValidationError:
            raise
        except GraphValidationError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise self._graph_validation_error_from_exception(
                exc=exc,
                payload=payload,
                agent_observations=agent_observations,
                targets=targets,
                graph_summary=graph_summary,
                semantic_payload_contract=semantic_payload_contract,
            ) from exc

    def _validate_payload_impl(
        self,
        payload: Dict[str, object],
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        graph_summary: Optional[Dict[str, object]] = None,
        scorer=None,
        semantic_payload_contract: str = "graph_mllm",
    ) -> Dict[str, object]:
        if semantic_payload_contract not in {"graph_mllm", "saved_materialized"}:
            raise ValueError(
                "Unknown semantic payload contract: %s" % semantic_payload_contract
            )

        common_top_level_keys = {
            "current_viewpoints_reassignment",
            "visible_region_nodes",
            "invisible_region_nodes",
            "viewpoint_node_assigns",
            "new_edges",
            "edge_distance_variances",
        }
        if semantic_payload_contract == "graph_mllm":
            required_top_level_keys = common_top_level_keys | {
                "region_target_scores",
                "viewpoint_target_scores",
            }
        else:
            required_top_level_keys = common_top_level_keys | {
                "viewpoint_target_probs",
                "viewpoint_target_score_basis",
            }

        if not isinstance(payload, dict):
            raise TypeError("payload must be a dictionary.")

        allowed_top_level_keys = set(required_top_level_keys)
        if semantic_payload_contract == "saved_materialized":
            allowed_top_level_keys.add("region_target_scores")

        extra_top_level_keys = set(payload).difference(allowed_top_level_keys)
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

        def validate_probability_or_zero(value, context: str) -> None:
            if not is_number(value):
                raise TypeError("%s must be numeric." % context)
            if not (0.0 <= float(value) <= 1.0):
                raise ValueError("%s=%s is outside [0, 1]." % (context, value))

        def validate_positive_number(value, context: str) -> None:
            if not is_number(value):
                raise TypeError("%s must be numeric." % context)
            if float(value) <= 0.0:
                raise ValueError("%s=%s must be positive." % (context, value))

        def validate_nonnegative_number(value, context: str) -> None:
            if not is_number(value):
                raise TypeError("%s must be numeric." % context)
            if float(value) < 0.0:
                raise ValueError("%s=%s must be nonnegative." % (context, value))

        def validate_nonempty_string(value, context: str) -> None:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("%s must be a nonempty string." % context)

        observation_by_agent = {
            str(observation["agent_id"]): observation
            for observation in agent_observations
        }
        target_ids = {str(target["target_id"]) for target in targets}
        ordered_target_ids = [str(target["target_id"]) for target in targets]
        if len(target_ids) != len(targets):
            raise ValueError("Target ids must be unique.")

        current_viewpoints_reassignment = require_list(
            payload["current_viewpoints_reassignment"],
            "current_viewpoints_reassignment",
        )
        visible_region_nodes = require_list(
            payload["visible_region_nodes"], "visible_region_nodes"
        )
        invisible_region_nodes = require_list(
            payload["invisible_region_nodes"], "invisible_region_nodes"
        )
        if semantic_payload_contract == "graph_mllm":
            region_target_scores = require_list(
                payload["region_target_scores"], "region_target_scores"
            )
            viewpoint_target_scores = require_list(
                payload["viewpoint_target_scores"], "viewpoint_target_scores"
            )
            viewpoint_target_probs = []
            viewpoint_target_score_basis = []
        else:
            region_target_scores = require_list(
                payload.get("region_target_scores", []), "region_target_scores"
            )
            viewpoint_target_scores = []
            viewpoint_target_probs = require_list(
                payload["viewpoint_target_probs"], "viewpoint_target_probs"
            )
            viewpoint_target_score_basis = require_list(
                payload["viewpoint_target_score_basis"],
                "viewpoint_target_score_basis",
            )
        viewpoint_node_assigns = require_list(
            payload["viewpoint_node_assigns"], "viewpoint_node_assigns"
        )
        new_edges = require_list(payload["new_edges"], "new_edges")
        edge_distance_variances = require_dict(
            payload["edge_distance_variances"], "edge_distance_variances"
        )

        agent_current_region = {}

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
                        "prior_raw_target_probs": dict(
                            node.get("raw_target_probs", {}) or {}
                        ),
                    }

        new_visible_neighbor_assignment_viewpoint_ids = (
            visible_viewpoint_ids - current_viewpoint_ids - graph_viewpoint_node_ids
        )

        current_viewpoint_ids_without_prior_region = {
            viewpoint_id
            for viewpoint_id in current_viewpoint_ids
            if viewpoint_id not in graph_viewpoint_to_region
        }

        assignment_required_viewpoint_ids = (
            new_visible_neighbor_assignment_viewpoint_ids
            | current_viewpoint_ids_without_prior_region
        )

        expected_assignment_viewpoint_ids = assignment_required_viewpoint_ids

        detection_fixed_viewpoint_ids = set(current_viewpoint_ids)
        for viewpoint_id, status in graph_viewpoint_status_by_id.items():
            if (
                bool(status.get("prior_grounded", False))
                or int(status.get("prior_visit_times", 0)) > 0
            ):
                detection_fixed_viewpoint_ids.add(viewpoint_id)

        def validate_region_target_probs(
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
                validate_probability_or_zero(
                    value,
                    "%s.target_probs[%s]" % (context, target_id),
                )

        def validate_partial_target_probs_nonnegative(
            target_probs: Dict[str, object],
            context: str,
        ) -> Dict[str, float]:
            target_probs = require_dict(target_probs, context + ".target_probs")

            returned_target_ids = {str(key) for key in target_probs}
            if not returned_target_ids.issubset(target_ids):
                raise ValueError(
                    "%s target_probs keys %s must be a subset of expected target ids %s."
                    % (context, sorted(returned_target_ids), sorted(target_ids))
                )

            for target_id, value in target_probs.items():
                validate_nonnegative_number(
                    value,
                    "%s.target_probs[%s]" % (context, target_id),
                )
            return {
                str(target_id): float(value)
                for target_id, value in target_probs.items()
            }

        def validate_partial_target_scores_nonnegative(
            target_scores: Dict[str, object],
            context: str,
        ) -> Dict[str, float]:
            target_scores = require_dict(target_scores, context + ".target_scores")

            returned_target_ids = {str(key) for key in target_scores}
            if not returned_target_ids.issubset(target_ids):
                raise ValueError(
                    "%s target_scores keys %s must be a subset of expected target ids %s."
                    % (context, sorted(returned_target_ids), sorted(target_ids))
                )

            for target_id, value in target_scores.items():
                validate_nonnegative_number(
                    value,
                    "%s.target_scores[%s]" % (context, target_id),
                )
            return {
                str(target_id): float(value)
                for target_id, value in target_scores.items()
            }

        def validate_region_label(label: str, context: str) -> None:
            normalized_label = " ".join(label.lower().split())

            if "agent" in normalized_label:
                raise ValueError(
                    "%s label must not mention agent ids or agent names: %s"
                    % (context, label)
                )

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
                if region_id in graph_region_records:
                    raise ValueError(
                        "%s region %s already exists in graph_summary. Existing "
                        "graph regions must be referenced by id, not re-emitted "
                        "with regenerated target_probs." % (region_key, region_id)
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

                validate_region_target_probs(
                    region["target_probs"],
                    "%s region %s" % (region_key, region_id),
                )

        if visible_region_ids & invisible_region_ids:
            raise ValueError(
                "Region ids cannot appear in both visible_region_nodes and "
                "invisible_region_nodes: %s"
                % sorted(visible_region_ids & invisible_region_ids)
            )

        graph_region_ids = set(graph_region_records)
        all_region_ids = visible_region_ids | invisible_region_ids | graph_region_ids

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

        raw_region_target_probs_by_id = {}
        for region_id, node in graph_region_records.items():
            source_target_probs = (
                node.get("raw_target_probs", {}) or node.get("target_probs", {}) or {}
            )
            raw_region_target_probs_by_id[region_id] = {
                target_id: float(source_target_probs.get(target_id, 0.0))
                for target_id in ordered_target_ids
            }

        for region in visible_region_nodes + invisible_region_nodes:
            region_id = int(region["id"])
            raw_region_target_probs_by_id[region_id] = {
                target_id: float(region["target_probs"][target_id])
                for target_id in ordered_target_ids
            }

        returned_region_score_ids = set()
        explicit_region_target_scores_by_id = {}
        for item in region_target_scores:
            item = require_dict(item, "region_target_scores[] item")

            expected_keys = {"id", "target_scores"}
            if set(item) != expected_keys:
                raise KeyError(
                    "Each region_target_scores item must contain exactly %s, got %s."
                    % (sorted(expected_keys), sorted(item))
                )

            region_id = int(item["id"])
            if region_id not in all_region_ids:
                raise ValueError(
                    "region_target_scores id %s is not a known region id." % region_id
                )
            if region_id in returned_region_score_ids:
                raise ValueError("Duplicated region_target_scores id %s." % region_id)
            returned_region_score_ids.add(region_id)

            target_scores = validate_partial_target_scores_nonnegative(
                item["target_scores"],
                "region_target_scores[%s]" % region_id,
            )
            explicit_region_target_scores_by_id[region_id] = target_scores
            raw_region_target_probs_by_id[region_id].update(target_scores)

        required_mllm_viewpoint_prob_ids = (
            graph_viewpoint_node_ids | visible_viewpoint_ids
        ) - detection_fixed_viewpoint_ids

        raw_viewpoint_target_probs_by_id = {}
        for viewpoint_id in required_mllm_viewpoint_prob_ids:
            status = graph_viewpoint_status_by_id.get(viewpoint_id, {})
            prior_raw_target_probs = status.get("prior_raw_target_probs", {}) or {}
            raw_viewpoint_target_probs_by_id[viewpoint_id] = {
                target_id: float(prior_raw_target_probs[target_id])
                for target_id in ordered_target_ids
                if target_id in prior_raw_target_probs
            }

        target_score_basis_by_id = {
            viewpoint_id: {} for viewpoint_id in required_mllm_viewpoint_prob_ids
        }
        evidence_strength_by_id = {
            viewpoint_id: {} for viewpoint_id in required_mllm_viewpoint_prob_ids
        }

        def validate_mllm_updatable_viewpoint_id(
            viewpoint_id: int,
            field_name: str,
        ) -> None:
            if viewpoint_id in detection_fixed_viewpoint_ids:
                raise ValueError(
                    "%s id %s is detection-fixed. Current, grounded, and visited "
                    "viewpoint target probabilities are detection-fixed and must not "
                    "be returned by the graph MLLM." % (field_name, viewpoint_id)
                )

            if viewpoint_id not in required_mllm_viewpoint_prob_ids:
                raise ValueError(
                    "%s id %s is not an MLLM-updatable non-current viewpoint."
                    % (field_name, viewpoint_id)
                )

        def project_non_decreasing(values: List[float]) -> List[float]:
            blocks = []
            for index, value in enumerate(values):
                blocks.append(
                    {
                        "start": index,
                        "end": index,
                        "weight": 1.0,
                        "total": float(value),
                    }
                )
                while len(blocks) >= 2:
                    left = blocks[-2]
                    right = blocks[-1]
                    left_avg = left["total"] / left["weight"]
                    right_avg = right["total"] / right["weight"]
                    if left_avg <= right_avg:
                        break
                    merged = {
                        "start": left["start"],
                        "end": right["end"],
                        "weight": left["weight"] + right["weight"],
                        "total": left["total"] + right["total"],
                    }
                    blocks[-2:] = [merged]

            projected = [0.0 for _ in values]
            for block in blocks:
                avg = block["total"] / block["weight"]
                for index in range(int(block["start"]), int(block["end"]) + 1):
                    projected[index] = float(avg)
            return projected

        if semantic_payload_contract == "graph_mllm":
            evidence_strength_rank = {"low": 0, "medium": 1, "high": 2}
            returned_viewpoint_score_ids = set()
            for item in viewpoint_target_scores:
                item = require_dict(item, "viewpoint_target_scores[] item")

                expected_keys = {"id", "target_scores"}
                if set(item) != expected_keys:
                    raise KeyError(
                        "Each viewpoint_target_scores item must contain exactly %s, got %s."
                        % (sorted(expected_keys), sorted(item))
                    )

                viewpoint_id = int(item["id"])
                validate_mllm_updatable_viewpoint_id(
                    viewpoint_id,
                    "viewpoint_target_scores",
                )
                if viewpoint_id in returned_viewpoint_score_ids:
                    raise ValueError(
                        "Duplicated viewpoint_target_scores id %s." % viewpoint_id
                    )
                returned_viewpoint_score_ids.add(viewpoint_id)

                target_scores = require_dict(
                    item["target_scores"],
                    "viewpoint_target_scores[%s].target_scores" % viewpoint_id,
                )
                returned_target_ids = {str(key) for key in target_scores}
                if not returned_target_ids.issubset(target_ids):
                    raise ValueError(
                        "viewpoint_target_scores id %s target_scores keys %s must be "
                        "a subset of expected target ids %s."
                        % (
                            viewpoint_id,
                            sorted(returned_target_ids),
                            sorted(target_ids),
                        )
                    )

                for target_id_raw, score_record_raw in target_scores.items():
                    target_id = str(target_id_raw)
                    score_record = require_dict(
                        score_record_raw,
                        "viewpoint_target_scores[%s].target_scores[%s]"
                        % (viewpoint_id, target_id),
                    )
                    expected_score_keys = {
                        "raw_score",
                        "evidence_strength",
                        "basis",
                    }
                    if set(score_record) != expected_score_keys:
                        raise KeyError(
                            "viewpoint_target_scores[%s].target_scores[%s] must "
                            "contain exactly %s, got %s."
                            % (
                                viewpoint_id,
                                target_id,
                                sorted(expected_score_keys),
                                sorted(score_record),
                            )
                        )

                    validate_nonnegative_number(
                        score_record["raw_score"],
                        "viewpoint_target_scores[%s].target_scores[%s].raw_score"
                        % (viewpoint_id, target_id),
                    )
                    evidence_strength = str(score_record["evidence_strength"])
                    if evidence_strength not in evidence_strength_rank:
                        raise ValueError(
                            "viewpoint_target_scores[%s].target_scores[%s]."
                            "evidence_strength must be one of %s, got %s."
                            % (
                                viewpoint_id,
                                target_id,
                                sorted(evidence_strength_rank),
                                evidence_strength,
                            )
                        )
                    validate_nonempty_string(
                        score_record["basis"],
                        "viewpoint_target_scores[%s].target_scores[%s].basis"
                        % (viewpoint_id, target_id),
                    )

                    raw_viewpoint_target_probs_by_id[viewpoint_id][target_id] = float(
                        score_record["raw_score"]
                    )
                    evidence_strength_by_id[viewpoint_id][target_id] = evidence_strength
                    target_score_basis_by_id[viewpoint_id][target_id] = str(
                        score_record["basis"]
                    )

            for target_id in ordered_target_ids:
                entries = [
                    (
                        evidence_strength_rank[
                            evidence_strength_by_id[viewpoint_id][target_id]
                        ],
                        raw_viewpoint_target_probs_by_id[viewpoint_id][target_id],
                        viewpoint_id,
                    )
                    for viewpoint_id in required_mllm_viewpoint_prob_ids
                    if target_id in evidence_strength_by_id[viewpoint_id]
                ]
                entries.sort()
                projected_values = project_non_decreasing(
                    [raw_score for _, raw_score, _ in entries]
                )
                for (_, _, viewpoint_id), projected_value in zip(
                    entries,
                    projected_values,
                ):
                    raw_viewpoint_target_probs_by_id[viewpoint_id][
                        target_id
                    ] = projected_value

        else:
            returned_viewpoint_score_basis_ids = set()
            for item in viewpoint_target_score_basis:
                item = require_dict(item, "viewpoint_target_score_basis[] item")

                expected_keys = {"id", "score_basis"}
                if set(item) != expected_keys:
                    raise KeyError(
                        "Each viewpoint_target_score_basis item must contain exactly %s, got %s."
                        % (sorted(expected_keys), sorted(item))
                    )

                viewpoint_id = int(item["id"])
                validate_mllm_updatable_viewpoint_id(
                    viewpoint_id,
                    "viewpoint_target_score_basis",
                )
                if viewpoint_id in returned_viewpoint_score_basis_ids:
                    raise ValueError(
                        "Duplicated viewpoint_target_score_basis id %s." % viewpoint_id
                    )
                returned_viewpoint_score_basis_ids.add(viewpoint_id)

                score_basis = require_dict(
                    item["score_basis"],
                    "viewpoint_target_score_basis[%s].score_basis" % viewpoint_id,
                )
                returned_score_basis_target_ids = {str(key) for key in score_basis}
                if not returned_score_basis_target_ids.issubset(target_ids):
                    raise ValueError(
                        "viewpoint_target_score_basis id %s score_basis keys %s must be "
                        "a subset of expected target ids %s."
                        % (
                            viewpoint_id,
                            sorted(returned_score_basis_target_ids),
                            sorted(target_ids),
                        )
                    )

                for target_id in returned_score_basis_target_ids:
                    validate_nonempty_string(
                        score_basis[target_id],
                        "viewpoint_target_score_basis[%s].score_basis[%s]"
                        % (viewpoint_id, target_id),
                    )
                    target_score_basis_by_id[viewpoint_id][target_id] = str(
                        score_basis[target_id]
                    )

            if returned_viewpoint_score_basis_ids != required_mllm_viewpoint_prob_ids:
                raise ValueError(
                    "Returned viewpoint_target_score_basis ids %s do not match expected "
                    "MLLM-updatable viewpoint ids %s."
                    % (
                        sorted(returned_viewpoint_score_basis_ids),
                        sorted(required_mllm_viewpoint_prob_ids),
                    )
                )

            returned_viewpoint_prob_ids = set()
            for item in viewpoint_target_probs:
                item = require_dict(item, "viewpoint_target_probs[] item")

                expected_key_sets = [
                    {"id", "target_probs"},
                    {"id", "target_probs", "raw_target_probs"},
                ]
                if set(item) not in expected_key_sets:
                    raise KeyError(
                        "Each viewpoint_target_probs item must contain one of %s, got %s."
                        % ([sorted(keys) for keys in expected_key_sets], sorted(item))
                    )

                viewpoint_id = int(item["id"])
                validate_mllm_updatable_viewpoint_id(
                    viewpoint_id,
                    "viewpoint_target_probs",
                )
                if viewpoint_id in returned_viewpoint_prob_ids:
                    raise ValueError(
                        "Duplicated viewpoint_target_probs id %s." % viewpoint_id
                    )

                returned_viewpoint_prob_ids.add(viewpoint_id)

                raw_source_key = (
                    "raw_target_probs" if "raw_target_probs" in item else "target_probs"
                )
                partial_target_probs = validate_partial_target_probs_nonnegative(
                    item[raw_source_key],
                    "MLLM-updatable viewpoint %s" % viewpoint_id,
                )

                raw_viewpoint_target_probs_by_id[viewpoint_id].update(
                    partial_target_probs
                )

            extra_viewpoint_prob_ids = (
                returned_viewpoint_prob_ids - required_mllm_viewpoint_prob_ids
            )
            if extra_viewpoint_prob_ids:
                raise ValueError(
                    "Unexpected MLLM-updatable viewpoint_target_probs ids %s. "
                    "Expected ids were %s."
                    % (
                        sorted(extra_viewpoint_prob_ids),
                        sorted(required_mllm_viewpoint_prob_ids),
                    )
                )

        missing_required_viewpoint_prob_values = {}
        for viewpoint_id in sorted(required_mllm_viewpoint_prob_ids):
            missing_target_ids = [
                target_id
                for target_id in ordered_target_ids
                if target_id not in raw_viewpoint_target_probs_by_id[viewpoint_id]
            ]
            if missing_target_ids:
                missing_required_viewpoint_prob_values[viewpoint_id] = (
                    missing_target_ids
                )

        if missing_required_viewpoint_prob_values:
            raise ValueError(
                "Missing required MLLM-updatable "
                "viewpoint_target_probs values %s. Returned ids were %s."
                % (
                    missing_required_viewpoint_prob_values,
                    sorted(
                        returned_viewpoint_score_ids
                        if semantic_payload_contract == "graph_mllm"
                        else returned_viewpoint_prob_ids
                    ),
                )
            )

        if semantic_payload_contract == "saved_materialized":
            missing_required_score_basis = {}
            for viewpoint_id in sorted(required_mllm_viewpoint_prob_ids):
                status = graph_viewpoint_status_by_id.get(viewpoint_id, {})
                prior_raw_target_probs = status.get("prior_raw_target_probs", {}) or {}

                for target_id in ordered_target_ids:
                    if target_id in target_score_basis_by_id[viewpoint_id]:
                        continue

                    if target_id not in prior_raw_target_probs:
                        missing_required_score_basis.setdefault(
                            viewpoint_id, []
                        ).append(target_id)
                        continue

                    if float(
                        raw_viewpoint_target_probs_by_id[viewpoint_id][target_id]
                    ) != float(prior_raw_target_probs[target_id]):
                        missing_required_score_basis.setdefault(
                            viewpoint_id, []
                        ).append(target_id)

            if missing_required_score_basis:
                raise ValueError(
                    "Missing required saved viewpoint_target_score_basis values %s. "
                    "Saved materialized payloads may omit basis only for unchanged "
                    "prior raw_target_probs." % missing_required_score_basis
                )

        normalized_viewpoint_target_probs = []
        normalized_viewpoint_target_probs_by_id = {}
        for target_id in ordered_target_ids:
            raw_sum = sum(
                raw_viewpoint_target_probs_by_id[viewpoint_id][target_id]
                for viewpoint_id in required_mllm_viewpoint_prob_ids
            )
            if required_mllm_viewpoint_prob_ids and raw_sum <= 0.0:
                raise ValueError(
                    "MLLM-updatable viewpoint_target_probs for target %s sum to %s."
                    % (target_id, raw_sum)
                )

        for viewpoint_id in sorted(required_mllm_viewpoint_prob_ids):
            normalized_target_probs = {}
            for target_id in ordered_target_ids:
                raw_sum = sum(
                    raw_viewpoint_target_probs_by_id[other_viewpoint_id][target_id]
                    for other_viewpoint_id in required_mllm_viewpoint_prob_ids
                )
                normalized_target_probs[target_id] = (
                    raw_viewpoint_target_probs_by_id[viewpoint_id][target_id] / raw_sum
                )

            normalized_viewpoint_target_probs.append(
                {
                    "id": viewpoint_id,
                    "target_probs": normalized_target_probs,
                    "raw_target_probs": dict(
                        raw_viewpoint_target_probs_by_id[viewpoint_id]
                    ),
                }
            )
            normalized_viewpoint_target_probs_by_id[viewpoint_id] = dict(
                normalized_target_probs
            )

        payload["viewpoint_target_probs"] = normalized_viewpoint_target_probs
        viewpoint_target_probs = payload["viewpoint_target_probs"]
        payload["viewpoint_target_score_basis"] = [
            {
                "id": viewpoint_id,
                "score_basis": dict(target_score_basis_by_id[viewpoint_id]),
            }
            for viewpoint_id in sorted(required_mllm_viewpoint_prob_ids)
        ]
        payload.pop("viewpoint_target_scores", None)

        # Build a one-to-one viewpoint-to-region map.
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
                    raise ValueError(
                        "Viewpoint %s is duplicated within one assignment group."
                        % viewpoint_id
                    )
                seen_ids_in_this_region.add(viewpoint_id)

                if viewpoint_id in assignment_candidates_by_viewpoint:
                    raise ValueError(
                        "Viewpoint %s appears in more than one assignment group."
                        % viewpoint_id
                    )

                assignment_candidates_by_viewpoint[viewpoint_id] = region_node_id

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

        assigned_viewpoint_to_region = dict(assignment_candidates_by_viewpoint)

        reassigned_current_viewpoint_to_region = {}
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
            new_region_id = int(item["new_assigned_region_id"])

            if viewpoint_id not in current_viewpoint_ids:
                raise ValueError(
                    "current_viewpoints_reassignment viewpoint_id %s is not a "
                    "current viewpoint." % viewpoint_id
                )

            if (
                new_region_id not in visible_region_ids
                and new_region_id not in graph_region_ids
            ):
                raise ValueError(
                    "current_viewpoints_reassignment new_assigned_region_id %s must "
                    "appear in visible_region_nodes or graph_summary region nodes."
                    % new_region_id
                )

            if viewpoint_id in seen_reassignment_viewpoints:
                raise ValueError(
                    "Duplicated current_viewpoints_reassignment item for viewpoint %s."
                    % viewpoint_id
                )
            seen_reassignment_viewpoints.add(viewpoint_id)

            old_region_id = graph_viewpoint_to_region.get(viewpoint_id)
            if old_region_id is None:
                raise ValueError(
                    "current_viewpoints_reassignment viewpoint_id %s has no prior "
                    "graph_summary.viewpoint_to_region assignment." % viewpoint_id
                )
            if new_region_id == old_region_id:
                raise ValueError(
                    "current_viewpoints_reassignment viewpoint_id %s does not change "
                    "its prior region %s." % (viewpoint_id, old_region_id)
                )
            if (
                viewpoint_id in assigned_viewpoint_to_region
                and assigned_viewpoint_to_region[viewpoint_id] != new_region_id
            ):
                raise ValueError(
                    "current_viewpoints_reassignment viewpoint_id %s assigns region "
                    "%s, but viewpoint_node_assigns assigns region %s."
                    % (
                        viewpoint_id,
                        new_region_id,
                        assigned_viewpoint_to_region[viewpoint_id],
                    )
                )

            reassigned_current_viewpoint_to_region[viewpoint_id] = new_region_id

        current_region_by_viewpoint = {}
        for observation in agent_observations:
            agent_id = str(observation["agent_id"])
            current_viewpoint_id = int(observation["current_viewpoint_index"])

            if current_viewpoint_id in assigned_viewpoint_to_region:
                current_region_id = assigned_viewpoint_to_region[current_viewpoint_id]
            elif current_viewpoint_id in reassigned_current_viewpoint_to_region:
                current_region_id = reassigned_current_viewpoint_to_region[
                    current_viewpoint_id
                ]
            else:
                if current_viewpoint_id not in graph_viewpoint_to_region:
                    raise ValueError(
                        "Current viewpoint %s has no region in viewpoint_node_assigns, "
                        "current_viewpoints_reassignment, or graph_summary.viewpoint_to_region."
                        % current_viewpoint_id
                    )
                current_region_id = graph_viewpoint_to_region[current_viewpoint_id]

            if (
                current_region_id not in visible_region_ids
                and current_region_id not in graph_region_ids
            ):
                raise ValueError(
                    "Derived current region %s for agent %s viewpoint %s is not in "
                    "visible_region_nodes or graph_summary region nodes."
                    % (current_region_id, agent_id, current_viewpoint_id)
                )

            current_region_by_viewpoint[current_viewpoint_id] = current_region_id
            agent_current_region[agent_id] = current_region_id

        expected_reassignment_by_viewpoint = {}
        for current_viewpoint_id, new_region_id in sorted(
            current_region_by_viewpoint.items()
        ):
            old_region_id = graph_viewpoint_to_region.get(current_viewpoint_id)

            if old_region_id is not None and new_region_id != old_region_id:
                expected_reassignment_by_viewpoint[current_viewpoint_id] = new_region_id

        if reassigned_current_viewpoint_to_region != expected_reassignment_by_viewpoint:
            raise ValueError(
                "current_viewpoints_reassignment %s does not match expected true "
                "current-region changes %s."
                % (
                    reassigned_current_viewpoint_to_region,
                    expected_reassignment_by_viewpoint,
                )
            )

        returned_reassignment_by_viewpoint = reassigned_current_viewpoint_to_region

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

        final_viewpoint_to_region = dict(graph_viewpoint_to_region)
        for viewpoint_id, region_id in assigned_viewpoint_to_region.items():
            final_viewpoint_to_region[viewpoint_id] = region_id
        for viewpoint_id, region_id in reassigned_current_viewpoint_to_region.items():
            final_viewpoint_to_region[viewpoint_id] = region_id

        region_to_all_assigned_viewpoints = {}
        for viewpoint_id, region_id in final_viewpoint_to_region.items():
            region_to_all_assigned_viewpoints.setdefault(region_id, set()).add(
                viewpoint_id
            )

        prior_type1_region_ids = {
            region_id
            for region_id in graph_region_ids
            if any(
                assigned_region_id == region_id
                for assigned_region_id in graph_viewpoint_to_region.values()
            )
        }

        type2_region_ids = [
            region_id
            for region_id in sorted(all_region_ids)
            if not region_to_all_assigned_viewpoints.get(region_id, set())
        ]

        invalid_region_score_ids = sorted(
            region_id
            for region_id in returned_region_score_ids
            if region_id not in type2_region_ids
        )

        missing_region_score_targets_by_id = {}
        for region_id in sorted(all_region_ids):
            assigned_viewpoint_ids = region_to_all_assigned_viewpoints.get(
                region_id,
                set(),
            )
            if assigned_viewpoint_ids:
                continue

            if region_id in prior_type1_region_ids:
                missing_target_ids = [
                    target_id
                    for target_id in ordered_target_ids
                    if target_id
                    not in explicit_region_target_scores_by_id.get(region_id, {})
                ]
                if missing_target_ids:
                    missing_region_score_targets_by_id[region_id] = missing_target_ids

        if invalid_region_score_ids or missing_region_score_targets_by_id:
            error_parts = []
            if invalid_region_score_ids:
                error_parts.append(
                    "remove region_target_scores for regions with final assigned "
                    "viewpoints %s" % invalid_region_score_ids
                )
            if missing_region_score_targets_by_id:
                error_parts.append(
                    "add complete region_target_scores for prior assigned regions "
                    "that became unassigned %s" % missing_region_score_targets_by_id
                )
            raise ValueError(
                "Invalid region_target_scores contract: %s."
                % "; ".join(error_parts)
            )

        for region_id in sorted(all_region_ids):
            assigned_viewpoint_ids = region_to_all_assigned_viewpoints.get(
                region_id,
                set(),
            )
            if assigned_viewpoint_ids:
                raw_region_target_probs_by_id[region_id] = {}
                for target_id in ordered_target_ids:
                    raw_region_target_probs_by_id[region_id][target_id] = sum(
                        (
                            0.0
                            if viewpoint_id in detection_fixed_viewpoint_ids
                            else normalized_viewpoint_target_probs_by_id[viewpoint_id][
                                target_id
                            ]
                        )
                        for viewpoint_id in assigned_viewpoint_ids
                    ) / float(len(assigned_viewpoint_ids))
                continue

        if all_region_ids:
            for target_id in ordered_target_ids:
                raw_sum = sum(
                    raw_region_target_probs_by_id[region_id][target_id]
                    for region_id in all_region_ids
                )
                if raw_sum <= 0.0:
                    raise ValueError(
                        "Region target probabilities for target %s sum to %s."
                        % (target_id, raw_sum)
                    )

                for region_id in all_region_ids:
                    raw_region_target_probs_by_id[region_id][target_id] = float(
                        raw_region_target_probs_by_id[region_id][target_id]
                    )

        normalized_region_target_probs_by_id = {}
        for region_id in sorted(all_region_ids):
            normalized_region_target_probs_by_id[region_id] = {}
            for target_id in ordered_target_ids:
                raw_sum = sum(
                    raw_region_target_probs_by_id[other_region_id][target_id]
                    for other_region_id in all_region_ids
                )
                normalized_region_target_probs_by_id[region_id][target_id] = (
                    raw_region_target_probs_by_id[region_id][target_id] / raw_sum
                )

        for region in visible_region_nodes + invisible_region_nodes:
            region_id = int(region["id"])
            region["target_probs"] = dict(
                normalized_region_target_probs_by_id[region_id]
            )

        payload["region_target_scores"] = [
            {
                "id": int(region_id),
                "target_scores": dict(raw_region_target_probs_by_id[region_id]),
            }
            for region_id in type2_region_ids
        ]

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
                i_status = graph_viewpoint_status_by_id.get(i)
                j_status = graph_viewpoint_status_by_id.get(j)
                if i_status is None or j_status is None:
                    raise ValueError(
                        "VV edge (%s, %s) endpoints must have prior visit-state "
                        "records in graph_summary." % (i, j)
                    )
                if (
                    bool(i_status.get("prior_grounded", False))
                    or bool(j_status.get("prior_grounded", False))
                    or int(i_status.get("prior_visit_times", 0)) > 0
                    or int(j_status.get("prior_visit_times", 0)) > 0
                ):
                    raise ValueError(
                        "VV edge (%s, %s) endpoints must both be ungrounded and "
                        "unvisited." % (i, j)
                    )

                cleaned_new_edges.append(edge)
                continue

            if edge_type == "VZ":
                valid_vz = (i_is_viewpoint and j_is_region) or (
                    i_is_region and j_is_viewpoint
                )
                if not valid_vz:
                    raise ValueError(
                        "VZ edge (%s, %s) does not connect exactly one "
                        "current-step viewpoint node and one region node." % (i, j)
                    )

                viewpoint_id = i if i_is_viewpoint else j
                region_id = i if i_is_region else j

                assigned_region_id = assigned_viewpoint_to_region.get(viewpoint_id)
                if assigned_region_id == region_id:
                    raise ValueError(
                        "VZ edge connects viewpoint %s to its assigned region %s."
                        % (viewpoint_id, region_id)
                    )

                assigned_viewpoints = region_to_all_assigned_viewpoints.get(
                    region_id, set()
                )
                if assigned_viewpoints:
                    raise ValueError(
                        "VZ edge connects to region %s, which already has assigned "
                        "viewpoints %s." % (region_id, sorted(assigned_viewpoints))
                    )

                cleaned_new_edges.append(edge)

        payload["new_edges"] = cleaned_new_edges

        return payload
