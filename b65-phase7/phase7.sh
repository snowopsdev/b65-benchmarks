#!/usr/bin/env bash
# Phase 7 Track A: Qwen3.8-27B on llama.cpp SYCL vs Intel llm-scaler vLLM, every engine through the same client (oai_bench.py).
# Usage: SYCL_BIN=~/src/llama.cpp/build-sycl/bin ./phase7.sh   PARTS="A0 A1 A2 A3"  DRY=1
# Long runs: systemd-run --user (user units carry the docker group; agent shells don't, use `newgrp docker` there).
# Parts: A0 llama.cpp SYCL Q4_K_M (recipe flags) | A1 vLLM sym_int4 | A2 vLLM fp8 | A3 vLLM sym_int4 + MTP
#        A1g, A3g: A1, A3 with graphs (patches/sym_int4.py) | A2b: fp8 with small prefill chunks | A4: exl3xpu EXL3 + MTP
#        A3k2, A3k4: MTP draft length (coding only) | B1, B2: Strata Flash-Next Coder with / without its MTP draft layer | B3: llama.cpp, same GGUF
#        A0mN: A0 + llama.cpp's own MTP (draft-mtp, N tokens), full suite | A0mkN: the same, coding only | B3n: B3 + n-gram drafts (ngram-mod)
set -euo pipefail
cd "$(dirname "$0")"
: "${SYCL_BIN:?set SYCL_BIN}"; PARTS="${PARTS:-A0 A1 A2 A3}"; DRY="${DRY:-0}"
PY="${PY:-$HOME/.local/share/unsloth-xpu/bin/python}"      # has `tokenizers`; the client itself is stdlib only
IMG=intel/llm-scaler-vllm:1.5; B65_PCI=0000:06:00.0; PORT=18080; NAME=p7-vllm
CARD=$(readlink -f /dev/dri/by-path/pci-$B65_PCI-card); REND=$(readlink -f /dev/dri/by-path/pci-$B65_PCI-render)   # renderD128 is the 3080
GGUF=$(find ~/.lmstudio/models -iname 'Qwen3.8-27B-Q4_K_M.gguf' | head -n1)
HFDIR=$HOME/models/Qwen3.8-27B; HFREV=1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0
TOK=$HOME/models/tokenizers/Qwen3.8-27B/tokenizer.json        # same revision, fetched on its own so A0 needn't wait for the weights
if [ "$DRY" = 1 ]; then SIZES=512,4096; REPS=1; GEN=64; LEVELS=1,2; TRIES=1; LIMIT=2
else SIZES=512,4096,16384,32768; REPS=3; GEN=256; LEVELS=1,2,4,8; TRIES=3; LIMIT=0; fi

set +u; source /opt/intel/oneapi/setvars.sh --force >/dev/null; set -u
export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1
DEVS=$("$SYCL_BIN/llama-bench" --list-devices 2>&1)   # SYCL0 must be the B65 with its VRAM free (Studio's servers stopped)
echo "$DEVS" | grep -qiE "SYCL0.*(B65|BMG|Arc|e222)" || { echo "!! SYCL0 is not the B65:"; echo "$DEVS"; exit 2; }
FREE=$(echo "$DEVS" | grep -oP 'MiB, \K[0-9]+(?= MiB free)' | head -n1); [ "${FREE:-0}" -ge 28000 ] || { echo "!! only ${FREE:-?} MiB free on the B65"; exit 2; }

