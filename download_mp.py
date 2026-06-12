#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from io import StringIO
import os
import ssl
import tempfile
from urllib.request import urlopen, Request
import zipfile
import certifi

# Use the working host + https
BASE_URL = "https://kaldir.vc.in.tum.de/matterport/"
RELEASE = "v1/scans"
RELEASE_TASKS = "v1/tasks/"
RELEASE_SIZE = "1.3TB"
TOS_URL = BASE_URL + "MP_TOS.pdf"

FILETYPES = [
    "cameras",
    "matterport_camera_intrinsics",
    "matterport_camera_poses",
    "matterport_color_images",
    "matterport_depth_images",
    "matterport_hdr_images",
    "matterport_mesh",
    "matterport_skybox_images",
    "undistorted_camera_parameters",
    "undistorted_color_images",
    "undistorted_depth_images",
    "undistorted_normal_images",
    "house_segmentations",
    "region_segmentations",
    "image_overlap_data",
    "poisson_meshes",
    "sens",
]

TASK_FILES = {
    "keypoint_matching_data": ["keypoint_matching/data.zip"],
    "keypoint_matching_models": ["keypoint_matching/models.zip"],
    "surface_normal_data": ["surface_normal/data_list.zip"],
    "surface_normal_models": ["surface_normal/models.zip"],
    "region_classification_data": ["region_classification/data.zip"],
    "region_classification_models": ["region_classification/models.zip"],
    "semantic_voxel_label_data": ["semantic_voxel_label/data.zip"],
    "semantic_voxel_label_models": ["semantic_voxel_label/models.zip"],
    "minos": ["mp3d_minos.zip"],
    "gibson": ["mp3d_for_gibson.tar.gz"],
    "habitat": ["mp3d_habitat.zip"],
    "pixelsynth": ["mp3d_pixelsynth.zip"],
    "igibson": ["mp3d_for_igibson.zip"],
    "mp360": [
        "mp3d_360/data_00.zip",
        "mp3d_360/data_01.zip",
        "mp3d_360/data_02.zip",
        "mp3d_360/data_03.zip",
        "mp3d_360/data_04.zip",
        "mp3d_360/data_05.zip",
        "mp3d_360/data_06.zip",
    ],
}

# Force a known CA bundle (fixes "unable to get local issuer certificate" in many setups)
SSL_CTX = ssl.create_default_context(cafile=certifi.where())

DOWNSIZED_WIDTH = 512
DOWNSIZED_HEIGHT = 512
SKYBOX_WIDTH = 1024
SKYBOX_HEIGHT = 1024
MATTERSIM_REQUIRED_TYPES = [
    "matterport_skybox_images",
    "undistorted_camera_parameters",
    "undistorted_depth_images",
]


def _urlopen(url: str):
    # Add a user-agent because some servers behave better with it
    req = Request(url, headers={"User-Agent": "mp-downloader/py3"})
    return urlopen(req, context=SSL_CTX)


def get_release_scans(release_file: str):
    with _urlopen(release_file) as resp:
        text = resp.read().decode("utf-8", errors="ignore").strip()
    # scans.txt is space-separated in the current hosting
    scans = [x for x in text.replace("\n", " ").split(" ") if x]
    return scans


def download_file(url: str, out_file: str, chunk_bytes: int = 1024 * 1024):
    out_dir = os.path.dirname(out_file)
    if out_dir and (not os.path.isdir(out_dir)):
        os.makedirs(out_dir, exist_ok=True)

    if os.path.isfile(out_file):
        print("WARNING: skipping existing file " + out_file)
        return

    print("\t" + url + " > " + out_file)

    fd, tmp_path = tempfile.mkstemp(dir=out_dir if out_dir else None)
    os.close(fd)

    try:
        with _urlopen(url) as r, open(tmp_path, "wb") as f:
            while True:
                chunk = r.read(chunk_bytes)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(tmp_path, out_file)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise


