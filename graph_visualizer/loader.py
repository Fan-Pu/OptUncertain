from __future__ import annotations

import json
import platform
import re
from pathlib import Path
from urllib.parse import quote

from route_plotter import load_environment_graph

from .topdown_texture import generate_cached_topdown_texture


STEP_RE = re.compile(r"graph_layout_step_(\d{4})\.json$")
OBSERVATION_RE = re.compile(r"observation_step_(\d{4})_agent_(.+)\.jpg$")


def resolve_project_root(project_root: str | Path | None = None) -> Path:
    if project_root is not None:
        return Path(project_root).resolve()
    return Path(__file__).resolve().parents[1]


def load_visualization_steps(
    instance_name: str,
    project_root: str | Path | None = None,
) -> list[dict[str, object]]:
    root = resolve_project_root(project_root)
    raw_dir = root / "mllm_raw_outputs" / str(instance_name)
    debug_dir = root / "mllm_debug_outputs" / str(instance_name)

    step_indices = _discover_step_indices(debug_dir)
    return [
        _load_step(
            instance_name=str(instance_name),
            project_root=root,
            raw_dir=raw_dir,
            debug_dir=debug_dir,
            step_index=step_index,
        )
        for step_index in step_indices
    ]


def load_solution_payload(
    instance_name: str,
    project_root: str | Path | None = None,
    texture_output_size: int = 1800,
    texture_cut_z_offset: float = 0.15,
    texture_render_mode: str = "multi_slice_composite",
    texture_composite_max_z_offset: float = 1.6,
    texture_composite_slices: int = 5,
    include_house_texture: bool = True,
) -> dict[str, object]:
    root = resolve_project_root(project_root)
    debug_dir = root / "mllm_debug_outputs" / str(instance_name)
    solutions = _load_solution_summaries(
        instance_name=str(instance_name),
        project_root=root,
        debug_dir=debug_dir,
    )
    payload: dict[str, object] = {
        "solutions": solutions,
        "environment_graph": _load_route_environment_graph(
            instance_name=str(instance_name),
            project_root=root,
        ),
    }
    if include_house_texture:
        payload["environment_graph"]["house_texture"] = load_house_texture_payload(
            instance_name=instance_name,
            project_root=root,
            texture_output_size=texture_output_size,
            texture_cut_z_offset=texture_cut_z_offset,
            texture_render_mode=texture_render_mode,
            texture_composite_max_z_offset=texture_composite_max_z_offset,
            texture_composite_slices=texture_composite_slices,
        )
    return payload


def load_house_texture_payload(
    instance_name: str,
    project_root: str | Path | None = None,
    texture_output_size: int = 1800,
    texture_cut_z_offset: float = 0.15,
    texture_render_mode: str = "multi_slice_composite",
    texture_composite_max_z_offset: float = 1.6,
    texture_composite_slices: int = 5,
) -> dict[str, object]:
    root = resolve_project_root(project_root)
    scenario = _read_json(root / "scenarios" / ("%s.json" % str(instance_name)))
    scan_id = str(scenario["scan_id"])
    return generate_cached_topdown_texture(
        scan_id=scan_id,
        project_root=root,
        instance_name=str(instance_name),
        connectivity_dir=root / "connectivity",
        output_size=texture_output_size,
        cut_z_offset=texture_cut_z_offset,
        render_mode=texture_render_mode,
        composite_max_z_offset=texture_composite_max_z_offset,
        composite_slices=texture_composite_slices,
    )


def _load_solution_summaries(
    instance_name: str,
    project_root: Path,
    debug_dir: Path,
) -> list[dict[str, object]]:
    specs = [
        (
            "mllm",
            "Proposed final solution",
            debug_dir / ("%s_mllm_route_summary.txt" % instance_name),
        ),
        (
            "oracle",
            "Theoretical optimal solution",
            debug_dir / ("%s_oracle_route_summary.txt" % instance_name),
        ),
    ]
    solutions = []
    for solution_id, label, path in specs:
        if path.exists():
            solutions.append(
                {
                    "id": solution_id,
                    "label": label,
                    "file": _relative_posix(project_root, path),
                    "summary": _read_json(path),
                }
            )
    return solutions


def _load_route_environment_graph(
    instance_name: str,
    project_root: Path,
) -> dict[str, object]:
    scenario = _read_json(project_root / "scenarios" / ("%s.json" % instance_name))
    if platform.system() == "Windows":
        environment_graph = load_environment_graph(
            scan_id=str(scenario["scan_id"]),
            connectivity_dir=project_root / "connectivity",
        )
    else:
        environment_graph = load_environment_graph(scan_id=str(scenario["scan_id"]))
    return {
        "scan_id": environment_graph.scan_id,
        "nodes": [
            {
                "node_id": int(node_id),
                "viewpoint_id": environment_graph.viewpoint_id_by_index[node_id],
                "x": float(environment_graph.coords_by_node_id[node_id][0]),
                "y": float(environment_graph.coords_by_node_id[node_id][1]),
            }
            for node_id in sorted(environment_graph.viewpoint_id_by_index)
        ],
        "edges": [
            {
                "i": int(edge_id[0]),
                "j": int(edge_id[1]),
                "distance": float(distance),
            }
            for edge_id, distance in sorted(environment_graph.edge_distances.items())
        ],
    }


