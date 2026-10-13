"""Per-rep board-power windows, shared by report.py and the dashboard."""
import os, bisect, re

REP = re.compile(r"^(\d+\.\d+) llama-bench: benchmark \d+/\d+: (?:prompt|generation) run (\d+)/\d+$")

def rep_starts(log_file):
    """Epoch start of each timed rep, from the time-stamped --progress lines (newer runs only)."""
    starts = {}
    if os.path.exists(log_file):
        for l in open(log_file):
            m = REP.match(l.strip())
            if m: starts.setdefault(int(m.group(2)), float(m.group(1)))
    return [starts[k] for k in sorted(starts)]

def window_watts(trace_file, windows):
    """Average board W over the given (start, end) windows from the 10 Hz energy trace (linear interpolation)."""
    if not os.path.exists(trace_file) or not windows: return ""
    pts = []
    for l in open(trace_file):
        try: t, e = l.strip().split(","); pts.append((float(t), float(e)))
        except ValueError: pass
    if len(pts) < 2 or pts[0][0] > windows[0][0] or pts[-1][0] < windows[-1][1] - 0.2: return ""
    ts = [p[0] for p in pts]
    def e_at(t):
        i = min(max(bisect.bisect_left(ts, t), 1), len(pts) - 1)
        (ta, ea), (tb, eb) = pts[i - 1], pts[i]
        return ea + (eb - ea) * (t - ta) / (tb - ta) if tb > ta else eb
    joules = sum(e_at(b) - e_at(a) for a, b in windows) / 1e6
    return joules / sum(b - a for a, b in windows)


def test_watts(out, model, test, j, t_end=None):
    """Board W over the timed reps of one llama-bench record j, or "" if it can't be isolated."""
    samples = [n / 1e9 for n in j.get("samples_ns") or []]
    starts = rep_starts(f"{out}/{model}.{test}.log")
    if len(starts) == len(samples) > 0:
        # exact: each timed rep is [progress-line time, + its samples_ns]
        windows = [(a, a + d) for a, d in zip(starts, samples)]
    elif not (j.get("n_depth") or 0) and samples and t_end:
        # older runs without stamped progress: trailing window before exit. Not valid for depth
        # tests (untimed depth prefill/restore between reps), which stay blank.
        windows = [(t_end - sum(samples), t_end)]
    else:
        return ""
    return window_watts(f"{out}/{model}.{test}.power.csv", windows)
