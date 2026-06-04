from __future__ import annotations

import json
import time
import zipfile

import numpy as np
import pytest
from PIL import Image

from graph_visualizer.topdown_texture import (
    ObjMesh,
    TEXTURE_RENDER_MODES,
    TextureRenderAssets,
    _build_texture_face_batches,
    _clip_triangle_at_z,
    _face_z_ranges,
    _render_topdown_slice,
    _topdown_texture_cache_paths,
    generate_cached_topdown_texture,
    load_cached_topdown_texture,
)


def _write_connectivity(tmp_path, scan_id, viewpoint_z=0.65):
    connectivity_dir = tmp_path / "connectivity"
    connectivity_dir.mkdir()
    (connectivity_dir / ("%s_connectivity.json" % scan_id)).write_text(
        json.dumps(
            [
                {
                    "image_id": "vp0",
                    "included": True,
                    "pose": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, viewpoint_z],
                }
            ]
        ),
        encoding="utf-8",
    )
    return connectivity_dir


def _cache_png_path(
    project_root,
    scan_id,
    *,
    output_size=1080,
    cut_z_offset=0.1,
    render_mode="multi_slice_composite",
    composite_max_z_offset=1.6,
    composite_slices=5,
):
    png_path, _ = _topdown_texture_cache_paths(
        project_root=project_root,
        scan_id=scan_id,
        render_mode=TEXTURE_RENDER_MODES[render_mode],
        output_size=output_size,
        cut_z_offset=cut_z_offset,
        composite_max_z_offset=composite_max_z_offset,
        composite_slices=composite_slices,
    )
    return png_path


def _asset_url(project_root, path):
    return "/assets/%s" % path.relative_to(project_root).as_posix()


def _metadata_png_path(project_root, metadata):
    return project_root / str(metadata["url"]).removeprefix("/assets/")


def test_generate_cached_topdown_texture_from_obj_mtl_zip(tmp_path, monkeypatch):
    scan_id = "scan"
    mesh_dir = tmp_path / "data" / "v1" / "scans" / scan_id
    mesh_dir.mkdir(parents=True)
    texture = Image.fromarray(
        np.array(
            [
                [[255, 0, 0], [0, 255, 0]],
                [[0, 0, 255], [255, 255, 0]],
            ],
            dtype=np.uint8,
        ),
        mode="RGB",
    )
    texture_path = tmp_path / "texture.png"
    texture.save(texture_path)
    obj_text = "\n".join(
        [
            "mtllib mesh.mtl",
            "v 0 0 0",
            "v 1 0 0",
            "v 1 1 0",
            "v 0 1 0",
            "vt 0 0",
            "vt 1 0",
            "vt 1 1",
            "vt 0 1",
            "usemtl material0",
            "f 1/1 2/2 3/3",
            "f 1/1 3/3 4/4",
        ]
    )
    with zipfile.ZipFile(mesh_dir / "matterport_mesh.zip", "w") as archive:
        archive.writestr("scan//matterport_mesh/mesh/mesh.obj", obj_text)
        archive.writestr(
            "scan//matterport_mesh/mesh/mesh.mtl",
            "newmtl material0\nmap_Kd texture.png\n",
        )
        archive.write(texture_path, "scan//matterport_mesh/mesh/texture.png")
    monkeypatch.setenv("MATTERPORT_DATA_DIR", str(tmp_path / "data"))
    connectivity_dir = _write_connectivity(tmp_path, scan_id)

    metadata = generate_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        instance_name="case",
        connectivity_dir=connectivity_dir,
        output_size=8,
    )

    cache_png_path = _metadata_png_path(tmp_path, metadata)
    assert metadata["url"] == _asset_url(tmp_path, cache_png_path)
    assert metadata["floors"][0]["floor_index"] == 0
    assert metadata["floors"][0]["floor_upper_z"] == float("inf")
    assert metadata["floors"][0]["node_ids"] == [0]
    assert metadata["render_mode"] == "multi_slice_hole_fill_v1"
    assert metadata["cut_z"] == 0.75
    assert metadata["cut_z_offset"] == 0.1
    assert metadata["composite_max_z"] == 2.25
    assert metadata["composite_max_z_offset"] == 1.6
    assert metadata["composite_slices"] == 5
    assert metadata["output_size"] == 8
    assert metadata["min_x"] == 0.0
    assert metadata["max_x"] == 1.0
    assert metadata["min_y"] == 0.0
    assert metadata["max_y"] == 1.0
    assert metadata["width"] == 8
    assert metadata["height"] == 8
    image = np.asarray(Image.open(cache_png_path))
    assert np.any(image != 255)

    reused_metadata = generate_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        instance_name="case-reuse",
        connectivity_dir=connectivity_dir,
        output_size=8,
    )

    assert reused_metadata["url"] == metadata["url"]
    assert not (
        tmp_path / "mllm_debug_outputs" / "case" / "scan_topdown_texture.png"
    ).exists()
    assert not (
        tmp_path / "mllm_debug_outputs" / "case-reuse" / "scan_topdown_texture.png"
    ).exists()

    custom_metadata = generate_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        instance_name="case-custom",
        connectivity_dir=connectivity_dir,
        output_size=10,
        cut_z_offset=0.5,
        render_mode="single_cutaway",
    )

    assert custom_metadata["render_mode"] == "single_cutaway_v1"
    assert custom_metadata["cut_z"] == 1.15
    assert custom_metadata["cut_z_offset"] == 0.5
    assert custom_metadata["output_size"] == 10
    assert custom_metadata["width"] == 10
    assert custom_metadata["height"] == 10


