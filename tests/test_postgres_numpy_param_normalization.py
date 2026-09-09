"""Urgent bug fix, 2026-09-09: confirmed live in Render's cloud logs --
a real trade decision for CC/USDT crashed with InvalidSchemaName('schema
"np" does not exist') because a numpy.float64 (from an ATR/indicator
stop-loss/take-profit calculation) reached a paper_positions INSERT's
parameter tuple. psycopg2 has no adapter for numpy scalar types and
fell back to str()'ing it -- producing the literal text
"np.float64(0.123)" in the query, which Postgres tried to parse as a
schema-qualified function call. data_engine.db_backend._PGConnection now
normalizes every numpy-scalar-like parameter (anything with a numpy-
style .item() method) to its native Python equivalent before it ever
reaches psycopg2.
"""
import numpy as np
from unittest.mock import MagicMock

from data_engine import db_backend


def test_normalize_param_converts_numpy_scalars_to_native_python():
    assert type(db_backend._normalize_param(np.float64(0.1206603))) is float
    assert db_backend._normalize_param(np.float64(0.1206603)) == 0.1206603
    assert type(db_backend._normalize_param(np.int64(42))) is int
    assert db_backend._normalize_param(np.int64(42)) == 42
    assert type(db_backend._normalize_param(np.bool_(True))) is bool


def test_normalize_param_leaves_native_python_types_untouched():
    assert db_backend._normalize_param(1.5) == 1.5
    assert type(db_backend._normalize_param(1.5)) is float
    assert db_backend._normalize_param("okx") == "okx"
    assert db_backend._normalize_param(None) is None
    assert db_backend._normalize_param(True) is True


def test_normalize_params_handles_a_mixed_tuple():
    raw = ("okx", "CC/USDT", "long", np.float64(0.1206603), np.float64(0.1178651), np.float64(0.19))
    normalized = db_backend._normalize_params(raw)
    assert normalized == ("okx", "CC/USDT", "long", 0.1206603, 0.1178651, 0.19)
    assert all(type(v) in (str, float) for v in normalized)


def test_pgconnection_execute_normalizes_numpy_params_before_psycopg2():
    raw = MagicMock()
    cur = MagicMock()
    raw.cursor.return_value = cur

    conn = db_backend._PGConnection(raw)
    conn.execute("INSERT INTO t (a, b) VALUES (?, ?)", (np.float64(0.5), "x"))

    called_sql, called_params = cur.execute.call_args[0]
    assert called_params == (0.5, "x")
    assert type(called_params[0]) is float


def test_pgconnection_executemany_normalizes_numpy_params():
    raw = MagicMock()
    cur = MagicMock()
    raw.cursor.return_value = cur

    conn = db_backend._PGConnection(raw)
    conn.executemany("INSERT INTO t (a) VALUES (?)", [(np.float64(1.1),), (np.int64(2),)])

    called_sql, called_params = cur.executemany.call_args[0]
    assert called_params == [(1.1,), (2,)]
    assert all(type(p[0]) in (float, int) for p in called_params)
