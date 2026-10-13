#!/usr/bin/env python3
"""Phase 1 summary: decode table, context-fit table, server TTFT table, loaded idle power. Writes phase1_summary.md."""
import csv, json, os, sys, glob, statistics as st
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
try:
    from powerwin import test_watts   # local: timed-rep board W, same method as Phase 0/0.5
except ImportError:
    test_watts = None
out = sys.argv[1]; L = []
ENV = dict(l.strip().split("=", 1) for l in open(os.path.join(out, "env.txt")) if "=" in l)
erows = {(r["model"], r["test"]): r for r in csv.DictReader(open(os.path.join(out, "energy.csv")))}
status = {k: r["status"] for k, r in erows.items()}
bench, bw = {}, {}
for p in glob.glob(os.path.join(out, "*.jsonl")):
    m, t = os.path.basename(p)[:-6].rsplit(".", 1)   # local: rsplit, model names contain dots (qwen3.8-27b)
    recs = [json.loads(l) for l in open(p) if l.strip().startswith("{")]
    if recs:
        bench[(m, t)] = recs[-1]["avg_ts"]
        e = erows.get((m, t), {})
        if test_watts: bw[(m, t)] = test_watts(out, m, t, recs[-1], float(e["t_end"]) if e.get("t_end") else None)
models = sorted({m for m, _ in status})
tests = ["tg128", "tg128@d4096", "tg128@d8192", "tg128@d16384", "tg128@d32768"]
L += [f"# Phase 1 summary ({ENV.get('run_id', '')})", "", f"## Decode tok/s by context depth ({ENV.get('backend', 'vulkan')}, fa={ENV.get('fa', '0')}; OOM = did not fit)", "",
      "| Model | " + " | ".join(t.replace("tg128@d", "@").replace("tg128", "@0") for t in tests) + " |",
      "|---|" + "---|" * len(tests)]
for m in models:
    cells = []
    for t in tests:
        s = status.get((m, t)); v = bench.get((m, t))
        cells.append(f"{v:.2f}" if v else ("OOM" if s == "oom" else (s or "-")))
    L.append(f"| {m} | " + " | ".join(cells) + " |")
if bw:   # local: board W over the timed reps for the decode tests
    L += ["", "## Decode board W (timed reps)", "", "| Model | " + " | ".join(t.replace("tg128@d", "@").replace("tg128", "@0") for t in tests) + " |",
          "|---|" + "---|" * len(tests)]
    for m in models: L.append(f"| {m} | " + " | ".join(f"{bw[(m, t)]:.1f}" if bw.get((m, t)) else "-" for t in tests) + " |")
sp = os.path.join(out, "serve.csv")
if os.path.exists(sp):
    rows = list(csv.DictReader(open(sp))); g = {}
    for r in rows: g.setdefault((r["model"], int(r["prompt_tokens"])), []).append(r)
    L += ["", "## llama-server (median of reps)", "", "| Model | Prompt tokens | TTFT s | Prompt tok/s | Gen tok/s | Board W |", "|---|---|---|---|---|---|"]
    for (m, n), rs in sorted(g.items()):
        med = lambda k: st.median(float(x[k]) for x in rs if x[k] not in ("", None))
        try: bw = f"{med('board_w'):.0f}"
        except Exception: bw = ""
        L.append(f"| {m} | {n} | {med('ttft_s'):.2f} | {med('prompt_tok_s'):.0f} | {med('gen_tok_s'):.2f} | {bw} |")
ip = os.path.join(out, "idle_loaded.csv")
if os.path.exists(ip):
    L += ["", "## Idle board power with model loaded (30 s)", "", "| Model | W |", "|---|---|"]
    for r in csv.DictReader(open(ip)):
        L.append(f"| {r['model']} | {float(r['loaded_idle_w']):.1f} |" if r["loaded_idle_w"] else f"| {r['model']} | n/a |")
open(os.path.join(out, "phase1_summary.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L))
