"""Local web console for inspecting Mneme memory state."""
# ruff: noqa: E501
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from mneme.memory.inspect import collect_snapshot
from mneme.memory.job_inspect import snapshot as collect_job_snapshot
from mneme.sleep.agent import run_sleep_cycle


async def collect_console_snapshot() -> dict[str, Any]:
    """Collect dashboard data without invoking LLM-backed agents."""
    memory = await collect_snapshot(limit=40, include_deleted=False)
    jobs = await collect_job_snapshot(limit=20)
    return {
        "status": "ok",
        "generated_at": datetime.now(UTC).isoformat(),
        "memory": memory,
        "jobs": jobs,
    }


async def console_page(_request: Request) -> HTMLResponse:
    return HTMLResponse(CONSOLE_HTML)


async def console_snapshot(_request: Request) -> JSONResponse:
    return JSONResponse(await collect_console_snapshot())


async def console_run_sleep(_request: Request) -> JSONResponse:
    summary = await run_sleep_cycle()
    return JSONResponse({
        "status": "ok" if summary.get("status") == "ok" else "error",
        "summary": summary,
    })


routes = [
    Route("/console", console_page, methods=["GET"]),
    Route("/api/console/snapshot", console_snapshot, methods=["GET"]),
    Route("/api/console/sleep/run", console_run_sleep, methods=["POST"]),
]


