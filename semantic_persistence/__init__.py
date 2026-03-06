"""
semantic_persistence package

This package implements a lightweight semantic persistence component:
  - propose semantic regions (via an MLLM client)
  - ground labels to Matterport viewpoint sets (retrieval)
  - match/merge nodes over time (persistence)
"""

from .mllm_client import LocalQwen2VLClient
from .nav_graph import load_nav_graph, shortest_path_next_hop, argmin_distance_to_set
