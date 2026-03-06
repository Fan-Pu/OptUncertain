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


class LocalQwen2VLClient:
    def __init__(
        self,
        model_name: str = "Qwen/Qwen2-VL-2B-Instruct",
        device: str | None = None,
        dtype: torch.dtype | None = None,
        max_new_tokens: int = 80,
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
        for img in observation_images:
            if img is None:
                continue
            if img.dtype != np.uint8:
                img = img.astype(np.uint8)
            pil_images.append(Image.fromarray(img))

        # -------------------- Optional downsample (keep mapping) --------------------
        # We keep a mapping so the MLLM can reference view indices robustly.
        index_map = list(range(len(pil_images)))

        if pil_images:
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
            else:
                # naive downsample if HFOV not set
                idx = list(range(0, len(pil_images), 8))
                pil_images = [pil_images[i] for i in idx]
                index_map = [index_map[i] for i in idx]

        # save pil_images to disk for debugging
        for i, im in enumerate(pil_images):
            im.save(f"debug_horizon_image_{i}.png")

        num_obs_images = len(pil_images)

        # -------------------- Prompt --------------------
        target_object = (target_object or "").strip()

        target_block = ""
        if target_object:
            target_block = f"""
        Task C (target detection)

        The target object is: "{target_object}".

        Decide whether the target object is clearly visible in ANY image.

        Output a "target" object with fields:
        - found: boolean
        - views: list of image indices where the target is visible
        - confidence: a value in [0,1] indicating confidence that the detected object is the target

        Rules:
        - If there is clear visual evidence of the target in one or more images:
            found = true
            views = indices of those images
            confidence in [0.6, 0.95]
        - If evidence is weak, ambiguous, or absent:
            found = false
            views = []
            confidence = 0.0
        - Do NOT guess. If uncertain, output found=false.

        Important:
        - Do not use confidence > 0.95.
        - Only include an index in views if the target itself is visible in that image.
        """.rstrip()

        instruction = f"""
        You are given a 360-degree horizon scan (multiple images) from inside a house.
        Each image is one viewing direction from the SAME physical location.
        Images are indexed from 0 to {max(0, num_obs_images - 1)}.

        Region labels describe functional areas or rooms in a house.

        Common examples include (but are NOT limited to):
        - kitchen area
        - living room area
        - bedroom area
        - bathroom area
        - hallway
        - dining area
        - entryway
        - corridor
        - stair area
        - office area
        - laundry area
        - garage area
        - storage area

        You may generate other reasonable room/area labels if the images support them.
        The region must be a ROOM or FUNCTIONAL AREA, not a single object.
        INVALID labels: chair, table, sofa, cabinet, door, TV.

        You must do THREE region tasks:

        Task A: Current region
        Infer the region/area the agent is currently in.
        - Output EXACTLY 1 current region label.
        - Provide:
        - label
        - confidence in [0,1] based ONLY on visible evidence

        Confidence calibration for Task A:
        - Do NOT use confidence = 1.0.
        - Use confidence in [0.6, 0.95].
        - Use 0.9 to 0.95 only if there are multiple strong room-level cues across the scan.
        - Use 0.6 to 0.8 if the evidence is partial or mixed.

        Task B: Neighbor regions (hypotheses)
        Propose up to {topk} additional region labels that are likely to be adjacent/nearby,
        even if they are not directly visible.
        These are HYPOTHESES.

        For each hypothesized neighbor region, provide:
        - label: a room/area label (not an object name)
        - existence_prob: a plausibility score in [0,1]

        Rules for neighbor regions:
        - Do not repeat the current region label.
        - Do not output object names.
        - neighbor_regions may be an empty list ONLY if current_region.confidence >= 0.9
        AND there are no obvious transition cues (doorways, corridor openings) in the scan.
        - Otherwise, output at least 1 neighbor region.

        existence_prob constraints:
        - If you output a neighbor region item, existence_prob MUST be >= 0.5.
        - Do NOT output any neighbor region with existence_prob < 0.5.

        existence_prob meaning:
        0.9 = very likely nearby (strong layout cues)
        0.7 = likely nearby (some cues or common adjacency)
        0.5 = plausible but weak evidence

        {target_block}

        Output the JSON object directly, starting with "{{" and ending with "}}".
        Do NOT include markdown fences like ```json.
        Do NOT include any text before or after the JSON.

        Return ONLY valid JSON in this format:
        {{
        "current_region": {{"label": "...", "confidence": 0.0}},
        "neighbor_regions": [
            {{"label": "...", "existence_prob": 0.0}}
        ],
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

        with torch.no_grad():
            out = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,  # deterministic, helps JSON stability
                temperature=0.0,  # keep consistent outputs
                top_p=1.0,
                repetition_penalty=1.05,  # small nudge to reduce loops
            )

        decoded = self.processor.batch_decode(out, skip_special_tokens=True)[0].strip()

        debugpy.breakpoint()

        # Keep only the last assistant segment if present
        marker = "assistant"
        if marker in decoded:
            decoded = decoded.split(marker)[-1].strip()

        # Strip common markdown code fences (```json ... ```)
        if decoded.startswith("```"):
            parts = decoded.split("```")
            if len(parts) >= 2:
                decoded = parts[1].strip()
            if decoded.startswith("json"):
                decoded = decoded.split("\n", 1)[-1].strip()
            if decoded.endswith("```"):
                decoded = decoded[:-3].strip()

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
        payload = None
        try:
            payload = json.loads(raw)
        except Exception:
            # 3) Fallback: extract the first valid {...} JSON object
            for i in range(len(raw)):
                if raw[i] != "{":
                    continue
                for j in range(len(raw), i, -1):
                    if raw[j - 1] != "}":
                        continue
                    candidate = raw[i:j]
                    try:
                        payload = json.loads(candidate)
                        break
                    except Exception:
                        continue
                if payload is not None:
                    break

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
        regions_in = payload.get("regions", [])
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
