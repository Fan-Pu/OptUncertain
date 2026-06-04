from __future__ import annotations

import json
import math
import os
import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import numba as nb
import numpy as np
from PIL import Image

from .floors import infer_floors, load_connectivity_viewpoints


SINGLE_CUTAWAY_RENDER_MODE = "single_cutaway_v1"
MULTI_SLICE_RENDER_MODE = "multi_slice_hole_fill_v1"
TEXTURE_RENDER_MODES = {
    "single_cutaway": SINGLE_CUTAWAY_RENDER_MODE,
    "multi_slice_composite": MULTI_SLICE_RENDER_MODE,
}
DEFAULT_CUT_Z_OFFSET_METERS = 0.1
DEFAULT_COMPOSITE_MAX_Z_OFFSET_METERS = 1.6
DEFAULT_COMPOSITE_SLICES = 5
TEXTURE_CACHE_DIR_NAME = "topdown_texture_cache"
TextureProgressCallback = Callable[[int, int | None, str], None]


@dataclass(frozen=True)
class ObjMesh:
    vertices: list[tuple[float, float, float]]
    texcoords: list[tuple[float, float]]
    faces: list[tuple[tuple[int, int], tuple[int, int], tuple[int, int], str]]


@dataclass(frozen=True)
class TextureRenderAssets:
    mesh: ObjMesh
    textures: dict[str, np.ndarray]
    face_z_ranges: list[tuple[float, float]]
    face_batches: list["TextureFaceBatch"]
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    width: int
    height: int


@dataclass(frozen=True)
class TextureFaceBatch:
    material: str
    texture: np.ndarray
    vertices: np.ndarray
    texcoords: np.ndarray
    z_min: np.ndarray
    z_max: np.ndarray


def generate_cached_topdown_texture(
    *,
    scan_id: str,
    project_root: Path,
    instance_name: str,
    connectivity_dir: Path,
    floors: list[dict[str, object]] | None = None,
    output_size: int = 1080,
    cut_z_offset: float = DEFAULT_CUT_Z_OFFSET_METERS,
    render_mode: str = "multi_slice_composite",
    composite_max_z_offset: float = DEFAULT_COMPOSITE_MAX_Z_OFFSET_METERS,
    composite_slices: int = DEFAULT_COMPOSITE_SLICES,
    force: bool = False,
    progress_callback: TextureProgressCallback | None = None,
) -> dict[str, object]:
    matterport_data_dir = Path(os.environ["MATTERPORT_DATA_DIR"])
    mesh_zip_path = (
        matterport_data_dir
        / "v1"
        / "scans"
        / str(scan_id)
        / "matterport_mesh.zip"
    )
    if floors is None:
        floors = infer_floors(
            load_connectivity_viewpoints(
                connectivity_dir / ("%s_connectivity.json" % str(scan_id))
            )
        )
    metadata_render_mode = TEXTURE_RENDER_MODES[render_mode]
    floor_specs = _topdown_texture_floor_specs(
        floors=floors,
        project_root=project_root,
        scan_id=scan_id,
        render_mode=metadata_render_mode,
        output_size=output_size,
        cut_z_offset=cut_z_offset,
        composite_max_z_offset=composite_max_z_offset,
        composite_slices=composite_slices,
    )

    missing_specs = []
    for spec in floor_specs:
        png_path = spec["png_path"]
        metadata_path = spec["metadata_path"]

        if not force and _cached_texture_is_current(
            png_path=png_path,
            metadata_path=metadata_path,
            cut_z=spec["cut_z"],
            output_size=output_size,
            cut_z_offset=cut_z_offset,
            render_mode=metadata_render_mode,
            composite_max_z_offset=composite_max_z_offset,
            composite_max_z=spec["composite_max_z"],
            composite_slices=composite_slices,
            floor_index=spec["floor_index"],
            floor_reference_z=spec["reference_z"],
            floor_lower_z=spec["lower_z"],
            floor_upper_z=spec["upper_z"],
        ):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        else:
            missing_specs.append(spec)
            metadata = None
        spec["metadata"] = metadata

    assets = (
        _load_texture_render_assets(
            mesh_zip_path=mesh_zip_path,
            output_size=output_size,
        )
        if missing_specs
        else None
    )
    if assets is not None and progress_callback is not None:
        render_passes = 1 if metadata_render_mode == SINGLE_CUTAWAY_RENDER_MODE else int(composite_slices)
        progress_callback(
            0,
            len(missing_specs) * render_passes * len(assets.face_batches),
            "mesh loaded",
        )
    for spec in missing_specs:
        metadata_path = spec["metadata_path"]
        png_path = spec["png_path"]
        metadata = _render_topdown_texture(
            assets=assets,
            png_path=png_path,
            output_size=output_size,
            cut_z=spec["cut_z"],
            cut_z_offset=cut_z_offset,
            render_mode=metadata_render_mode,
            composite_max_z_offset=composite_max_z_offset,
            composite_max_z=spec["composite_max_z"],
            composite_slices=composite_slices,
            floor_index=spec["floor_index"],
            floor_reference_z=spec["reference_z"],
            floor_lower_z=spec["lower_z"],
            floor_upper_z=spec["upper_z"],
            progress_callback=progress_callback,
        )
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        spec["metadata"] = metadata

    return _topdown_texture_payload_from_specs(project_root=project_root, floor_specs=floor_specs)


