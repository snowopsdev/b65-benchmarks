#!/usr/bin/env bash
# Phase 1.5: registry lab runs on the B65. For each model: start the launch's pinned image the way the registry SDK
# prints it (docker run --device /dev/dri ..., but published on 127.0.0.1 only), then `lab.py try --on endpoint`.
# A passing run writes the recipe into the registry clone; every run keeps its evidence in <clone>/lab/runs/.
# Usage: REG=~/src/ext/local-ai-registry-20261014 ./registry_run.sh   [MODELS="qwen3.8-27b gemma-4-31b muse-glimmer-30b"] [CTXS="131072 65536"]
# Evidence for cards the registry can't rent (BOUNTIES.md "When it pays"): the kit's tools/probe.py once, and per launch its
# tools/memwatch.sh (host RAM/swap; its GPU column is nvidia-smi = the RTX 3080 here) plus a B65 VRAM log from the xe fdinfo.
# Each context needs its launches first: P15_CTX=<ctx> ./make_launches.py "$REG". Logs are <model>.<ctx>k.* (the first, 32K-only run used <model>.*).
set -euo pipefail
cd "$(dirname "$0")"
: "${REG:?set REG to the registry clone}"; MODELS="${MODELS:-qwen3.8-27b gemma-4-31b muse-glimmer-30b}"; CTXS="${CTXS:-32768}"
KIT="${KIT:-$HOME/src/ext/local-ai-recipe-kit-20261014}"
GPU_DESC="${GPU_DESC:-Intel Arc Pro B65 32 GB (ASRock Creator; owner: Ryzen 7 5700X, PCIe 4.0 x4)}"
if ! docker info >/dev/null 2>&1; then   # in the docker group but this session predates it: re-run under the group
  if [ -z "${P15_SG:-}" ] && getent group docker | grep -qw "$(id -un)"; then exec newgrp docker <<< "P15_SG=1 REG='$REG' MODELS='$MODELS' CTXS='$CTXS' KIT='$KIT' '$0'"; fi   # no sg here; newgrp reads the command from stdin
  echo "!! docker is not reachable: run setup-docker.sh first"; exit 2; fi
[ -f "$KIT/tools/memwatch.sh" ] && [ -f "$KIT/tools/probe.py" ] || { echo "!! no recipe kit at $KIT"; exit 2; }
command -v bc >/dev/null || { echo "!! memwatch.sh needs bc (sudo pacman -S bc)"; exit 2; }
RUN_ID="p15reg-$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"; PORT=8098; NAME=b65-p15-server; echo $$ > "$OUT/pid"
{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"; echo "docker=$(docker version --format '{{.Server.Version}}')"
  echo "registry=$REG commit=$(git -C "$REG" rev-parse HEAD) branch=$(git -C "$REG" branch --show-current)"; echo "models=$MODELS"; echo "ctxs=$CTXS"; echo "kit=$KIT commit=$(git -C "$KIT" rev-parse HEAD)"; } > "$OUT/env.txt"; cat "$OUT/env.txt"
python3 -I "$KIT/tools/probe.py" --models-dir ~/.lmstudio/models --out "$OUT/probe.json" > /dev/null
LOGPID=""; MWPID=""; VWPID=""
cleanup() { for p in $LOGPID $MWPID $VWPID; do kill $p 2>/dev/null || true; done; docker rm -f $NAME >/dev/null 2>&1 || true; }; trap cleanup EXIT
# B65 VRAM held by the server: xe DRM fdinfo inside the container (resident vram0, summed over unique clients; as Phase 1S).
# Read through cat: the image's awk is mawk, which stops at the first fdinfo file it can't open.
VRAM_AWK='/^pos:/{xe=0;id=""} /^drm-driver:/{xe=($2=="xe")} /^drm-client-id:/{id=$2}
  /^drm-resident-vram0:/{if(xe && !(id in seen)){seen[id]=1;v=$2;u=$3;tot+=(u=="MiB")?v*1024:(u=="GiB")?v*1048576:(u=="KiB")?v:v/1024}} END{printf "%d",tot/1024}'
