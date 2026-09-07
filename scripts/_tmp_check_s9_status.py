import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_engine import storage

with storage.get_conn() as conn:
    rows = conn.execute(
        "SELECT batch_id, strategy_name, created_at, status FROM backtest_batches "
        "WHERE strategy_name LIKE '%Ichimoku%Indicator%' ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    for r in rows:
        print(r)
