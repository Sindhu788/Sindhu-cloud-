/* Login "Market terrain" (master plan V2 LG2 + LG3). ES module, imported only after the login form is usable.
   96 BTC/USDT 15m candles as instanced 3D candlesticks on a slow ribbon (bodies + wicks + one faint echo row = 288 instances <= 300),
   muted profit/loss tones, the teal accent as the single rim light, soft fog, slow camera drift, pointer parallax on desktop only.
   Pauses when the tab is hidden or the canvas is off-screen; falls back to the poster when frames are slow; frees the GPU on stop(). */
export async function start(canvas, data, opts) {
  const THREE = await import(opts.threeUrl);
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || "#000";
  const candles = (data.candles || []).slice(-96);
  if (candles.length < 10) return null;
  const low = !!opts.low;
  const N = candles.length;

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: !low, alpha: true, powerPreference: "low-power" });
  } catch (e) { opts.onFallback && opts.onFallback("no-webgl"); return null; }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, low ? 1 : 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const bg = new THREE.Color(css("--bg"));
  scene.fog = new THREE.Fog(bg, 8, 22);
  const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 60);

  scene.add(new THREE.HemisphereLight(0xbfc8d0, 0x0b0e11, 0.8));
  const key = new THREE.DirectionalLight(0xffffff, 0.9); key.position.set(-4, 8, 6); scene.add(key);
  const rim = new THREE.DirectionalLight(new THREE.Color(css("--accent")), 3.2); rim.position.set(5, 4, -6); scene.add(rim);

  // ribbon layout: x along time, z bends gently, y = price (0..1 scaled)
  const W = 16, H = 3.2;
  const xs = i => (i / (N - 1) - 0.5) * W;
  const zs = (i, t) => Math.sin(i / 14 + t * 0.08) * 1.4;
  const up = new THREE.Color(css("--profit")).lerp(new THREE.Color(0x8a949e), 0.35);
  const dn = new THREE.Color(css("--loss")).lerp(new THREE.Color(0x8a949e), 0.35);

  const bodyGeo = new THREE.BoxGeometry(1, 1, 1);
  const wickGeo = new THREE.BoxGeometry(1, 1, 1);
  const bodyMat = new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.15 });
  const wickMat = new THREE.MeshStandardMaterial({ roughness: 0.8, metalness: 0.0, color: 0x6b757f });
  const echoMat = new THREE.MeshStandardMaterial({ roughness: 0.9, metalness: 0.0, transparent: true, opacity: 0.18 });
  const bodies = new THREE.InstancedMesh(bodyGeo, bodyMat, N);
  const wicks = new THREE.InstancedMesh(wickGeo, wickMat, N);
  const echo = new THREE.InstancedMesh(bodyGeo, echoMat, N);
  [bodies, wicks, echo].forEach(m => { m.instanceMatrix.setUsage(THREE.DynamicDrawUsage); scene.add(m); });
  if (low) echo.visible = false;                    // low-end device: 192 instances instead of 288, 30 fps cap below
  const dummy = new THREE.Object3D();
  const bw = (W / N) * 0.74;
  let rise = new Float32Array(N).fill(1);          // 0 -> 1 when a new candle arrives

  function layout(t) {
    for (let i = 0; i < N; i++) {
      const [o, h, l, c, v] = candles[i];
      const r = rise[i];
      const top = Math.max(o, c), bot = Math.min(o, c);
      const x = xs(i), z = zs(i, t);
      dummy.position.set(x, ((top + bot) / 2) * H * r, z);
      dummy.scale.set(bw, Math.max(0.03, (top - bot) * H) * r, bw);
      dummy.rotation.set(0, Math.cos(i / 14 + t * 0.08) * 0.25, 0);
      dummy.updateMatrix(); bodies.setMatrixAt(i, dummy.matrix);
      dummy.position.set(x, ((h + l) / 2) * H * r, z);
      dummy.scale.set(bw * 0.16, Math.max(0.02, (h - l) * H) * r, bw * 0.16);
      dummy.updateMatrix(); wicks.setMatrixAt(i, dummy.matrix);
      dummy.position.set(x, -0.35, z - 2.2);
      dummy.scale.set(bw, 0.05 + v * 0.9, bw);
      dummy.updateMatrix(); echo.setMatrixAt(i, dummy.matrix);
    }
    bodies.instanceMatrix.needsUpdate = wicks.instanceMatrix.needsUpdate = echo.instanceMatrix.needsUpdate = true;
  }
  function colors() {
    for (let i = 0; i < N; i++) { const col = candles[i][3] >= candles[i][0] ? up : dn; bodies.setColorAt(i, col); echo.setColorAt(i, col); }
    bodies.instanceColor.needsUpdate = echo.instanceColor.needsUpdate = true;
  }
  colors();

  function resize() {
    const w = canvas.clientWidth || canvas.parentNode.clientWidth, h = canvas.clientHeight || canvas.parentNode.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.fov = w / h < 1.1 ? 48 : 34;
    camera.updateProjectionMatrix();
  }
  resize();
  const ro = new ResizeObserver(resize); ro.observe(canvas.parentNode);

  // pointer parallax: desktop (fine pointer) only
  const px = { x: 0, y: 0, tx: 0, ty: 0 };
  const finePointer = matchMedia("(pointer: fine)").matches;
  const onMove = e => { px.tx = (e.clientX / innerWidth - 0.5) * 2; px.ty = (e.clientY / innerHeight - 0.5) * 2; };
  if (finePointer) addEventListener("pointermove", onMove, { passive: true });

  // pause when hidden / off-screen
  let visible = true, running = true, raf = 0, last = 0;
  const io = new IntersectionObserver(es => { visible = es[0].isIntersecting; if (visible && running) loop(performance.now()); });
  io.observe(canvas);
  const onVis = () => { if (!document.hidden && running) loop(performance.now()); };
  document.addEventListener("visibilitychange", onVis);

  // frame-time watchdog (LG3): average > 33 ms over the first 2 s -> stop and show the poster
  const minFrame = low ? 1000 / 30 : 0;
  let probeStart = 0, probeFrames = 0, probing = !opts.noWatchdog;
  const t0 = performance.now();

  function loop(now) {
    cancelAnimationFrame(raf);
    if (!running || document.hidden || !visible) return;
    raf = requestAnimationFrame(loop);
    if (minFrame && now - last < minFrame - 1) return;
    const dt = now - last; last = now;
    if (probing) {
      if (!probeStart) probeStart = now;
      else { probeFrames++; if (now - probeStart > 2000) { probing = false; if ((now - probeStart) / probeFrames > 33) { stop(); opts.onFallback && opts.onFallback("slow"); return; } } }
    }
    const t = (now - t0) / 1000;
    for (let i = 0; i < N; i++) if (rise[i] < 1) rise[i] = Math.min(1, rise[i] + (dt || 16) / 900);
    layout(t);
    px.x += (px.tx - px.x) * 0.04; px.y += (px.ty - px.y) * 0.04;
    const drift = Math.sin(t * 0.05) * 1.6;
    camera.position.set(drift + px.x * 0.8, 3.0 - px.y * 0.4, 9.2);
    camera.lookAt(drift * 0.4, 1.4, 0);
    renderer.render(scene, camera);
  }
  layout(0);
  loop(performance.now());
  if (opts.noWatchdog) window.__sindhuScene = { renderer, scene, camera, bodies };   // poster tool only

  // new candle every 15 min: refresh the shape data every 5 min; a new last candle rises in
  const lastOpen = { v: data.last_open_utc };
  const poll = setInterval(async () => {
    if (document.hidden || !running) return;
    try {
      const d = await (await fetch("/api/public/login-scene", { credentials: "same-origin" })).json();
      if (d.last_open_utc && d.last_open_utc !== lastOpen.v && (d.candles || []).length === N) {
        lastOpen.v = d.last_open_utc;
        for (let i = 0; i < N; i++) candles[i] = d.candles[i];
        rise = new Float32Array(N).fill(1); rise[N - 1] = 0;
        colors();
      }
    } catch (e) { /* keep the current picture */ }
  }, 300000);

  function stop() {
    running = false;
    cancelAnimationFrame(raf); clearInterval(poll);
    io.disconnect(); ro.disconnect();
    document.removeEventListener("visibilitychange", onVis);
    if (finePointer) removeEventListener("pointermove", onMove);
    [bodyGeo, wickGeo, bodyMat, wickMat, echoMat].forEach(x => x.dispose());
    [bodies, wicks, echo].forEach(m => m.dispose && m.dispose());
    renderer.dispose();
    try { renderer.forceContextLoss(); } catch (e) { /* already gone */ }
  }
  addEventListener("pagehide", stop, { once: true });
  return { stop, instances: N * 3 };
}
