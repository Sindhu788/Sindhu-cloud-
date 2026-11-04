"""SINDHU data platform (Day 5): a clean, verified, protected 1-minute candle dataset for LOCAL backtesting.

Candles are never written to Postgres and Cloud never needs these files. The dataset lives OUTSIDE the git repository
(default D:\\sindhu_data, override with SINDHU_DATA_ROOT) and is never deleted, moved or overwritten by any code here: files are written
under a temporary name and renamed atomically, finished files are marked read-only, and nothing is ever replaced.
"""
