from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from semantic_persistence.mllm_client import (
    GRAPH_IMAGE_JPEG_QUALITY,
    GRAPH_IMAGE_MAX_WIDTH,
    MLLMClient,
    MLLMProviderCreditError,
    MLLMRetryExhaustedError,
)


class DirectActionValidationError(ValueError):
    pass


class MLLMDirectPolicy:
    def __init__(
        self,
        client: MLLMClient,
        config: Dict[str, object],
        raw_output_dir: str,
        debug_output_dir: str,
    ) -> None:
        self.client = client
        self.include_one_step_distances = bool(
            config.get("include_one_step_distances", True)
        )
        self.max_validation_retries = int(
            config.get("max_validation_retries", 1)
        )
        if self.max_validation_retries != 1:
            raise ValueError(
                "mllm_direct.max_validation_retries must be exactly 1."
            )
        self.raw_output_dir = Path(raw_output_dir)
        self.debug_output_dir = Path(debug_output_dir)

    @staticmethod
    def rotating_order(agent_ids: List[str], step_index: int) -> List[str]:
        ordered = sorted(str(agent_id) for agent_id in agent_ids)
        if not ordered:
            return []
        offset = (int(step_index) - 1) % len(ordered)
        return ordered[offset:] + ordered[:offset]

    @staticmethod
    def _system_message() -> str:
        return (
            "You are the action-selection module for one embodied target-search "
            "agent. You receive one current horizontal panorama whose immediately "
            "reachable neighboring viewpoints are annotated with short numeric "
            "IDs. Choose exactly one allowed short viewpoint ID as the agent's "
            "next move. Use only "
            "the current panorama and the supplied target list. Do not construct, "
            "assume, or describe a map. Do not assume access to earlier "
            "observations or future images. Never output a viewpoint ID that is "
            "not in ALLOWED_SHORT_VIEWPOINT_IDS. Return valid JSON only."
        )

    @staticmethod
    def _short_viewpoint_id(action: Dict[str, object]) -> str:
        return str(int(action["viewpoint_index"]))

    def _user_message(
        self,
        active_targets: List[Dict[str, object]],
        allowed_actions: List[Dict[str, object]],
        reserved_ids: List[str],
    ) -> str:
        allowed_ids = [
            self._short_viewpoint_id(action) for action in allowed_actions
        ]
        distances = (
            {
                self._short_viewpoint_id(action): float(action["distance"])
                for action in allowed_actions
            }
            if self.include_one_step_distances
            else None
        )
        return (
            "You need to find the following targets:\n"
            + json.dumps(active_targets, indent=2, sort_keys=True)
            + "\n\nWhich viewpoint from the given panorama should be the next "
            "viewpoint to reach to find the most promising one or more targets?\n\n"
            + "ALLOWED_SHORT_VIEWPOINT_IDS:\n"
            + json.dumps(allowed_ids)
            + "\n\nONE_STEP_TRAVEL_DISTANCES:\n"
            + json.dumps(distances, sort_keys=True)
            + "\n\nSHORT_VIEWPOINT_IDS_RESERVED_BY_OTHER_AGENTS_THIS_ROUND:\n"
            + json.dumps(sorted(reserved_ids))
            + "\n\nReturn valid JSON only. Return exactly:\n"
            + '{\n  "next_viewpoint_id": "<one allowed ID or WAIT>",\n'
            + '  "promising_target_ids": ["<zero or more target IDs>"]\n}'
        )

    @staticmethod
    def _repair_message(
        valid_ids: List[str],
        active_target_ids: List[str],
        error: object,
    ) -> str:
        return (
            "Your previous output was invalid. Error: %s\n"
            "Return JSON only. Set next_viewpoint_id to exactly one ID from: "
            "%s. Do not output WAIT or any other viewpoint ID. Set "
            "promising_target_ids to a JSON list containing zero or more IDs "
            "only from: %s. Do not put viewpoint IDs in promising_target_ids. "
            "Return exactly next_viewpoint_id and promising_target_ids."
            % (
                str(error),
                json.dumps(valid_ids),
                json.dumps(active_target_ids),
            )
        )

    @staticmethod
    def parse_and_validate(
        decoded: str,
        allowed_ids: List[str],
        active_target_ids: List[str],
    ) -> Dict[str, object]:
        raw = MLLMClient._strip_code_fences(str(decoded))
        payload = MLLMClient._parse_json_strict(raw)
        if set(payload) != {"next_viewpoint_id", "promising_target_ids"}:
            raise DirectActionValidationError(
                "Direct action output must contain exactly next_viewpoint_id and "
                "promising_target_ids."
            )
        next_viewpoint_id = str(payload["next_viewpoint_id"])
        if next_viewpoint_id == "WAIT":
            raise DirectActionValidationError(
                "WAIT is invalid while an unreserved action exists."
            )
        if next_viewpoint_id not in set(allowed_ids):
            raise DirectActionValidationError(
                "Selected viewpoint %s is not an allowed unreserved ID."
                % next_viewpoint_id
            )
        promising = payload["promising_target_ids"]
        if not isinstance(promising, list):
            raise DirectActionValidationError(
                "promising_target_ids must be a JSON list."
            )
        promising_ids = [str(target_id) for target_id in promising]
        if len(promising_ids) != len(set(promising_ids)):
            raise DirectActionValidationError(
                "promising_target_ids must not contain duplicates."
            )
        unknown = sorted(set(promising_ids) - set(active_target_ids))
        if unknown:
            raise DirectActionValidationError(
                "promising_target_ids contains inactive IDs %s." % unknown
            )
        return {
            "next_viewpoint_id": next_viewpoint_id,
            "promising_target_ids": promising_ids,
        }

    def _raw_path(self, step_index: int, agent_id: str) -> Path:
        return self.raw_output_dir / (
            "direct_action_step_%04d_agent_%s.json"
            % (int(step_index), str(agent_id))
        )

    def _prompt_path(self, step_index: int, agent_id: str) -> Path:
        return self.raw_output_dir / (
            "direct_action_prompt_step_%04d_agent_%s.txt"
            % (int(step_index), str(agent_id))
        )

    def _error_path(
        self,
        step_index: int,
        agent_id: str,
        attempt_index: int,
    ) -> Path:
        return self.raw_output_dir / (
            "direct_action_step_%04d_agent_%s_attempt_%02d_error.txt"
            % (int(step_index), str(agent_id), int(attempt_index))
        )

    @staticmethod
    def _write_text(path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(value), encoding="utf-8")

    def _select_one(
        self,
        step_index: int,
        observation: Dict[str, object],
        active_targets: List[Dict[str, object]],
        allowed_actions: List[Dict[str, object]],
        reserved_ids: List[str],
    ) -> Dict[str, object]:
        agent_id = str(observation["agent_id"])
        allowed_ids = [
            self._short_viewpoint_id(action) for action in allowed_actions
        ]
        active_target_ids = [
            str(target["target_id"]) for target in active_targets
        ]
        user_message = self._user_message(
            active_targets=active_targets,
            allowed_actions=allowed_actions,
            reserved_ids=reserved_ids,
        )
        self._write_text(self._prompt_path(step_index, agent_id), user_message)

        raw_path = self._raw_path(step_index, agent_id)
        if self.client.read_saved_raw_outputs and raw_path.exists():
            decoded = raw_path.read_text(encoding="utf-8")
            return self.parse_and_validate(
                decoded=decoded,
                allowed_ids=allowed_ids,
                active_target_ids=active_target_ids,
            )

        image_bytes = MLLMClient._resize_panorama_array(
            observation["annotated_panorama"],
            max_width=GRAPH_IMAGE_MAX_WIDTH,
            jpeg_quality=GRAPH_IMAGE_JPEG_QUALITY,
        )
        image_content = {
            "type": "image_url",
            "image_url": {"url": MLLMClient._image_to_data_url(image_bytes)},
        }
        last_error = None
        for attempt_index in range(self.max_validation_retries + 1):
            attempt_message = (
                user_message
                if attempt_index == 0
                else self._repair_message(
                    allowed_ids,
                    active_target_ids,
                    last_error,
                )
            )
            messages = [
                {"role": "system", "content": self._system_message()},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": attempt_message},
                        image_content,
                    ],
                },
            ]
            decoded = None
            try:
                decoded = self.client.request_action_completion(messages)
                parsed = self.parse_and_validate(
                    decoded=decoded,
                    allowed_ids=allowed_ids,
                    active_target_ids=active_target_ids,
                )
                self._write_text(
                    raw_path,
                    json.dumps(parsed, indent=2, sort_keys=True) + "\n",
                )
                return parsed
            except MLLMProviderCreditError:
                raise
            except (DirectActionValidationError, ValueError) as exc:
                last_error = exc
                self._write_text(
                    self._error_path(step_index, agent_id, attempt_index),
                    str(decoded if decoded is not None else exc),
                )
                if attempt_index >= self.max_validation_retries:
                    raise MLLMRetryExhaustedError(
                        stage="direct_action",
                        step_index=step_index,
                        attempts=self.max_validation_retries + 1,
                        last_error=last_error,
                    ) from exc
            except Exception:
                raise

        raise RuntimeError("Unexpected direct action retry loop exit.")

    def select_actions(
        self,
        step_index: int,
        agent_observations: List[Dict[str, object]],
        active_targets: List[Dict[str, object]],
    ) -> Dict[str, object]:
        observations = {
            str(observation["agent_id"]): observation
            for observation in agent_observations
        }
        order = self.rotating_order(list(observations), step_index)
        reserved = set()
        decisions = {}
        audit_records = []

        for agent_id in order:
            observation = observations[agent_id]
            local_actions = sorted(
                list(observation["local_actions"]),
                key=lambda action: str(action["viewpoint_id"]),
            )
            allowed_actions = [
                action
                for action in local_actions
                if self._short_viewpoint_id(action) not in reserved
            ]
            reserved_before = sorted(reserved)
            if not allowed_actions:
                selected = {
                    "next_viewpoint_id": "WAIT",
                    "promising_target_ids": [],
                }
                action_record = None
            else:
                selected = self._select_one(
                    step_index=step_index,
                    observation=observation,
                    active_targets=active_targets,
                    allowed_actions=allowed_actions,
                    reserved_ids=reserved_before,
                )
                action_record = next(
                    action
                    for action in allowed_actions
                    if self._short_viewpoint_id(action)
                    == str(selected["next_viewpoint_id"])
                )
                reserved.add(self._short_viewpoint_id(action_record))

            if action_record is None:
                decisions[agent_id] = {
                    "agent_id": agent_id,
                    "wait": True,
                    "next_viewpoint_id": str(observation["current_viewpoint_id"]),
                    "next_viewpoint_index": int(
                        observation["current_viewpoint_index"]
                    ),
                    "target_heading": float(
                        observation["start_state"].heading
                    ),
                }
            else:
                decisions[agent_id] = {
                    "agent_id": agent_id,
                    "wait": False,
                    "next_viewpoint_id": str(action_record["viewpoint_id"]),
                    "next_viewpoint_index": int(action_record["viewpoint_index"]),
                    "target_heading": float(action_record["bearing"]),
                }
            audit_records.append(
                {
                    "agent_id": agent_id,
                    "reserved_before": reserved_before,
                    "allowed_short_viewpoint_ids": [
                        self._short_viewpoint_id(action)
                        for action in allowed_actions
                    ],
                    "short_to_stable_viewpoint_ids": {
                        self._short_viewpoint_id(action): str(
                            action["viewpoint_id"]
                        )
                        for action in allowed_actions
                    },
                    "selected": selected,
                }
            )

        log = {
            "method": "mllm_direct",
            "step_index": int(step_index),
            "rotating_order": order,
            "active_targets": active_targets,
            "agent_decisions": audit_records,
            "final_reserved_short_viewpoint_ids": sorted(reserved),
        }
        log_path = self.debug_output_dir / (
            "mllm_direct_step_%04d.json" % int(step_index)
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            json.dumps(log, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return {
            "terminal": False,
            "actions": [decisions[agent_id] for agent_id in sorted(decisions)],
            "log_path": str(log_path),
        }
