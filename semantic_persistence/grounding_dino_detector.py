from __future__ import annotations

import io
from typing import Dict, Iterable, List, Optional

import numpy as np
from PIL import Image


class GroundingDinoDetector:
    def __init__(
        self,
        model_name: str = "IDEA-Research/grounding-dino-tiny",
        score_threshold: float = 0.35,
        text_threshold: float = 0.25,
        device: Optional[str] = None,
    ):
        import torch
        from transformers import AutoModelForZeroShotObjectDetection
        from transformers import GroundingDinoProcessor

        self.torch = torch
        self.model_name = str(model_name)
        self.score_threshold = float(score_threshold)
        self.text_threshold = float(text_threshold)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        self.processor = GroundingDinoProcessor.from_pretrained(self.model_name)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(
            self.model_name
        )
        self.model.to(self.device)
        self.model.eval()

    @staticmethod
    def _to_pil_image(image: object) -> Image.Image:
        if isinstance(image, Image.Image):
            return image.convert("RGB")
        if isinstance(image, bytes):
            return Image.open(io.BytesIO(image)).convert("RGB")
        if isinstance(image, np.ndarray):
            if image.dtype != np.uint8:
                image = image.astype(np.uint8)
            return Image.fromarray(image).convert("RGB")
        raise TypeError("Expected PIL image, JPEG bytes, or numpy.ndarray.")

    def detect(
        self,
        image: object,
        text_queries: Iterable[str],
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, object]]:
        query_scores = self.score_queries(
            image=image,
            text_queries=text_queries,
            score_threshold=score_threshold,
        )
        detections = []
        for query_score in query_scores:
            for detection in query_score["open_vocab_detections"]:
                detections.append(
                    {
                        "query": query_score["query"],
                        "label_index": query_score["label_index"],
                        "score": detection["score"],
                        "box": detection["box"],
                    }
                )
        return detections

    def score_queries(
        self,
        image: object,
        text_queries: Iterable[str],
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, object]]:
        queries = [str(query) for query in text_queries]
        if not queries:
            return []

        threshold = self.score_threshold if score_threshold is None else float(
            score_threshold
        )
        pil_image = self._to_pil_image(image)
        query_scores = []

        for query_index, query in enumerate(queries):
            inputs = self.processor(
                images=pil_image,
                text=[[query]],
                return_tensors="pt",
            ).to(self.device)

            with self.torch.inference_mode():
                outputs = self.model(**inputs)

            results = self.processor.post_process_grounded_object_detection(
                outputs,
                inputs.input_ids,
                threshold=0.0,
                text_threshold=self.text_threshold,
                target_sizes=[pil_image.size[::-1]],
            )[0]

            boxes = results["boxes"].detach().cpu().tolist()
            scores = results["scores"].detach().cpu().tolist()

            open_vocab_detections = [
                {
                    "score": float(score),
                    "box": [float(value) for value in box],
                }
                for box, score in zip(boxes, scores)
                if float(score) >= threshold
            ]

            max_score = max([float(score) for score in scores], default=0.0)
            query_scores.append(
                {
                    "query": query,
                    "label_index": query_index,
                    "score": max_score,
                    "score_threshold": threshold,
                    "open_vocab_detections": open_vocab_detections,
                }
            )

        return query_scores
