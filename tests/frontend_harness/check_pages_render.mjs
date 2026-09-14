// 2026-09-14 regression harness: loads the REAL app.js in a Node vm sandbox
// with just enough DOM/browser stubs to execute, mocks every fetch() with a
// recursive "magic" Proxy that never throws "cannot read property of
// undefined" (so execution reaches deep into each render function's body
// instead of stopping at the first missing mock field), then calls every
// top-level page in PAGES and reports which ones throw.
//
// This exists because a purely static (text-based) scope check could not
// reliably catch the 2026-09-14 Paper Trading bug: `renderPaperTrading`'s
// "Self-Learning Progress by Strategy" section used a bare `en` identifier
// that was never declared in that closure (a different sibling closure in
// the same outer function happened to declare its own local `en` for an
// unrelated purpose, which a same-function-body text scan can't tell apart
// from the real one). Actually EXECUTING the code with a real JS engine
// is the only fully reliable way to catch a `ReferenceError` of this kind,
// so this harness reproduces -- offline, without needing a login session --
// the exact technique used to originally diagnose the bug live in a
// browser (a temporary window.__SINDHU_DEBUG__ hook + a mocked fetch).
//
// Run directly: node tests/frontend_harness/check_pages_render.mjs
// Exits 0 and prints {"ok": true, "pages": {...}} if every page renders
// cleanly; exits 1 and prints the failing pages otherwise.

import vm from "node:vm";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { webcrypto as crypto } from "node:crypto";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP_JS_PATH = path.join(__dirname, "..", "..", "sindhu_web", "static", "js", "app.js");

function makeMagic(depth = 0) {
  if (depth > 10) return null;
  const arrMethods = {
    map: () => [], filter: () => [], sort: () => [], flatMap: () => [],
    forEach: () => undefined, find: () => undefined, some: () => false, every: () => true,
    reduce: (fn, init) => init, concat: () => [], flat: () => [],
  };
  const target = function () {};
  const handler = {
    get(t, prop) {
      if (prop === Symbol.toPrimitive) return (hint) => (hint === "number" ? 0 : "");
      if (prop === "then" || prop === "catch" || prop === "finally") return undefined;
      if (prop === Symbol.iterator) return function* () {};
      if (prop === "length") return 0;
      if (typeof prop === "symbol") return undefined;
      if (Object.prototype.hasOwnProperty.call(arrMethods, prop)) return arrMethods[prop];
      if (prop === "toFixed") return () => "0";
      if (prop === "toString") return () => "";
      if (prop === "valueOf") return () => 0;
      if (prop === "hasOwnProperty") return () => false;
      return makeMagic(depth + 1);
    },
    has() { return true; },
    apply() { return makeMagic(depth + 1); },
  };
  return new Proxy(target, handler);
}

function makeElementStub() {
  const style = { setProperty() {}, removeProperty() {}, getPropertyValue: () => "" };
  const el = {
    style, dataset: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    children: [], childNodes: [],
    addEventListener() {}, removeEventListener() {},
    appendChild(c) { return c; }, removeChild() {}, remove() {},
    setAttribute() {}, getAttribute: () => null, removeAttribute() {},
    querySelector: () => null, querySelectorAll: () => [],
    closest: () => null, matches: () => false,
    focus() {}, blur() {}, click() {}, scrollIntoView() {},
    getBoundingClientRect: () => ({ top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0 }),
  };
  let innerHTML = "", textContent = "", value = "";
  Object.defineProperty(el, "innerHTML", { get: () => innerHTML, set: (v) => { innerHTML = String(v); } });
  Object.defineProperty(el, "textContent", { get: () => textContent, set: (v) => { textContent = String(v); } });
  Object.defineProperty(el, "value", { get: () => value, set: (v) => { value = v; } });
  el.disabled = false;
  el.scrollTop = 0;
  el.scrollHeight = 0;
  return el;
}

