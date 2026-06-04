from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tqdm import tqdm

from graph_visualizer.loader import resolve_project_root
from graph_visualizer.topdown_texture import (
    DEFAULT_COMPOSITE_MAX_Z_OFFSET_METERS,
    DEFAULT_COMPOSITE_SLICES,
    DEFAULT_CUT_Z_OFFSET_METERS,
    generate_cached_topdown_texture,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate cached house texture files for a scan.")
    parser.add_argument("scan_id", help="Matterport scan id, such as 1pXnuDYAj8r.")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--connectivity-dir", type=Path, default=None)
    parser.add_argument("--output-size", type=int, default=1080)
    parser.add_argument("--texture-cut-z-offset", type=float, default=DEFAULT_CUT_Z_OFFSET_METERS)
    parser.add_argument(
        "--texture-render-mode",
        choices=("multi_slice_composite", "single_cutaway"),
        default="multi_slice_composite",
    )
    parser.add_argument(
        "--texture-composite-max-z-offset",
        type=float,
        default=DEFAULT_COMPOSITE_MAX_Z_OFFSET_METERS,
    )
    parser.add_argument("--texture-composite-slices", type=int, default=DEFAULT_COMPOSITE_SLICES)
    parser.add_argument("--force", action="store_true", help="Regenerate even when cache is current.")
    args = parser.parse_args(argv)

    project_root = resolve_project_root(args.project_root)
    connectivity_dir = args.connectivity_dir or (project_root / "connectivity")
    progress_bar = None

    def update_progress(increment: int, total: int | None, message: str) -> None:
        nonlocal progress_bar
        if total is not None and progress_bar is None and total > 0:
            progress_bar = tqdm(
                total=total,
                unit="batch",
                file=sys.stdout,
                bar_format="{l_bar}{bar}| {percentage:3.0f}% ETA {remaining_s:.0f}s",
            )
        if progress_bar is not None:
            progress_bar.set_description(message)
            if increment:
                progress_bar.update(increment)

    metadata = generate_cached_topdown_texture(
        scan_id=args.scan_id,
        project_root=project_root,
        instance_name=args.scan_id,
        connectivity_dir=connectivity_dir,
        output_size=args.output_size,
        cut_z_offset=args.texture_cut_z_offset,
        render_mode=args.texture_render_mode,
        composite_max_z_offset=args.texture_composite_max_z_offset,
        composite_slices=args.texture_composite_slices,
        force=args.force,
        progress_callback=update_progress,
    )
    if progress_bar is not None:
        progress_bar.close()
    else:
        print("Texture cache is current.")
    print("Generated house texture cache for scan %s." % args.scan_id)
    for floor in metadata["floors"]:
        print("floor %s: %s" % (floor["floor_index"], floor["url"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
