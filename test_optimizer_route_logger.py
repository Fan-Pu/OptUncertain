import json

from optimizer_route_logger import write_optimizer_route_log


def test_write_optimizer_route_log_serializes_agent_routes_and_edges(tmp_path):
    optimization_result = {
        "objective_value": 0.25,
        "objective_terms": {
            "global": {
                "raw": {
                    "goal": 1.0,
                    "distance": 2.0,
                    "arc_nonexistence": 0.0,
                    "node_nonexistence": 0.0,
                    "revisit": 0.0,
                },
                "normalized": {},
                "weighted": {},
            },
            "by_agent": {
                "agent0": {
                    "raw": {"goal": 1.0},
                    "normalized_contribution": {},
                    "weighted_contribution": {},
                }
            },
        },
        "target_assignments": [
            {"target_id": "target", "node_id": 2, "agent_id": "agent0"}
        ],
        "agent_paths": {
            "agent0": {
                "route_node_ids": [1, 2],
                "planned_path_node_ids": [2],
                "next_vp_node_id": 2,
                "objective_terms": {
                    "raw": {"goal": 1.0},
                    "normalized_contribution": {},
                    "weighted_contribution": {},
                },
            }
        },
        "selected_edges": {"agent0": [(1, 2)]},
    }

    output_path = write_optimizer_route_log(
        output_dir=tmp_path,
        test_case="case",
        optimization_result=optimization_result,
        agent_ids=["agent0"],
        step_index=3,
    )

    assert output_path == tmp_path / "optimizer_routes_step_0003.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert set(payload) == {"agents", "target_assignments"}
    assert payload["target_assignments"] == [
        {"target_id": "target", "node_id": 2, "agent_id": "agent0"}
    ]
    assert payload["agents"] == [
        {
            "agent_id": "agent0",
            "route_node_ids": [1, 2],
            "objective_terms": {
                "raw": {"goal": 1.0},
                "normalized_contribution": {},
                "weighted_contribution": {},
            },
        }
    ]


def test_write_optimizer_route_log_uses_explicit_filename(tmp_path):
    optimization_result = {
        "objective_value": 1.0,
        "objective_terms": {"global": {}, "by_agent": {"agent0": {}}},
        "target_assignments": [],
        "agent_paths": {
            "agent0": {
                "route_node_ids": [1],
                "planned_path_node_ids": [],
                "next_vp_node_id": 1,
                "objective_terms": {},
            }
        },
        "selected_edges": {"agent0": []},
    }

    output_path = write_optimizer_route_log(
        output_dir=tmp_path,
        test_case="case",
        optimization_result=optimization_result,
        agent_ids=["agent0"],
        step_index=None,
        filename="optimizer_routes_oracle.json",
    )

    assert output_path == tmp_path / "optimizer_routes_oracle.json"
    assert set(json.loads(output_path.read_text(encoding="utf-8"))) == {
        "agents",
        "target_assignments",
    }
