#!/usr/bin/env python3
"""Merge a raw run into results.csv and draw the Phase 0 charts. Re-running on a run replaces that run's rows."""
import csv, json, sys, glob, os
from powerwin import test_watts
out = sys.argv[1].rstrip("/"); run_id = os.path.basename(out)
env = dict(l.strip().split("=", 1) for l in open(f"{out}/env.txt") if "=" in l)
energy = {(r["model"], r["test"]): r for r in csv.DictReader(open(f"{out}/energy.csv"))}

rows = []
for (model, test), e in energy.items():
    base = dict(run_id=run_id, date=env.get("date"), kernel=env.get("kernel"), mesa=env.get("mesa"),
                model=model, quant=e["quant"], file=e["file"], test=test, status=e["status"])
    f = f"{out}/{model}.{test}.jsonl"
    recs = [json.loads(l) for l in open(f) if l.strip().startswith("{")] if os.path.exists(f) else []
    if e["status"] != "ok" or not recs:
        rows.append(dict(base, status=e["status"] if e["status"] != "ok" else "no_output"))
        continue
    for j in recs:
        ts = j.get("avg_ts"); depth = j.get("n_depth", 0) or 0
        jpt = ""
        watts = test_watts(out, model, test, j, float(e["t_end"]) if e.get("t_end") else None)
        if watts and ts: jpt = ts / watts  # tokens per joule of GPU board energy, prefill and decode
        inv_w = float(e["energy_j"]) / float(e["seconds"]) if e.get("energy_j") and e.get("seconds") else ""
        rows.append(dict(base, llama_build=j.get("build_number") or j.get("build_commit"),
            llama_commit=j.get("build_commit"), backend=j.get("backends"), gpu=j.get("gpu_info"),
            n_prompt=j.get("n_prompt"), n_gen=j.get("n_gen"), n_depth=depth,
            tok_s=ts, tok_s_sd=j.get("stddev_ts"), reps=len(j.get("samples_ts") or []),
            board_w_avg=watts, tok_per_joule=jpt, invocation_w_avg=inv_w, invocation_s=e["seconds"]))

FIELDS = ["run_id", "date", "kernel", "mesa", "llama_build", "llama_commit", "backend", "gpu", "model", "quant",
          "file", "test", "status", "n_prompt", "n_gen", "n_depth", "tok_s", "tok_s_sd", "reps",
          "board_w_avg", "tok_per_joule", "invocation_w_avg", "invocation_s"]
# idempotent: drop any earlier rows for this run, then append the fresh ones
old = [r for r in csv.DictReader(open("results.csv"))] if os.path.exists("results.csv") else []
kept = [r for r in old if r.get("run_id") != run_id]
with open("results.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
    w.writeheader(); w.writerows(kept); w.writerows(rows)
print(f"{len(rows)} rows written to results.csv" + (f" (replaced {len(old) - len(kept)})" if len(old) != len(kept) else ""))
for r in rows:
    print(f"  {r['model']:<18} {r['test']:<13} {r['status']:<8} "
          + (f"{r['tok_s']:8.2f} ± {r['tok_s_sd']:.2f} tok/s" if r.get("tok_s") else "")
          + (f"  {r['board_w_avg']:.1f} W" if r.get("board_w_avg") else ""))

try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
except ImportError:
    print("matplotlib missing; skip charts (pacman -S python-matplotlib)"); sys.exit(0)
os.makedirs("charts", exist_ok=True)
build = next((r["llama_build"] for r in rows if r.get("llama_build")), "")
foot = (f"Arc Pro B65 32GB | llama.cpp Vulkan b{build} | {env.get('mesa', '')} | kernel {env.get('kernel', '')}"
        f" | PCIe {env.get('pcie_link', '').split(' (')[0]} | {env.get('date', '')[:10]} | run {run_id}")
for kind, title in (("pp", "Prefill (prompt processing) tok/s"), ("tg", "Decode (generation) tok/s")):
    sel = [r for r in rows if r["test"].startswith(kind)]
    if not sel: continue
    tests = sorted({r["test"] for r in sel}, key=lambda t: (len(t), t))
    order = [l.split("|")[0] for l in open("models.conf") if l.strip() and not l.startswith("#")]
    models = sorted({r["model"] for r in sel}, key=lambda m: order.index(m) if m in order else len(order))
    fig, ax = plt.subplots(figsize=(16, 9), dpi=100); wbar = 0.8 / len(models)
    for i, m in enumerate(models):
        cell = {r["test"]: r for r in sel if r["model"] == m}
        xs = [k + i * wbar for k in range(len(tests))]
        vals = [cell[t]["tok_s"] if t in cell and cell[t].get("tok_s") else 0 for t in tests]
        errs = [cell[t].get("tok_s_sd") or 0 if t in cell else 0 for t in tests]
        color = ("#2a78d6", "#eb6834", "#1baf7a")[order.index(m) % 3] if m in order else None
        b = ax.bar(xs, vals, wbar, yerr=errs, capsize=4, label=m, color=color)
        ax.bar_label(b, labels=[f"{v:.1f}" if v else ("failed" if t in cell else "") for v, t in zip(vals, tests)],
                     padding=3)
    ax.set_xticks([k + wbar * (len(models) - 1) / 2 for k in range(len(tests))], tests)
    ax.set_title(title, fontsize=20); ax.set_ylabel("tokens / second"); ax.legend()
    fig.text(0.01, 0.01, foot, fontsize=9, color="gray"); fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(f"charts/{run_id}-{kind}.png"); print(f"chart: charts/{run_id}-{kind}.png")
