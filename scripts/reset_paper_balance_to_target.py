"""Reset every paper strategy book to a target balance (default 100), archiving trades.

Dry-run by default. Refuses Postgres/Cloud unless --allow-cloud is given.
Take a backup of the database FIRST (copy data/database/sindhu.db).

  python scripts/reset_paper_balance_to_target.py                # preview only
  python scripts/reset_paper_balance_to_target.py --apply        # perform the reset
  python scripts/reset_paper_balance_to_target.py --target 100 --apply

Point it at a copy with SINDHU_DATA_DIR=<folder containing database/sindhu.db and config/>.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paper_trading import balance_reset  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=float, default=100.0)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-cloud", action="store_true")
    args = parser.parse_args()
    result = balance_reset.reset_to_target(args.target, apply=args.apply, allow_cloud=args.allow_cloud)
    print(json.dumps(result, indent=2, default=str))
    return 0 if (not args.apply or result.get("ok")) else 1


if __name__ == "__main__":
    sys.exit(main())
