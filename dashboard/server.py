#!/usr/bin/env python3
"""Live B65 Bench dashboard: reads raw/<latest run>/ plus the xe hwmon sensors. Read-only; never touches the GPU.
Usage: python dashboard/server.py [--port 8765]   (binds 127.0.0.1; expose with `tailscale serve`)"""
import csv, glob, json, os, re, sys, threading, time, collections, argparse, statistics
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from powerwin import test_watts  # noqa: E402

RAW = os.environ.get("B65_RAW") or os.path.join(ROOT, "raw")  # override only for testing share cards
CHARTS, HERE = os.path.join(ROOT, "charts"), os.path.dirname(os.path.abspath(__file__))
PROGRESS = re.compile(r"^(\d+\.\d+) llama-bench: benchmark \d+/\d+: (.+)$")


# --- live sensors: 1 Hz sampler over the xe hwmon (card energy, temps, fan) ---
def find_xe():
    for h in sorted(os.listdir("/sys/class/hwmon")):
        d = f"/sys/class/hwmon/{h}"
        try:
            if open(f"{d}/name").read().strip() != "xe": continue
        except OSError: continue
        files = {}
        for f in os.listdir(d):
            if f.endswith("_label"):
                files[open(f"{d}/{f}").read().strip() + ":" + f.split("_")[0][:4]] = f"{d}/{f[:-6]}_input"
        return {"energy": files.get("card:ener"), "pkg": files.get("pkg:temp"), "vram": files.get("vram:temp"),
                "fan": f"{d}/fan1_input" if os.path.exists(f"{d}/fan1_input") else None}
    return {}

XE = find_xe()
HIST = collections.deque(maxlen=1800)  # 30 min at 1 Hz: [t, watts, pkg C, vram C, fan rpm]

def read_num(p):
    try: return float(open(p).read())
    except (OSError, TypeError, ValueError): return None

def sampler():
    last = None
    while True:
        t, e = time.time(), read_num(XE.get("energy"))
        w = None
        if last and e is not None and t > last[0]: w = (e - last[1]) / 1e6 / (t - last[0])
        last = (t, e) if e is not None else None
        pkg, vram, fan = (read_num(XE.get(k)) for k in ("pkg", "vram", "fan"))
        if w is not None:
            HIST.append([round(t, 2), round(w, 1), pkg and pkg / 1000, vram and vram / 1000, fan])
        time.sleep(1)


# --- run state from raw/<run_id>/ ---
def pid_alive(pid):
    try: return "run.sh" in open(f"/proc/{pid}/cmdline").read()
    except (OSError, ValueError): return False

def read_lines(p):
    try: return open(p).read().splitlines()
    except OSError: return []

def run_state(out):
    run_id = os.path.basename(out)
    env = dict(l.split("=", 1) for l in read_lines(f"{out}/env.txt") if "=" in l)
    energy = {}
    if os.path.exists(f"{out}/energy.csv"):
        for r in csv.DictReader(open(f"{out}/energy.csv")): energy[(r["model"], r["test"])] = r
    pid = (read_lines(f"{out}/pid") or [""])[0].strip()
    if os.path.exists(f"{out}/done"): state = "finished"
    elif pid and pid_alive(pid): state = "running"
    else: state = "stopped"
    cur = (read_lines(f"{out}/current") or [""])[0].split("|") if state == "running" else []
    plan = [tuple(l.split("|")) for l in read_lines(f"{out}/plan.txt") if "|" in l]
    if not plan:  # runs from before plan.txt existed
        plan = list(energy.keys())
    tests = []
    for model, test in plan:
        row = dict(model=model, test=test, status="pending")
        if test == "spotcheck":
            txt = "\n".join(read_lines(f"{out}/{model}.spotcheck.txt")).strip()
            if txt: row.update(status="ok", text=txt)
            if cur[:2] == [model, test]: row["status"] = "running"
            tests.append(row); continue
        e = energy.get((model, test))
        if e:
            row.update(status=e["status"], seconds=float(e["seconds"] or 0), exit_code=e["exit_code"])
            jf = f"{out}/{model}.{test}.jsonl"
            recs = [json.loads(l) for l in read_lines(jf) if l.strip().startswith("{")]
            if e["status"] == "ok" and recs:
                j = recs[0]
                w = test_watts(out, model, test, j, float(e["t_end"]) if e.get("t_end") else None)
                row.update(tok_s=j.get("avg_ts"), sd=j.get("stddev_ts"), reps=len(j.get("samples_ns") or []), watts=w or None,
                           tpj=(j["avg_ts"] / w) if w and test.startswith("tg") else None)
            elif e["status"] == "ok":
                row["status"] = "no_output"
            if row["status"] != "ok":
                row["error"] = "\n".join(read_lines(f"{out}/{model}.{test}.log")[-6:])
        elif cur[:2] == [model, test]:
            row["status"] = "running"
            row["started"] = float(cur[2]) if len(cur) > 2 else None
            phase = None
            for l in read_lines(f"{out}/{model}.{test}.log"):
                m = PROGRESS.match(l)
                if m: phase = m.group(2)
            row["phase"] = phase or "loading model"
        tests.append(row)
    return dict(run_id=run_id, state=state, env=env, tests=tests,
                done_at=(read_lines(f"{out}/done") or [None])[0])

def status():
    runs = sorted(d for d in os.listdir(RAW) if os.path.isdir(os.path.join(RAW, d))) if os.path.isdir(RAW) else []
    latest = run_state(os.path.join(RAW, runs[-1])) if runs else None
    charts = sorted(f for f in os.listdir(CHARTS) if f.endswith(".png")) if os.path.isdir(CHARTS) else []
    return dict(now=time.time(), run=latest, runs=runs[::-1], charts=charts[::-1],
                sensors=bool(XE.get("energy")))


# --- share cards: the server decides what is safe to publish ---
DISPLAY = {"qwen3.8-27b": "Qwen3.8 27B", "gemma-4-31b-qat": "Gemma 4 31B QAT", "muse-glimmer": "Muse Glimmer 28B"}

def model_specs():
    """name -> (quant, GGUF size in GB) from models.conf and the files on disk: specs, not measurements."""
    import fnmatch
    files = []
    for base in (os.path.expanduser("~/.lmstudio"), os.path.expanduser("~/.cache/lm-studio")):
        for dp, _, fs in os.walk(base):
            files += [os.path.join(dp, f) for f in fs if f.endswith(".gguf") and "mmproj" not in f]
    specs = {}
    for l in read_lines(os.path.join(ROOT, "models.conf")):
        if not l.strip() or l.startswith("#") or l.count("|") < 2: continue
        name, quant, glob = l.split("|", 2)
        hit = next((f for f in files if fnmatch.fnmatch(os.path.basename(f).lower(), glob.strip().lower())), None)
        specs[name] = (quant, round(os.path.getsize(hit) / 1e9, 1) if hit else None)
    return specs

def power_shape(out, points=150, window_s=900):
    """Unitless 0..1 shape of board power over the last window_s of this run, from its 10 Hz traces."""
    pts = []
    for f in os.listdir(out):
        if f.endswith(".power.csv"):
            for l in read_lines(os.path.join(out, f)):
                try: t, e = l.split(","); pts.append((float(t), float(e)))
                except ValueError: pass
    pts.sort()
    watts = []  # per-sample W; skip deltas across untraced gaps between tests
    for (t0, e0), (t1, e1) in zip(pts, pts[1:]):
        if 0 < t1 - t0 < 1.0: watts.append((t1, (e1 - e0) / 1e6 / (t1 - t0)))
    if not watts: return []
    watts = [w for w in watts if w[0] >= watts[-1][0] - window_s]
    k = max(1, len(watts) // points)
    v = [max(w for _, w in watts[i:i + k]) for i in range(0, len(watts), k)]
    lo, hi = min(v), max(v)
    return [round((x - lo) / (hi - lo), 3) if hi > lo else 0.5 for x in v]

def sh(cmd):
    import subprocess
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError): return ""

# static facts about the machine (config/specs, never measurements); read once at startup
SYSTEM = dict(omarchy=sh(["omarchy-version"]).split("-")[0],
              ram=next((l.split()[-1] for l in sh(["lsmem", "--summary"]).splitlines() if "online memory" in l), ""),
              hyprland=(sh(["hyprctl", "version"]).split() or ["", ""])[1] if sh(["hyprctl", "version"]) else "")

