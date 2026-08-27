/**
 * Shared XYPI REPL terminal — wired to map mixer via /api/exec.
 */
(() => {
  const outputEl = document.getElementById("terminal-output");
  const inputEl = document.getElementById("terminal-input");
  const runBtn = document.getElementById("run-btn");
  const helpBtn = document.getElementById("help-btn");
  const templatesBtn = document.getElementById("templates-btn");
  const resetBtn = document.getElementById("reset-btn");
  const channelCountEl = document.getElementById("channel-count");

  function appendBlock(text, className = "") {
    if (!text) return;
    const span = document.createElement("span");
    if (className) span.className = className;
    span.textContent = text.endsWith("\n") ? text : text + "\n";
    outputEl.appendChild(span);
    outputEl.scrollTop = outputEl.scrollHeight;
  }

  function appendPrompt(code) {
    const line = document.createElement("div");
    line.innerHTML = `<span class="prompt">&gt;&gt;&gt; </span>${escapeHtml(code)}`;
    outputEl.appendChild(line);
    outputEl.scrollTop = outputEl.scrollHeight;
  }

  function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function updateChannelCount(n) {
    channelCountEl.textContent = `${n} channel${n === 1 ? "" : "s"}`;
  }

  async function refreshMap(payloads) {
    if (!payloads || !payloads.length) {
      document.getElementById("mixer").innerHTML = "";
      updateChannelCount(0);
      document.getElementById("status").textContent = "No channels — call play(gdf, ...) in the terminal";
      return;
    }
    XYPIPlayer.loadFromGeoJSONList(payloads);
    updateChannelCount(payloads.length);
    document.getElementById("status").textContent = `${payloads.length} channel(s) loaded`;
  }

  async function execCode(code) {
    appendPrompt(code);
    runBtn.disabled = true;
    try {
      const res = await fetch("/api/exec", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const data = await res.json();
      if (data.stdout) appendBlock(data.stdout);
      if (data.stderr) appendBlock(data.stderr, "error");
      if (data.result) appendBlock(data.result, "result");
      if (data.error) appendBlock(data.error, "error");
      await refreshMap(data.payloads || []);
    } catch (err) {
      appendBlock(String(err), "error");
    } finally {
      runBtn.disabled = false;
    }
  }

  async function fetchHelp() {
    const res = await fetch("/api/help");
    return res.json();
  }

  async function showHelp() {
    try {
      const data = await fetchHelp();
      if (data.intro) appendBlock(data.intro + "\n");
      appendBlock("play() signature:\n" + data.play);
      appendBlock("\nQuick examples:");
      data.examples.forEach((ex) => appendBlock("  " + ex));
      if (data.templates?.length) {
        appendBlock("\nClick Templates for copy-paste snippets.");
      }
    } catch (err) {
      appendBlock(String(err), "error");
    }
  }

  async function showTemplates() {
    try {
      const data = await fetchHelp();
      appendBlock("Templates — paste into the editor, then Run (Ctrl+Enter):\n");
      (data.templates || []).forEach((t, i) => {
        appendBlock(`--- ${i + 1}. ${t.title} ---`);
        appendBlock(t.code);
        appendBlock("");
      });
      if (data.geojson_example) {
        appendBlock(`--- ${data.geojson_example.title} ---`);
        appendBlock(data.geojson_example.code);
        if (data.geojson_example.file) {
          appendBlock(`\nSample file: examples/${data.geojson_example.file}`);
        }
      }
      appendBlock("\nOr run help_templates() in the terminal.");
    } catch (err) {
      appendBlock(String(err), "error");
    }
  }

  async function loadInitial() {
    await XYPIPlayer.init({ skipAutoLoad: true });
    try {
      const data = await fetchHelp();
      if (data.intro) appendBlock(data.intro + "\n");
      if (data.welcome_lines) {
        data.welcome_lines.forEach((line) => appendBlock(line));
        appendBlock("");
      }
      appendBlock("Quick start:");
      (data.examples || []).slice(0, 3).forEach((ex) => appendBlock("  " + ex));
      appendBlock("");
    } catch (_) {
      appendBlock("Connected. Define a GeoDataFrame and call play(gdf).\n");
    }
  }

  runBtn.addEventListener("click", () => {
    const code = inputEl.value.trim();
    if (!code) return;
    execCode(code);
    inputEl.value = "";
  });

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      runBtn.click();
    }
  });

  helpBtn.addEventListener("click", showHelp);
  templatesBtn.addEventListener("click", showTemplates);

  resetBtn.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/reset");
      const data = await res.json();
      outputEl.innerHTML = "";
      appendBlock("REPL reset.\n");
      await refreshMap(data.payloads || []);
    } catch (err) {
      appendBlock(String(err), "error");
    }
  });

  document.addEventListener("DOMContentLoaded", loadInitial);
})();
