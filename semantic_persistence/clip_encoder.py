# -*- coding: utf-8 -*-
"""
clip_encoder.py (Python 3.6.9 + transformers 4.18 compatible)

Offline usage:
  Put the model files in a local folder, for example:
    /workspace/OptUncertain/models/clip-vit-base-patch32/

  Then load with local_files_only=True.

Recommended model:
  openai/clip-vit-base-patch32
"""

from __future__ import print_function

import numpy as np
import torch


class _CLIPBase(object):
    def __init__(self, model_id, device=None, fp16=True, local_files_only=False):
        self.model_id = model_id
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.fp16 = bool(fp16) and (self.device == "cuda")
        self.local_files_only = bool(local_files_only)
        self._load()

    def _load(self):
        from transformers import CLIPModel, CLIPProcessor

        self._processor = CLIPProcessor.from_pretrained(
            self.model_id, local_files_only=self.local_files_only
        )
        self._model = CLIPModel.from_pretrained(
            self.model_id, local_files_only=self.local_files_only
        )

        self._model.eval().to(self.device)
        if self.fp16:
            self._model = self._model.half()


class CLIPTextEmbedder(_CLIPBase):
    @torch.no_grad()
    def embed(self, text):
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")

        inputs = self._processor(
            text=[text], return_tensors="pt", padding=True, truncation=True
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # Some model classes return an output object, not a tensor
        if hasattr(self._model, "get_text_features"):
            out = self._model.get_text_features(**inputs)
        else:
            out = self._model(**inputs)

        feats = _unwrap_feats(out, prefer="text")
        feats = feats.float()
        feats = feats / (feats.norm(dim=-1, keepdim=True) + 1e-12)
        return feats[0].detach().cpu().numpy().astype(np.float32)


class CLIPImageEmbedder(_CLIPBase):
    @torch.no_grad()
    def embed(self, image_rgb):
        if image_rgb is None or not isinstance(image_rgb, np.ndarray):
            raise ValueError("image_rgb must be a numpy array")
        if image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
            raise ValueError("image_rgb must have shape (H, W, 3)")

        inputs = self._processor(images=[image_rgb], return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        if hasattr(self._model, "get_image_features"):
            out = self._model.get_image_features(**inputs)
        else:
            out = self._model(**inputs)

        feats = _unwrap_feats(out, prefer="image")
        feats = feats.float()
        feats = feats / (feats.norm(dim=-1, keepdim=True) + 1e-12)
        return feats[0].detach().cpu().numpy().astype(np.float32)


def _unwrap_feats(out, prefer: str):
    """
    Convert various HF outputs to a torch.Tensor feature matrix.
    prefer: "text" or "image"
    """
    import torch

    if isinstance(out, torch.Tensor):
        return out

    # CLIPModel forward output can have text_embeds / image_embeds
    if prefer == "text" and hasattr(out, "text_embeds") and out.text_embeds is not None:
        return out.text_embeds
    if (
        prefer == "image"
        and hasattr(out, "image_embeds")
        and out.image_embeds is not None
    ):
        return out.image_embeds

    # Many HF encoder outputs use pooler_output
    if hasattr(out, "pooler_output") and out.pooler_output is not None:
        return out.pooler_output

    # Fallback: use CLS token from last_hidden_state if available
    if hasattr(out, "last_hidden_state") and out.last_hidden_state is not None:
        return out.last_hidden_state[:, 0, :]

    raise RuntimeError(f"Could not extract features from output type: {type(out)}")
