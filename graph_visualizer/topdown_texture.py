from __future__ import annotations

import json
import math
import os
import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import numpy as np
from PIL import Image


SINGLE_CUTAWAY_RENDER_MODE = "single_cutaway_v1"
MULTI_SLICE_RENDER_MODE = "multi_slice_hole_fill_v1"
TEXTURE_RENDER_MODES = {
    "single_cutaway": SINGLE_CUTAWAY_RENDER_MODE,
    "multi_slice_composite": MULTI_SLICE_RENDER_MODE,
}
DEFAULT_CUT_Z_OFFSET_METERS = 0.15
DEFAULT_COMPOSITE_MAX_Z_OFFSET_METERS = 1.6
DEFAULT_COMPOSITE_SLICES = 5
TEXTURE_CACHE_DIR_NAME = "topdown_texture_cache"


@dataclass(frozen=True)
class ObjMesh:
    vertices: list[tuple[float, float, float]]
    texcoords: list[tuple[float, float]]
    faces: list[tuple[tuple[int, int], tuple[int, int], tuple[int, int], str]]


def generate_cached_topdown_texture(
    *,
    scan_id: str,
    project_root: Path,
    instance_name: str,
    connectivity_dir: Path,
    output_size: int = 1800,
    cut_z_offset: float = DEFAULT_CUT_Z_OFFSET_METERS,
    render_mode: str = "multi_slice_composite",
    composite_max_z_offset: float = DEFAULT_COMPOSITE_MAX_Z_OFFSET_METERS,
    composite_slices: int = DEFAULT_COMPOSITE_SLICES,
) -> dict[str, object]:
    matterport_data_dir = Path(os.environ["MATTERPORT_DATA_DIR"])
    mesh_zip_path = (
        matterport_data_dir
        / "v1"
        / "scans"
        / str(scan_id)
        / "matterport_mesh.zip"
    )
    viewpoint_z = _interior_reference_z(
        connectivity_path=connectivity_dir / ("%s_connectivity.json" % str(scan_id))
    )
    cut_z = viewpoint_z + float(cut_z_offset)
    composite_max_z = viewpoint_z + float(composite_max_z_offset)
    metadata_render_mode = TEXTURE_RENDER_MODES[render_mode]
    png_path, metadata_path = _topdown_texture_cache_paths(
        project_root=project_root,
        scan_id=scan_id,
        render_mode=metadata_render_mode,
        output_size=output_size,
        cut_z_offset=cut_z_offset,
        composite_max_z_offset=composite_max_z_offset,
        composite_slices=composite_slices,
    )

    if _cached_texture_is_current(
        png_path=png_path,
        metadata_path=metadata_path,
        cut_z=cut_z,
        output_size=output_size,
        cut_z_offset=cut_z_offset,
        render_mode=metadata_render_mode,
        composite_max_z_offset=composite_max_z_offset,
        composite_max_z=composite_max_z,
        composite_slices=composite_slices,
    ):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        metadata = _render_topdown_texture(
            mesh_zip_path=mesh_zip_path,
            png_path=png_path,
            output_size=output_size,
            cut_z=cut_z,
            cut_z_offset=cut_z_offset,
            render_mode=metadata_render_mode,
            composite_max_z_offset=composite_max_z_offset,
            composite_max_z=composite_max_z,
            composite_slices=composite_slices,
        )
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    asset_path = png_path.relative_to(project_root).as_posix()
    return {
        **metadata,
        "url": "/assets/%s" % quote(asset_path, safe="/"),
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
) -> tuple[Path, Path]:
    cache_key = _topdown_texture_cache_key(
        scan_id=scan_id,
        render_mode=render_mode,
        output_size=output_size,
        cut_z_offset=cut_z_offset,
        composite_max_z_offset=composite_max_z_offset,
        composite_slices=composite_slices,
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
) -> str:
    raw_key = "_".join(
        [
            str(scan_id),
            str(render_mode),
            "size%s" % int(output_size),
            "cut%s" % _cache_float_token(cut_z_offset),
            "comp%s" % _cache_float_token(composite_max_z_offset),
            "slices%s" % int(composite_slices),
        ]
    )
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_key)


