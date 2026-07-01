from evaluate_detection_model import _read_case_id_file, _selected_case_ids


def test_read_case_id_file_ignores_blanks_and_comments(tmp_path):
    path = tmp_path / "case_ids.txt"
    path.write_text(
        "\n# focused subset\ncase_a\n\ncase_b\n",
        encoding="utf-8",
    )

    assert _read_case_id_file(path) == ["case_a", "case_b"]


def test_selected_case_ids_uses_explicit_order():
    summary = {
        "cases": {
            "case_a": {},
            "case_b": {},
        }
    }

    assert _selected_case_ids(
        summary=summary,
        sample_count=1,
        sample_seed=0,
        sample_balance="marginal",
        case_ids=["case_b", "case_a"],
    ) == ["case_b", "case_a"]
