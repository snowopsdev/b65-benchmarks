# Agent-shaped decode test: N tokens of real source code as context, then a coding request; thinking off, greedy.
import json, sys, time, urllib.request
from tokenizers import Tokenizer
base, model, tokpath, srcpath, out = sys.argv[1:6]; sizes = [int(x) for x in sys.argv[6].split(",")]
tok = Tokenizer.from_file(tokpath); ids = tok.encode(open(srcpath).read()).ids
ask = "\n\nAbove is part of a Zig codebase. Write a Python script that reads a safetensors index JSON file and prints each tensor name with its shard, sorted by shard, with argparse and error handling. Only code."
rows = []
for n in sizes:
    for rep in range(2):
        ctx = tok.decode(ids[rep * 97: rep * 97 + n])   # a different slice per rep, so no prompt-cache hit
        body = {"model": model, "stream": True, "temperature": 0, "max_tokens": 512, "stream_options": {"include_usage": True},
                "chat_template_kwargs": {"enable_thinking": False},
                "messages": [{"role": "user", "content": ctx + ask}]}
        req = urllib.request.Request(base + "/v1/chat/completions", json.dumps(body).encode(), {"content-type": "application/json"})
        t0 = time.time(); first = last = None; usage = None
        with urllib.request.urlopen(req, timeout=1800) as r:
            for line in r:
                line = line.strip()
                if not line.startswith(b"data:") or line == b"data: [DONE]": continue
                d = json.loads(line[5:])
                if d.get("usage"): usage = d["usage"]
                for c in d.get("choices", []):
                    if (c.get("delta") or {}).get("content"):
                        now = time.time(); first = first or now; last = now
        ct = usage["completion_tokens"]; pt = usage["prompt_tokens"]
        row = {"ctx": n, "rep": rep, "prompt_tokens": pt, "ttft": round(first - t0, 2), "completion": ct, "decode": round((ct - 1) / (last - first), 1)}
        print(row, flush=True); rows.append(row)
json.dump(rows, open(out, "w"), indent=1)