def _discover_step_indices(debug_dir: Path) -> list[int]:
    step_indices = []
    for path in debug_dir.glob("graph_layout_step_*.json"):
        match = STEP_RE.match(path.name)
        if match is not None:
            step_indices.append(int(match.group(1)))
    if not step_indices:
        raise FileNotFoundError(
            "No graph_layout_step_XXXX.json files found in %s" % debug_dir
        )
    return sorted(step_indices)


def _load_step(
    instance_name: str,
    project_root: Path,
    raw_dir: Path,
    debug_dir: Path,
    step_index: int,
) -> dict[str, object]:
    suffix = "%04d" % int(step_index)
    layout_path = debug_dir / ("graph_layout_step_%s.json" % suffix)
    hypothesis_path = debug_dir / ("hypothesis_step_%s.json" % suffix)
    semantic_path = raw_dir / ("semantic_step_%s.json" % suffix)
    detection_path = raw_dir / ("detection_step_%s.json" % suffix)
    open_vocab_verification_path = raw_dir / (
        "open_vocab_verification_step_%s.json" % suffix
    )
    user_message_path = raw_dir / ("user_message_step_%s.txt" % suffix)

    layout = _read_json(layout_path)
    hypothesis = _read_json(hypothesis_path)
    detection = _read_json(detection_path)
    open_vocab_verification = (
        _read_json(open_vocab_verification_path)
        if open_vocab_verification_path.exists()
        else None
    )
    semantic, user_message = _load_semantic_and_user_message(
        semantic_path=semantic_path,
        user_message_path=user_message_path,
        hypothesis=hypothesis,
    )

    observation_images = _load_observation_images(
        project_root=project_root,
        debug_dir=debug_dir,
        step_index=step_index,
    )

    return {
        "instance_name": instance_name,
        "step_index": int(step_index),
        "files": {
            "layout": _relative_posix(project_root, layout_path),
            "hypothesis": _relative_posix(project_root, hypothesis_path),
            "semantic": _relative_posix(project_root, semantic_path),
            "detection": _relative_posix(project_root, detection_path),
            "open_vocab_verification": _relative_posix(
                project_root,
                open_vocab_verification_path,
            ),
            "user_message": _relative_posix(project_root, user_message_path),
        },
        "layout": layout,
        "hypothesis": hypothesis,
        "semantic": semantic,
        "detection": detection,
        "open_vocab_verification": open_vocab_verification,
        "user_message": user_message,
        "observation_images": observation_images,
    }


def _load_semantic_and_user_message(
    semantic_path: Path,
    user_message_path: Path,
    hypothesis: object,
) -> tuple[object, str]:
    semantic_exists = semantic_path.exists()
    user_message_exists = user_message_path.exists()

    if semantic_exists and user_message_exists:
        return (
            _read_json(semantic_path),
            user_message_path.read_text(encoding="utf-8"),
        )

    if _is_terminal_detection_only_step(hypothesis):
        semantic = _read_json(semantic_path) if semantic_exists else None
        user_message = (
            user_message_path.read_text(encoding="utf-8")
            if user_message_exists
            else ""
        )
        return semantic, user_message

    return (
        _read_json(semantic_path),
        user_message_path.read_text(encoding="utf-8"),
    )


def _is_terminal_detection_only_step(hypothesis: object) -> bool:
    if not isinstance(hypothesis, dict):
        return False

    target_found = hypothesis.get("target_found")
    if not isinstance(target_found, dict) or not target_found:
        return False

    return all(bool(found) for found in target_found.values())


def _load_observation_images(
    project_root: Path,
    debug_dir: Path,
    step_index: int,
) -> list[dict[str, str]]:
    suffix = "%04d" % int(step_index)
    images = []
    for path in sorted(debug_dir.glob("observation_step_%s_agent_*.jpg" % suffix)):
        match = OBSERVATION_RE.match(path.name)
        agent_id = match.group(2)
        asset_path = _relative_posix(project_root, path)
        images.append(
            {
                "agent_id": agent_id,
                "asset_path": asset_path,
                "url": "/assets/%s" % quote(asset_path, safe="/"),
            }
        )
    return images


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative_posix(project_root: Path, path: Path) -> str:
    return path.relative_to(project_root).as_posix()