def test_load_cached_topdown_texture_reads_cache_without_mesh(tmp_path, monkeypatch):
    scan_id = "scan"
    mesh_dir = tmp_path / "data" / "v1" / "scans" / scan_id
    mesh_dir.mkdir(parents=True)
    texture = Image.fromarray(np.array([[[255, 0, 0]]], dtype=np.uint8), mode="RGB")
    texture_path = tmp_path / "texture.png"
    texture.save(texture_path)
    obj_text = "\n".join(
        [
            "mtllib mesh.mtl",
            "v 0 0 0",
            "v 1 0 0",
            "v 0 1 0",
            "vt 0 0",
            "usemtl material0",
            "f 1/1 2/1 3/1",
        ]
    )
    with zipfile.ZipFile(mesh_dir / "matterport_mesh.zip", "w") as archive:
        archive.writestr("scan//matterport_mesh/mesh/mesh.obj", obj_text)
        archive.writestr(
            "scan//matterport_mesh/mesh/mesh.mtl",
            "newmtl material0\nmap_Kd texture.png\n",
        )
        archive.write(texture_path, "scan//matterport_mesh/mesh/texture.png")
    monkeypatch.setenv("MATTERPORT_DATA_DIR", str(tmp_path / "data"))
    connectivity_dir = _write_connectivity(tmp_path, scan_id)
    generated = generate_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        instance_name="case",
        connectivity_dir=connectivity_dir,
        output_size=8,
    )
    monkeypatch.setattr(
        "graph_visualizer.topdown_texture.zipfile.ZipFile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("mesh should not load")),
    )

    cached = load_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        connectivity_dir=connectivity_dir,
        output_size=8,
    )

    assert cached == generated


def test_load_cached_topdown_texture_returns_none_when_missing(tmp_path):
    scan_id = "scan"
    connectivity_dir = _write_connectivity(tmp_path, scan_id)

    cached = load_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        connectivity_dir=connectivity_dir,
        output_size=8,
    )

    assert cached is None


def test_cutaway_removes_above_cut_ceiling_triangles(tmp_path, monkeypatch):
    scan_id = "scan"
    mesh_dir = tmp_path / "data" / "v1" / "scans" / scan_id
    mesh_dir.mkdir(parents=True)
    texture = Image.fromarray(
        np.array([[[220, 40, 40], [220, 40, 40]]], dtype=np.uint8),
        mode="RGB",
    )
    texture_path = tmp_path / "texture.png"
    texture.save(texture_path)
    obj_text = "\n".join(
        [
            "mtllib mesh.mtl",
            "v 0 0 0.2",
            "v 1 0 0.2",
            "v 1 1 0.2",
            "v 0 1 0.2",
            "v 0 0 2.0",
            "v 1 0 2.0",
            "v 1 1 2.0",
            "v 0 1 2.0",
            "vt 0 0",
            "vt 1 0",
            "vt 1 1",
            "vt 0 1",
            "usemtl material0",
            "f 1/1 2/2 3/3",
            "f 1/1 3/3 4/4",
            "f 5/1 6/2 7/3",
            "f 5/1 7/3 8/4",
        ]
    )
    with zipfile.ZipFile(mesh_dir / "matterport_mesh.zip", "w") as archive:
        archive.writestr("scan//matterport_mesh/mesh/mesh.obj", obj_text)
        archive.writestr(
            "scan//matterport_mesh/mesh/mesh.mtl",
            "newmtl material0\nmap_Kd texture.png\n",
        )
        archive.write(texture_path, "scan//matterport_mesh/mesh/texture.png")
    monkeypatch.setenv("MATTERPORT_DATA_DIR", str(tmp_path / "data"))
    connectivity_dir = _write_connectivity(tmp_path, scan_id, viewpoint_z=0.65)

    metadata = generate_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        instance_name="case",
        connectivity_dir=connectivity_dir,
        output_size=8,
        render_mode="single_cutaway",
    )

    assert metadata["render_mode"] == "single_cutaway_v1"
    assert metadata["cut_z"] == 0.75
    assert metadata["cut_z_offset"] == 0.1
    cache_png_path = _metadata_png_path(tmp_path, metadata)
    image = np.asarray(
        Image.open(cache_png_path)
    )
    assert np.any(np.all(image == [220, 40, 40], axis=2))


