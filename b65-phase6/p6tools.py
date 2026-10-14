#!/usr/bin/env python3
"""Phase 6 helpers: coding | regen | summary. Reuses p5tools (stream, exact_prompt, append, post) and quality (graders)."""
import argparse, csv, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quality as Q, p5tools as P

SYSMSG = {"role": "system", "content": "Reply with only one ```python code block containing the full solution. No explanation."}

def coding(a):
    tasks = json.load(open("tasks/coding.json"))[: a.limit or None]
    H = ["model", "task", "try", "pass", "finish_reason", "completion_tokens", "seconds", "err", "reasoning_chars"]   # local: reasoning_chars shows whether thinking was really off
    for t in tasks:
        for i in range(a.tries):
            # local: the same system message as Phase 3's coding section (quality.py), so the scores compare like for like
            body = {"messages": [SYSMSG, {"role": "user", "content": t["prompt"]}], "max_tokens": 4096, "temperature": 0 if i == 0 else 0.3,
                    "seed": 2000 + i, "chat_template_kwargs": {"enable_thinking": False}}
            t0 = time.time()
            try: d = json.load(P.post(a.port, "/v1/chat/completions", body, timeout=1800))   # local: one failed request is a fail, not a lost model
            except Exception as e: d = {"choices": [{"message": {"content": ""}, "finish_reason": f"error {e}"[:80]}]}
            s = time.time() - t0
            m = d["choices"][0]["message"]; ok, err = Q.run_test(Q.code_from(m.get("content") or ""), t["test"])
            P.append(a.out, H, [a.model, t["id"], i, int(ok), d["choices"][0].get("finish_reason"), d.get("usage", {}).get("completion_tokens"), round(s, 1), err.replace("\n", " ")[:200], len(m.get("reasoning_content") or "")])
            print(f"  {a.model} {t['id']} try {i}: {'PASS' if ok else 'FAIL'} {d.get('usage',{}).get('completion_tokens')} tok {s:.0f}s", flush=True)

def regen(a):
    """Build an N-turn chat, then measure 3 non-append edits: regen (identical resend), edit-last (change final user msg), edit-early (change turn 3)."""
    H = ["model", "backend", "cfg", "step", "ctx_tokens", "prompt_n_processed", "ttft_s", "server_prompt_ms"]
    block = P.exact_prompt(a.port, 1500); sysm = {"role": "system", "content": "You are a concise SEO assistant. Answer in two sentences."}
    def ask(msgs, step):
        tt, _, tim, txt = P.stream(a.port, "/v1/chat/completions", {"messages": msgs, "max_tokens": 64, "temperature": 0, "cache_prompt": True,
                                                                   "chat_template_kwargs": {"enable_thinking": False}})
        P.append(a.out, H, a.label.split(",") + [step, tim.get("cache_n", 0) + tim.get("prompt_n", 0), tim.get("prompt_n", ""), round(tt or -1, 3), round(tim.get("prompt_ms", -1), 1)])
        print(f"  {a.label} {step}: reprocessed={tim.get('prompt_n')} ttft={(tt or -1):.2f}s", flush=True); return Q.strip_think(txt)
    users = [f"Turn {t} notes:\n{block}\nQuestion {t}: summarize the main risk in these notes." for t in range(1, a.turns + 1)]
    msgs = [sysm]
    for t, u in enumerate(users, 1):
        msgs.append({"role": "user", "content": u}); r = ask(msgs, f"turn{t}")
        if t < a.turns: msgs.append({"role": "assistant", "content": r})
    ask(msgs, "regen")                                  # identical resend: should reprocess ~1 token
    ask(msgs, "regen2")
    m2 = msgs[:-1] + [{"role": "user", "content": users[-1].replace("main risk", "main opportunity")}]
    ask(m2, "edit-last")                                # tail edit: should reprocess ~last turn
    k = min(3, a.turns); m3 = [dict(x) for x in msgs]; m3[2 * k - 1]["content"] = users[k - 1].replace("main risk", "biggest win")
    ask(m3, "edit-early")                               # early edit: must reprocess from turn k on
    ask(msgs, "back-to-original")                       # return to the original chat after the edit

def summary(a):
    o = a.out; print(f"# Phase 6 summary ({os.path.basename(o)})\n\n```\n{open(os.path.join(o,'env.txt')).read()}```\n")
    p = os.path.join(o, "A_coding.csv")
    if os.path.exists(p):
        rows = list(csv.DictReader(open(p))); print("## A. Coding, thinking off (10 tasks x tries)\n\n| model | pass | greedy pass | failed tasks | median tokens | total s |\n|---|---|---|---|---|---|")
        for m in dict.fromkeys(r["model"] for r in rows):
            rs = [r for r in rows if r["model"] == m]; g = [r for r in rs if r["try"] == "0"]; tok = sorted(int(r["completion_tokens"] or 0) for r in rs)
            fails = sorted({f"{r['task']}(t{r['try']})" for r in rs if r["pass"] == "0"})
            print(f"| {m} | {sum(int(r['pass']) for r in rs)}/{len(rs)} | {sum(int(r['pass']) for r in g)}/{len(g)} | {' '.join(fails) or '-'} | {tok[len(tok)//2]} | {sum(float(r['seconds']) for r in rs):.0f} |")
        print()
    p = os.path.join(o, "B_regen.csv")
    if os.path.exists(p):
        rows = list(csv.DictReader(open(p))); steps = ["regen", "regen2", "edit-last", "edit-early", "back-to-original"]
        print("## B. Regenerate / edit: tokens reprocessed (ttft s)\n\n| model | backend | cfg | ctx | " + " | ".join(steps) + " |\n|---|---|---|---|" + "---|" * len(steps))
        for k in dict.fromkeys((r["model"], r["backend"], r["cfg"]) for r in rows):
            rs = {r["step"]: r for r in rows if (r["model"], r["backend"], r["cfg"]) == k}; ctx = rs.get("regen", {}).get("ctx_tokens", "")
            print(f"| {' | '.join(k)} | {ctx} | " + " | ".join(f"{rs[s]['prompt_n_processed']} ({rs[s]['ttft_s']})" if s in rs else "-" for s in steps) + " |")
        print()
    p = os.path.join(o, "C_canary.csv")
    if os.path.exists(p):
        b = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline_ub2048.json")))
        print("## C. Canary at ub 2048 vs Phase 5 baseline (flag > 5%)\n\n| model | test | baseline | now | drift | flag |\n|---|---|---|---|---|---|")
        for r in csv.DictReader(open(p)):
            base = b.get(r["model"], {}).get(r["test"])
            if r["tok_s"] == "FAIL" or not base: print(f"| {r['model']} | {r['test']} | {base} | {r['tok_s']} | | !! |"); continue
            d = (float(r["tok_s"]) / base - 1) * 100; print(f"| {r['model']} | {r['test']} | {base} | {r['tok_s']} | {d:+.1f}% | {'!!' if abs(d) > 5 else 'ok'} |")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("coding"); [s.add_argument(x, **k) for x, k in [("--port", {}), ("--model", {}), ("--out", {}), ("--tries", {"type": int, "default": 3}), ("--limit", {"type": int, "default": 0})]]
    s = sp.add_parser("regen"); [s.add_argument(x, **k) for x, k in [("--port", {}), ("--label", {}), ("--out", {}), ("--turns", {"type": int, "default": 6})]]
    s = sp.add_parser("summary"); s.add_argument("out")
    a = ap.parse_args(); {"coding": coding, "regen": regen, "summary": summary}[a.cmd](a)
