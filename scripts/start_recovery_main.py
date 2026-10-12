"""Safe local Main launcher; isolated QA uses normal setup/login middleware."""
import argparse
import os
import platform
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--isolated-qa", action="store_true")
    parser.add_argument("--data-dir")
    parser.add_argument("--port", type=int, default=8420)
    args=parser.parse_args()
    data=Path(args.data_dir).resolve() if args.data_dir else ROOT/"data/recovery_main"
    if args.isolated_qa:
        qa_parent=(ROOT/"data/functional_qa").resolve()
        if not data.is_relative_to(qa_parent) or data==qa_parent or args.port==8420:
            raise ValueError("Isolated QA requires a dedicated functional_qa child and a non-Main port")
    elif data!=(ROOT/"data/recovery_main").resolve() or args.port!=8420:
        raise ValueError("Nonstandard data/port requires explicit isolated QA mode")
    os.environ.update(DATABASE_URL="",SINDHU_DATA_DIR=str(data),
                      SINDHU_SAFE_START="1",SINDHU_TELEGRAM_DRY_RUN="1",
                      SINDHU_PUBLIC_SIGNAL_OWNER="disabled",SINDHU_OPEN_BROWSER="0",
                      SINDHU_CLOUD_MODE="0",OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1")
    if os.name=="nt":
        platform._wmi_query=lambda *a,**k: (_ for _ in ()).throw(OSError("WMI unavailable"))
    from data_engine import storage
    storage.init_db()
    if not args.isolated_qa:
        from sindhu_web.local_account_recovery import restore_unconfigured_account
        restore_unconfigured_account(Path("D:/sindhu/data/config/auth_credentials.json"),
                                     data/"config/auth_credentials.json")
    from sindhu_web.server import run
    run(host="127.0.0.1",port=args.port,open_browser=False)


if __name__=="__main__":main()
