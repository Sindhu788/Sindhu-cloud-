/* master plan V2: the old dashboard now lives at /legacy. On Cloud the server sets data-default-hash="wallet" on <html> (the old #home
   calls endpoints Cloud does not mount). External file because the CSP allows no inline script. */
(function () { var d = document.documentElement.getAttribute("data-default-hash"); if (d && !location.hash) location.hash = "#" + d; })();
