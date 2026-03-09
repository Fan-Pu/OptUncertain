import base64
import io
import json
import os

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
        max_new_tokens: int = 160,
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
        required = ("current_region", "neighbor_regions", "target")
        return all(key in obj for key in required)

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

    def _build_instruction(
        self,
        num_obs_images: int,
        topk: int,
        target_object: str,
    ) -> str:
        """
        Builds the instruction string for the MLLM based on the given parameters.
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

        prompt = (
            f"You are given {num_obs_images} indoor images from one 360° viewpoint "
            f"(indices 0-{max(0, num_obs_images - 1)}). "
            "Output one-line compact JSON only. "
            'Schema: {"current_region":{"label":"","confidence":0.0},'
            '"neighbor_regions":[{"label":"","existence_prob":0.0,"target_prob":0.0}],'
            '"region_connections":[{"region_a":"","region_b":"","connection_prob":0.0,"travel_distance":-1}],'
            '"target":{"found":false,"views":[],"confidence":[]}}. '
            "Use room/area labels only (no objects): kitchen area, living room area, bedroom area, "
            "bedroom area, bathroom area, hallway, dining area, entryway, corridor, office area. "
            "current_region: one label for the camera location; confidence in [0.6,0.95]. "
            f"{target_line} "
            "target: views = image indices where target confidence >0.5. "
            "confidence = list of detection confidences aligned with views. "
            "If no view has confidence >0.5 set found=false and return empty lists. "
            f"neighbor_regions: up to {topk}, no duplicates, exclude current_region. "
            "Fields: label, existence_prob [0.5,0.95], target_prob [0,1]. "
            "region_connections: for each unique pair among current_region and neighbors. "
            "Fields: region_a, region_b, connection_prob [0,1], travel_distance (meters). "
            "If not directly connected set travel_distance=-1. "
            "Connections are symmetric: output A→B only, not B→A. "
            "Return JSON only. No explanation or markdown."
        )

        debugpy.breakpoint()
        return prompt

    def _build_distance_instruction(self, target_object: str) -> str:
        """
        Build a short distance-estimation prompt for one aligned RGB/depth pair.

        The target has already been detected before this call, so the prompt only
        asks the model to read the distance, not to decide whether the target exists.
        """

        target_object = target_object.strip()
        return (
            f'Target: "{target_object}". '
            "Two aligned images are provided: RGB first, depth second. "
            "The target is definitely visible in RGB, so do not verify presence. "
            "Use RGB to locate the target, then estimate distance from depth. "
            "Depth conversion: meters = pixel_value in the last dimension / 4000.0. "
            'Return only valid JSON with exactly one key: "distance_m". '
            'Example valid outputs: {"distance_m": 2.37} or {"distance_m": null}. '
            "Do not output any other text."
        )

    def _request_completion(self, content_items, max_tokens: int) -> str:
        """
        Sends a chat completion request to the Hugging Face router API with the given content items and max tokens.
        Returns the text content of the response message.
        """
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": content_items}],
                max_tokens=max_tokens,
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
    ):
        """
        observation_images: list of RGB uint8 arrays (H,W,3), typically horizon scan frames.

        Returns a dict:
          {
            "current_region": {"label": "...", "confidence": 0.0},
            "neighbor_regions": [{"label": "...", "existence_prob": 0.0}],
            "target": {"found": true/false, "views": [..], "confidence": 0.0}
          }
        """

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
                idx = self._select_evenly_spaced_indices(
                    total_count=len(pil_images),
                    sample_count=target_count,
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
        )

        content_items = [{"type": "text", "text": instruction}]
        for image in pil_images:
            content_items.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._image_to_data_url(image)},
                }
            )

        # decoded = self._request_completion(content_items, self.max_new_tokens)
        decoded = '{"current_region":{"label":"living room area","confidence":0.9},"neighbor_regions":[{"label":"bedroom area","existence_prob":0.9,"target_prob":0.3},{"label":"kitchen area","existence_prob":0.7,"target_prob":0.1},{"label":"dining area","existence_prob":0.7,"target_prob":0.1},{"label":"hallway","existence_prob":0.6,"target_prob":0.1}],"region_connections":[{"region_a":"living room area","region_b":"bedroom area","connection_prob":0.95,"travel_distance":3},{"region_a":"living room area","region_b":"kitchen area","connection_prob":0.9,"travel_distance":4},{"region_a":"living room area","region_b":"dining area","connection_prob":0.9,"travel_distance":4},{"region_a":"living room area","region_b":"hallway","connection_prob":0.7,"travel_distance":2}],"target":{"found":true,"views":[0,2],"confidence":0.95}}'
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
                "current_region": {"label": "", "confidence": 0.0},
                "neighbor_regions": [],
                "target": {"found": False, "views": [], "confidence": 0.0},
            }

        # The rest of the code is dedicated to normalizing and validating the parsed output.

        current_region = payload.get("current_region", {})
        current_label = str(current_region.get("label", "")).strip()
        current_confidence = float(current_region.get("confidence", 0.0))

        neighbor_regions = payload.get("neighbor_regions", [])
        legacy_regions = payload.get("regions", [])

        if not current_label and legacy_regions:
            first_region = legacy_regions[0]
            current_label = str(first_region.get("label", "")).strip()
            current_confidence = float(first_region.get("confidence", 0.0))

            if not neighbor_regions:
                neighbor_regions = legacy_regions[1:]

        normalized_neighbors = []
        for neighbor in neighbor_regions:
            label = str(neighbor.get("label", "")).strip()
            if not label or label == current_label:
                continue

            existence_prob = float(
                neighbor.get("existence_prob", neighbor.get("confidence", 0.0))
            )
            normalized_neighbors.append(
                {
                    "label": label,
                    "existence_prob": existence_prob,
                }
            )

        target = payload.get("target", {})
        found = bool(target.get("found", False))

        # Map the original view indices returned by MLLM back to the corresponding horizon scan indices.
        target_views = [
            int(index_map[int(view_idx)])
            for view_idx in target.get("views", [])
            if 0 <= int(view_idx) < len(index_map)
        ]

        deduped_views = list(dict.fromkeys(target_views))
        target_confidence = float(target.get("confidence", 0.0))

        return {
            "current_region": {
                "label": current_label,
                "confidence": current_confidence,
            },
            "neighbor_regions": normalized_neighbors[:topk],
            "target": {
                "found": found,
                "views": deduped_views,
                "confidence": target_confidence,
            },
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

        # Keep the existing debug depth dump untouched so your current debugging flow
        # stays the same.
        pil_depth = Image.fromarray(depth_image, mode="I;16")
        if self.save_debug_images:
            pil_depth.save("debug_target_depth_query.png")

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
