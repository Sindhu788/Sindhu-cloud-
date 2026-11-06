"""Master plan V2 R3 (P11): ccxt is loaded without importing every exchange class; behaviour is unchanged."""
import subprocess
import sys
import textwrap

ROOT = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))


def _run(code, env_extra=None):
    import os
    env = dict(os.environ, **(env_extra or {}))
    out = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def test_lazy_install_loads_only_the_exchanges_that_are_used():
    out = _run("""
        import sys
        from data_engine.exchanges import ccxt_client
        import ccxt
        loaded = [m for m in sys.modules if m.startswith('ccxt.') and m.count('.') == 1 and not m.startswith(('ccxt.base', 'ccxt.static_dependencies', 'ccxt.abstract'))]
        assert getattr(ccxt, '__lazy_exchanges__', None), 'lazy loader not installed'
        assert len(ccxt.exchanges) > 50
        e = ccxt.okx({'enableRateLimit': True})
        loaded2 = [m for m in sys.modules if m.startswith('ccxt.') and m.count('.') == 1 and not m.startswith(('ccxt.base', 'ccxt.static_dependencies', 'ccxt.abstract'))]
        print(len(loaded), len(loaded2), type(e).__name__, issubclass(ccxt.RateLimitExceeded, ccxt.NetworkError))
    """)
    before, after, name, sub = out.split()
    assert int(before) <= 2 and int(after) <= 3 and name == "okx" and sub == "True"


def test_switch_off_gives_the_normal_full_import():
    out = _run("""
        import sys
        from data_engine.exchanges import ccxt_client
        import ccxt
        print(hasattr(ccxt, '__lazy_exchanges__'), 'ccxt.kraken' in sys.modules)
    """, {"SINDHU_LAZY_CCXT": "0"})
    assert out == "False True"


def test_unknown_attribute_still_raises():
    out = _run("""
        from data_engine.exchanges import ccxt_client
        import ccxt
        try:
            ccxt.not_an_exchange
            print('no')
        except AttributeError:
            print('ok')
    """)
    assert out == "ok"
