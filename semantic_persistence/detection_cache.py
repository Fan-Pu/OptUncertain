from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


DETECTION_PROMPT_VERSION = "direct_detection_v1"


class DetectionCacheConflictError(ValueError):
    pass


class DetectionCache:
    KEY_FIELDS = (
        "scan_id",
        "viewpoint_id",
        "target_id",
        "target_description_hash",
        "detection_model",
        "prompt_version",
        "panorama_image_hash",
    )

    def __init__(
        self,
        cache_dir: str | os.PathLike[str],
        batch_id: str,
        conflict_policy: str = "raise",
    ):
        self.cache_dir = Path(cache_dir)
        self.batch_id = str(batch_id)
        self.path = self.cache_dir / self.batch_id / "detections.jsonl"
        self.conflict_path = (
            self.cache_dir / self.batch_id / "detection_conflicts.jsonl"
        )
        normalized_policy = str(conflict_policy).strip().lower()
        if normalized_policy not in {"raise", "quarantine"}:
            raise ValueError(
                "conflict_policy must be exactly 'raise' or 'quarantine'."
            )
        self.conflict_policy = normalized_policy

    @staticmethod
    def sha256_bytes(value: bytes) -> str:
        return hashlib.sha256(value).hexdigest()

    @staticmethod
    def target_description_hash(description: object) -> str:
        encoded = json.dumps(
            str(description),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def active_target_set_hash(cls, targets: List[Dict[str, object]]) -> str:
        records = sorted(
            [
                {
                    "target_id": str(target["target_id"]),
                    "target_description_hash": cls.target_description_hash(
                        str(target["description"])
                    ),
                }
                for target in targets
            ],
            key=lambda item: item["target_id"],
        )
        encoded = json.dumps(
            records,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _key_tuple(cls, entry: Dict[str, object]) -> Tuple[str, ...]:
        return tuple(str(entry[field]) for field in cls.KEY_FIELDS)

    @staticmethod
    def _result_tuple(entry: Dict[str, object]) -> Tuple[bool, Optional[float]]:
        found = bool(entry["found"])
        center_x = entry.get("target_center_x")
        return found, None if center_x is None else float(center_x)

    @classmethod
    def _conflict_message(
        cls,
        existing: Dict[str, object],
        incoming: Dict[str, object],
    ) -> str:
        key = {field: existing.get(field) for field in cls.KEY_FIELDS}
        return (
            "Conflicting detection cache entries for key %s: existing=%s incoming=%s"
            % (
                json.dumps(key, sort_keys=True),
                json.dumps(
                    {
                        "found": existing.get("found"),
                        "target_center_x": existing.get("target_center_x"),
                    },
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "found": incoming.get("found"),
                        "target_center_x": incoming.get("target_center_x"),
                    },
                    sort_keys=True,
                ),
            )
        )

    @classmethod
    def _conflict_record(
        cls,
        existing: Dict[str, object],
        incoming: Dict[str, object],
    ) -> Dict[str, object]:
        return {
            "key": {field: existing.get(field) for field in cls.KEY_FIELDS},
            "existing": {
                "found": existing.get("found"),
                "target_center_x": existing.get("target_center_x"),
                "case_id": existing.get("case_id"),
                "step_index": existing.get("step_index"),
                "agent_id": existing.get("agent_id"),
                "service_tier": existing.get("service_tier"),
            },
            "incoming": {
                "found": incoming.get("found"),
                "target_center_x": incoming.get("target_center_x"),
                "case_id": incoming.get("case_id"),
                "step_index": incoming.get("step_index"),
                "agent_id": incoming.get("agent_id"),
                "service_tier": incoming.get("service_tier"),
            },
        }

    def _read_conflict_keys(self) -> set[Tuple[str, ...]]:
        if not self.conflict_path.exists():
            return set()
        conflict_keys = set()
        with self.conflict_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                record = json.loads(text)
                key_record = record["key"]
                conflict_keys.add(tuple(str(key_record[field]) for field in self.KEY_FIELDS))
        return conflict_keys

    def _append_conflict(
        self,
        existing: Dict[str, object],
        incoming: Dict[str, object],
    ) -> None:
        self.conflict_path.parent.mkdir(parents=True, exist_ok=True)
        with self.conflict_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    self._conflict_record(existing, incoming),
                    sort_keys=True,
                )
                + "\n"
            )

    def _read_index(self) -> Dict[Tuple[str, ...], Dict[str, object]]:
        if not self.path.exists():
            return {}

        index: Dict[Tuple[str, ...], Dict[str, object]] = {}
        conflict_keys = (
            self._read_conflict_keys()
            if self.conflict_policy == "quarantine"
            else set()
        )
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                entry = json.loads(text)
                key = self._key_tuple(entry)
                if key in conflict_keys:
                    continue
                existing = index.get(key)
                if existing is not None:
                    if self._result_tuple(existing) != self._result_tuple(entry):
                        if self.conflict_policy == "quarantine":
                            self._append_conflict(existing, entry)
                            conflict_keys.add(key)
                            index.pop(key, None)
                            continue
                        raise DetectionCacheConflictError(
                            "%s at %s:%s"
                            % (
                                self._conflict_message(existing, entry),
                                str(self.path),
                                line_number,
                            )
                        )
                    continue
                index[key] = entry
        return index

    @classmethod
    def _entry(
        cls,
        *,
        scan_id: str,
        viewpoint_id: str,
        active_target_set_hash: str,
        target: Dict[str, object],
        detection_model: str,
        prompt_version: str,
        panorama_image_hash: str,
        found: bool,
        target_center_x: Optional[float],
        case_id: str,
        step_index: int,
        agent_id: str,
        viewpoint_index: object,
        service_tier: object,
        source_run_id: object = None,
    ) -> Dict[str, object]:
        target_id = str(target["target_id"])
        target_description = str(target["description"])
        entry = {
            "scan_id": str(scan_id),
            "viewpoint_id": str(viewpoint_id),
            "active_target_set_hash": str(active_target_set_hash),
            "target_id": target_id,
            "target_description_hash": cls.target_description_hash(
                target_description
            ),
            "detection_model": str(detection_model),
            "prompt_version": str(prompt_version),
            "panorama_image_hash": str(panorama_image_hash),
            "found": bool(found),
            "target_center_x": (
                None if target_center_x is None else float(target_center_x)
            ),
            "target_description": target_description,
            "case_id": str(case_id),
            "step_index": int(step_index),
            "agent_id": str(agent_id),
            "viewpoint_index": (
                None if viewpoint_index is None else int(viewpoint_index)
            ),
            "service_tier": None if service_tier is None else str(service_tier),
            "source_run_id": None if source_run_id is None else str(source_run_id),
        }
        if not entry["found"] and entry["target_center_x"] is not None:
            raise ValueError("Negative detection cache entries must not have center_x.")
        if entry["found"] and entry["target_center_x"] is None:
            raise ValueError("Positive detection cache entries require center_x.")
        return entry

    @staticmethod
    def _record_by_agent(
        detection_image_records: Iterable[Dict[str, object]],
    ) -> Dict[str, Dict[str, object]]:
        records = {}
        for record in detection_image_records:
            agent_id = str(record["agent_id"])
            if agent_id in records:
                raise ValueError("Duplicate detection image record for %s." % agent_id)
            records[agent_id] = record
        return records

    def lookup_step(
        self,
        *,
        scan_id: str,
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        detection_image_records: List[Dict[str, object]],
        detection_model: str,
        prompt_version: str = DETECTION_PROMPT_VERSION,
    ) -> Optional[List[Dict[str, object]]]:
        index = self._read_index()
        if not index:
            return None

        records_by_agent = self._record_by_agent(detection_image_records)
        detections_by_agent: Dict[str, Dict[str, List[object]]] = {}
        active_target_set_hash = self.active_target_set_hash(targets)

        for observation in agent_observations:
            agent_id = str(observation["agent_id"])
            record = records_by_agent[agent_id]
            viewpoint_id = str(
                record.get("current_viewpoint_id")
                or observation.get("current_viewpoint_id")
            )
            panorama_image_hash = str(record["image_sha256"])

            for target in targets:
                entry = self._entry(
                    scan_id=scan_id,
                    viewpoint_id=viewpoint_id,
                    active_target_set_hash=active_target_set_hash,
                    target=target,
                    detection_model=detection_model,
                    prompt_version=prompt_version,
                    panorama_image_hash=panorama_image_hash,
                    found=False,
                    target_center_x=None,
                    case_id="lookup",
                    step_index=0,
                    agent_id=agent_id,
                    viewpoint_index=record.get("current_viewpoint_index"),
                    service_tier=None,
                )
                cached = index.get(self._key_tuple(entry))
                if cached is None:
                    return None
                if bool(cached["found"]):
                    agent_result = detections_by_agent.setdefault(
                        agent_id,
                        {
                            "found_target_indices": [],
                            "target_center_xs": [],
                        },
                    )
                    agent_result["found_target_indices"].append(
                        str(target["target_id"])
                    )
                    agent_result["target_center_xs"].append(
                        float(cached["target_center_x"])
                    )

        detections = []
        for agent_id in sorted(detections_by_agent):
            result = detections_by_agent[agent_id]
            detections.append(
                {
                    "agent_id": agent_id,
                    "found_target_indices": result["found_target_indices"],
                    "target_center_xs": result["target_center_xs"],
                }
            )
        return detections

    def append_step(
        self,
        *,
        scan_id: str,
        case_id: str,
        step_index: int,
        agent_observations: List[Dict[str, object]],
        targets: List[Dict[str, object]],
        detection_image_records: List[Dict[str, object]],
        detections: List[Dict[str, object]],
        detection_model: str,
        prompt_version: str = DETECTION_PROMPT_VERSION,
        service_tier: object = None,
        source_run_id: object = None,
    ) -> int:
        index = self._read_index()
        conflict_keys = (
            self._read_conflict_keys()
            if self.conflict_policy == "quarantine"
            else set()
        )
        records_by_agent = self._record_by_agent(detection_image_records)
        active_target_set_hash = self.active_target_set_hash(targets)
        detections_by_agent_target: Dict[Tuple[str, str], float] = {}
        for detection in detections:
            agent_id = str(detection["agent_id"])
            found_target_indices = detection["found_target_indices"]
            target_center_xs = detection["target_center_xs"]
            for target_id, center_x in zip(found_target_indices, target_center_xs):
                detections_by_agent_target[(agent_id, str(target_id))] = float(center_x)

        entries_to_append = []
        for observation in agent_observations:
            agent_id = str(observation["agent_id"])
            record = records_by_agent[agent_id]
            viewpoint_id = str(
                record.get("current_viewpoint_id")
                or observation.get("current_viewpoint_id")
            )
            panorama_image_hash = str(record["image_sha256"])

            for target in targets:
                target_id = str(target["target_id"])
                target_center_x = detections_by_agent_target.get(
                    (agent_id, target_id)
                )
                entry = self._entry(
                    scan_id=scan_id,
                    viewpoint_id=viewpoint_id,
                    active_target_set_hash=active_target_set_hash,
                    target=target,
                    detection_model=detection_model,
                    prompt_version=prompt_version,
                    panorama_image_hash=panorama_image_hash,
                    found=target_center_x is not None,
                    target_center_x=target_center_x,
                    case_id=case_id,
                    step_index=step_index,
                    agent_id=agent_id,
                    viewpoint_index=record.get("current_viewpoint_index"),
                    service_tier=service_tier,
                    source_run_id=source_run_id,
                )
                key = self._key_tuple(entry)
                if key in conflict_keys:
                    continue
                existing = index.get(key)
                if existing is not None:
                    if self._result_tuple(existing) != self._result_tuple(entry):
                        if self.conflict_policy == "quarantine":
                            self._append_conflict(existing, entry)
                            conflict_keys.add(key)
                            index.pop(key, None)
                            continue
                        raise DetectionCacheConflictError(
                            self._conflict_message(existing, entry)
                        )
                    continue
                index[key] = entry
                entries_to_append.append(entry)

        if not entries_to_append:
            return 0

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            for entry in entries_to_append:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return len(entries_to_append)
