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

        evenly_spaced = MLLMClient._select_evenly_spaced_indices(total_count, sample_count)
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
    def _build_grounded_label(cls, region_label: str, viewpoint_index: int | None) -> str:
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
        self,
        num_obs_images: int,
        topk: int,
        target_object: str,
        graph_context: dict | None = None,
        viewpoint_context: dict | None = None,
    ) -> str:
        """
        Build the semantic-graph prompt for the MLLM.

        The prompt explicitly separates grounded visible viewpoints from purely
        hypothetical future regions so navigation targets remain physically valid.
        """
        target_object = target_object.strip()
        if target_object:
            target_line = (
                f'target: detect "{target_object}". '
                'If visible, return {"found":true,"views":[indices],"confidence":[]}; '
                'otherwise {"found":false,"views":[],"confidence":[]}.'
            )
        else:
            target_line = 'target: always {"found":false,"views":[],"confidence":[]}.'

        graph_context = graph_context or {}
        graph_context_json = json.dumps(graph_context, separators=(",", ":"))

        viewpoint_context = viewpoint_context or {}
        current_viewpoint_index = self._normalize_viewpoint_index(
            viewpoint_context.get("current_viewpoint_index")
        )
        visible_viewpoint_indices = sorted(
            {
                int(item["viewpoint_index"])
                for item in viewpoint_context.get("visible_viewpoints", []) or []
                if self._normalize_viewpoint_index(item.get("viewpoint_index"))
                is not None
            }
        )
        visible_marker_text = ", ".join(
            f"vp-{idx}" for idx in visible_viewpoint_indices
        ) or "none"
        current_marker_text = (
            f"vp-{current_viewpoint_index}"
            if current_viewpoint_index is not None
            else "the current camera viewpoint"
        )

        prompt = (
            f"You are given {num_obs_images} indoor images from one 360-degree viewpoint "
            f"(indices 0-{max(0, num_obs_images - 1)}). "
            "Some images contain overlaid viewpoint markers like vp-17; each marker is a real physical navigable viewpoint. "
            "Output one-line compact JSON only. "
            'Schema: {"current_region":{"node_id":"","region_label":"","label":"","confidence":0.0},'
            '"visible_viewpoints":[{"node_id":"","viewpoint_index":0,"region_label":"","label":"","existence_prob":0.0,"target_prob":0.0}],'
            '"hypothesis_regions":[{"node_id":"","label":"","existence_prob":0.0,"target_prob":0.0}],'
            '"region_connections":[{"region_a":"","region_b":"","connection_prob":0.0,"travel_distance":0.0}],'
            '"target":{"found":false,"views":[],"confidence":[]}}. '
            "Use room/area labels only (no objects): kitchen area, living room area, bedroom area, "
            "bathroom area, hallway, dining area, entryway, corridor, office area. "
            "Every region instance label must be <room-or-area>-<instance>, for example dining area-1 or hallway-2. "
            "Every grounded viewpoint label must be <region_label>-vp-<viewpoint_index>, for example dining area-1-vp-17. "
            "If two visible viewpoints belong to the same semantic region, reuse the same region instance number but keep different vp suffixes. "
            f"The current camera viewpoint is {current_marker_text}. "
            f"Visible viewpoint markers that must each appear exactly once in visible_viewpoints: [{visible_marker_text}]. "
            "current_region: one grounded label for the current physical viewpoint; region_label omits the vp suffix; confidence in [0.6,0.95]. "
            "If current_region matches a previously proposed hypothesis in graph_context, reuse that exact node_id. "
            "visible_viewpoints: include one item for every visible marker listed above, no omissions and no duplicates. "
            "Fields: node_id, viewpoint_index, region_label, label, existence_prob [0.5,0.99], target_prob (0,1), note optional. "
            "The label must exactly equal region_label + '-vp-' + viewpoint_index. "
            f"hypothesis_regions: up to {topk}, optional extra region-instance labels with no vp suffix and no physical grounding yet. "
            "These are allowed even if no visible viewpoint is currently grounded to them. "
            "Reuse nodes from graph_context instead of creating redundant hypotheses whenever possible. "
            "region_connections: include only direct connections among current_region, visible_viewpoints, and hypothesis_regions. "
            "Do not enumerate all pairs. Omit any pair if direct connectivity or travel distance is uncertain. "
            "Fields: region_a, region_b, connection_prob [0.5,1], travel_distance (>0 meters). "
            "Connections are symmetric: output A->B only, not B->A. region_a and region_b must copy the exact labels used elsewhere in your JSON. "
            f"{target_line} "
            "target: views = image indices where target confidence >0.5. "
            "confidence = list of detection confidences aligned with views. "
            "If no view has confidence >0.5 set found=false and return empty lists. "
            "graph_context is the persistent graph before this observation. "
            f"graph_context={graph_context_json}. "
            "node_id: copy an existing node_id from graph_context when there is a clear match; otherwise use an empty string. "
            "Return JSON only. No explanation or markdown."
        )

        debugpy.breakpoint()
        return prompt

    @staticmethod
    def _normalize_target_output(target: dict, index_map: list[int]) -> dict:
        found = bool(target.get("found", False))

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
            "found": found and bool(deduped_views),
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
            viewpoint_index = cls._normalize_viewpoint_index(entry.get("viewpoint_index"))
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
                        for item in viewpoint_context.get("visible_viewpoints", []) or []
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
            topk=topk,
            target_object=target_object or "",
            graph_context=graph_context,
            viewpoint_context=viewpoint_context,
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
            retry_tokens = min(max(self.max_new_tokens * 2, 224), 384)
            decoded = self._request_completion(content_items, retry_tokens)
            print("\n[MLLM RAW OUTPUT RETRY]\n", decoded)
            raw = self._strip_code_fences(decoded)
            payload = self._try_parse_json(raw)

        if payload is None:
            print("[MLLM] Failed to parse JSON. Raw output:")
            print(decoded)
            return {
                "current_region": {
                    "node_id": "",
                    "region_label": "",
                    "label": "",
                    "viewpoint_index": None,
                    "viewpoint_id": viewpoint_context.get("current_viewpoint_id", ""),
                    "confidence": 0.0,
                    "note": "",
                },
                "visible_viewpoints": [],
                "hypothesis_regions": [],
                "region_connections": [],
                "target": {"found": False, "view": -1, "views": [], "confidence": []},
            }

        current_region = payload.get("current_region", {}) or {}
        raw_visible_viewpoints = payload.get("visible_viewpoints", []) or []
        raw_hypothesis_regions = payload.get("hypothesis_regions", []) or []
        legacy_neighbor_regions = payload.get("neighbor_regions", []) or []
        legacy_regions = payload.get("regions", []) or []

        current_region_label = self._normalize_region_label(
            current_region.get("region_label", "") or current_region.get("label", "")
        )
        current_confidence = self._safe_float(
            current_region.get("confidence", 0.0), 0.0
        )
        current_node_id = self._normalize_node_id(current_region.get("node_id", ""))
        current_note = self._normalize_note(current_region.get("note", ""))

        if not current_region_label and legacy_regions:
            first_region = legacy_regions[0]
            current_region_label = self._normalize_region_label(
                first_region.get("region_label", "") or first_region.get("label", "")
            )
            current_confidence = self._safe_float(
                first_region.get("confidence", 0.0), 0.0
            )
            current_node_id = self._normalize_node_id(first_region.get("node_id", ""))
            current_note = self._normalize_note(first_region.get("note", ""))
            if not raw_visible_viewpoints and not raw_hypothesis_regions:
                legacy_neighbor_regions = legacy_regions[1:]

        if legacy_neighbor_regions:
            for region in legacy_neighbor_regions:
                if (
                    self._normalize_viewpoint_index(region.get("viewpoint_index"))
                    is not None
                    or self._extract_viewpoint_index_from_label(
                        region.get("label", "")
                    )
                    is not None
                ):
                    raw_visible_viewpoints.append(region)
                else:
                    raw_hypothesis_regions.append(region)

        current_viewpoint_index = self._normalize_viewpoint_index(
            viewpoint_context.get("current_viewpoint_index")
        )
        current_label = self._build_grounded_label(
            current_region_label,
            current_viewpoint_index,
        )

        normalized_visible_viewpoints, visible_label_aliases = self._normalize_visible_viewpoints(
            raw_visible_viewpoints,
            viewpoint_context=viewpoint_context,
        )
        normalized_hypotheses, hypothesis_label_aliases = self._normalize_hypothesis_regions(
            raw_hypothesis_regions,
            topk=topk,
        )

        label_aliases = {}
        if current_region_label:
            label_aliases[current_region_label] = current_label or current_region_label
        if current_label:
            label_aliases[current_label] = current_label
        label_aliases.update(visible_label_aliases)
        label_aliases.update(hypothesis_label_aliases)

        normalized_connections = self._normalize_region_connections(
            payload.get("region_connections", []),
            label_aliases=label_aliases,
        )

        target = self._normalize_target_output(payload.get("target", {}), index_map)

        return {
            "current_region": {
                "node_id": current_node_id,
                "region_label": current_region_label,
                "label": current_label,
                "viewpoint_index": current_viewpoint_index,
                "viewpoint_id": str(viewpoint_context.get("current_viewpoint_id", "")),
                "confidence": current_confidence,
                "note": current_note,
            },
            "visible_viewpoints": normalized_visible_viewpoints,
            "hypothesis_regions": normalized_hypotheses,
            "region_connections": normalized_connections,
            "target": target,
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
