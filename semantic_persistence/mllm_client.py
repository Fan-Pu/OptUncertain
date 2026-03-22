import base64
from doctest import debug
import io
import json
import os
import re
import Helper
import numpy as np
from openai import BadRequestError, OpenAI
from PIL import Image
import debugpy
from textwrap import dedent

from semantic_persistence import hypothesis_graph


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
        last_image_right_shift_steps: int = 1,
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
        self.last_image_right_shift_steps = max(0, int(last_image_right_shift_steps))
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
        if "current_region_node" in obj and "target" in obj:
            return True
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
    def _nudge_final_sample_right(
        indices: list[int],
        total_count: int,
        shift_steps: int = 1,
    ) -> list[int]:
        if len(indices) < 2 or total_count <= 0 or shift_steps <= 0:
            return indices

        adjusted = sorted(int(index) for index in indices)
        used = set(adjusted[:-1])
        last_index = adjusted[-1]
        shifted = 0

        for candidate in range(last_index + 1, total_count):
            if candidate not in used:
                adjusted[-1] = candidate
                shifted += 1
                if shifted >= shift_steps:
                    return adjusted

        return adjusted

    def _build_instruction(
        self,
        num_obs_images: int,
        target_object: str,
        graph: hypothesis_graph,
        current_vp_node_id: int,
        neighbor_vp_node_ids: list[int],
        neighbor_vp_distances_list: list[float],
    ) -> str:
        """Build the instruction prompt for MLLM based on the current graph context and observations."""
        target_object = target_object.strip()
        graph_summary = graph.get_MLLM_summary()
        # untangle the graph summary into individual variables for easier formatting in the prompt
        node_indices = graph_summary.get("node_indices", [])
        node_grounding_list = graph_summary.get("node_grounding_list", [])
        node_existence_list = graph_summary.get("node_existence_list", [])
        node_target_list = graph_summary.get("node_target_list", [])
        node_type_list = graph_summary.get("node_type_list", [])
        node_assign_dict = graph_summary.get("node_assign_dict", {})
        arc_indices = graph_summary.get("arc_indices", [])
        arc_grounding_list = graph_summary.get("arc_grounding_list", [])
        arc_existence_list = graph_summary.get("arc_existence_list", [])
        arc_distance_list = graph_summary.get("arc_distance_list", [])
        if len(node_indices) > 0:
            start_region_node_id = max(node_indices) + 1
        else:
            start_region_node_id = (
                int(max(Helper.viewpoint_index_by_vp_label.values())) + 1
            )

        system_message = dedent(
            """
            You are an indoor scene graph proposal module.

            Return compact JSON only.
            Do not output markdown or any explanation.

            All ids must be integers.
            All probabilities and distances must be numeric values, not strings.
            Use True/False for booleans.

            Each figure may contain a text number indicating a potential next viewpoint.
            The same text number can appear in multiple images, and the same text number always refers to the same viewpoint.

            Region labels must be room or area labels only, not object names.
            Each region label must be descriptive and must include:
            1. a characteristic or appearance cue,
            2. the room or area type,
            3. a relative location cue.

            Good examples:
            - modern living room area with curved sofa and TV wall near kitchen bar
            - open dining and kitchen bar area with stools near living room
            - minimalist bedroom area with large bed and window near living room

            Bad examples:
            - living room area
            - kitchen area
            - bedroom area

            Do not generate too many region nodes.
            A maximum of 5 new region nodes in total may be proposed at each step.

            When a region is revisited, reuse the previous label instead of proposing a new one.
            Only propose a similar label if it is a different physical region.

            No region-to-region arcs are allowed.

            Do not generate arcs between the current viewpoint node and its neighbor viewpoint nodes.

            Do not generate an arc between a viewpoint node and its assigned region node.

            Every neighboring viewpoint node must be assigned to exactly one region node.

            Normalization rules:
            - target_prob for all returned region nodes and that for existing region nodes must sum to 1.
            - target_prob values must be positive, not all zero.
            - viewpoint_target_probs must be provided for all neighboring viewpoint nodes listed by the user.
            - target_prob for viewpoint node i should not be larger than the target_prob of its assigned region node j.

            If the target object is not directly observed in the current RGB observation, set:
            "found": False, "confidence": 0.0, "view_id": -1. The view_id field is the index of the provided RGB image that contains the target. If multiple images contain the target, set view_id to the one where the target is most centered.
            
            If at least one legal connection is supported by the observation and assignments, new_arcs must not be empty.
            """
        ).strip()

        user_message = dedent(
            f"""
            You are given {num_obs_images} indoor images from one 360-degree viewpoint (indices 0-{max(0, num_obs_images - 1)}).

            The following is the condensed snapshot of the accumulated graph context.

            node_indices = {node_indices}
            node_grounding_list = {node_grounding_list}   # 0 = not grounded, 1 = grounded
            node_existence_list = {node_existence_list}
            node_target_list = {node_target_list}
            node_type_list = {node_type_list}             # 0 = region, 1 = viewpoint
            node_assigns = {node_assign_dict}             # region_id -> list of assigned viewpoint ids

            arc_indices = {arc_indices}                   # stored only for i < j
            arc_grounding_list = {arc_grounding_list}
            arc_existence_list = {arc_existence_list}
            arc_distance_list = {arc_distance_list}       # in meters 

            Arc connection is symmetric. If (i, j) exists, then (j, i) is the reverse arc with the same existence probability and distance.
            Only one direction with i < j is listed.

            Region node ids must be no less than {start_region_node_id}.
            Current viewpoint node id = {current_vp_node_id}
            Neighbor viewpoint node ids = {neighbor_vp_node_ids}
            Distances from current viewpoint node to neighboring viewpoint nodes = {neighbor_vp_distances_list} # in meters

            Grounding rules:
            - a region node is grounded if any viewpoint is assigned to that region
            - a viewpoint node is grounded if it is visited by the robot
            - an arc is grounded if both endpoint nodes are grounded

            Target object = {target_object}
            
            Generation priority:
            1.identify current region.
            2.identify distinct visible regions.
            3.infer hidden adjacent regions when strong layout cues exist.
            4.assign each neighboring viewpoint to one region.
            5.generate all legal arcs supported by observation and assignments.

            Generate JSON with exactly this schema:
            {{
                "current_region_node": {{"label": "", "id": 0, "target_prob": 0.0}},
                "new_visible_region_nodes": [{{"label": "", "id": 0, "exist_prob": 0.0, "target_prob": 0.0}}],
                "new_invisible_region_nodes": [{{"label": "", "id": 0, "exist_prob": 0.0, "target_prob": 0.0}}],
                "viewpoint_target_probs": [{{"id": 0, "target_prob": 0.0}}],
                "new_arcs": [{{"i": 0, "j": 0, "exist_prob": 0.0, "dist": 0.0}}],
                "target": {{"found": False, "confidence": 0.0, "view_id": 0}},
                "viewpoint_node_assigns": [{{"id": 0, "assign_region_node_id": 0}}],
                "region_merges": []
            }}

            Notes:
            - current_region_node is the region node assigned to the current viewpoint node.
            - new_visible_region_nodes are new region nodes supported by the current RGB observations.
            - new_invisible_region_nodes are plausible new region nodes not directly visible now but strongly suggested by layout cues (e.g., doorway openings, partial room visibility, continuation of space, or necessary to support neighboring viewpoint assignments).
            - viewpoint_target_probs must include one item for each neighboring viewpoint id in {neighbor_vp_node_ids}.
            - new_arcs may connect viewpoint-region or viewpoint-viewpoint, but never region-region.
            - only generate arcs supported by the current observations and graph context.
            - do not generate arcs between the current viewpoint node and its neighboring viewpoint nodes.
            - do not generate an arc between a viewpoint node and its assigned region node.
            - viewpoint_node_assigns must include all neighboring viewpoint ids in {neighbor_vp_node_ids}, and each must be assigned to exactly one region node.
            - region_merges contains pairs of region node ids that should be merged if they refer to the same physical region.
            - do not leave new_visible_region_nodes, new_invisible_region_nodes, or new_arcs empty by default if there is reasonable supporting evidence.
            """
        ).strip()

        print("system_message = \n\n", system_message)
        print("user_message = \n", user_message)

        return system_message, user_message

    @staticmethod
    def _remap_target_view_id(payload: dict, index_map: list[int]) -> dict:
        target = payload["target"]
        view_id = int(target["view_id"])
        if view_id >= 0:
            target["view_id"] = int(index_map[view_id])
        return payload

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

    def _request_completion(self, messages) -> str:
        """
        Sends a chat completion request to the Hugging Face router API with the given content items and max tokens.
        Returns the text content of the response message.
        """
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.0,
                top_p=0.9,
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
        target_object: str | None = None,
        viewpoint_context: dict | None = None,
        graph: hypothesis_graph.HypothesisGraph | None = None,
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
                        if item.get("viewpoint_index") is not None
                    ],
                )
                idx = self._nudge_final_sample_right(
                    indices=idx,
                    total_count=len(pil_images),
                    shift_steps=self.last_image_right_shift_steps,
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

        current_vp_node_id = viewpoint_context["current_viewpoint_index"]
        neighbor_vp_node_ids = [
            vp["viewpoint_index"] for vp in viewpoint_context["visible_viewpoints"]
        ]
        neighbor_vp_distances = [
            vp["distance"] for vp in viewpoint_context["visible_viewpoints"]
        ]

        num_obs_images = len(pil_images)
        system_message, user_message = self._build_instruction(
            num_obs_images=num_obs_images,
            target_object=target_object,
            graph=graph,
            current_vp_node_id=current_vp_node_id,
            neighbor_vp_node_ids=neighbor_vp_node_ids,
            neighbor_vp_distances_list=neighbor_vp_distances,
        )

        user_content = [{"type": "text", "text": user_message}]
        for image in pil_images:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._image_to_data_url(image)},
                }
            )

        messages = [
            {
                "role": "system",
                "content": system_message,
            },
            {
                "role": "user",
                "content": user_content,
            },
        ]

        # decoded = self._request_completion(messages)

        decoded = {
            "current_region_node": {
                "label": "modern living room area with curved sofa and TV wall beside kitchen bar",
                "id": 45,
                "target_prob": 0.4,
            },
            "new_visible_region_nodes": [
                {
                    "label": "minimalist bedroom area with large bed and window beyond doorway from living room",
                    "id": 46,
                    "exist_prob": 0.95,
                    "target_prob": 0.3,
                },
                {
                    "label": "open dining and kitchen bar area with stools and bright counter adjacent to TV wall",
                    "id": 47,
                    "exist_prob": 0.97,
                    "target_prob": 0.3,
                },
            ],
            "new_invisible_region_nodes": [],
            "viewpoint_target_probs": [
                {"id": 16, "target_prob": 0.2},
                {"id": 21, "target_prob": 0.25},
            ],
            "new_arcs": [
                {"i": 16, "j": 45, "exist_prob": 0.9, "dist": 1.0},
                {"i": 21, "j": 45, "exist_prob": 0.92, "dist": 1.2},
            ],
            "target": {"found": False, "confidence": 0.0, "view_id": -1},
            "viewpoint_node_assigns": [
                {"id": 16, "assign_region_node_id": 46},
                {"id": 21, "assign_region_node_id": 47},
            ],
            "region_merges": [],
        }

        decoded["current_vp_id"] = current_vp_node_id
        decoded["neighbor_vp_ids"] = neighbor_vp_node_ids
        decoded["neighbor_vp_distances"] = neighbor_vp_distances

        print("\n[MLLM RAW OUTPUT]\n", decoded)
        debugpy.breakpoint()
        if isinstance(decoded, dict):
            payload = decoded
        else:
            raw = self._strip_code_fences(decoded)
            payload = self._try_parse_json(raw)

        if payload is None:
            print("[MLLM] Failed to parse JSON. Raw output:")
            print(decoded)
            return {
                "current_region_node": {
                    "id": -1,
                    "label": "",
                    "exist_prob": 1.0,
                    "target_prob": 0.0,
                },
                "new_visible_region_nodes": [],
                "new_invisible_region_nodes": [],
                "new_arcs": [],
                "target": {
                    "found": False,
                    "confidence": 0.0,
                },
                "viewpoint_node_assigns": [],
                "region_merges": [],
            }

        payload = self._remap_target_view_id(payload, index_map)

        return payload

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

        decoded = self._request_completion(content_items)
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
