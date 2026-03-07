import json
import numpy as np
import torch
from PIL import Image
from transformers import AutoProcessor
import debugpy

try:
    # transformers 4.x
    from transformers import AutoModelForVision2Seq as AutoVLM
except ImportError:
    # transformers 5.x name
    from transformers import AutoModelForImageTextToText as AutoVLM


class LocalQwen3VLClient:
    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-VL-4B-Instruct",
        device: str | None = None,
        dtype: torch.dtype | None = None,
        max_new_tokens: int = 256,
        h_fov: float = -1.0,
    ):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if dtype is None:
            dtype = torch.float16 if device == "cuda" else torch.float32

        self.device = device
        self.dtype = dtype
        self.max_new_tokens = max_new_tokens
        self.h_fov = h_fov

        self.processor = AutoProcessor.from_pretrained(
            model_name, trust_remote_code=True
        )
        self.model = AutoVLM.from_pretrained(
            model_name,
            torch_dtype=dtype,
            device_map="auto" if device == "cuda" else None,
            trust_remote_code=True,
        )
        if device != "cuda":
            self.model.to(device)
        self.model.eval()

    def propose_semantic_nodes(
        self,
        observation_images: list[np.ndarray],
        depth_images: list[np.ndarray] | None = None,
        topk: int = 5,
        target_object: str | None = None,
    ):
        """
        observation_images: list of RGB uint8 arrays (H,W,3), typically your horizon scan frames.

        Returns a dict:
          {
            "regions": [{"label": "...", "confidence": 0.7, "support_views": [0,3]}],
            "target": {"query": "...", "found": true/false, "views": [..]},
            "num_obs_images": <int>,
            "index_map": <list[int]>   # index_map[i] = original horizon index of image i shown to the MLLM
          }

        Notes:
          - The MLLM may output fewer than topk regions.
          - "views" indices refer to the images actually provided to the MLLM (after any downsampling),
            so you can map them back to original horizon indices via index_map.
        """

        # -------------------- Convert to PIL --------------------
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

            # Depth input is expected as z-depth in shape (H, W, 1) uint16,
            # where meters = depth_value / 4000.0 (0.25 mm per increment).
            if depth_img.ndim == 3:
                depth_img = depth_img[:, :, 0]

            # Preserve metric depth fidelity in uint16 whenever possible.
            if depth_img.dtype == np.float32 or depth_img.dtype == np.float64:
                # If already in meters, convert back to 16-bit depth units.
                depth_img = np.clip(depth_img * 4000.0, 0, 65535).astype(np.uint16)
            elif depth_img.dtype != np.uint16:
                depth_img = depth_img.astype(np.uint16)

            pil_depths.append(Image.fromarray(depth_img, mode="I;16"))

        # -------------------- Optional downsample (keep mapping) --------------------
        # We keep a mapping so the MLLM can reference view indices robustly.
        index_map = list(range(len(pil_images)))

        if self.h_fov > 0:
            target_count = int(np.ceil((2.0 * np.pi) / self.h_fov))
            target_count = max(1, target_count)

            if len(pil_images) > target_count:
                idx = np.linspace(
                    0,
                    len(pil_images) - 1,
                    num=target_count,
                    endpoint=False,
                    dtype=int,
                ).tolist()
                pil_images = [pil_images[i] for i in idx]
                index_map = [index_map[i] for i in idx]
                if pil_depths:
                    pil_depths = [pil_depths[i] for i in idx]
        else:
            # naive downsample if HFOV not set
            idx = list(range(0, len(pil_images), 8))
            pil_images = [pil_images[i] for i in idx]
            index_map = [index_map[i] for i in idx]
            if pil_depths:
                pil_depths = [pil_depths[i] for i in idx]

        # save pil_images to disk for debugging
        for i, im in enumerate(pil_images):
            im.save(f"debug_horizon_image_{i}.png")
        # save pil_depths to disk for debugging
        for i, d in enumerate(pil_depths):
            d.save(f"debug_horizon_depth_{i}.png")

        num_obs_images = len(pil_images)

        # -------------------- Prompt --------------------
        target_object = (target_object or "").strip()

        if target_object:
            target_block = f"""
            Task C: Target detection

            Target: "{target_object}"

            Output:
            "target": {{"found": boolean, "views": [indices], "confidence": float}}

            Rules:
            - If clearly visible in any image: found=true, views=list of those image indices, confidence in [0.6, 0.95]
            - Otherwise: found=false, views=[], confidence=0.0
            - Do not guess. If uncertain, use found=false.
            """.strip()
        else:
            target_block = """
            Task C: Target detection

            Output:
            "target": {"found": false, "views": [], "confidence": 0.0}
            """.strip()

        instruction = f"""
        You are given a 360-degree indoor horizon scan. Each image is a different direction from the same location. Image indices: 0 to {max(0, num_obs_images - 1)}.

        Region labels must be rooms or functional areas, not objects. Examples: kitchen area, living room area, bedroom area, bathroom area, hallway, dining area, entryway, corridor, stair area, office area, laundry area, garage area, storage area. Other reasonable room/area labels are allowed if supported by the images. Invalid labels: chair, table, sofa, cabinet, door, TV.

        Task A: Current region
        Infer exactly one current room/area label.

        Output:
        "current_region": {{"label": "...", "confidence": 0.0}}

        Rules:
        - Confidence is based only on visible evidence
        - confidence in [0.6, 0.95], never 1.0

        Task B: Neighbor regions
        Propose up to {topk} likely adjacent or nearby room/area labels, even if not directly visible.

        Output:
        "neighbor_regions": [{{"label": "...", "existence_prob": 0.0}}]

        Rules:
        - Do not repeat the current region
        - Do not use object names
        - Each existence_prob must be >= 0.5
        - neighbor_regions may be empty only if current_region.confidence >= 0.9 and there are no obvious transition cues

        {target_block}

        Return only valid JSON, no markdown, no extra text:
        {{
        "current_region": {{"label": "...", "confidence": 0.0}},
        "neighbor_regions": [{{"label": "...", "existence_prob": 0.0}}],
        "target": {{"found": false, "views": [], "confidence": 0.0}}
        }}
        """.strip()

        # -------------------- Build chat-style prompt --------------------
        messages = [
            {
                "role": "user",
                "content": [{"type": "image", "image": im} for im in pil_images]
                + [{"type": "text", "text": instruction}],
            }
        ]

        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        inputs = self.processor(text=[text], images=pil_images, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        def _decode_with_max_tokens(max_tokens: int) -> str:
            with torch.no_grad():
                out = self.model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    do_sample=False,  # deterministic, helps JSON stability
                    temperature=0.0,  # keep consistent outputs
                    top_p=1.0,
                    repetition_penalty=1.05,  # small nudge to reduce loops
                )

            # For decoder-only chat models, `generate` returns prompt + completion.
            # Decode only the newly generated tokens so we don't re-parse the prompt.
            input_len = inputs["input_ids"].shape[-1]
            generated = out[:, input_len:]
            return self.processor.batch_decode(
                generated,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )[0].strip()

        decoded = _decode_with_max_tokens(self.max_new_tokens)

        print("\n[MLLM RAW OUTPUT]\n", decoded)

        debugpy.breakpoint()

        # 1) Strip markdown code fences if present
        raw = decoded.strip()
        if "```" in raw:
            lines = raw.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines).strip()

        # 2) Try direct JSON parse
        def _try_parse_json(candidate_raw: str):
            parsed = None
            try:
                parsed = json.loads(candidate_raw)
            except Exception:
                # Fallback: extract the first valid {...} JSON object.
                for i in range(len(candidate_raw)):
                    if candidate_raw[i] != "{":
                        continue
                    for j in range(len(candidate_raw), i, -1):
                        if candidate_raw[j - 1] != "}":
                            continue
                        candidate = candidate_raw[i:j]
                        try:
                            parsed = json.loads(candidate)
                            break
                        except Exception:
                            continue
                    if parsed is not None:
                        break
            return parsed

        payload = _try_parse_json(raw)

        # If output appears truncated (common with too-small max_new_tokens),
        # regenerate once with a larger token budget.
        if payload is None and raw.count("{") > raw.count("}"):
            retry_tokens = max(self.max_new_tokens * 2, 512)
            decoded = _decode_with_max_tokens(retry_tokens)
            print("\n[MLLM RAW OUTPUT RETRY]\n", decoded)
            raw = decoded.strip()
            if "```" in raw:
                lines = raw.splitlines()
                if lines and lines[0].strip().startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
                raw = "\n".join(lines).strip()
            payload = _try_parse_json(raw)

        if payload is None:
            print("[MLLM] Failed to parse JSON. Raw output:")
            print(decoded)
            return {
                "regions": [],
                "target": {"query": target_object, "found": False, "views": []},
                "num_obs_images": num_obs_images,
                "index_map": index_map,
            }

        # -------------------- Normalize output --------------------
        # Preferred schema from the instruction prompt:
        # {
        #   "current_region": {"label": str, "confidence": float},
        #   "neighbor_regions": [{"label": str, "existence_prob": float}],
        #   "target": {"found": bool, "views": [int], "confidence": float}
        # }
        # Backward-compatible fallback still supports "regions".
        regions_in = payload.get("regions", [])
        if not isinstance(regions_in, list):
            regions_in = []

        current_region = payload.get("current_region", {}) or {}
        if isinstance(current_region, dict):
            regions_in.insert(
                0,
                {
                    "label": current_region.get("label", ""),
                    "confidence": current_region.get("confidence", 0.0),
                    "support_views": [],
                },
            )

        neighbor_regions = payload.get("neighbor_regions", []) or []
        if isinstance(neighbor_regions, list):
            for neighbor in neighbor_regions:
                if not isinstance(neighbor, dict):
                    continue
                regions_in.append(
                    {
                        "label": neighbor.get("label", ""),
                        "confidence": neighbor.get("existence_prob", 0.0),
                        "support_views": [],
                    }
                )

        target_in = payload.get("target", {}) or {}

        regions = []
        for r in regions_in[:topk] if isinstance(regions_in, list) else []:
            label = str(r.get("label", "")).strip()
            try:
                conf = float(r.get("confidence", 0.0))
            except Exception:
                conf = 0.0
            sv = r.get("support_views", []) or []
            support_views = []
            for x in sv if isinstance(sv, (list, tuple)) else []:
                try:
                    support_views.append(int(x))
                except Exception:
                    continue
            if not label:
                continue
            regions.append(
                {
                    "label": label,
                    "confidence": conf,
                    "support_views": support_views,
                    "type": "region",
                }
            )

        found = bool(target_in.get("found", False))
        views = target_in.get("views", []) or []
        target_views = []
        for x in views if isinstance(views, (list, tuple)) else []:
            try:
                target_views.append(int(x))
            except Exception:
                continue

        return {
            "regions": regions,
            "target": {
                "query": str(target_in.get("query", target_object)).strip(),
                "found": found,
                "views": target_views,
            },
            "num_obs_images": num_obs_images,
            "index_map": index_map,
        }
