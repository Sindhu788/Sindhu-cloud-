# Security review (Day 4, 4 Nov 2026) - passive, our own service only

Method: dependency scan (`pip-audit`), a handful of single requests to https://sindhu-cloud-1.onrender.com (headers, one CORS preflight, unauthenticated calls, one unknown path, one query-string quote), and code reading of `sindhu_web/security.py`, `sindhu_web/api/auth.py`, `cloud_runtime/app.py`. No exploitation, no fuzzing, no brute force, no load. Total requests to Cloud for this review: 14.

| # | Finding | Severity | Evidence | Status |
|---|---|---|---|---|
| 1 | Dependency vulnerabilities in `requirements-cloud.txt` | none found | `pip-audit -r requirements-cloud.txt --no-deps`: "No known vulnerabilities found" (pins are fully versioned; transitive dependencies were not resolved: NOT VERIFIED for them) | - |
| 2 | No login throttling: unlimited password guesses on `/api/auth/login` | **medium** | code: handler only checked the password | **FIXED**: 8 failures per client address per 10 min, 40 overall per 10 min, then HTTP 429 until the window passes (expires by itself, so it cannot lock the owner out for good); tests `test_security_hardening.py` |
| 3 | Session cookie had no `Secure` flag | low-medium | code: `set_cookie(httponly=True, samesite="lax")` | **FIXED**: Secure when `X-Forwarded-Proto: https` (Render/Cloudflare); HttpOnly and SameSite=Lax kept; test |
| 4 | Missing hardening headers (nosniff, frame denial, referrer policy) | low | response headers of `/health` had none | **FIXED**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, `Permissions-Policy` on every response; test. A Content-Security-Policy was NOT added (dashboard uses inline scripts; would break it) - listed below |
| 5 | CORS allows any origin (`allow_origins=["*"]`) | low | `cloud_runtime/app.py` | not changed. A foreign-origin preflight to a settings endpoint returned 401 without any `Access-Control-Allow-*` header (the login gate answers first), and cookies are not sent cross-site (SameSite=Lax), so there is no demonstrated cross-site read. Recommend restricting to the dashboard origin (owner/next run). |
| 6 | State-changing endpoints require login + token | ok | unauthenticated `POST /api/ops/test-owner-alert` -> 401 "login required"; `GET /api/paper-trading/telegram/settings` -> 401; middleware: session gate for every non-exempt path, plus `X-Sindhu-Token` for non-GET | pass |
| 7 | Public endpoints | ok | only `/health` (status, version, commit, engine flag, mode flags, start time: no secrets), `/login`, `/static/*` and the login API; every `/api/*` path answers 401 without a session | pass |
| 8 | Error messages leak internals | ok | unknown API path and a path with a quote both returned `{"detail":"login required"}` 401; the global exception handler returns `{"detail":"internal error"}` and logs the real error server-side | pass |
| 9 | Interactive API docs exposed | ok | `/docs`, `/openapi.json`, `/redoc` answer 307 (redirect to login) | pass |
| 10 | Secrets in logs | no evidence | Render log search for token/password patterns found none in the lines read (about 600 lines over the run); the new exchange-retry log prints only public exchange error text | partial (NOT a full log audit) |
| 11 | Rate limiting elsewhere | open, low | no general request rate limit; the free instance (0.15 CPU) can be slowed by many requests; Cloudflare is in front but its settings are not visible from here | owner/next run |
| 12 | Content-Security-Policy | open, low | see 4 | next run: add after replacing inline scripts, or use a report-only policy first |
| 13 | `/health` timing / availability | fixed earlier today | slow session lookups blocked the whole event loop (reproduced in a test); lookups now run in the thread pool and `/health` is `async def` | **FIXED** (Step 8) |
| 14 | Secrets rotation | owner action | docs/SECRETS_ROTATION.md (not rotated by me) | open |
| 15 | Old Render services may hold the same bot token | **medium, NOT VERIFIED** | see docs/OWNER_TODO.md "Token/service conflict" | owner |

