#!/usr/bin/env python3
"""Compare canary.csv to baseline.json (SYCL ub512 rows). Flag |drift| > 5%. Also tabulates ub2048 and Vulkan rows."""
import csv, json, sys, os
out = sys.argv[1]; D = os.path.dirname(os.path.abspath(__file__)); base = json.load(open(os.path.join(D, "baseline.json")))
b2 = {k: v for k, v in json.load(open(os.path.join(D, "baseline_ub2048.json"))).items() if not k.startswith("_")}
rows = list(csv.DictReader(open(f"{out}/canary.csv"))); env = open(f"{out}/env.txt").read()
L = ["# Canary (" + os.path.basename(out) + ")", "", "```", env.strip(), "```", "",
     "## Drift vs baseline (SYCL fa1; ub 512 vs baseline.json, ub 2048 vs baseline_ub2048.json; flag = more than 5%)", "", "| Model | Test | ub | Baseline | Now | Drift | W | Flag |", "|---|---|---|---|---|---|---|---|"]
flags = 0
for r in rows:
    if r["backend"] != "sycl" or r["ub"] not in ("512", "2048"): continue
    b = (base if r["ub"] == "512" else b2).get(r["model"], {}).get(r["test"])
    if b is None: continue
    if r["tok_s"] in ("FAIL", "") : L.append(f"| {r['model']} | {r['test']} | {r['ub']} | {b} | FAIL | | | **!!** |"); flags += 1; continue
    now = float(r["tok_s"]); d = (now - b) / b * 100 if b else 0; f = abs(d) > 5; flags += f
    L.append(f"| {r['model']} | {r['test']} | {r['ub']} | {b} | {now:.2f} | {d:+.1f}% | {r['board_w']} | {'**!!**' if f else 'ok'} |")
# local: the micro-batch table only when there is something to compare (both ubs on SYCL, or Vulkan rows); at UB=2048 alone it would just repeat the drift table
ub = [r for r in rows if r["ub"] != rows[0]["ub"] or r["backend"] == "vulkan"] if rows else []
ub = [r for r in rows if r["ub"] == "2048" or r["backend"] == "vulkan"] if ub else []
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
