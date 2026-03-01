import numpy as np
import torch
from transformers import OwlViTProcessor, OwlViTForObjectDetection

"""
This module implements open-vocabulary object detection using OWL-ViT and a robust distance estimation from the detected box using depth values."""


def _depth_to_meters(depth_raw: np.ndarray) -> np.ndarray:
    """
    MatterportSim depth: (H,W,1) uint16, 0.25mm per value, value=0 means invalid.
    Convert to meters, invalid -> NaN.
    """
    depth = np.array(depth_raw, copy=False)
    if depth.ndim == 3 and depth.shape[-1] == 1:
        depth = depth[:, :, 0]
    depth = depth.astype(np.float32)
    depth[depth <= 0] = np.nan
    return depth / 4000.0


def distance_from_box(depth_raw, box_xyxy, percentile=10.0) -> float:
    """
    Robust distance estimate from depth values inside the detected box.
    Uses a percentile instead of min to reduce sensitivity to noisy pixels.
    """
    z = _depth_to_meters(depth_raw)
    x1, y1, x2, y2 = box_xyxy
    region = z[y1:y2, x1:x2]
    vals = region[~np.isnan(region)]
    if vals.size == 0:
        return float("inf")
    return float(np.percentile(vals, percentile))


class OwlDetector:
    """
    Open-vocabulary text-conditioned box detection using OWL-ViT.
    This implementation avoids processor.post_process_object_detection()
    to stay compatible across transformers versions.
    """

    def __init__(self, device=None, model_name="google/owlvit-base-patch32"):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.processor = OwlViTProcessor.from_pretrained(model_name)
        self.model = OwlViTForObjectDetection.from_pretrained(model_name).to(device)
        self.model.eval()

    @torch.no_grad()
    def detect_best_box(self, rgb_uint8, text_query, score_thresh=0.2):
        """
        Args:
            rgb_uint8: (H,W,3) RGB uint8
            text_query: string, e.g., "glass"
            score_thresh: float, probability threshold on the best query score

        Returns:
            (box_xyxy, score)
            box_xyxy: (x1,y1,x2,y2) int pixels, or None if not detected
            score: float confidence for the returned box
        """
        H, W = rgb_uint8.shape[:2]

        inputs = self.processor(
            text=[text_query], images=rgb_uint8, return_tensors="pt"
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        outputs = self.model(**inputs)

        # outputs.logits: [B, Q, C]
        # outputs.pred_boxes: [B, Q, 4] in normalized cxcywh
        logits = outputs.logits[0]  # [Q, C]
        pred_boxes = outputs.pred_boxes[0]  # [Q, 4]

        # Convert logits to probabilities
        probs = logits.sigmoid()  # [Q, C]

        # Many configs include a background class as the last column.
        # Dropping the last class is safe when background exists.
        if probs.shape[-1] > 1:
            probs_nobg = probs[:, :-1]
        else:
            probs_nobg = probs

        # Best score per query across classes
        best_per_query, _ = probs_nobg.max(dim=-1)  # [Q]
        best_score = float(best_per_query.max().item())
        best_q = int(best_per_query.argmax().item())

        if best_score < score_thresh:
            return None, best_score

        # Convert cxcywh -> xyxy pixel coords
        cx, cy, bw, bh = pred_boxes[best_q].tolist()
        x1 = int((cx - bw / 2.0) * W)
        y1 = int((cy - bh / 2.0) * H)
        x2 = int((cx + bw / 2.0) * W)
        y2 = int((cy + bh / 2.0) * H)

        # Clamp to image bounds
        x1 = max(0, min(W - 1, x1))
        y1 = max(0, min(H - 1, y1))
        x2 = max(0, min(W, x2))
        y2 = max(0, min(H, y2))

        # Sanity check for a valid box
        if x2 <= x1 + 1 or y2 <= y1 + 1:
            return None, best_score

        return (x1, y1, x2, y2), best_score

    def detect_and_distance(
        self,
        rgb,
        depth_raw,
        text_query,
        score_thresh=0.2,
        dist_thresh_m=1.5,
        percentile=10.0,
    ):
        """
        Returns:
            found (bool),
            distance_m (float),
            box_xyxy (tuple or None),
            score (float)

        found is True only if:
        - the detector score >= score_thresh
        - depth distance is finite
        - distance_m < dist_thresh_m
        """
        box, score = self.detect_best_box(rgb, text_query, score_thresh=score_thresh)
        if box is None:
            return False, float("inf"), None, float(score)

        dist_m = distance_from_box(depth_raw, box, percentile=percentile)
        found = (
            (score >= score_thresh) and np.isfinite(dist_m) and (dist_m < dist_thresh_m)
        )
        return found, float(dist_m), box, float(score)