function buildSandbox() {
  const localStorageStore = {};
  const localStorage = {
    getItem: (k) => (k in localStorageStore ? localStorageStore[k] : null),
    setItem: (k, v) => { localStorageStore[k] = String(v); },
    removeItem: (k) => { delete localStorageStore[k]; },
  };
  const sessionStorageStore = {};
  const sessionStorage = {
    getItem: (k) => (k in sessionStorageStore ? sessionStorageStore[k] : null),
    setItem: (k, v) => { sessionStorageStore[k] = String(v); },
    removeItem: (k) => { delete sessionStorageStore[k]; },
  };
  const document = {
    getElementById: () => makeElementStub(),
    createElement: () => makeElementStub(),
    querySelector: () => makeElementStub(),
    querySelectorAll: () => [],
    addEventListener() {}, removeEventListener() {},
    body: makeElementStub(),
    documentElement: makeElementStub(),
    title: "",
  };
  const location = { hash: "#ceo", href: "http://localhost/", host: "localhost", reload() {} };
  const navigator = { userAgent: "node-test-harness", clipboard: { writeText: async () => {} } };

  class FakeWebSocket {
    constructor() {}
    send() {}
    close() {}
  }
  class FakeMutationObserver {
    observe() {}
    disconnect() {}
  }

  const sandbox = {
    console,
    setTimeout, clearTimeout, setInterval, clearInterval, queueMicrotask,
    AbortController,
    URLSearchParams,
    localStorage,
    sessionStorage,
    document,
    location,
    navigator,
    WebSocket: FakeWebSocket,
    MutationObserver: FakeMutationObserver,
    fetch: async () => ({ ok: true, status: 200, json: async () => makeMagic(), text: async () => "" }),
    addEventListener() {}, removeEventListener() {},
    crypto,
    innerWidth: 1280, innerHeight: 800, devicePixelRatio: 1,
    matchMedia: () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }),
    requestAnimationFrame: (cb) => setTimeout(cb, 0), cancelAnimationFrame: () => {},
    scrollTo() {},
  };
  sandbox.window = sandbox;
  sandbox.self = sandbox;
  sandbox.globalThis = sandbox;
  return sandbox;
}

function loadAppJsWithTestExport(sandbox) {
  let src = fs.readFileSync(APP_JS_PATH, "utf-8");
  // tolerate either line-ending style (this checkout uses CRLF)
  const markerRe = /\)\(\);\r?\n\}\)\(\);\s*$/;
  const m = markerRe.exec(src);
  if (!m) {
    throw new Error("could not find the expected end-of-file IIFE closing pattern in app.js -- harness assumption broke, update the marker");
  }
  const idx = m.index;
  const inject = ")();\nwindow.__TEST_EXPORTS__ = { PAGES, route, getLang, setLang };\n})();";
  src = src.slice(0, idx) + inject;
  const context = vm.createContext(sandbox);
  vm.runInContext(src, context, { filename: "app.js" });
  return sandbox.__TEST_EXPORTS__;
}

async function main() {
  const sandbox = buildSandbox();
  const exportsObj = loadAppJsWithTestExport(sandbox);
  // let the auto-running init() IIFE's microtasks settle before we start
  // calling pages ourselves (it awaits ensureToken/renderNav/route()).
  await new Promise((r) => setTimeout(r, 50));

  const results = {};
  for (const [id, fn] of Object.entries(exportsObj.PAGES)) {
    try {
      await fn();
      results[id] = { ok: true };
    } catch (e) {
      results[id] = { ok: false, error: e && e.message, stack: e && e.stack };
    }
  }

  const failing = Object.entries(results).filter(([, r]) => !r.ok);
  const output = { ok: failing.length === 0, pages: results };
  console.log(JSON.stringify(output));
  process.exit(failing.length === 0 ? 0 : 1);
}

main().catch((e) => {
  console.log(JSON.stringify({ ok: false, fatal: e.message, stack: e.stack }));
  process.exit(1);
});
