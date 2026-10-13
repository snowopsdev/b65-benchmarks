#!/usr/bin/env python3
"""Compare canary.csv to baseline.json (SYCL ub512 rows). Flag |drift| > 5%. Also tabulates ub2048 and Vulkan rows."""
import csv, json, sys, os
out = sys.argv[1]; base = json.load(open(os.path.join(os.path.dirname(__file__), "baseline.json")))
rows = list(csv.DictReader(open(f"{out}/canary.csv"))); env = open(f"{out}/env.txt").read()
L = ["# Phase 4 canary (" + os.path.basename(out) + ")", "", "```", env.strip(), "```", "",
     "## Drift vs baseline (SYCL fa1, ub 512; flag = more than 5%)", "", "| Model | Test | Baseline | Now | Drift | W | Flag |", "|---|---|---|---|---|---|---|"]
flags = 0
for r in rows:
    if r["backend"] != "sycl" or r["ub"] != "512": continue
    b = base.get(r["model"], {}).get(r["test"])
    if b is None: continue   # local: no baseline for this test (e.g. pp4096 from the micro-batch check); it shows in the ub table
    if r["tok_s"] in ("FAIL", "") : L.append(f"| {r['model']} | {r['test']} | {b} | FAIL | | | **!!** |"); flags += 1; continue
    now = float(r["tok_s"]); d = (now - b) / b * 100 if b else 0; f = abs(d) > 5; flags += f
    L.append(f"| {r['model']} | {r['test']} | {b} | {now:.2f} | {d:+.1f}% | {r['board_w']} | {'**!!**' if f else 'ok'} |")
ub = [r for r in rows if r["ub"] == "2048" or r["backend"] == "vulkan"]
if ub:
    L += ["", "## Micro-batch check", "", "| Backend | Model | Test | ub | tok/s | W |", "|---|---|---|---|---|---|"]
    L += [f"| {r['backend']} | {r['model']} | {r['test']} | {r['ub']} | {r['tok_s']} | {r['board_w']} |" for r in ub]
    sy = {(r["model"], r["test"], r["ub"]): r["tok_s"] for r in rows if r["backend"] == "sycl"}
    for (m, t, u), v in list(sy.items()):
        if u == "2048" and (m, t, "512") in sy:
            try: L.append(f"- {m} {t}: ub2048 vs ub512 = {(float(v)/float(sy[(m,t,'512')])-1)*100:+.1f}%")
            except ValueError: pass
L += ["", f"**{flags} flagged.** " + ("Investigate before trusting new numbers; rerun once to rule out noise." if flags else "Nothing drifted more than 5%.")]
open(f"{out}/canary_summary.md", "w").write("\n".join(L) + "\n"); print("\n".join(L))