def load_cached_topdown_texture(
    *,
    scan_id: str,
    project_root: Path,
    connectivity_dir: Path,
    floors: list[dict[str, object]] | None = None,
    output_size: int = 1080,
    cut_z_offset: float = DEFAULT_CUT_Z_OFFSET_METERS,
    render_mode: str = "multi_slice_composite",
    composite_max_z_offset: float = DEFAULT_COMPOSITE_MAX_Z_OFFSET_METERS,
    composite_slices: int = DEFAULT_COMPOSITE_SLICES,
) -> dict[str, object] | None:
    if floors is None:
        floors = infer_floors(
            load_connectivity_viewpoints(
                connectivity_dir / ("%s_connectivity.json" % str(scan_id))
            )
        )
    metadata_render_mode = TEXTURE_RENDER_MODES[render_mode]
    floor_specs = _topdown_texture_floor_specs(
        floors=floors,
        project_root=project_root,
        scan_id=scan_id,
        render_mode=metadata_render_mode,
        output_size=output_size,
        cut_z_offset=cut_z_offset,
        composite_max_z_offset=composite_max_z_offset,
        composite_slices=composite_slices,
    )
    for spec in floor_specs:
        if not _cached_texture_is_current(
            png_path=spec["png_path"],
            metadata_path=spec["metadata_path"],
            cut_z=spec["cut_z"],
            output_size=output_size,
            cut_z_offset=cut_z_offset,
            render_mode=metadata_render_mode,
            composite_max_z_offset=composite_max_z_offset,
            composite_max_z=spec["composite_max_z"],
            composite_slices=composite_slices,
            floor_index=spec["floor_index"],
            floor_reference_z=spec["reference_z"],
            floor_lower_z=spec["lower_z"],
            floor_upper_z=spec["upper_z"],
        ):
            return None
        spec["metadata"] = json.loads(spec["metadata_path"].read_text(encoding="utf-8"))
    return _topdown_texture_payload_from_specs(project_root=project_root, floor_specs=floor_specs)


def missing_topdown_texture_payload(*, scan_id: str) -> dict[str, object]:
    command = "python generate_house_texture.py %s" % str(scan_id)
    return {
        "scan_id": str(scan_id),
        "message": "House texture not found. Run: %s" % command,
        "command": command,
    }


def _topdown_texture_floor_specs(
    *,
    floors: list[dict[str, object]],
    project_root: Path,
    scan_id: str,
    render_mode: str,
    output_size: int,
    cut_z_offset: float,
    composite_max_z_offset: float,
    composite_slices: int,
) -> list[dict[str, object]]:
    reference_zs = [float(floor["reference_z"]) for floor in floors]
    floor_specs = []
    for floor in floors:
        floor_index = int(floor["floor_index"])
        reference_z = float(floor["reference_z"])
        lower_z, upper_z = _floor_z_bounds(
            floor_index=floor_index,
            reference_zs=reference_zs,
        )
        cut_z = reference_z + float(cut_z_offset)
        composite_max_z = min(
            reference_z + float(composite_max_z_offset),
            upper_z,
        )
        png_path, metadata_path = _topdown_texture_cache_paths(
            project_root=project_root,
            scan_id=scan_id,
            render_mode=render_mode,
            output_size=output_size,
            cut_z_offset=cut_z_offset,
            composite_max_z_offset=composite_max_z_offset,
            composite_slices=composite_slices,
            floor_index=floor_index,
            floor_reference_z=reference_z,
            floor_lower_z=lower_z,
            floor_upper_z=upper_z,
        )
        floor_specs.append(
            {
                "floor": floor,
                "floor_index": floor_index,
                "reference_z": reference_z,
                "lower_z": lower_z,
                "upper_z": upper_z,
                "cut_z": cut_z,
                "composite_max_z": composite_max_z,
                "png_path": png_path,
                "metadata_path": metadata_path,
            }
        )
    return floor_specs


