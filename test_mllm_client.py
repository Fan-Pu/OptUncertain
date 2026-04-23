import importlib.util
import pathlib
import sys
import types
import unittest
import numpy as np


helper_stub = types.ModuleType("Helper")
helper_stub.DELTA_HEADING_RAD = 0.1
helper_stub.viewpoint_index_by_vp_label = {"vp-0": 0}
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


class _FakeGraph:
    def get_MLLM_summary(self):
        return {
            "node_indices": [7, 44],
            "node_grounding_list": [1, 0],
            "node_existence_list": [1.0, 0.9],
            "node_target_list": [0.4, 0.6],
            "node_type_list": [1, 0],
            "node_assign_dict": {44: [16, 21]},
            "arc_indices": [(7, 44)],
            "arc_grounding_list": [0],
            "arc_existence_list": [0.8],
            "arc_distance_list": [1.2],
        }


class MLLMClientPromptTest(unittest.TestCase):
    def test_build_instruction_uses_strip_index_schema(self):
        client = MLLMClient.__new__(MLLMClient)

        system_message, user_message = client._build_instruction(
            num_panorama_images=2,
            num_panorama_strips=48,
            target_object="chair",
            graph=_FakeGraph(),
            current_vp_node_id=7,
            neighbor_vp_node_ids=[16, 21],
            neighbor_vp_distances_list=[1.1, 2.2],
        )

        self.assertIn('"strip_index": -1', system_message)
        self.assertNotIn("view_id", system_message)
        self.assertIn('"strip_index": 0', user_message)
        self.assertNotIn("view_id", user_message)
        self.assertIn("Image 0 is the raw RGB panorama.", user_message)
        self.assertIn("Image 1 is the annotated panorama", user_message)


class MLLMClientSamplingTest(unittest.TestCase):
    def test_select_evenly_spaced_indices_starts_at_first_frame(self):
        self.assertEqual(
            MLLMClient._select_evenly_spaced_indices(12, 5),
            [0, 2, 5, 7, 10],
        )

    def test_propose_semantic_nodes_uses_raw_and_annotated_panoramas(self):
        client = MLLMClient.__new__(MLLMClient)
        client.save_debug_images = False
        client._build_instruction = lambda **kwargs: ("system", "user")
        client._image_to_data_url = lambda image: "data:image/png;base64,test"
        client._request_completion = (
            lambda messages: """
            {
                "current_region_node": {"label": "living room", "id": 44, "target_prob": 0.4},
                "new_visible_region_nodes": [],
                "new_invisible_region_nodes": [],
                "viewpoint_target_probs": [],
                "new_arcs": [],
                "target": {"found": true, "confidence": 0.9, "strip_index": 7},
                "viewpoint_node_assigns": [],
                "region_merges": []
            }
            """
        )

        rgb_markers = []
        original_fromarray = mllm_client_under_test.Image.fromarray

        def _capture_fromarray(image, mode=None):
            rgb_markers.append(int(image.reshape(-1)[0]))
            return types.SimpleNamespace(save=lambda path: None)

        mllm_client_under_test.Image.fromarray = _capture_fromarray

        try:
            raw_panorama = 11 * np.ones((2, 3, 3), dtype=np.uint8)
            annotated_panorama = 22 * np.ones((2, 3, 3), dtype=np.uint8)

            payload = client.propose_semantic_nodes(
                observation_images=[raw_panorama],
                annotated_observation_images=[annotated_panorama],
                depth_images=[np.zeros((1, 1), dtype=np.uint16) for _ in range(48)],
                target_object="chair",
                viewpoint_context={
                    "current_viewpoint_index": 7,
                    "visible_viewpoints": [],
                    "frame_visible_viewpoint_indices": [[] for _ in range(48)],
                },
                graph=None,
            )
        finally:
            mllm_client_under_test.Image.fromarray = original_fromarray

        self.assertEqual(rgb_markers, [11, 22])
        self.assertEqual(payload["target"]["strip_index"], 7)


if __name__ == "__main__":
    unittest.main()