What was NOT tested: the dashboard behind login (no credentials), WebSocket endpoints, file-upload endpoints, the Telegram webhook state (the token is not available to me), Neon network access rules.

---
# Day 7 review of everything added in Days 5-7 (5 Nov 2026)
Scope: candle downloader, loader, quality/validation tools, experiment tracker, sandbox and candidate tool, the six OFF flags, the fingerprint logger, the Cloud export/backup scripts, file permissions, log content, Cloud endpoints. Method: code reading, regex scans of tracked files and of `D:\sindhu_data\logs` and `manifest`, file attribute check, tests. Severity: High / Medium / Low / Info.
| # | Finding | Severity | Evidence | Action |
|---|---|---|---|---|
| 1 | **Cloud backups held the Cloud API token and the strategy-sync secret in plain text** (`cloud_settings.jsonl`, keys `api_token`, `strategy_sync_secret`). The files are outside git and on the owner's laptop, but any copy of the folder carries them | **Medium** | the 5 Nov export (value present, 45 and 46 characters; values were not printed) | **FIXED for new exports:** `scripts/backup_cloud_export.py` now replaces the value of every secret-like key by `<redacted:N chars>` (row counts unchanged, restore check unaffected); tests `tests/test_backup_export_redaction.py`. **NOT fixed for existing folders** (`D:\sindhu_backup_phase0\cloud_export_*` of 4 and 5 Nov): backups are never deleted or overwritten. Owner: keep that folder private (do not upload or share it) and rotate the token and secret when you decide on secrets rotation |
| 2 | Symbol and period names from an external API became file-path parts without a check | Low (the universe builder already keeps only alphanumeric base assets) | `data_platform/universe.py::eligible`; `store.py` | **FIXED (defence in depth):** `store.month_path/day_path/native_path` reject anything that is not a plain name or a `YYYY-MM[-DD]` period (no `..`, separators, drive letters); test in `tests/test_data_loader.py` |
| 3 | Data folder could be added to git by accident | Low | `.gitignore` had no entry (the folders are outside the repository) | **FIXED:** `.gitignore` now lists `sindhu_data/`, `sindhu_data_copy_*/`, `sindhu_backup*/`, `cloud_export_*/`, `*.parquet` |
| 4 | Dataset integrity and permissions | Info (good) | all 748 Parquet files are read-only; every file re-hashed against the manifest: 0 mismatches; writes go to a temporary name then an atomic rename; downloads are checked against Binance's published SHA-256 | none |
| 5 | Downloader uses public endpoints only | Info (good) | only `data.binance.vision`; no API key, no login, a generic client name; backoff with jitter | none |
| 6 | The checksum comes from the same host as the file | Low | `downloader.py` fetches `.CHECKSUM` next to the zip | accepted: protects against corruption, not against a hostile server; HTTPS only |
| 7 | A corrupt or oversized zip is parsed in memory | Low | `parse_zip_bytes` | accepted: monthly 1-minute files are about 3 MB each; checksum is verified first |
| 8 | Sandbox (candidate tool) isolation | Info with a residual risk | `data_platform/sandbox.py`, 7 tests: credential-like environment variables removed before any import; `socket.connect`, `connect_ex`, `create_connection` and `getaddrinfo` refuse non-loopback targets, including in the worker processes | residual (Low): the lock is a Python-level patch, not a firewall; code that talks to the network through the C library directly, or starts a non-Python program, would bypass it. The candidate code is a strategy rule file run by the existing engine, not arbitrary code. A Windows firewall rule would be the stronger fence (system setting: not changed by me) |
| 9 | Flags | Info (good) | the six flags are read from environment variables with strict parsing, default OFF, and can only withhold a Telegram message, skip an evaluation, hide one line, or print a log line; none touches money, keys or the database | none |
| 10 | Fingerprint logger output | Info | `[candle-fp]` lines contain exchange, symbol, timeframe, candle time, OHLCV and a hash; no secrets | none |
| 11 | Secrets in logs and tracked files | Info (good) | regex scan of `D:\sindhu_data\logs` and `manifest`: no matches; tracked files: matches only in tests, all fake values | none |
| 12 | Cloud endpoints | Info | no endpoint was added in Days 5-7; `/api/ops/pinger` answers 401 "login required" without a session; `/health` is public by design and shows the commit and engine state | none |
| 13 | Old Render services may hold the bot token | Medium, **NOT VERIFIED** | the connector cannot list environment variables; the services show no log lines since 1-3 Nov | owner: check each service's Environment page (docs/OWNER_TODO.md, Day 7 readiness) |
| 14 | Owner alert routing is off | Medium (operational) | Cloud log: "personal_chat_id not configured yet" | owner: enter the chat id |
| 15 | The Telegram bot token is never on this laptop | Info (good) | local settings: token and chat ids empty | none |