def rig(env):
    """Test-rig card data: hardware and software configuration only."""
    link = env.get("pcie_link", "").split(" (")[0]          # e.g. "16.0 GT/s PCIe x4"
    gen = {"2.5": "1.0", "5.0": "2.0", "8.0": "3.0", "16.0": "4.0", "32.0": "5.0", "64.0": "6.0"}.get(link.split(" ")[0], "")
    width = link.split(" ")[-1] if link else ""
    llama = re.search(r"build (\d+), commit (\w+)\) built with (\S+) ([\d.]+)", env.get("llama_bench", ""))
    return dict(
        gpu="Intel Arc Pro B65", gpu_spec="32 GB GDDR6 · 608 GB/s · 20 Xe2 cores",
        pcie=(f"PCIe {gen} {width}" if gen else link) + (" via chipset slot" if width == "x4" else ""),
        rebar="Resizable BAR on" if env.get("rebar_bar2_mib") == "32768" else ("BAR " + env.get("rebar_bar2_mib", "?") + " MiB"),
        display_gpu="RTX 3080 drives the display, excluded from every test",
        cpu=env.get("cpu", "").replace(" 8-Core Processor", ""), ram=SYSTEM["ram"] and SYSTEM["ram"].replace("G", " GB"),
        os=f"Omarchy {SYSTEM['omarchy']}".strip(), os_detail=f"Arch Linux · Hyprland {SYSTEM['hyprland']}".strip(),
        kernel=env.get("kernel", "").split("-")[0],
        mesa=env.get("mesa", "").replace("mesa 1:", "").split("-")[0],
        llama_build=llama.group(1) if llama else "", llama_commit=llama.group(2)[:7] if llama else "",
        compiler=f"{llama.group(3)} {llama.group(4)}".replace("GNU", "GCC") if llama else "",
        governor=env.get("cpu_governor", ""), args=env.get("bench_args", ""),
        power_cap_w=str(int(env["power1_cap_uw"]) // 1000000) if env.get("power1_cap_uw", "").isdigit() else "")

def spot(out, model):
    """Spot-check generation (the model's own words, no measurements): (prompt, output) or None."""
    txt = "\n".join(read_lines(f"{out}/{model}.spotcheck.txt")).strip()
    # split on the exact prompt from run.sh: some models continue the prompt line instead of starting a new paragraph
    m = re.search(r'spot-check.*?-p "([^"]+)"', open(os.path.join(ROOT, "run.sh")).read(), re.S)
    prompt = m.group(1) if m else txt.split("\n", 1)[0]
    if not txt.startswith(prompt): return None
    output = " ".join(txt[len(prompt):].replace("[end of text]", "").split())
    return dict(prompt=prompt, output=output) if output else None

def holds():
    """(model, test, fa) -> reason for results held back from publishing (holds.conf).
    test may carry a setting: "pp512@fa=1" holds only that setting; a bare test holds every setting.
    Phase 0 ran with flash attention on, so its results count as fa=1."""
    h = {}
    for l in read_lines(os.path.join(ROOT, "holds.conf")):
        if l.strip() and not l.startswith("#") and l.count("|") >= 2:
            m, t, why = l.split("|", 2); t = t.strip()
            test, fa = (t.split("@fa=", 1) + [None])[:2] if "@fa=" in t else (t, None)
            h[(m.strip(), test, fa)] = why.strip()
    return h

def is_held(held, model, test, fa):
    return (model, test, None) in held or (model, test, fa) in held

def p05_status():
    """Phase 0.5 sweep progress for the preview card: counts and state only, never a measured value."""
    base = os.path.join(ROOT, "b65-phase05", "raw")
    runs = sorted(d for d in os.listdir(base) if d.startswith("p05-")) if os.path.isdir(base) else []
    models = [l.split("|")[0] for l in read_lines(os.path.join(ROOT, "b65-phase05", "models.conf")) if l.strip() and not l.startswith("#")]
    total = len(models) * 2 * 4   # fa 0/1 x pp512, pp4096, pp16384, tg128@d16384
    if not runs: return dict(state="not started", done=0, total=total)
    out = os.path.join(base, runs[-1])
    done = max(0, len(read_lines(f"{out}/energy.csv")) - 1)
    pid = (read_lines(f"{out}/pid") or [""])[0].strip()
    alive = False
    try: alive = pid and "phase05" in open(f"/proc/{pid}/cmdline").read()
    except OSError: pass
    state = "finished" if os.path.exists(f"{out}/done") else "running" if alive else "stopped"
    return dict(state=state, done=min(done, total), total=total)

P05_TESTS = ["pp512", "pp4096", "pp16384", "tg128@d16384"]          # main sweep, fa 0 and 1
FU_TESTS = ["tg128", "tg128@d4096"]                                # follow-up (p05b-*), fa 0 only; fa 1 = Phase 0
ALL_TESTS = ["pp512", "pp4096", "pp16384", "tg128", "tg128@d4096", "tg128@d16384"]

def sweep_dir(prefix):
    base = os.path.join(ROOT, "b65-phase05", "raw")
    runs = sorted(d for d in os.listdir(base) if d.startswith(prefix + "-")) if os.path.isdir(base) else []
    return os.path.join(base, runs[-1]) if runs else None

def sweep_state(out):
    if not out: return "not started"
    pid = (read_lines(f"{out}/pid") or [""])[0].strip(); alive = False
    try: alive = bool(pid) and "phase05" in open(f"/proc/{pid}/cmdline").read()
    except OSError: pass
    return "finished" if os.path.exists(f"{out}/done") else "running" if alive else "stopped"

def sweep_cells(out, log_name, state):
    """(model, fa, test) -> cell for one sweep folder, plus the test currently running (if any)."""
    cells, cur = {}, None
    if not out: return cells, cur
    energy = {}
    if os.path.exists(f"{out}/energy.csv"):
        for r in csv.DictReader(open(f"{out}/energy.csv")): energy[(r["model"], r["fa"], r["test"])] = r
    if state == "running":   # last ">>" line in the run log whose row isn't written yet
        starts = [l[3:].split() for l in read_lines(os.path.join(ROOT, "b65-phase05", log_name)) if l.startswith(">> ")]
        if starts:
            m, fa, t = starts[-1][0], starts[-1][1].replace("fa=", ""), starts[-1][2]
            if (m, fa, t) not in energy:
                lines = read_lines(f"{out}/{m}.fa{fa}.{t}.log"); phase = None
                for l in lines:
                    mm = PROGRESS.match(l)
                    if mm: phase = mm.group(2)
                t0 = float(lines[0].split(" ", 1)[0]) if lines and re.match(r"^\d+\.\d+ ", lines[0]) else None
                cur = dict(model=m, fa=fa, test=t, phase=phase or "loading model", started=t0)
    for (m, fa, t), e in energy.items():
        c = dict(status={"ok": "ok", "fail": "failed", "skipped": "skipped"}.get(e["status"], e["status"]),
                 seconds=float(e["seconds"]) if e.get("seconds") else None)
        recs = [json.loads(l) for l in read_lines(f"{out}/{m}.fa{fa}.{t}.jsonl") if l.strip().startswith("{")]
        if c["status"] == "ok" and recs:
            j = recs[-1]
            w = test_watts(out, m, f"fa{fa}.{t}", j, float(e["t_end"]) if e.get("t_end") else None)
            c.update(tok_s=j.get("avg_ts"), sd=j.get("stddev_ts"), watts=w or None)
        elif c["status"] == "failed":
            c["error"] = "\n".join(read_lines(f"{out}/{m}.fa{fa}.{t}.log")[-4:])
        cells[(m, fa, t)] = c
    return cells, cur

def p05_full():
    """Phase 0.5 dashboard data (private dashboard, so measured values are included): the main fa 0/1 sweep plus
    the fa=0 decode follow-up, against Phase 0 (fa on) as the reference."""
    kit = os.path.join(ROOT, "b65-phase05")
    models = [l.split("|")[0] for l in read_lines(os.path.join(kit, "models.conf")) if l.strip() and not l.startswith("#")]
    st = p05_status(); out = sweep_dir("p05"); fu_out = sweep_dir("p05b"); fu_state = sweep_state(fu_out)
    res = dict(state=st["state"], done=st["done"], total=st["total"], models=models, tests=ALL_TESTS,
               run_id=os.path.basename(out) if out else None, env={}, cells=[], provenance=[], current=None,
               followup=dict(state=fu_state, run_id=os.path.basename(fu_out) if fu_out else None, tests=FU_TESTS))
    p0 = {}
    p0runs = sorted(d for d in os.listdir(RAW) if re.match(r"^\d{8}-\d{6}$", d) and os.path.exists(os.path.join(RAW, d, "done"))) if os.path.isdir(RAW) else []
    if p0runs:
        res["phase0_run"] = p0runs[-1]
        for t in run_state(os.path.join(RAW, p0runs[-1]))["tests"]:
            if t.get("tok_s"): p0[(t["model"], t["test"])] = dict(tok_s=t["tok_s"], sd=t["sd"], watts=t.get("watts"))
    if out: res["env"] = dict(l.split("=", 1) for l in read_lines(f"{out}/env.txt") if "=" in l)
    main, cur = sweep_cells(out, "p05-run.log", st["state"])
    fu, fu_cur = sweep_cells(fu_out, "p05b-run.log", fu_state)
    res["current"] = cur or fu_cur
    fu_done = sum(1 for k in fu if k[1] == "0"); res["followup"].update(done=fu_done, total=len(models) * len(FU_TESTS))
    for m in models:
        for t in ALL_TESTS:
            for fa in ("0", "1"):
                c = dict(model=m, test=t, fa=fa, status="pending", ref=p0.get((m, t)) if fa == "1" else None)
                if t in FU_TESTS:
                    c["fu"] = True
                    if fa == "1": c["status"] = "skipped"          # on-value comes from Phase 0 (same build, fa on)
                    else:
                        src, now = fu.get((m, "0", t)), fu_cur
                        if now and (now["model"], now["fa"], now["test"]) == (m, "0", t): c["status"] = "running"
                        elif src: c.update(src)
                else:
                    if cur and (cur["model"], cur["fa"], cur["test"]) == (m, fa, t): c["status"] = "running"
                    elif (m, fa, t) in main: c.update(main[(m, fa, t)])
                res["cells"].append(c)
    if out and os.path.exists(f"{out}/provenance.csv"):
        res["provenance"] = list(csv.DictReader(open(f"{out}/provenance.csv")))
    return res

def p05_share():
    """Phase 0.5 data for share cards. Until the sweep has finished every test, only statuses leave the server
    (failures report as "done"); afterwards numbers are included, except results listed in holds.conf, which are
    held for both flash-attention settings."""
    full = p05_full(); held = holds()
    # completion is the main sweep only; the decode follow-up has its own gate (followup.state)
    complete = full["state"] == "finished" and all(c["status"] not in ("pending", "running") for c in full["cells"] if not c.get("fu"))
    cells = []
    fu_done = full["followup"]["state"] == "finished"
    for c in full["cells"]:
        st = c["status"]
        if not complete or (c.get("fu") and c["fa"] == "0" and not fu_done):
            cells.append(dict(model=c["model"], test=c["test"], fa=c["fa"], status=st if st in ("pending", "running", "skipped") else "done"))
            continue
        if is_held(held, c["model"], c["test"], c["fa"]):
            cells.append(dict(model=c["model"], test=c["test"], fa=c["fa"], status="held")); continue
        o = dict(model=c["model"], test=c["test"], fa=c["fa"], status=st)
        if st == "ok": o.update(tok_s=c.get("tok_s"), sd=c.get("sd"), watts=c.get("watts"))
        # the Phase 0 reference is a flash-attention-on result, so it follows the fa=1 holds
        if c.get("ref") and not is_held(held, c["model"], c["test"], "1"):
            o["ref"] = dict(tok_s=c["ref"]["tok_s"], watts=c["ref"].get("watts"))
        cells.append(o)
    out = os.path.join(ROOT, "b65-phase05", "raw", full["run_id"]) if full["run_id"] else None
    return dict(state=full["state"], complete=complete, done=full["done"], total=full["total"], run_id=full["run_id"],
                followup=dict(state=full["followup"]["state"], done=full["followup"]["done"], total=full["followup"]["total"]),
                tests=full["tests"], models=full["models"], cells=cells,
                provenance=[dict(repo=p["repo"], file=p["file"], hf_commit=p["hf_commit"], match=p["sha_matches_hf"]) for p in full["provenance"]],
                shape=power_shape(out) if out else [])

P1_BENCH = ["tg128", "tg128@d4096", "tg128@d8192", "tg128@d16384", "tg128@d32768"]
P1_SIZES = [512, 4096, 16384]
P1_REPS = 3

P1_VK_RUN = os.path.join(ROOT, "b65-phase1", "raw", "p1-20261012-180308")      # Phase 1 on Vulkan (fa off)
P2_RUN = os.path.join(ROOT, "b65-phase2", "raw", "p2-20261013-091509")          # Phase 2 (SYCL fa1 decode = drift check for 1S)

def jsonl_ts(path):
    recs = [json.loads(l) for l in read_lines(path) if l.strip().startswith("{")]
    return recs[-1].get("avg_ts") if recs else None

def p1_full(kit_name="b65-phase1", run_re=r"^p1-\d{8}-\d{6}$", log_name="p1-run.log", sycl=False):
    """Phase 1 dashboard data (private, measured values included): decode by context depth, llama-server
    TTFT at three prompt sizes, loaded idle power + VRAM. Phase 1 (Vulkan) reads Phase 0.5 fa=0 as a drift check;
    Phase 1S (sycl=True: b65-phase1s, SYCL fa on) reads Phase 2 SYCL fa1 as the drift check and Phase 1 Vulkan for comparison."""
    kit = os.path.join(ROOT, kit_name); base = os.path.join(kit, "raw")
    runs = [d for d in os.listdir(base) if re.match(run_re, d)] if os.path.isdir(base) else []   # main Phase 1 runs only (p1-swa-* is the Gemma rerun)
    models = [l.split("|")[0] for l in read_lines(os.path.join(kit, "models.conf")) if l.strip() and not l.startswith("#")]
    res = dict(state="not started", run_id=None, models=models, bench_tests=P1_BENCH, sizes=P1_SIZES, reps=P1_REPS,
               env={}, bench=[], serve=[], idle=[], current=None, done=0, total=len(models) * (len(P1_BENCH) + 1 + len(P1_SIZES) * P1_REPS),
               dry=False, sycl=sycl)
    if not runs: return res
    run = max(runs, key=lambda r: r[-15:]); out = os.path.join(base, run); res["run_id"] = run
    if "-dry-" in run:   # dry run: first model, tg128 + one 512-token request
        models = res["models"] = models[:1]; res.update(dry=True, bench_tests=["tg128"], sizes=[512], reps=1, total=1 + 1 + 1)
    pid = (read_lines(f"{out}/pid") or [""])[0].strip(); alive = False
    try: alive = bool(pid) and "phase1" in open(f"/proc/{pid}/cmdline").read()
    except OSError: pass
    res["state"] = "finished" if os.path.exists(f"{out}/done") else "running" if alive else "stopped"
    res["env"] = dict(l.split("=", 1) for l in read_lines(f"{out}/env.txt") if "=" in l)
    ref, vk = {}, {}
    if sycl:   # drift check: Phase 2 SYCL fa1 decode; comparison: Phase 1 Vulkan decode + server medians
        for m in models:
            for t in P1_BENCH:
                ref[(m, t)] = jsonl_ts(f"{P2_RUN}/{m}.sycl.fa1.{t}.jsonl")
                vk[(m, t)] = jsonl_ts(f"{P1_VK_RUN}/{m}.{t}.jsonl")
        vrows = list(csv.DictReader(open(f"{P1_VK_RUN}/serve.csv"))) if os.path.exists(f"{P1_VK_RUN}/serve.csv") else []
        res["vk_serve"] = {m: serve_medians(vrows, m) for m in models}
        # Gemma: compare like with like. Phase 1S runs it with --ctx-checkpoints 0, so its Vulkan baseline is the
        # Phase 1 rerun with the same flag (p1-swa ckpt-off), not Phase 1's default-checkpoint run.
        gk = os.path.join(ROOT, "b65-phase1", "raw", "p1-swa-20261013-081841", "ckpt-off", "serve.csv")
        if res["env"].get("gemma_ckpt", "0") == "0" and os.path.exists(gk):
            for m in models:
                if m.startswith("gemma"): res["vk_serve"][m] = serve_medians(list(csv.DictReader(open(gk))), m)
        res["vk_serve_note"] = "Gemma's Vulkan server baseline is the --ctx-checkpoints 0 rerun (p1-swa-20261013-081841)"
    else:   # Phase 0.5 fa=0 references (tg128 / tg128@d4096 from the follow-up, tg128@d16384 from the main sweep)
        for prefix, key in (("p05b", "fa0.tg128"), ("p05b", "fa0.tg128@d4096"), ("p05", "fa0.tg128@d16384")):
            d = sweep_dir(prefix)
            if not d: continue
            for m in models:
                recs = [json.loads(l) for l in read_lines(f"{d}/{m}.{key}.jsonl") if l.strip().startswith("{")]
                if recs: ref[(m, key.split(".", 1)[1])] = recs[-1].get("avg_ts")
    energy = {}
    for r in csv.DictReader(open(f"{out}/energy.csv")) if os.path.exists(f"{out}/energy.csv") else []:
        if r.get("section") == "bench": energy[(r["model"], r["test"])] = r
    # current step from the run log
    log = read_lines(os.path.join(kit, log_name)); last = [l[3:].split() for l in log if l.startswith(">> ")]
    serve_rows = list(csv.DictReader(open(f"{out}/serve.csv"))) if os.path.exists(f"{out}/serve.csv") else []
    idle_rows = {r["model"]: r for r in csv.DictReader(open(f"{out}/idle_loaded.csv"))} if os.path.exists(f"{out}/idle_loaded.csv") else {}
    cur = None
    if res["state"] == "running" and last:
        kind, m = last[-1][0], last[-1][1]
        if kind == "bench" and (m, last[-1][2]) not in energy:
            t = last[-1][2]; lines = read_lines(f"{out}/{m}.{t}.log"); phase = None
            for l in lines:
                mm = PROGRESS.match(l)
                if mm: phase = mm.group(2)
            t0 = float(lines[0].split(" ", 1)[0]) if lines and re.match(r"^\d+\.\d+ ", lines[0]) else None
            cur = dict(kind="bench", model=m, test=t, phase=phase or "loading model", started=t0)
        elif kind == "server":
            n = sum(1 for r in serve_rows if r["model"] == m)
            phase = "starting llama-server" if m not in idle_rows and n == 0 else \
                    f"requests {n} of {len(res['sizes']) * res['reps']}" if m in idle_rows else "loaded idle power (30 s)"
            cur = dict(kind="server", model=m, phase=phase)
    res["current"] = cur
    for m in models:
        for t in res["bench_tests"]:
            c = dict(model=m, test=t, status="pending", ref=ref.get((m, t)), vk=vk.get((m, t)))
            e = energy.get((m, t))
            if cur and cur["kind"] == "bench" and (cur["model"], cur["test"]) == (m, t): c["status"] = "running"
            elif e:
                c["status"] = e["status"]; c["seconds"] = float(e["seconds"]) if e.get("seconds") else None
                recs = [json.loads(l) for l in read_lines(f"{out}/{m}.{t}.jsonl") if l.strip().startswith("{")]
                if e["status"] == "ok" and recs:
                    j = recs[-1]; w = test_watts(out, m, t, j, float(e["t_end"]) if e.get("t_end") else None)
                    c.update(tok_s=j.get("avg_ts"), sd=j.get("stddev_ts"), watts=w or None)
                elif e["status"] != "ok":
                    c["error"] = "\n".join(l for l in read_lines(f"{out}/{m}.{t}.log")[-6:])
            res["bench"].append(c)
        for n in res["sizes"]:
            rows = [r for r in serve_rows if r["model"] == m and abs(int(float(r["prompt_tokens"] or 0)) - n) <= max(64, n // 20)]
            med = lambda k: (statistics.median(float(r[k]) for r in rows if r.get(k) not in ("", None)) if any(r.get(k) not in ("", None) for r in rows) else None)
            st = "pending" if not rows else "ok" if len(rows) >= res["reps"] else "running"
            res["serve"].append(dict(model=m, size=n, status=st, reps=len(rows), ttft=med("ttft_s"), prompt_tok_s=med("prompt_tok_s"),
                                     gen_tok_s=med("gen_tok_s"), total_s=med("total_s"), watts=med("board_w"),
                                     ttft_all=[float(r["ttft_s"]) for r in rows if r.get("ttft_s")]))
        r = idle_rows.get(m)
        res["idle"].append(dict(model=m, status="ok" if r else "pending",
                                watts=float(r["loaded_idle_w"]) if r and r.get("loaded_idle_w") else None,
                                vram_mib=int(r["vram_used_mib"]) if r and (r.get("vram_used_mib") or "").isdigit() else None))
    # failed server starts count as done steps (reported in the log)
    res["server_failed"] = [l.split("for ", 1)[-1] for l in log if l.startswith("!! server did not come up")]
    res["done"] = (sum(1 for c in res["bench"] if c["status"] not in ("pending", "running")) + sum(1 for i in res["idle"] if i["status"] == "ok")
                   + sum(min(s["reps"], res["reps"]) for s in res["serve"]))
    p0 = sorted(d for d in os.listdir(RAW) if re.match(r"^\d{8}-\d{6}$", d)) if os.path.isdir(RAW) else []
    if p0: res["idle_unloaded_w"] = float(dict(l.split("=", 1) for l in read_lines(os.path.join(RAW, p0[-1], "env.txt")) if "=" in l).get("idle_unloaded_w") or 0) or None
    res["shape"] = power_shape(out)
    return res

P1G_SIZE_N = len(P1_SIZES) * P1_REPS
SRV_PROGRESS = re.compile(r"prompt processing, n_tokens =\s*(\d+), progress = ([\d.]+), t =\s*([\d.]+) s")

def serve_medians(rows, model=None):
    """median TTFT / prompt / gen / W per prompt size from serve_bench.py rows"""
    rows = [r for r in rows if model is None or r["model"] == model]; res = []
    for n in P1_SIZES:
        sel = [r for r in rows if abs(int(float(r["prompt_tokens"] or 0)) - n) <= max(64, n // 20)]
        med = lambda k: (statistics.median(float(r[k]) for r in sel if r.get(k) not in ("", None)) if any(r.get(k) not in ("", None) for r in sel) else None)
        res.append(dict(size=n, reps=len(sel), ttft=med("ttft_s"), prompt_tok_s=med("prompt_tok_s"), gen_tok_s=med("gen_tok_s"),
                        watts=med("board_w"), ttft_all=[float(r["ttft_s"]) for r in sel if r.get("ttft_s")],
                        status="pending" if not sel else "ok" if len(sel) >= P1_REPS else "running"))
    return res

def p1g_full():
    """Gemma llama-server rerun (raw/p1-swa-*): one server config per variant, compared with the Phase 1 baseline."""
    kit = os.path.join(ROOT, "b65-phase1"); base = os.path.join(kit, "raw")
    runs = sorted(d for d in os.listdir(base) if d.startswith("p1-swa-")) if os.path.isdir(base) else []
    res = dict(state="not started", run_id=None, env={}, variants=[], baseline=None, current=None, done=0, total=0, reps=P1_REPS, sizes=P1_SIZES)
    if not runs: return res
    out = os.path.join(base, runs[-1]); res["run_id"] = runs[-1]
    pid = (read_lines(f"{out}/pid") or [""])[0].strip(); alive = False
    try: alive = bool(pid) and "gemma_server_rerun" in open(f"/proc/{pid}/cmdline").read()
    except OSError: pass
    res["state"] = "finished" if os.path.exists(f"{out}/done") else "running" if alive else "stopped"
    env = res["env"] = dict(l.split("=", 1) for l in read_lines(f"{out}/env.txt") if "=" in l)
    model = env.get("model", "gemma-4-31b-qat"); names = env.get("variants", "").split()
    flags = {"ckpt-off": "--ctx-checkpoints 0", "swa-full": "--swa-full", "default": "defaults (control)"}
    vrows = {r["variant"]: r for r in csv.DictReader(open(f"{out}/variants.csv"))} if os.path.exists(f"{out}/variants.csv") else {}
    log = read_lines(os.path.join(kit, "p1g-run.log")); last = [l[3:].split() for l in log if l.startswith(">> ")]
    cur_v = last[-1][2] if res["state"] == "running" and last else None
    for v in names:
        d = os.path.join(out, v); rows = list(csv.DictReader(open(f"{d}/serve.csv"))) if os.path.exists(f"{d}/serve.csv") else []
        vr = vrows.get(v); st = vr["status"] if vr else "running" if v == cur_v else "pending"
        x = dict(name=v, flags=flags.get(v, v), status=st, serve=serve_medians(rows, model),
                 idle_w=float(vr["loaded_idle_w"]) if vr and vr.get("loaded_idle_w") else None,
                 vram_mib=int(vr["vram_used_mib"]) if vr and (vr.get("vram_used_mib") or "").isdigit() else None)
        if st in ("fail", "oom"): x["error"] = "\n".join(read_lines(f"{d}/server.log")[-8:])
        res["variants"].append(x)
        if v == cur_v:
            slog = read_lines(f"{d}/server.log"); prog = None
            for l in slog:
                mm = SRV_PROGRESS.search(l)
                if mm: prog = dict(n_tokens=int(mm.group(1)), progress=float(mm.group(2)), t=float(mm.group(3)))
                elif "launch_slot_" in l: prog = None
            up = any("listening on" in l for l in slog); n = len(rows)
            phase = ("loading model" if not up else "loaded idle power + VRAM (30 s)" if last[-1][0] == "server"
                     else f"request {min(n + 1, P1G_SIZE_N)} of {P1G_SIZE_N} · {P1_SIZES[min(n, P1G_SIZE_N - 1) // P1_REPS]}-token prompt")
            res["current"] = dict(variant=v, flags=flags.get(v, v), phase=phase, prompt=prog if up and last[-1][0] == "requests" else None)
    brun = env.get("baseline_run")
    if brun and os.path.exists(os.path.join(base, brun, "serve.csv")):
        res["baseline"] = dict(run_id=brun, serve=serve_medians(list(csv.DictReader(open(os.path.join(base, brun, "serve.csv")))), model))
    res["total"] = len(names) * (1 + P1G_SIZE_N)
    res["done"] = sum((1 if x["idle_w"] is not None or x["status"] in ("fail", "oom") else 0) +
                      (P1G_SIZE_N if x["status"] in ("fail", "oom") else sum(min(s["reps"], P1_REPS) for s in x["serve"])) for x in res["variants"])
    # idle step is recorded with the variant row (after requests); count it once requests start
    for x in res["variants"]:
        if x["idle_w"] is None and x["status"] == "running" and any(s["reps"] for s in x["serve"]): res["done"] += 1
    return res

def p1_share(f=None):
    """Phase 1 data for share cards: statuses only until the run is complete (an OOM is reported as "done", since
    it's a result); afterwards the numbers, except anything listed in holds.conf ("server" holds a model's llama-server rows).
    Also serves Phase 1S (f = p1s_full()); a dry run never counts as complete."""
    sycl = f is not None; f = f or p1_full(); held = holds()
    complete = f["state"] == "finished" and not f.get("dry") and f["done"] >= f["total"] - len(f.get("server_failed", [])) * (1 + len(P1_SIZES) * P1_REPS)
    bench, serve, idle = [], [], []
    for c in f["bench"]:
        st = c["status"]
        if not complete: bench.append(dict(model=c["model"], test=c["test"], status=st if st in ("pending", "running") else "done")); continue
        if is_held(held, c["model"], c["test"], "0"): bench.append(dict(model=c["model"], test=c["test"], status="held")); continue
        bench.append(dict(model=c["model"], test=c["test"], status=st, tok_s=c.get("tok_s"), sd=c.get("sd"), watts=c.get("watts"), ref=c.get("ref"), vk=c.get("vk")))
    for x in f["serve"]:
        if not complete: serve.append(dict(model=x["model"], size=x["size"], status=x["status"] if x["status"] in ("pending", "running") else "done", reps=x["reps"])); continue
        if is_held(held, x["model"], "server", "0"): serve.append(dict(model=x["model"], size=x["size"], status="held", reps=x["reps"])); continue
        serve.append({k: x[k] for k in ("model", "size", "status", "reps", "ttft", "prompt_tok_s", "gen_tok_s", "total_s", "watts")})
    for x in f["idle"]:
        idle.append(dict(model=x["model"], status=x["status"] if not complete else x["status"], **({} if not complete else dict(watts=x["watts"], vram_mib=x["vram_mib"]))))
    return dict(state=f["state"], complete=complete, done=f["done"], total=f["total"], run_id=f["run_id"], models=f["models"],
                bench_tests=f["bench_tests"], sizes=f["sizes"], bench=bench, serve=serve, idle=idle, shape=f.get("shape") or [],
                server_failed=f.get("server_failed", []) if complete else [], idle_unloaded_w=f.get("idle_unloaded_w") if complete else None,
                rerun=None if sycl else p1g_share(), sycl=sycl, dry=f.get("dry", False), env=dict(gemma_ckpt=f["env"].get("gemma_ckpt"), compute_runtime=f["env"].get("compute_runtime"), oneapi=f["env"].get("oneapi")),
                vk_serve={m: [{k: x[k] for k in ("size", "ttft", "gen_tok_s")} for x in v] for m, v in f.get("vk_serve", {}).items()} if complete else {},
                vk_serve_note=f.get("vk_serve_note"))

P2_TESTS = ["pp512", "pp4096", "pp16384", "tg128", "tg128@d4096", "tg128@d16384", "tg128@d32768"]
P2_RUNS = [("vulkan", "0"), ("sycl", "0"), ("sycl", "1")]

def p2_full():
    """Phase 2 dashboard data: llama-bench on Vulkan fa0 vs SYCL fa0/fa1, per model and test, plus the SYCL build state.
    Vulkan fa0 references from Phase 0.5 / Phase 1 are attached as a drift check."""
    kit = os.path.join(ROOT, "b65-phase2"); base = os.path.join(kit, "raw")
    runs = sorted(d for d in os.listdir(base) if re.match(r"^p2-(dry-)?\d{8}-\d{6}$", d)) if os.path.isdir(base) else []   # not p2-spot-*
    models = [l.split("|")[0] for l in read_lines(os.path.join(kit, "models.conf")) if l.strip() and not l.startswith("#")]
    blog = read_lines(os.path.join(kit, "build_sycl.log"))
    build = dict(state="not started" if not blog else "built" if any(l.startswith("SYCL bins:") for l in blog)
                 else "failed" if any(re.search(r"(error|failed|FAILED)", l) for l in blog[-30:]) else "building",
                 version=next((l for l in blog if "build " in l and "commit" in l), None),
                 devices=[l.strip() for l in blog if re.match(r"\s*(SYCL\d|\[level_zero)", l)], tail=blog[-12:])
    res = dict(state="not started", run_id=None, models=models, tests=P2_TESTS, runs=[f"{b}/fa{f}" for b, f in P2_RUNS],
               env={}, cells=[], current=None, done=0, total=0, build=build, dry=False)
    if not runs: return res
    run = max(runs, key=lambda r: r[-15:])   # newest by timestamp, dry run or full
    out = os.path.join(base, run); res["run_id"] = run; res["dry"] = run.startswith("p2-dry-")
    pid = (read_lines(f"{out}/pid") or [""])[0].strip(); alive = False
    try: alive = bool(pid) and "phase2" in open(f"/proc/{pid}/cmdline").read()
    except OSError: pass
    res["state"] = "finished" if os.path.exists(f"{out}/done") else "running" if alive else "stopped"
    env = res["env"] = dict(l.split("=", 1) for l in read_lines(f"{out}/env.txt") if "=" in l)
    tests = ["pp512", "tg128"] if res["dry"] else P2_TESTS
    mods = models[:1] if res["dry"] else models
    res["tests"] = tests; res["models"] = mods
    energy = {(r["backend"], r["fa"], r["test"], r["model"]): r for r in csv.DictReader(open(f"{out}/energy.csv"))} if os.path.exists(f"{out}/energy.csv") else {}
    log = read_lines(os.path.join(kit, "p2-run.log")); last = [l[3:].split() for l in log if l.startswith(">> ")]
    cur = None
    if res["state"] == "running" and last:
        m, b, fa, t = last[-1][0], last[-1][1], last[-1][2].split("=")[1], last[-1][3]
        if (b, fa, t, m) not in energy:
            tag = f"{m}.{b}.fa{fa}.{t}"; lines = read_lines(f"{out}/{tag}.log"); phase = None
            for l in lines:
                mm = PROGRESS.match(l)
                if mm: phase = mm.group(2)
            t0 = float(lines[0].split(" ", 1)[0]) if lines and re.match(r"^\d+\.\d+ ", lines[0]) else None
            cur = dict(model=m, backend=b, fa=fa, test=t, phase=phase or ("loading model / JIT compiling" if b == "sycl" else "loading model"), started=t0)
    res["current"] = cur
    # Vulkan fa0 references: P0.5 prefill + tg@16K, P0.5b tg128 / tg@4K, Phase 1 tg@32K
    ref = {}
    for prefix, keys in (("p05", ("pp512", "pp4096", "pp16384", "tg128@d16384")), ("p05b", ("tg128", "tg128@d4096"))):
        d = sweep_dir(prefix)
        for m in mods:
            for k in keys:
                recs = [json.loads(l) for l in read_lines(f"{d}/{m}.fa0.{k}.jsonl") if l.strip().startswith("{")] if d else []
                if recs: ref[(m, k)] = recs[-1].get("avg_ts")
    p1 = os.path.join(ROOT, "b65-phase1", "raw", "p1-20261012-180308")
    for m in mods:
        recs = [json.loads(l) for l in read_lines(f"{p1}/{m}.tg128@d32768.jsonl") if l.strip().startswith("{")]
        if recs: ref[(m, "tg128@d32768")] = recs[-1].get("avg_ts")
    for m in mods:
        for b, fa in P2_RUNS:
            for t in tests:
                c = dict(model=m, run=f"{b}/fa{fa}", test=t, status="pending", ref=ref.get((m, t)) if b == "vulkan" else None)
                e = energy.get((b, fa, t, m)); tag = f"{m}.{b}.fa{fa}.{t}"
                if cur and (cur["model"], cur["backend"], cur["fa"], cur["test"]) == (m, b, fa, t): c["status"] = "running"
                elif e:
                    c["status"] = e["status"]; c["seconds"] = float(e["seconds"]) if e.get("seconds") else None
                    recs = [json.loads(l) for l in read_lines(f"{out}/{tag}.jsonl") if l.strip().startswith("{")]
                    if e["status"] == "ok" and recs:
                        j = recs[-1]; w = test_watts(out, f"{m}.{b}.fa{fa}", t, j, float(e["t_end"]) if e.get("t_end") else None)
                        c.update(tok_s=j.get("avg_ts"), sd=j.get("stddev_ts"), watts=w or None, gpu=j.get("gpu_info"))
                    elif e["status"] != "ok":
                        c["error"] = "\n".join(l for l in read_lines(f"{out}/{tag}.log")[-6:])
                res["cells"].append(c)
    res["total"] = len(res["cells"]); res["done"] = sum(1 for c in res["cells"] if c["status"] not in ("pending", "running"))
    return res

def p2_share():
    """Phase 2 data for share cards: statuses only until the FULL run (not a dry run) has every cell done (an OOM counts
    as done, it's a result); afterwards tok/s and board W per cell."""
    f = p2_full()
    complete = f["state"] == "finished" and not f["dry"] and f["total"] > 0 and f["done"] >= f["total"]
    cells = []
    for c in f["cells"]:
        st = c["status"]
        if not complete: cells.append(dict(model=c["model"], run=c["run"], test=c["test"], status=st if st in ("pending", "running") else "done")); continue
        cells.append(dict(model=c["model"], run=c["run"], test=c["test"], status=st, tok_s=c.get("tok_s"), sd=c.get("sd"), watts=c.get("watts"), ref=c.get("ref")))
    out = os.path.join(ROOT, "b65-phase2", "raw", f["run_id"]) if f["run_id"] else None
    return dict(state=f["state"], dry=f["dry"], complete=complete, done=f["done"], total=f["total"], run_id=f["run_id"], models=f["models"],
                tests=f["tests"], runs=f["runs"], cells=cells, build=dict(state=f["build"]["state"]),
                sycl=dict(compute_runtime=f["env"].get("compute_runtime"), oneapi=f["env"].get("oneapi")),
                shape=power_shape(out) if out and os.path.isdir(out) and f["state"] == "running" else [])

def nav_status():
    """Cheap per-phase state for the sidebar: latest run folder's done/pid markers only."""
    def latest(base, pat):
        runs = sorted(d for d in os.listdir(base) if re.match(pat, d)) if os.path.isdir(base) else []
        return os.path.join(base, runs[-1]) if runs else None
    def state(out):
        if not out: return dict(state="not started")
        pid = (read_lines(f"{out}/pid") or [""])[0].strip()
        try: alive = bool(pid) and ".sh" in open(f"/proc/{pid}/cmdline").read()   # any phase's runner script
        except OSError: alive = False
        st = "finished" if os.path.exists(f"{out}/done") else "running" if alive else "stopped"
        return dict(state=st, run_id=os.path.basename(out))
    p05, p05b = (latest(os.path.join(ROOT, "b65-phase05", "raw"), rf"^{k}-\d{{8}}-\d{{6}}$") for k in ("p05", "p05b"))
    s05 = state(p05); b = state(p05b) if p05b else None
    if b and b["state"] == "running": s05 = b
    p2base = os.path.join(ROOT, "b65-phase2", "raw")
    s2 = state(latest(p2base, r"^p2-\d{8}-\d{6}$"))
    if s2["state"] == "not started":
        dry = latest(p2base, r"^p2-dry-\d{8}-\d{6}$")
        if dry: s2 = state(dry); s2["state"] = "running" if s2["state"] == "running" else "dry"
    return dict(p0=state(latest(RAW, r"^\d{8}-\d{6}$")), p05=s05,
                p1=state(latest(os.path.join(ROOT, "b65-phase1", "raw"), r"^p1-\d{8}-\d{6}$")),
                p1g=state(latest(os.path.join(ROOT, "b65-phase1", "raw"), r"^p1-swa-\d{8}-\d{6}$")), p2=s2,
                p1s=state(latest(os.path.join(ROOT, "b65-phase1s", "raw"), r"^p1s-\d{8}-\d{6}$")),
                gd=state(latest(os.path.join(ROOT, "b65-gemmadiag", "raw"), r"^gd-\d{8}-\d{6}$")),
                p3=state(latest(os.path.join(ROOT, "b65-phase3", "raw"), r"^p3-\d{8}-\d{6}$")),
                p4=state(latest(os.path.join(ROOT, "b65-phase4", "raw"), r"^p4-\d{8}-\d{6}$")),
                us=state(latest(os.path.join(ROOT, "b65-ubserve", "raw"), r"^us-\d{8}-\d{6}$")),
                p5=state(latest(os.path.join(ROOT, "b65-phase5", "raw"), r"^p5-\d{8}-\d{6}$")),
                p6=p6_nav(), p15=p15_nav(), p7=p7_nav())

def p6_nav():
    """Phase 6 sidebar dot: the full run if there is one, else the dry run (shown as running/dry)."""
    base = os.path.join(ROOT, "b65-phase6", "raw")
    full = sorted(d for d in os.listdir(base) if re.match(r"^p6-\d{8}-\d{6}$", d)) if os.path.isdir(base) else []
    if full: out = os.path.join(base, full[-1])
    else:
        dry = sorted(d for d in os.listdir(base) if re.match(r"^p6-dry-\d{8}-\d{6}$", d)) if os.path.isdir(base) else []
        if not dry: return dict(state="not started")
        out = os.path.join(base, dry[-1])
    pid = (read_lines(f"{out}/pid") or [""])[0].strip()
    try: alive = bool(pid) and ".sh" in open(f"/proc/{pid}/cmdline").read()
    except OSError: alive = False
    st = "finished" if os.path.exists(f"{out}/done") else "running" if alive else "stopped"
    if not full and st != "running": st = "dry"
    return dict(state=st, run_id=os.path.basename(out))

def p1s_full():
    return p1_full("b65-phase1s", r"^p1s-(dry-)?\d{8}-\d{6}$", "p1s-run.log", sycl=True)

GD_VARIANTS = [("ckpt0", "--ctx-checkpoints 0", 32768), ("default", "default checkpoints", 32768), ("ckpt0_ub2048", "--ctx-checkpoints 0 -b 2048 -ub 2048", 32768),
               ("ckpt0_swafull_16k", "--ctx-checkpoints 0 --swa-full, ctx 17K", 17408), ("ckpt0_ctx16k", "--ctx-checkpoints 0, ctx 17K", 17408),
               ("ckpt0_fa0", "--ctx-checkpoints 0, flash attention off (local addition)", 32768)]

def gd_full():
    """Gemma SYCL server prefill diagnostic (b65-gemmadiag/raw/gd-*): llama-bench ub512 vs ub2048, then server variants."""
    kit = os.path.join(ROOT, "b65-gemmadiag"); base = os.path.join(kit, "raw")
    runs = [d for d in os.listdir(base) if re.match(r"^gd-(dry-)?\d{8}-\d{6}$", d)] if os.path.isdir(base) else []
    res = dict(state="not started", run_id=None, env={}, bench=[], variants=[], current=None, dry=False, sizes=P1_SIZES, reps=P1_REPS,
               refs={})
    s1 = os.path.join(ROOT, "b65-phase1s", "raw", "p1s-20261013-111949", "serve.csv")
    vk = os.path.join(ROOT, "b65-phase1", "raw", "p1-swa-20261013-081841", "ckpt-off", "serve.csv")
    if os.path.exists(s1): res["refs"]["sycl_p1s"] = serve_medians(list(csv.DictReader(open(s1))), "gemma-4-31b-qat")
    if os.path.exists(vk): res["refs"]["vulkan_ckpt0"] = serve_medians(list(csv.DictReader(open(vk))), "gemma-4-31b-qat")
    res["refs"]["bench_pp16384"] = jsonl_ts(os.path.join(P2_RUN, "gemma-4-31b-qat.sycl.fa1.pp16384.jsonl"))
    if not runs: return res
    run = max(runs, key=lambda r: r[-15:]); out = os.path.join(base, run); res.update(run_id=run, dry="-dry-" in run)
    pid = (read_lines(f"{out}/pid") or [""])[0].strip(); alive = False
    try: alive = bool(pid) and "gemmadiag" in open(f"/proc/{pid}/cmdline").read()
    except OSError: pass
    res["state"] = "finished" if os.path.exists(f"{out}/done") else "running" if alive else "stopped"
    res["env"] = dict(l.split("=", 1) for l in read_lines(f"{out}/env.txt") if "=" in l)
    log = read_lines(os.path.join(kit, "gd-run.log")); last = [l[3:].split() for l in log if l.startswith(">> ")]
    cur = last[-1] if res["state"] == "running" and last else None
    for ub in (512, 2048):
        v = jsonl_ts(f"{out}/bench.ub{ub}.jsonl")
        res["bench"].append(dict(ub=ub, tok_s=v, status="ok" if v else "running" if cur and cur[0] == "bench" and cur[1] == f"ub{ub}" else "pending"))
    notes = read_lines(f"{out}/notes.txt")
    for lab, desc, ctx in GD_VARIANTS[:1] if res["dry"] else GD_VARIANTS:
        d = os.path.join(out, lab); rows = list(csv.DictReader(open(f"{d}/serve.csv"))) if os.path.exists(f"{d}/serve.csv") else []
        note = next((n.split(": ", 1)[1] for n in notes if n.startswith(lab + ":")), None)
        if note and note != "OOM" and any(re.search(r"OUT_OF_DEVICE_MEMORY|out of memory|failed to allocate", l, re.I) for l in read_lines(f"{d}/server.log")): note = "OOM"   # Level Zero wording
        running = bool(cur and cur[0] == "server" and cur[1] == lab)
        sizes = [512] if res["dry"] else P1_SIZES
        serve = [x for x in serve_medians(rows) if x["size"] in sizes]
        st = ("oom" if note == "OOM" else "fail") if note else "running" if running else "ok" if serve and all(x["reps"] >= (1 if res["dry"] else P1_REPS) for x in serve) else "pending" if not rows else "stopped"
        x = dict(name=lab, flags=desc, ctx=ctx, status=st, serve=serve)
        if running:
            prog = None
            for l in read_lines(f"{d}/server.log"):
                mm = SRV_PROGRESS.search(l)
                if mm: prog = dict(n_tokens=int(mm.group(1)), progress=float(mm.group(2)), t=float(mm.group(3)))
                elif "launch_slot_" in l: prog = None
            res["current"] = dict(variant=lab, flags=desc, phase=f"request {min(len(rows) + 1, len(sizes) * P1_REPS)} of {len(sizes) * (1 if res['dry'] else P1_REPS)}" if rows or any("listening on" in l for l in read_lines(f"{d}/server.log")) else "loading model", prompt=prog)
        res["variants"].append(x)
    if cur and cur[0] == "bench": res["current"] = dict(variant=f"llama-bench pp16384 {cur[1]}", flags="", phase="running", prompt=None)
    res["total"] = len(res["bench"]) + len(res["variants"]); res["done"] = sum(1 for b in res["bench"] if b["status"] == "ok") + sum(1 for v in res["variants"] if v["status"] in ("ok", "oom", "fail"))
    return res

def gd_share():
    """Gemma SYCL diagnostic for share cards: medians only once the full (non-dry) run has finished."""
    g = gd_full(); done = g["state"] == "finished" and not g["dry"]
    pick = lambda rows: [{k: x[k] for k in ("size", "ttft", "prompt_tok_s", "gen_tok_s")} for x in rows]
    return dict(run_id=g["run_id"], state=g["state"], complete=done, dry=g["dry"], done=g.get("done", 0), total=g.get("total", 0),
                variants={v["name"]: dict(status=v["status"] if done or v["status"] in ("pending", "running") else "done", flags=v["flags"],
                                          serve=pick(v["serve"]) if done else []) for v in g["variants"]},
                sycl_p1s=pick(g["refs"].get("sycl_p1s", [])) if done else [],
                bench={b["ub"]: b["tok_s"] for b in g["bench"]} if done else {},
                vulkan=pick(g["refs"].get("vulkan_ckpt0", [])) if done else [])

P3_SECTIONS = [("coding", "c"), ("tools", "t"), ("notes", "n"), ("writing", "w")]

def p3_full():
    """Phase 3 quality checks (b65-phase3/raw/p3-*): per model, per section, per item; live from <model>.quality.log."""
    kit = os.path.join(ROOT, "b65-phase3"); base = os.path.join(kit, "raw")
    runs = [d for d in os.listdir(base) if re.match(r"^p3-(dry-)?\d{8}-\d{6}$", d)] if os.path.isdir(base) else []
    models = [l.split("|")[0] for l in read_lines(os.path.join(kit, "models.conf")) if l.strip() and not l.startswith("#")]
    T = os.path.join(kit, "tasks"); ids = {}
    for sec, f in (("coding", "coding.json"), ("tools", "tools.json"), ("notes", "notes.json"), ("writing", "writing.json")):
        try:
            j = json.load(open(os.path.join(T, f))); j = j["cases"] if sec == "tools" else j
            if sec == "coding" and os.path.exists(os.path.join(T, "coding_repo.json")): j += json.load(open(os.path.join(T, "coding_repo.json")))
            ids[sec] = [x["id"] for x in j]
        except (OSError, ValueError, KeyError): ids[sec] = []
    res = dict(state="not started", run_id=None, env={}, models=models, sections=[s_ for s_, _ in P3_SECTIONS], ids=ids, results={}, current=None, done=0, total=0, dry=False)
    if not runs: return res
    run = max(runs, key=lambda r: r[-15:]); out = os.path.join(base, run); res.update(run_id=run, dry="-dry-" in run)
    if res["dry"]: models = res["models"] = models[:1]; res["ids"] = ids = {k: v[:2] for k, v in ids.items()}
    pid = (read_lines(f"{out}/pid") or [""])[0].strip(); alive = False
    try: alive = bool(pid) and "phase3" in open(f"/proc/{pid}/cmdline").read()
    except OSError: pass
    res["state"] = "finished" if os.path.exists(f"{out}/done") else "running" if alive else "stopped"
    res["env"] = dict(l.split("=", 1) for l in read_lines(f"{out}/env.txt") if "=" in l)
    log = read_lines(os.path.join(kit, "p3-run.log")); last = [l[3:].split() for l in log if l.startswith(">> ")]
    cur_m = last[-1][1] if res["state"] == "running" and last else None
    for m in models:
        qj = os.path.join(out, f"{m}.quality.json"); r = {}
        if os.path.exists(qj):
            try:
                q = json.load(open(qj))
                for sec in res["sections"]:
                    r[sec] = [dict(id=x["id"], status="done" if sec == "writing" else "pass" if x.get("pass") else "fail", s=x.get("s"), finish=x.get("finish"),
                                   tokens=x.get("tokens"), why=(x.get("why") or (x.get("err") or "")[-160:] or x.get("answer", "")[:160]) if not x.get("pass") and sec != "writing" else "",
                                   answer=x.get("answer", "")[:200] if sec == "notes" else "") for x in q.get(sec, [])]
            except (OSError, ValueError): pass
        else:   # live: "<model> <id> PASS|FAIL ..." / "<model> <id> done ..." lines
            seen = {}
            for l in read_lines(os.path.join(out, f"{m}.quality.log")):
                p_ = l.split()
                if len(p_) >= 3 and p_[0] == m: seen[p_[1]] = "pass" if p_[2] == "PASS" else "fail" if p_[2] == "FAIL" else "done"
            for sec in res["sections"]: r[sec] = [dict(id=i, status=seen[i]) for i in ids[sec] if i in seen]
        status = "done" if os.path.exists(qj) else "running" if m == cur_m else "pending"
        res["results"][m] = dict(status=status, sections=r)
        if status == "running":
            n = sum(len(v) for v in r.values()); tot = sum(len(v) for v in ids.values())
            nxt = next((i for sec in res["sections"] for i in ids[sec] if i not in {x["id"] for x in r.get(sec, [])}), None)
            res["current"] = dict(model=m, item=nxt, n=n, of=tot, phase="loading model" if not os.path.exists(os.path.join(out, f"{m}.quality.log")) else f"item {n + 1} of {tot}")
    per = sum(len(v) for v in ids.values()); res["total"] = per * len(models)
    res["done"] = sum(sum(len(v) for v in x["sections"].values()) for x in res["results"].values())
    for f in ("phase3_summary.md", "blind_packet.md"): res[f.split(".")[0]] = os.path.exists(os.path.join(out, f))
    return res

def p3_share():
    """Phase 3 for share cards: progress counts only until the full (non-dry) run finishes; then pass counts and times.
    Writing outputs never leave the server (they're for AJ's blind ranking)."""
    f = p3_full(); complete = f["state"] == "finished" and not f["dry"]
    models = {}
    for m, x in f["results"].items():
        secs_ = {}
        for sec, items in x["sections"].items():
            secs_[sec] = dict(done=len(items), n=len(f["ids"].get(sec, [])), **({} if not complete or sec == "writing" else dict(passed=sum(1 for i in items if i["status"] == "pass"))))
        models[m] = dict(status=x["status"], sections=secs_, **({} if not complete else dict(seconds=round(sum((i.get("s") or 0) for v in x["sections"].values() for i in v)))))
    # writing: only once AJ has ranked every prompt blind (b65-phase3/writing_ranks.json, unblinded with the key afterwards)
    writing = None
    try:
        wr = json.load(open(os.path.join(ROOT, "b65-phase3", "writing_ranks.json")))
        if complete and wr.get("run_id") == f["run_id"] and len(wr.get("ranks", {})) >= len(f["ids"].get("writing", [])) and wr.get("unblinded"):
            writing = dict(by_prompt=wr["unblinded"]["by_prompt"], totals=wr["unblinded"]["totals"])
    except (OSError, ValueError, KeyError): pass
    return dict(state=f["state"], complete=complete, dry=f["dry"], run_id=f["run_id"], done=f["done"], total=f["total"], models=models, sections=f["sections"],
                ids={k: len(v) for k, v in f["ids"].items()}, writing=writing)

def p4_plan(models, ubcheck, vk, main_ub="512"):
    plan = []
    for m in models:
        plan += [("sycl", m, t, main_ub) for t in ("pp512", "pp16384", "tg128", "tg128@d16384")]
        if ubcheck:
            plan += [k for k in [("sycl", m, "pp4096", "512"), ("sycl", m, "pp4096", "2048"), ("sycl", m, "pp16384", "2048"), ("sycl", m, "tg128@d16384", "2048")] if k not in plan]
            if vk: plan += [("vulkan", m, "pp16384", "512"), ("vulkan", m, "pp16384", "2048")]
    return plan

def p4_full():
    """Canary (b65-phase4/raw/p4-*): SYCL fa1 drift, ub 512 rows vs baseline.json and ub 2048 rows vs baseline_ub2048.json (Phase 6), plus the optional micro-batch check."""
    kit = os.path.join(ROOT, "b65-phase4"); base = os.path.join(kit, "raw")
    runs = [d for d in os.listdir(base) if re.match(r"^p4-(dry-)?\d{8}-\d{6}$", d)] if os.path.isdir(base) else []
    try: baseline = json.load(open(os.path.join(kit, "baseline.json")))
    except (OSError, ValueError): baseline = {}
    try: baseline2 = json.load(open(os.path.join(kit, "baseline_ub2048.json")))
    except (OSError, ValueError): baseline2 = {}
    res = dict(state="not started", run_id=None, env={}, rows=[], current=None, done=0, total=0, dry=False, baseline_src=baseline.get("_source"), baseline2_src=baseline2.get("_source"), flags=0,
               runs=sorted((r for r in runs if not r.startswith("p4-dry-")), reverse=True))
    if not runs: return res
    run = max(runs, key=lambda r: r[-15:]); out = os.path.join(base, run); res.update(run_id=run, dry="-dry-" in run)
    pid = (read_lines(f"{out}/pid") or [""])[0].strip(); alive = False
    try: alive = bool(pid) and "canary" in open(f"/proc/{pid}/cmdline").read()
    except OSError: pass
    res["state"] = "finished" if os.path.exists(f"{out}/done") else "running" if alive else "stopped"
    env = res["env"] = dict(l.split("=", 1) for l in read_lines(f"{out}/env.txt") if "=" in l)
    models = env.get("models", "").split(); ub = env.get("ubcheck") == "1"
    vk = ub and env.get("vk_index", "1") != ""   # runs before vk_index was recorded had it set
    got = {(r["backend"], r["model"], r["test"], r["ub"]): r for r in csv.DictReader(open(f"{out}/canary.csv"))} if os.path.exists(f"{out}/canary.csv") else {}
    log = read_lines(os.path.join(kit, "p4-run.log")); last = [l[3:].split() for l in log if l.startswith(">> ")]
    cur = tuple(last[-1][:3]) + (last[-1][3][2:],) if res["state"] == "running" and last else None
    plan = p4_plan(models, ub, vk, env.get("ub", "512"))   # runs before Phase 6 have no ub= line: they ran at 512
    for k in plan:
        r = got.get(k); b = {"512": baseline, "2048": baseline2}.get(k[3], {}).get(k[1], {}).get(k[2]) if k[0] == "sycl" else None
        row = dict(backend=k[0], model=k[1], test=k[2], ub=k[3], baseline=b, status="pending")
        if r:
            if r["tok_s"] in ("FAIL", ""): row["status"] = "fail"
            else:
                v = float(r["tok_s"]); row.update(status="ok", tok_s=v, watts=float(r["board_w"]) if r.get("board_w") else None)
                if b: row["drift"] = round((v - b) / b * 100, 2); row["flag"] = abs(row["drift"]) > 5
        elif cur and (cur[0], cur[1], cur[2], cur[3]) == k: row["status"] = "running"
        res["rows"].append(row)
    res["total"] = len(plan); res["done"] = sum(1 for r in res["rows"] if r["status"] in ("ok", "fail"))
    res["flags"] = sum(1 for r in res["rows"] if r.get("flag") or r["status"] == "fail" and r["baseline"])
    if cur: res["current"] = dict(backend=cur[0], model=cur[1], test=cur[2], ub=cur[3])
    return res

def p4_share():
    f = p4_full(); complete = f["state"] == "finished" and not f["dry"]
    rows = [{k: r.get(k) for k in (("backend", "model", "test", "ub", "status", "baseline", "tok_s", "watts", "drift", "flag") if complete else ("backend", "model", "test", "ub", "status"))} for r in f["rows"]]
    if not complete: rows = [dict(r, status=r["status"] if r["status"] in ("pending", "running") else "done") for r in rows]
    return dict(state=f["state"], complete=complete, dry=f["dry"], run_id=f["run_id"], done=f["done"], total=f["total"], rows=rows,
                flags=f["flags"] if complete else None, env={k: f["env"].get(k) for k in ("kernel", "mesa", "level_zero", "llama_sycl", "oneapi")} if complete else {})

def us_full():
    """llama-server at -b 2048 -ub 2048 for Qwen and Muse (b65-ubserve/raw/us-*), vs Phase 1S (ub 512) and Phase 1 Vulkan;
    Gemma's ub 2048 server numbers come from the Gemma diagnostic (ckpt0_ub2048)."""
    kit = os.path.join(ROOT, "b65-ubserve"); base = os.path.join(kit, "raw")
    runs = [d for d in os.listdir(base) if re.match(r"^us-\d{8}-\d{6}$", d)] if os.path.isdir(base) else []
    p1s = os.path.join(ROOT, "b65-phase1s", "raw", "p1s-20261013-111949"); gdv = os.path.join(ROOT, "b65-gemmadiag", "raw", "gd-20261013-123933", "ckpt0_ub2048", "serve.csv")
    rows = lambda f: list(csv.DictReader(open(f))) if os.path.exists(f) else []
    ref512 = rows(f"{p1s}/serve.csv"); vk = rows(f"{P1_VK_RUN}/serve.csv"); gk = rows(os.path.join(ROOT, "b65-phase1", "raw", "p1-swa-20261013-081841", "ckpt-off", "serve.csv"))
    res = dict(state="not started", run_id=None, env={}, models=[], current=None, done=0, total=0)
    if not runs: return res
    run = max(runs); out = os.path.join(base, run); res["run_id"] = run
    pid = (read_lines(f"{out}/pid") or [""])[0].strip(); alive = False
    try: alive = bool(pid) and "ubserve" in open(f"/proc/{pid}/cmdline").read()
    except OSError: pass
    res["state"] = "finished" if os.path.exists(f"{out}/done") else "running" if alive else "stopped"
    env = res["env"] = dict(l.split("=", 1) for l in read_lines(f"{out}/env.txt") if "=" in l)
    now = rows(f"{out}/serve.csv"); idle = {r["model"]: r for r in rows(f"{out}/idle_loaded.csv")}
    i512 = {r["model"]: r for r in rows(f"{p1s}/idle_loaded.csv")}
    log = read_lines(os.path.join(kit, "us-run.log")); last = [l[3:].split() for l in log if l.startswith(">> ")]
    for m in env.get("models", "").split() + ["gemma-4-31b-qat"]:
        gem = m.startswith("gemma")
        x = dict(model=m, from_diag=gem, ub2048=serve_medians(rows(gdv) if gem else now, None if gem else m), ub512=serve_medians(ref512, m),
                 vulkan=serve_medians(gk if gem else vk, m), idle_w=float(idle[m]["loaded_idle_w"]) if m in idle and idle[m].get("loaded_idle_w") else None,
                 vram_mib=int(idle[m]["vram_used_mib"]) if m in idle and (idle[m].get("vram_used_mib") or "").isdigit() else None,
                 vram512_mib=int(i512[m]["vram_used_mib"]) if m in i512 and (i512[m].get("vram_used_mib") or "").isdigit() else None)
        res["models"].append(x)
    res["total"] = len(env.get("models", "").split()) * (1 + len(P1_SIZES) * P1_REPS)
    res["done"] = sum(min(s_["reps"], P1_REPS) for x in res["models"] if not x["from_diag"] for s_ in x["ub2048"]) + len(idle)
    if res["state"] == "running" and last: res["current"] = dict(step=last[-1][0], model=last[-1][1])
    return res

def us_share():
    f = us_full(); complete = f["state"] == "finished"
    keep = lambda rows_: [{k: r[k] for k in ("size", "ttft", "prompt_tok_s", "gen_tok_s")} for r in rows_]
    return dict(state=f["state"], complete=complete, run_id=f["run_id"], done=f["done"], total=f["total"],
                models=[dict(model=x["model"], from_diag=x["from_diag"], **({} if not complete else dict(ub2048=keep(x["ub2048"]), ub512=keep(x["ub512"]), vulkan=keep(x["vulkan"]),
                             vram_mib=x["vram_mib"], vram512_mib=x["vram512_mib"]))) for x in f["models"]])

def p5_full():
    """Phase 5 (b65-phase5/raw/p5-*): A new ub2048 baseline, B Gemma short-prompt TTFT, C multi-turn cache, D Qwen thinking on c08."""
    kit = os.path.join(ROOT, "b65-phase5"); base = os.path.join(kit, "raw")
    runs = [d for d in os.listdir(base) if re.match(r"^p5-(dry-)?\d{8}-\d{6}$", d)] if os.path.isdir(base) else []
    res = dict(state="not started", run_id=None, env={}, dry=False, A=[], B=[], C=[], D=[], current=None, parts=[], ref={}, progress=[], live=None, recent=[], elapsed_s=None)
    try:
        b512 = json.load(open(os.path.join(ROOT, "b65-phase4", "baseline.json"))); res["ref"]["baseline_ub512"] = {k: v for k, v in b512.items() if not k.startswith("_")}
    except (OSError, ValueError): pass
    p4 = os.path.join(ROOT, "b65-phase4", "raw", "p4-20261013-150339", "canary.csv")
    if os.path.exists(p4): res["ref"]["p4_ub2048"] = {f"{r['model']}|{r['test']}": float(r["tok_s"]) for r in csv.DictReader(open(p4)) if r["backend"] == "sycl" and r["ub"] == "2048" and r["tok_s"] not in ("", "FAIL")}
    if not runs: return res
    run = max(runs, key=lambda r: r[-15:]); out = os.path.join(base, run); res.update(run_id=run, dry="-dry-" in run)
    pid = (read_lines(f"{out}/pid") or [""])[0].strip(); alive = False
    try: alive = bool(pid) and "phase5" in open(f"/proc/{pid}/cmdline").read()
    except OSError: pass
    res["state"] = "finished" if os.path.exists(f"{out}/done") else "running" if alive else "stopped"
    env = res["env"] = dict(l.split("=", 1) for l in read_lines(f"{out}/env.txt") if "=" in l)
    res["parts"] = (env.get("parts_list") or "A B C D").split()
    for k, fn_ in (("A", "A_baseline.csv"), ("B", "B_ttft.csv"), ("C", "C_multiturn.csv"), ("D", "D_think.csv")):
        f = os.path.join(out, fn_)
        if os.path.exists(f): res[k] = list(csv.DictReader(open(f)))
    for r in res["A"]:   # the csv has the mean only; llama-bench's sd is in the per-test jsonl
        for l in read_lines(os.path.join(out, f"A.{r['model']}.{r['test']}.jsonl")):
            try: r["sd"] = json.loads(l)["stddev_ts"]
            except (ValueError, KeyError): pass
    # A: attach timed-rep W already in the csv; B: medians per (backend,cfg,size,cached)
    log = read_lines(os.path.join(kit, "p5-run.log"))
    marks = [l[3:] for l in log if l.startswith(">> ")]
    if res["state"] == "running" and marks:
        part = next((m.split()[1] for m in reversed(marks) if m.startswith("part ")), None)
        tail = [l for l in log if l.strip()][-1].strip()
        res["current"] = dict(part=part, step=marks[-1], last=tail[:160])
    res["recent"] = [l.rstrip()[:200] for l in log if l.strip()][-10:] if res["state"] == "running" else []
    # expected row counts per part (mirrors phase5.sh / p5tools.py loops)
    dry = res["dry"]; reps = 1 if dry else 5; nsz = 5
    D_CAPS = [("think-4k", 4096), ("think-8k", 8192), ("think-16k", 16384), ("think-8k-pp1.5", 8192), ("think-8k-qwen-sampler", 8192), ("nothink", 2048)]
    tries = 1 if dry else 5
    totals = dict(A=12, B=4 * nsz * reps * 2, C=3 * 4 * (2 if dry else 8), D=len(D_CAPS) * tries)
    seen = [m.split()[1] for m in marks if m.startswith("part ")]
    cur = res["current"]["part"] if res["current"] else None
    res["progress"] = [dict(part=p, done=len(res[p]), total=totals[p],
                            status="done" if res["state"] == "finished" or (p in seen and p != cur) else "running" if p == cur else "pending" if res["state"] == "running" else "skipped")
                       for p in res["parts"] if p in totals]
    # live view of the in-flight request: newest server log, last generation tick after the last finished request
    live = None
    if res["state"] == "running" and cur in ("B", "C", "D"):
        logs = glob.glob(os.path.join(out, "*.server.log"))
        if logs:
            sl = max(logs, key=os.path.getmtime); age = time.time() - os.path.getmtime(sl)
            ln = read_lines(sl); i = max((k for k, l in enumerate(ln) if "stop processing" in l), default=-1)
            ticks = [re.search(r"n_gen =\s*(\d+), tg =\s*([\d.]+)", l) for l in ln[i + 1:]]
            ticks = [t for t in ticks if t]
            live = dict(server=os.path.basename(sl).replace(".server.log", ""), log_age_s=round(age),
                        n_gen=int(ticks[-1].group(1)) if ticks and age < 30 else None, tg=float(ticks[-1].group(2)) if ticks and age < 30 else None)
            if cur == "D":
                k = len(res["D"]); tok_s = live["tg"] or 21.9
                if k < len(D_CAPS) * tries:
                    live.update(variant=D_CAPS[k // tries][0], try_=k % tries + 1, tries=tries, cap=D_CAPS[k // tries][1])
                    left = sum(D_CAPS[j // tries][1] for j in range(k, len(D_CAPS) * tries)) - (live["n_gen"] or 0)
                    live["worst_left_s"] = round(left / tok_s)
            elif cur == "C":
                live["turn"] = (len(res["C"]) % (2 if dry else 8)) + 1
            elif cur == "B":
                live["in_cfg"] = len(res["B"]) % (nsz * reps * 2); live["per_cfg"] = nsz * reps * 2
        res["live"] = live
    res["elapsed_s"] = None
    try:
        from datetime import datetime
        t0 = datetime.fromisoformat(env["date"]).timestamp()
        t1 = os.path.getmtime(f"{out}/done") if os.path.exists(f"{out}/done") else time.time()
        res["elapsed_s"] = round(t1 - t0)
    except (KeyError, ValueError, OSError): pass
    return res

def p5_share():
    f = p5_full(); complete = f["state"] == "finished" and not f["dry"]
    return dict(state=f["state"], complete=complete, dry=f["dry"], run_id=f["run_id"], parts=f["parts"],
                progress={k: len(f[k]) for k in ("A", "B", "C", "D")}, **({k: f[k] for k in ("A", "B", "C", "D")} if complete else {}),
                ref=f["ref"] if complete else {})

def p6_full():
    """Phase 6 (b65-phase6/raw/p6-*): A Qwen/Muse coding with thinking off, B regenerate/edit with checkpoints on/off, C canary at ub 2048."""
    kit = os.path.join(ROOT, "b65-phase6"); base = os.path.join(kit, "raw")
    runs = [d for d in os.listdir(base) if re.match(r"^p6-(dry-)?\d{8}-\d{6}$", d)] if os.path.isdir(base) else []
    res = dict(state="not started", run_id=None, env={}, dry=False, A=[], B=[], C=[], current=None, parts=[], ref={}, progress=[], live=None, recent=[], elapsed_s=None)
    try: res["ref"]["baseline_ub2048"] = {k: v for k, v in json.load(open(os.path.join(kit, "baseline_ub2048.json"))).items() if not k.startswith("_")}
    except (OSError, ValueError): pass
    p3 = os.path.join(ROOT, "b65-phase3", "raw", "p3-20261013-135609")
    for m in ("qwen3.8-27b", "muse-glimmer"):
        try: res["ref"].setdefault("p3_coding", {})[m] = {c["id"]: dict(passed=bool(c["pass"]), tokens=c.get("tokens"), s=c.get("s")) for c in json.load(open(os.path.join(p3, f"{m}.quality.json")))["coding"]}
        except (OSError, ValueError, KeyError): pass
    if not runs: return res
    run = max(runs, key=lambda r: r[-15:]); out = os.path.join(base, run); res.update(run_id=run, dry="-dry-" in run)
    pid = (read_lines(f"{out}/pid") or [""])[0].strip(); alive = False
    try: alive = bool(pid) and "phase6" in open(f"/proc/{pid}/cmdline").read()
    except OSError: pass
    res["state"] = "finished" if os.path.exists(f"{out}/done") else "running" if alive else "stopped"
    env = res["env"] = dict(l.split("=", 1) for l in read_lines(f"{out}/env.txt") if "=" in l)
    res["parts"] = (env.get("parts_list") or "A B C").split()
    for k, fn_ in (("A", "A_coding.csv"), ("B", "B_regen.csv"), ("C", "C_canary.csv")):
        f = os.path.join(out, fn_)
        if os.path.exists(f): res[k] = list(csv.DictReader(open(f)))
    log = read_lines(os.path.join(kit, "p6-dry.log" if res["dry"] else "p6-run.log"))
    marks = [l[3:] for l in log if l.startswith(">> ")]
    if res["state"] == "running" and marks:
        part = next((m.split()[1] for m in reversed(marks) if m.startswith("part ")), None)
        tail = [l for l in log if l.strip()][-1].strip()
        res["current"] = dict(part=part, step=marks[-1], last=tail[:160])
    res["recent"] = [l.rstrip()[:200] for l in log if l.strip()][-10:] if res["state"] == "running" else []
    dry = res["dry"]; tries = 1 if dry else 3; ntask = 2 if dry else 10; turns = 2 if dry else 6
    per_cfg = turns + 5; totals = dict(A=2 * ntask * tries, B=8 * per_cfg, C=4 if dry else 8)
    seen = [m.split()[1] for m in marks if m.startswith("part ")]
    cur = res["current"]["part"] if res["current"] else None
    res["progress"] = [dict(part=p, done=len(res[p]), total=totals[p],
                            status="done" if res["state"] == "finished" or (p in seen and p != cur) else "running" if p == cur else "pending" if res["state"] == "running" else "skipped")
                       for p in res["parts"] if p in totals]
    if res["state"] == "running" and cur in ("A", "B"):
        logs = glob.glob(os.path.join(out, "*.server.log"))
        if logs:
            sl = max(logs, key=os.path.getmtime); age = time.time() - os.path.getmtime(sl)
            ln = read_lines(sl); i = max((k for k, l in enumerate(ln) if "stop processing" in l), default=-1)
            ticks = [t for t in (re.search(r"n_gen =\s*(\d+), tg =\s*([\d.]+)", l) for l in ln[i + 1:]) if t]
            live = dict(server=os.path.basename(sl).replace(".server.log", ""), n_gen=int(ticks[-1].group(1)) if ticks and age < 30 else None,
                        tg=float(ticks[-1].group(2)) if ticks and age < 30 else None)
            if cur == "A":
                k = len(res["A"]) % (ntask * tries); live.update(task=f"c{k // tries + 1:02d}", try_=k % tries + 1, tries=tries, cap=4096)
            else:
                k = len(res["B"]) % per_cfg; steps = [f"turn{t}" for t in range(1, turns + 1)] + ["regen", "regen2", "edit-last", "edit-early", "back-to-original"]
                live.update(step=steps[k] if k < len(steps) else "?", step_i=k + 1, steps=per_cfg)
            res["live"] = live
    try:
        from datetime import datetime
        t0 = datetime.fromisoformat(env["date"]).timestamp()
        t1 = os.path.getmtime(f"{out}/done") if os.path.exists(f"{out}/done") else time.time()
        res["elapsed_s"] = round(t1 - t0)
    except (KeyError, ValueError, OSError): pass
    return res

# --- Phase 7: other engines (b65-phase7/raw/p7-*): llama.cpp SYCL vs Intel llm-scaler vLLM, one OpenAI-API client ---
P7_WEIGHTS = (os.path.expanduser("~/models/Qwen3.8-27B"), 55.6e9)   # Qwen/Qwen3.8-27B BF16, for the vLLM parts
_p7_dl = {"t": 0, "v": None}

def p7_download():
    """Size of the BF16 weight folder so far (cached 10 s; it walks the folder)."""
    if time.time() - _p7_dl["t"] < 10: return _p7_dl["v"]
    d, total = P7_WEIGHTS; got = 0
    for dp, _, fs in os.walk(d):
        for f in fs:
            try: got += os.path.getsize(os.path.join(dp, f))
            except OSError: pass
    _p7_dl.update(t=time.time(), v=dict(path=d, bytes=got, total=total, complete=os.path.exists(os.path.join(d, ".complete"))))
    return _p7_dl["v"]

def p7_runs():
    base = os.path.join(ROOT, "b65-phase7", "raw")
    return base, sorted((d for d in os.listdir(base) if re.match(r"^p7-(dry-)?\d{8}-\d{6}$", d)), key=lambda r: r[-15:]) if os.path.isdir(base) else []

def p7_state(out):
    pid = (read_lines(f"{out}/pid") or [""])[0].strip()
    try: alive = bool(pid) and "phase7" in open(f"/proc/{pid}/cmdline").read()
    except OSError: alive = False
    return "finished" if os.path.exists(f"{out}/done") else "running" if alive else "stopped"

def p7_nav():
    base, runs = p7_runs()
    if not runs: return dict(state="not started")
    st = p7_state(os.path.join(base, runs[-1]))
    return dict(state="dry" if "-dry-" in runs[-1] and st != "running" else st, run_id=runs[-1])

def p7_full(run=None):
    kit = os.path.join(ROOT, "b65-phase7"); base, runs = p7_runs()
    res = dict(state="not started", run_id=None, runs=runs[::-1], download=p7_download())
    if not runs: return res
    run = run if run in runs else runs[-1]; out = os.path.join(base, run)
    res.update(run_id=run, dry="-dry-" in run, state=p7_state(out))
    env = res["env"] = dict(l.split("=", 1) for l in read_lines(f"{out}/env.txt") if "=" in l)
    res["plan"] = [dict(zip(("part", "label"), l.split("|", 1))) for l in read_lines(f"{out}/plan.txt") if "|" in l]
    res["engines"] = list(csv.DictReader(open(f"{out}/engines.csv"))) if os.path.exists(f"{out}/engines.csv") else []
    cur = (read_lines(f"{out}/current") or [""])[0].split("|") if res["state"] == "running" else []
    res["current"] = dict(part=cur[0], step=cur[1], since=float(cur[2])) if len(cur) == 3 else None
    rows = lambda n: list(csv.DictReader(open(os.path.join(out, n)))) if os.path.exists(os.path.join(out, n)) else []
    f = lambda v: float(v) if v not in ("", None) else None
    med = lambda xs: round(statistics.median(xs), 2) if xs else None
    sp, cc, cd = rows("speed.csv"), rows("conc.csv"), rows("coding.csv")
    res["speed"] = [dict(label=l, prompt=int(n), reps=len(g), ttft=med([f(r["ttft_s"]) for r in g]), prefill=med([f(r["prefill_tok_s"]) for r in g]),
                         decode=med([f(r["decode_tok_s"]) for r in g]), decode_all=[f(r["decode_tok_s"]) for r in g],
                         watts=med([f(r["board_w"]) for r in g if r["board_w"]]), short=sum(int(r["short"]) for r in g))
                    for (l, n) in dict.fromkeys((r["label"], r["prompt_target"]) for r in sp)
                    for g in [[r for r in sp if r["label"] == l and r["prompt_target"] == n]]]
    res["conc"] = [dict(label=l, streams=int(c), reps=len({r["rep"] for r in g}), agg=med(list({f(r["agg_tok_s"]) for r in g})),
                        per_stream=med([f(r["decode_tok_s"]) for r in g]), ttft=med([f(r["ttft_s"]) for r in g]), watts=med([f(r["board_w"]) for r in g if r["board_w"]]))
                   for (l, c) in dict.fromkeys((r["label"], r["conc"]) for r in cc)
                   for g in [[r for r in cc if r["label"] == l and r["conc"] == c]]]
    res["coding"] = [dict(label=l, passed=sum(int(r["pass"]) for r in g), n=len(g), decode=med([f(r["decode_tok_s"]) for r in g if f(r["decode_tok_s"])]),
                          tokens=med([f(r["completion_tokens"]) for r in g if r["completion_tokens"]]), last=g[-1]["task"] + " try " + g[-1]["try"])
                     for l in dict.fromkeys(r["label"] for r in cd) for g in [[r for r in cd if r["label"] == l]]]
    vr = rows("vram.csv"); res["vram"] = {}
    for r in vr: v = res["vram"].setdefault(r["part"], dict(now=0, peak=0)); m = int(r["b65_vram_mib"] or 0); v["now"] = m; v["peak"] = max(v["peak"], m); v["t"] = float(r["t"])
    log = read_lines(os.path.join(kit, "p7-dry.log" if res["dry"] else "p7-run.log"))
    start = max((i for i, l in enumerate(log) if l == f"run_id={run}"), default=0)
    res["log"] = [l[:220] for l in log[start:] if l.strip() and not l.startswith(("date=", "kernel=", "docker=", "llama_sycl", "sycl_device", "image=", "gguf=", "hf_weights", "b65=", "parts_list", "sizes=", "dry=", "kit_commit"))][-14:]
    if res["current"]:   # live view of the request in flight: last client line, server log tail for loading
        sl = os.path.join(out, f"{res['current']['part']}.server.log")
        res["server_tail"] = [l[:200] for l in read_lines(sl) if l.strip() and "unused tensor" not in l][-4:] if res["current"]["step"] in ("loading", "weights") else []
    try:
        from datetime import datetime
        t0 = datetime.fromisoformat(env["date"]).timestamp()
        res["elapsed_s"] = round((os.path.getmtime(f"{out}/done") if os.path.exists(f"{out}/done") else time.time()) - t0)
    except (KeyError, ValueError, OSError): res["elapsed_s"] = None
    return res

def p7_share():
    """Phase 7 for the share page: every full (non-dry) run merged, the latest result per engine label. Measured values
    leave the server only once b65-phase7/FINAL exists (written after the last track); before that, statuses only."""
    base, runs = p7_runs(); full = [r for r in runs if "-dry-" not in r]
    final = os.path.exists(os.path.join(ROOT, "b65-phase7", "FINAL"))
    parts, envs = {}, {}
    for run in full:
        f = p7_full(run); envs[run] = f.get("env", {})
        ok = {e["part"]: e for e in f.get("engines", []) if e["status"] == "ok"}
        for e in f.get("engines", []):
            p = parts.setdefault(e["part"], dict(part=e["part"], label=e["label"], engine=e["engine"], tries=[]))
            p["tries"].append(dict(run=run, status=e["status"], load_s=float(e["load_s"] or 0), args=e["args"]))
            if e["part"] in ok:
                lab = ok[e["part"]]["label"]
                p.update(label=lab, run=run, load_s=float(ok[e["part"]]["load_s"] or 0), args=ok[e["part"]]["args"], status="ok",
                         speed=[x for x in f["speed"] if x["label"] == lab], conc=[x for x in f["conc"] if x["label"] == lab],
                         coding=next((x for x in f["coding"] if x["label"] == lab), None),
                         vram_peak_mib=(f["vram"].get(e["part"]) or {}).get("peak"))
            elif p.get("status") != "ok": p["status"] = "fail"
    for p in parts.values():   # loaded, then died under load (A2: fp8 OOM on the first 4K prompt): not a working setup
        cd = p.get("coding")
        if p.get("status") == "ok" and cd and cd["n"] and cd["passed"] == 0 and any(not x["decode"] for x in p.get("speed", [])):
            p["status"] = "crashed"
    res = dict(complete=final, runs=full, state="finished" if final else (p7_nav().get("state") or "not started"),
               parts=[dict(part=p["part"], label=p["label"], engine=p["engine"], status=p.get("status"), tries=len(p["tries"])) for p in parts.values()])
    if final:
        res.update(parts=list(parts.values()), env=envs)
    return res

# --- Phase 1.5: registry lab gates (b65-phase15): native pre-check (p15pre-*) and registry runs in the pinned image (p15reg-*) ---
P15_REG = os.path.expanduser("~/src/ext/local-ai-registry-20261014")
P15_CARD = "intel-arc-pro-b65-32gb"
P15_IMAGE = "ghcr.io/ggml-org/llama.cpp@sha256:86b37d266ce85b485127adea68c9dc6d04d0ec9a64b0979844d5bbd8d66c53c5"
P15_GATES = ["load", "chat", "reasoning", "tools", "context", "speed"]
_p15_setup = {"t": 0, "v": None}

def p15_setup():
    """Docker, group, image, registry branch: cached for 30 s (it shells out)."""
    import subprocess, grp, getpass
    if _p15_setup["v"] and time.time() - _p15_setup["t"] < 30: return _p15_setup["v"]
    def sh(*a):
        try: r = subprocess.run(a, capture_output=True, text=True, timeout=8); return r.returncode, r.stdout.strip()
        except Exception as e: return 1, str(e)
    rc, act = sh("systemctl", "is-active", "docker")
    try: in_group = getpass.getuser() in grp.getgrnam("docker").gr_mem
    except KeyError: in_group = False
    sock = os.access("/var/run/docker.sock", os.W_OK)
    image = None
    if sock: image = sh("docker", "image", "inspect", "--format", "{{.Size}}", P15_IMAGE)[0] == 0
    elif in_group and act == "active":   # this process predates the group change; newgrp picks it up without a password
        try: image = subprocess.run(["newgrp", "docker"], input=f"docker image inspect --format '{{{{.Size}}}}' {P15_IMAGE} >/dev/null && echo yes\n",
                                    capture_output=True, text=True, timeout=8).stdout.strip() == "yes"   # no sg here; newgrp reads stdin
        except Exception: image = None
    branch = sh("git", "-C", P15_REG, "branch", "--show-current")[1] if os.path.isdir(P15_REG) else None
    launches = sorted(os.path.basename(f)[:-5] for f in glob.glob(os.path.join(P15_REG, "registry", "launches", "*arc-pro-b65*.json")))
    recipes = []
    for f in sorted(glob.glob(os.path.join(P15_REG, "registry", "recipes", "intel", P15_CARD, "*.json"))):
        try: r = json.load(open(f)); pr = r["proof"][0]; recipes.append(dict(file=os.path.basename(f), model=r["model"], at=pr.get("at"), tps=pr.get("tps"), prefill=pr.get("prefill"), gates=pr.get("gates")))
        except (OSError, ValueError, KeyError, IndexError): pass
    v = dict(docker=act, in_group=in_group, socket=sock, image=image, image_ref=P15_IMAGE, registry=P15_REG if os.path.isdir(P15_REG) else None, branch=branch,
             card=os.path.exists(os.path.join(P15_REG, "registry", "cards", "intel", P15_CARD + ".json")), launches=launches, recipes=recipes)
    _p15_setup.update(t=time.time(), v=v); return v

def p15_live(log_path):
    """Which lab gate a llama-server is on, from its log: completed requests, the long context prompt, the streamed speed answer."""
    ln = read_lines(log_path); done, cur, big_done = [], None, False
    for l in ln:
        if "launch_slot_" in l: cur = dict(prompt=None, prog=None, n_gen=None, tg=None)
        elif cur is not None and "prompt processing, n_tokens" in l:
            m = re.search(r"n_tokens =\s*(\d+), progress = ([\d.]+)", l)
            if m: cur.update(prompt_n=int(m.group(1)), prog=float(m.group(2)))
        elif cur is not None and "prompt eval time" in l:
            m = re.search(r"/\s*(\d+) tokens", l); cur["prompt"] = int(m.group(1)) if m else None
        elif cur is not None and "n_gen =" in l:
            m = re.search(r"n_gen =\s*(\d+), tg =\s*([\d.]+)", l)
            if m: cur.update(n_gen=int(m.group(1)), tg=float(m.group(2)))
        elif cur is not None and "stop processing" in l:
            m = re.search(r"n_tokens = (\d+)", l); cur["total"] = int(m.group(1)) if m else None; done.append(cur); cur = None
    big = lambda r: (r.get("prompt") or r.get("prompt_n") or 0) > 4096
    big_done = any(big(r) for r in done)
    loaded = bool(done) or cur is not None or any("model loaded" in l or "listening on" in l for l in ln)
    if not loaded: stage = "load"
    elif big_done: stage = "speed"
    elif cur and (cur.get("prog") is not None and (cur.get("prompt_n") or 0) > 4096): stage = "context"
    else: stage = ["chat", "reasoning", "tools", "tools", "context"][min(len(done), 4)]
    live = dict(stage=stage, requests=len(done))
    if cur:
        live.update(prog=cur.get("prog") if stage == "context" else None, n_gen=cur.get("n_gen"), tg=cur.get("tg"))
    if big_done:
        b = next(r for r in done if big(r)); live["context_tokens"] = b.get("prompt")
    try: live["age_s"] = round(time.time() - os.path.getmtime(log_path))
    except OSError: pass
    return live

def p15_runs(kind):
    kit = os.path.join(ROOT, "b65-phase15"); base = os.path.join(kit, "raw")
    pat = r"^p15pre-\d{8}-\d{6}$" if kind == "pre" else r"^p15reg-\d{8}-\d{6}$"
    runs = sorted(d for d in os.listdir(base) if re.match(pat, d)) if os.path.isdir(base) else []
    res = dict(kind=kind, state="not started", run_id=None, env={}, models=[], recent=[], elapsed_s=None)
    if not runs: return res
    out = os.path.join(base, runs[-1]); res["run_id"] = runs[-1]
    env = res["env"] = dict(l.split("=", 1) for l in read_lines(f"{out}/env.txt") if "=" in l)
    logf = os.path.join(kit, "precheck.log" if kind == "pre" else "registry_run.log"); log = read_lines(logf)
    pid = (read_lines(f"{out}/pid") or [""])[0].strip(); alive = False
    try: alive = bool(pid) and (".sh" in open(f"/proc/{pid}/cmdline").read() or "sg" in open(f"/proc/{pid}/cmdline").read())
    except OSError: pass
    finished = os.path.exists(f"{out}/done") or any(l.strip() == f">> done {runs[-1]}" for l in log)
    res["state"] = "finished" if finished else "running" if alive else "stopped"
    for k, v in list(env.items()):   # the pre-check wrote "ctx=… models=…" on one line
        m = re.match(r"^(\S*)\s+models=(.+)$", v)
        if m: env[k], env["models"] = m.group(1), m.group(2)
    names = env.get("models", "").split()
    ks = [int(c) // 1024 for c in env.get("ctxs", "").split()]   # multi-context runs name files <model>.<ctx>k.*
    items = [(m, k, f"{m}.{k}k") for k in ks for m in names] if ks else [(m, None, m) for m in names]
    t0 = None
    try:
        from datetime import datetime
        t0 = datetime.fromisoformat(env["date"]).timestamp()
        t1 = max([os.path.getmtime(f) for f in glob.glob(f"{out}/*")] or [t0]) if res["state"] != "running" else time.time()
        res["elapsed_s"] = round(t1 - t0)
    except (KeyError, ValueError): pass
    for m, k, tag in items:
        row = dict(model=m, ctx_k=k, status="pending", ok={}, tps=None, prefill=None, context_tokens=None, context_s=None, error=None, live=None, recipe=None)
        if kind == "pre":
            try:
                g = json.load(open(f"{out}/{m}.gates.json")); ev = g.get("evidence") or {}
                row.update(status="pass" if g["passed"] else "fail", ok=ev.get("ok", {}), tps=(g.get("proof") or {}).get("tps"), prefill=(g.get("proof") or {}).get("prefill"),
                           context_tokens=(ev.get("context") or {}).get("prompt_tokens"), context_s=(ev.get("context") or {}).get("seconds"), error=g.get("error"),
                           speed_tokens=(ev.get("speed") or {}).get("tokens_total"), speed_s=(ev.get("speed") or {}).get("seconds_total"))
            except (OSError, ValueError, KeyError): pass
        else:
            evs = sorted(glob.glob(os.path.join(P15_REG, "lab", "runs", f"{P15_CARD}.{m}.*.{k}k.*.json" if k else f"{P15_CARD}.{m}.*.json")), key=os.path.getmtime)
            evs = [f for f in evs if not t0 or os.path.getmtime(f) >= t0]
            if evs:
                try:
                    g = json.load(open(evs[-1])); ev = g.get("evidence") or {}; pr = g.get("proof") or {}
                    row.update(status="pass" if g["passed"] else "fail", ok=ev.get("ok", {}), tps=pr.get("tps"), prefill=pr.get("prefill"),
                               context_tokens=(ev.get("context") or {}).get("prompt_tokens"), context_s=(ev.get("context") or {}).get("seconds"),
                               speed_tokens=(ev.get("speed") or {}).get("tokens_total"), speed_s=(ev.get("speed") or {}).get("seconds_total"),
                               evidence=os.path.relpath(evs[-1], P15_REG))
                except (OSError, ValueError, KeyError): pass
            if row["status"] == "pending" and any(l.startswith(f"!! {tag}:") for l in log):
                row.update(status="fail", error=next(l[3:] for l in log if l.startswith(f"!! {tag}:")))
        mem = {}   # evidence logs (kit memwatch.sh: host RAM/swap; b65vram.csv: B65 VRAM from xe fdinfo), newer runs only
        for f, col, key in ((f"{out}/{tag}.b65vram.csv", 1, "vram_mib"), (f"{out}/{tag}.memwatch.csv", 1, "host_avail_gb"), (f"{out}/{tag}.memwatch.csv", 2, "swap_gb")):
            vals = []
            for l in read_lines(f)[1:]:
                try: vals.append(float(l.strip().split(",")[col]))
                except (ValueError, IndexError): pass
            if vals: mem[key] = vals[-1]; mem[key + "_" + ("peak" if key == "vram_mib" or key == "swap_gb" else "min")] = max(vals) if key != "host_avail_gb" else min(vals)
        if mem: row["mem"] = mem
        sl = f"{out}/{tag}.server.log"
        if row["status"] == "pending" and os.path.exists(sl):
            row["status"] = "running" if res["state"] == "running" else "stopped"
            if res["state"] == "running": row["live"] = p15_live(sl)
        res["models"].append(row)
    res["recent"] = [l.rstrip()[:220] for l in log if l.strip()][-12:]
    return res

def p15_full():
    return dict(setup=p15_setup(), pre=p15_runs("pre"), reg=p15_runs("reg"), gates=P15_GATES)

def p15_nav():
    f = p15_full(); r = f["reg"] if f["reg"]["run_id"] else f["pre"]
    if f["reg"]["state"] == "running" or f["pre"]["state"] == "running": return dict(state="running", run_id=(f["reg"] if f["reg"]["state"] == "running" else f["pre"])["run_id"])
    return dict(state=r["state"], run_id=r["run_id"])

def p6_share():
    f = p6_full(); complete = f["state"] == "finished" and not f["dry"]
    return dict(state=f["state"], complete=complete, dry=f["dry"], run_id=f["run_id"], parts=f["parts"], progress=f["progress"],
                **({k: f[k] for k in ("A", "B", "C")} if complete else {}), ref=f["ref"] if complete else {})

def p1g_share():
    """Gemma server rerun for share cards: statuses only until it finishes, then medians per config."""
    g = p1g_full()
    if not g["run_id"]: return None
    complete = g["state"] == "finished"
    vs = [dict(name=v["name"], flags=v["flags"], status=v["status"] if complete else ("done" if v["status"] not in ("pending", "running") else v["status"]),
               **({} if not complete else dict(serve=[{k: x[k] for k in ("size", "reps", "ttft", "prompt_tok_s", "gen_tok_s", "watts")} for x in v["serve"]],
                                               idle_w=v["idle_w"], vram_mib=v["vram_mib"]))) for v in g["variants"]]
    return dict(run_id=g["run_id"], state=g["state"], complete=complete, done=g["done"], total=g["total"], variants=vs)

def share_status():
    """Data for the share page. Measured values (tok/s, W, tok/J, sensor readings) are included ONLY once the
    run has finished every planned test; before that the page physically cannot draw a number it never got."""
    runs = sorted(d for d in os.listdir(RAW) if os.path.isdir(os.path.join(RAW, d))) if os.path.isdir(RAW) else []
    if not runs: return dict(run=None)
    out = os.path.join(RAW, runs[-1]); r = run_state(out); env = r["env"]
    bench = [t for t in r["tests"] if t["test"] != "spotcheck"]
    complete = r["state"] == "finished" and bool(bench) and all(t["status"] not in ("pending", "running") for t in bench)
    specs = model_specs()
    models = list(dict.fromkeys(t["model"] for t in bench))
    cells, held = [], holds()
    for t in bench:
        # before completion a failure is itself a result (e.g. 16K didn't fit), so it is reported as plain "done"
        st = t["status"] if complete or t["status"] in ("pending", "running") else "done"
        c = dict(model=t["model"], test=t["test"], status=st)
        if complete and is_held(held, t["model"], t["test"], "1"):   # held results never leave the server
            c.update(status="held", reason=held.get((t["model"], t["test"], "1")) or held.get((t["model"], t["test"], None)))
        elif complete and t["status"] == "ok":
            c.update(tok_s=t.get("tok_s"), sd=t.get("sd"), watts=t.get("watts"), tpj=t.get("tpj"))
        cells.append(c)
    shape = power_shape(out)  # normalized: no watts leave the server
    build = re.search(r"build (\d+)", env.get("llama_bench", "")); mesa = env.get("mesa", "").replace("mesa 1:", "").split("-")[0]
    res = dict(run_id=r["run_id"], state=r["state"], complete=complete, p05=p05_share(), p1=p1_share(), p1s=p1_share(p1s_full()), gd=gd_share(), p3=p3_share(), p4=p4_share(), us=us_share(), p5=p5_share(), p6=p6_share(), p7=p7_share(), p2=p2_share(), models=[
        dict(name=m, display=DISPLAY.get(m, m), quant=specs.get(m, ("", None))[0], size_gb=specs.get(m, ("", None))[1],
             spot=spot(out, m)) for m in models], cells=cells, done=sum(c["status"] not in ("pending", "running") for c in cells), total=len(cells),
        reps=int(re.search(r"-r (\d+)", env.get("bench_args", "-r 5")).group(1)), shape=shape,
        stack=dict(llama_build=build.group(1) if build else "", mesa=mesa, kernel=env.get("kernel", ""),
                   pcie=env.get("pcie_link", "").split(" (")[0]), rig=rig(env))
    if complete:
        res.update(idle_w=float(env["idle_unloaded_w"]) if env.get("idle_unloaded_w") else None, finished=r.get("done_at"))
    return dict(run=res)


# --- read-only file access to benchmark outputs (tailnet only via tailscale serve) ---
FILE_ROOTS = ("findings", "dist", "charts", "raw", "b65-phase05", "b65-phase1", "b65-phase1s", "b65-gemmadiag", "b65-phase2", "b65-phase3", "b65-phase4", "b65-ubserve", "b65-phase5", "b65-phase6", "b65-phase15", "results.csv", "README.md")
INLINE = (".png", ".csv", ".txt", ".md", ".json", ".jsonl", ".log", ".sha256")

def safe_path(rel):
    """Map a /files/<rel> path into ROOT; only the whitelisted roots, never outside them (symlinks resolved)."""
    from urllib.parse import unquote
    rel = unquote(rel).strip("/")
    if not rel: return ""
    if rel.split("/")[0] not in FILE_ROOTS: return None
    if any(part.startswith(".") for part in rel.split("/")): return None   # dot-files (e.g. Phase 3's .blind_key.json) are never served
    full = os.path.realpath(os.path.join(ROOT, rel))
    top = os.path.realpath(os.path.join(ROOT, rel.split("/")[0]))
    return full if (full == top or full.startswith(top + os.sep)) and os.path.exists(full) else None

def listing(rel, full):
    import html
    from urllib.parse import quote
    names = list(FILE_ROOTS) if not rel else sorted(os.listdir(full), reverse=rel.strip("/") in ("raw", "dist"))
    rows = []
    if rel: rows.append(f'<tr><td><a href="/files/{quote(os.path.dirname(rel.strip("/")))}">../</a></td><td></td><td></td></tr>')
    for n in names:
        if n.startswith("."): continue   # hidden: .blind_key.json and friends
        r = f"{rel.strip('/')}/{n}".strip("/"); f = os.path.join(ROOT, r)
        if not os.path.exists(f): continue
        isdir = os.path.isdir(f); st = os.stat(f)
        size = "" if isdir else (f"{st.st_size / 1e6:.1f} MB" if st.st_size > 1e6 else f"{st.st_size / 1e3:.1f} KB")
        rows.append(f'<tr><td><a href="/files/{quote(r)}">{html.escape(n)}{"/" if isdir else ""}</a></td><td>{size}</td>'
                    f'<td>{time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))}</td></tr>')
    title = html.escape("/" + rel.strip("/"))
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>B65 files {title}</title><style>body{{font:14px/1.5 system-ui,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;
color-scheme:light dark}}td{{padding:6px 12px 6px 0;border-bottom:1px solid rgba(128,128,128,.25)}}td:nth-child(n+2){{color:gray;
white-space:nowrap}}table{{border-collapse:collapse;width:100%}}a{{text-decoration:none}}</style>
<p><a href="/">← dashboard</a> · <a href="/files/">files</a></p><h2>B65 bench files {title}</h2>
<p style="color:gray">Read-only. Benchmark outputs only (dist, charts, raw, results.csv, README).</p>
<table>{"".join(rows)}</table>""".encode()


class H(BaseHTTPRequestHandler):
    def send(self, code, body, ctype):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self.send(200, open(os.path.join(HERE, "index.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/files" or path.startswith("/files/"):
            rel = path[len("/files"):].lstrip("/")
            full = safe_path(rel)
            if full is None: return self.send(404, b"not found", "text/plain")
            if full == "" or os.path.isdir(full): return self.send(200, listing(rel, full or ROOT), "text/html; charset=utf-8")
            import mimetypes
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if full.endswith((".jsonl", ".log", ".sha256", ".md", ".csv", ".txt")): ctype = "text/plain; charset=utf-8"
            if full.endswith(".gz"): ctype = "application/gzip"
            self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(os.path.getsize(full)))
            disp = "inline" if full.endswith(INLINE) else "attachment"
            self.send_header("Content-Disposition", f'{disp}; filename="{os.path.basename(full)}"'); self.end_headers()
            with open(full, "rb") as fh: self.wfile.write(fh.read())
            return
        if path in ("/share", "/share.html"):
            return self.send(200, open(os.path.join(HERE, "share.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/api/share":
            return self.send(200, json.dumps(share_status()).encode(), "application/json")
        if path in ("/p05", "/p05.html"):
            return self.send(200, open(os.path.join(HERE, "p05.html"), "rb").read(), "text/html; charset=utf-8")
        if path in ("/p1", "/p1.html"):
            return self.send(200, open(os.path.join(HERE, "p1.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/nav.js":
            return self.send(200, open(os.path.join(HERE, "nav.js"), "rb").read(), "text/javascript; charset=utf-8")
        if path == "/api/nav":
            h = list(HIST); k = max(1, len(h) // 90)
            spark = [max(x[1] for x in h[i:i + k]) for i in range(0, len(h), k)]
            return self.send(200, json.dumps(dict(nav_status(), live=h[-1] if h else None, spark=spark,
                                                  span_s=round(h[-1][0] - h[0][0]) if len(h) > 1 else 0)).encode(), "application/json")
        if path in ("/gd", "/gd.html"):
            return self.send(200, open(os.path.join(HERE, "gd.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/api/gd":
            return self.send(200, json.dumps(dict(gd=gd_full(), now=time.time())).encode(), "application/json")
        if path in ("/p15", "/p15.html"):
            return self.send(200, open(os.path.join(HERE, "p15.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/api/p15":
            return self.send(200, json.dumps(dict(p15=p15_full(), now=time.time())).encode(), "application/json")
        if path in ("/p7", "/p7.html"):
            return self.send(200, open(os.path.join(HERE, "p7.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/api/p7":
            from urllib.parse import parse_qs, urlparse
            run = (parse_qs(urlparse(self.path).query).get("run") or [None])[0]
            return self.send(200, json.dumps(dict(p7=p7_full(run), now=time.time())).encode(), "application/json")
        if path in ("/p6", "/p6.html"):
            return self.send(200, open(os.path.join(HERE, "p6.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/api/p6":
            return self.send(200, json.dumps(dict(p6=p6_full(), now=time.time())).encode(), "application/json")
        if path in ("/p5", "/p5.html"):
            return self.send(200, open(os.path.join(HERE, "p5.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/api/p5":
            return self.send(200, json.dumps(dict(p5=p5_full(), now=time.time())).encode(), "application/json")
        if path in ("/us", "/us.html"):
            return self.send(200, open(os.path.join(HERE, "us.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/api/us":
            return self.send(200, json.dumps(dict(us=us_full(), now=time.time())).encode(), "application/json")
        if path in ("/p4", "/p4.html"):
            return self.send(200, open(os.path.join(HERE, "p4.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/api/p4":
            return self.send(200, json.dumps(dict(p4=p4_full(), now=time.time())).encode(), "application/json")
        if path in ("/p3", "/p3.html"):
            return self.send(200, open(os.path.join(HERE, "p3.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/api/p3":
            return self.send(200, json.dumps(dict(p3=p3_full(), now=time.time())).encode(), "application/json")
        if path in ("/p1s", "/p1s.html"):
            return self.send(200, open(os.path.join(HERE, "p1s.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/api/p1s":
            return self.send(200, json.dumps(dict(p1=p1s_full(), now=time.time())).encode(), "application/json")
        if path in ("/p2", "/p2.html"):
            return self.send(200, open(os.path.join(HERE, "p2.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/api/p2":
            return self.send(200, json.dumps(dict(p2=p2_full(), now=time.time())).encode(), "application/json")
        if path in ("/p1g", "/p1g.html"):
            return self.send(200, open(os.path.join(HERE, "p1g.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/api/p1g":
            return self.send(200, json.dumps(dict(p1g=p1g_full(), now=time.time())).encode(), "application/json")
        if path == "/api/p1":
            return self.send(200, json.dumps(dict(p1=p1_full(), now=time.time())).encode(), "application/json")
        if path == "/api/p05":
            return self.send(200, json.dumps(dict(p05=p05_full(), now=time.time())).encode(), "application/json")
        if path == "/api/status":
            return self.send(200, json.dumps(status()).encode(), "application/json")
        if path.startswith("/charts/"):
            name = os.path.basename(path)
            p = os.path.join(CHARTS, name)
            if name.endswith(".png") and os.path.isfile(p):
                return self.send(200, open(p, "rb").read(), "image/png")
        self.send(404, b"not found", "text/plain")

    def log_message(self, *a): pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8765); a = ap.parse_args()
    threading.Thread(target=sampler, daemon=True).start()
    print(f"dashboard on http://127.0.0.1:{a.port}  (xe sensors: {XE or 'none'})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
