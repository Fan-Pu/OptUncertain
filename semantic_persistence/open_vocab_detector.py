from __future__ import annotations

import io
from typing import Dict, Iterable, List, Optional

import numpy as np
from PIL import Image


class OpenVocabularyDetector:
    def __init__(
        self,
        model_name: str = "google/owlv2-base-patch16-ensemble",
        score_threshold: float = 0.15,
        device: Optional[str] = None,
    ):
        import torch
        from transformers import Owlv2ForObjectDetection, Owlv2Processor

        self.torch = torch
        self.model_name = str(model_name)
        self.score_threshold = float(score_threshold)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        self.processor = Owlv2Processor.from_pretrained(self.model_name)
        self.model = Owlv2ForObjectDetection.from_pretrained(self.model_name)
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
        inputs = self.processor(
            text=[queries],
            images=pil_image,
            return_tensors="pt",
        )
        inputs = {key: value.to(self.device) for key, value in inputs.items()}

        with self.torch.inference_mode():
            outputs = self.model(**inputs)

        target_sizes = self.torch.tensor(
            [pil_image.size[::-1]],
            device=self.device,
        )
        results = self.processor.image_processor.post_process_object_detection(
            outputs=outputs,
            target_sizes=target_sizes,
            threshold=0.0,
        )[0]

        query_scores = [
            {
                "query": query,
                "label_index": query_index,
                "score": 0.0,
                "score_threshold": threshold,
                "open_vocab_detections": [],
            }
            for query_index, query in enumerate(queries)
        ]

        boxes = results["boxes"].detach().cpu().tolist()
        scores = results["scores"].detach().cpu().tolist()
        labels = results["labels"].detach().cpu().tolist()

        for box, score, label in zip(boxes, scores, labels):
            label_index = int(label)
            score = float(score)
            query_scores[label_index]["score"] = max(
                float(query_scores[label_index]["score"]),
                score,
            )
            if score >= threshold:
                query_scores[label_index]["open_vocab_detections"].append(
                    {
                        "score": score,
                        "box": [float(value) for value in box],
                    }
                )

        return query_scores