def test_multi_slice_composite_includes_higher_mesh_surfaces(tmp_path, monkeypatch):
    scan_id = "scan"
    mesh_dir = tmp_path / "data" / "v1" / "scans" / scan_id
    mesh_dir.mkdir(parents=True)
    red_texture = Image.fromarray(np.array([[[255, 0, 0]]], dtype=np.uint8), mode="RGB")
    blue_texture = Image.fromarray(np.array([[[0, 0, 255]]], dtype=np.uint8), mode="RGB")
    red_path = tmp_path / "red.png"
    blue_path = tmp_path / "blue.png"
    red_texture.save(red_path)
    blue_texture.save(blue_path)
    obj_text = "\n".join(
        [
            "mtllib mesh.mtl",
            "v 0 0 0.2",
            "v 0.45 0 0.2",
            "v 0 0.45 0.2",
            "v 0.55 0.55 1.0",
            "v 1 0.55 1.0",
            "v 0.55 1 1.0",
            "vt 0 0",
            "usemtl low",
            "f 1/1 2/1 3/1",
            "usemtl high",
            "f 4/1 5/1 6/1",
        ]
    )
    with zipfile.ZipFile(mesh_dir / "matterport_mesh.zip", "w") as archive:
        archive.writestr("scan//matterport_mesh/mesh/mesh.obj", obj_text)
        archive.writestr(
            "scan//matterport_mesh/mesh/mesh.mtl",
            "newmtl low\nmap_Kd red.png\nnewmtl high\nmap_Kd blue.png\n",
        )
        archive.write(red_path, "scan//matterport_mesh/mesh/red.png")
        archive.write(blue_path, "scan//matterport_mesh/mesh/blue.png")
    monkeypatch.setenv("MATTERPORT_DATA_DIR", str(tmp_path / "data"))
    connectivity_dir = _write_connectivity(tmp_path, scan_id, viewpoint_z=0.65)

    single_metadata = generate_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        instance_name="single",
        connectivity_dir=connectivity_dir,
        output_size=16,
        cut_z_offset=0.15,
        render_mode="single_cutaway",
    )
    multi_metadata = generate_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        instance_name="multi",
        connectivity_dir=connectivity_dir,
        output_size=16,
        cut_z_offset=0.15,
        render_mode="multi_slice_composite",
        composite_max_z_offset=0.6,
        composite_slices=3,
    )

    single_image = np.asarray(Image.open(_metadata_png_path(tmp_path, single_metadata)))
    multi_image = np.asarray(Image.open(_metadata_png_path(tmp_path, multi_metadata)))
    assert single_metadata["render_mode"] == "single_cutaway_v1"
    assert multi_metadata["render_mode"] == "multi_slice_hole_fill_v1"
    assert not np.any(np.all(single_image == [0, 0, 255], axis=2))
    assert np.any(np.all(multi_image == [0, 0, 255], axis=2))


