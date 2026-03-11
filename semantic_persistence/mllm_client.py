import base64
import io
import json
import os
import re

import numpy as np
from openai import BadRequestError, OpenAI
from PIL import Image
import debugpy


MAX_MLLM_INPUT_IMAGES = 5


class MLLMClient:
    def __init__(
        self,
        model_name: str = "meta-llama/Llama-4-Scout-17B-16E-Instruct:cheapest",
        base_url: str = "https://router.huggingface.co/v1",
        api_key_env: str = "HF_TOKEN",
        max_new_tokens: int = 2000,
        h_fov: float = -1.0,
        request_timeout: float = 120.0,
        save_debug_images: bool = True,
    ):
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Environment variable {api_key_env} is required for the Hugging Face router API."
            )

        self.model_name = model_name
        self.base_url = base_url
        self.max_new_tokens = max_new_tokens
        self.h_fov = h_fov
        self.request_timeout = request_timeout
        self.save_debug_images = save_debug_images
        self.client = OpenAI(
            base_url=base_url, api_key=api_key, timeout=request_timeout
        )

    @staticmethod
    def _strip_code_fences(raw_text: str) -> str:
        raw = raw_text.strip()
        if "```" not in raw:
            return raw
        lines = raw.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()

    @staticmethod
    def _is_complete_payload(obj) -> bool:
        if not isinstance(obj, dict):
            return False
        if "current_region" not in obj or "target" not in obj:
            return False
        return any(
            key in obj
            for key in (
                "updated_graph_context",
                "direction_heading_label",
                "visible_viewpoints",
                "hypothesis_regions",
                "neighbor_regions",
                "regions",
            )
        )

    def _try_parse_json(self, candidate_raw: str):
        try:
            parsed = json.loads(candidate_raw)
            if self._is_complete_payload(parsed):
                return parsed
        except Exception:
            pass

        for i in range(len(candidate_raw)):
            if candidate_raw[i] != "{":
                continue
            for j in range(len(candidate_raw), i, -1):
                if candidate_raw[j - 1] != "}":
                    continue
                candidate = candidate_raw[i:j]
                try:
                    parsed = json.loads(candidate)
                    if self._is_complete_payload(parsed):
                        return parsed
                except Exception:
                    continue
        return None

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

        for i in range(len(candidate_raw)):
            if candidate_raw[i] != "{":
                continue
            for j in range(len(candidate_raw), i, -1):
                if candidate_raw[j - 1] != "}":
                    continue
                candidate = candidate_raw[i:j]
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
        return f"data:image/png;base64,{encoded}"

    @staticmethod
    def _select_evenly_spaced_indices(total_count: int, sample_count: int) -> list[int]:
        if total_count <= 0 or sample_count <= 0:
            return []

        sample_count = min(total_count, sample_count)
        if sample_count == total_count:
            return list(range(total_count))

        import Helper

        step_rad = (2.0 * np.pi) / sample_count
        used_indices = set()
        selected_indices = []

        for sample_idx in range(sample_count):
            ideal_heading = sample_idx * step_rad
            index = int(round(ideal_heading / Helper.DELTA_HEADING_RAD)) % total_count

            if index in used_indices:
                fallback_index = int(
                    np.floor((sample_idx * total_count) / sample_count)
                )
                while (
                    fallback_index in used_indices and fallback_index < total_count - 1
                ):
                    fallback_index += 1
                while fallback_index in used_indices and fallback_index > 0:
                    fallback_index -= 1
                index = fallback_index

            selected_indices.append(index)
            used_indices.add(index)

        return selected_indices

    @staticmethod
    def _select_indices_with_viewpoint_coverage(
        total_count: int,
        sample_count: int,
        frame_viewpoint_indices: list[list[int]] | None = None,
        required_viewpoint_indices: list[int] | None = None,
    ) -> list[int]:
        if total_count <= 0 or sample_count <= 0:
            return []

        sample_count = min(total_count, sample_count)
        if sample_count == total_count:
            return list(range(total_count))

        frame_viewpoint_indices = frame_viewpoint_indices or []
        required = set(int(idx) for idx in (required_viewpoint_indices or []))
        if not frame_viewpoint_indices or not required:
            return MLLMClient._select_evenly_spaced_indices(total_count, sample_count)

        selected = []
        unused = set(range(total_count))
        uncovered = set(required)

        while uncovered and len(selected) < sample_count and unused:
            best_idx = None
            best_cover = set()
            for frame_idx in sorted(unused):
                visible = set(frame_viewpoint_indices[frame_idx])
                cover = uncovered & visible
                if best_idx is None or len(cover) > len(best_cover):
                    best_idx = frame_idx
                    best_cover = cover
                elif len(cover) == len(best_cover) and best_idx is not None:
                    if len(visible) > len(set(frame_viewpoint_indices[best_idx])):
                        best_idx = frame_idx
                        best_cover = cover
            if best_idx is None or not best_cover:
                break
            selected.append(best_idx)
            unused.remove(best_idx)
            uncovered -= best_cover

        evenly_spaced = MLLMClient._select_evenly_spaced_indices(
            total_count, sample_count
        )
        for frame_idx in evenly_spaced:
            if len(selected) >= sample_count:
                break
            if frame_idx not in selected:
                selected.append(frame_idx)

        if len(selected) < sample_count:
            for frame_idx in range(total_count):
                if len(selected) >= sample_count:
                    break
                if frame_idx not in selected:
                    selected.append(frame_idx)

        return sorted(selected[:sample_count])

    @staticmethod
    def _normalize_viewpoint_index(value) -> int | None:
        try:
            index = int(value)
        except (TypeError, ValueError):
            return None
        return index if index > 0 else None

    @staticmethod
    def _strip_grounded_suffix(label: str) -> str:
        label = str(label or "").strip()
        return re.sub(r"\s*-vp-\d+\s*$", "", label, flags=re.IGNORECASE).strip()

    @classmethod
    def _normalize_region_label(cls, value) -> str:
        label = cls._strip_grounded_suffix(value)
        label = " ".join(label.split())
        return label[:160]

    @classmethod
    def _build_grounded_label(
        cls, region_label: str, viewpoint_index: int | None
    ) -> str:
        region_label = cls._normalize_region_label(region_label)
        if not region_label:
            return ""
        if viewpoint_index is None:
            return region_label
        return f"{region_label}-vp-{int(viewpoint_index)}"

    @classmethod
    def _extract_viewpoint_index_from_label(cls, label: str) -> int | None:
        match = re.search(r"-vp-(\d+)\s*$", str(label or ""), flags=re.IGNORECASE)
        if match is None:
            return None
        return cls._normalize_viewpoint_index(match.group(1))

    def _build_instruction(
        self, num_obs_images: int, target_object: str, graph_context: dict | None = None
    ) -> str:
        target_object = target_object.strip()
        if target_object:
            target_line = (
                f'target: detect "{target_object}". '
                'If visible, return {"found":true,"views":[indices],"confidence":[]}; '
                'otherwise {"found":false,"views":[],"confidence":[]}.'
            )
        else:
            target_line = 'target: always {"found":false,"views":[],"confidence":[]}.'

        graph_context = self._normalize_standalone_graph_context(graph_context)
        graph_context_json = json.dumps(
            graph_context,
            separators=(",", ":"),
            ensure_ascii=True,
        )

        visited_labels = []
        prompt = (
            f"You are given {num_obs_images} indoor images from one 360-degree viewpoint "
            f"(indices 0-{max(0, num_obs_images - 1)}). "
            "Output compact JSON only. "
            "Each figure may contain a text number indicating the potential movement direction. "
            "The same text number can appear in multiple images, and the same text number refer to the same physical direction. "
            'Schema: {"current_region":{"label":""},"neighbor_regions":[{"label":"","prob":0.0,"target_prob":0.0}],'
            '"region_connections":[{"A":"","B":"","prob":0.0,"dist":0.0}],'
            '"target":{"found":false,"views":[],"confidence":[]},'
            '"direction_heading_label":[{"id":"","label":""}],"updated_graph_context":{}}. '
            "Use room/area labels only (no objects), e.g., kitchen area, living room area, bedroom area, bathroom area, hallway, dining area, entryway, corridor, office area. "
            "The graph_context is the persistent graph before this observation, taking the form: "
            '{"label_names":[],"label_existence_probs":[],"label_target_probs":[],"label_connection_ajacent_matrix":[],"label_connection_prob_ajacent_matrix":[],"label_distance_ajacent_matrix":[],"label_assigns":{"label_name":[assigned viewpoints indices]},"viewpoints_target_confidences":{"viewpoint_id":0.0}}. '
            "label_connection_prob_ajacent_matrix describes the probability that a direct connection exists between two regions"
            'For ajacent matrix and array, the index of rows and colums uses the index of labels in "label_names". '
            '"label_assigns" records the viewpoints assigned to each label. Each viewpoint can be at most assigned to one label. '
            "Some label can have empty assigned viewpoints if no observations match that label. "
            'Each item in "viewpoints_target_confidences" records the confidence that the target object is at that viewpoint. '
            "This confidence should be no larger than the confidence that the target is within the region label that the viewpoint is assigned. "
            f"The current graph context is: {graph_context_json}. "
            "current_region: one label for the region the current physical viewpoint is in. If current_region matches a label in graph_context, reuse that exact label. "
            f"{target_line} "
            "target: views = image indices where target confidence >0.5. confidence = list of detection confidences aligned with views. If no view has confidence >0.5 set found=false and return empty lists. "
            "neighbor_regions: up to 5, no duplicates, exclude current_region. Fields: label, prob [0.5,0.95] the probability the region exists, target_prob (0,1) the probability the target is at that region. Neighbor_regions should be new proposed regions induced from current observations that are not in graph_context. "
            "region_connections: include only hypothetical direct connections among the union of current_region, the listed new neighbors, and the existing label in graph_context only if strongly supported. Do not enumerate all pairs. Omit any pair if direct connectivity or travel distance is uncertain. Fields: A, B, prob in [0.5,1] the connection_probability, dist (>0 meters) the travel_distance. Connections are symmetric: output A->B only, not B->A. "
            'direction_heading_label: for each potential movement direction, output its text number id and the region label it heads to. Use the form [{"id":"","label":""}]. The label must be current_region, a label in graph_context, or a label in neighbor_regions. '
            "updated_graph_context: update graph_context using the current observation and keep it fully consistent with the other output fields. Strictly follow the graph_context format. Append any new labels to label_names in alphabetical order, and keep all arrays, matrices, assignments, and probabilities aligned with the final label_names order. "
            f"Labels have been visited are: {visited_labels}. For each visited label, its prob=1 meaning it must exist."
            "Return JSON only. No explanation or markdown."
        )

        debugpy.breakpoint()
        return prompt

    @staticmethod
    def _normalize_target_output(target: dict, index_map: list[int]) -> dict:
        raw_views = target.get("views", [])
        if not isinstance(raw_views, list):
            raw_views = [raw_views]

        raw_confidences = target.get("confidence", [])
        if isinstance(raw_confidences, list):
            confidence_candidates = raw_confidences
        elif raw_confidences is None:
            confidence_candidates = []
        else:
            confidence_candidates = [raw_confidences]

        normalized_pairs = []
        for idx, raw_view in enumerate(raw_views):
            try:
                sampled_view_idx = int(raw_view)
            except (TypeError, ValueError):
                continue

            if not (0 <= sampled_view_idx < len(index_map)):
                continue

            confidence_value = 0.0
            if idx < len(confidence_candidates):
                try:
                    confidence_value = float(confidence_candidates[idx])
                except (TypeError, ValueError):
                    confidence_value = 0.0
            elif len(confidence_candidates) == 1:
                try:
                    confidence_value = float(confidence_candidates[0])
                except (TypeError, ValueError):
                    confidence_value = 0.0

            normalized_pairs.append(
                (int(index_map[sampled_view_idx]), float(confidence_value))
            )

        best_confidence_by_view = {}
        for view_idx, confidence_value in normalized_pairs:
            if confidence_value <= 0.5:
                continue
            previous = best_confidence_by_view.get(view_idx)
            if previous is None or confidence_value > previous:
                best_confidence_by_view[view_idx] = confidence_value

        deduped_views = list(best_confidence_by_view.keys())
        deduped_confidences = [
            float(best_confidence_by_view[view_idx]) for view_idx in deduped_views
        ]

        best_view = -1
        if deduped_views:
            best_pair = max(
                zip(deduped_views, deduped_confidences), key=lambda pair: pair[1]
            )
            best_view = int(best_pair[0])

        return {
            "found": bool(deduped_views),
            "view": best_view,
            "views": deduped_views,
            "confidence": deduped_confidences,
        }

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        """Convert arbitrary model fields to float while staying robust to bad JSON."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _normalize_note(value) -> str:
        """Keep model-generated notes short and single-line for downstream logging."""
        note = str(value or "").strip()
        note = " ".join(note.split())
        return note[:160]

    @staticmethod
    def _normalize_node_id(value) -> str:
        """Normalize optional node ids returned by the prompt context matching step."""
        return str(value or "").strip()

    @staticmethod
    def _clamp_float(value, low: float, high: float, default: float) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = float(default)
        return max(low, min(high, value))

    @classmethod
    def _canonical_label_key(cls, value) -> str:
        label = cls._normalize_region_label(value).lower()
        label = re.sub(r"[^a-z0-9\s]+", " ", label)
        label = re.sub(r"\s+", " ", label)
        return label.strip()

    @classmethod
    def _build_label_lookup(cls, labels: list[str]) -> dict[str, str]:
        lookup = {}
        for label in labels or []:
            normalized = cls._normalize_region_label(label)
            key = cls._canonical_label_key(normalized)
            if key and key not in lookup:
                lookup[key] = normalized
        return lookup

    @classmethod
    def _resolve_label(cls, value, label_lookup: dict[str, str] | None = None) -> str:
        normalized = cls._normalize_region_label(value)
        if not normalized:
            return ""
        if not label_lookup:
            return normalized
        return label_lookup.get(cls._canonical_label_key(normalized), normalized)

    @staticmethod
    def _empty_graph_context() -> dict:
        return {
            "label_names": [],
            "label_existence_probs": [],
            "label_target_probs": [],
            "label_connection_ajacent_matrix": [],
            "label_distance_ajacent_matrix": [],
            "label_assigns": {},
            "viewpoints_target_confidences": {},
        }

    @classmethod
    def _normalize_standalone_graph_context(cls, raw_context) -> dict:
        if not isinstance(raw_context, dict):
            return cls._empty_graph_context()

        raw_labels = raw_context.get("label_names", []) or []
        raw_existence = raw_context.get("label_existence_probs", []) or []
        raw_target = raw_context.get("label_target_probs", []) or []
        raw_connection = raw_context.get("label_connection_ajacent_matrix", []) or []
        raw_distance = raw_context.get("label_distance_ajacent_matrix", []) or []
        raw_assigns = raw_context.get("label_assigns", {}) or {}
        raw_view_confidences = (
            raw_context.get("viewpoints_target_confidences", {}) or {}
        )

        canonical_to_label = {}
        raw_index_by_key = {}
        for idx, raw_label in enumerate(raw_labels):
            label = cls._normalize_region_label(raw_label)
            key = cls._canonical_label_key(label)
            if not key or key in canonical_to_label:
                continue
            canonical_to_label[key] = label
            raw_index_by_key[key] = idx

        label_names = sorted(canonical_to_label.values(), key=lambda item: item.lower())
        label_lookup = cls._build_label_lookup(label_names)

        existence_map = {}
        target_map = {}
        for label in label_names:
            key = cls._canonical_label_key(label)
            raw_idx = raw_index_by_key.get(key, -1)
            raw_exist = (
                raw_existence[raw_idx] if 0 <= raw_idx < len(raw_existence) else 0.5
            )
            raw_tgt = raw_target[raw_idx] if 0 <= raw_idx < len(raw_target) else 0.0
            existence_map[label] = cls._clamp_float(raw_exist, 0.0, 1.0, 0.5)
            target_map[label] = cls._clamp_float(raw_tgt, 0.0, 1.0, 0.0)

        label_assigns = {label: [] for label in label_names}
        assigned_viewpoints = set()
        for raw_label, raw_values in raw_assigns.items():
            label = cls._resolve_label(raw_label, label_lookup)
            if not label:
                continue
            candidates = raw_values if isinstance(raw_values, list) else [raw_values]
            cleaned = []
            for value in candidates:
                viewpoint_index = cls._normalize_viewpoint_index(value)
                if viewpoint_index is None or viewpoint_index in assigned_viewpoints:
                    continue
                assigned_viewpoints.add(viewpoint_index)
                cleaned.append(int(viewpoint_index))
            label_assigns[label] = sorted(cleaned)

        edge_map = {}
        distance_map = {}
        for label_a in label_names:
            key_a = cls._canonical_label_key(label_a)
            raw_idx_a = raw_index_by_key.get(key_a, -1)
            if raw_idx_a < 0:
                continue
            for label_b in label_names:
                key_b = cls._canonical_label_key(label_b)
                raw_idx_b = raw_index_by_key.get(key_b, -1)
                if raw_idx_b < 0 or label_a == label_b:
                    continue
                conn_candidates = []
                dist_candidates = []
                if (
                    isinstance(raw_connection, list)
                    and raw_idx_a < len(raw_connection)
                    and isinstance(raw_connection[raw_idx_a], list)
                    and raw_idx_b < len(raw_connection[raw_idx_a])
                ):
                    conn_candidates.append(raw_connection[raw_idx_a][raw_idx_b])
                if (
                    isinstance(raw_distance, list)
                    and raw_idx_a < len(raw_distance)
                    and isinstance(raw_distance[raw_idx_a], list)
                    and raw_idx_b < len(raw_distance[raw_idx_a])
                ):
                    dist_candidates.append(raw_distance[raw_idx_a][raw_idx_b])
                pair_key = tuple(
                    sorted((label_a, label_b), key=lambda item: item.lower())
                )
                prob = max(
                    (
                        cls._clamp_float(value, 0.0, 1.0, 0.0)
                        for value in conn_candidates
                    ),
                    default=0.0,
                )
                dist_values = []
                for value in dist_candidates:
                    dist = cls._clamp_float(value, 0.0, 1e6, 0.0)
                    if dist > 0.0:
                        dist_values.append(dist)
                if prob > 0.0 and dist_values:
                    edge_map[pair_key] = prob
                    distance_map[pair_key] = min(dist_values)

        viewpoint_owner = {}
        for label, assignments in label_assigns.items():
            for viewpoint_index in assignments:
                viewpoint_owner[int(viewpoint_index)] = label

        viewpoints_target_confidences = {}
        for raw_key, raw_value in raw_view_confidences.items():
            viewpoint_index = cls._normalize_viewpoint_index(raw_key)
            if viewpoint_index is None or viewpoint_index not in viewpoint_owner:
                continue
            label = viewpoint_owner[viewpoint_index]
            value = cls._clamp_float(raw_value, 0.0, target_map.get(label, 0.0), 0.0)
            viewpoints_target_confidences[str(int(viewpoint_index))] = value

        label_index = {label: idx for idx, label in enumerate(label_names)}
        size = len(label_names)
        connection_matrix = [[0.0 for _ in range(size)] for _ in range(size)]
        distance_matrix = [[0.0 for _ in range(size)] for _ in range(size)]
        for (label_a, label_b), prob in edge_map.items():
            idx_a = label_index[label_a]
            idx_b = label_index[label_b]
            dist = distance_map.get((label_a, label_b), 0.0)
            if prob <= 0.0 or dist <= 0.0:
                continue
            connection_matrix[idx_a][idx_b] = prob
            connection_matrix[idx_b][idx_a] = prob
            distance_matrix[idx_a][idx_b] = dist
            distance_matrix[idx_b][idx_a] = dist

        return {
            "label_names": label_names,
            "label_existence_probs": [
                float(existence_map.get(label, 0.5)) for label in label_names
            ],
            "label_target_probs": [
                float(target_map.get(label, 0.0)) for label in label_names
            ],
            "label_connection_ajacent_matrix": connection_matrix,
            "label_distance_ajacent_matrix": distance_matrix,
            "label_assigns": {
                label: sorted(label_assigns.get(label, [])) for label in label_names
            },
            "viewpoints_target_confidences": {
                key: viewpoints_target_confidences[key]
                for key in sorted(
                    viewpoints_target_confidences.keys(), key=lambda item: int(item)
                )
            },
        }

    @classmethod
    def _normalize_neighbor_regions_payload(
        cls,
        raw_regions,
        prior_graph_context: dict,
        current_region_label: str,
        topk: int,
    ) -> list[dict]:
        prior_lookup = cls._build_label_lookup(
            prior_graph_context.get("label_names", [])
        )
        current_key = cls._canonical_label_key(current_region_label)
        normalized_by_key = {}

        for region in raw_regions or []:
            label = cls._normalize_region_label(region.get("label", ""))
            key = cls._canonical_label_key(label)
            if not key or key == current_key or key in prior_lookup:
                continue

            normalized = {
                "label": label,
                "prob": cls._clamp_float(
                    region.get("prob", region.get("existence_prob", 0.5)),
                    0.5,
                    0.95,
                    0.5,
                ),
                "target_prob": cls._clamp_float(
                    region.get("target_prob", 0.0),
                    0.0,
                    1.0,
                    0.0,
                ),
            }

            previous = normalized_by_key.get(key)
            if previous is None:
                normalized_by_key[key] = normalized
                continue

            previous["prob"] = max(previous["prob"], normalized["prob"])
            previous["target_prob"] = max(
                previous["target_prob"], normalized["target_prob"]
            )

        normalized_regions = list(normalized_by_key.values())
        normalized_regions.sort(
            key=lambda item: (item["target_prob"], item["prob"], item["label"].lower()),
            reverse=True,
        )
        return normalized_regions[:topk]

    @classmethod
    def _normalize_region_connections_payload(
        cls,
        raw_connections,
        allowed_labels: list[str],
    ) -> list[dict]:
        label_lookup = cls._build_label_lookup(allowed_labels)
        allowed_set = set(allowed_labels)
        normalized_by_pair = {}

        for connection in raw_connections or []:
            label_a = cls._resolve_label(
                connection.get("A", connection.get("region_a", "")), label_lookup
            )
            label_b = cls._resolve_label(
                connection.get("B", connection.get("region_b", "")), label_lookup
            )
            if (
                not label_a
                or not label_b
                or label_a == label_b
                or label_a not in allowed_set
                or label_b not in allowed_set
            ):
                continue

            prob = cls._clamp_float(
                connection.get("prob", connection.get("connection_prob", 0.0)),
                0.5,
                1.0,
                0.5,
            )
            dist = cls._clamp_float(
                connection.get("dist", connection.get("travel_distance", 0.0)),
                0.0,
                1e6,
                0.0,
            )
            if dist <= 0.0:
                continue

            pair_key = tuple(sorted((label_a, label_b), key=lambda item: item.lower()))
            normalized = {"A": label_a, "B": label_b, "prob": prob, "dist": dist}
            previous = normalized_by_pair.get(pair_key)
            if previous is None:
                normalized_by_pair[pair_key] = normalized
                continue

            previous["prob"] = max(previous["prob"], normalized["prob"])
            previous["dist"] = min(previous["dist"], normalized["dist"])

        normalized_connections = list(normalized_by_pair.values())
        normalized_connections.sort(
            key=lambda item: (
                item["prob"],
                -item["dist"],
                item["A"].lower(),
                item["B"].lower(),
            ),
            reverse=True,
        )
        return normalized_connections

    @classmethod
    def _normalize_direction_heading_payload(
        cls,
        raw_directions,
        allowed_labels: list[str],
        viewpoint_context: dict | None = None,
    ) -> list[dict]:
        if isinstance(raw_directions, dict):
            raw_directions = [
                {"id": key, "label": value} for key, value in raw_directions.items()
            ]

        viewpoint_context = viewpoint_context or {}
        valid_direction_ids = {
            str(int(item["viewpoint_index"]))
            for item in viewpoint_context.get("visible_viewpoints", []) or []
            if cls._normalize_viewpoint_index(item.get("viewpoint_index")) is not None
        }
        label_lookup = cls._build_label_lookup(allowed_labels)
        allowed_set = set(allowed_labels)
        normalized_by_id = {}

        for entry in raw_directions or []:
            raw_id = str(entry.get("id", "")).strip()
            match = re.search(r"(\d+)", raw_id)
            if match is None:
                continue
            direction_id = str(int(match.group(1)))
            if valid_direction_ids and direction_id not in valid_direction_ids:
                continue

            label = cls._resolve_label(entry.get("label", ""), label_lookup)
            if not label or label not in allowed_set:
                continue

            normalized_by_id[direction_id] = {"id": direction_id, "label": label}

        return [
            normalized_by_id[key]
            for key in sorted(normalized_by_id.keys(), key=lambda item: int(item))
        ]

    @classmethod
    def _normalize_updated_graph_context(
        cls,
        raw_context,
        *,
        prior_graph_context: dict | None = None,
        current_region_label: str = "",
        neighbor_regions: list[dict] | None = None,
        region_connections: list[dict] | None = None,
        target: dict | None = None,
        viewpoint_context: dict | None = None,
    ) -> dict:
        prior_context = cls._normalize_standalone_graph_context(prior_graph_context)
        candidate_context = cls._normalize_standalone_graph_context(raw_context)
        if candidate_context["label_names"] or not prior_context["label_names"]:
            base_context = candidate_context
        else:
            base_context = prior_context

        labels = list(base_context["label_names"])
        existence_map = {
            label: float(base_context["label_existence_probs"][idx])
            for idx, label in enumerate(labels)
        }
        target_map = {
            label: float(base_context["label_target_probs"][idx])
            for idx, label in enumerate(labels)
        }
        label_assigns = {
            label: list(base_context["label_assigns"].get(label, []))
            for label in labels
        }
        edge_map = {}
        distance_map = {}
        for i, label_a in enumerate(labels):
            for j in range(i + 1, len(labels)):
                label_b = labels[j]
                prob = cls._clamp_float(
                    base_context["label_connection_ajacent_matrix"][i][j],
                    0.0,
                    1.0,
                    0.0,
                )
                dist = cls._clamp_float(
                    base_context["label_distance_ajacent_matrix"][i][j],
                    0.0,
                    1e6,
                    0.0,
                )
                if prob > 0.0 and dist > 0.0:
                    pair_key = tuple(
                        sorted((label_a, label_b), key=lambda item: item.lower())
                    )
                    edge_map[pair_key] = prob
                    distance_map[pair_key] = dist

        viewpoints_target_confidences = dict(
            base_context["viewpoints_target_confidences"]
        )

        def ensure_label(
            raw_label, existence_default: float = 0.5, target_default: float = 0.0
        ) -> str:
            nonlocal labels
            label_lookup = cls._build_label_lookup(labels)
            label = cls._resolve_label(raw_label, label_lookup)
            if not label:
                return ""
            if label not in existence_map:
                labels.append(label)
                existence_map[label] = cls._clamp_float(
                    existence_default, 0.0, 1.0, 0.5
                )
                target_map[label] = cls._clamp_float(target_default, 0.0, 1.0, 0.0)
                label_assigns[label] = []
            return label

        current_label = ensure_label(current_region_label, 0.95, 0.0)
        if current_label:
            existence_map[current_label] = max(
                existence_map.get(current_label, 0.0), 0.95
            )

        for region in neighbor_regions or []:
            label = ensure_label(
                region.get("label", ""),
                region.get("prob", 0.5),
                region.get("target_prob", 0.0),
            )
            if not label:
                continue
            existence_map[label] = max(
                existence_map.get(label, 0.0),
                cls._clamp_float(region.get("prob", 0.5), 0.5, 0.95, 0.5),
            )
            target_map[label] = max(
                target_map.get(label, 0.0),
                cls._clamp_float(region.get("target_prob", 0.0), 0.0, 1.0, 0.0),
            )

        max_target_confidence = 0.0
        if isinstance(target, dict):
            confidence_values = target.get("confidence", []) or []
            if confidence_values:
                max_target_confidence = max(
                    cls._clamp_float(value, 0.0, 1.0, 0.0)
                    for value in confidence_values
                )
        if current_label and max_target_confidence > 0.0:
            target_map[current_label] = max(
                target_map.get(current_label, 0.0), max_target_confidence
            )

        for connection in region_connections or []:
            label_a = ensure_label(connection.get("A", ""), 0.5, 0.0)
            label_b = ensure_label(connection.get("B", ""), 0.5, 0.0)
            if not label_a or not label_b or label_a == label_b:
                continue
            pair_key = tuple(sorted((label_a, label_b), key=lambda item: item.lower()))
            edge_map[pair_key] = max(
                edge_map.get(pair_key, 0.0),
                cls._clamp_float(connection.get("prob", 0.5), 0.5, 1.0, 0.5),
            )
            dist = cls._clamp_float(connection.get("dist", 0.0), 0.0, 1e6, 0.0)
            if dist > 0.0:
                previous_dist = distance_map.get(pair_key, 0.0)
                distance_map[pair_key] = (
                    dist if previous_dist <= 0.0 else min(previous_dist, dist)
                )

        viewpoint_context = viewpoint_context or {}
        current_viewpoint_index = cls._normalize_viewpoint_index(
            viewpoint_context.get("current_viewpoint_index")
        )
        if current_viewpoint_index is not None and current_label:
            for label in label_assigns:
                label_assigns[label] = [
                    value
                    for value in label_assigns.get(label, [])
                    if int(value) != int(current_viewpoint_index)
                ]
            label_assigns[current_label] = sorted(
                set(label_assigns.get(current_label, []))
                | {int(current_viewpoint_index)}
            )

        label_order_for_assignment = []
        if current_label:
            label_order_for_assignment.append(current_label)
        label_order_for_assignment.extend(
            sorted(
                [label for label in labels if label != current_label],
                key=lambda item: item.lower(),
            )
        )
        seen_assignments = set()
        for label in label_order_for_assignment:
            cleaned = []
            for value in sorted(set(label_assigns.get(label, []))):
                viewpoint_index = cls._normalize_viewpoint_index(value)
                if viewpoint_index is None or viewpoint_index in seen_assignments:
                    continue
                cleaned.append(int(viewpoint_index))
                seen_assignments.add(int(viewpoint_index))
            label_assigns[label] = cleaned

        if (
            current_viewpoint_index is not None
            and current_label
            and max_target_confidence > 0.0
        ):
            viewpoints_target_confidences[str(int(current_viewpoint_index))] = (
                max_target_confidence
            )

        viewpoint_owner = {}
        for label, assignments in label_assigns.items():
            for viewpoint_index in assignments:
                viewpoint_owner[int(viewpoint_index)] = label

        for key in list(viewpoints_target_confidences.keys()):
            viewpoint_index = cls._normalize_viewpoint_index(key)
            if viewpoint_index is None or viewpoint_index not in viewpoint_owner:
                viewpoints_target_confidences.pop(key, None)
                continue
            owner_label = viewpoint_owner[viewpoint_index]
            viewpoints_target_confidences[str(int(viewpoint_index))] = cls._clamp_float(
                viewpoints_target_confidences[key],
                0.0,
                target_map.get(owner_label, 0.0),
                0.0,
            )
            if str(int(viewpoint_index)) != key:
                viewpoints_target_confidences.pop(key, None)

        final_labels = sorted(set(labels), key=lambda item: item.lower())
        label_index = {label: idx for idx, label in enumerate(final_labels)}
        size = len(final_labels)
        connection_matrix = [[0.0 for _ in range(size)] for _ in range(size)]
        distance_matrix = [[0.0 for _ in range(size)] for _ in range(size)]
        for pair_key, prob in edge_map.items():
            dist = distance_map.get(pair_key, 0.0)
            if prob <= 0.0 or dist <= 0.0:
                continue
            label_a, label_b = pair_key
            idx_a = label_index[label_a]
            idx_b = label_index[label_b]
            connection_matrix[idx_a][idx_b] = prob
            connection_matrix[idx_b][idx_a] = prob
            distance_matrix[idx_a][idx_b] = dist
            distance_matrix[idx_b][idx_a] = dist

        return {
            "label_names": final_labels,
            "label_existence_probs": [
                float(existence_map.get(label, 0.5)) for label in final_labels
            ],
            "label_target_probs": [
                float(target_map.get(label, 0.0)) for label in final_labels
            ],
            "label_connection_ajacent_matrix": connection_matrix,
            "label_distance_ajacent_matrix": distance_matrix,
            "label_assigns": {
                label: list(label_assigns.get(label, [])) for label in final_labels
            },
            "viewpoints_target_confidences": {
                key: viewpoints_target_confidences[key]
                for key in sorted(
                    viewpoints_target_confidences.keys(), key=lambda item: int(item)
                )
            },
        }

    @classmethod
    def _normalize_visible_viewpoints(
        cls,
        visible_viewpoints,
        viewpoint_context: dict | None,
    ) -> tuple[list[dict], dict[str, str]]:
        viewpoint_context = viewpoint_context or {}
        visible_infos = viewpoint_context.get("visible_viewpoints", []) or []
        viewpoint_id_by_index = {
            int(item["viewpoint_index"]): str(item["viewpoint_id"])
            for item in visible_infos
            if cls._normalize_viewpoint_index(item.get("viewpoint_index")) is not None
        }
        required_indices = sorted(viewpoint_id_by_index.keys())

        normalized_by_index = {}
        label_aliases = {}
        for entry in visible_viewpoints or []:
            raw_label = str(entry.get("label", "")).strip()
            viewpoint_index = cls._normalize_viewpoint_index(
                entry.get("viewpoint_index")
            )
            if viewpoint_index is None:
                viewpoint_index = cls._extract_viewpoint_index_from_label(raw_label)
            if viewpoint_index is None or viewpoint_index not in viewpoint_id_by_index:
                continue

            region_label = cls._normalize_region_label(
                entry.get("region_label", "") or raw_label
            )
            if not region_label:
                continue

            label = cls._build_grounded_label(region_label, viewpoint_index)
            normalized = {
                "node_id": cls._normalize_node_id(entry.get("node_id", "")),
                "viewpoint_index": int(viewpoint_index),
                "viewpoint_id": viewpoint_id_by_index[int(viewpoint_index)],
                "region_label": region_label,
                "label": label,
                "existence_prob": cls._safe_float(
                    entry.get("existence_prob", entry.get("confidence", 0.0)),
                    0.0,
                ),
                "target_prob": cls._safe_float(entry.get("target_prob", 0.0), 0.0),
                "note": cls._normalize_note(entry.get("note", "")),
            }

            previous = normalized_by_index.get(int(viewpoint_index))
            if previous is None:
                normalized_by_index[int(viewpoint_index)] = normalized
            else:
                if not previous["node_id"] and normalized["node_id"]:
                    previous["node_id"] = normalized["node_id"]
                previous["existence_prob"] = max(
                    previous["existence_prob"], normalized["existence_prob"]
                )
                previous["target_prob"] = max(
                    previous["target_prob"], normalized["target_prob"]
                )
                if normalized["note"] and not previous["note"]:
                    previous["note"] = normalized["note"]
                previous["region_label"] = normalized["region_label"]
                previous["label"] = normalized["label"]

            label_aliases[str(raw_label)] = label
            label_aliases[str(region_label)] = label
            label_aliases[str(label)] = label

        for viewpoint_index in required_indices:
            if viewpoint_index in normalized_by_index:
                continue
            region_label = f"unresolved area-{int(viewpoint_index)}"
            label = cls._build_grounded_label(region_label, viewpoint_index)
            normalized_by_index[viewpoint_index] = {
                "node_id": "",
                "viewpoint_index": int(viewpoint_index),
                "viewpoint_id": viewpoint_id_by_index[int(viewpoint_index)],
                "region_label": region_label,
                "label": label,
                "existence_prob": 0.5,
                "target_prob": 0.0,
                "note": "auto-filled because the model omitted this visible viewpoint",
            }
            label_aliases[region_label] = label
            label_aliases[label] = label

        normalized = [
            normalized_by_index[idx] for idx in sorted(normalized_by_index.keys())
        ]
        return normalized, label_aliases

    @classmethod
    def _normalize_hypothesis_regions(
        cls,
        hypothesis_regions,
        topk: int,
    ) -> tuple[list[dict], dict[str, str]]:
        normalized_by_key = {}
        label_aliases = {}

        for region in hypothesis_regions or []:
            raw_label = str(region.get("label", "")).strip()
            label = cls._normalize_region_label(raw_label)
            if not label:
                continue

            node_id = cls._normalize_node_id(region.get("node_id", ""))
            dedupe_key = node_id or label.lower()
            normalized = {
                "node_id": node_id,
                "label": label,
                "existence_prob": cls._safe_float(
                    region.get("existence_prob", region.get("confidence", 0.0)),
                    0.0,
                ),
                "target_prob": cls._safe_float(region.get("target_prob", 0.0), 0.0),
                "note": cls._normalize_note(region.get("note", "")),
            }

            previous = normalized_by_key.get(dedupe_key)
            if previous is None:
                normalized_by_key[dedupe_key] = normalized
                continue

            if not previous["node_id"] and normalized["node_id"]:
                previous["node_id"] = normalized["node_id"]
            previous["existence_prob"] = max(
                previous["existence_prob"], normalized["existence_prob"]
            )
            previous["target_prob"] = max(
                previous["target_prob"], normalized["target_prob"]
            )
            if normalized["note"] and not previous["note"]:
                previous["note"] = normalized["note"]

            label_aliases[str(raw_label)] = label
            label_aliases[label] = label

        normalized_hypotheses = list(normalized_by_key.values())
        normalized_hypotheses.sort(
            key=lambda item: (item["target_prob"], item["existence_prob"]),
            reverse=True,
        )
        return normalized_hypotheses[:topk], label_aliases

    @classmethod
    def _normalize_region_connections(
        cls,
        region_connections,
        label_aliases: dict[str, str] | None = None,
    ) -> list[dict]:
        normalized_by_pair = {}
        label_aliases = label_aliases or {}

        for connection in region_connections or []:
            raw_a = str(connection.get("region_a", "")).strip()
            raw_b = str(connection.get("region_b", "")).strip()
            if not raw_a or not raw_b:
                continue

            region_a = label_aliases.get(raw_a, raw_a)
            region_b = label_aliases.get(raw_b, raw_b)
            if region_a == region_b:
                continue

            pair_key = tuple(sorted((region_a.lower(), region_b.lower())))
            if pair_key[0] == pair_key[1]:
                continue

            travel_distance = cls._safe_float(
                connection.get("travel_distance", -1.0), -1.0
            )
            if travel_distance <= 0.0:
                continue

            normalized = {
                "region_a": region_a,
                "region_b": region_b,
                "connection_prob": cls._safe_float(
                    connection.get("connection_prob", 0.0), 0.0
                ),
                "travel_distance": travel_distance,
            }

            previous = normalized_by_pair.get(pair_key)
            if previous is None:
                normalized_by_pair[pair_key] = normalized
                continue

            if normalized["connection_prob"] > previous["connection_prob"]:
                previous["connection_prob"] = normalized["connection_prob"]
                previous["region_a"] = normalized["region_a"]
                previous["region_b"] = normalized["region_b"]

            previous["travel_distance"] = min(
                previous["travel_distance"], normalized["travel_distance"]
            )

        normalized_connections = list(normalized_by_pair.values())
        normalized_connections.sort(
            key=lambda item: (item["connection_prob"], -item["travel_distance"]),
            reverse=True,
        )
        return normalized_connections

    def _build_distance_instruction(self, target_object: str) -> str:
        """
        Build a short distance-estimation prompt for one aligned RGB/depth pair.

        The target has already been detected before this call, so the prompt only
        asks the model to read the distance, not to decide whether the target exists.
        """

        target_object = target_object.strip()

        debugpy.breakpoint()

        # prompt = (
        #     f"Two aligned images are provided: RGB first, depth second. The target object {target_object} is present in the RGB image."
        #     "First use an open-vocabulary detection tool on the RGB image with the target name to detect the object and obtain bounding boxes. Select the single box with the highest detection confidence."
        #     "Then estimate the object distance using the aligned depth image. Collect all valid depth pixel values inside the selected bounding box. Use the median depth value inside the box as the measurement. "
        #     "Depth conversion rule:"
        #     "distance_m = median(depth_pixel_value in the last channel) / 4000.0. "
        #     "Rules: use RGB only for detection and depth only for distance. Do not estimate distance from RGB. Do not use pixels outside the selected box. Ignore invalid depth pixels. Do not verify whether the object exists. "
        #     "Return only valid JSON with exactly one key: "
        #     '{"distance_m": 2.37}. '
        #     "Do not output any other text."
        # )

        prompt = (
            f'Target: "{target_object}". '
            "Two aligned images are provided: RGB first, depth second. "
            "The target is definitely visible in RGB, so do not verify presence. "
            "Use RGB to locate the target, then estimate distance from depth. "
            "Depth conversion: meters = pixel_value in the last dimension / 4000.0. "
            'Return only valid JSON with exactly one key: "distance_m". '
            'Example valid outputs: {"distance_m": 2.37}. '
            "Do not output any other text."
        )

        debugpy.breakpoint()

        return prompt

    def _request_completion(self, content_items, max_tokens: int) -> str:
        """
        Sends a chat completion request to the Hugging Face router API with the given content items and max tokens.
        Returns the text content of the response message.
        """
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": content_items}],
                temperature=0.0,
                seed=42,
            )
        except BadRequestError as exc:
            message = str(exc)
            if "model_not_found" in message or "does not exist" in message:
                raise RuntimeError(
                    "The configured Hugging Face router model was not found. "
                    f"Resolved model='{self.model_name}'. "
                    "Use the full repo id, for example "
                    "'meta-llama/Llama-4-Scout-17B-16E-Instruct'."
                ) from exc
            raise
        return self._message_to_text(completion.choices[0].message.content)

    def propose_semantic_nodes(
        self,
        observation_images: list[np.ndarray],
        depth_images: list[np.ndarray] | None = None,
        topk: int = 5,
        target_object: str | None = None,
        graph_context: dict | None = None,
        viewpoint_context: dict | None = None,
    ):
        """
        observation_images: list of RGB uint8 arrays (H,W,3), typically horizon scan frames.

        Returns a dict with grounded visible viewpoints separated from ungrounded
        hypothesis regions so downstream navigation can stay physically consistent.
        """

        viewpoint_context = viewpoint_context or {}

        pil_images = []
        pil_depths = []
        for img in observation_images:
            if img is None:
                continue
            if img.dtype != np.uint8:
                img = img.astype(np.uint8)
            pil_images.append(Image.fromarray(img))

        for depth_img in depth_images or []:
            if depth_img is None:
                continue

            if depth_img.ndim == 3:
                depth_img = depth_img[:, :, 0]

            if depth_img.dtype == np.float32 or depth_img.dtype == np.float64:
                depth_img = np.clip(depth_img * 4000.0, 0, 65535).astype(np.uint16)
            elif depth_img.dtype != np.uint16:
                depth_img = depth_img.astype(np.uint16)

            pil_depths.append(Image.fromarray(depth_img, mode="I;16"))

        index_map = list(range(len(pil_images)))

        if self.h_fov > 0:
            target_count = int(np.ceil((2.0 * np.pi) / self.h_fov))
            target_count = max(1, min(MAX_MLLM_INPUT_IMAGES, target_count))

            if len(pil_images) > target_count:
                idx = self._select_indices_with_viewpoint_coverage(
                    total_count=len(pil_images),
                    sample_count=target_count,
                    frame_viewpoint_indices=viewpoint_context.get(
                        "frame_visible_viewpoint_indices", []
                    ),
                    required_viewpoint_indices=[
                        int(item["viewpoint_index"])
                        for item in viewpoint_context.get("visible_viewpoints", [])
                        or []
                        if self._normalize_viewpoint_index(item.get("viewpoint_index"))
                        is not None
                    ],
                )
                pil_images = [pil_images[i] for i in idx]
                index_map = [index_map[i] for i in idx]
                if pil_depths:
                    pil_depths = [pil_depths[i] for i in idx]
        else:
            idx = list(range(0, len(pil_images), 8))
            pil_images = [pil_images[i] for i in idx]
            index_map = [index_map[i] for i in idx]
            if pil_depths:
                pil_depths = [pil_depths[i] for i in idx]

        if self.save_debug_images:
            for i, im in enumerate(pil_images):
                im.save(f"debug_horizon_image_{i}.png")
            for i, depth in enumerate(pil_depths):
                depth.save(f"debug_horizon_depth_{i}.png")

        num_obs_images = len(pil_images)
        instruction = self._build_instruction(
            num_obs_images=num_obs_images,
            target_object=target_object or "",
            graph_context=graph_context,
        )

        content_items = [{"type": "text", "text": instruction}]
        for image in pil_images:
            content_items.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._image_to_data_url(image)},
                }
            )

        decoded = self._request_completion(content_items, self.max_new_tokens)
        print("\n[MLLM RAW OUTPUT]\n", decoded)

        raw = self._strip_code_fences(decoded)
        payload = self._try_parse_json(raw)

        needs_retry = (
            payload is None
            or raw.count("{") > raw.count("}")
            or not raw.rstrip().endswith("}")
        )
        if needs_retry:
            retry_tokens = min(max(self.max_new_tokens * 2, 768), 1536)
            decoded = self._request_completion(content_items, retry_tokens)
            print("\n[MLLM RAW OUTPUT RETRY]\n", decoded)
            raw = self._strip_code_fences(decoded)
            payload = self._try_parse_json(raw)

        prior_graph_context = self._normalize_standalone_graph_context(graph_context)

        if payload is None:
            print("[MLLM] Failed to parse JSON. Raw output:")
            print(decoded)
            return {
                "current_region": {"label": ""},
                "neighbor_regions": [],
                "region_connections": [],
                "target": {"found": False, "view": -1, "views": [], "confidence": []},
                "direction_heading_label": [],
                "updated_graph_context": prior_graph_context,
            }

        current_region = payload.get("current_region", {}) or {}
        raw_updated_graph_context = payload.get("updated_graph_context", {}) or {}
        raw_neighbor_regions = payload.get("neighbor_regions", []) or []
        if not raw_neighbor_regions:
            raw_neighbor_regions = payload.get("hypothesis_regions", []) or []
        legacy_regions = payload.get("regions", []) or []

        raw_current_region_label = self._normalize_region_label(
            current_region.get("label", "") or current_region.get("region_label", "")
        )
        if not raw_current_region_label and legacy_regions:
            raw_current_region_label = self._normalize_region_label(
                legacy_regions[0].get("label", "")
                or legacy_regions[0].get("region_label", "")
            )
            if not raw_neighbor_regions:
                raw_neighbor_regions = legacy_regions[1:]

        prior_label_lookup = self._build_label_lookup(
            prior_graph_context.get("label_names", [])
        )
        current_region_label = self._resolve_label(
            raw_current_region_label, prior_label_lookup
        )

        target = self._normalize_target_output(payload.get("target", {}), index_map)
        neighbor_regions = self._normalize_neighbor_regions_payload(
            raw_neighbor_regions,
            prior_graph_context=prior_graph_context,
            current_region_label=current_region_label,
            topk=min(topk, 5),
        )

        allowed_labels = list(prior_graph_context.get("label_names", []))
        if current_region_label and current_region_label not in allowed_labels:
            allowed_labels.append(current_region_label)
        for region in neighbor_regions:
            if region["label"] not in allowed_labels:
                allowed_labels.append(region["label"])

        region_connections = self._normalize_region_connections_payload(
            payload.get("region_connections", []) or [],
            allowed_labels=allowed_labels,
        )
        updated_graph_context = self._normalize_updated_graph_context(
            raw_updated_graph_context,
            prior_graph_context=prior_graph_context,
            current_region_label=current_region_label,
            neighbor_regions=neighbor_regions,
            region_connections=region_connections,
            target=target,
            viewpoint_context=viewpoint_context,
        )

        final_label_lookup = self._build_label_lookup(
            updated_graph_context.get("label_names", [])
        )
        current_viewpoint_index = self._normalize_viewpoint_index(
            viewpoint_context.get("current_viewpoint_index")
        )
        if not current_region_label and current_viewpoint_index is not None:
            for label, assignments in updated_graph_context.get(
                "label_assigns", {}
            ).items():
                if int(current_viewpoint_index) in [
                    int(value) for value in assignments
                ]:
                    current_region_label = label
                    break
        current_region_label = self._resolve_label(
            current_region_label, final_label_lookup
        )

        deduped_neighbor_regions = []
        seen_neighbor_keys = set()
        current_key = self._canonical_label_key(current_region_label)
        for region in neighbor_regions:
            label = self._resolve_label(region.get("label", ""), final_label_lookup)
            key = self._canonical_label_key(label)
            if not label or key == current_key or key in seen_neighbor_keys:
                continue
            deduped_neighbor_regions.append(
                {
                    "label": label,
                    "prob": float(region["prob"]),
                    "target_prob": float(region["target_prob"]),
                }
            )
            seen_neighbor_keys.add(key)
        neighbor_regions = deduped_neighbor_regions

        final_allowed_labels = list(updated_graph_context.get("label_names", []))
        if current_region_label and current_region_label not in final_allowed_labels:
            final_allowed_labels.append(current_region_label)
        region_connections = self._normalize_region_connections_payload(
            region_connections,
            allowed_labels=final_allowed_labels,
        )
        direction_heading_label = self._normalize_direction_heading_payload(
            payload.get("direction_heading_label", []) or [],
            allowed_labels=final_allowed_labels,
            viewpoint_context=viewpoint_context,
        )

        return {
            "current_region": {"label": current_region_label},
            "neighbor_regions": neighbor_regions,
            "region_connections": region_connections,
            "target": target,
            "direction_heading_label": direction_heading_label,
            "updated_graph_context": updated_graph_context,
        }

    def estimate_target_distance(
        self,
        rgb_image: np.ndarray,
        depth_image: np.ndarray,
        target_object: str,
    ):
        """
        Estimate the target distance from one aligned RGB/depth pair.

        The RGB image tells the model where the already-detected target is in the
        frame, and the depth image provides the metric value for that location.
        """

        if rgb_image is None or depth_image is None:
            return {"found": False, "distance_m": None, "confidence": 0.0}

        # Keep the RGB image unchanged aside from dtype normalization so the model sees
        # the same target appearance that was used in the earlier detection step.
        if rgb_image.dtype != np.uint8:
            rgb_image = rgb_image.astype(np.uint8)
        pil_rgb = Image.fromarray(rgb_image)

        # Depth may arrive as float meters or as an integer map. Convert it to the
        # same 16-bit representation described in the prompt before sending it.
        if depth_image.ndim == 3:
            depth_image = depth_image[:, :, 0]

        if depth_image.dtype == np.float32 or depth_image.dtype == np.float64:
            depth_image = np.clip(depth_image * 4000.0, 0, 65535).astype(np.uint16)
        elif depth_image.dtype != np.uint16:
            depth_image = depth_image.astype(np.uint16)

        pil_depth = Image.fromarray(depth_image, mode="I;16")

        debugpy.breakpoint()

        # Send the RGB image first and the aligned depth image second to match the
        # concise prompt in _build_distance_instruction().
        content_items = [
            {"type": "text", "text": self._build_distance_instruction(target_object)},
            {
                "type": "image_url",
                "image_url": {"url": self._image_to_data_url(pil_rgb)},
            },
            {
                "type": "image_url",
                "image_url": {"url": self._image_to_data_url(pil_depth)},
            },
        ]

        debugpy.breakpoint()

        decoded = self._request_completion(content_items, max_tokens=96)
        print("\n[MLLM DISTANCE RAW OUTPUT]\n", decoded)

        raw = self._strip_code_fences(decoded)
        payload = self._extract_json_object(raw)

        if payload is None:
            print("[MLLM] Failed to parse distance JSON. Raw output:")
            print(decoded)
            return {"distance_m": None}

        # Treat only numeric values as valid distances. This avoids passing malformed
        # model output deeper into the navigation loop.
        distance_m = None
        raw_distance = payload.get("distance_m")
        if raw_distance is not None:
            try:
                distance_m = float(raw_distance)
            except Exception:
                distance_m = None

        return {
            "distance_m": distance_m,
        }

