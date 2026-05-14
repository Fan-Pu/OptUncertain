__all__ = ["RollingHorizonOptimizer"]


def __getattr__(name):
    if name == "RollingHorizonOptimizer":
        from .optimizer import RollingHorizonOptimizer

        return RollingHorizonOptimizer
    raise AttributeError(name)

