/**
 * XYPI Mixer — grid-aware playback with explicit horizontal / vertical / radial time.
 */
const XYPIPlayer = (() => {
  const PAD = 36;
  const CANVAS_H = 360;
  const SAMPLE_NAMES = ["", "kick", "snare", "hat", "blip"];

  let channels = [], audioCtx = null, masterGain = null;
  let playing = false, mixMuted = false, rafId = null;
  let loopStart = 0, lastStep = -1;
  let bpm = 150, nSteps = 8, stepSec = 0.4, cycleDuration = 3.2;

  function inferTimeFlow(config, gridLayout) {
    if (gridLayout?.time_flow) return gridLayout.time_flow;
    if (config.x_axis === "time") return "x";
    if (config.y_axis === "time") return "y";
    if (config.time?.flow) return config.time.flow;
    return "x";
  }

  function gridDims(ch) {
    const flow = inferTimeFlow(ch.config, ch.gridLayout);
    const t = ch.grid.time;
    const p = ch.grid.pitch;
    if (flow === "radial") {
      const oct = ch.config.space?.octave_cells || 4;
      return { flow, cols: p, rows: oct, timeCells: t, pitchCells: p };
    }
    if (flow === "y") return { flow, cols: p, rows: t, timeCells: t, pitchCells: p };
    return { flow, cols: t, rows: p, timeCells: t, pitchCells: p };
  }

  function midiToFreq(m) { return 440 * Math.pow(2, (m - 69) / 12); }

  function ensureAudio() {
    if (!audioCtx) {
      audioCtx = new AudioContext();
      masterGain = audioCtx.createGain();
      masterGain.connect(audioCtx.destination);
    }
    if (audioCtx.state === "suspended") audioCtx.resume();
  }

  function env(when, gain, dur, peak = 0.22) {
    gain.gain.setValueAtTime(0, when);
    gain.gain.linearRampToValueAtTime(peak, when + 0.008);
    gain.gain.exponentialRampToValueAtTime(0.001, when + dur);
  }

  function playSynth(midi, dur = 0.28) {
    const when = audioCtx.currentTime;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = "sine";
    osc.frequency.value = midiToFreq(midi);
    env(when, gain, dur);
    osc.connect(gain); gain.connect(masterGain);
    osc.start(when); osc.stop(when + dur + 0.05);
  }

  function playSample(slot, dur = 0.2) {
    const when = audioCtx.currentTime;
    const gain = audioCtx.createGain();
    gain.connect(masterGain);
    const n = Math.floor(audioCtx.sampleRate * dur);
    const buf = audioCtx.createBuffer(1, n, audioCtx.sampleRate);
    const d = buf.getChannelData(0);
    if (slot === 1) for (let i = 0; i < n; i++) { const t = i / audioCtx.sampleRate; d[i] = Math.sin(2 * Math.PI * (90 + 140 * Math.exp(-18 * t)) * t) * Math.exp(-10 * t); }
    else if (slot === 2) for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * Math.exp(-14 * i / n);
    else if (slot === 3) for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * Math.exp(-22 * i / n);
    else for (let i = 0; i < n; i++) { const t = i / audioCtx.sampleRate; d[i] = Math.sin(2 * Math.PI * 220 * t) * Math.exp(-6 * t); }
    const src = audioCtx.createBufferSource();
    src.buffer = buf; env(when, gain, dur, 0.35);
    src.connect(gain); src.start(when);
  }

  function playHit(ch, e) {
    if (mixMuted || ch.muted || !masterGain) return;
    const val = e.value ?? e.midi;
    if (!val) return;
    if ((ch.config.sound?.mode || "synth") === "sample") playSample(Math.round(val));
    else playSynth(Math.round(val));
  }

  function parseGeoJSON(data, label) {
    const props = data.properties?.xypi || {};
    const config = props.channel || {};
    return {
      label: label || config.name || "channel",
      bpm: props.bpm || 150,
      config,
      geometry: data.features[0].geometry,
      events: props.events || [],
      sourcePoints: props.source_points || [],
      grid: props.grid || { time: 8, pitch: 8 },
      gridLayout: props.grid_layout || {},
      radial: props.radial || null,
      bounds: computeBounds(data.features[0].geometry),
      muted: false,
    };
  }

  function computeBounds(geom) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const [x, y] of allCoords(geom)) {
      minX = Math.min(minX, x); minY = Math.min(minY, y);
      maxX = Math.max(maxX, x); maxY = Math.max(maxY, y);
    }
    return { minX, minY, maxX, maxY, width: maxX - minX || 1, height: maxY - minY || 1 };
  }

  function allCoords(geom) {
    if (geom.type === "Point") return [geom.coordinates];
    if (geom.type === "MultiPoint") return geom.coordinates;
    if (geom.type === "LineString") return geom.coordinates;
    if (geom.type === "MultiLineString") return geom.coordinates.flat();
    if (geom.type === "Polygon") return geom.coordinates[0];
    if (geom.type === "MultiPolygon") return geom.coordinates.flatMap(p => p[0]);
    return [];
  }

  function rings(geom) {
    if (geom.type === "Polygon") return [geom.coordinates[0]];
    if (geom.type === "MultiPolygon") return geom.coordinates.map(p => p[0]);
    if (geom.type === "LineString") return [geom.coordinates];
    if (geom.type === "MultiLineString") return geom.coordinates;
    return [];
  }

  function worldToCanvas(x, y, bounds, canvas) {
    const w = canvas.width - PAD * 2, h = canvas.height - PAD * 2;
    return [
      PAD + ((x - bounds.minX) / bounds.width) * w,
      PAD + (1 - (y - bounds.minY) / bounds.height) * h,
    ];
  }

  function cellWorldRect(col, row, dims, bounds) {
    const x0 = bounds.minX + (col / dims.cols) * bounds.width;
    const x1 = bounds.minX + ((col + 1) / dims.cols) * bounds.width;
    const y0 = bounds.minY + (row / dims.rows) * bounds.height;
    const y1 = bounds.minY + ((row + 1) / dims.rows) * bounds.height;
    return { x0, y0, x1, y1 };
  }

  function drawCellRect(c, rect, bounds, canvas, fill) {
    const [cx0, cy0] = worldToCanvas(rect.x0, rect.y1, bounds, canvas);
    const [cx1, cy1] = worldToCanvas(rect.x1, rect.y0, bounds, canvas);
    c.fillStyle = fill;
    c.fillRect(cx0, cy0, cx1 - cx0, cy1 - cy0);
  }

  function drawGrid(ch, canvas, activeStep) {
    const c = ch.canvas.getContext("2d");
    const { bounds } = ch;
    const dims = gridDims(ch);

    c.strokeStyle = "rgba(42, 47, 61, 0.95)";
    c.lineWidth = 1;
    for (let i = 1; i < dims.cols; i++) {
      const x = bounds.minX + (bounds.width * i) / dims.cols;
      const [cx] = worldToCanvas(x, bounds.minY, bounds, canvas);
      c.beginPath(); c.moveTo(cx, PAD); c.lineTo(cx, canvas.height - PAD); c.stroke();
    }
    for (let j = 1; j < dims.rows; j++) {
      const y = bounds.minY + (bounds.height * j) / dims.rows;
      const [, cy] = worldToCanvas(bounds.minX, y, bounds, canvas);
      c.beginPath(); c.moveTo(PAD, cy); c.lineTo(canvas.width - PAD, cy); c.stroke();
    }

    // Active pitch cells (same technique for x-time and y-time)
    const seen = new Set();
    ch.events.forEach((e) => {
      if (e.grid_col < 0 || e.grid_row < 0) return;
      const key = `${e.grid_col},${e.grid_row}`;
      if (seen.has(key)) return;
      seen.add(key);
      const rect = cellWorldRect(e.grid_col, e.grid_row, dims, bounds);
      drawCellRect(c, rect, bounds, canvas, e.hit ? "rgba(74, 222, 128, 0.12)" : "rgba(108, 158, 255, 0.06)");
    });

    // Current step: time band (column for x, row for y)
    if (activeStep >= 0 && dims.flow !== "radial") {
      if (dims.flow === "x") {
        const rect = cellWorldRect(activeStep, 0, { cols: dims.timeCells, rows: 1 }, bounds);
        rect.y1 = bounds.maxY; rect.y0 = bounds.minY;
        drawCellRect(c, rect, bounds, canvas, "rgba(249, 115, 22, 0.12)");
      } else if (dims.flow === "y") {
        const rect = cellWorldRect(0, activeStep, { cols: 1, rows: dims.timeCells }, bounds);
        rect.x1 = bounds.maxX; rect.x0 = bounds.minX;
        drawCellRect(c, rect, bounds, canvas, "rgba(249, 115, 22, 0.12)");
      }
    }

    // Radial expanding ring
    if (dims.flow === "radial" && ch.radial && activeStep >= 0) {
      const [ccx, ccy] = worldToCanvas(ch.radial.center.x, ch.radial.center.y, bounds, canvas);
      const maxPx = (ch.radial.max_radius / bounds.width) * (canvas.width - PAD * 2);
      const rOuter = ((activeStep + 1) / dims.timeCells) * maxPx;
      const rInner = (activeStep / dims.timeCells) * maxPx;
      c.strokeStyle = "rgba(249, 115, 22, 0.55)";
      c.lineWidth = 2;
      c.beginPath(); c.arc(ccx, ccy, rOuter, 0, Math.PI * 2); c.stroke();
      if (rInner > 0) {
        c.strokeStyle = "rgba(249, 115, 22, 0.2)";
        c.beginPath(); c.arc(ccx, ccy, rInner, 0, Math.PI * 2); c.stroke();
      }
      c.fillStyle = "rgba(249, 115, 22, 0.08)";
      c.beginPath(); c.arc(ccx, ccy, rOuter, 0, Math.PI * 2); c.fill();
    }

    drawAxisLabel(c, canvas, dims.flow);
  }

  function drawAxisLabel(c, canvas, flow) {
    c.font = "11px system-ui, sans-serif";
    c.fillStyle = "#f97316";
    if (flow === "x") {
      c.fillText("time →", canvas.width - PAD - 42, canvas.height - 10);
      c.fillStyle = "#8b92a5";
      c.fillText("pitch ↑", PAD + 4, PAD + 12);
    } else if (flow === "y") {
      c.fillStyle = "#f97316";
      c.fillText("time ↑", PAD + 4, PAD + 12);
      c.fillStyle = "#8b92a5";
      c.fillText("pitch →", canvas.width - PAD - 48, canvas.height - 10);
    } else {
      c.fillText("radial time ⊙", PAD + 4, PAD + 12);
      c.fillStyle = "#8b92a5";
      c.fillText("note →  octave ↑", canvas.width - PAD - 110, canvas.height - 10);
    }
  }

  function drawGeometry(ch, canvas) {
    const c = ch.canvas.getContext("2d");
    const { geometry: geom, bounds } = ch;
    const type = geom.type;

    if (type === "MultiPoint" || type === "Point") {
      for (const [x, y] of allCoords(geom)) {
        const [cx, cy] = worldToCanvas(x, y, bounds, canvas);
        c.beginPath(); c.arc(cx, cy, 4, 0, Math.PI * 2);
        c.fillStyle = "#6c9eff"; c.fill();
      }
      return;
    }

    for (const ring of rings(geom)) {
      if (ring.length < 2) continue;
      c.beginPath();
      const [sx, sy] = worldToCanvas(ring[0][0], ring[0][1], bounds, canvas);
      c.moveTo(sx, sy);
      for (let i = 1; i < ring.length; i++) {
        const [px, py] = worldToCanvas(ring[i][0], ring[i][1], bounds, canvas);
        c.lineTo(px, py);
      }
      const closed = type.includes("Polygon");
      if (closed) c.closePath();
      if (closed) { c.fillStyle = "rgba(108, 158, 255, 0.1)"; c.fill(); }
      c.strokeStyle = "#6c9eff"; c.lineWidth = 2; c.stroke();
    }
  }

  function drawChannel(ch, activeStep) {
    const canvas = ch.canvas;
    const c = canvas.getContext("2d");
    c.clearRect(0, 0, canvas.width, canvas.height);

    drawGrid(ch, canvas, activeStep);
    drawGeometry(ch, canvas);

    for (const pt of ch.sourcePoints) {
      const [cx, cy] = worldToCanvas(pt.x, pt.y, ch.bounds, canvas);
      c.beginPath(); c.arc(cx, cy, 5, 0, Math.PI * 2);
      c.fillStyle = "#6c9eff"; c.fill();
      c.strokeStyle = "#fff"; c.lineWidth = 1; c.stroke();
    }

    const ev = ch.events[activeStep];
    if (ev && ev.inside) {
      const [cx, cy] = worldToCanvas(ev.x, ev.y, ch.bounds, canvas);
      c.beginPath(); c.arc(cx, cy, 10, 0, Math.PI * 2);
      c.fillStyle = ev.hit ? "#4ade80" : "#f97316";
      c.fill(); c.strokeStyle = "#fff"; c.lineWidth = 2; c.stroke();
    }

    ch.stepBar.innerHTML = "";
    ch.events.forEach((e, i) => {
      const cell = document.createElement("div");
      cell.className = "step-cell" + (e.hit ? " hit" : "") + (i === activeStep ? " active" : "");
      ch.stepBar.appendChild(cell);
    });

    const flow = inferTimeFlow(ch.config, ch.gridLayout);
    const flowLabel = flow === "y" ? "vertical time" : flow === "radial" ? "radial time" : "horizontal time";
    const stepLabel = ch.stripEl.querySelector(".step-label");
    if (activeStep >= 0 && ev) {
      const mode = ch.config.sound?.mode || "synth";
      const val = ev.hit ? (mode === "sample" ? SAMPLE_NAMES[Math.round(ev.value)] || ev.value : `midi ${Math.round(ev.value)}`) : "rest";
      stepLabel.textContent = `${flowLabel} · step ${activeStep + 1} · ${val}`;
    } else {
      stepLabel.textContent = `${flowLabel} · ${ch.events.length} steps`;
    }
  }

  function renderAll(step) { channels.forEach(ch => drawChannel(ch, step)); updateStatus(step); }

  function updateStatus(step) {
    const el = document.getElementById("status");
    if (!playing) { el.textContent = `${channels.length} ch · ${bpm} BPM · ${cycleDuration.toFixed(1)}s loop`; return; }
    el.textContent = `Loop ${Math.floor((audioCtx.currentTime - loopStart) / cycleDuration) + 1} · step ${step + 1}/${nSteps} · ${bpm} BPM`;
  }

  function resizeCanvases() {
    const w = document.documentElement.clientWidth;
    const cols = window.innerWidth >= 1100 ? 2 : 1;
    const stripW = Math.floor(w / cols);
    channels.forEach(ch => { ch.canvas.width = stripW; ch.canvas.height = CANVAS_H; });
    renderAll(lastStep);
  }

  function triggerStep(step) { channels.forEach(ch => { if (!ch.muted) { const e = ch.events[step]; if (e?.hit) playHit(ch, e); } }); }

  function tick() {
    if (!playing) return;
    const step = Math.min(Math.floor(((audioCtx.currentTime - loopStart) % cycleDuration) / stepSec), nSteps - 1);
    if (step !== lastStep) { lastStep = step; triggerStep(step); }
    renderAll(step);
    rafId = requestAnimationFrame(tick);
  }

  function play() { if (!channels.length) return; ensureAudio(); playing = true; loopStart = audioCtx.currentTime; lastStep = -1; document.getElementById("play-btn").textContent = "▶ Playing…"; tick(); }
  function stop() { playing = false; lastStep = -1; if (rafId) cancelAnimationFrame(rafId); document.getElementById("play-btn").textContent = "▶ Play"; renderAll(-1); }
  function setMixMuted(m) { mixMuted = m; document.getElementById("mute-all-btn").textContent = m ? "Unmute all" : "Mute all"; document.getElementById("mute-all-btn").classList.toggle("muted", m); if (masterGain) masterGain.gain.value = m ? 0 : 1; }
  function toggleChannelMute(i) { const ch = channels[i]; ch.muted = !ch.muted; ch.muteBtn.textContent = ch.muted ? "Unmute" : "Mute"; ch.muteBtn.classList.toggle("muted", ch.muted); ch.stripEl.classList.toggle("muted-strip", ch.muted); }

  function timeFlowLabel(ch) {
    const f = inferTimeFlow(ch.config, ch.gridLayout);
    if (f === "y") return "vertical time (y)";
    if (f === "radial") return "radial time";
    return "horizontal time (x)";
  }

  function buildMixerUI() {
    document.getElementById("mixer").innerHTML = "";
    channels.forEach((ch, i) => {
      const strip = document.createElement("section");
      strip.className = "channel-strip";
      const mode = ch.config.sound?.mode || "synth";
      const tf = timeFlowLabel(ch);
      strip.innerHTML = `
        <div class="strip-header">
          <div>
            <div class="strip-title">${ch.label}</div>
            <div class="strip-meta">${mode} · ${tf} · x=${ch.config.x_axis} y=${ch.config.y_axis} · grid ${ch.grid.time}×${ch.grid.pitch}</div>
          </div>
          <div class="strip-controls">
            <span class="step-label">${ch.events.length} steps</span>
            <button type="button" class="mute-btn">Mute</button>
          </div>
        </div>
        <div class="canvas-wrap"><canvas></canvas></div>
        <div class="timeline"><div class="step-bar"></div></div>`;
      ch.stripEl = strip;
      ch.canvas = strip.querySelector("canvas");
      ch.stepBar = strip.querySelector(".step-bar");
      ch.muteBtn = strip.querySelector(".mute-btn");
      ch.muteBtn.onclick = () => toggleChannelMute(i);
      document.getElementById("mixer").appendChild(strip);
    });
    resizeCanvases();
    window.addEventListener("resize", resizeCanvases);
  }

  async function loadChannel(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`Failed ${url}`);
    return parseGeoJSON(await r.json(), url.split("/").pop().replace(".geojson", ""));
  }

  async function loadAll(urls) {
    channels = await Promise.all(urls.map(loadChannel));
    if (channels.length) {
      bpm = channels[0].bpm; nSteps = channels[0].events.length;
      stepSec = 60 / bpm; cycleDuration = nSteps * stepSec;
    }
    buildMixerUI(); renderAll(-1);
  }

  async function init() {
    document.getElementById("play-btn").onclick = play;
    document.getElementById("stop-btn").onclick = stop;
    document.getElementById("mute-all-btn").onclick = () => setMixMuted(!mixMuted);
    const urls = window.XYPI_DEFAULT_CHANNELS || [];
    if (urls.length) try { await loadAll(urls); } catch (e) { document.getElementById("status").textContent = e.message; }
  }

  return { init, loadAll, play, stop };
})();
