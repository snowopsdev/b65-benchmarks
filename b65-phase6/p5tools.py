#!/usr/bin/env python3
"""Phase 5 helpers: mkbaseline | ttft | multiturn | think | summary. Talks to llama-server on 127.0.0.1."""
import argparse, csv, glob, json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quality as Q

def post(port, path, body, timeout=900):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)

def stream(port, path, body):
    """Returns wall TTFT (s), total s, last timings dict, generated text."""
    body = dict(body, stream=True); t0 = time.time(); ttft = None; tim = {}; text = []
    with post(port, path, body) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data:"): continue
            p = line[5:].strip()
            if p == "[DONE]": break
            d = json.loads(p); tim = d.get("timings", tim) or tim
            piece = d.get("content") or ""
            if "choices" in d and d["choices"]:
                dl = d["choices"][0].get("delta", {}); piece = (dl.get("content") or "") + (dl.get("reasoning_content") or "")
            if piece:
                if ttft is None: ttft = time.time() - t0
                text.append(piece)
    return ttft, time.time() - t0, tim, "".join(text)

def exact_prompt(port, n):
    filler = ("The quick brown fox audits canonical tags and schema markup on every page. " * (n // 8 + 20))
    toks = json.load(post(port, "/tokenize", {"content": filler}))["tokens"][:n]
    return json.load(post(port, "/detokenize", {"tokens": toks}))["content"]

def append(path, header, row):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f); new and w.writerow(header); w.writerow(row)

def mkbaseline(a):
    out = {}
    for r in csv.DictReader(open(a.csv)):
        if r["tok_s"] not in ("", "FAIL"): out.setdefault(r["model"], {})[r["test"]] = float(r["tok_s"])
    json.dump({"note": "Phase 5 baseline: SYCL fa1, -b 2048 -ub 2048", "results": out}, open(a.out, "w"), indent=2)

def ttft(a):
    H = ["model", "backend", "cfg", "prompt_tokens", "rep", "cached", "ttft_s", "server_prompt_ms", "prompt_n"]
    for n in [int(x) for x in a.sizes.split()][: (2 if a.dry else None)]:
        p = exact_prompt(a.port, n)
        for rep in range(a.reps):
            for cached in (False, True):  # cold (no reuse) then the identical prompt with cache on
                tt, _, tim, _ = stream(a.port, "/completion", {"prompt": p, "n_predict": 1, "cache_prompt": cached, "temperature": 0})
                append(a.out, H, a.label.split(",") + [n, rep, int(cached), round(tt or -1, 3), round(tim.get("prompt_ms", -1), 1), tim.get("prompt_n", "")])
            print(f"  {a.label} n={n} rep={rep} ttft={tt:.3f}s")

def multiturn(a):
    """8-turn chat, each user turn adds ~1.5k tokens of notes. Measures how much of the prompt is reprocessed per turn."""
    H = ["model", "backend", "cfg", "turn", "ctx_tokens", "prompt_n_processed", "ttft_s", "server_prompt_ms", "decode_tok_s"]
    block = exact_prompt(a.port, 1500); msgs = [{"role": "system", "content": "You are a concise SEO assistant. Answer in two sentences."}]
    for t in range(1, a.turns + 1):
        msgs.append({"role": "user", "content": f"Turn {t} notes:\n{block}\nQuestion {t}: summarize the main risk in these notes."})
        tt, _, tim, txt = stream(a.port, "/v1/chat/completions", {"messages": msgs, "max_tokens": 96, "temperature": 0, "cache_prompt": True,
                                                              "chat_template_kwargs": {"enable_thinking": False}})
        msgs.append({"role": "assistant", "content": Q.strip_think(txt)})
        ctx = tim.get("cache_n", 0) + tim.get("prompt_n", 0)
        append(a.out, H, a.label.split(",") + [t, ctx, tim.get("prompt_n", ""), round(tt or -1, 3), round(tim.get("prompt_ms", -1), 1), round(tim.get("predicted_per_second", 0), 2)])
        print(f"  {a.label} turn {t}: ctx~{ctx} reprocessed={tim.get('prompt_n')} ttft={tt:.2f}s")

THINK = [  # name, max_tokens, extra sampler
    ("think-4k", 4096, {}), ("think-8k", 8192, {}), ("think-16k", 16384, {}),
    ("think-8k-pp1.5", 8192, {"presence_penalty": 1.5}),
    ("think-8k-qwen-sampler", 8192, {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0}),
]
def think(a):
    task = [x for x in json.load(open("tasks/coding.json")) if x["id"] == "c08"][0]
    H = ["variant", "try", "pass", "finish_reason", "completion_tokens", "reasoning_chars", "seconds", "err"]
    variants = [("nothink", 2048, {})] if a.only == "nothink" else THINK
    for name, mt, extra in variants:
        for i in range(a.tries):
            body = {"messages": [{"role": "user", "content": task["prompt"]}], "max_tokens": mt, "temperature": 0, "seed": 1000 + i}
            body.update(extra)
            if extra.get("temperature") is None and i > 0: body["temperature"] = 0.3  # vary tries beyond the first greedy one
            t0 = time.time(); d = json.load(post(a.port, "/v1/chat/completions", body, timeout=3600)); s = time.time() - t0
            m = d["choices"][0]["message"]; ok, err = Q.run_test(Q.code_from(m.get("content") or ""), task["test"])
            append(a.out, H, [name, i, int(ok), d["choices"][0].get("finish_reason"), d.get("usage", {}).get("completion_tokens"),
                              len(m.get("reasoning_content") or ""), round(s, 1), err.replace("\n", " ")[:200]])
            print(f"  {name} try {i}: pass={ok} finish={d['choices'][0].get('finish_reason')} tokens={d.get('usage',{}).get('completion_tokens')} {s:.0f}s")

def summary(a):
    o = a.out; print(f"# Phase 5 summary ({os.path.basename(o)})\n\n```\n{open(os.path.join(o,'env.txt')).read()}```\n")
    def table(fn, title, keys, agg):
        p = os.path.join(o, fn)
        if not os.path.exists(p): return
        rows = list(csv.DictReader(open(p))); print(f"## {title}\n"); groups = {}
        for r in rows: groups.setdefault(tuple(r[k] for k in keys), []).append(r)
        cols = list(agg.keys()); print("| " + " | ".join(keys + cols) + " |"); print("|" + "---|" * (len(keys) + len(cols)))
        for g, rs in groups.items(): print("| " + " | ".join(list(g) + [f(rs) for f in agg.values()]) + " |")
        print()
    med = lambda c: (lambda rs: f"{sorted(float(r[c]) for r in rs)[len(rs)//2]:.3f}")
    table("A_baseline.csv", "A. New baseline (SYCL fa1, ub 2048)", ["model", "test"], {"tok_s": lambda rs: rs[0]["tok_s"], "W": lambda rs: rs[0]["board_w"]})
    table("B_ttft.csv", "B. Gemma TTFT, median of reps (cached=1 means identical prompt reused)", ["backend", "cfg", "prompt_tokens", "cached"], {"ttft_s": med("ttft_s"), "server_prompt_ms": med("server_prompt_ms")})
    table("C_multiturn.csv", "C. Multi-turn: tokens reprocessed per turn", ["model", "backend", "cfg"],
          {"turns": lambda rs: str(len(rs)), "reprocessed/turn (t2+)": lambda rs: "/".join(r["prompt_n_processed"] for r in rs[1:]),
           "last ttft_s": lambda rs: rs[-1]["ttft_s"], "last ctx": lambda rs: rs[-1]["ctx_tokens"]})
    table("D_think.csv", "D. Qwen c08 thinking", ["variant"], {"pass": lambda rs: f"{sum(int(r['pass']) for r in rs)}/{len(rs)}",
          "hit cap": lambda rs: str(sum(r["finish_reason"] == "length" for r in rs)), "median tokens": med("completion_tokens"), "median s": med("seconds")})

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("mkbaseline"); s.add_argument("csv"); s.add_argument("out")
    s = sp.add_parser("ttft"); [s.add_argument(x, **k) for x, k in [("--port", {}), ("--label", {}), ("--out", {}), ("--reps", {"type": int, "default": 5}), ("--sizes", {"default": "16 64 256 1024 4096"}), ("--dry", {"action": "store_true"})]]
    s = sp.add_parser("multiturn"); [s.add_argument(x, **k) for x, k in [("--port", {}), ("--label", {}), ("--out", {}), ("--turns", {"type": int, "default": 8})]]
    s = sp.add_parser("think"); [s.add_argument(x, **k) for x, k in [("--port", {}), ("--out", {}), ("--tries", {"type": int, "default": 5}), ("--only", {"default": ""})]]
    s = sp.add_parser("summary"); s.add_argument("out")
    a = ap.parse_args(); {"mkbaseline": mkbaseline, "ttft": ttft, "multiturn": multiturn, "think": think, "summary": summary}[a.cmd](a)
