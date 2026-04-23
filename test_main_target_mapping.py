import importlib.util
import pathlib
import sys
import types
import unittest


debugpy_stub = types.ModuleType("debugpy")
debugpy_stub.breakpoint = lambda: None
debugpy_stub.listen = lambda *args, **kwargs: None
debugpy_stub.wait_for_client = lambda: None
sys.modules.setdefault("debugpy", debugpy_stub)

helper_stub = types.ModuleType("Helper")
helper_stub.HFOV = 1.0
helper_stub.viewpoint_index_by_vp_label = {}
sys.modules.setdefault("Helper", helper_stub)

optimization_model_stub = types.ModuleType("optimization_model")
optimization_model_stub.RollingHorizonOptimizer = object
sys.modules.setdefault("optimization_model", optimization_model_stub)

semantic_pkg = types.ModuleType("semantic_persistence")
hypothesis_graph_stub = types.ModuleType("semantic_persistence.hypothesis_graph")
hypothesis_graph_stub.HypothesisGraph = object
mllm_client_stub = types.ModuleType("semantic_persistence.mllm_client")
mllm_client_stub.MLLMClient = object
semantic_pkg.hypothesis_graph = hypothesis_graph_stub
semantic_pkg.mllm_client = mllm_client_stub
sys.modules.setdefault("semantic_persistence", semantic_pkg)
sys.modules.setdefault("semantic_persistence.hypothesis_graph", hypothesis_graph_stub)
sys.modules.setdefault("semantic_persistence.mllm_client", mllm_client_stub)

module_path = pathlib.Path(__file__).resolve().parent / "main.py"
spec = importlib.util.spec_from_file_location("main_under_test", module_path)
main_under_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_under_test)


class MainTargetMappingTest(unittest.TestCase):
    def test_select_target_observation_maps_strip_index_to_frame_heading_and_depth(self):
        headings = [0.1, 0.2, 0.3]
        rgb_frames = ["frame-0", "frame-1", "frame-2"]
        depth_frames = ["depth-0", "depth-1", "depth-2"]

        target_heading, target_rgb_image, target_depth_image = (
            main_under_test.select_target_observation(
                {"found": True, "strip_index": 1},
                headings,
                rgb_frames,
                depth_frames,
            )
        )

        self.assertEqual(target_heading, 0.2)
        self.assertEqual(target_rgb_image, "frame-1")
        self.assertEqual(target_depth_image, "depth-1")


if __name__ == "__main__":
    unittest.main()