vram_watch() { echo "t,b65_vram_resident_mib" > "$1"
  while [ "$(docker inspect -f '{{.State.Running}}' $NAME 2>/dev/null)" = true ]; do
    echo "$(date +%s),$(docker exec $NAME sh -c 'cat /proc/[0-9]*/fdinfo/* 2>/dev/null | awk "$0"' "$VRAM_AWK" 2>/dev/null)" >> "$1"; sleep 1; done; }
for CTX in $CTXS; do K=$((CTX / 1024)); for MO in $MODELS; do T="$MO.${K}k"
  # launch id, image, weights and args come from the launch file the recipe will pin (nothing duplicated here)
  read -r LID IMAGE REPO REV FILE < <(P15_CTX=$CTX python3 -I - "$REG" "$MO" <<'PY'
import json, sys, glob
reg, mo = sys.argv[1], sys.argv[2]
sys.path.insert(0, "."); from make_launches import launch_id
l = json.load(open(f"{reg}/registry/launches/{launch_id(mo)}.json")); w = l["weights"][0]
print(l["id"], l["image"], w["repo"], w["revision"], w["files"])
PY
)
  DIR=$(find ~/.lmstudio/models ~/.cache/lm-studio -path "*/$REPO/$FILE" 2>/dev/null | head -n1 | xargs -r dirname || true)   # one of the roots may not exist
  [ -n "$DIR" ] || { echo "!! $T: $REPO/$FILE not found locally"; continue; }
  WANT=$(curl -sf "https://huggingface.co/api/models/$REPO/tree/$REV" | python3 -I -c "import json,sys;print(next(f['lfs']['oid'] for f in json.load(sys.stdin) if f['path']==sys.argv[1]))" "$FILE")
  HAVE=$(sha256sum "$DIR/$FILE" | cut -d' ' -f1); echo "$HAVE  $DIR/$FILE  want=$WANT" >> "$OUT/models.sha256"
  [ "$HAVE" = "$WANT" ] || { echo "!! $T: local file does not match $REPO@$REV"; continue; }
  mapfile -t ARGS < <(python3 -I -c "import json,sys;[print(a) for a in json.load(open(sys.argv[1]))['args']]" "$REG/registry/launches/$LID.json")
  mapfile -t ENVS < <(python3 -I -c "import json,sys;[print(f'-e{k}={v}') for k,v in json.load(open(sys.argv[1]))['env'].items()]" "$REG/registry/launches/$LID.json")
  echo ">> $T: $LID"; cleanup
  bash "$KIT/tools/memwatch.sh" "$OUT/$T.memwatch.csv" & MWPID=$!; sleep 2   # memwatch starts before the server
  docker run -d --name $NAME --device /dev/dri -p 127.0.0.1:$PORT:8080 --shm-size 8g "${ENVS[@]}" -v "$DIR:/models:ro" "$IMAGE" "${ARGS[@]}" > "$OUT/$T.container"
  docker logs -f $NAME > "$OUT/$T.server.log" 2>&1 & LOGPID=$!   # live, for the dashboard
  vram_watch "$OUT/$T.b65vram.csv" & VWPID=$!
  up=0; for _ in $(seq 1 600); do curl -sf http://127.0.0.1:$PORT/health >/dev/null 2>&1 && { up=1; break; }
    [ "$(docker inspect -f '{{.State.Running}}' $NAME 2>/dev/null)" = true ] || break; sleep 1; done
  if [ $up = 1 ]; then
    ( cd "$REG" && python3 -I lab/lab.py try "$REPO@$REV" --model "$MO" --engine "$LID" --card intel-arc-pro-b65-32gb \
        --on endpoint --endpoint http://127.0.0.1:$PORT --gpu "$GPU_DESC" ) 2>&1 | tee "$OUT/$T.lab.log" || true
  else echo "!! $T: server did not come up"; fi
  sleep 2; cleanup; LOGPID=""; MWPID=""; VWPID=""; sleep 3
done; done
echo ">> done $RUN_ID"; touch "$OUT/done"; rm -f "$OUT/pid"
