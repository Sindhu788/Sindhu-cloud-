"""Day 7 Step 8: largest Python allocations (tracemalloc) at the END of a local profile scan. Usage: python tools/mem_top.py [profile_scan args]
Local sandbox only (the mock exchange of scripts/profile_scan.py)."""
import os, runpy, sys, tracemalloc
tracemalloc.start(1)
sys.argv = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "profile_scan.py")] + sys.argv[1:]
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit:
    pass
cur, peak = tracemalloc.get_traced_memory()
print(f"TRACEMALLOC current {cur / 1e6:.1f} MB, peak {peak / 1e6:.1f} MB")
for st in tracemalloc.take_snapshot().statistics("lineno")[:14]:
    fr = st.traceback[0]
    print(f"TOP {st.size / 1e6:7.2f} MB  {st.count:8d} blocks  {os.path.relpath(fr.filename) if os.path.isabs(fr.filename) else fr.filename}:{fr.lineno}")
