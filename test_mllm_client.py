import importlib.util
import pathlib
import sys
import types
import unittest


helper_stub = types.ModuleType("Helper")
helper_stub.DELTA_HEADING_RAD = 0.1
helper_stub.viewpoint_index_by_vp_label = {}
sys.modules.setdefault("Helper", helper_stub)

debugpy_stub = types.ModuleType("debugpy")
debugpy_stub.breakpoint = lambda: None
sys.modules.setdefault("debugpy", debugpy_stub)

openai_stub = types.ModuleType("openai")
openai_stub.BadRequestError = Exception


class _DummyOpenAI:
    def __init__(self, *args, **kwargs):
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=lambda **kwargs: None)
        )


openai_stub.OpenAI = _DummyOpenAI
sys.modules.setdefault("openai", openai_stub)

pil_module = types.ModuleType("PIL")
pil_image_module = types.ModuleType("PIL.Image")
pil_image_module.fromarray = lambda image, mode=None: image
pil_module.Image = pil_image_module
sys.modules.setdefault("PIL", pil_module)
sys.modules.setdefault("PIL.Image", pil_image_module)

semantic_pkg = types.ModuleType("semantic_persistence")
hypothesis_graph_stub = types.ModuleType("semantic_persistence.hypothesis_graph")
hypothesis_graph_stub.HypothesisGraph = object
semantic_pkg.hypothesis_graph = hypothesis_graph_stub
sys.modules.setdefault("semantic_persistence", semantic_pkg)
sys.modules.setdefault("semantic_persistence.hypothesis_graph", hypothesis_graph_stub)

module_path = (
    pathlib.Path(__file__).resolve().parent
    / "semantic_persistence"
    / "mllm_client.py"
)
spec = importlib.util.spec_from_file_location("mllm_client_under_test", module_path)
mllm_client_under_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mllm_client_under_test)
MLLMClient = mllm_client_under_test.MLLMClient


class MLLMClientViewIdRemapTest(unittest.TestCase):
    def test_remaps_sampled_view_id_to_original_horizon_index(self):
        payload = {"target": {"found": True, "confidence": 0.9, "view_id": 2}}

        remapped = MLLMClient._remap_target_view_id(payload, [0, 8, 16, 24])

        self.assertEqual(remapped["target"]["view_id"], 16)

    def test_keeps_missing_detection_view_id_negative(self):
        payload = {"target": {"found": False, "confidence": 0.0, "view_id": -1}}

        remapped = MLLMClient._remap_target_view_id(payload, [0, 8, 16, 24])

        self.assertEqual(remapped["target"]["view_id"], -1)


if __name__ == "__main__":
    unittest.main()
