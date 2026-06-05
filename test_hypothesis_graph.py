from semantic_persistence.hypothesis_graph import HypothesisGraph


def test_hypothesis_snapshot_omits_targets_but_mllm_summary_keeps_them():
    targets = [{"target_id": "0", "description": "target zero"}]
    graph = HypothesisGraph(targets=targets)

    assert "targets" not in graph.get_hypothesis_snapshot()
    assert graph.get_mllm_summary()["targets"] == targets
