"""
nav_graph.py

Utilities for working with the Matterport connectivity graph.

In Matterport3DSimulator, the geometric navigation graph is fixed and known via:
  connectivity/<scan_id>_connectivity.json

We use it to:
  - load adjacency between viewpoint IDs
  - compute shortest paths (unweighted BFS)
  - choose the next hop toward a target viewpoint
"""

from typing import Dict, List, Optional, Set, Tuple
import json
import os
from collections import deque


def load_nav_graph(connectivity_dir: str, scan_id: str) -> Dict[str, List[str]]:
    """
    Returns:
      adjacency: dict vp_id -> list of neighbor vp_ids (both included and unobstructed).
    """
    path = os.path.join(connectivity_dir, f"{scan_id}_connectivity.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Connectivity file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    included = [bool(item.get("included", False)) for item in data]
    vp_ids = [str(item.get("image_id")) for item in data]

    adjacency: Dict[str, List[str]] = {vp: [] for vp, inc in zip(vp_ids, included) if inc}

    for i, item in enumerate(data):
        if not included[i]:
            continue
        src = vp_ids[i]
        unob = item.get("unobstructed", None)
        if unob is None:
            continue
        for j, ok in enumerate(unob):
            if not ok:
                continue
            if j >= len(vp_ids) or not included[j]:
                continue
            dst = vp_ids[j]
            adjacency[src].append(dst)

    return adjacency


def shortest_path_next_hop(
    adjacency: Dict[str, List[str]],
    start_vp: str,
    goal_vp: str,
) -> Optional[str]:
    """
    Compute the next hop from start_vp to goal_vp on an unweighted graph using BFS.

    Returns:
      next_vp: the first viewpoint after start_vp along a shortest path, or None if unreachable or already at goal.
    """
    if start_vp == goal_vp:
        return None
    if start_vp not in adjacency or goal_vp not in adjacency:
        return None

    q = deque([start_vp])
    parent: Dict[str, Optional[str]] = {start_vp: None}

    while q:
        u = q.popleft()
        if u == goal_vp:
            break
        for v in adjacency.get(u, []):
            if v in parent:
                continue
            parent[v] = u
            q.append(v)

    if goal_vp not in parent:
        return None

    # backtrack: goal -> ... -> start, take the node just after start
    cur = goal_vp
    prev = parent[cur]
    while prev is not None and prev != start_vp:
        cur = prev
        prev = parent[cur]
    return cur if prev == start_vp else None


def argmin_distance_to_set(
    adjacency: Dict[str, List[str]],
    start_vp: str,
    target_set: Set[str],
    max_nodes: int = 5000,
) -> Tuple[Optional[str], Optional[int]]:
    """
    Find the closest target viewpoint in target_set from start_vp in hop distance (BFS).

    Returns:
      (best_target_vp, hop_distance)
    """
    if start_vp in target_set:
        return start_vp, 0

    q = deque([start_vp])
    dist = {start_vp: 0}
    explored = 0

    while q and explored < max_nodes:
        u = q.popleft()
        explored += 1
        d = dist[u]
        for v in adjacency.get(u, []):
            if v in dist:
                continue
            dist[v] = d + 1
            if v in target_set:
                return v, dist[v]
            q.append(v)

    return None, None
