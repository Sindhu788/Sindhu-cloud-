"""Print the go-live gate table (read-only). Uses the database selected by the environment
(SINDHU_DATA_DIR -> local sindhu.db, or DATABASE_URL -> Cloud Postgres).  python scripts/go_live_status.py [out.md]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_engine import storage  # noqa: E402
from paper_trading import go_live  # noqa: E402

with storage.get_conn() as conn:
    text = go_live.render_markdown(go_live.evaluate(conn))
print(text)
if len(sys.argv) > 1:
    open(sys.argv[1], "w", encoding="utf-8").write(text + "\n")
