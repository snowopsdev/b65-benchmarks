#!/usr/bin/env python3
"""Phase 3 quality checks against a running llama-server (OpenAI-compatible API).
Sections: coding (exec tests), tools (auto-graded), notes (recall over tasks/notes/*.md), writing (saved for blind A/B).
Temperature 0. Results -> <out>/<model>.quality.json"""
import argparse, json, os, re, subprocess, sys, tempfile, time, urllib.request, glob

def chat(port, messages, tools=None, max_tokens=1024):
    body = {"messages": messages, "temperature": 0, "max_tokens": max_tokens}
    if tools: body["tools"] = tools; body["tool_choice"] = "auto"
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=900) as r: d = json.load(r)
    return d["choices"][0]["message"], time.time() - t

def strip_think(s):
    return re.sub(r"<think>.*?</think>", "", s or "", flags=re.S).strip()

def code_from(s):
    s = strip_think(s); m = re.findall(r"```(?:python|py)?\n(.*?)```", s, re.S)
    return max(m, key=len) if m else s

def run_test(code, test):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code + "\n\n" + test + "\nprint('PASS')\n"); p = f.name
    try:
        r = subprocess.run([sys.executable, p], capture_output=True, text=True, timeout=20)
        return r.returncode == 0 and "PASS" in r.stdout, (r.stderr or "")[-400:]
    except subprocess.TimeoutExpired: return False, "timeout"
    finally: os.unlink(p)

def norm(v): return v.lower().strip() if isinstance(v, str) else v

def grade_tool(msg, exp):
    calls = msg.get("tool_calls") or []
    if exp["name"] is None: return not calls, "no-call expected"
    if not calls: return False, "no tool call"
    fn = calls[0]["function"]
    if fn["name"] != exp["name"]: return False, f"wrong tool {fn['name']}"
    try: args = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
    except Exception: return False, "bad json args"
    a = {k: norm(v) for k, v in args.items()}
    for k, v in exp.get("args", {}).items():
        if a.get(k) != norm(v): return False, f"{k}={a.get(k)!r}"
    for k, v in exp.get("args_contains", {}).items():
        if norm(v) not in str(a.get(k, "")): return False, f"{k} missing {v}"
    return True, ""

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--port", default="8099"); ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--tasks", default="tasks"); ap.add_argument("--dry", action="store_true")
    o = ap.parse_args(); T = o.tasks; res = {"model": o.model, "coding": [], "tools": [], "notes": [], "writing": []}
    lim = (lambda x: x[:2]) if o.dry else (lambda x: x)
    sysmsg = {"role": "system", "content": "Reply with only one ```python code block containing the full solution. No explanation."}
    coding = json.load(open(f"{T}/coding.json"))
    if os.path.exists(f"{T}/coding_repo.json"): coding += json.load(open(f"{T}/coding_repo.json"))
    for c in lim(coding):
        m, dt = chat(o.port, [sysmsg, {"role": "user", "content": c["prompt"]}], max_tokens=2048)
        ok, err = run_test(code_from(m.get("content")), c["test"])
        res["coding"].append({"id": c["id"], "pass": ok, "err": err, "s": round(dt, 2)}); print(o.model, c["id"], "PASS" if ok else "FAIL", flush=True)
    tj = json.load(open(f"{T}/tools.json"))
    for c in lim(tj["cases"]):
        try:
            m, dt = chat(o.port, [{"role": "user", "content": c["prompt"]}], tools=tj["tools"], max_tokens=1024); ok, why = grade_tool(m, c["expect"])
        except Exception as e: ok, why, dt = False, f"error {e}", 0
        res["tools"].append({"id": c["id"], "pass": ok, "why": why, "s": round(dt, 2)}); print(o.model, c["id"], "PASS" if ok else f"FAIL {why}", flush=True)
    corpus = "\n\n".join(open(p).read() for p in sorted(glob.glob(f"{T}/notes/*.md")))
    for c in lim(json.load(open(f"{T}/notes.json"))):
        m, dt = chat(o.port, [{"role": "system", "content": "Answer from these notes only, in one short sentence.\n\n" + corpus},
                              {"role": "user", "content": c["q"]}], max_tokens=1024)
        a = strip_think(m.get("content")).lower(); ok = any(x.lower() in a for x in c["expect_any"])
        res["notes"].append({"id": c["id"], "pass": ok, "answer": a[:300], "s": round(dt, 2)}); print(o.model, c["id"], "PASS" if ok else "FAIL", flush=True)
    for c in lim(json.load(open(f"{T}/writing.json"))):
        m, dt = chat(o.port, [{"role": "user", "content": c["prompt"]}], max_tokens=2048)
        res["writing"].append({"id": c["id"], "text": strip_think(m.get("content")), "s": round(dt, 2)})
    json.dump(res, open(f"{o.out}/{o.model}.quality.json", "w"), indent=1)

if __name__ == "__main__": main()