CONSOLE_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mneme Console</title>
  <style>
    :root {
      --bg: #f4f1ea;
      --panel: #fffdf7;
      --panel-2: #ebe6dc;
      --ink: #20231f;
      --muted: #6d6a62;
      --line: #d6d0c3;
      --green: #2f6f59;
      --green-soft: #dcebe4;
      --amber: #9a651f;
      --amber-soft: #f3e4c8;
      --red: #a94335;
      --red-soft: #f1d9d4;
      --steel: #405a63;
      --shadow: 0 18px 45px rgba(39, 35, 28, 0.12);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        linear-gradient(90deg, rgba(32,35,31,0.045) 1px, transparent 1px),
        linear-gradient(0deg, rgba(32,35,31,0.035) 1px, transparent 1px),
        radial-gradient(circle at top left, rgba(47,111,89,0.14), transparent 34rem),
        var(--bg);
      background-size: 34px 34px, 34px 34px, auto, auto;
      font-family: "Avenir Next", "Gill Sans", ui-sans-serif, system-ui, sans-serif;
      letter-spacing: 0;
    }

    button, input, select { font: inherit; }

    .shell {
      display: grid;
      grid-template-columns: 248px minmax(0, 1fr);
      min-height: 100vh;
    }

    aside {
      position: sticky;
      top: 0;
      height: 100vh;
      padding: 24px 18px;
      background: rgba(255, 253, 247, 0.82);
      border-right: 1px solid var(--line);
      backdrop-filter: blur(12px);
    }

    .brand {
      font-family: Georgia, "Times New Roman", serif;
      font-size: 30px;
      line-height: 1;
      margin: 0 0 8px;
    }

    .subtitle {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
      margin-bottom: 28px;
    }

    nav {
      display: grid;
      gap: 7px;
    }

    nav a {
      color: var(--ink);
      text-decoration: none;
      padding: 10px 12px;
      border: 1px solid transparent;
      border-radius: 8px;
      font-size: 14px;
    }

    nav a:hover {
      background: var(--green-soft);
      border-color: #b8d2c7;
    }

    .main {
      padding: 28px;
      max-width: 1500px;
      width: 100%;
    }

    .topbar {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 18px;
      margin-bottom: 22px;
    }

    h1 {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(34px, 4vw, 58px);
      line-height: 1;
      letter-spacing: 0;
    }

    .dek {
      color: var(--muted);
      max-width: 720px;
      margin-top: 10px;
      line-height: 1.5;
    }

    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .btn {
      border: 1px solid var(--ink);
      background: var(--ink);
      color: #fffdf7;
      border-radius: 8px;
      padding: 10px 13px;
      cursor: pointer;
      min-height: 40px;
    }

    .btn.secondary {
      background: var(--panel);
      color: var(--ink);
      border-color: var(--line);
    }

    .btn:disabled {
      opacity: 0.55;
      cursor: wait;
    }

    .stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }

    .stat, section {
      background: rgba(255, 253, 247, 0.88);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }

    .stat {
      padding: 16px;
    }

    .label {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .value {
      font-size: 31px;
      line-height: 1.1;
      margin-top: 8px;
      font-family: Georgia, "Times New Roman", serif;
    }

    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(360px, 0.9fr);
      gap: 14px;
      align-items: start;
    }

    section {
      overflow: hidden;
      margin-bottom: 14px;
    }

    .section-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      background: rgba(235, 230, 220, 0.55);
    }

    h2 {
      margin: 0;
      font-size: 17px;
      letter-spacing: 0;
    }

    .section-body {
      padding: 14px 16px 16px;
    }

    .core-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .core-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
      min-height: 132px;
    }

    .core-card h3 {
      margin: 0 0 8px;
      font-size: 14px;
      color: var(--green);
      letter-spacing: 0;
    }

    .core-card p, .empty {
      color: var(--muted);
      line-height: 1.45;
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }

    th, td {
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }

    th {
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      background: rgba(244, 241, 234, 0.8);
    }

    td {
      line-height: 1.45;
    }

    .scroll {
      overflow: auto;
      max-height: 520px;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 3px 8px;
      background: var(--panel-2);
      color: var(--steel);
      font-size: 12px;
      margin: 0 4px 4px 0;
      white-space: nowrap;
    }

    .chip.ok { color: var(--green); background: var(--green-soft); }
    .chip.warn { color: var(--amber); background: var(--amber-soft); }
    .chip.bad { color: var(--red); background: var(--red-soft); }

    .timeline {
      display: grid;
      gap: 10px;
    }

    .op {
      border-left: 3px solid var(--green);
      padding: 0 0 0 11px;
    }

    .op strong {
      display: block;
      font-size: 13px;
    }

    .op p {
      margin: 4px 0 0;
      color: var(--muted);
      line-height: 1.4;
      word-break: break-word;
    }

    .status-line {
      color: var(--muted);
      font-size: 13px;
      margin-top: 10px;
      min-height: 20px;
    }

    .mono {
      font-family: "SFMono-Regular", Consolas, ui-monospace, monospace;
    }

    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      background: #24251f;
      color: #f8f2e7;
      padding: 14px;
      border-radius: 8px;
      max-height: 360px;
      overflow: auto;
      font-size: 12px;
      line-height: 1.5;
    }

    @media (max-width: 1000px) {
      .shell { grid-template-columns: 1fr; }
      aside {
        position: static;
        height: auto;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
      nav { grid-template-columns: repeat(5, minmax(0, 1fr)); }
      nav a { text-align: center; padding: 9px 6px; }
      .topbar { flex-direction: column; }
      .actions { justify-content: flex-start; }
      .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .grid { grid-template-columns: 1fr; }
    }

    @media (max-width: 640px) {
      .main { padding: 18px; }
      nav { grid-template-columns: 1fr 1fr; }
      .stats { grid-template-columns: 1fr; }
      .core-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <h1 class="brand">Mneme</h1>
      <div class="subtitle">Local memory console for Claude Code. Durable writes, archival facts, Sleep ops, and core blocks in one place.</div>
      <nav>
        <a href="#overview">Overview</a>
        <a href="#core">Core</a>
        <a href="#facts">Facts</a>
        <a href="#jobs">Jobs</a>
        <a href="#ops">Ops</a>
      </nav>
    </aside>
    <main class="main">
      <div class="topbar">
        <div>
          <h1>Mneme Console</h1>
          <div class="dek">A local operator view for the memory system behind Claude Code. Use it to inspect what was remembered, whether async writes finished, and what Sleep changed.</div>
          <div id="status" class="status-line">Loading snapshot...</div>
        </div>
        <div class="actions">
          <button class="btn secondary" id="refreshBtn">Refresh</button>
          <button class="btn" id="sleepBtn">Run Sleep</button>
        </div>
      </div>

      <section id="overview">
        <div class="section-head"><h2>Overview</h2><span id="generatedAt" class="label"></span></div>
        <div class="section-body stats" id="stats"></div>
      </section>

      <div class="grid">
        <div>
          <section id="core">
            <div class="section-head"><h2>Core Blocks</h2><span class="label">Sleep-owned</span></div>
            <div class="section-body"><div class="core-grid" id="coreBlocks"></div></div>
          </section>

          <section id="facts">
            <div class="section-head"><h2>Archival Facts</h2><span class="label">Latest active facts</span></div>
            <div class="scroll"><table id="factsTable"></table></div>
          </section>
        </div>

        <div>
          <section id="jobs">
            <div class="section-head"><h2>Write Jobs</h2><span class="label">remember / forget</span></div>
            <div class="scroll"><table id="jobsTable"></table></div>
          </section>

          <section id="ops">
            <div class="section-head"><h2>Ops Log</h2><span class="label">Recent mutations</span></div>
            <div class="section-body"><div class="timeline" id="opsTimeline"></div></div>
          </section>

          <section>
            <div class="section-head"><h2>Sleep Result</h2><span class="label">Manual run output</span></div>
            <div class="section-body"><pre id="sleepOutput">{}</pre></div>
          </section>
        </div>
      </div>
    </main>
  </div>

  <script>
    const els = {
      status: document.getElementById("status"),
      generatedAt: document.getElementById("generatedAt"),
      stats: document.getElementById("stats"),
      coreBlocks: document.getElementById("coreBlocks"),
      factsTable: document.getElementById("factsTable"),
      jobsTable: document.getElementById("jobsTable"),
      opsTimeline: document.getElementById("opsTimeline"),
      sleepOutput: document.getElementById("sleepOutput"),
      refreshBtn: document.getElementById("refreshBtn"),
      sleepBtn: document.getElementById("sleepBtn"),
    };

    function esc(value) {
      return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      })[ch]);
    }

    function fmtTime(value) {
      if (!value) return "";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value;
      return date.toLocaleString();
    }

    function chip(text, tone = "") {
      return `<span class="chip ${tone}">${esc(text)}</span>`;
    }

    function statusTone(status) {
      if (status === "succeeded" || status === "ok") return "ok";
      if (status === "failed" || status === "error") return "bad";
      if (status === "pending" || status === "running") return "warn";
      return "";
    }

    function renderStats(data) {
      const memory = data.memory || {};
      const counts = memory.counts || {};
      const jobs = ((data.jobs || {}).jobs || []);
      const failedJobs = jobs.filter((job) => job.status === "failed").length;
      const pendingJobs = jobs.filter((job) => job.status === "pending" || job.status === "running").length;
      const recentOps = (memory.recent_ops || []).length;
      const items = [
        ["Active Facts", counts.active_archival_facts ?? 0],
        ["Deleted Facts", counts.deleted_archival_facts ?? 0],
        ["Open Jobs", pendingJobs],
        ["Recent Ops", recentOps],
      ];
      if (failedJobs > 0) items[2][1] = `${pendingJobs} / ${failedJobs} failed`;
      els.stats.innerHTML = items.map(([label, value]) => `
        <div class="stat"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div></div>
      `).join("");
    }

    function renderCore(blocks) {
      if (!blocks || blocks.length === 0) {
        els.coreBlocks.innerHTML = `<p class="empty">No core blocks found.</p>`;
        return;
      }
      els.coreBlocks.innerHTML = blocks.map((block) => `
        <article class="core-card">
          <h3>${esc(block.label)} <span class="chip">v${esc(block.version)}</span></h3>
          <p>${esc(block.value || "Empty")}</p>
        </article>
      `).join("");
    }

    function renderFacts(facts) {
      if (!facts || facts.length === 0) {
        els.factsTable.innerHTML = `<tbody><tr><td class="empty">No active archival facts.</td></tr></tbody>`;
        return;
      }
      els.factsTable.innerHTML = `
        <thead><tr><th>ID</th><th>Content</th><th>Signals</th><th>Use</th><th>Created</th></tr></thead>
        <tbody>
        ${facts.map((fact) => `
          <tr>
            <td class="mono">${esc(fact.id)}</td>
            <td>${esc(fact.content)}<div>${(fact.tags || []).map((tag) => chip(tag)).join("")}</div></td>
            <td>${chip("c" + fact.confidence)}${chip(fact.stability)}${chip("s" + fact.salience)}</td>
            <td class="mono">${esc(fact.use_count)}</td>
            <td>${esc(fmtTime(fact.created_at))}</td>
          </tr>
        `).join("")}
        </tbody>`;
    }

    function renderJobs(jobs) {
      if (!jobs || jobs.length === 0) {
        els.jobsTable.innerHTML = `<tbody><tr><td class="empty">No write jobs yet.</td></tr></tbody>`;
        return;
      }
      els.jobsTable.innerHTML = `
        <thead><tr><th>ID</th><th>Op</th><th>Status</th><th>Attempts</th><th>Updated</th></tr></thead>
        <tbody>
        ${jobs.map((job) => `
          <tr>
            <td class="mono">${esc(job.id)}</td>
            <td>${esc(job.operation)}</td>
            <td>${chip(job.status, statusTone(job.status))}${job.last_error ? `<p>${esc(job.last_error)}</p>` : ""}</td>
            <td class="mono">${esc(job.attempt_count)} / ${esc(job.max_attempts)}</td>
            <td>${esc(fmtTime(job.updated_at))}</td>
          </tr>
        `).join("")}
        </tbody>`;
    }

    function renderOps(ops) {
      if (!ops || ops.length === 0) {
        els.opsTimeline.innerHTML = `<p class="empty">No recent ops.</p>`;
        return;
      }
      els.opsTimeline.innerHTML = ops.map((op) => `
        <div class="op">
          <strong>${esc(op.op_type)} ${chip(op.actor)} ${op.target_id ? chip(op.target_id) : ""}</strong>
          <p>${esc(op.reason || op.after_value_preview || op.before_value_preview || "No reason recorded.")}</p>
          <p class="mono">${esc(fmtTime(op.ts))}</p>
        </div>
      `).join("");
    }

    function render(data) {
      els.generatedAt.textContent = data.generated_at ? `generated ${fmtTime(data.generated_at)}` : "";
      renderStats(data);
      renderCore((data.memory || {}).core_blocks || []);
      renderFacts((data.memory || {}).archival_facts || []);
      renderJobs(((data.jobs || {}).jobs || []));
      renderOps((data.memory || {}).recent_ops || []);
    }

    async function refresh() {
      els.status.textContent = "Loading snapshot...";
      els.refreshBtn.disabled = true;
      try {
        const response = await fetch("/api/console/snapshot");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        render(data);
        els.status.textContent = "Snapshot loaded.";
      } catch (error) {
        els.status.textContent = `Snapshot failed: ${error.message}`;
      } finally {
        els.refreshBtn.disabled = false;
      }
    }

    async function runSleep() {
      els.sleepBtn.disabled = true;
      els.sleepOutput.textContent = "Running Sleep...";
      try {
        const response = await fetch("/api/console/sleep/run", { method: "POST" });
        const data = await response.json();
        els.sleepOutput.textContent = JSON.stringify(data.summary || data, null, 2);
        await refresh();
      } catch (error) {
        els.sleepOutput.textContent = `Sleep failed: ${error.message}`;
      } finally {
        els.sleepBtn.disabled = false;
      }
    }

    els.refreshBtn.addEventListener("click", refresh);
    els.sleepBtn.addEventListener("click", runSleep);
    refresh();
  </script>
</body>
</html>
"""
