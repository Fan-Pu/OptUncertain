from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Sequence


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)
    if not isinstance(data, dict):
        raise TypeError("%s must contain a JSON object." % str(path))
    return data


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2)
        file_handle.write("\n")


def refresh_manifest(batch_config_path: Path, manifest_path: Path) -> Path:
    project_root = _project_root()
    sys.path.insert(0, str(project_root))

    from main import refresh_batch_summary_hash_metadata

    batch_config = _read_json(batch_config_path)
    summary = _read_json(manifest_path)
    batch_id = batch_config_path.stem
    refreshed = refresh_batch_summary_hash_metadata(
        summary=summary,
        batch_config=batch_config,
        batch_id=batch_id,
        summary_path=manifest_path,
    )
    _write_json(manifest_path, refreshed)
    return manifest_path


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh generated batch-case manifest compatibility metadata."
    )
    parser.add_argument(
        "--batch-config",
        required=True,
        help="Current batch config JSON, for example scenarios/batch_test.json.",
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Existing generated_cases.json manifest to validate and update.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    output_path = refresh_manifest(
        batch_config_path=Path(args.batch_config),
        manifest_path=Path(args.manifest),
    )
    print("Updated %s" % str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
