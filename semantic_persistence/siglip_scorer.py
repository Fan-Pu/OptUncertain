from __future__ import annotations

from typing import Dict, Iterable, List
import torch
import numpy as np
from PIL import Image


class SigLIPScorer:
    def __init__(
        self,
        model_name: str = "google/siglip-large-patch16-256",
        device: str | None = None,
    ):
        import torch
        from transformers import AutoModel, AutoProcessor

        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = AutoProcessor.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()
        self.text_embedding_cache: Dict[str, object] = {}

    def clear_cache(self) -> None:
        self.text_embedding_cache.clear()

    def _to_pil_images(self, images: Iterable[object]) -> List[Image.Image]:
        pil_images = []
        for image in images:
            if isinstance(image, Image.Image):
                pil_images.append(image)
                continue
            if not isinstance(image, np.ndarray):
                raise TypeError("Expected PIL image or numpy.ndarray")
            if image.dtype != np.uint8:
                image = image.astype(np.uint8)
            pil_images.append(Image.fromarray(image))
        return pil_images

    def _encode_text(self, text: str):
        if text not in self.text_embedding_cache:
            inputs = self.processor(text=[text], padding=True, return_tensors="pt")
            inputs = {key: value.to(self.device) for key, value in inputs.items()}
            with self.torch.no_grad():
                embeddings = self.model.get_text_features(**inputs)
            embeddings = self.torch.nn.functional.normalize(embeddings, dim=-1)
            self.text_embedding_cache[text] = embeddings[0]
        return self.text_embedding_cache[text]

    def _encode_images(self, images: Iterable[object]):
        pil_images = self._to_pil_images(images)
        inputs = self.processor(images=pil_images, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with self.torch.no_grad():
            embeddings = self.model.get_image_features(**inputs)
        return self.torch.nn.functional.normalize(embeddings, dim=-1)

    def score_images_text(self, images: Iterable[object], text: str) -> float:
        images = list(images)
        if not images:
            return 0.0
        text_embedding = self._encode_text(str(text))
        image_embeddings = self._encode_images(images)
        similarities = image_embeddings @ text_embedding
        return float(similarities.max().item())

    def test_score_images_text(self, image_path: str) -> None:
        image = Image.open(image_path).convert("RGB")
        texts = [
            "a photo of a hallway",
            "a photo of a kitchen",
            "a photo of a bedroom",
            "a photo of a bathroom",
        ]
        inputs = self.processor(
            text=texts, images=image, padding="max_length", return_tensors="pt"
        )

        inputs = {
            k: (
                v.to(self.device, dtype=torch.float16)
                if k == "pixel_values"
                else v.to(self.device)
            )
            for k, v in inputs.items()
        }

        with torch.inference_mode():
            outputs = self.model(**inputs)

        logits = outputs.logits_per_image[0]
        probs = torch.sigmoid(logits)

        for text, prob in zip(texts, probs):
            print(f"{text}: {prob.item():.4f}")
