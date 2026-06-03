# delete_step_logs.py

import argparse
import re
from pathlib import Path


def collect_step_logs(test_name: str, step: int) -> list[Path]:
    base_dir = Path(__file__).resolve().parent

    target_dirs = [
        base_dir / "mllm_raw_outputs" / test_name,
        base_dir / "mllm_debug_outputs" / test_name,
    ]

    # Match step_4, step_04, step_004, step_0004, etc.
    # Avoid matching step_40 when step = 4.
    pattern = re.compile(rf"step_0*{step}(?!\d)")

    files_to_delete = []

    for folder in target_dirs:
        if not folder.exists():
            print(f"[Skip] Folder does not exist: {folder}")
            continue

        for file_path in folder.iterdir():
            if file_path.is_file() and pattern.search(file_path.name):
                files_to_delete.append(file_path)

    return sorted(files_to_delete)


def delete_step_logs(test_name: str, step: int) -> None:
    base_dir = Path(__file__).resolve().parent
    files_to_delete = collect_step_logs(test_name, step)

    if not files_to_delete:
        print(f"No files found for step {step} in test '{test_name}'.")
        return

    print(f"The following {len(files_to_delete)} file(s) will be deleted:\n")

    for file_path in files_to_delete:
        print(file_path.relative_to(base_dir))

    confirm = (
        input("\nConfirm deletion? Enter 'y' to delete or 'n' to cancel: ")
        .strip()
        .lower()
    )

    if confirm != "y":
        print("Deletion canceled.")
        return

    deleted_count = 0

    for file_path in files_to_delete:
        try:
            file_path.unlink()
            deleted_count += 1
            print(f"[Deleted] {file_path.relative_to(base_dir)}")
        except OSError as error:
            print(f"[Error] Failed to delete {file_path}: {error}")

    print(f"\nDone. Deleted {deleted_count} file(s).")


def main():
    parser = argparse.ArgumentParser(
        description="Delete log files for a given step from raw and debug output folders."
    )
    parser.add_argument("test_name", help="Test folder name, such as test4")
    parser.add_argument("step", type=int, help="Step number, such as 4")

    args = parser.parse_args()
    delete_step_logs(args.test_name, args.step)


if __name__ == "__main__":
    main()
