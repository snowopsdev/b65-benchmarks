#!/usr/bin/env python3
"""Phase 9 part T: decode by prompt depth, shaped like SergiioB's XPU_ATTN_PREF receipt (TensorFold fork, B70).
Code and prose prompts at ~68 / 8K / 32K / 131K tokens, 512 tokens out, greedy, thinking off, one stream.
Streamed decode tok/s after the first token; text sha256 so drafted vs "draft": false and default vs switch can be compared.
Usage: tf_depth.py BASE MODEL TOKENIZER CODE_SRC PROSE_SRC OUT.json LABEL [--sizes 68,8000,32600,131000] [--reps 2] [--nodraft 8000,32600]
"""
import argparse, hashlib, json, os, sys, time, urllib.request
from tokenizers import Tokenizer

ap = argparse.ArgumentParser()
for a in ("base", "model", "tokenizer", "code_src", "prose_src", "out", "label"): ap.add_argument(a)
ap.add_argument("--sizes", default="68,8000,32600,131000")
ap.add_argument("--reps", type=int, default=2)
ap.add_argument("--nodraft", default="8000,32600", help='sizes that also run once with "draft": false')
ap.add_argument("--gen", type=int, default=512)
a = ap.parse_args()
tok = Tokenizer.from_file(a.tokenizer)
ASK = {"code": "\n\nAbove is part of a Zig codebase. Write a Python script that reads a safetensors index JSON file and prints each "
               "tensor name with its shard, sorted by shard, with argparse and error handling. Only code.",
       "prose": "\n\nAbove are notes from a benchmarking project. Write a clear, detailed essay on what makes a GPU benchmark "
                "trustworthy, with examples."}
SRC = {"code": tok.encode(open(a.code_src).read()).ids, "prose": tok.encode(open(a.prose_src).read()).ids}

def prompt(kind, n):
    ask = ASK[kind]; na = len(tok.encode(ask).ids)
    if n <= na + 16: return ask.strip()                       # the "68-token" cell: the request alone
    body = SRC[kind][: n - na]
    assert len(body) == n - na, f"{kind} source too short for {n}"
    return tok.decode(body) + ask

def run(kind, n, draft=True):
    body = {"model": a.model, "stream": True, "temperature": 0, "max_tokens": a.gen, "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False}, "messages": [{"role": "user", "content": prompt(kind, n)}]}
    if not draft: body["draft"] = False
    req = urllib.request.Request(a.base + "/v1/chat/completions", json.dumps(body).encode(), {"content-type": "application/json"})
    t0 = time.time(); first = last = None; usage = None; text = []; extra = {}
    with urllib.request.urlopen(req, timeout=3600) as r:
        for line in r:
            line = line.strip()
            if not line.startswith(b"data:") or line == b"data: [DONE]": continue
            d = json.loads(line[5:])
            if d.get("usage"): usage = d["usage"]
            for k in ("token_sha", "timings", "spec", "draft_stats"):
                if k in d: extra[k] = d[k]
            for c in d.get("choices", []):
                piece = (c.get("delta") or {}).get("content")
                if piece:
                    now = time.time(); first = first or now; last = now; text.append(piece)
    ct, pt = usage["completion_tokens"], usage["prompt_tokens"]
    txt = "".join(text)
    return {"label": a.label, "kind": kind, "target": n, "draft": draft, "prompt_tokens": pt, "completion_tokens": ct,
            "ttft_s": round(first - t0, 3), "decode_tok_s": round((ct - 1) / (last - first), 2),
            "text_sha256": hashlib.sha256(txt.encode()).hexdigest(), **extra}

rows = json.load(open(a.out)) if os.path.exists(a.out) else []
def keep(r):
    print(json.dumps(r), flush=True); rows.append(r); json.dump(rows, open(a.out, "w"), indent=1)
w = run("code", 68); w["warmup"] = True; keep(w)                # one discarded warmup per server
sizes = [int(x) for x in a.sizes.split(",")]; nod = {int(x) for x in a.nodraft.split(",") if x}
for n in sizes:
    for kind in ("code", "prose"):
        for rep in range(a.reps if n < 100000 else 1):          # 131K: one rep (as the receipt), cold prefill is minutes
            r = run(kind, n); r["rep"] = rep; keep(r)
        if n in nod:
            r = run(kind, n, draft=False); r["rep"] = 0; keep(r)