## Login (master plan V2 LG4, 2026-11-07)
| Control | What it does | Where / test |
|---|---|---|
| Two ways in, no lockout | `owner` + DASHBOARD_PASSWORD (Render env) and the saved account both work; reset tool for the saved account | `sindhu_web/api/auth.py`, `tools/reset_dashboard_user.py`; tests `test_env_owner_login_works_from_a_browser_with_csrf`, `test_saved_account_login_works` |
| Login CSRF | browser POSTs (Origin / Sec-Fetch-Site present) must be same-origin and carry `X-Login-CSRF` equal to the HttpOnly `sindhu_login_csrf` cookie (SameSite=Strict, path /api/auth). Scripts without browser headers are not exposed to CSRF and are not asked for it | `_csrf_ok`; tests `test_browser_login_without_csrf_is_rejected`, `test_cross_site_login_is_rejected_even_with_a_token` |
| Every other write | needs the login session and `X-Sindhu-Token` (same-origin `/api/token`): unchanged | `sindhu_web/security.py` |
| Guessing | per IP: 8 failures / 10 min (unchanged); per username: after 3 failures waits 2, 4, 8 ... s (max 15 min), for any username string, so it reveals nothing | `_user_wait_s`; `test_per_username_backoff_then_success_after_waiting`, `test_ip_rate_limit_still_triggers` |
| Same answer for wrong user or password | one generic 401; the password hash is always computed and both values compared in constant time | `auth.verify_password`; `test_wrong_password_and_wrong_username_get_the_same_generic_error` |
| Session cookie | HttpOnly, SameSite=Lax, Secure behind HTTPS (Render) | `_set_session_cookie`; `test_session_rotates_on_login_and_cookie_flags` |
| Rotation | a new token on every login; the token sent with the login request stops working | `auth_login` |
| Idle timeout | 12 h without use ends the session (sliding, written at most every 5 min); absolute cap 30 days | `auth.is_valid_session`; `test_idle_timeout_and_sliding_expiry` |
| Logout | in the account menu on every v2 page | `shell.js` |
| Attempt log | `[auth] login ok/failed/blocked-... ip#<10 hex of sha256(ip)>`: no username, no password | `_log_attempt` |
| Headers on all HTML | CSP `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy | `security_headers_middleware`; `test_html_has_security_headers` |
| No inline script | all `<script>` tags have `src` (or are JSON data blocks); the inline scripts of concepts.html and activity_log.html moved to files unchanged | `test_no_inline_script_or_inline_handlers` |
| Public endpoints | `/health`, `/health/details` (no secrets), `/api/public/login-scene` (only 0-1 candle shapes + last candle time, cached 5 min, <= 4 KB) | `test_public_endpoints_stay_public_and_others_need_login` |

Known limits (NOT VERIFIED / accepted): `style-src` allows inline styles because the old dashboard sets ~900 style attributes; the
per-IP and per-username counters are in memory, so a restart clears them; 2FA is optional and off (LG6).
