#!/usr/bin/env python3
"""Streamed /completion requests against llama-server. Measures client TTFT and reads server timings.
Prompts are built from the server's own tokenizer so token counts are exact."""
import argparse, csv, json, os, time, urllib.request
ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int); ap.add_argument("--model"); ap.add_argument("--out")
ap.add_argument("--energy", default=""); ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
base = f"http://127.0.0.1:{a.port}"
def post(path, body):
    return urllib.request.urlopen(urllib.request.Request(base + path, json.dumps(body).encode(),
                                  {"Content-Type": "application/json"}), timeout=3600)
def energy():
    try: return int(open(a.energy).read()) if a.energy else None
    except Exception: return None
filler = ("The quick brown fox audits the warehouse ledger, counts each crate twice, and writes the totals "
          "into a notebook before the night shift arrives. ")
def prompt_of(n):
    toks = json.load(post("/tokenize", {"content": filler * (n // 10 + 50)}))["tokens"]
    return json.load(post("/detokenize", {"tokens": toks[:n]}))["content"]
sizes = [512] if a.dry else [512, 4096, 16384]
reps = 1 if a.dry else 3
path = os.path.join(a.out, "serve.csv"); new = not os.path.exists(path)
with open(path, "a", newline="") as fh:
    w = csv.writer(fh)
    if new: w.writerow(["model", "prompt_tokens", "rep", "ttft_s", "prompt_tok_s", "gen_tokens", "gen_tok_s", "total_s", "board_w"])
    for n in sizes:
        p = prompt_of(n)
        for r in range(reps):
            body = {"prompt": p, "n_predict": 128, "stream": True, "cache_prompt": False,
                    "temperature": 0, "ignore_eos": True}
            e0, t0 = energy(), time.perf_counter(); ttft = None; timings = {}
            with post("/completion", body) as resp:
                for line in resp:
                    line = line.decode().strip()
                    if not line.startswith("data:"): continue
                    d = json.loads(line[5:])
                    if ttft is None and d.get("content"): ttft = time.perf_counter() - t0
                    if d.get("stop"): timings = d.get("timings", {})
            tot = time.perf_counter() - t0; e1 = energy()
            bw = (e1 - e0) / 1e6 / tot if e0 is not None and e1 is not None else ""
            w.writerow([a.model, timings.get("prompt_n", n), r + 1, round(ttft or 0, 3),
                        round(timings.get("prompt_per_second", 0), 2), timings.get("predicted_n", ""),
                        round(timings.get("predicted_per_second", 0), 2), round(tot, 3), round(bw, 1) if bw else ""])
            fh.flush(); print(f"   {a.model} {n} tok rep{r+1}: ttft {ttft:.2f}s, gen {timings.get('predicted_per_second',0):.2f} tok/s")
