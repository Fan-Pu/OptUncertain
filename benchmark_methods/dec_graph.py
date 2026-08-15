from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import time
from typing import Callable, Dict, List, Tuple


@dataclass(frozen=True)
class AgentPhaseTiming:
    started_at: float
    ended_at: float


class DecGraphAgentPhaseError(RuntimeError):
    def __init__(self, stage: str, agent_id: str, cause: BaseException):
        self.stage = str(stage)
        self.agent_id = str(agent_id)
        self.cause = cause
        super().__init__(
            "Dec-Graph %s failed for %s: %s"
            % (self.stage, self.agent_id, str(cause))
        )


def run_parallel_agent_phase(
    *,
    stage: str,
    agent_ids: List[str],
    call: Callable[[str], object],
) -> Tuple[Dict[str, object], Dict[str, AgentPhaseTiming]]:
    """Run one synchronous Dec-Graph phase concurrently for all agents."""

    def timed_call(agent_id: str):
        started_at = time.time()
        result = call(agent_id)
        ended_at = time.time()
        return result, AgentPhaseTiming(started_at, ended_at)

    results: Dict[str, object] = {}
    timings: Dict[str, AgentPhaseTiming] = {}
    with ThreadPoolExecutor(max_workers=len(agent_ids)) as executor:
        future_to_agent = {
            executor.submit(timed_call, agent_id): agent_id
            for agent_id in agent_ids
        }
        for future in as_completed(future_to_agent):
            agent_id = future_to_agent[future]
            try:
                result, timing = future.result()
            except Exception as exc:
                raise DecGraphAgentPhaseError(stage, agent_id, exc) from exc
            results[agent_id] = result
            timings[agent_id] = timing

    return results, timings


def create_started_gurobi_environments(agent_ids: List[str]):
    from gurobipy import Env

    environments = {}
    for agent_id in agent_ids:
        environment = Env(empty=True)
        environment.setParam("OutputFlag", 0)
        environment.start()
        environments[str(agent_id)] = environment
    return environments


def dispose_gurobi_environments(environments: Dict[str, object]) -> None:
    for environment in environments.values():
        environment.dispose()
