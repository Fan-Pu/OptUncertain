from __future__ import annotations

import json
import zipfile

import numpy as np
from PIL import Image

from graph_visualizer.topdown_texture import (
    TEXTURE_RENDER_MODES,
    _clip_triangle_at_z,
    _topdown_texture_cache_paths,
    generate_cached_topdown_texture,
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
    output_size=1800,
    cut_z_offset=0.15,
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

    cache_png_path = _cache_png_path(tmp_path, scan_id, output_size=8)
    assert metadata["url"] == _asset_url(tmp_path, cache_png_path)
    assert metadata["render_mode"] == "multi_slice_hole_fill_v1"
    assert metadata["cut_z"] == 0.8
    assert metadata["cut_z_offset"] == 0.15
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
    assert metadata["cut_z"] == 0.8
    assert metadata["cut_z_offset"] == 0.15
    cache_png_path = _cache_png_path(
        tmp_path,
        scan_id,
        output_size=8,
        render_mode="single_cutaway",
    )
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

    single_image = np.asarray(
        Image.open(
            _cache_png_path(
                tmp_path,
                scan_id,
                output_size=16,
                render_mode="single_cutaway",
            )
        )
    )
    multi_image = np.asarray(
        Image.open(
            _cache_png_path(
                tmp_path,
                scan_id,
                output_size=16,
                render_mode="multi_slice_composite",
                composite_max_z_offset=0.6,
                composite_slices=3,
            )
        )
    )
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

    image = np.asarray(
        Image.open(
            _cache_png_path(
                tmp_path,
                scan_id,
                output_size=16,
                render_mode="multi_slice_composite",
                composite_max_z_offset=0.6,
                composite_slices=3,
            )
        )
    )
    assert metadata["render_mode"] == "multi_slice_hole_fill_v1"
    assert np.any(np.all(image == [255, 0, 0], axis=2))
    assert not np.any(np.all(image == [0, 0, 255], axis=2))


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
        cut_z_offset=0.15,
        composite_max_z_offset=1.7,
        composite_slices=6,
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
