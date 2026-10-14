#!/usr/bin/env python3
"""Run the registry's six lab gates (local-ai-registry lab/lab.py `gates`, unmodified) against a running server.
Usage: gates.py --lab <registry clone>/lab/lab.py --endpoint http://127.0.0.1:8099 --ctx 32768 --out result.json"""
import argparse, hashlib, importlib.util, json, sys, time

ap = argparse.ArgumentParser()
ap.add_argument("--lab", required=True); ap.add_argument("--endpoint", required=True)
ap.add_argument("--ctx", type=int, required=True); ap.add_argument("--out", required=True); ap.add_argument("--label", default="")
a = ap.parse_args()
spec = importlib.util.spec_from_file_location("lab", a.lab); lab = importlib.util.module_from_spec(spec); spec.loader.exec_module(lab)
t0 = time.time()
try:
    passed, proof, ev = lab.gates(a.endpoint, {"ctx": a.ctx})
    err = None
except Exception as e:  # a gate that crashes is a fail, kept with its reason
    passed, proof, ev, err = False, {}, {}, f"{type(e).__name__}: {e}"
out = {"label": a.label, "ctx": a.ctx, "passed": passed, "proof": proof, "evidence": ev, "error": err,
       "seconds": round(time.time() - t0, 1), "lab_sha256": hashlib.sha256(open(a.lab, "rb").read()).hexdigest()}
json.dump(out, open(a.out, "w"), indent=1)
ok = (ev or {}).get("ok", {})
print(f">> {a.label}: {'PASS' if passed else 'FAIL'}  " + " ".join(f"{g}={'y' if ok.get(g) else 'n'}" for g in lab.GATES)
      + (f"  tps={proof.get('tps')} prefill={proof.get('prefill')}" if proof else "") + (f"  error={err}" if err else ""))
sys.exit(0)
