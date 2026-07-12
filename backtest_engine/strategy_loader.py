import importlib.util
import inspect
import os

from strategies.base import Strategy

_STRATEGIES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "strategies")
_SKIP_FILES = {"__init__.py", "base.py"}


def discover_strategies():
    """Scan strategies/*.py for Strategy subclasses and return {name: class}.
    Each strategy file is saved locally under strategies/ -- this just finds
    what's there; it never generates strategy logic itself."""
    found = {}
    if not os.path.isdir(_STRATEGIES_DIR):
        return found

    for filename in sorted(os.listdir(_STRATEGIES_DIR)):
        if not filename.endswith(".py") or filename in _SKIP_FILES:
            continue

        module_name = f"strategies._loaded_{filename[:-3]}"
        file_path = os.path.join(_STRATEGIES_DIR, filename)
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Strategy) and obj is not Strategy and obj.__module__ == module_name:
                found[obj.name] = obj

    return found


def get_strategy(name):
    strategies = discover_strategies()
    if name not in strategies:
        raise ValueError(f"Unknown strategy {name!r}. Available: {sorted(strategies)}")
    return strategies[name]()
