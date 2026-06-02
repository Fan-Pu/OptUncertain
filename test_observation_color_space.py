import importlib
import io
import sys
import types

import numpy as np
from PIL import Image


def _install_import_stubs(monkeypatch):
    cv2_stub = types.ModuleType("cv2")
    cv2_stub.COLOR_BGR2RGB = 1
    cv2_stub.COLOR_RGB2BGR = 2
    cv2_stub.FONT_HERSHEY_SIMPLEX = 0

    def cvt_color(image, code):
        if code in (cv2_stub.COLOR_BGR2RGB, cv2_stub.COLOR_RGB2BGR):
            return np.asarray(image)[..., ::-1].copy()
        raise ValueError("unsupported cvtColor code")

    cv2_stub.cvtColor = cvt_color
    cv2_stub.getTextSize = lambda text, font, font_scale, thickness: ((0, 0), 0)
    cv2_stub.putText = lambda *args, **kwargs: None
    cv2_stub.rectangle = lambda *args, **kwargs: None
    cv2_stub.line = lambda *args, **kwargs: None
    cv2_stub.imshow = lambda *args, **kwargs: None
    cv2_stub.waitKey = lambda *args, **kwargs: None
    cv2_stub.namedWindow = lambda *args, **kwargs: None

    mattersim_stub = types.ModuleType("MatterSim")
    mattersim_stub.Simulator = object

    openai_stub = types.ModuleType("openai")
    openai_stub.APITimeoutError = RuntimeError
    openai_stub.BadRequestError = RuntimeError
    openai_stub.OpenAI = object

    monkeypatch.setitem(sys.modules, "cv2", cv2_stub)
    monkeypatch.setitem(sys.modules, "MatterSim", mattersim_stub)
    monkeypatch.setitem(sys.modules, "openai", openai_stub)
    sys.modules.pop("Helper", None)
    sys.modules.pop("semantic_persistence.mllm_client", None)


def test_simulator_bgr_frame_converts_to_rgb(monkeypatch):
    _install_import_stubs(monkeypatch)
    Helper = importlib.import_module("Helper")

    simulator_bgr_red = np.array([[[0, 0, 255]]], dtype=np.uint8)

    rgb = Helper.simulator_frame_to_rgb(simulator_bgr_red)

    assert rgb[0, 0].tolist() == [255, 0, 0]


def test_panorama_preserves_rgb_after_simulator_conversion(monkeypatch):
    _install_import_stubs(monkeypatch)
    Helper = importlib.import_module("Helper")
    monkeypatch.setattr(Helper, "DELTA_HEADING_RAD", Helper.HFOV)

    simulator_bgr_red = np.full((2, 4, 3), [0, 0, 255], dtype=np.uint8)
    simulator_bgr_blue = np.full((2, 4, 3), [255, 0, 0], dtype=np.uint8)
    frames = [
        Helper.simulator_frame_to_rgb(simulator_bgr_red),
        Helper.simulator_frame_to_rgb(simulator_bgr_blue),
    ]

    panorama = Helper.build_truncated_panorama(frames)

    assert panorama[0, 0].tolist() == [255, 0, 0]
    assert panorama[0, 4].tolist() == [0, 0, 255]


def test_resized_panorama_jpeg_keeps_rgb_red_dominant(monkeypatch):
    _install_import_stubs(monkeypatch)
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")

    rgb_red = np.zeros((4, 4, 3), dtype=np.uint8)
    rgb_red[:, :, 0] = 255

    image_bytes = mllm_client.MLLMClient._resize_panorama_array(
        rgb_red,
        max_width=1280,
        quality=100,
    )
    decoded = np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))

    assert decoded[:, :, 0].mean() > 250
    assert decoded[:, :, 2].mean() < 5
