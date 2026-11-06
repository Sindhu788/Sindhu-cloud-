/* master plan V2: apply the saved theme before the first paint (external file: the CSP allows no inline script) */
(function () { try { var t = localStorage.getItem("sindhu_theme"); if (!t) t = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"; document.documentElement.setAttribute("data-theme", t); } catch (e) { /* keep dark */ } })();
