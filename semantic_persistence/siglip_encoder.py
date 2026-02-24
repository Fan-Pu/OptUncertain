"""semantic_persistence.siglip_encoder

SigLIP text/image encoders (GPU-friendly).

These encoders are designed to be consistent with the embeddings used in the
vpbank (ViewpointBank). If you build the vpbank with SigLIP image embeddings,
you must also use SigLIP text embeddings at run time.

Requirements:
  - torch
  - transformers

Install:
  pip install torch transformers

Model selection:
  Set SIGLIP_MODEL_ID to override the default model.
  Example:
    export SIGLIP_MODEL_ID=google/siglip-so400m-patch14-384
"""


import os
from typing import Optional

import numpy as np
import torch


def _default_device() -> str:
    """Return 'cuda' if available, else 'cpu'."""
    return "cuda" if torch.cuda.is_available() else "cpu"


class _SigLIPBase:
    """Shared loader for SigLIP models."""

    def __init__(
        self,
        model_id: Optional[str] = None,
        device: Optional[str] = None,
        fp16: bool = True,
    ):
        self.model_id = model_id or os.environ.get(
            "SIGLIP_MODEL_ID", "google/siglip-so400m-patch14-384"
        )
        self.device = device or _default_device()
        self.fp16 = bool(fp16) and (self.device == "cuda")

        self._processor = None
        self._model = None
        self._load()

    def _load(self) -> None:
        """Load processor + model, supporting multiple transformers versions."""
        try:
            from transformers import SiglipModel, SiglipProcessor

            self._processor = SiglipProcessor.from_pretrained(self.model_id)
            self._model = SiglipModel.from_pretrained(self.model_id)
        except Exception:
            # Some transformers versions may not expose Siglip* symbols.
            from transformers import AutoModel, AutoProcessor

            self._processor = AutoProcessor.from_pretrained(self.model_id)
            self._model = AutoModel.from_pretrained(self.model_id)

        self._model.eval().to(self.device)
        if self.fp16:
            self._model = self._model.half()

    @property
    def processor(self):
        return self._processor

    @property
    def model(self):
        return self._model


class SigLIPTextEmbedder(_SigLIPBase):
    """Text -> normalized embedding vector."""

    @torch.no_grad()
    def embed(self, text: str) -> np.ndarray:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")

        inputs = self.processor(
            text=[text], return_tensors="pt", padding=True, truncation=True
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # Preferred API
        if hasattr(self.model, "get_text_features"):
            feats = self.model.get_text_features(**inputs)
        else:
            out = self.model(**inputs)
            if hasattr(out, "text_embeds") and out.text_embeds is not None:
                feats = out.text_embeds
            elif hasattr(out, "pooler_output") and out.pooler_output is not None:
                feats = out.pooler_output
            else:
                raise RuntimeError("Could not extract text embeddings from model output")

        feats = feats.float()
        feats = feats / (feats.norm(dim=-1, keepdim=True) + 1e-12)
        return feats[0].detach().cpu().numpy().astype(np.float32)


class SigLIPImageEmbedder(_SigLIPBase):
    """RGB image (numpy) -> normalized embedding vector."""

    @torch.no_grad()
    def embed(self, image_rgb: np.ndarray) -> np.ndarray:
        if image_rgb is None or not isinstance(image_rgb, np.ndarray):
            raise ValueError("image_rgb must be a numpy array")
        if image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
            raise ValueError("image_rgb must have shape (H, W, 3)")

        inputs = self.processor(images=[image_rgb], return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        if hasattr(self.model, "get_image_features"):
            feats = self.model.get_image_features(**inputs)
        else:
            out = self.model(**inputs)
            if hasattr(out, "image_embeds") and out.image_embeds is not None:
                feats = out.image_embeds
            elif hasattr(out, "pooler_output") and out.pooler_output is not None:
                feats = out.pooler_output
            else:
                raise RuntimeError("Could not extract image embeddings from model output")

        feats = feats.float()
        feats = feats / (feats.norm(dim=-1, keepdim=True) + 1e-12)
        return feats[0].detach().cpu().numpy().astype(np.float32)
