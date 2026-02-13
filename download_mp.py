#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import ssl
import tempfile
from urllib.request import urlopen, Request
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

    if args.id and args.id.upper() != "ALL":
        scan_id = args.id
        if scan_id not in release_scans:
            print("ERROR: Invalid scan id: " + scan_id)
            return
        out_dir = os.path.join(args.out_dir, RELEASE, scan_id)
        download_scan(scan_id, out_dir, file_types)
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
