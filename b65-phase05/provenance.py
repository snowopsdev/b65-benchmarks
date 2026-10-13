#!/usr/bin/env python3
"""Match each local GGUF's sha256 to a Hugging Face repo file and record the commit. Writes <out>/provenance.csv."""
import csv, json, sys, urllib.request, os
out = sys.argv[1]
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "b65-bench"}), timeout=30) as r:
        return json.load(r)
rows = []
for line in open(os.path.join(out, "models.sha256")):
    sha, path = line.split(None, 1); path = path.strip()
    parts = path.split("/models/", 1)[-1].split("/")       # <org>/<repo>/<file>
    repo, fname = f"{parts[0]}/{parts[1]}", parts[-1]
    commit, match = "", "unknown"
    try:
        commit = get(f"https://huggingface.co/api/models/{repo}/revision/main")["sha"]
        for f in get(f"https://huggingface.co/api/models/{repo}/tree/{commit}?recursive=1"):
            if f.get("path", "").endswith(fname):
                match = "yes" if (f.get("lfs") or {}).get("oid") == sha else "NO (local file differs from main)"
    except Exception as e:
        match = f"lookup error: {e}"
    rows.append(dict(repo=repo, file=fname, sha256=sha, hf_commit=commit, sha_matches_hf=match))
with open(os.path.join(out, "provenance.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
for r in rows: print(f"{r['repo']}/{r['file']}  commit={r['hf_commit'][:12]}  match={r['sha_matches_hf']}")
