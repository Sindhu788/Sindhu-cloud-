import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("bce", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "backup_cloud_export.py")
bce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bce)
COLS = ["key", "value_json", "updated_at"]


def test_secret_like_settings_are_redacted_but_keep_their_row_and_length():
    for key in ("api_token", "strategy_sync_secret", "Some_Password", "bot_token"):
        out = bce.redact_row("cloud_settings", COLS, (key, "SUPERSECRETVALUE123", "t"))
        assert "SUPERSECRET" not in str(out) and out[1] == "<redacted:19 chars>" and out[0] == key and out[2] == "t"


def test_non_secret_settings_and_other_tables_are_untouched():
    row = ("paper_trading_settings", '{"opposite_signal_policy": "block"}', "t")
    assert bce.redact_row("cloud_settings", COLS, row) == row
    other = ("api_token", "keep", "t")
    assert bce.redact_row("paper_positions", COLS, other) == other


def test_redaction_keeps_the_tuple_shape_so_the_row_count_check_still_works():
    out = bce.redact_row("cloud_settings", COLS, ("api_token", "x", "t"))
    assert isinstance(out, tuple) and len(out) == 3