def test_multi_slice_composite_preserves_lower_surface_on_overlap(tmp_path, monkeypatch):
    scan_id = "scan"
    mesh_dir = tmp_path / "data" / "v1" / "scans" / scan_id
    mesh_dir.mkdir(parents=True)
    red_texture = Image.fromarray(np.array([[[255, 0, 0]]], dtype=np.uint8), mode="RGB")
    blue_texture = Image.fromarray(np.array([[[0, 0, 255]]], dtype=np.uint8), mode="RGB")
    red_path = tmp_path / "red.png"
    blue_path = tmp_path / "blue.png"
    red_texture.save(red_path)
    blue_texture.save(blue_path)
    obj_text = "\n".join(
        [
            "mtllib mesh.mtl",
            "v 0 0 0.2",
            "v 1 0 0.2",
            "v 0 1 0.2",
            "v 0 0 1.0",
            "v 1 0 1.0",
            "v 0 1 1.0",
            "vt 0 0",
            "usemtl low",
            "f 1/1 2/1 3/1",
            "usemtl high",
            "f 4/1 5/1 6/1",
        ]
    )
    with zipfile.ZipFile(mesh_dir / "matterport_mesh.zip", "w") as archive:
        archive.writestr("scan//matterport_mesh/mesh/mesh.obj", obj_text)
        archive.writestr(
            "scan//matterport_mesh/mesh/mesh.mtl",
            "newmtl low\nmap_Kd red.png\nnewmtl high\nmap_Kd blue.png\n",
        )
        archive.write(red_path, "scan//matterport_mesh/mesh/red.png")
        archive.write(blue_path, "scan//matterport_mesh/mesh/blue.png")
    monkeypatch.setenv("MATTERPORT_DATA_DIR", str(tmp_path / "data"))
    connectivity_dir = _write_connectivity(tmp_path, scan_id, viewpoint_z=0.65)

    metadata = generate_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        instance_name="case",
        connectivity_dir=connectivity_dir,
        output_size=16,
        cut_z_offset=0.15,
        render_mode="multi_slice_composite",
        composite_max_z_offset=0.6,
        composite_slices=3,
    )

    image = np.asarray(Image.open(_metadata_png_path(tmp_path, metadata)))
    assert metadata["render_mode"] == "multi_slice_hole_fill_v1"
    assert np.any(np.all(image == [255, 0, 0], axis=2))
    assert not np.any(np.all(image == [0, 0, 255], axis=2))


def test_single_slice_uses_highest_z_on_overlapping_triangles(tmp_path, monkeypatch):
    scan_id = "scan"
    mesh_dir = tmp_path / "data" / "v1" / "scans" / scan_id
    mesh_dir.mkdir(parents=True)
    red_texture = Image.fromarray(np.array([[[255, 0, 0]]], dtype=np.uint8), mode="RGB")
    blue_texture = Image.fromarray(np.array([[[0, 0, 255]]], dtype=np.uint8), mode="RGB")
    red_path = tmp_path / "red.png"
    blue_path = tmp_path / "blue.png"
    red_texture.save(red_path)
    blue_texture.save(blue_path)
    obj_text = "\n".join(
        [
            "mtllib mesh.mtl",
            "v 0 0 0.2",
            "v 1 0 0.2",
            "v 0 1 0.2",
            "v 0 0 0.4",
            "v 1 0 0.4",
            "v 0 1 0.4",
            "vt 0 0",
            "usemtl low",
            "f 1/1 2/1 3/1",
            "usemtl high",
            "f 4/1 5/1 6/1",
        ]
    )
    with zipfile.ZipFile(mesh_dir / "matterport_mesh.zip", "w") as archive:
        archive.writestr("scan//matterport_mesh/mesh/mesh.obj", obj_text)
        archive.writestr(
            "scan//matterport_mesh/mesh/mesh.mtl",
            "newmtl low\nmap_Kd red.png\nnewmtl high\nmap_Kd blue.png\n",
        )
        archive.write(red_path, "scan//matterport_mesh/mesh/red.png")
        archive.write(blue_path, "scan//matterport_mesh/mesh/blue.png")
    monkeypatch.setenv("MATTERPORT_DATA_DIR", str(tmp_path / "data"))
    connectivity_dir = _write_connectivity(tmp_path, scan_id, viewpoint_z=0.65)

    metadata = generate_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        instance_name="case",
        connectivity_dir=connectivity_dir,
        output_size=16,
        render_mode="single_cutaway",
    )

    image = np.asarray(Image.open(_metadata_png_path(tmp_path, metadata)))
    assert np.any(np.all(image == [0, 0, 255], axis=2))
    assert not np.any(np.all(image == [255, 0, 0], axis=2))


