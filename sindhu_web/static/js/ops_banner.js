/* Owner-facing warnings banner: shows critical/warning items from /api/ops/warnings (engine off, signals blocked,
   stale data, DB nearly full). Self-contained; never touches app state. */
(function () {
  function render(items) {
    var old = document.getElementById("opsBanner");
    if (old) old.remove();
    items = (items || []).filter(function (w) { return w.level !== "info"; });
    if (!items.length) return;
    var bar = document.createElement("div");
    bar.id = "opsBanner";
    bar.setAttribute("role", "alert");
    bar.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:9999;padding:8px 14px;font:13px system-ui,sans-serif;" +
      "background:" + (items.some(function (w) { return w.level === "critical"; }) ? "#7a1f1f" : "#7a5a1f") + ";color:#fff;" +
      "display:flex;gap:12px;align-items:flex-start;max-height:30vh;overflow:auto";
    var text = document.createElement("div");
    text.style.flex = "1";
    items.forEach(function (w) {
      var p = document.createElement("div");
      p.textContent = (w.level === "critical" ? "\u26d4 " : "\u26a0\ufe0f ") + w.message;
      text.appendChild(p);
    });
    var close = document.createElement("button");
    close.textContent = "Dismiss";
    close.style.cssText = "background:transparent;border:1px solid #fff;color:#fff;border-radius:4px;padding:2px 8px;cursor:pointer";
    close.onclick = function () { bar.remove(); };
    bar.appendChild(text);
    bar.appendChild(close);
    document.body.appendChild(bar);
  }
  function load() {
    fetch("/api/ops/warnings", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : { warnings: [] }; })
      .then(function (d) { render(d.warnings); })
      .catch(function () {});
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", load); else load();
  setInterval(load, 120000);
})();
