from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote


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
    user_message_path = raw_dir / ("user_message_step_%s.txt" % suffix)

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
            "user_message": _relative_posix(project_root, user_message_path),
        },
        "layout": _read_json(layout_path),
        "hypothesis": _read_json(hypothesis_path),
        "semantic": _read_json(semantic_path),
        "detection": _read_json(detection_path),
        "user_message": user_message_path.read_text(encoding="utf-8"),
        "observation_images": observation_images,
    }


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
