// Shared left sidebar for every dashboard page: phase links, current page highlighted, a live status dot per phase.
// Pages only need <script src="nav.js"></script>; phases are listed here once.
(() => {
  const PHASES = [
    { key: "p0", href: "./", num: "0", name: "Baseline", sub: "prefill + decode, FA on" },
    { key: "p05", href: "p05", num: "0.5", name: "Flash attention", sub: "off vs on" },
    { key: "p1", href: "p1", num: "1", name: "Context & serving", sub: "32K, TTFT, loaded idle" },
    { key: "p1g", href: "p1g", num: "1+", name: "Gemma server rerun", sub: "--ctx-checkpoints 0" },
    { key: "p2", href: "p2", num: "2", name: "Vulkan vs SYCL", sub: "engine comparison" },
  ];
  const LINKS = [
    { href: "share", name: "Share cards" },
    { href: "files/findings/", name: "Findings" },
    { href: "files/", name: "Files" },
  ];
  const here = location.pathname.replace(/\/+$/, "").split("/").pop().replace(/\.html$/, "") || "";
  const isHere = href => { const h = href.replace(/^\.\/?/, "").replace(/\/$/, ""); return h === here || (h === "" && (here === "" || here === "index")); };

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
    .b65nav .brand, .b65nav .sec, .b65nav .sb, .b65nav .legend { display: none; }
    .b65nav a { grid-template-columns: auto auto 8px; padding: 6px 8px; }
    .b65nav .num { grid-row: auto; padding: 1px 6px; }
    .b65nav .st { grid-row: auto; }
    body.b65-has-nav .viz-root { margin-left: 0; }
  }`;
  const style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);
  const nav = document.createElement("aside"); nav.className = "b65nav"; nav.setAttribute("role", "navigation"); nav.setAttribute("aria-label", "Benchmark phases");
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  nav.innerHTML = `<div class="brand"><b>Arc Pro B65 bench</b><span>llama.cpp · 32 GB · tailnet</span></div>
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
    } catch (e) { /* dashboard offline: leave the dots as they are */ }
    setTimeout(poll, 15000);
  }
  poll();
})();
