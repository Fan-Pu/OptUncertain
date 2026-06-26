from types import SimpleNamespace

import pytest
from gurobipy import GRB

from optimizer_route_logger import build_optimizer_route_log_payload
from optimization_model.optimizer import RollingHorizonOptimizer


def _model(status, sol_count):
    return SimpleNamespace(Status=status, SolCount=sol_count)


def test_optimizer_accepts_optimal_status():
    RollingHorizonOptimizer._assert_accepted_solver_status(
        _model(status=GRB.OPTIMAL, sol_count=1)
    )


def test_optimizer_accepts_time_limit_with_incumbent():
    RollingHorizonOptimizer._assert_accepted_solver_status(
        _model(status=GRB.TIME_LIMIT, sol_count=1)
    )


def test_optimizer_rejects_time_limit_without_incumbent():
    with pytest.raises(RuntimeError, match="without a feasible incumbent"):
        RollingHorizonOptimizer._assert_accepted_solver_status(
            _model(status=GRB.TIME_LIMIT, sol_count=0)
        )


def test_optimizer_rejects_unrelated_non_optimal_status():
    with pytest.raises(RuntimeError, match="Gurobi status: INFEASIBLE"):
        RollingHorizonOptimizer._assert_accepted_solver_status(
            _model(status=GRB.INFEASIBLE, sol_count=0)
        )


class MultiObjectiveModel:
    Status = GRB.OPTIMAL
    Runtime = 0.05
    SolCount = 3
    ObjVal = -0.00211965
    NumObj = 2

    @property
    def ObjBound(self):
        raise AttributeError("Unable to retrieve attribute 'ObjBound'")

    @property
    def MIPGap(self):
        raise AttributeError("Unable to retrieve attribute 'MIPGap'")


def test_scalar_solver_metadata_records_bound_and_gap():
    model = SimpleNamespace(
        Status=GRB.TIME_LIMIT,
        Runtime=60.25,
        SolCount=2,
        ObjVal=12.5,
        NumObj=1,
        ObjBound=13.0,
        MIPGap=0.04,
    )

    metadata = RollingHorizonOptimizer._solver_metadata(model)

    assert metadata == {
        "status": GRB.TIME_LIMIT,
        "status_name": "TIME_LIMIT",
        "runtime_seconds": 60.25,
        "solution_count": 2,
        "objective_value": 12.5,
        "used_time_limit_incumbent": True,
        "is_multi_objective": False,
        "objective_bound": 13.0,
        "mip_gap": 0.04,
    }


def test_multi_objective_solver_metadata_omits_scalar_bound_and_gap():
    metadata = RollingHorizonOptimizer._solver_metadata(MultiObjectiveModel())

    assert metadata == {
        "status": GRB.OPTIMAL,
        "status_name": "OPTIMAL",
        "runtime_seconds": 0.05,
        "solution_count": 3,
        "objective_value": -0.00211965,
        "used_time_limit_incumbent": False,
        "is_multi_objective": True,
    }


def test_optimizer_route_log_includes_solver_metadata():
    solver_metadata = {
        "status": GRB.TIME_LIMIT,
        "status_name": "TIME_LIMIT",
        "runtime_seconds": 60.25,
        "solution_count": 2,
        "objective_value": 12.5,
        "objective_bound": 13.0,
        "mip_gap": 0.04,
        "used_time_limit_incumbent": True,
        "is_multi_objective": False,
    }

    payload = build_optimizer_route_log_payload(
        test_case="case",
        optimization_result={
            "solver": solver_metadata,
            "target_assignments": [],
            "agent_paths": {
                "agent0": {
                    "route_node_ids": [1, 2],
                    "objective_terms": {"objective_value": 12.5},
                }
            },
        },
        agent_ids=["agent0"],
        step_index=0,
    )

    assert payload["solver"] == solver_metadata
