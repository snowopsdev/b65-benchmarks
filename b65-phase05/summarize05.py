#!/usr/bin/env python3
"""Summarize the FA sweep: tok/s, avg board W and tok/J per test (prefill AND decode), plus the faster FA per model."""
import csv, json, sys, os, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
try:
    from powerwin import test_watts   # local: timed-rep board W, same method as Phase 0
except ImportError:
    test_watts = None
out = sys.argv[1]
energy = {(r["model"], r["fa"], r["test"]): r for r in csv.DictReader(open(os.path.join(out, "energy.csv")))}
rows = []
for p in sorted(glob.glob(os.path.join(out, "*.jsonl"))):
    name, fa, test = os.path.basename(p)[:-6].split(".fa", 1)[0], None, None
    rest = os.path.basename(p)[:-6].split(".fa", 1)[1]; fa, test = rest.split(".", 1)
    recs = [json.loads(l) for l in open(p) if l.strip().startswith("{")]
    if not recs: continue
    r = recs[-1]; ts = r["avg_ts"]
    e = energy.get((name, fa, test), {})
    inv = None
    if e.get("energy_j") and e.get("seconds"):
        inv = float(e["energy_j"]) / float(e["seconds"])   # invocation-average board W (includes load)
    w = test_watts(out, name, f"fa{fa}.{test}", r, float(e["t_end"]) if e.get("t_end") else None) if test_watts else None
    rows.append(dict(model=name, fa=fa, test=test, tok_s=round(ts, 2), sd=round(r["stddev_ts"], 3),
                     board_w=round(w, 1) if w else "", tok_per_j=round(ts / w, 4) if w else "",
                     invocation_w=round(inv, 1) if inv else ""))
with open(os.path.join(out, "fa_sweep.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(f"{'model':18} {'test':14} {'fa=0':>9} {'fa=1':>9}  faster")
by = {}
for r in rows: by.setdefault((r["model"], r["test"]), {})[r["fa"]] = r["tok_s"]
for (m, t), v in sorted(by.items()):
    a, b = v.get("0"), v.get("1")
    best = "" if a is None or b is None else ("fa=0" if a > b else "fa=1")
    print(f"{m:18} {t:14} {a if a is not None else '-':>9} {b if b is not None else '-':>9}  {best}")
