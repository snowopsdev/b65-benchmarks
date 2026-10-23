#!/usr/bin/env python3
"""Phase 7 client: the same measurements against any OpenAI-compatible server (llama-server, vLLM, Strata).

  speed   single stream: prompt 512/4K/16K/32K tokens, 256 generated, 3 reps (+1 warmup)
  conc    N requests released together (1/2/4/8): 512-token prompts, 256 generated, aggregate and per-stream tok/s
  coding  tasks/coding.json, 3 tries each, thinking off: pass rate, plus decode speed on real answers
  summary medians per label -> <out>/summary.md

Everything is timed on the client from the stream, so no engine's own timings are trusted over another's.
Prompts are windows of this repo's own markdown (real, non-repeating text), cut to exact token counts with the
model's tokenizer.json; each rep starts at a different offset, so no prefix cache can serve it.
Generation uses ignore_eos so every engine produces the same number of tokens; a row whose server returns fewer
is kept but marked short=1. --chat (servers without /v1/completions or ignore_eos, e.g. Strata) sends the same window
as a user message asking for a continuation, thinking off; it stops when the model does, so short rows are expected
and every engine compared in chat mode gets the identical request."""
import argparse, csv, glob, json, os, statistics as S, sys, threading, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quality as Q

HERE = os.path.dirname(os.path.abspath(__file__))
SYSMSG = {"role": "system", "content": "Reply with only one ```python code block containing the full solution. No explanation."}

def post(a, path, body, timeout=3600):
    h = {"Content-Type": "application/json"}
    if a.api_key: h["Authorization"] = f"Bearer {a.api_key}"
    return urllib.request.urlopen(urllib.request.Request(a.base + path, json.dumps(body).encode(), h), timeout=timeout)

def energy(a):
    try: return int(open(a.energy).read()) if a.energy else None
    except OSError: return None

def stream(a, path, body):
    """Streams one request. Returns dict: t_start, ttft, t_first, t_last, text, usage, finish."""
    body = dict(body, model=a.model, stream=True, stream_options={"include_usage": True})
    r = {"t_start": time.perf_counter(), "ttft": None, "t_first": None, "t_last": None, "usage": {}, "finish": None, "chunks": 0}
    text = []
    with post(a, path, body) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if not line.startswith("data:"): continue
            p = line[5:].strip()
            if p == "[DONE]": break
            d = json.loads(p)
            if d.get("usage"): r["usage"] = d["usage"]
            for c in d.get("choices") or []:
                piece = c.get("text") or ""
                dl = c.get("delta") or {}
                piece += (dl.get("content") or "") + (dl.get("reasoning_content") or dl.get("reasoning") or "")
                if piece:
                    now = time.perf_counter()
                    if r["t_first"] is None: r["t_first"] = now; r["ttft"] = now - r["t_start"]
                    r["t_last"] = now; r["chunks"] += 1; text.append(piece)
                if c.get("finish_reason"): r["finish"] = c["finish_reason"]
    r["t_end"] = time.perf_counter(); r["text"] = "".join(text)
    return r

def decode_tps(r):
    n = r["usage"].get("completion_tokens") or 0
    dt = (r["t_last"] or 0) - (r["t_first"] or 0)
    return (n - 1) / dt if n > 1 and dt > 0 else 0.0

class Prompts:
    """Exact-length prompts cut from the repo's markdown with the model's own tokenizer."""
    def __init__(self, tokenizer_json):
        from tokenizers import Tokenizer
        self.tok = Tokenizer.from_file(tokenizer_json)
        root = os.path.dirname(HERE)
        files = sorted(glob.glob(f"{root}/findings/*.md") + glob.glob(f"{root}/b65-*/README.md") + glob.glob(f"{root}/b65-*/HANDOFF.md"))
        self.ids = self.tok.encode("\n\n".join(open(f).read() for f in files), add_special_tokens=False).ids
    def get(self, n, rep):
        start = (rep * 7919 + n) % len(self.ids)                    # a different window for every (size, rep)
        ids = (self.ids[start:] + self.ids) * (n // len(self.ids) + 2)
        return self.tok.decode(ids[:n])

H_SPEED = ["label", "test", "prompt_target", "prompt_tokens", "conc", "rep", "ttft_s", "prefill_tok_s", "gen_tokens",
           "decode_tok_s", "total_s", "agg_tok_s", "board_w", "short", "finish", "head"]

def write(a, name, rows):
    path = os.path.join(a.out, name); new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f); new and w.writerow(H_SPEED); [w.writerow(r) for r in rows]

