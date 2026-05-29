import importlib.util
import sys
import types


def _install_openai_stub():
    module = types.ModuleType("openai")

    class FakeOpenAI:
        def __init__(self, *args, **kwargs):
            pass

    class FakeAPITimeoutError(Exception):
        pass

    module.APITimeoutError = FakeAPITimeoutError
    module.BadRequestError = Exception
    module.OpenAI = FakeOpenAI
    sys.modules["openai"] = module


def _install_cv2_stub():
    module = types.ModuleType("cv2")
    module.FONT_HERSHEY_SIMPLEX = 0
    sys.modules["cv2"] = module


def _install_matter_sim_stub():
    module = types.ModuleType("MatterSim")

    class FakeSimulator:
        pass

    module.Simulator = FakeSimulator
    sys.modules["MatterSim"] = module


if importlib.util.find_spec("openai") is None:
    _install_openai_stub()

if importlib.util.find_spec("cv2") is None:
    _install_cv2_stub()

if importlib.util.find_spec("MatterSim") is None:
    _install_matter_sim_stub()