def _cache_float_token(value: float) -> str:
    return repr(float(value)).replace("-", "m").replace(".", "p")


def _render_topdown_texture(
    *,
    mesh_zip_path: Path,
    png_path: Path,
    output_size: int,
    cut_z: float,
    cut_z_offset: float,
    render_mode: str,
    composite_max_z_offset: float,
    composite_max_z: float,
    composite_slices: int,
) -> dict[str, object]:
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
    if render_mode == SINGLE_CUTAWAY_RENDER_MODE:
        image, _ = _render_topdown_slice(
            mesh=mesh,
            textures=textures,
            min_x=min_x,
            max_x=max_x,
            min_y=min_y,
            max_y=max_y,
            width=width,
            height=height,
            cut_z=cut_z,
        )
    else:
        image = _render_multi_slice_composite(
            mesh=mesh,
            textures=textures,
            min_x=min_x,
            max_x=max_x,
            min_y=min_y,
            max_y=max_y,
            width=width,
            height=height,
            cut_z=cut_z,
            composite_max_z=composite_max_z,
            composite_slices=composite_slices,
        )

    png_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, mode="RGB").save(png_path)
    return {
        "render_mode": render_mode,
        "cut_z": float(cut_z),
        "cut_z_offset": float(cut_z_offset),
        "composite_max_z": float(composite_max_z),
        "composite_max_z_offset": float(composite_max_z_offset),
        "composite_slices": int(composite_slices),
        "output_size": int(output_size),
        "min_x": float(min_x),
        "max_x": float(max_x),
        "min_y": float(min_y),
        "max_y": float(max_y),
        "width": int(width),
        "height": int(height),
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
    )


def _render_topdown_slice(
    *,
    mesh: ObjMesh,
    textures: dict[str, np.ndarray],
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    width: int,
    height: int,
    cut_z: float,
) -> tuple[np.ndarray, np.ndarray]:
    image, depth = _blank_canvas(width=width, height=height)
    for face in mesh.faces:
        _rasterize_textured_triangle(
            image=image,
            depth=depth,
            mesh=mesh,
            face=face,
            textures=textures,
            min_x=min_x,
            max_x=max_x,
            min_y=min_y,
            max_y=max_y,
            width=width,
            height=height,
            cut_z=cut_z,
        )
    return image, depth


def _render_multi_slice_composite(
    *,
    mesh: ObjMesh,
    textures: dict[str, np.ndarray],
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    width: int,
    height: int,
    cut_z: float,
    composite_max_z: float,
    composite_slices: int,
) -> np.ndarray:
    composite = np.full((height, width, 3), 255, dtype=np.uint8)
    composite_covered = np.zeros((height, width), dtype=bool)
    cut_values = np.linspace(float(cut_z), float(composite_max_z), int(composite_slices))

    for slice_index, slice_cut_z in enumerate(cut_values):
        slice_image, slice_depth = _render_topdown_slice(
            mesh=mesh,
            textures=textures,
            min_x=min_x,
            max_x=max_x,
            min_y=min_y,
            max_y=max_y,
            width=width,
            height=height,
            cut_z=float(slice_cut_z),
        )
        slice_covered = slice_depth > -np.inf
        newly_covered = slice_covered & ~composite_covered
        composite[newly_covered] = slice_image[newly_covered]
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


def _rasterize_textured_triangle(
    *,
    image: np.ndarray,
    depth: np.ndarray,
    mesh: ObjMesh,
    face: tuple[tuple[int, int], tuple[int, int], tuple[int, int], str],
    textures: dict[str, np.ndarray],
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    width: int,
    height: int,
    cut_z: float,
) -> None:
    refs = face[:3]
    material = face[3]
    texture = textures[material]
    vertex_indices = [ref[0] for ref in refs]
    texcoord_indices = [ref[1] for ref in refs]
    vertices = np.array([mesh.vertices[index] for index in vertex_indices], dtype=np.float32)
    texcoords = np.array([mesh.texcoords[index] for index in texcoord_indices], dtype=np.float32)
    for clipped_vertices, clipped_texcoords in _clip_triangle_at_z(
        vertices=vertices,
        texcoords=texcoords,
        cut_z=cut_z,
    ):
        _rasterize_clipped_textured_triangle(
            image=image,
            depth=depth,
            vertices=clipped_vertices,
            texcoords=clipped_texcoords,
            texture=texture,
            min_x=min_x,
            max_x=max_x,
            min_y=min_y,
            max_y=max_y,
            width=width,
            height=height,
        )