def _topdown_texture_payload_from_specs(
    *,
    project_root: Path,
    floor_specs: list[dict[str, object]],
) -> dict[str, object]:
    rendered_floors = []
    for spec in floor_specs:
        metadata = spec["metadata"]
        png_path = spec["png_path"]
        floor = spec["floor"]
        asset_path = png_path.relative_to(project_root).as_posix()
        rendered_floors.append(
            {
                **floor,
                **metadata,
                "url": "/assets/%s" % quote(asset_path, safe="/"),
            }
        )
    first_floor = rendered_floors[0]
    return {
        "floors": rendered_floors,
        "url": first_floor["url"],
        "render_mode": first_floor["render_mode"],
        "cut_z": first_floor["cut_z"],
        "cut_z_offset": first_floor["cut_z_offset"],
        "composite_max_z": first_floor["composite_max_z"],
        "composite_max_z_offset": first_floor["composite_max_z_offset"],
        "composite_slices": first_floor["composite_slices"],
        "output_size": first_floor["output_size"],
        "min_x": first_floor["min_x"],
        "max_x": first_floor["max_x"],
        "min_y": first_floor["min_y"],
        "max_y": first_floor["max_y"],
        "width": first_floor["width"],
        "height": first_floor["height"],
    }


def _topdown_texture_cache_paths(
    *,
    project_root: Path,
    scan_id: str,
    render_mode: str,
    output_size: int,
    cut_z_offset: float,
    composite_max_z_offset: float,
    composite_slices: int,
    floor_index: int | None = None,
    floor_reference_z: float | None = None,
    floor_lower_z: float | None = None,
    floor_upper_z: float | None = None,
) -> tuple[Path, Path]:
    cache_key = _topdown_texture_cache_key(
        scan_id=scan_id,
        render_mode=render_mode,
        output_size=output_size,
        cut_z_offset=cut_z_offset,
        composite_max_z_offset=composite_max_z_offset,
        composite_slices=composite_slices,
        floor_index=floor_index,
        floor_reference_z=floor_reference_z,
        floor_lower_z=floor_lower_z,
        floor_upper_z=floor_upper_z,
    )
    cache_dir = project_root / TEXTURE_CACHE_DIR_NAME / str(scan_id)
    return (
        cache_dir / ("%s_topdown_texture.png" % cache_key),
        cache_dir / ("%s_topdown_texture.json" % cache_key),
    )


def _topdown_texture_cache_key(
    *,
    scan_id: str,
    render_mode: str,
    output_size: int,
    cut_z_offset: float,
    composite_max_z_offset: float,
    composite_slices: int,
    floor_index: int | None = None,
    floor_reference_z: float | None = None,
    floor_lower_z: float | None = None,
    floor_upper_z: float | None = None,
) -> str:
    parts = [
        str(scan_id),
        str(render_mode),
        "size%s" % int(output_size),
        "cut%s" % _cache_float_token(cut_z_offset),
        "comp%s" % _cache_float_token(composite_max_z_offset),
        "slices%s" % int(composite_slices),
    ]
    if floor_index is not None:
        parts.extend(
            [
                "floor%s" % int(floor_index),
                "ref%s" % _cache_float_token(float(floor_reference_z)),
                "lower%s" % _cache_float_token(float(floor_lower_z)),
                "upper%s" % _cache_float_token(float(floor_upper_z)),
            ]
        )
    raw_key = "_".join(parts)
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_key)


def _cache_float_token(value: float) -> str:
    return repr(float(value)).replace("-", "m").replace(".", "p")


def _load_texture_render_assets(
    *,
    mesh_zip_path: Path,
    output_size: int,
) -> TextureRenderAssets:
    with zipfile.ZipFile(mesh_zip_path) as archive:
        obj_name = _single_zip_member_with_suffix(archive, ".obj")
        obj_text = archive.read(obj_name).decode("utf-8")
        mesh, material_libraries = _parse_obj(obj_text)
        materials = _load_materials(archive, obj_name, material_libraries)
        textures = {
            material_name: np.asarray(
                Image.open(archive.open(texture_name)).convert("RGB"),
                dtype=np.uint8,
            )
            for material_name, texture_name in materials.items()
        }

    min_x, max_x, min_y, max_y = _mesh_xy_bounds(mesh.vertices)
    width, height = _output_dimensions(
        min_x=min_x,
        max_x=max_x,
        min_y=min_y,
        max_y=max_y,
        output_size=output_size,
    )
    return TextureRenderAssets(
        mesh=mesh,
        textures=textures,
        face_z_ranges=_face_z_ranges(mesh),
        face_batches=_build_texture_face_batches(mesh=mesh, textures=textures),
        min_x=min_x,
        max_x=max_x,
        min_y=min_y,
        max_y=max_y,
        width=width,
        height=height,
    )