def test_floor_textures_use_independent_z_bands(tmp_path, monkeypatch):
    scan_id = "scan"
    mesh_dir = tmp_path / "data" / "v1" / "scans" / scan_id
    mesh_dir.mkdir(parents=True)
    red_texture = Image.fromarray(np.array([[[255, 0, 0]]], dtype=np.uint8), mode="RGB")
    blue_texture = Image.fromarray(np.array([[[0, 0, 255]]], dtype=np.uint8), mode="RGB")
    red_path = tmp_path / "red.png"
    blue_path = tmp_path / "blue.png"
    red_texture.save(red_path)
    blue_texture.save(blue_path)
    obj_text = "\n".join(
        [
            "mtllib mesh.mtl",
            "v 0 0 0.0",
            "v 1 0 0.0",
            "v 0 1 0.0",
            "v 0 0 3.0",
            "v 1 0 3.0",
            "v 0 1 3.0",
            "vt 0 0",
            "usemtl low",
            "f 1/1 2/1 3/1",
            "usemtl high",
            "f 4/1 5/1 6/1",
        ]
    )
    with zipfile.ZipFile(mesh_dir / "matterport_mesh.zip", "w") as archive:
        archive.writestr("scan//matterport_mesh/mesh/mesh.obj", obj_text)
        archive.writestr(
            "scan//matterport_mesh/mesh/mesh.mtl",
            "newmtl low\nmap_Kd red.png\nnewmtl high\nmap_Kd blue.png\n",
        )
        archive.write(red_path, "scan//matterport_mesh/mesh/red.png")
        archive.write(blue_path, "scan//matterport_mesh/mesh/blue.png")
    monkeypatch.setenv("MATTERPORT_DATA_DIR", str(tmp_path / "data"))
    connectivity_dir = tmp_path / "connectivity"
    connectivity_dir.mkdir()
    (connectivity_dir / ("%s_connectivity.json" % scan_id)).write_text(
        json.dumps(
            [
                {
                    "image_id": "vp0",
                    "included": True,
                    "pose": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                },
                {
                    "image_id": "vp1",
                    "included": True,
                    "pose": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1],
                },
                {
                    "image_id": "vp2",
                    "included": True,
                    "pose": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 3.0],
                },
                {
                    "image_id": "vp3",
                    "included": True,
                    "pose": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 3.1],
                },
            ]
        ),
        encoding="utf-8",
    )

    metadata = generate_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        instance_name="case",
        connectivity_dir=connectivity_dir,
        output_size=16,
        render_mode="multi_slice_composite",
        cut_z_offset=0.2,
        composite_max_z_offset=4.0,
        composite_slices=3,
    )

    assert [floor["floor_index"] for floor in metadata["floors"]] == [0, 1]
    assert metadata["floors"][0]["floor_upper_z"] == pytest.approx(1.55)
    assert metadata["floors"][0]["composite_max_z"] == pytest.approx(1.55)
    assert metadata["floors"][1]["floor_lower_z"] == pytest.approx(1.55)
    assert metadata["floors"][1]["floor_upper_z"] == float("inf")
    low_image = np.asarray(Image.open(tmp_path / metadata["floors"][0]["url"].removeprefix("/assets/")))
    high_image = np.asarray(Image.open(tmp_path / metadata["floors"][1]["url"].removeprefix("/assets/")))
    assert np.any(np.all(low_image == [255, 0, 0], axis=2))
    assert not np.any(np.all(low_image == [0, 0, 255], axis=2))
    assert np.any(np.all(high_image == [0, 0, 255], axis=2))
    assert not np.any(np.all(high_image == [255, 0, 0], axis=2))


