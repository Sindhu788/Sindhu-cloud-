/* SINDHU Lite layer - loaded BEFORE app.js.
   Purpose: make the dashboard usable on a very small host (Render free plan, ~0.1 CPU, sleeps when idle).
   It changes HOW requests are made, never WHAT is shown or any trading behaviour:
     1. At most MAX_PARALLEL non-critical GET /api/* requests run at once; the rest wait in a FIFO queue
        (a page used to fire 20-27 at the same moment and every one of them waited for all the others).
     2. Critical status calls (home, token, auth, ops warnings, engine status) skip the queue.
     3. GET responses are cached for a short time and identical in-flight requests are shared. Any write
        (POST/PUT/PATCH/DELETE) clears the cache so a screen never shows data older than the user's own action.
     4. Known-heavy endpoints are started a moment later than the shell so the page frame renders first.
     5. If the caller gives up (its own timeout) the request keeps running and fills the cache, so the next
        poll is instant instead of starting from scratch.
     6. A page-scoped GET whose page has already been left is dropped (its promise never settles), so a slow loader of the
        page you just left can no longer write into the next page (this caused console errors such as "Cannot set
        properties of null"). Global polls (notifications, status, health, ops) are never dropped.
     7. A 502/503/504 or network error on a critical call shows "Server waking up, retrying..." until it recovers.
   Disable with localStorage.setItem("sindhu_lite", "off") (or ?lite=off once). */
(function () {
  "use strict";
  var off = false;
  try { off = (localStorage.getItem("sindhu_lite") === "off") || /[?&]lite=off/.test(location.search); } catch (e) {}
  if (off || !window.fetch || window.__sindhuLite) return;
  window.__sindhuLite = true;

  var MAX_PARALLEL = 4;
  var TTL_MS = 20000;
  var HEAVY_DELAY_MS = 900;
  var CRITICAL = [/^\/api\/home(\?|$)/, /^\/api\/token/, /^\/api\/auth\//, /^\/api\/ops\/warnings/,
                  /^\/api\/paper-trading\/status/, /^\/health/];
  var HEAVY = [/analytics/, /strategy-configs/, /decision-center/, /evolution\//, /pipeline-history/, /\/api\/jobs/,
               /backtesting\/strategies/, /risk-metrics/, /retirement-suggestions/, /coin-priority/, /correlation/,
               /backtest-history/, /compare-strategies/, /project-status/, /risk-department/, /telegram\/log/,
               /signal-tracker/, /best-worst/, /strategy-summary/];

  // Exactly the endpoints the always-on pollers in app.js use (topbar, notifications, engine banner, session warning, badge).
  var GLOBAL_POLL = [/^\/api\/activity/, /^\/api\/home/, /^\/api\/token/, /^\/api\/auth\//, /^\/api\/ops\//,
                     /^\/api\/paper-trading\/status/, /^\/api\/paper-trading\/dashboard-badge-status/, /^\/health/];
  var pageEpoch = 0;
  window.addEventListener("hashchange", function () { pageEpoch++; });

  var origFetch = window.fetch.bind(window);
  var cache = Object.create(null);      // url -> {t, status, statusText, headers, body}
  var inflight = Object.create(null);   // url -> Promise<entry>
  var queue = [];
  var running = 0;
  var wakeBanner = null;

  function pathOf(input) {
    var u = typeof input === "string" ? input : (input && input.url) || "";
    try { var a = new URL(u, location.origin); return a.origin === location.origin ? a.pathname + a.search : null; }
    catch (e) { return null; }
  }
  function matches(list, p) { for (var i = 0; i < list.length; i++) if (list[i].test(p)) return true; return false; }

  function showWake(on) {
    if (on && !wakeBanner) {
      wakeBanner = document.createElement("div");
      wakeBanner.id = "liteWakeBanner";
      wakeBanner.setAttribute("role", "status");
      wakeBanner.textContent = "Server waking up, retrying...";
      wakeBanner.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:10000;padding:6px 12px;text-align:center;" +
        "font:13px system-ui,sans-serif;background:#7a5a1f;color:#fff";
      (document.body || document.documentElement).appendChild(wakeBanner);
    } else if (!on && wakeBanner) { wakeBanner.remove(); wakeBanner = null; }
  }

  function pump() {
    while (running < MAX_PARALLEL && queue.length) { var job = queue.shift(); running++; job(); }
  }

  function run(url, init, critical) {
    return new Promise(function (resolve, reject) {
      function start() {
        // The caller's AbortSignal is deliberately NOT forwarded: the request finishes and fills the cache even if the
        // caller already gave up (see point 5 above). A hard 90 s limit still applies.
        var ctl = new AbortController();
        var hard = setTimeout(function () { ctl.abort(); }, 90000);
        var opts = Object.assign({}, init || {}); delete opts.signal; opts.signal = ctl.signal;
        origFetch(url, opts).then(function (res) {
          return res.text().then(function (body) {
            var entry = { t: Date.now(), status: res.status, statusText: res.statusText, headers: Array.from(res.headers.entries()), body: body };
            if (critical) showWake(res.status === 502 || res.status === 503 || res.status === 504);
            resolve(entry);
          });
        }).catch(function (e) { if (critical) showWake(true); reject(e); })
          .then(function () { clearTimeout(hard); if (!critical) { running--; pump(); } });
      }
      if (critical) start(); else { queue.push(start); pump(); }
    });
  }

  function toResponse(e) { return new Response(e.body, { status: e.status, statusText: e.statusText, headers: e.headers }); }

  window.fetch = function (input, init) {
    var method = ((init && init.method) || (typeof input !== "string" && input && input.method) || "GET").toUpperCase();
    var p = pathOf(input);
    if (p === null || p.indexOf("/api/") !== 0 && p.indexOf("/health") !== 0) return origFetch(input, init);
    if (method !== "GET") { cache = Object.create(null); return origFetch(input, init); }
    var signal = init && init.signal;
    var critical = matches(CRITICAL, p);
    var epoch = pageEpoch, pageScoped = !critical && !matches(GLOBAL_POLL, p);
    var hit = cache[p];
    var pending;
    if (hit && Date.now() - hit.t < (critical ? 3000 : TTL_MS)) pending = Promise.resolve(hit);
    else if (inflight[p]) pending = inflight[p];
    else {
      var go = function () {
        return run(p, init, critical).then(function (e) {
          if (e.status < 400) cache[p] = e;
          delete inflight[p]; return e;
        }, function (err) { delete inflight[p]; throw err; });
      };
      pending = inflight[p] = (!critical && matches(HEAVY, p))
        ? new Promise(function (r) { setTimeout(r, HEAVY_DELAY_MS); }).then(go) : go();
    }
    // Hand the caller its own abort behaviour: reject quickly if the caller's signal fires, while the work continues.
    return new Promise(function (resolve, reject) {
      if (signal) {
        var abort = function () { reject(new DOMException("Aborted", "AbortError")); };
        if (signal.aborted) return abort();
        signal.addEventListener("abort", abort, { once: true });
      }
      pending.then(function (e) {
        if (pageScoped && epoch !== pageEpoch) return;     // the page that asked is gone: never settle (see point 6)
        resolve(toResponse(e));
      }, function (err) { if (pageScoped && epoch !== pageEpoch) return; reject(err); });
    });
  };
})();
