"""Master plan V2 R3 (P11): load ccxt WITHOUT importing all ~100 exchange classes.

`import ccxt` runs ccxt/__init__.py, which imports every exchange module (measured: +56 MiB RSS; okx alone: +21 MiB). The Cloud
service only ever talks to okx (binance/bybit are geo-blocked there). install() builds the `ccxt` package module from the real
__init__.py source with the per-exchange import lines left out, and adds a module-level __getattr__ that imports an exchange the
first time it is used (`ccxt.okx`, `getattr(ccxt, "kraken")`). Everything else (__version__, Exchange, errors, decimal_to_precision,
the `exchanges` list) is the real code, unchanged. Any problem -> the normal full import. Off with SINDHU_LAZY_CCXT=0."""
import importlib
import importlib.util
import os
import re
import sys
import types

_EXCHANGE_IMPORT = re.compile(r"^from ccxt\.(?!base\b)([a-z0-9_]+) import ([a-z0-9_]+)\s*(#.*)?$", re.M)


def install():
    if "ccxt" in sys.modules:
        return False
    if (os.environ.get("SINDHU_LAZY_CCXT") or "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    try:
        spec = importlib.util.find_spec("ccxt")
        if spec is None or not spec.origin or not spec.submodule_search_locations:
            return False
        with open(spec.origin, encoding="utf-8") as f:
            src = f.read()
        names = {m.group(1) for m in _EXCHANGE_IMPORT.finditer(src)}
        if len(names) < 10:              # layout not recognised: do not guess
            return False
        lean = _EXCHANGE_IMPORT.sub("", src)
        mod = types.ModuleType("ccxt", "CCXT (lazy exchange loading, master plan V2 R3)")
        mod.__file__ = spec.origin
        mod.__path__ = list(spec.submodule_search_locations)
        mod.__spec__ = spec
        mod.__package__ = "ccxt"

        def __getattr__(name, _names=names, _mod=mod):
            if name in _names:
                sub = importlib.import_module(f"ccxt.{name}")
                cls = getattr(sub, name)
                setattr(_mod, name, cls)
                return cls
            raise AttributeError(f"module 'ccxt' has no attribute {name!r}")

        mod.__getattr__ = __getattr__
        mod.__lazy_exchanges__ = frozenset(names)
        sys.modules["ccxt"] = mod
        try:
            exec(compile(lean, spec.origin, "exec"), mod.__dict__)
        except Exception:
            for k in [k for k in sys.modules if k == "ccxt" or k.startswith("ccxt.")]:
                del sys.modules[k]
            return False
        return True
    except Exception:
        sys.modules.pop("ccxt", None)
        return False