def download_scan(scan_id: str, out_dir: str, file_types):
    print("Downloading MP scan " + scan_id + " ...")
    os.makedirs(out_dir, exist_ok=True)

    for ft in file_types:
        url = BASE_URL + RELEASE + "/" + scan_id + "/" + ft + ".zip"
        out_file = os.path.join(out_dir, ft + ".zip")
        download_file(url, out_file)

    print("Downloaded scan " + scan_id)


def extract_scan_zip(scan_id: str, scan_dir: str, file_type: str):
    zip_path = os.path.join(scan_dir, file_type + ".zip")
    print("Extracting " + zip_path + " ...")

    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue

            parts = [p for p in member.filename.replace("\\", "/").split("/") if p]
            if parts[0] == scan_id:
                parts = parts[1:]

            out_file = os.path.join(scan_dir, *parts)
            os.makedirs(os.path.dirname(out_file), exist_ok=True)
            with zf.open(member) as src, open(out_file, "wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)


def generate_rgb_skyboxes(scan_dir: str):
    import cv2
    import numpy as np

    skybox_dir = os.path.join(scan_dir, "matterport_skybox_images")
    pano_ids = sorted(
        {
            name.split("_skybox")[0]
            for name in os.listdir(skybox_dir)
            if name.endswith("_sami.jpg") and "_skybox" in name
        }
    )
    print("Generating RGB skyboxes for " + str(len(pano_ids)) + " panoramas ...")

    for pano_id in pano_ids:
        ims = []
        for skybox_ix in range(6):
            skybox_file = os.path.join(
                skybox_dir, "%s_skybox%d_sami.jpg" % (pano_id, skybox_ix)
            )
            skybox = cv2.imread(skybox_file)
            ims.append(
                cv2.resize(
                    skybox,
                    (DOWNSIZED_WIDTH, DOWNSIZED_HEIGHT),
                    interpolation=cv2.INTER_AREA,
                )
            )
        out_file = os.path.join(skybox_dir, pano_id + "_skybox_small.jpg")
        assert cv2.imwrite(out_file, np.concatenate(ims, axis=1))


def camera_parameters(scan_dir: str, scan_id: str):
    import numpy as np
    from numpy.linalg import inv

    camera_file = os.path.join(
        scan_dir, "undistorted_camera_parameters", scan_id + ".conf"
    )
    intrinsics = {}
    extrinsics = {}
    with open(camera_file) as f:
        pos = -1
        for line in f.readlines():
            if "intrinsics_matrix" in line:
                intr = line.split()
                c = np.zeros((3, 3), np.double)
                c[0, 0] = intr[1]
                c[1, 1] = intr[5]
                c[0, 2] = intr[3]
                c[1, 2] = intr[6]
                c[2, 2] = 1.0
                pos = 0
            elif pos >= 0 and pos < 6:
                q = line.find(".jpg")
                camera = line[q - 37 : q]
                if pos == 0:
                    intrinsics[camera[:-2]] = c
                transform = np.loadtxt(StringIO(line.split("jpg ")[1])).reshape((4, 4))
                extrinsics[camera] = (transform, inv(transform))
                pos += 1
    return intrinsics, extrinsics


def z_to_euclid(k_inv, depth):
    import numpy as np
    from numpy.linalg import norm

    assert len(depth.shape) == 2
    h = depth.shape[0]
    w = depth.shape[1]
    y, x = np.indices((h, w))
    homo_pixels = np.vstack((x.flatten(), y.flatten(), np.ones((x.size))))
    rays = k_inv.dot(homo_pixels)
    cos_theta = np.array([0, 0, 1]).dot(rays) / norm(rays, axis=0)
    return depth / cos_theta.reshape(h, w)


def intrinsic_matrix(width: int, height: int):
    import numpy as np

    k = np.zeros((3, 3), np.double)
    k[0, 0] = width / 2
    k[1, 1] = height / 2
    k[0, 2] = width / 2
    k[1, 2] = height / 2
    k[2, 2] = 1.0
    return k


def generate_depth_skyboxes(scan_id: str, scan_dir: str):
    import cv2
    import numpy as np
    from numpy.linalg import inv

    skybox_dir = os.path.join(scan_dir, "matterport_skybox_images")
    depth_dir = os.path.join(scan_dir, "undistorted_depth_images")
    intrinsics, extrinsics = camera_parameters(scan_dir, scan_id)
    k_skybox = intrinsic_matrix(SKYBOX_WIDTH, SKYBOX_HEIGHT)
    pano_ids = sorted(set([item.split("_")[0] for item in intrinsics.keys()]))
    skybox_transforms = [
        np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=np.double),
        np.eye(3, dtype=np.double),
        np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], dtype=np.double),
        np.array([[-1, 0, 0], [0, 1, 0], [0, 0, -1]], dtype=np.double),
        np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], dtype=np.double),
        np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=np.double),
    ]
    print("Generating depth skyboxes for " + str(len(pano_ids)) + " panoramas ...")

    for pano_id in pano_ids:
        depth = {}
        for camera in range(3):
            k_inv = inv(intrinsics["%s_i%d" % (pano_id, camera)])
            for angle in range(6):
                name = "%d_%d" % (camera, angle)
                depth_file = os.path.join(
                    depth_dir, "%s_d%s.png" % (pano_id, name)
                )
                d_im = cv2.imread(depth_file, cv2.IMREAD_ANYDEPTH)
                depth[name] = z_to_euclid(k_inv, d_im)

        ims = []
        for skybox_ix in range(6):
            skybox_ctw, _ = extrinsics[pano_id + "_i1_5"]
            skybox_ctw = skybox_ctw[:3, :3].dot(skybox_transforms[skybox_ix])
            skybox_wtc = inv(skybox_ctw)
            base_depth = np.zeros((SKYBOX_HEIGHT, SKYBOX_WIDTH), np.uint16)

            for camera in range(3):
                for angle in range(6):
                    im_name = "%d_%d" % (camera, angle)
                    k_im = intrinsics[pano_id + "_i" + im_name[0]]
                    t_ctw, _ = extrinsics[pano_id + "_i" + im_name]
                    r_ctw = t_ctw[:3, :3]
                    z = np.array([0, 0, 1])
                    if r_ctw.dot(z).dot(skybox_ctw.dot(z)) < 0:
                        continue

                    h = k_skybox.dot(skybox_wtc.dot(r_ctw.dot(inv(k_im))))
                    flip = cv2.flip(depth[im_name], 1)
                    warp = cv2.warpPerspective(
                        flip,
                        h,
                        (SKYBOX_HEIGHT, SKYBOX_WIDTH),
                        flags=cv2.INTER_NEAREST,
                    )
                    mask = cv2.warpPerspective(
                        np.ones_like(flip),
                        h,
                        (SKYBOX_HEIGHT, SKYBOX_WIDTH),
                        flags=cv2.INTER_LINEAR,
                    )
                    mask[warp == 0] = 0
                    mask = cv2.erode(
                        mask, np.ones((3, 3), np.uint8), iterations=1
                    )
                    locs = np.where(mask == 1)
                    base_depth[locs[0], locs[1]] = warp[locs[0], locs[1]]

            depth_small = cv2.resize(
                cv2.flip(base_depth, 1),
                (DOWNSIZED_WIDTH, DOWNSIZED_HEIGHT),
                interpolation=cv2.INTER_NEAREST,
            )
            ims.append(depth_small)

        out_file = os.path.join(
            skybox_dir, pano_id + "_skybox_depth_small.png"
        )
        assert cv2.imwrite(out_file, np.concatenate(ims, axis=1)), (
            "Could not write to " + out_file
        )