def _render_topdown_texture(
    *,
    assets: TextureRenderAssets,
    png_path: Path,
    output_size: int,
    cut_z: float,
    cut_z_offset: float,
    render_mode: str,
    composite_max_z_offset: float,
    composite_max_z: float,
    composite_slices: int,
    floor_index: int,
    floor_reference_z: float,
    floor_lower_z: float,
    floor_upper_z: float,
    progress_callback: TextureProgressCallback | None = None,
) -> dict[str, object]:
    if render_mode == SINGLE_CUTAWAY_RENDER_MODE:
        image, _ = _render_topdown_slice(
            assets=assets,
            cut_z=cut_z,
            lower_z=floor_lower_z,
            progress_callback=progress_callback,
        )
    else:
        image = _render_multi_slice_composite(
            assets=assets,
            cut_z=cut_z,
            lower_z=floor_lower_z,
            composite_max_z=composite_max_z,
            composite_slices=composite_slices,
            progress_callback=progress_callback,
        )

    png_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, mode="RGB").save(png_path)
    if progress_callback is not None:
        progress_callback(0, None, "wrote %s" % png_path.name)
    return {
        "render_mode": render_mode,
        "floor_index": int(floor_index),
        "floor_reference_z": float(floor_reference_z),
        "floor_lower_z": float(floor_lower_z),
        "floor_upper_z": float(floor_upper_z),
        "cut_z": float(cut_z),
        "cut_z_offset": float(cut_z_offset),
        "composite_max_z": float(composite_max_z),
        "composite_max_z_offset": float(composite_max_z_offset),
        "composite_slices": int(composite_slices),
        "output_size": int(output_size),
        "min_x": float(assets.min_x),
        "max_x": float(assets.max_x),
        "min_y": float(assets.min_y),
        "max_y": float(assets.max_y),
        "width": int(assets.width),
        "height": int(assets.height),
    }


def _cached_texture_is_current(
    *,
    png_path: Path,
    metadata_path: Path,
    cut_z: float,
    output_size: int,
    cut_z_offset: float,
    render_mode: str,
    composite_max_z_offset: float,
    composite_max_z: float,
    composite_slices: int,
    floor_index: int | None = None,
    floor_reference_z: float | None = None,
    floor_lower_z: float | None = None,
    floor_upper_z: float | None = None,
) -> bool:
    if not png_path.exists() or not metadata_path.exists():
        return False
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return (
        metadata.get("render_mode") == render_mode
        and float(metadata.get("cut_z")) == float(cut_z)
        and metadata.get("output_size") == int(output_size)
        and metadata.get("cut_z_offset") == float(cut_z_offset)
        and metadata.get("composite_max_z_offset") == float(composite_max_z_offset)
        and metadata.get("composite_max_z") == float(composite_max_z)
        and metadata.get("composite_slices") == int(composite_slices)
        and (
            floor_index is None
            or (
                metadata.get("floor_index") == int(floor_index)
                and float(metadata.get("floor_reference_z")) == float(floor_reference_z)
                and float(metadata.get("floor_lower_z")) == float(floor_lower_z)
                and metadata.get("floor_upper_z") == float(floor_upper_z)
            )
        )
    )


