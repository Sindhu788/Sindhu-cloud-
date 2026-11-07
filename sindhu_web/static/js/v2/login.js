/* Login v2 (master plan V2 LG1 + L6, LG3 loading rules). The form works on its own (no framework); the 3D scene is imported only
   after the form is usable, on idle, and only when the device and the user's settings allow it. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  let assets = {};
  try { assets = JSON.parse($("sindhu-assets").textContent || "{}"); } catch (e) { /* default paths */ }
  const asset = k => assets[k] || "/static/" + k;
  const SPRITE = asset("vendor/lucide-sprite.svg");
  const icon = n => `<svg class="icon" aria-hidden="true"><use href="${SPRITE}#i-${n}"></use></svg>`;
  let mode = "login", csrf = "", scene = null;

  async function getCsrf() {
    try { const r = await fetch("/api/auth/csrf", { credentials: "same-origin", cache: "no-store" }); csrf = (await r.json()).csrf || ""; } catch (e) { csrf = ""; }
  }

  function showError(msg) { const e = $("lgError"); e.textContent = msg; e.hidden = !msg; }
  function busy(on) {
    const b = $("lgSubmit");
    b.disabled = on; b.classList.toggle("loading", on);
    b.innerHTML = on ? `<span class="spin" aria-hidden="true"></span><span class="lbl">${mode === "setup" ? "Creating..." : "Signing in..."}</span>`
      : `<span class="lbl">${mode === "setup" ? "Create account" : "Sign in"}</span>`;
    $("lgForm").setAttribute("aria-busy", String(on));
  }

  function setMode(m) {
    mode = m;
    $("lgTitle").textContent = m === "setup" ? "Create the dashboard account" : "Sign in";
    $("lgConfirmF").hidden = m !== "setup";
    $("lgPass").setAttribute("autocomplete", m === "setup" ? "new-password" : "current-password");
    busy(false);
  }

  async function submit(e) {
    e.preventDefault();
    showError("");
    const username = $("lgUser").value.trim(), password = $("lgPass").value;
    if (!username || !password) { showError("Username aur password dono likho."); (username ? $("lgPass") : $("lgUser")).focus(); return; }
    if (mode === "setup") {
      if (password.length < 8) { showError("Password kam se kam 8 characters ka ho."); return; }
      if (password !== $("lgPass2").value) { showError("Dono passwords ek jaise nahi hain."); return; }
    }
    busy(true);
    try {
      if (!csrf) await getCsrf();
      const r = await fetch(mode === "setup" ? "/api/auth/setup" : "/api/auth/login", {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-Login-CSRF": csrf },
        body: JSON.stringify({ username, password }) });
      if (r.ok) {
        if (scene && scene.stop) scene.stop();           // free the GPU before leaving
        location.replace("/");
        return;
      }
      let detail = ""; try { detail = (await r.json()).detail || ""; } catch (x) { /* plain */ }
      if (r.status === 401) showError("Username ya password galat hai.");
      else if (r.status === 429) showError(/\d+ s/.test(detail) ? "Bahut zyada galat koshishen. " + detail.replace(/^.*Try again in/, "Dobara try karo") : "Bahut zyada galat koshishen. 10 minute baad try karo.");
      else if (r.status === 403) { await getCsrf(); showError(mode === "setup" ? String(detail || "Setup allowed nahi.") : "Page purana tha. Ab dobara Sign in dabao."); }
      else showError(mode === "setup" ? String(detail || "Account nahi bana.") : "Server ne jawab nahi diya. Thodi der baad try karo (free server ~1 minute mein jaagta hai).");
      $("lgPass").select();
    } catch (err) {
      showError("Server tak nahi pahunch sake. Internet check karo, ya 1 minute baad try karo (free server jaag raha ho sakta hai).");
    }
    busy(false);
  }

  function wire() {
    $("lgReveal").innerHTML = icon("eye");
    $("lgReveal").addEventListener("click", () => {
      const p = $("lgPass"), show = p.type === "password";
      p.type = show ? "text" : "password";
      $("lgReveal").innerHTML = icon(show ? "eye-off" : "eye");
      $("lgReveal").setAttribute("aria-pressed", String(show));
      $("lgReveal").setAttribute("aria-label", show ? "Hide password" : "Show password");
      p.focus();
    });
    const caps = e => { if (e.getModifierState) $("lgCaps").hidden = !e.getModifierState("CapsLock"); };
    ["lgPass", "lgPass2", "lgUser"].forEach(id => { $(id).addEventListener("keydown", caps); $(id).addEventListener("keyup", caps); });
    $("lgForgot").addEventListener("click", () => {
      const h = $("lgHelp"), open = h.hidden;
      h.hidden = !open; $("lgForgot").setAttribute("aria-expanded", String(open));
    });
    $("lgForm").addEventListener("submit", submit);
    const tick = () => { $("lgClock").textContent = new Date().toISOString().slice(11, 16) + " UTC"; };
    tick(); setInterval(tick, 15000);
    try { $("lgBuild").textContent = JSON.parse($("sindhu-build").textContent || '""'); } catch (e) { /* none */ }
  }

  async function status() {
    try {
      const r = await fetch("/api/auth/status", { credentials: "same-origin", cache: "no-store" });
      const d = await r.json();
      if (d.logged_in) { location.replace("/"); return; }
      setMode(d.configured ? "login" : "setup");
    } catch (e) { setMode("login"); }
  }

  // ---- LG3: decide whether the live scene may run, then import it lazily
  const FORCE = /[?&]scene=force/.test(location.search);    // only for rendering the poster image (tools/login_poster.py)
  function sceneAllowed() {
    if (FORCE) return { ok: true, low: false };
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return { ok: false, why: "reduced-motion" };
    try {
      const c = document.createElement("canvas");
      const gl = c.getContext("webgl2") || c.getContext("webgl");
      if (!gl) return { ok: false, why: "no-webgl" };
      const lose = gl.getExtension("WEBGL_lose_context"); if (lose) lose.loseContext();
    } catch (e) { return { ok: false, why: "no-webgl" }; }
    const cores = navigator.hardwareConcurrency || 8, mem = navigator.deviceMemory || 8;
    return { ok: true, low: cores <= 4 || mem <= 4 };
  }

  async function marketLine() {
    try {
      const d = await (await fetch("/api/public/login-scene", { credentials: "same-origin" })).json();
      if (d.source === "live" && d.last_open_utc) {
        const min = Math.max(0, Math.round((Date.now() - Date.parse(d.last_open_utc)) / 60000) - 15);
        $("lgMarket").textContent = `Market data: BTC/USDT 15m, updated ${min} min ago`;
        $("lgCaption").textContent = "BTC/USDT 15m, last 96 candles";
      } else {
        $("lgMarket").textContent = "Market data: demo (no fresh candles in memory)";
        $("lgCaption").textContent = "Demo data";
      }
      return d;
    } catch (e) { $("lgMarket").textContent = "Market data: not available"; return null; }
  }

  async function startScene(data) {
    const allow = sceneAllowed();
    document.documentElement.setAttribute("data-scene", allow.ok ? (allow.low ? "low" : "full") : allow.why);
    if (!allow.ok || !data) return;
    try {
      const mod = await import(asset("js/v2/login_scene.js"));
      scene = await mod.start($("lgCanvas"), data, { threeUrl: asset("vendor/three-0.160.1.module.min.js"), low: allow.low, noWatchdog: FORCE,
        onFallback: why => { console.warn("[login-scene] fallback: " + why); document.documentElement.setAttribute("data-scene", why); $("lgPoster").classList.remove("off"); $("lgCanvas").classList.remove("on"); } });
      if (scene) { $("lgCanvas").classList.add("on"); $("lgPoster").classList.add("off"); }
    } catch (e) { document.documentElement.setAttribute("data-scene", "error"); }
  }

  function boot() {
    wire();
    $("lgUser").focus();
    status();
    getCsrf();
    const idle = window.requestIdleCallback || (fn => setTimeout(fn, 300));
    idle(async () => { const d = await marketLine(); startScene(d); }, { timeout: 2000 });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
