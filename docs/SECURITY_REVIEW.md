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