def test_multi_floor_render_loads_mesh_once(tmp_path, monkeypatch):
    scan_id = "scan"
    mesh_dir = tmp_path / "data" / "v1" / "scans" / scan_id
    mesh_dir.mkdir(parents=True)
    texture = Image.fromarray(np.array([[[255, 0, 0]]], dtype=np.uint8), mode="RGB")
    texture_path = tmp_path / "texture.png"
    texture.save(texture_path)
    obj_text = "\n".join(
        [
            "mtllib mesh.mtl",
            "v 0 0 0.0",
            "v 1 0 0.0",
            "v 0 1 0.0",
            "v 0 0 3.0",
            "v 1 0 3.0",
            "v 0 1 3.0",
            "vt 0 0",
            "usemtl material0",
            "f 1/1 2/1 3/1",
            "f 4/1 5/1 6/1",
        ]
    )
    with zipfile.ZipFile(mesh_dir / "matterport_mesh.zip", "w") as archive:
        archive.writestr("scan//matterport_mesh/mesh/mesh.obj", obj_text)
        archive.writestr(
            "scan//matterport_mesh/mesh/mesh.mtl",
            "newmtl material0\nmap_Kd texture.png\n",
        )
        archive.write(texture_path, "scan//matterport_mesh/mesh/texture.png")
    connectivity_dir = tmp_path / "connectivity"
    connectivity_dir.mkdir()
    (connectivity_dir / ("%s_connectivity.json" % scan_id)).write_text(
        json.dumps(
            [
                {
                    "image_id": "vp0",
                    "included": True,
                    "pose": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                },
                {
                    "image_id": "vp1",
                    "included": True,
                    "pose": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1],
                },
                {
                    "image_id": "vp2",
                    "included": True,
                    "pose": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 3.0],
                },
                {
                    "image_id": "vp3",
                    "included": True,
                    "pose": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 3.1],
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MATTERPORT_DATA_DIR", str(tmp_path / "data"))
    zipfile_open_count = 0
    original_zipfile = zipfile.ZipFile

    def counting_zipfile(*args, **kwargs):
        nonlocal zipfile_open_count
        zipfile_open_count += 1
        return original_zipfile(*args, **kwargs)

    monkeypatch.setattr("graph_visualizer.topdown_texture.zipfile.ZipFile", counting_zipfile)

    metadata = generate_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        instance_name="case",
        connectivity_dir=connectivity_dir,
        output_size=16,
    )

    assert [floor["floor_index"] for floor in metadata["floors"]] == [0, 1]
    assert zipfile_open_count == 1


def test_triangle_crossing_cut_plane_is_clipped():
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 2.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float32,
    )
    texcoords = np.array(
        [
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
        ],
        dtype=np.float32,
    )

    triangles = _clip_triangle_at_z(vertices=vertices, texcoords=texcoords, cut_z=1.0)

    assert len(triangles) == 2
    for clipped_vertices, clipped_texcoords in triangles:
        assert np.all(clipped_vertices[:, 2] <= 1.0)
        assert clipped_vertices.shape == (3, 3)
        assert clipped_texcoords.shape == (3, 2)


def test_compiled_rasterizer_handles_repeated_faces_quickly():
    face_count = 20000
    vertices = []
    texcoords = []
    faces = []
    for face_index in range(face_count):
        vertex_start = len(vertices)
        texcoord_start = len(texcoords)
        z = 0.2 + 0.000001 * face_index
        vertices.extend([(0.0, 0.0, z), (1.0, 0.0, z), (0.0, 1.0, z)])
        texcoords.extend([(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)])
        faces.append(
            (
                (vertex_start, texcoord_start),
                (vertex_start + 1, texcoord_start + 1),
                (vertex_start + 2, texcoord_start + 2),
                "material0",
            )
        )
    mesh = ObjMesh(vertices=vertices, texcoords=texcoords, faces=faces)
    textures = {"material0": np.array([[[10, 20, 30]]], dtype=np.uint8)}
    assets = TextureRenderAssets(
        mesh=mesh,
        textures=textures,
        face_z_ranges=_face_z_ranges(mesh),
        face_batches=_build_texture_face_batches(mesh=mesh, textures=textures),
        min_x=0.0,
        max_x=1.0,
        min_y=0.0,
        max_y=1.0,
        width=64,
        height=64,
    )

    _render_topdown_slice(assets=assets, cut_z=1.0, lower_z=-np.inf)
    start = time.perf_counter()
    image, depth = _render_topdown_slice(assets=assets, cut_z=1.0, lower_z=-np.inf)
    elapsed = time.perf_counter() - start

    assert np.any(depth > -np.inf)
    assert np.any(np.all(image == [10, 20, 30], axis=2))
    assert elapsed < 2.0


