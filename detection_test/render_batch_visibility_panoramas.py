from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


MANIFEST_FIELDNAMES = [
    "scan_id",
    "target_id",
    "target_description",
    "viewpoint_id",
    "viewpoint_index",
    "panorama_path",
    "reviewed_visible",
    "review_notes",
]


def _read_json(path: Path) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _target_viewpoint_rows(
    batch_config: Dict[str, object],
) -> Iterable[Tuple[str, str, str, str]]:
    for scan in batch_config["scans"]:
        scan_id = str(scan["scan_id"])
        for target in scan["targets"]:
            target_id = str(target["target_id"])
            description = str(target["description"])
            for viewpoint_id in target["detectable_viewpoint_ids"]:
                yield scan_id, target_id, description, str(viewpoint_id)


def _unique_viewpoints_by_scan(
    batch_config: Dict[str, object],
) -> Dict[str, List[str]]:
    scan_viewpoints: Dict[str, List[str]] = {}
    seen: set[Tuple[str, str]] = set()
    for scan_id, _target_id, _description, viewpoint_id in _target_viewpoint_rows(
        batch_config
    ):
        key = (scan_id, viewpoint_id)
        if key in seen:
            continue
        seen.add(key)
        scan_viewpoints.setdefault(scan_id, []).append(viewpoint_id)
    return scan_viewpoints


def _panorama_path(
    panorama_root: Path,
    scan_id: str,
    viewpoint_index: int,
    viewpoint_id: str,
) -> Path:
    return panorama_root / scan_id / ("%04d_%s.jpg" % (viewpoint_index, viewpoint_id))


def _write_manifest(
    path: Path,
    rows: Sequence[Dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=MANIFEST_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def render_batch_visibility_panoramas(
    batch_config_path: Path,
    out_dir: Path,
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    import cv2
    import Helper

    batch_config = _read_json(batch_config_path)
    panorama_root = out_dir / "panoramas"
    scan_viewpoints = _unique_viewpoints_by_scan(batch_config)
    viewpoint_index_by_key: Dict[Tuple[str, str], int] = {}
    panorama_path_by_key: Dict[Tuple[str, str], Path] = {}

    for scan_id, viewpoint_ids in scan_viewpoints.items():
        Helper.build_viewpoint_index(scan_id)
        sim = Helper.init_render(batch_size=1, enable_render=False)
        sim.initialize()

        for viewpoint_id in viewpoint_ids:
            viewpoint_index = int(Helper.viewpoint_index_by_vp_label[viewpoint_id])
            output_path = _panorama_path(
                panorama_root=panorama_root,
                scan_id=scan_id,
                viewpoint_index=viewpoint_index,
                viewpoint_id=viewpoint_id,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)

            sim.newEpisode([scan_id], [viewpoint_id], [0.0], [0.0])
            observation = Helper.horizon_scan_return(
                sim=sim,
                agent_id="agent0",
                viewpoint_index_by_vp=Helper.viewpoint_index_by_vp_label,
            )
            raw_panorama_bgr = cv2.cvtColor(
                observation["raw_panorama"],
                cv2.COLOR_RGB2BGR,
            )
            if not cv2.imwrite(str(output_path), raw_panorama_bgr):
                raise RuntimeError("Failed to write panorama %s" % str(output_path))

            key = (scan_id, viewpoint_id)
            viewpoint_index_by_key[key] = viewpoint_index
            panorama_path_by_key[key] = output_path

    manifest_rows = []
    for scan_id, target_id, description, viewpoint_id in _target_viewpoint_rows(
        batch_config
    ):
        key = (scan_id, viewpoint_id)
        manifest_rows.append(
            {
                "scan_id": scan_id,
                "target_id": target_id,
                "target_description": description,
                "viewpoint_id": viewpoint_id,
                "viewpoint_index": viewpoint_index_by_key[key],
                "panorama_path": panorama_path_by_key[key].as_posix(),
                "reviewed_visible": "",
                "review_notes": "",
            }
        )

    _write_manifest(out_dir / "manifest.csv", manifest_rows)
    print(
        "Wrote %d panoramas and %d manifest rows to %s."
        % (
            len(panorama_path_by_key),
            len(manifest_rows),
            str(out_dir),
        )
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render every configured batch-test detectable viewpoint."
    )
    parser.add_argument(
        "--batch-config",
        default="scenarios/batch_test.json",
    )
    parser.add_argument(
        "--out",
        default="detection_test/batch_visibility_review",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    render_batch_visibility_panoramas(
        batch_config_path=Path(args.batch_config),
        out_dir=Path(args.out),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