CHAT_ASK = "Continue the following document exactly where it stops, in the same style. Write at least 400 more words.\n\n"

def completion_body(prompt, gen):
    return {"prompt": prompt, "max_tokens": gen, "temperature": 0, "ignore_eos": True}

def chat_body(prompt, gen):
    return {"messages": [{"role": "user", "content": CHAT_ASK + prompt}], "max_tokens": gen, "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False}}

def gen_req(a, prompt, gen):
    return ("/v1/chat/completions", chat_body(prompt, gen)) if a.chat else ("/v1/completions", completion_body(prompt, gen))

def speed(a):
    P = Prompts(a.tokenizer)
    stream(a, *gen_req(a, P.get(256, 99), 32))          # warmup (JIT, graph capture)
    for n in a.sizes:
        for rep in range(a.reps):
            e0 = energy(a); r = stream(a, *gen_req(a, P.get(n, rep), a.gen)); e1 = energy(a)
            pt = r["usage"].get("prompt_tokens") or n; gt = r["usage"].get("completion_tokens") or 0
            bw = round((e1 - e0) / 1e6 / (r["t_end"] - r["t_start"]), 1) if e0 is not None and e1 is not None else ""
            write(a, "speed.csv", [[a.label, "single", n, pt, 1, rep + 1, round(r["ttft"] or 0, 3),
                   round(pt / r["ttft"], 1) if r["ttft"] else 0, gt, round(decode_tps(r), 2),
                   round(r["t_end"] - r["t_start"], 2), "", bw, int(gt < a.gen), r["finish"], r["text"][:60].replace("\n", " ")]])
            print(f"  {a.label} pp{n} rep{rep+1}: ttft {r['ttft'] or 0:.2f}s  decode {decode_tps(r):.1f} tok/s  ({gt} tok)", flush=True)

def conc(a):
    P = Prompts(a.tokenizer)
    stream(a, *gen_req(a, P.get(256, 99), 32))
    for c in a.levels:
        for rep in range(a.reps):
            res = [None] * c
            def one(i): res[i] = stream(a, *gen_req(a, P.get(a.conc_prompt, 1000 + rep * 64 + i), a.gen))
            th = [threading.Thread(target=one, args=(i,)) for i in range(c)]
            e0 = energy(a); [t.start() for t in th]; [t.join() for t in th]; e1 = energy(a)
            t0 = min(r["t_start"] for r in res); t1 = max(r["t_end"] for r in res)
            tot = sum(r["usage"].get("completion_tokens") or 0 for r in res)
            bw = round((e1 - e0) / 1e6 / (t1 - t0), 1) if e0 is not None and e1 is not None else ""
            agg = round(tot / (t1 - t0), 1)
            write(a, "conc.csv", [[a.label, "conc", a.conc_prompt, r["usage"].get("prompt_tokens"), c, rep + 1, round(r["ttft"] or 0, 3), "",
                   r["usage"].get("completion_tokens"), round(decode_tps(r), 2), round(r["t_end"] - r["t_start"], 2), agg, bw,
                   int((r["usage"].get("completion_tokens") or 0) < a.gen), r["finish"], ""] for r in res])
            print(f"  {a.label} C{c} rep{rep+1}: aggregate {agg} tok/s, per-stream median {S.median(decode_tps(r) for r in res):.1f}", flush=True)

def coding(a):
    tasks = json.load(open(os.path.join(HERE, "tasks/coding.json")))[: a.limit or None]
    H = ["label", "task", "try", "pass", "finish", "completion_tokens", "ttft_s", "decode_tok_s", "seconds", "reasoning_chars", "err"]
    path = os.path.join(a.out, "coding.csv"); new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f); new and w.writerow(H)
        for t in tasks:
            for i in range(a.tries):
                body = {"messages": [SYSMSG, {"role": "user", "content": t["prompt"]}], "max_tokens": 4096,
                        "temperature": 0 if i == 0 else 0.3, "seed": 2000 + i, "chat_template_kwargs": {"enable_thinking": False}}
                try: r = stream(a, "/v1/chat/completions", body); err = ""
                except Exception as e: r = {"text": "", "usage": {}, "finish": "error", "ttft": None, "t_first": None, "t_last": None, "t_start": 0, "t_end": 0}; err = str(e)[:120]
                ok, terr = Q.run_test(Q.code_from(r["text"]), t["test"])
                think = len(r["text"]) - len(Q.strip_think(r["text"]))
                w.writerow([a.label, t["id"], i, int(ok), r["finish"], r["usage"].get("completion_tokens"), round(r["ttft"] or 0, 2),
                            round(decode_tps(r), 2), round(r["t_end"] - r["t_start"], 1), think, (err or terr).replace("\n", " ")[:200]])
                f.flush(); print(f"  {a.label} {t['id']} try {i}: {'PASS' if ok else 'FAIL'}  {decode_tps(r):.1f} tok/s", flush=True)

