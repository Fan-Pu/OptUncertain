import importlib.util
import pathlib
import sys
import types
import unittest
import numpy as np


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


class MLLMClientSamplingTest(unittest.TestCase):
    def test_select_evenly_spaced_indices_starts_at_first_frame(self):
        self.assertEqual(
            MLLMClient._select_evenly_spaced_indices(12, 5),
            [0, 2, 5, 8, 11],
        )

    def test_propose_semantic_nodes_samples_aligned_rgb_and_depth_frames(self):
        client = MLLMClient.__new__(MLLMClient)
        client.save_debug_images = False
        client._build_instruction = lambda **kwargs: ("system", "user")
        client._image_to_data_url = lambda image: "data:image/png;base64,test"

        captured_index_map = {}

        def _capture_remap(payload, index_map):
            captured_index_map["value"] = list(index_map)
            return payload

        client._remap_target_view_id = _capture_remap

        rgb_markers = []
        depth_markers = []
        original_fromarray = mllm_client_under_test.Image.fromarray

        def _capture_fromarray(image, mode=None):
            marker = int(image.reshape(-1)[0])
            if mode == "I;16":
                depth_markers.append(marker)
            else:
                rgb_markers.append(marker)
            return types.SimpleNamespace(save=lambda path: None)

        mllm_client_under_test.Image.fromarray = _capture_fromarray

        try:
            observation_images = [
                (index * np.ones((1, 1, 3), dtype=np.uint8)) for index in range(12)
            ]
            depth_images = [
                (index * np.ones((1, 1), dtype=np.uint16)) for index in range(12)
            ]

            client.propose_semantic_nodes(
                observation_images=observation_images,
                depth_images=depth_images,
                target_object="chair",
                viewpoint_context={
                    "current_viewpoint_index": 7,
                    "visible_viewpoints": [],
                },
                graph=None,
            )
        finally:
            mllm_client_under_test.Image.fromarray = original_fromarray

        self.assertEqual(captured_index_map["value"], [0, 2, 5, 8, 11])
        self.assertEqual(rgb_markers, [0, 2, 5, 8, 11])
        self.assertEqual(depth_markers, [0, 2, 5, 8, 11])


if __name__ == "__main__":
    unittest.main()
