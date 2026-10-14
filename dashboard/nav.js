// Shared left sidebar for every dashboard page: phase links, current page highlighted, a live status dot per phase.
// Pages only need <script src="nav.js"></script>; phases are listed here once.
(() => {
  if (new URLSearchParams(location.search).get("solo")) return;   // share-card renders: the card only, no sidebar
  const PHASES = [
    { key: "p0", href: "./", num: "0", name: "Baseline", sub: "prefill + decode, FA on" },
    { key: "p05", href: "p05", num: "0.5", name: "Flash attention", sub: "off vs on" },
    { key: "p1", href: "p1", num: "1", name: "Context & serving", sub: "32K, TTFT, loaded idle" },
    { key: "p1g", href: "p1g", num: "1+", name: "Gemma server rerun", sub: "--ctx-checkpoints 0" },
    { key: "p2", href: "p2", num: "2", name: "Vulkan vs SYCL", sub: "engine comparison" },
    { key: "p1s", href: "p1s", num: "1S", name: "Phase 1 on SYCL", sub: "context & serving, FA on" },
    { key: "gd", href: "gd", num: "G", name: "Gemma SYCL diagnostic", sub: "server prefill gap" },
    { key: "p3", href: "p3", num: "3", name: "Quality checks", sub: "coding, tools, recall, writing" },
    { key: "p4", href: "p4", num: "4", name: "Canary", sub: "drift after updates, ub check" },
    { key: "us", href: "us", num: "4+", name: "Server at ub 2048", sub: "TTFT at the new default" },
    { key: "p5", href: "p5", num: "5", name: "Open questions", sub: "baseline, short TTFT, cache, Qwen loops" },
    { key: "p6", href: "p6", num: "6", name: "Confirming the recipes", sub: "thinking off, regen/edit, ub 2048 canary" },
    { key: "p15", href: "p15", num: "1.5", name: "Registry recipes", sub: "local-ai-registry lab gates" },
  ];
  const LINKS = [
    { href: "share", name: "Share cards" },
    { href: "files/findings/", name: "Findings" },
    { href: "files/", name: "Files" },
  ];
  const here = location.pathname.replace(/\/+$/, "").split("/").pop().replace(/\.html$/, "") || "";
  const isHere = href => { const h = href.split("#")[0].replace(/^\.\/?/, "").replace(/\/$/, ""); return h === here || (h === "" && (here === "" || here === "index")); };
  // on a phase page, "Share cards" opens that phase's tab (the Gemma rerun's cards live under Phase 1)
  const curPhase = PHASES.find(p => isHere(p.href)), shareTab = curPhase && { p1g: "p1", p1s: "p1s", gd: "gd", p3: "p3", p4: "p4", us: "us", p5: "p5", p6: "p6" }[curPhase.key] || (curPhase && curPhase.key);
  if (shareTab) LINKS.find(l => l.href === "share").href = "share#" + shareTab;

  const css = `
  .b65nav { --nav-w: 232px; --n-bg: #f3f3f0; --n-ink: #0b0b0b; --n-ink2: #52514e; --n-muted: #898781; --n-line: rgba(11,11,11,.10);
    --n-hover: rgba(11,11,11,.05); --n-active: rgba(42,120,214,.12); --n-accent: #2a78d6; --n-good: #0ca30c; --n-warn: #fab219;
    position: fixed; inset: 0 auto 0 0; width: var(--nav-w); z-index: 50; overflow-y: auto; box-sizing: border-box;
    background: var(--n-bg); border-right: 1px solid var(--n-line); padding: 20px 12px;
    font: 14px/1.35 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--n-ink); }
  @media (prefers-color-scheme: dark) { .b65nav { --n-bg: #121211; --n-ink: #f0efec; --n-ink2: #c3c2b7; --n-line: rgba(255,255,255,.10);
    --n-hover: rgba(255,255,255,.05); --n-active: rgba(57,135,229,.18); --n-accent: #3987e5; } }
  .b65nav .brand { padding: 0 10px 14px; border-bottom: 1px solid var(--n-line); margin-bottom: 12px; }
  .b65nav .brand b { display: block; font-size: 15px; }
  .b65nav .brand span { color: var(--n-muted); font-size: 12px; }
  .b65nav .gpu { margin: 0 4px 6px; padding: 10px; border: 1px solid var(--n-line); border-radius: 10px; }
  .b65nav .gpu .w { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .b65nav .gpu .w small { font-size: 12px; color: var(--n-ink2); font-weight: 500; margin-left: 2px; }
  .b65nav .gpu .t { color: var(--n-ink2); font-size: 12px; font-variant-numeric: tabular-nums; }
  .b65nav .gpu svg { display: block; width: 100%; height: 34px; margin-top: 6px; }
  .b65nav .gpu .cap { color: var(--n-muted); font-size: 11px; margin-top: 2px; }
  .b65nav .sec { color: var(--n-muted); font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; padding: 10px 10px 6px; }
  .b65nav a { display: grid; grid-template-columns: 34px 1fr 10px; align-items: center; gap: 0 8px; padding: 8px 10px; border-radius: 8px;
    color: inherit; text-decoration: none; }
  .b65nav a:hover { background: var(--n-hover); }
  .b65nav a.on { background: var(--n-active); }
  .b65nav a.on .nm { color: var(--n-accent); }
  .b65nav .num { grid-row: span 2; font-weight: 750; font-size: 13px; color: var(--n-ink2); text-align: center; border: 1px solid var(--n-line);
    border-radius: 6px; padding: 3px 0; font-variant-numeric: tabular-nums; }
  .b65nav a.on .num { border-color: var(--n-accent); color: var(--n-accent); }
  .b65nav .nm { font-weight: 600; }
  .b65nav .sb { grid-column: 2; color: var(--n-muted); font-size: 12px; }
  .b65nav .st { grid-row: 1; grid-column: 3; width: 8px; height: 8px; border-radius: 50%; background: transparent; }
  .b65nav .st.running { background: var(--n-good); animation: b65pulse 1.6s infinite; }
  .b65nav .st.finished { background: var(--n-muted); opacity: .6; }
  .b65nav .st.stopped { background: var(--n-warn); }
  .b65nav a.plain { grid-template-columns: 1fr; padding: 7px 10px; color: var(--n-ink2); }
  .b65nav .legend { color: var(--n-muted); font-size: 11px; padding: 14px 10px 0; display: flex; gap: 10px; flex-wrap: wrap; }
  .b65nav .legend i { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 4px; vertical-align: 1px; }
  @keyframes b65pulse { 50% { opacity: .3; } }
  body.b65-has-nav .viz-root { margin-left: var(--nav-w, 232px); }
  @media (max-width: 900px) {
    .b65nav { position: sticky; inset: auto; top: 0; width: auto; display: flex; gap: 4px; overflow-x: auto; padding: 8px; border-right: 0;
      border-bottom: 1px solid var(--n-line); white-space: nowrap; }
    .b65nav .brand, .b65nav .sec, .b65nav .sb, .b65nav .legend, .b65nav .gpu { display: none; }
    .b65nav a { grid-template-columns: auto auto 8px; padding: 6px 8px; }
    .b65nav .num { grid-row: auto; padding: 1px 6px; }
    .b65nav .st { grid-row: auto; }
    body.b65-has-nav .viz-root { margin-left: 0; }
  }`;
  const style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);
  const nav = document.createElement("aside"); nav.className = "b65nav"; nav.setAttribute("role", "navigation"); nav.setAttribute("aria-label", "Benchmark phases");
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  nav.innerHTML = `<div class="brand"><b>Arc Pro B65 bench</b><span>llama.cpp · 32 GB · tailnet</span></div>
    <div class="sec">GPU now</div>
    <div class="gpu" title="xe hwmon: board power, GPU package temp, fan"><div class="w" id="b65-w">–</div><div class="t" id="b65-t"></div>
      <svg id="b65-spark" viewBox="0 0 200 34" preserveAspectRatio="none" aria-label="Board power, last 30 min"></svg><div class="cap" id="b65-cap">board power, last 30 min</div></div>
    <div class="sec">Phases</div>
    ${PHASES.map(p => `<a href="${p.href}" class="${isHere(p.href) ? "on" : ""}"${isHere(p.href) ? ' aria-current="page"' : ""}>
      <span class="num">${esc(p.num)}</span><span class="nm">${esc(p.name)}</span><span class="st" id="b65st-${p.key}" title=""></span>
      <span class="sb">${esc(p.sub)}</span></a>`).join("")}
    <div class="sec">More</div>
    ${LINKS.map(l => `<a class="plain ${isHere(l.href) ? "on" : ""}" href="${l.href}"><span class="nm">${esc(l.name)}</span></a>`).join("")}
    <div class="legend"><span><i style="background:#0ca30c"></i>running</span><span><i style="background:#898781"></i>done</span><span><i style="background:#fab219"></i>stopped</span></div>`;
  const mount = () => { document.body.prepend(nav); document.body.classList.add("b65-has-nav"); };
  document.body ? mount() : document.addEventListener("DOMContentLoaded", mount);

  const LABEL = { running: "running", finished: "done", stopped: "stopped (incomplete)", dry: "dry run only", "not started": "not started" };
  async function poll() {
    try {
      const s = await (await fetch("api/nav", { cache: "no-store" })).json();
      PHASES.forEach(p => { const el = document.getElementById("b65st-" + p.key), x = s[p.key] || {};
        if (!el) return; el.className = "st " + (x.state === "dry" ? "stopped" : x.state || "");
        el.title = (LABEL[x.state] || x.state || "") + (x.run_id ? ` · ${x.run_id}` : ""); });
      const L = s.live, w = document.getElementById("b65-w"), t = document.getElementById("b65-t"), sv = document.getElementById("b65-spark");
      if (w && L) { w.innerHTML = `${L[1].toFixed(1)}<small>W</small>`;
        t.innerHTML = [L[2] != null ? `GPU ${L[2].toFixed(0)} °C` : "", L[3] != null ? `VRAM ${L[3].toFixed(0)} °C` : ""].filter(Boolean).join(" · ") + (L[4] != null ? `<br>fan ${Math.round(L[4])} rpm` : ""); }
      if (sv && s.spark && s.spark.length > 1) {   // fixed 0-200 W scale (board cap) so the line height means the same everywhere
        const n = s.spark.length, y = v => 33 - Math.min(v, 200) / 200 * 32;
        const d = s.spark.map((v, i) => `${i ? "L" : "M"}${(i / (n - 1) * 200).toFixed(1)},${y(v).toFixed(1)}`).join("");
        sv.innerHTML = `<path d="${d}L200,34L0,34Z" fill="var(--n-active)"/><path d="${d}" fill="none" stroke="var(--n-accent)" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`;
        document.getElementById("b65-cap").textContent = `board power, last ${Math.max(1, Math.round(s.span_s / 60))} min · 0–200 W`; }
    } catch (e) { /* dashboard offline: leave the dots as they are */ }
    setTimeout(poll, 5000);
  }
  poll();
})();