def summary(a):
    def rows(name):
        p = os.path.join(a.out, name)
        return list(csv.DictReader(open(p))) if os.path.exists(p) else []
    med = lambda xs: round(S.median(xs), 1) if xs else "–"
    out = ["# Phase 7 summary (medians)", ""]
    sp = rows("speed.csv")
    if sp:
        out += ["## Single stream", "", "| label | prompt | TTFT s | prefill tok/s | decode tok/s | board W | short |", "|---|---|---|---|---|---|---|"]
        for (l, n) in dict.fromkeys((r["label"], r["prompt_target"]) for r in sp):
            g = [r for r in sp if r["label"] == l and r["prompt_target"] == n]
            out.append(f"| {l} | {n} | {med([float(r['ttft_s']) for r in g])} | {med([float(r['prefill_tok_s']) for r in g])} | "
                       f"{med([float(r['decode_tok_s']) for r in g])} | {med([float(r['board_w']) for r in g if r['board_w']])} | {sum(int(r['short']) for r in g)} |")
    cc = rows("conc.csv")
    if cc:
        out += ["", "## Concurrency (512-token prompts)", "", "| label | streams | aggregate tok/s | per-stream decode tok/s | TTFT s |", "|---|---|---|---|---|"]
        for (l, c) in dict.fromkeys((r["label"], r["conc"]) for r in cc):
            g = [r for r in cc if r["label"] == l and r["conc"] == c]
            out.append(f"| {l} | {c} | {med(list({float(r['agg_tok_s']) for r in g}))} | {med([float(r['decode_tok_s']) for r in g])} | {med([float(r['ttft_s']) for r in g])} |")
    cd = rows("coding.csv")
    if cd:
        out += ["", "## Coding (thinking off)", "", "| label | pass | decode tok/s on answers |", "|---|---|---|"]
        for l in dict.fromkeys(r["label"] for r in cd):
            g = [r for r in cd if r["label"] == l]
            out.append(f"| {l} | {sum(int(r['pass']) for r in g)}/{len(g)} | {med([float(r['decode_tok_s']) for r in g if float(r['decode_tok_s']) > 0])} |")
    open(os.path.join(a.out, "summary.md"), "w").write("\n".join(out) + "\n"); print("\n".join(out))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("speed", "conc", "coding", "summary"):
        s = sp.add_parser(name); s.add_argument("--out", required=True)
        if name == "summary": continue
        s.add_argument("--base", default="http://127.0.0.1:8080"); s.add_argument("--model", required=True)
        s.add_argument("--label", required=True); s.add_argument("--api-key", default=os.environ.get("API_KEY", ""))
        s.add_argument("--energy", default=""); s.add_argument("--reps", type=int, default=3); s.add_argument("--gen", type=int, default=256)
        if name in ("speed", "conc"):
            s.add_argument("--tokenizer", required=True, help="the model's tokenizer.json")
            s.add_argument("--chat", action="store_true", help="chat continuation instead of /v1/completions + ignore_eos")
        if name == "speed": s.add_argument("--sizes", type=lambda v: [int(x) for x in v.split(",")], default=[512, 4096, 16384, 32768])
        if name == "conc":
            s.add_argument("--levels", type=lambda v: [int(x) for x in v.split(",")], default=[1, 2, 4, 8])
            s.add_argument("--conc-prompt", type=int, default=512)
        if name == "coding": s.add_argument("--tries", type=int, default=3); s.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    {"speed": speed, "conc": conc, "coding": coding, "summary": summary}[a.cmd](a)