def prepare_mattersim_scan(scan_id: str, scan_dir: str, file_types):
    missing = [ft for ft in MATTERSIM_REQUIRED_TYPES if ft not in file_types]
    if missing:
        raise ValueError(
            "--prepare_mattersim requires --type to include: " + ", ".join(missing)
        )

    for file_type in MATTERSIM_REQUIRED_TYPES:
        extract_scan_zip(scan_id, scan_dir, file_type)

    generate_rgb_skyboxes(scan_dir)
    generate_depth_skyboxes(scan_id, scan_dir)
    print("Prepared MatterSim files for scan " + scan_id)


def download_release(release_scans, out_dir: str, file_types):
    print("Downloading MP release to " + out_dir + "...")
    for scan_id in release_scans:
        scan_out_dir = os.path.join(out_dir, scan_id)
        download_scan(scan_id, scan_out_dir, file_types)
    print("Downloaded MP release.")


def download_task_data(task_data, out_dir: str):
    print("Downloading MP task data for " + str(task_data) + " ...")
    for task_data_id in task_data:
        if task_data_id not in TASK_FILES:
            continue
        for filepart in TASK_FILES[task_data_id]:
            url = BASE_URL + RELEASE_TASKS + "/" + filepart
            localpath = os.path.join(out_dir, filepart)
            localdir = os.path.dirname(localpath)
            os.makedirs(localdir, exist_ok=True)
            download_file(url, localpath)
        print("Downloaded task data " + task_data_id)


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description=(
            "Downloads MP public data release.\n"
            "Example:\n"
            "  py download_mp.py -o base_dir --id 17DRP5sb8fy --type matterport_skybox_images\n"
        ),
    )
    parser.add_argument("-o", "--out_dir", required=True, help="directory in which to download")
    parser.add_argument(
        "--task_data",
        default=[],
        nargs="+",
        help="task data files to download. Any of: " + ",".join(TASK_FILES.keys()),
    )
    parser.add_argument("--id", default="ALL", help="specific scan id to download or ALL to download entire dataset")
    parser.add_argument("--type", nargs="+", help="specific file types to download. Any of: " + ",".join(FILETYPES))
    parser.add_argument(
        "--prepare_mattersim",
        action="store_true",
        help="extract scan ZIPs and generate MatterSim *_skybox_small.jpg and *_skybox_depth_small.png files",
    )
    args = parser.parse_args()

    print("By pressing Enter you confirm that you have agreed to the MP terms of use as described at:")
    print(TOS_URL)
    print("***")
    print("Press Enter to continue, or CTRL-C to exit.")
    input("")

    release_file = BASE_URL + RELEASE + ".txt"
    release_scans = get_release_scans(release_file)
    file_types = FILETYPES

    if args.task_data:
        unknown = [x for x in args.task_data if x not in TASK_FILES]
        if unknown:
            print("ERROR: Unrecognized task data id(s): " + ", ".join(unknown))
            return
        out_dir = os.path.join(args.out_dir, RELEASE_TASKS)
        download_task_data(args.task_data, out_dir)

        print("Done downloading task_data for " + str(args.task_data))
        print("Press Enter to continue on to main dataset download, or CTRL-C to exit.")
        input("")

    if args.type:
        invalid = [t for t in args.type if t not in FILETYPES]
        if invalid:
            print("ERROR: Invalid file type(s): " + ", ".join(invalid))
            return
        file_types = args.type

    if args.prepare_mattersim and args.id.upper() == "ALL":
        raise ValueError("--prepare_mattersim requires a single scan id via --id")

    if args.id and args.id.upper() != "ALL":
        scan_id = args.id
        if scan_id not in release_scans:
            print("ERROR: Invalid scan id: " + scan_id)
            return
        out_dir = os.path.join(args.out_dir, RELEASE, scan_id)
        download_scan(scan_id, out_dir, file_types)
        if args.prepare_mattersim:
            prepare_mattersim_scan(scan_id, out_dir, file_types)
        return

    if "minos" not in args.task_data and args.id.upper() == "ALL":
        if len(file_types) == len(FILETYPES):
            print("WARNING: You are downloading the entire MP release which requires " + RELEASE_SIZE + " of space.")
        else:
            print("WARNING: You are downloading all MP scans of type " + str(file_types))
        print("Note that existing scan directories will be skipped. Delete partially downloaded directories to re-download.")
        print("***")
        print("Press Enter to continue, or CTRL-C to exit.")
        input("")
        out_dir = os.path.join(args.out_dir, RELEASE)
        download_release(release_scans, out_dir, file_types)


if __name__ == "__main__":
    main()
