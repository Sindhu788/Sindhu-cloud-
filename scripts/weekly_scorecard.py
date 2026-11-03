"""Weekly scorecard (read-only). Usage:  python scripts/weekly_scorecard.py [output.md]

Uses the database selected by the environment (SINDHU_DATA_DIR -> local sindhu.db, or DATABASE_URL -> Cloud Postgres).
Prints the scorecard and optionally writes it to a markdown file. Never modifies anything.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_engine import storage  # noqa: E402
from paper_trading import scorecard  # noqa: E402


def main():
    with storage.get_conn() as conn:
        trades = scorecard.load_trades(conn)
    text = scorecard.render_markdown(scorecard.build(trades))
    print(text)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()
