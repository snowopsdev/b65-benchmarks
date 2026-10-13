#!/usr/bin/env python3
"""Phase 2 summary: per model and test, Vulkan fa0 vs SYCL fa0/fa1 tok/s, plus board W and tok/J. Writes phase2_summary.md + backend_compare.csv."""
import csv, json, os, sys, glob
out = sys.argv[1]
en = {(r["backend"], r["fa"], r["test"], r["model"]): r for r in csv.DictReader(open(os.path.join(out, "energy.csv")))}
data, rows = {}, []
for p in glob.glob(os.path.join(out, "*.jsonl")):
    m, b, fa, t = os.path.basename(p)[:-6].split(".", 3); fa = fa[2:]
    recs = [json.loads(l) for l in open(p) if l.strip().startswith("{")]
    if not recs: continue
    ts = recs[-1]["avg_ts"]; e = en.get((b, fa, t, m), {})
    w = float(e["energy_j"]) / float(e["seconds"]) if e.get("energy_j") and e.get("seconds") else None
    data[(m, t, f"{b}/fa{fa}")] = ts
    rows.append(dict(model=m, backend=b, fa=fa, test=t, tok_s=round(ts, 2), sd=round(recs[-1]["stddev_ts"], 3),
                     board_w=round(w, 1) if w else "", tok_per_j=round(ts / w, 4) if w else ""))
if rows:
    with open(os.path.join(out, "backend_compare.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
cols = ["vulkan/fa0", "sycl/fa0", "sycl/fa1"]
status = {(k[3], k[2], f"{k[0]}/fa{k[1]}"): v["status"] for k, v in en.items()}
L = ["# Phase 2 summary: Vulkan vs SYCL (tok/s)", "", "| Model | Test | " + " | ".join(cols) + " | SYCL best vs Vulkan |", "|---|---|---|---|---|---|"]
for m, t in sorted({(k[0], k[1]) for k in status}):
    c = [f"{data[(m,t,x)]:.2f}" if (m, t, x) in data else (status.get((m, t, x)) or "-") for x in cols]
    v = data.get((m, t, "vulkan/fa0")); sb = max([data[(m, t, x)] for x in cols[1:] if (m, t, x) in data] or [0])
    L.append(f"| {m} | {t} | " + " | ".join(c) + f" | {((sb/v-1)*100):+.0f}% |" if v and sb else f"| {m} | {t} | " + " | ".join(c) + " | - |")
open(os.path.join(out, "phase2_summary.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L))
