#!/usr/bin/env python3
"""Phase 9 part L summary: old (b11574) vs new (v1.0.0) per backend/model/test from results.csv, as a markdown table."""
import csv, sys, os, collections

out = sys.argv[1]
rows = list(csv.DictReader(open(os.path.join(out, "results.csv"))))
cell = collections.OrderedDict()
for r in rows:
    k = (r["backend"], r["model"], r["test"])
    cell.setdefault(k, {})[r["build"]] = r

def f(v):
    try: return float(v)
    except (TypeError, ValueError): return None

print(f"# Phase 9 part L: llama.cpp b11574 vs v1.0.0 ({os.path.basename(out)})\n")
print("| backend | model | test | b11574 tok/s | v1.0.0 tok/s | change | b11574 W | v1.0.0 W |")
print("|---|---|---|---:|---:|---:|---:|---:|")
gains = collections.defaultdict(list)
for (be, m, t), d in cell.items():
    o, n = d.get("old", {}), d.get("new", {})
    a, b = f(o.get("tok_s")), f(n.get("tok_s"))
    fmt = lambda r, v: "FAIL" if r.get("tok_s") == "FAIL" else (f"{v:.2f} ± {f(r.get('sd')) or 0:.2f}" if v else "")
    ch = f"{(b / a - 1) * 100:+.1f}%" if a and b else ""
    if a and b: gains[(be, "pp" if t.startswith("pp") else "tg")].append(b / a)
    print(f"| {be} | {m} | {t} | {fmt(o, a)} | {fmt(n, b)} | {ch} | {o.get('board_w', '')} | {n.get('board_w', '')} |")
print()
for (be, kind), g in sorted(gains.items()):
    gm = 1.0
    for x in g: gm *= x
    gm **= 1 / len(g)
    print(f"- {be} {'prefill' if kind == 'pp' else 'decode'}: geometric mean {(gm - 1) * 100:+.1f}% over {len(g)} tests")
