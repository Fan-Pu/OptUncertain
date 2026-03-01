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
        self, observation_images: list[np.ndarray], topk: int = 5
    ):
        """
        observation_images: list of RGB uint8 arrays (H,W,3), typically your horizon scan frames.
        Returns a list of dicts like:
          [{"label": "kitchen area", "confidence": 0.7, "type": "region"}, ...]
        """

        # Convert to PIL
        pil_images = []
        for img in observation_images:
            if img is None:
                continue
            if img.dtype != np.uint8:
                img = img.astype(np.uint8)
            pil_images.append(Image.fromarray(img))

        # Reduce load using HFOV in radians: pick the minimum number of
        # non-overlapping views needed to cover the full 2*pi panorama.
        # Example: HFOV = 0.5*pi -> ceil(2*pi / HFOV) = 4 images.
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
                    )
                    pil_images = [pil_images[i] for i in idx.tolist()]
            else:
                pil_images = pil_images[::8]  # naive downsample if HFOV not set

        instruction = f"""
        You are given a 360-degree horizon scan (multiple images) from inside a house.
        Each image is one viewing direction from the SAME physical location.

        Task:
        Propose BETWEEN 0 and {topk} HOUSE REGIONS/AREAS that are strongly supported by the images.
        Return fewer labels if you are not sure. Do NOT guess. If no region is clearly supported, return an empty list.

        Definition of "supported":
        A region label is supported ONLY if there is clear visual evidence in the images that the agent is currently located in or directly observing that region.

        A region is considered supported when:
        - Multiple images show consistent visual cues of the same room/area, OR
        - One image shows strong, unambiguous room-level structure.

        Examples of valid supporting cues:
        - kitchen area: cabinets, countertops, sink layout, stove area, tiled kitchen structure
        - living room area: sofa arrangement, TV area, open lounge layout
        - bedroom area: bed layout, nightstands, bedroom furniture arrangement
        - hallway: narrow corridor-like geometry, doors along a passage
        - bathroom area: sink + mirror + bathroom layout

        Important:
        - Support must come from ROOM-LEVEL structure, not single objects.
        - Seeing one object alone (for example a chair or table) is NOT enough evidence.
        - If evidence is weak or ambiguous, do NOT output the label.

        Allowed label style:
        "<room/area> area" or "<room/area>".

        Do NOT output object names (chair, table, sofa, TV, counter, cabinet, door).
        Optional short descriptors are allowed, but the head noun must be a room/area.

        Confidence definition:
        - confidence is an evidence score in [0,1] based ONLY on the images.
        - 1.0 = strong evidence visible in many views.
        - 0.7 = clear evidence in a few views.
        - 0.4 = weak or ambiguous evidence.
        - Do NOT output labels with confidence < 0.6.

        Also provide minimal evidence:
        - support_views: indices of images that support the label (for example [0,3,4]).
        Use at most 8 indices.

        Return ONLY valid JSON (no markdown, no explanations):
        {{
        "regions": [
            {{"label": "...", "confidence": 0.0, "support_views": [0]}}
        ]
        }}
        """

        # Build a chat-style prompt. Qwen2-VL uses messages with images.
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
            out = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens)

        decoded = self.processor.batch_decode(out, skip_special_tokens=True)[0]
        # Keep only the assistant part (last occurrence)
        marker = "assistant"
        if marker in decoded:
            decoded = decoded.split(marker)[-1].strip()

        print("\n[MLLM RAW OUTPUT]\n", decoded)

        # 1) Strip markdown code fences if present
        text = decoded.strip()
        if "```" in text:
            lines = text.splitlines()
            # remove leading ```json / ``` and trailing ```
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # 2) Try direct JSON parse
        payload = None
        try:
            payload = json.loads(text)
        except Exception:
            # 3) Fallback: extract the first valid {...} JSON object
            for i in range(len(text)):
                if text[i] != "{":
                    continue
                for j in range(len(text), i, -1):
                    if text[j - 1] != "}":
                        continue
                    candidate = text[i:j]
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
            return []

        regions = payload.get("regions", [])

        result = []
        num_obs_images = len(pil_images)
        for r in regions[:topk]:
            label = str(r.get("label", "")).strip()
            conf = float(r.get("confidence", 0.0))
            sv = r.get("support_views", [])
            if sv is None:
                sv = []
            # ensure list[int]
            support_views = []
            for x in sv if isinstance(sv, (list, tuple)) else []:
                try:
                    support_views.append(int(x))
                except Exception:
                    continue
            if not label:
                continue
            result.append(
                {
                    "label": label,
                    "confidence": conf,
                    "support_views": support_views,
                    "num_obs_images": num_obs_images,
                    "type": "region",
                }
            )
        return result