RUN_ID="p7-$( [ "$DRY" = 1 ] && echo dry- )$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"; echo $$ > "$OUT/pid"
# oneCCL opens every node listed in /dev/dri/by-path, even with world_size 1; the host's also lists the 3080 -> "fill_device_fds" failure.
BYPATH="$PWD/$OUT/bypath"; mkdir -p "$BYPATH"; ln -sfn "../$(basename "$CARD")" "$BYPATH/pci-$B65_PCI-card"; ln -sfn "../$(basename "$REND")" "$BYPATH/pci-$B65_PCI-render"
LOG="$PWD/$( [ "$DRY" = 1 ] && echo p7-dry.log || echo p7-run.log )"; exec > >(tee -a "$LOG") 2>&1
ENERGY=""; for h in /sys/class/hwmon/hwmon*; do [ "$(cat "$h/name" 2>/dev/null)" = xe ] || continue
  for l in "$h"/energy*_label; do [ "$(cat "$l")" = "card" ] && { ENERGY="${l%_label}_input"; break 2; }; done; done
{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"; echo "docker=$(docker version --format '{{.Server.Version}}')"
  echo "llama_sycl=$("$SYCL_BIN/llama-bench" --version 2>&1 | grep -m1 '^version:')"; echo "sycl_device=$(echo "$DEVS" | grep -m1 SYCL0)"
  echo "image=$(docker image inspect $IMG --format '{{index .RepoDigests 0}}')"; echo "gguf=$GGUF"; echo "hf_weights=Qwen/Qwen3.8-27B@$HFREV"
  echo "b65=$B65_PCI $CARD $REND"; echo "parts_list=$PARTS"; echo "sizes=$SIZES reps=$REPS gen=$GEN levels=$LEVELS tries=$TRIES limit=$LIMIT"
  echo "dry=$DRY energy_file=${ENERGY:-none}"; echo "kit_commit=$(git rev-parse HEAD)"; } > "$OUT/env.txt"; cat "$OUT/env.txt"
sha256sum "$GGUF" > "$OUT/models.sha256" &

declare -A LABEL=([A0]="A0 llama.cpp SYCL Q4_K_M" [A1]="A1 vLLM sym_int4" [A2]="A2 vLLM fp8" [A3]="A3 vLLM sym_int4 + MTP"
  [A1g]="A1g vLLM sym_int4 graphs" [A2b]="A2b vLLM fp8 small batch" [A3g]="A3g vLLM sym_int4 + MTP graphs"
  [B1]="B1 Strata Coder IQ1_M drafts on" [B2]="B2 Strata Coder IQ1_M no MTP" [B3]="B3 llama.cpp SYCL Coder IQ1_M"
  [A4]="A4 exl3xpu EXL3 4bpw + MTP" [A3k2]="A3k2 vLLM sym_int4 + MTP k=2 graphs" [A3k4]="A3k4 vLLM sym_int4 + MTP k=4 graphs"
  [A3k5]="A3k5 vLLM sym_int4 + MTP k=5 graphs" [A3k6]="A3k6 vLLM sym_int4 + MTP k=6 graphs"
  [A5]="A5 vLLM sym_int4 + MTP k=5 graphs" [B3n]="B3n llama.cpp SYCL Coder IQ1_M + ngram-mod")
for k in 2 3 4 5 6; do LABEL[A0m$k]="A0m$k llama.cpp SYCL Q4_K_M + MTP k=$k"; LABEL[A0mk$k]="A0mk$k llama.cpp SYCL Q4_K_M + MTP k=$k"; done
for P in $PARTS; do echo "$P|${LABEL[$P]}"; done > "$OUT/plan.txt"
echo "part,label,engine,status,load_s,args" > "$OUT/engines.csv"

SPID=""; VWPID=""; LGPID=""
cleanup() { for p in $SPID $VWPID $LGPID; do kill $p 2>/dev/null || true; done; docker rm -f $NAME >/dev/null 2>&1 || true; }
trap cleanup EXIT

# B65 VRAM held by the server, 1 Hz: xe DRM fdinfo (resident vram0, unique clients), read inside the container for vLLM
VRAM_AWK='/^pos:/{xe=0;id=""} /^drm-driver:/{xe=($2=="xe")} /^drm-client-id:/{id=$2}
  /^drm-resident-vram0:/{if(xe && !(id in seen)){seen[id]=1;v=$2;u=$3;tot+=(u=="MiB")?v*1024:(u=="GiB")?v*1048576:(u=="KiB")?v:v/1024}} END{printf "%d",tot/1024}'
