from __future__ import annotations

import json
import zipfile

import numpy as np
from PIL import Image

from graph_visualizer.topdown_texture import (
    _clip_triangle_at_z,
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

    assert metadata["url"] == "/assets/mllm_debug_outputs/case/scan_topdown_texture.png"
    assert metadata["render_mode"] == "interior_cutaway_v1"
    assert metadata["cut_z"] == 0.8
    assert metadata["min_x"] == 0.0
    assert metadata["max_x"] == 1.0
    assert metadata["min_y"] == 0.0
    assert metadata["max_y"] == 1.0
    assert metadata["width"] == 8
    assert metadata["height"] == 8
    image = np.asarray(
        Image.open(tmp_path / "mllm_debug_outputs" / "case" / "scan_topdown_texture.png")
    )
    assert np.any(image != 255)


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
    )

    assert metadata["cut_z"] == 0.8
    image = np.asarray(
        Image.open(tmp_path / "mllm_debug_outputs" / "case" / "scan_topdown_texture.png")
    )
    assert np.any(np.all(image == [220, 40, 40], axis=2))


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
    cache_dir = tmp_path / "mllm_debug_outputs" / "case"
    cache_dir.mkdir(parents=True)
    (cache_dir / "scan_topdown_texture.png").write_bytes(b"stale")
    (cache_dir / "scan_topdown_texture.json").write_text(
        json.dumps({"width": 1, "height": 1}),
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
    )

    assert metadata["render_mode"] == "interior_cutaway_v1"
    Image.open(cache_dir / "scan_topdown_texture.png").verify()
