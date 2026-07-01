__all__ = [
    "HypothesisGraph",
    "MLLMClient",
    "MLLMProviderCreditError",
    "MLLMRetryExhaustedError",
    "load_nav_graph",
    "shortest_path_next_hop",
    "argmin_distance_to_set",
]


def __getattr__(name):
    if name == "HypothesisGraph":
        from .hypothesis_graph import HypothesisGraph

        return HypothesisGraph
    if name == "MLLMClient":
        from .mllm_client import MLLMClient

        return MLLMClient
    if name == "MLLMRetryExhaustedError":
        from .mllm_client import MLLMRetryExhaustedError

        return MLLMRetryExhaustedError
    if name == "MLLMProviderCreditError":
        from .mllm_client import MLLMProviderCreditError

        return MLLMProviderCreditError
    if name in ("load_nav_graph", "shortest_path_next_hop", "argmin_distance_to_set"):
        from .nav_graph import (
            argmin_distance_to_set,
            load_nav_graph,
            shortest_path_next_hop,
        )

        return {
            "load_nav_graph": load_nav_graph,
            "shortest_path_next_hop": shortest_path_next_hop,
            "argmin_distance_to_set": argmin_distance_to_set,
        }[name]
    raise AttributeError(name)
