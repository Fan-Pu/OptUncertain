"""semantic_persistence.interfaces

Python 3.6 compatible interfaces.

We avoid:
  - typing.Protocol (Python 3.8+)

Instead we provide simple base classes that your implementations can inherit.
"""

from typing import Any, Dict, List

import numpy as np


class TextEmbedder(object):
    """Text -> embedding vector."""

    def embed(self, text):
        """Return a 1D numpy array (D,)."""
        raise NotImplementedError


class ImageEmbedder(object):
    """RGB image -> embedding vector."""

    def embed(self, image_rgb):
        """Return a 1D numpy array (D,)."""
        raise NotImplementedError


class MLLMClient(object):
    """MLLM wrapper for semantic proposals and equivalence checks."""

    def propose_semantic_nodes(
        self,
        instruction,  # type: str
        observation_images,  # type: List[np.ndarray]
        memory_summary,  # type: str
        max_proposals=6,  # type: int
    ):
        # type: (...) -> List[Dict[str, Any]]
        raise NotImplementedError

    def verify_equivalence(
        self,
        new_label,  # type: str
        new_syn,  # type: List[str]
        old_label,  # type: str
        old_syn,  # type: List[str]
        evidence,  # type: str
    ):
        # type: (...) -> Dict[str, Any]
        raise NotImplementedError
