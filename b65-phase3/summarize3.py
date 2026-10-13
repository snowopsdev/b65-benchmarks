#!/usr/bin/env python3
"""Scores table + blind A/B packet (writing outputs shuffled, key kept separately)."""
import json, glob, sys, random, os
out = sys.argv[1]; R = [json.load(open(p)) for p in sorted(glob.glob(f"{out}/*.quality.json"))]
L = ["# Phase 3 quality summary", "", "| Model | Coding | Tools | Notes recall | Total s |", "|---|---|---|---|---|"]
for r in R:
    f = lambda k: f"{sum(x['pass'] for x in r[k])}/{len(r[k])}"
    t = sum(x["s"] for k in ("coding", "tools", "notes", "writing") for x in r[k])
    L.append(f"| {r['model']} | {f('coding')} | {f('tools')} | {f('notes')} | {t:.0f} |")
L += ["", "Failures:"] + [f"- {r['model']} {x['id']}: {x.get('why') or x.get('err','')[-120:] or x.get('answer','')[:120]}"
       for r in R for k in ("coding", "tools", "notes") for x in r[k] if not x["pass"]]
open(f"{out}/phase3_summary.md", "w").write("\n".join(L) + "\n"); print("\n".join(L))
rng = random.Random(1013); pk, key = ["# Blind writing packet: rank each prompt's answers best to worst", ""], {}
if R:
    for i, w in enumerate(R[0]["writing"]):
        entries = [(r["model"], r["writing"][i]["text"]) for r in R]; rng.shuffle(entries)
        pk += [f"## {w['id']}", ""]; key[w["id"]] = {}
        for j, (m, t) in enumerate(entries):
            lab = "ABC"[j]; key[w["id"]][lab] = m; pk += [f"### {lab}", "", t, ""]
    open(f"{out}/blind_packet.md", "w").write("\n".join(pk)); json.dump(key, open(f"{out}/.blind_key.json", "w"), indent=1)
