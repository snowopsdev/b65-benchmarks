#!/usr/bin/env python3
"""Summarize a Gemma llama-server rerun (raw/p1-swa-*) against the Phase 1 baseline run. Writes rerun_summary.md."""
import csv, os, statistics, sys
out = sys.argv[1].rstrip("/")
env = dict(l.strip().split("=", 1) for l in open(f"{out}/env.txt") if "=" in l)
base = os.path.join(os.path.dirname(out), env.get("baseline_run", ""), "serve.csv")
SIZES = (512, 4096, 16384)
def med(rows, k):
    v = [float(r[k]) for r in rows if r.get(k) not in ("", None)]
    return statistics.median(v) if v else None
def table(path, model):
    rows = [r for r in csv.DictReader(open(path)) if r["model"] == model] if os.path.exists(path) else []
    res = {}
    for n in SIZES:
        sel = [r for r in rows if abs(int(float(r["prompt_tokens"] or 0)) - n) <= max(64, n // 20)]
        if sel: res[n] = {k: med(sel, k) for k in ("ttft_s", "prompt_tok_s", "gen_tok_s", "board_w")} | {"reps": len(sel)}
    return res
model = env.get("model", "gemma-4-31b-qat")
variants = list(csv.DictReader(open(f"{out}/variants.csv")))
tabs = [("baseline (p1-20261012-180308)", table(base, model), None)]
for v in variants:
    tabs.append((f"{v['variant']} ({v['flags'] or 'defaults'})", table(f"{out}/{v['variant']}/serve.csv", model), v))
f = lambda x, d=2: "" if x is None else f"{x:.{d}f}"
L = [f"# Gemma llama-server rerun: {env.get('run_id')}", "",
     f"{env.get('date')} · {env.get('llama_server')} · fa=0 · ctx {env.get('ctx')} · median of reps", "",
     "| Config | Prompt | TTFT s | Prompt tok/s | Gen tok/s | Board W | Reps |", "|---|---|---|---|---|---|---|"]
for name, t, _ in tabs:
    for n in SIZES:
        r = t.get(n)
        L.append(f"| {name} | {n} | " + (f"{f(r['ttft_s'])} | {f(r['prompt_tok_s'], 0)} | {f(r['gen_tok_s'])} | {f(r['board_w'], 0)} | {r['reps']} |" if r else "not run | | | | |"))
L += ["", "## Loaded idle (30 s) and VRAM", "", "| Variant | Status | Idle W | VRAM MiB |", "|---|---|---|---|"]
for v in variants:
    L.append(f"| {v['variant']} | {v['status']} | {f(float(v['loaded_idle_w']), 1) if v['loaded_idle_w'] else ''} | {v['vram_used_mib']} |")
open(f"{out}/rerun_summary.md", "w").write("\n".join(L) + "\n"); print("\n".join(L))
