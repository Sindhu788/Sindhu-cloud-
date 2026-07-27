from fastapi import APIRouter

from data_engine import storage, config
from data_engine.symbols import pick_top_symbols
from data_engine.downloader import download_all
from data_engine.exchanges.registry import get_exchange_client
from data_engine import data_quality_score
from sindhu_web import cache
from sindhu_web.jobs import job_manager

router = APIRouter()


def _default_exchange():
    cfg = config.load_or_seed("exchanges.json", config.DEFAULTS["exchanges.json"])
    return cfg["default"]


@router.get("/api/data")
def get_data_overview():
    exchange = _default_exchange()
    symbols = storage.load_symbols(exchange)

    def _compute():
        rows = []
        with storage.get_conn() as conn:
            for symbol in symbols:
                r = conn.execute(
                    "SELECT COUNT(*), MIN(open_time), MAX(open_time) FROM klines_1m WHERE exchange=? AND symbol=?",
                    (exchange, symbol),
                ).fetchone()
                last_open_time, status = storage.get_progress(exchange, symbol)
                rows.append({
                    "symbol": symbol, "candles": r[0],
                    "start": r[1], "end": r[2], "status": status,
                })
        return rows

    rows = cache.cached(f"data_overview_{exchange}", 60, _compute)
    missing = [r["symbol"] for r in rows if r["candles"] == 0]

    return {
        "exchange": exchange,
        "coins": rows,
        "timeframes": config.SUPPORTED_INTERVALS,
        "missing_data": missing,
        "total_coins": len(symbols),
        "database_size_bytes": storage.db_file_size_bytes(),
    }


@router.get("/api/data/quality")
def get_data_quality():
    """Data Quality Engine (B3): a live per-symbol health score, kept
    entirely separate from strategy performance -- cached 5min (a 50-symbol
    scan) since this is a slow-changing signal, not something that needs
    second-by-second freshness."""
    exchange = _default_exchange()

    def _compute():
        return data_quality_score.score_all_tracked_symbols(exchange)
    return cache.cached(f"data_quality_{exchange}", 300, _compute)


@router.post("/api/data/download")
def start_download():
    """Kicks off (or resumes) the Phase 1 download pass as a background
    job -- reuses the exact same data_engine.downloader as the desktop app
    and CLI, never re-downloading candles that are already stored."""
    import uuid
    from data_engine.control import DownloadControl

    exchange = _default_exchange()
    control = DownloadControl()
    job_id = uuid.uuid4().hex[:12]

    def _target():
        client = get_exchange_client(exchange)
        storage.init_db()
        symbols = storage.load_symbols(exchange)
        if not symbols:
            symbols = pick_top_symbols(client, config.NUM_COINS, config.QUOTE_ASSET)

        def _progress_cb(i, total, symbol):
            job_manager.update_progress(job_id, done=i, total=total, current_coin=symbol)

        log_fn = job_manager.make_log_fn(job_id)
        download_all(client, symbols, log=log_fn, control=control, progress_cb=_progress_cb)
        cache.invalidate(f"data_overview_{exchange}")
        cache.invalidate("total_candles")
        return {"exchange": exchange, "symbols": len(symbols)}

    job_manager.create_job("download", _target, control=control, job_id=job_id)
    return {"job_id": job_id}