[ -f "$OUT/vram.csv" ] || echo "t,part,b65_vram_mib" > "$OUT/vram.csv"
vram_watch() { local part=$1; while :; do local v=""
    if [ "$(docker inspect -f '{{.State.Running}}' $NAME 2>/dev/null)" = true ]; then
      v=$(docker exec $NAME sh -c 'cat /proc/[0-9]*/fdinfo/* 2>/dev/null | awk "$0"' "$VRAM_AWK" 2>/dev/null)
    elif [ -s "$OUT/.spid" ]; then v=$(cat /proc/$(<"$OUT/.spid")/fdinfo/* 2>/dev/null | awk "$VRAM_AWK"); fi   # the watcher forks before the server exists
    [ -n "$v" ] && echo "$(date +%s),$part,$v" >> "$OUT/vram.csv"; sleep 1; done; }

current() { echo "$1|$2|$(date +%s)" > "$OUT/current"; echo ">> step $1 $2"; }
healthy() { curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; }   # llama-server: 503 while loading; vLLM binds only once ready

start_llama() { local P=$1; shift
  "$SYCL_BIN/llama-server" -m "${LGGUF:-$GGUF}" --port $PORT --host 127.0.0.1 --no-webui --jinja --alias qwen "$@" > "$OUT/$P.server.log" 2>&1 &
  SPID=$!; echo $SPID > "$OUT/.spid"; for _ in $(seq 1 300); do healthy && return 0; kill -0 $SPID 2>/dev/null || break; sleep 1; done
  kill $SPID 2>/dev/null || true; SPID=""; return 1; }
stop_llama() { [ -n "$SPID" ] && { kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true; }; SPID=""; rm -f "$OUT/.spid"; sleep 3; }

start_vllm() { local P=$1; shift   # extra vllm serve args; 40 min budget (online quantization of 55 GB + graph capture)
  docker rm -f $NAME >/dev/null 2>&1 || true
  docker run -d --name $NAME --device "$CARD" --device "$REND" -v "$BYPATH:/dev/dri/by-path:ro" "${VEXTRA[@]}" \
    --group-add "$(getent group render | cut -d: -f3)" --group-add "$(getent group video | cut -d: -f3)" --shm-size 32g \
    -p 127.0.0.1:$PORT:8000 -v "$HFDIR:/llm/models/Qwen3.8-27B:ro" -e VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 -e VLLM_WORKER_MULTIPROC_METHOD=spawn \
    --entrypoint vllm $IMG serve /llm/models/Qwen3.8-27B --served-model-name qwen --host 0.0.0.0 --port 8000 --dtype float16 \
    --trust-remote-code --language-model-only --no-enable-prefix-caching --max-num-seqs 8 "$@" > /dev/null
  docker logs -f $NAME >> "$OUT/$P.server.log" 2>&1 & LGPID=$!
  for _ in $(seq 1 480); do healthy && return 0
    [ "$(docker inspect -f '{{.State.Running}}' $NAME 2>/dev/null)" = true ] || break
    grep -qE 'Engine core initialization failed|EngineCore failed to start' "$OUT/$P.server.log" 2>/dev/null && break; sleep 5; done   # A2b: the API server outlived its engine
  return 1; }
# A4: 0xSero's exl3xpu image (llm-scaler's vLLM + EXL3 ESIMD kernels) with its own B70 model config, unchanged except
# the served name and prefix caching (off, like every other part; the recipe turns it on, with mamba_cache_mode align)
EXL_IMG=ghcr.io/0xsero/exl3xpu@sha256:21412bdd7535e9c653eeb3d099dce3bc79a83d440def2cd9556111c79c870fa8
EXLDIR=$HOME/models/Qwen3.8-27B-exl3-4.00bpw
start_exl() { local P=$1; shift
  docker rm -f $NAME >/dev/null 2>&1 || true
  docker run -d --name $NAME --device "$CARD" --device "$REND" -v "$BYPATH:/dev/dri/by-path:ro" \
    --group-add "$(getent group render | cut -d: -f3)" --group-add "$(getent group video | cut -d: -f3)" --shm-size 32g \
    -p 127.0.0.1:$PORT:8000 -v "$EXLDIR:/models:ro" -e HF_HUB_OFFLINE=1 $EXL_IMG \
    models/qwen3.8-27b-exl3-4.00bpw --gpu 0 --port 8000 --model-path /models --set served_model_name=qwen "$@" > /dev/null
  docker logs -f $NAME >> "$OUT/$P.server.log" 2>&1 & LGPID=$!
  for _ in $(seq 1 480); do healthy && return 0
    [ "$(docker inspect -f '{{.State.Running}}' $NAME 2>/dev/null)" = true ] || break
    grep -qE 'Engine core initialization failed|EngineCore failed to start' "$OUT/$P.server.log" 2>/dev/null && break; sleep 5; done   # A2b: the API server outlived its engine
  return 1; }
# Track B: Strata (its own engine, SYCL port, AOT bmg-g31) on Qwen3.8-Flash-Next Coder IQ1_M, from setup's config
STRATA=$HOME/strata-b65/Strata; SCFG=$STRATA/strata-coder-iq1_m.json
FNEXT=$HOME/strata-b65/Strata-data/models/Qwen3.8-Flash-Next-GSQ-RCO-IQ1_M-00001-of-00002.gguf
TOKB=$HOME/models/tokenizers/Qwen3.8-Flash-Next/tokenizer.json   # Qwen/Qwen3.8-Flash-Next's; same ids as the 27B's on this repo's text
strata_ready() { curl -sf "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"loaded": *true'; }   # /health is 200 while loading
start_strata() { local P=$1; shift; local cfg="$PWD/$OUT/strata-$P.json"   # absolute: the server starts in $STRATA
  # setup's args minus --ple-io ram (setup took this 46 GB host for 1024 GB of RAM and put the 29 GB n-gram table in it);
  # extra "key=value" words: spec=N sets --spec, nomtp drops the draft layer
  python3 - "$SCFG" "$cfg" "$PORT" "$PWD/$OUT/$P.engine.log" "$@" <<'PY'
import json, sys
src, dst, port, log, *mods = sys.argv[1:]; c = json.load(open(src)); a = c["args"]
def drop(flag, n=1):
    if flag in a: i = a.index(flag); del a[i:i + 1 + n]
drop("--ple-io")
for m in mods:
    if m.startswith("spec="): a[a.index("--spec") + 1] = m[5:]
    if m == "nomtp": drop("--mtp"); drop("--spec-min-p")
c.update(port=int(port), log=log, open_browser=False); json.dump(c, open(dst, "w"), indent=1)
PY
  ( cd "$STRATA" && STRATA_SYCL_NAME=$NAME exec .venv/bin/python sycl/serve/server_intel.py --engine strata --config "$cfg" --port $PORT ) >> "$OUT/$P.server.log" 2>&1 &
  SPID=$!; for _ in $(seq 1 240); do strata_ready && return 0; kill -0 $SPID 2>/dev/null || break; sleep 5; done
  return 1; }
stop_strata() { [ -n "$SPID" ] && { kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true; }; SPID=""; docker rm -f $NAME >/dev/null 2>&1 || true; sleep 5; }
stop_vllm() { docker rm -f $NAME >/dev/null 2>&1 || true; kill $LGPID 2>/dev/null || true; LGPID=""; sleep 3; }
stop_engine() { case $1 in llama) stop_llama ;; strata) stop_strata ;; *) stop_vllm ;; esac; }

maxlen_sizes() { local ml=$1; echo "$SIZES" | tr , '\n' | awk -v ml="$ml" -v g="$GEN" '$1+g+64<=ml' | paste -sd, -; }

bench() { local P=$1 lab=$2 sizes=$3; local c=(--base "http://127.0.0.1:$PORT" --model qwen --label "$lab" --out "$OUT")
  if [ "${CHAT:-0}" = 1 ]; then   # Track B: chat continuation (Strata has no /v1/completions), one stream (Strata serves one at a time)
    current $P speed;  "$PY" oai_bench.py speed "${c[@]}" --chat --tokenizer "$TOKB" --energy "$ENERGY" --sizes "$sizes" --reps $REPS --gen $GEN || echo "!! $P speed failed"
    current $P coding; "$PY" oai_bench.py coding "${c[@]}" --tries $TRIES --limit $LIMIT || echo "!! $P coding failed"; return; fi
  if [ "${CODING_ONLY:-0}" = 1 ]; then current $P coding; "$PY" oai_bench.py coding "${c[@]}" --tries $TRIES --limit $LIMIT || echo "!! $P coding failed"; return; fi
  current $P speed;  "$PY" oai_bench.py speed "${c[@]}" --tokenizer "$TOK" --energy "$ENERGY" --sizes "$sizes" --reps $REPS --gen $GEN || echo "!! $P speed failed"
  current $P conc;   "$PY" oai_bench.py conc "${c[@]}" --tokenizer "$TOK" --energy "$ENERGY" --levels $LEVELS --reps $REPS --gen $GEN || echo "!! $P conc failed"
  current $P coding; "$PY" oai_bench.py coding "${c[@]}" --tries $TRIES --limit $LIMIT || echo "!! $P coding failed"; }

# run one part: try each variant (args string) in order until a server comes up, then bench it
run_part() { local P=$1 engine=$2; shift 2; local lab="${LABEL[$P]}"
  echo ">> part $P $lab"
  if [ "$engine" = vllm ] && [ ! -f "$HFDIR/.complete" ]; then current $P weights; echo ">> waiting for weights ($HFDIR)"
    while [ ! -f "$HFDIR/.complete" ]; do sleep 30; done; fi
  for args in "$@"; do
    current $P loading; echo ">> load $P: $args"; vram_watch $P & VWPID=$!; local t0=$(date +%s) ok=1
    if [ "$engine" = llama ]; then start_llama $P $args || ok=0
    elif [ "$engine" = exl ]; then eval "set -- $args"; start_exl $P "$@" || ok=0
    elif [ "$engine" = strata ]; then start_strata $P $args || ok=0
    else eval "set -- $args"; start_vllm $P "$@" || ok=0; fi
    local dt=$(( $(date +%s) - t0 ))
    if [ $ok = 1 ]; then
      echo "$P,$lab,$engine,ok,$dt,\"$args\"" >> "$OUT/engines.csv"; echo ">> $P up in ${dt}s"
      local ml; ml=$(echo "$args" | grep -oP -- '--max-model-len \K[0-9]+' || echo 65536)   # A4: 262144 in its config
      bench $P "$lab" "$(maxlen_sizes $ml)"
      stop_engine $engine; kill $VWPID 2>/dev/null || true; return 0
    fi
    echo "$P,$lab,$engine,fail,$dt,\"$args\"" >> "$OUT/engines.csv"; echo "!! $P failed to load after ${dt}s: $args"
    { tail -n 5 "$OUT/$P.server.log" | sed 's/^/   /'; } || true
    stop_engine $engine; kill $VWPID 2>/dev/null || true; mv "$OUT/$P.server.log" "$OUT/$P.server.fail-$t0.log" 2>/dev/null || true
  done
  echo "!! $P: no variant loaded"; }

COMMON="--gpu-memory-utilization 0.9 --max-model-len 40960"
MTP="--speculative-config '{\"method\":\"qwen3_5_mtp\",\"num_speculative_tokens\":3}'"
# sym_int4.apply() calls logger.info_once inside the compiled region, which torch.compile rejects (dynamo gb0291), so graph mode
# never loads with sym_int4 in llm-scaler 1.5. patches/sym_int4.py turns those two log calls into no-ops; nothing else changes.
PATCH=(-v "$PWD/patches/sym_int4.py:/opt/venv/lib/python3.12/site-packages/vllm/model_executor/layers/quantization/sym_int4.py:ro")
VEXTRA=()
for P in $PARTS; do VEXTRA=(); CODING_ONLY=0; CHAT=0; LGGUF=""; case $P in
  # the published recipe (-fa on -b 2048 -ub 2048, all layers); 8 slots sharing one 64K KV so conc and 32K prompts both fit
  A0) run_part A0 llama "-ngl 99 -fa on -b 2048 -ub 2048 -c 65536 -np 8 -kvu" ;;
  # A0 was llama.cpp without speculative decoding; this build has its own MTP (the GGUF carries the nextn layer), so the fair
  # comparison with vLLM's MTP is A0 + draft-mtp. Full suite for the default k=3, coding-only sweep for the rest (as A3k*)
  A0m[2-9]) k=${P#A0m}; run_part $P llama "-ngl 99 -fa on -b 2048 -ub 2048 -c 65536 -np 8 -kvu --spec-type draft-mtp --spec-draft-n-max $k" ;;
  A0mk[2-9]) CODING_ONLY=1; k=${P#A0mk}; run_part $P llama "-ngl 99 -fa on -b 2048 -ub 2048 -c 65536 -np 8 -kvu --spec-type draft-mtp --spec-draft-n-max $k" ;;
  # Intel's 4-bit; XPU graphs first, Intel's README default (--enforce-eager) as the fallback
  A1) run_part A1 vllm "--quantization sym_int4 $COMMON" "--quantization sym_int4 $COMMON --enforce-eager" ;;
  # 8-bit: ~28 GB of weights on a 32 GB card, so step the context down before giving up (a no-fit is a result)
  A2) run_part A2 vllm "--quantization fp8 --gpu-memory-utilization 0.95 --max-model-len 40960" \
                       "--quantization fp8 --gpu-memory-utilization 0.95 --max-model-len 8192" \
                       "--quantization fp8 --gpu-memory-utilization 0.95 --max-model-len 8192 --enforce-eager" ;;
  # MTP is verified by Intel on Qwen3.6 only; Qwen3.8 shares the Qwen3_5 architecture
  A3) run_part A3 vllm "--quantization sym_int4 $COMMON $MTP" "--quantization sym_int4 $COMMON --enforce-eager $MTP" ;;
  A1g) VEXTRA=("${PATCH[@]}"); run_part A1g vllm "--quantization sym_int4 $COMMON" ;;
  A3g) VEXTRA=("${PATCH[@]}"); run_part A3g vllm "--quantization sym_int4 $COMMON $MTP" ;;
  # fp8 weights take 27.6 GiB, so ~2 GiB is left; small prefill chunks keep the activations inside it (A2 died on a 4K prompt)
  # MTP draft length: scored on the coding suite only (acceptance depends on real content)
  # the sweep's winner (k=5: 74.3 tok/s coding, k=6 71.8), measured in full
  A5) VEXTRA=("${PATCH[@]}"); run_part A5 vllm "--quantization sym_int4 $COMMON --speculative-config '{\"method\":\"qwen3_5_mtp\",\"num_speculative_tokens\":5}'" ;;
  A3k[2-9]) VEXTRA=("${PATCH[@]}"); CODING_ONLY=1; k=${P#A3k}
    run_part $P vllm "--quantization sym_int4 $COMMON --speculative-config '{\"method\":\"qwen3_5_mtp\",\"num_speculative_tokens\":$k}'" ;;
  B1) CHAT=1; run_part B1 strata "" ;;
  # the native IQ pack refuses --spec < 2, so "no MTP" is the closest to drafts off: --spec 2 with only the suffix drafter
  # (Strata's docs: accepted ~9% of the time on the B70, nearly one token per round)
  B2) CHAT=1; run_part B2 strata "spec=2 nomtp" ;;
  # the same file on llama.cpp, as Strata's docs run it: all layers on the card except shard 2's 28.8 GB per_layer_token_embd
  # (mmapped from the SSD), q8_0 KV; B70: 28.4 GB of VRAM at 32K. Persistent JIT cache off (segfaults on Xe2, docs/INTEL.md)
  B3) CHAT=1; LGGUF=$FNEXT; export SYCL_CACHE_PERSISTENT=0
      run_part B3 llama "-ngl 999 --override-tensor per_layer_token_embd=CPU -fa on -ctk q8_0 -ctv q8_0 -c 40960 -np 1" ;;
  # Flash-Next's GGUF has no nextn layer, so llama.cpp's closest to Strata's drafts is n-gram drafting: ngram-mod is its
  # --spec-default (shared hash pool across requests, like Strata's suffix cache); defaults n-min 48 / n-max 64 (docs: MoEs want long drafts)
  B3n) CHAT=1; LGGUF=$FNEXT; export SYCL_CACHE_PERSISTENT=0
      run_part B3n llama "-ngl 999 --override-tensor per_layer_token_embd=CPU -fa on -ctk q8_0 -ctv q8_0 -c 40960 -np 1 --spec-type ngram-mod" ;;
  A4) run_part A4 exl "--set vllm.enable_prefix_caching=false --set vllm.mamba_cache_mode=null" ;;
  A2b) run_part A2b vllm "--quantization fp8 --gpu-memory-utilization 0.95 --max-model-len 8192 --max-num-batched-tokens 512 --enforce-eager" ;;
  *) echo "!! unknown part $P" ;;
esac; done

wait
"$PY" oai_bench.py summary --out "$OUT" > /dev/null || true
rm -f "$OUT/current"; date -Iseconds > "$OUT/done"; echo ">> done $RUN_ID"
