# DB LATENCY FINDINGS (master plan V2 R5, N2)

Question: is the database round trip (Render in Oregon, Neon in Ohio) the main cost of a Cloud scan, and would the Ohio region help?
**Answer: VERIFIED.** On the scan thread alone, the database is 56-62 % of every warm scan, and almost all of it is network round trips.

## Measurements (Cloud, after gate G1, commit ab38f58; instance k72mz; 6 Nov 2026)
`[db-latency]` probe: 20 x `SELECT 1` on one pooled connection, from the Cloud instance:

| Probe | p50 | p95 | min | max |
|---|---|---|---|---|
| 07:40:54 UTC | 47.2 ms | 94.2 ms | 47.1 ms | 94.2 ms |

`[scan-db]` = the scan thread's own statements, commits and connection checkouts (other threads excluded); 10 warm scans:

| Scan finished (UTC) | Scan | Statements (s) | Commits (s) | DB share | RSS |
|---|---|---|---|---|---|
| 11:59 | 1,808 s | 7,062 (728) | 6,868 (340) | 59 % | 385 MB |
| 12:31 | 1,824 s | 6,644 (738) | 6,497 (343) | 59 % | 384 MB |
| 13:02 | 1,825 s | 6,971 (727) | 6,798 (338) | 58 % | 388 MB |
| 13:35 | 1,906 s | 6,972 (772) | 6,839 (359) | 59 % | 392 MB |
| 14:10 | 2,031 s | 7,638 (835) | 7,458 (387) | 60 % | 359 MB |
| 14:43 | 1,950 s | 7,174 (780) | 7,025 (362) | 59 % | 363 MB |
| 15:21 | 2,179 s | 8,334 (923) | 8,017 (418) | 62 % | 367 MB |
| 15:57 | 2,098 s | 7,557 (848) | 7,366 (391) | 59 % | 366 MB |
| 16:33 | 2,106 s | 7,327 (826) | 7,162 (383) | 58 % | 369 MB |
| 17:08 | 2,023 s | 7,041 (774) | 6,886 (356) | 56 % | 371 MB |

Per statement: about **103-111 ms** = about 2 round trips (psycopg2 sends `BEGIN` before the first statement of a transaction, then the
statement). Per commit: about **49-52 ms** = 1 round trip. The query work itself is small: `SELECT 1` costs the same 47 ms.

## The single biggest item
`SELECT value_json FROM cloud_settings WHERE key=?` ran **3,647-3,907 times per scan (385-410 s)**, plus a commit each (~185 s).
These are settings reads (paper-trading and Telegram settings blobs) repeated for every strategy and coin.

## Ohio idea, with numbers
If the service ran next to the database (round trip ~1-2 ms instead of 47 ms; NOT measured, a typical same-region value), the
~1,100 s of database time per warm scan would drop to roughly 25-50 s, and a warm scan from ~2,000 s to roughly 900-1,000 s.
**VERIFIED as the main cost; the exact gain is an estimate.** Moving region = a new Render service (new URL, pinger, Telegram polling):
not done in this plan (owner decision, rule 8).

## Fixes that do not move regions
| Fix | Effect (expected) | Status |
|---|---|---|
| Cache `get_cloud_setting` for 10 s in memory; this process's saves update it at once | about -3,700 statements and -3,700 commits per scan, roughly -570 s (-28 %) | **done** (V2 R5, `data_engine/storage.py`, tests `tests/test_db_round_trip_fixes.py`); to be measured after G2 |
| Refetch deferrals (R2) no longer counted as scan errors; budget 8 after two unlimited scans | scans report `complete` again; coins left over after a cut first download load within a scan or two | **done** (G1 logs showed 6-14 "errors" per scan that were all `RefetchDeferred`) |
| Read-only statements in autocommit (no BEGIN/COMMIT round trips) | each read 1 round trip instead of 3 | not done: needs every caller audited for read-then-write in one transaction |
| One transaction per coin for writes | ~1 commit per coin instead of ~140 | not done: changes failure behaviour (one error would roll back a coin's writes) |
| Cache per-scan reads of strategy config / pause state / lessons (next 4 items in the top list, ~30-60 s each) | -150 to -200 s | candidate for a later step |