def _render_topdown_slice(
    *,
    assets: TextureRenderAssets,
    cut_z: float,
    lower_z: float = -math.inf,
    progress_callback: TextureProgressCallback | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    image, depth = _blank_canvas(width=assets.width, height=assets.height)
    covered = np.zeros((assets.height, assets.width), dtype=np.bool_)
    for batch in assets.face_batches:
        _rasterize_texture_batch(
            batch.vertices,
            batch.texcoords,
            batch.z_min,
            batch.z_max,
            batch.texture,
            image,
            depth,
            covered,
            False,
            assets.min_x,
            assets.max_x,
            assets.min_y,
            assets.max_y,
            assets.width,
            assets.height,
            cut_z,
            lower_z,
        )
        if progress_callback is not None:
            progress_callback(1, None, "rendering cut %.3f" % float(cut_z))
    return image, depth


def _render_multi_slice_composite(
    *,
    assets: TextureRenderAssets,
    cut_z: float,
    lower_z: float,
    composite_max_z: float,
    composite_slices: int,
    progress_callback: TextureProgressCallback | None = None,
) -> np.ndarray:
    composite = np.full((assets.height, assets.width, 3), 255, dtype=np.uint8)
    composite_covered = np.zeros((assets.height, assets.width), dtype=bool)
    cut_values = np.linspace(float(cut_z), float(composite_max_z), int(composite_slices))

    for slice_index, slice_cut_z in enumerate(cut_values):
        slice_depth = np.full((assets.height, assets.width), -np.inf, dtype=np.float32)
        for batch in assets.face_batches:
            _rasterize_texture_batch(
                batch.vertices,
                batch.texcoords,
                batch.z_min,
                batch.z_max,
                batch.texture,
                composite,
                slice_depth,
                composite_covered,
                True,
                assets.min_x,
                assets.max_x,
                assets.min_y,
                assets.max_y,
                assets.width,
                assets.height,
                float(slice_cut_z),
                lower_z,
            )
            if progress_callback is not None:
                progress_callback(1, None, "rendering cut %.3f" % float(slice_cut_z))
        slice_covered = slice_depth > -np.inf
        composite_covered |= slice_covered

    return composite


def _interior_reference_z(*, connectivity_path: Path) -> float:
    connectivity = json.loads(connectivity_path.read_text(encoding="utf-8"))
    viewpoint_zs = [
        float(item["pose"][11])
        for item in connectivity
        if bool(item["included"])
    ]
    return max(viewpoint_zs)


def _floor_z_bounds(
    *,
    floor_index: int,
    reference_zs: list[float],
) -> tuple[float, float]:
    if floor_index == 0:
        lower_z = -math.inf
    else:
        lower_z = (reference_zs[floor_index - 1] + reference_zs[floor_index]) / 2.0
    if floor_index == len(reference_zs) - 1:
        upper_z = math.inf
    else:
        upper_z = (reference_zs[floor_index] + reference_zs[floor_index + 1]) / 2.0
    return lower_z, upper_z


def _single_zip_member_with_suffix(archive: zipfile.ZipFile, suffix: str) -> str:
    names = [
        name
        for name in archive.namelist()
        if not name.endswith("/") and name.lower().endswith(suffix)
    ]
    if len(names) != 1:
        raise ValueError(
            "Expected exactly one %s file in %s, found %d."
            % (suffix, archive.filename, len(names))
        )
    return names[0]


def _parse_obj(text: str) -> tuple[ObjMesh, list[str]]:
    vertices: list[tuple[float, float, float]] = []
    texcoords: list[tuple[float, float]] = []
    faces: list[tuple[tuple[int, int], tuple[int, int], tuple[int, int], str]] = []
    material_libraries: list[str] = []
    current_material = ""

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "mtllib":
            material_libraries.append(" ".join(parts[1:]))
        elif parts[0] == "usemtl":
            current_material = " ".join(parts[1:])
        elif parts[0] == "v":
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == "vt":
            texcoords.append((float(parts[1]), float(parts[2])))
        elif parts[0] == "f":
            refs = [_parse_face_ref(part, len(vertices), len(texcoords)) for part in parts[1:]]
            for index in range(1, len(refs) - 1):
                faces.append((refs[0], refs[index], refs[index + 1], current_material))

    return ObjMesh(vertices=vertices, texcoords=texcoords, faces=faces), material_libraries


def _parse_face_ref(
    token: str,
    vertex_count: int,
    texcoord_count: int,
) -> tuple[int, int]:
    values = token.split("/")
    vertex_index = _obj_index(values[0], vertex_count)
    texcoord_index = _obj_index(values[1], texcoord_count)
    return vertex_index, texcoord_index


def _obj_index(raw_index: str, count: int) -> int:
    index = int(raw_index)
    if index < 0:
        return count + index
    return index - 1


def _load_materials(
    archive: zipfile.ZipFile,
    obj_name: str,
    material_libraries: list[str],
) -> dict[str, str]:
    materials: dict[str, str] = {}
    obj_dir = posixpath.dirname(obj_name)
    if obj_dir == ".":
        obj_dir = ""
    for library_name in material_libraries:
        mtl_name = _resolve_zip_member(archive, _zip_join(obj_dir, library_name))
        current_material = ""
        for raw_line in archive.read(mtl_name).decode("utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if parts[0] == "newmtl":
                current_material = " ".join(parts[1:])
            elif parts[0] == "map_Kd":
                materials[current_material] = _resolve_zip_member(
                    archive,
                    _zip_join(obj_dir, _parse_texture_path(parts)),
                )
    return materials


def _parse_texture_path(parts: list[str]) -> str:
    option_arg_counts = {
        "-blendu": 1,
        "-blendv": 1,
        "-boost": 1,
        "-mm": 2,
        "-o": 3,
        "-s": 3,
        "-t": 3,
        "-texres": 1,
        "-clamp": 1,
        "-bm": 1,
        "-imfchan": 1,
        "-type": 1,
    }
    index = 1
    while index < len(parts):
        option = parts[index]
        if not option.startswith("-"):
            return " ".join(parts[index:])
        index += 1 + option_arg_counts[option]
    raise ValueError("map_Kd line does not contain a texture path.")


def _zip_join(base: str, relative: str) -> str:
    if not base:
        return relative.replace("\\", "/")
    return (base.rstrip("/") + "/" + relative).replace("\\", "/")


def _resolve_zip_member(archive: zipfile.ZipFile, requested_name: str) -> str:
    requested_name = requested_name.replace("\\", "/")
    names = archive.namelist()
    if requested_name in names:
        return requested_name

    normalized_requested_name = _normalize_zip_path(requested_name)
    matches = [
        name
        for name in names
        if _normalize_zip_path(name) == normalized_requested_name
    ]
    if len(matches) != 1:
        raise KeyError(
            "Expected exactly one archive member matching %r in %s, found %d."
            % (requested_name, archive.filename, len(matches))
        )
    return matches[0]


def _normalize_zip_path(path: str) -> str:
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    return "/".join(parts)


def _mesh_xy_bounds(
    vertices: list[tuple[float, float, float]],
) -> tuple[float, float, float, float]:
    xs = [vertex[0] for vertex in vertices]
    ys = [vertex[1] for vertex in vertices]
    return min(xs), max(xs), min(ys), max(ys)


def _face_z_ranges(mesh: ObjMesh) -> list[tuple[float, float]]:
    ranges = []
    for face in mesh.faces:
        zs = [mesh.vertices[ref[0]][2] for ref in face[:3]]
        ranges.append((min(zs), max(zs)))
    return ranges


def _build_texture_face_batches(
    *,
    mesh: ObjMesh,
    textures: dict[str, np.ndarray],
) -> list[TextureFaceBatch]:
    batches: list[TextureFaceBatch] = []
    current_material: str | None = None
    batch_vertices: list[list[tuple[float, float, float]]] = []
    batch_texcoords: list[list[tuple[float, float]]] = []

    def flush_batch() -> None:
        nonlocal batch_vertices, batch_texcoords
        if current_material is None:
            return
        vertices = np.asarray(batch_vertices, dtype=np.float32)
        texcoords = np.asarray(batch_texcoords, dtype=np.float32)
        z_values = vertices[:, :, 2]
        batches.append(
            TextureFaceBatch(
                material=current_material,
                texture=np.ascontiguousarray(textures[current_material]),
                vertices=np.ascontiguousarray(vertices),
                texcoords=np.ascontiguousarray(texcoords),
                z_min=np.ascontiguousarray(np.min(z_values, axis=1).astype(np.float32)),
                z_max=np.ascontiguousarray(np.max(z_values, axis=1).astype(np.float32)),
            )
        )
        batch_vertices = []
        batch_texcoords = []

    for face in mesh.faces:
        material = face[3]
        if current_material is not None and material != current_material:
            flush_batch()
        current_material = material
        batch_vertices.append([mesh.vertices[ref[0]] for ref in face[:3]])
        batch_texcoords.append([mesh.texcoords[ref[1]] for ref in face[:3]])
    flush_batch()
    return batches


def _z_ranges_intersect(
    face_z_range: tuple[float, float],
    lower_z: float,
    cut_z: float,
) -> bool:
    face_min_z, face_max_z = face_z_range
    return face_max_z >= lower_z and face_min_z <= cut_z


def _output_dimensions(
    *,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    output_size: int,
) -> tuple[int, int]:
    world_width = max_x - min_x
    world_height = max_y - min_y
    scale = float(output_size) / max(world_width, world_height)
    return (
        max(1, int(math.ceil(world_width * scale))),
        max(1, int(math.ceil(world_height * scale))),
    )


def _blank_canvas(*, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.full((height, width, 3), 255, dtype=np.uint8),
        np.full((height, width), -np.inf, dtype=np.float32),
    )


@nb.njit(cache=True)
def _rasterize_texture_batch(
    vertices: np.ndarray,
    texcoords: np.ndarray,
    z_min: np.ndarray,
    z_max: np.ndarray,
    texture: np.ndarray,
    image: np.ndarray,
    depth: np.ndarray,
    covered: np.ndarray,
    only_uncovered: bool,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    width: int,
    height: int,
    cut_z: float,
    lower_z: float,
) -> None:
    for face_index in range(vertices.shape[0]):
        if z_max[face_index] < lower_z or z_min[face_index] > cut_z:
            continue
        if z_min[face_index] >= lower_z and z_max[face_index] <= cut_z:
            _rasterize_triangle_numba(
                vertices[face_index],
                texcoords[face_index],
                0,
                1,
                2,
                texture,
                image,
                depth,
                covered,
                only_uncovered,
                min_x,
                max_x,
                min_y,
                max_y,
                width,
                height,
            )
            continue

        polygon_vertices = np.empty((8, 3), dtype=np.float32)
        polygon_texcoords = np.empty((8, 2), dtype=np.float32)
        tmp_vertices = np.empty((8, 3), dtype=np.float32)
        tmp_texcoords = np.empty((8, 2), dtype=np.float32)
        clipped_vertices = np.empty((8, 3), dtype=np.float32)
        clipped_texcoords = np.empty((8, 2), dtype=np.float32)
        for vertex_index in range(3):
            for axis in range(3):
                polygon_vertices[vertex_index, axis] = vertices[face_index, vertex_index, axis]
            for axis in range(2):
                polygon_texcoords[vertex_index, axis] = texcoords[face_index, vertex_index, axis]

        upper_count = _clip_polygon_by_z_numba(
            polygon_vertices,
            polygon_texcoords,
            3,
            tmp_vertices,
            tmp_texcoords,
            cut_z,
            True,
        )
        if upper_count < 3:
            continue
        clipped_count = _clip_polygon_by_z_numba(
            tmp_vertices,
            tmp_texcoords,
            upper_count,
            clipped_vertices,
            clipped_texcoords,
            lower_z,
            False,
        )
        if clipped_count < 3:
            continue
        for polygon_index in range(1, clipped_count - 1):
            _rasterize_triangle_numba(
                clipped_vertices,
                clipped_texcoords,
                0,
                polygon_index,
                polygon_index + 1,
                texture,
                image,
                depth,
                covered,
                only_uncovered,
                min_x,
                max_x,
                min_y,
                max_y,
                width,
                height,
            )


@nb.njit(cache=True)
def _clip_polygon_by_z_numba(
    input_vertices: np.ndarray,
    input_texcoords: np.ndarray,
    count: int,
    output_vertices: np.ndarray,
    output_texcoords: np.ndarray,
    z_value: float,
    keep_below: bool,
) -> int:
    output_count = 0
    for index in range(count):
        previous_index = count - 1 if index == 0 else index - 1
        previous_z = input_vertices[previous_index, 2]
        current_z = input_vertices[index, 2]
        previous_inside = _z_inside_numba(previous_z, z_value, keep_below)
        current_inside = _z_inside_numba(current_z, z_value, keep_below)

        if current_inside:
            if not previous_inside:
                _write_z_intersection_numba(
                    input_vertices,
                    input_texcoords,
                    previous_index,
                    index,
                    z_value,
                    output_vertices,
                    output_texcoords,
                    output_count,
                )
                output_count += 1
            for axis in range(3):
                output_vertices[output_count, axis] = input_vertices[index, axis]
            for axis in range(2):
                output_texcoords[output_count, axis] = input_texcoords[index, axis]
            output_count += 1
        elif previous_inside:
            _write_z_intersection_numba(
                input_vertices,
                input_texcoords,
                previous_index,
                index,
                z_value,
                output_vertices,
                output_texcoords,
                output_count,
            )
            output_count += 1
    return output_count


@nb.njit(cache=True)
def _z_inside_numba(z: float, z_value: float, keep_below: bool) -> bool:
    if keep_below:
        return z <= z_value
    return z >= z_value


@nb.njit(cache=True)
def _write_z_intersection_numba(
    input_vertices: np.ndarray,
    input_texcoords: np.ndarray,
    start_index: int,
    end_index: int,
    cut_z: float,
    output_vertices: np.ndarray,
    output_texcoords: np.ndarray,
    output_index: int,
) -> None:
    denominator = input_vertices[end_index, 2] - input_vertices[start_index, 2]
    t = (cut_z - input_vertices[start_index, 2]) / denominator
    for axis in range(3):
        output_vertices[output_index, axis] = input_vertices[start_index, axis] + t * (
            input_vertices[end_index, axis] - input_vertices[start_index, axis]
        )
    for axis in range(2):
        output_texcoords[output_index, axis] = input_texcoords[start_index, axis] + t * (
            input_texcoords[end_index, axis] - input_texcoords[start_index, axis]
        )


@nb.njit(cache=True)
def _rasterize_triangle_numba(
    vertices: np.ndarray,
    texcoords: np.ndarray,
    vertex_index_0: int,
    vertex_index_1: int,
    vertex_index_2: int,
    texture: np.ndarray,
    image: np.ndarray,
    depth: np.ndarray,
    covered: np.ndarray,
    only_uncovered: bool,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    width: int,
    height: int,
) -> None:
    p0x = (vertices[vertex_index_0, 0] - min_x) / (max_x - min_x) * (width - 1)
    p0y = (max_y - vertices[vertex_index_0, 1]) / (max_y - min_y) * (height - 1)
    p1x = (vertices[vertex_index_1, 0] - min_x) / (max_x - min_x) * (width - 1)
    p1y = (max_y - vertices[vertex_index_1, 1]) / (max_y - min_y) * (height - 1)
    p2x = (vertices[vertex_index_2, 0] - min_x) / (max_x - min_x) * (width - 1)
    p2y = (max_y - vertices[vertex_index_2, 1]) / (max_y - min_y) * (height - 1)
    denominator = (p1y - p2y) * (p0x - p2x) + (p2x - p1x) * (p0y - p2y)
    if denominator == 0.0:
        return

    min_px = max(0, int(math.floor(min(p0x, p1x, p2x))))
    max_px = min(width - 1, int(math.ceil(max(p0x, p1x, p2x))))
    min_py = max(0, int(math.floor(min(p0y, p1y, p2y))))
    max_py = min(height - 1, int(math.ceil(max(p0y, p1y, p2y))))
    if min_px > max_px or min_py > max_py:
        return

    texture_height = texture.shape[0]
    texture_width = texture.shape[1]
    for py in range(min_py, max_py + 1):
        for px in range(min_px, max_px + 1):
            if only_uncovered and covered[py, px]:
                continue
            w0 = ((p1y - p2y) * (px - p2x) + (p2x - p1x) * (py - p2y)) / denominator
            w1 = ((p2y - p0y) * (px - p2x) + (p0x - p2x) * (py - p2y)) / denominator
            w2 = 1.0 - w0 - w1
            if w0 < 0.0 or w1 < 0.0 or w2 < 0.0:
                continue
            z = (
                w0 * vertices[vertex_index_0, 2]
                + w1 * vertices[vertex_index_1, 2]
                + w2 * vertices[vertex_index_2, 2]
            )
            if z < depth[py, px]:
                continue
            u = (
                w0 * texcoords[vertex_index_0, 0]
                + w1 * texcoords[vertex_index_1, 0]
                + w2 * texcoords[vertex_index_2, 0]
            )
            v = (
                w0 * texcoords[vertex_index_0, 1]
                + w1 * texcoords[vertex_index_1, 1]
                + w2 * texcoords[vertex_index_2, 1]
            )
            texture_x = int(np.rint(u * (texture_width - 1)))
            texture_y = int(np.rint((1.0 - v) * (texture_height - 1)))
            if texture_x < 0:
                texture_x = 0
            elif texture_x >= texture_width:
                texture_x = texture_width - 1
            if texture_y < 0:
                texture_y = 0
            elif texture_y >= texture_height:
                texture_y = texture_height - 1
            image[py, px, 0] = texture[texture_y, texture_x, 0]
            image[py, px, 1] = texture[texture_y, texture_x, 1]
            image[py, px, 2] = texture[texture_y, texture_x, 2]
            depth[py, px] = z


def _clip_triangle_at_z(
    *,
    vertices: np.ndarray,
    texcoords: np.ndarray,
    cut_z: float,
) -> list[tuple[np.ndarray, np.ndarray]]:
    return _clip_triangle_to_z_range(
        vertices=vertices,
        texcoords=texcoords,
        lower_z=-math.inf,
        cut_z=cut_z,
    )


def _clip_triangle_to_z_range(
    *,
    vertices: np.ndarray,
    texcoords: np.ndarray,
    lower_z: float,
    cut_z: float,
) -> list[tuple[np.ndarray, np.ndarray]]:
    upper_vertices, upper_texcoords = _clip_polygon_by_z(
        vertices=vertices,
        texcoords=texcoords,
        z_value=cut_z,
        keep_below=True,
    )
    if len(upper_vertices) < 3:
        return []
    clipped_vertices, clipped_texcoords = _clip_polygon_by_z(
        vertices=upper_vertices,
        texcoords=upper_texcoords,
        z_value=lower_z,
        keep_below=False,
    )
    if len(clipped_vertices) < 3:
        return []

    triangles = []
    for index in range(1, len(clipped_vertices) - 1):
        triangles.append(
            (
                np.array(
                    [
                        clipped_vertices[0],
                        clipped_vertices[index],
                        clipped_vertices[index + 1],
                    ],
                    dtype=np.float32,
                ),
                np.array(
                    [
                        clipped_texcoords[0],
                        clipped_texcoords[index],
                        clipped_texcoords[index + 1],
                    ],
                    dtype=np.float32,
                ),
            )
        )
    return triangles


def _clip_polygon_by_z(
    *,
    vertices: np.ndarray,
    texcoords: np.ndarray,
    z_value: float,
    keep_below: bool,
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    clipped_vertices: list[np.ndarray] = []
    clipped_texcoords: list[np.ndarray] = []
    count = len(vertices)
    for index in range(count):
        previous_index = (index - 1) % count
        previous_vertex = vertices[previous_index]
        current_vertex = vertices[index]
        previous_texcoord = texcoords[previous_index]
        current_texcoord = texcoords[index]
        previous_inside = _z_inside(float(previous_vertex[2]), z_value, keep_below)
        current_inside = _z_inside(float(current_vertex[2]), z_value, keep_below)

        if current_inside:
            if not previous_inside:
                vertex, texcoord = _intersect_z_plane(
                    start_vertex=previous_vertex,
                    end_vertex=current_vertex,
                    start_texcoord=previous_texcoord,
                    end_texcoord=current_texcoord,
                    cut_z=z_value,
                )
                clipped_vertices.append(vertex)
                clipped_texcoords.append(texcoord)
            clipped_vertices.append(current_vertex)
            clipped_texcoords.append(current_texcoord)
        elif previous_inside:
            vertex, texcoord = _intersect_z_plane(
                start_vertex=previous_vertex,
                end_vertex=current_vertex,
                start_texcoord=previous_texcoord,
                end_texcoord=current_texcoord,
                cut_z=z_value,
            )
            clipped_vertices.append(vertex)
            clipped_texcoords.append(texcoord)

    return clipped_vertices, clipped_texcoords


def _z_inside(z: float, z_value: float, keep_below: bool) -> bool:
    if keep_below:
        return z <= z_value
    return z >= z_value


def _intersect_z_plane(
    *,
    start_vertex: np.ndarray,
    end_vertex: np.ndarray,
    start_texcoord: np.ndarray,
    end_texcoord: np.ndarray,
    cut_z: float,
) -> tuple[np.ndarray, np.ndarray]:
    t = (float(cut_z) - float(start_vertex[2])) / (
        float(end_vertex[2]) - float(start_vertex[2])
    )
    return (
        start_vertex + t * (end_vertex - start_vertex),
        start_texcoord + t * (end_texcoord - start_texcoord),
    )


