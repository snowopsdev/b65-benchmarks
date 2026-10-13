#!/usr/bin/env python3
"""Phase 2 summary: per model and test, Vulkan fa0 vs SYCL fa0/fa1 tok/s, plus board W and tok/J. Writes phase2_summary.md + backend_compare.csv.
Local changes: model names contain dots (qwen3.8-27b), so tags are split from the right; board W is averaged over the
timed reps (stamped --progress + 10 Hz trace, same as Phases 0-1), with the whole-invocation average kept alongside."""
import csv, json, os, sys, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from powerwin import test_watts  # noqa: E402
out = sys.argv[1].rstrip("/")
en = {(r["backend"], r["fa"], r["test"], r["model"]): r for r in csv.DictReader(open(os.path.join(out, "energy.csv")))}
data, rows = {}, []
for p in glob.glob(os.path.join(out, "*.jsonl")):
    m, b, fa, t = os.path.basename(p)[:-6].rsplit(".", 3); fa = fa[2:]
    recs = [json.loads(l) for l in open(p) if l.strip().startswith("{")]
    e = en.get((b, fa, t, m), {})
    if not recs or e.get("status", "ok") != "ok": continue
    j = recs[-1]; ts = j["avg_ts"]
    w = test_watts(out, f"{m}.{b}.fa{fa}", t, j, float(e["t_end"]) if e.get("t_end") else None) or None
    inv = float(e["energy_j"]) / float(e["seconds"]) if e.get("energy_j") and e.get("seconds") else None
    data[(m, t, f"{b}/fa{fa}")] = ts
    rows.append(dict(model=m, backend=b, fa=fa, test=t, tok_s=round(ts, 2), sd=round(j["stddev_ts"], 3),
                     board_w=round(w, 1) if w else "", tok_per_j=round(ts / w, 4) if w else "",
                     invocation_w=round(inv, 1) if inv else "", gpu_info=j.get("gpu_info", "")))
rows.sort(key=lambda r: (r["model"], r["test"], r["backend"], r["fa"]))
if rows:
    with open(os.path.join(out, "backend_compare.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
cols = ["vulkan/fa0", "sycl/fa0", "sycl/fa1"]
status = {(k[3], k[2], f"{k[0]}/fa{k[1]}"): v["status"] for k, v in en.items()}
L = ["# Phase 2 summary: Vulkan vs SYCL (tok/s)", "", "| Model | Test | " + " | ".join(cols) + " | SYCL best vs Vulkan |", "|---|---|---|---|---|---|"]
for m, t in sorted({(k[0], k[1]) for k in status}, key=lambda k: (k[0], len(k[1]), k[1])):
    c = [f"{data[(m,t,x)]:.2f}" if (m, t, x) in data else (status.get((m, t, x)) or "-") for x in cols]
    v = data.get((m, t, "vulkan/fa0")); sb = max([data[(m, t, x)] for x in cols[1:] if (m, t, x) in data] or [0])
    L.append(f"| {m} | {t} | " + " | ".join(c) + (f" | {((sb/v-1)*100):+.0f}% |" if v and sb else " | - |"))
W = {(r["model"], r["test"], f"{r['backend']}/fa{r['fa']}"): r["board_w"] for r in rows}
L += ["", "## Board W over the timed reps (GPU board power, xe hwmon)", "", "| Model | Test | " + " | ".join(cols) + " |", "|---|---|---|---|---|"]
for m, t in sorted({(k[0], k[1]) for k in status}, key=lambda k: (k[0], len(k[1]), k[1])):
    L.append(f"| {m} | {t} | " + " | ".join(str(W.get((m, t, x)) or "-") for x in cols) + " |")
open(os.path.join(out, "phase2_summary.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L))