def _clip_triangle_at_z(
    *,
    vertices: np.ndarray,
    texcoords: np.ndarray,
    cut_z: float,
) -> list[tuple[np.ndarray, np.ndarray]]:
    clipped_vertices: list[np.ndarray] = []
    clipped_texcoords: list[np.ndarray] = []
    for index in range(3):
        previous_index = (index - 1) % 3
        previous_vertex = vertices[previous_index]
        current_vertex = vertices[index]
        previous_texcoord = texcoords[previous_index]
        current_texcoord = texcoords[index]
        previous_inside = float(previous_vertex[2]) <= float(cut_z)
        current_inside = float(current_vertex[2]) <= float(cut_z)

        if current_inside:
            if not previous_inside:
                vertex, texcoord = _intersect_z_plane(
                    start_vertex=previous_vertex,
                    end_vertex=current_vertex,
                    start_texcoord=previous_texcoord,
                    end_texcoord=current_texcoord,
                    cut_z=cut_z,
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
                cut_z=cut_z,
            )
            clipped_vertices.append(vertex)
            clipped_texcoords.append(texcoord)

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


def _rasterize_clipped_textured_triangle(
    *,
    image: np.ndarray,
    depth: np.ndarray,
    vertices: np.ndarray,
    texcoords: np.ndarray,
    texture: np.ndarray,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    width: int,
    height: int,
) -> None:
    points = np.array(
        [
            [
                (vertex[0] - min_x) / (max_x - min_x) * (width - 1),
                (max_y - vertex[1]) / (max_y - min_y) * (height - 1),
            ]
            for vertex in vertices
        ],
        dtype=np.float32,
    )
    denominator = (
        (points[1, 1] - points[2, 1]) * (points[0, 0] - points[2, 0])
        + (points[2, 0] - points[1, 0]) * (points[0, 1] - points[2, 1])
    )
    if denominator == 0:
        return

    min_px = max(0, int(math.floor(float(np.min(points[:, 0])))))
    max_px = min(width - 1, int(math.ceil(float(np.max(points[:, 0])))))
    min_py = max(0, int(math.floor(float(np.min(points[:, 1])))))
    max_py = min(height - 1, int(math.ceil(float(np.max(points[:, 1])))))
    if min_px > max_px or min_py > max_py:
        return

    grid_y, grid_x = np.mgrid[min_py : max_py + 1, min_px : max_px + 1]
    px = grid_x.astype(np.float32)
    py = grid_y.astype(np.float32)
    w0 = (
        (points[1, 1] - points[2, 1]) * (px - points[2, 0])
        + (points[2, 0] - points[1, 0]) * (py - points[2, 1])
    ) / denominator
    w1 = (
        (points[2, 1] - points[0, 1]) * (px - points[2, 0])
        + (points[0, 0] - points[2, 0]) * (py - points[2, 1])
    ) / denominator
    w2 = 1.0 - w0 - w1
    inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
    z = w0 * vertices[0, 2] + w1 * vertices[1, 2] + w2 * vertices[2, 2]
    depth_window = depth[min_py : max_py + 1, min_px : max_px + 1]
    visible = inside & (z >= depth_window)
    if not np.any(visible):
        return

    u = w0 * texcoords[0, 0] + w1 * texcoords[1, 0] + w2 * texcoords[2, 0]
    v = w0 * texcoords[0, 1] + w1 * texcoords[1, 1] + w2 * texcoords[2, 1]
    texture_height, texture_width = texture.shape[:2]
    texture_x = np.clip(np.rint(u * (texture_width - 1)), 0, texture_width - 1).astype(np.int32)
    texture_y = np.clip(np.rint((1.0 - v) * (texture_height - 1)), 0, texture_height - 1).astype(np.int32)
    image_window = image[min_py : max_py + 1, min_px : max_px + 1]
    image_window[visible] = texture[texture_y[visible], texture_x[visible]]
    depth_window[visible] = z[visible]