def test_stale_topdown_cache_is_regenerated(tmp_path, monkeypatch):
    scan_id = "scan"
    mesh_dir = tmp_path / "data" / "v1" / "scans" / scan_id
    mesh_dir.mkdir(parents=True)
    texture = Image.fromarray(
        np.array([[[10, 20, 30]]], dtype=np.uint8),
        mode="RGB",
    )
    texture_path = tmp_path / "texture.png"
    texture.save(texture_path)
    obj_text = "\n".join(
        [
            "mtllib mesh.mtl",
            "v 0 0 0",
            "v 1 0 0",
            "v 0 1 0",
            "vt 0 0",
            "vt 1 0",
            "vt 0 1",
            "usemtl material0",
            "f 1/1 2/2 3/3",
        ]
    )
    with zipfile.ZipFile(mesh_dir / "matterport_mesh.zip", "w") as archive:
        archive.writestr("scan//matterport_mesh/mesh/mesh.obj", obj_text)
        archive.writestr(
            "scan//matterport_mesh/mesh/mesh.mtl",
            "newmtl material0\nmap_Kd texture.png\n",
        )
        archive.write(texture_path, "scan//matterport_mesh/mesh/texture.png")
    cache_png_path, cache_metadata_path = _topdown_texture_cache_paths(
        project_root=tmp_path,
        scan_id=scan_id,
        render_mode=TEXTURE_RENDER_MODES["multi_slice_composite"],
        output_size=8,
        cut_z_offset=0.1,
        composite_max_z_offset=1.7,
        composite_slices=6,
        floor_index=0,
        floor_reference_z=0.65,
        floor_lower_z=float("-inf"),
        floor_upper_z=float("inf"),
    )
    cache_png_path.parent.mkdir(parents=True)
    cache_png_path.write_bytes(b"stale")
    cache_metadata_path.write_text(
        json.dumps(
            {
                "render_mode": "single_cutaway_v1",
                "cut_z": 0.8,
                "cut_z_offset": 0.15,
                "composite_max_z": 2.25,
                "composite_max_z_offset": 1.6,
                "composite_slices": 5,
                "output_size": 4,
                "width": 1,
                "height": 1,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MATTERPORT_DATA_DIR", str(tmp_path / "data"))
    connectivity_dir = _write_connectivity(tmp_path, scan_id)

    metadata = generate_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        instance_name="case",
        connectivity_dir=connectivity_dir,
        output_size=8,
        render_mode="multi_slice_composite",
        composite_max_z_offset=1.7,
        composite_slices=6,
    )

    assert metadata["render_mode"] == "multi_slice_hole_fill_v1"
    assert metadata["output_size"] == 8
    assert metadata["composite_max_z_offset"] == 1.7
    assert metadata["composite_slices"] == 6
    Image.open(cache_png_path).verify()


def test_generate_house_texture_command_generates_cache_with_progress(
    tmp_path,
    monkeypatch,
    capsys,
):
    scan_id = "scan"
    mesh_dir = tmp_path / "data" / "v1" / "scans" / scan_id
    mesh_dir.mkdir(parents=True)
    texture = Image.fromarray(np.array([[[10, 20, 30]]], dtype=np.uint8), mode="RGB")
    texture_path = tmp_path / "texture.png"
    texture.save(texture_path)
    obj_text = "\n".join(
        [
            "mtllib mesh.mtl",
            "v 0 0 0",
            "v 1 0 0",
            "v 0 1 0",
            "vt 0 0",
            "vt 1 0",
            "vt 0 1",
            "usemtl material0",
            "f 1/1 2/2 3/3",
        ]
    )
    with zipfile.ZipFile(mesh_dir / "matterport_mesh.zip", "w") as archive:
        archive.writestr("scan//matterport_mesh/mesh/mesh.obj", obj_text)
        archive.writestr(
            "scan//matterport_mesh/mesh/mesh.mtl",
            "newmtl material0\nmap_Kd texture.png\n",
        )
        archive.write(texture_path, "scan//matterport_mesh/mesh/texture.png")
    monkeypatch.setenv("MATTERPORT_DATA_DIR", str(tmp_path / "data"))
    connectivity_dir = _write_connectivity(tmp_path, scan_id)
    from generate_house_texture import main

    result = main(
        [
            scan_id,
            "--project-root",
            str(tmp_path),
            "--connectivity-dir",
            str(connectivity_dir),
            "--output-size",
            "8",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "%" in output
    assert "ETA" in output
    assert "Generated house texture cache for scan scan." in output
    cached = load_cached_topdown_texture(
        scan_id=scan_id,
        project_root=tmp_path,
        connectivity_dir=connectivity_dir,
        output_size=8,
    )
    assert cached is not None
    assert cached["floors"][0]["url"].startswith("/assets/topdown_texture_cache/scan/")
