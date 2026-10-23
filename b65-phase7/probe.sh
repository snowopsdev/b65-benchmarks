#!/usr/bin/env bash
# Phase 7 step 0: does Intel's llm-scaler vLLM image see the B65 on this (non-Ubuntu) host?
# Read-only for the GPU: enumerates devices and prints versions, loads no model.
# Run as: echo "./probe.sh" | newgrp docker      (agent shells predate the docker group)
set -euo pipefail
cd "$(dirname "$0")"
IMG=${IMG:-intel/llm-scaler-vllm:1.5}
# the B65 is 0000:06:00.0 here (card0 + renderD129); renderD128 is the 3080, unlike Intel's single-GPU example
B65_PCI=${B65_PCI:-0000:06:00.0}
CARD=$(readlink -f /dev/dri/by-path/pci-$B65_PCI-card); REND=$(readlink -f /dev/dri/by-path/pci-$B65_PCI-render)
OUT=raw/p7probe-$(date +%Y%m%d-%H%M%S); mkdir -p "$OUT"

{
  echo "image=$IMG"; docker image inspect "$IMG" --format 'digest={{index .RepoDigests 0}} created={{.Created}}'
  echo "host_kernel=$(uname -r)"; echo "b65_pci=$B65_PCI card=$CARD render=$REND"
  echo "host_xe_driver=$(basename "$(readlink -f /sys/bus/pci/devices/$B65_PCI/driver)")"
} | tee "$OUT/env.txt"

docker run --rm --entrypoint /bin/bash \
  --device "$CARD" --device "$REND" \
  -v "/dev/dri/by-path:/dev/dri/by-path:ro" \
  --group-add "$(getent group render | cut -d: -f3)" --group-add "$(getent group video | cut -d: -f3)" \
  "$IMG" -c '
    echo "== os"; . /etc/os-release; echo "$PRETTY_NAME"
    echo "== sycl-ls"; (command -v sycl-ls >/dev/null && sycl-ls) || echo "no sycl-ls"
    echo "== level-zero / compute-runtime packages"; dpkg -l 2>/dev/null | grep -E "level-zero|intel-opencl|libze|intel-igc|intel-ocloc" | awk "{print \$2, \$3}"
    echo "== torch.xpu"
    python3 -c "import torch; print(torch.__version__, torch.xpu.is_available(), torch.xpu.device_count()); [print(i, torch.xpu.get_device_name(i), round(torch.xpu.get_device_properties(i).total_memory/2**30,1), \"GiB\") for i in range(torch.xpu.device_count())]"
    echo "== vllm"; python3 -c "import vllm; print(vllm.__version__)"
  ' 2>&1 | tee "$OUT/probe.txt"

# pass = torch sees exactly one XPU and it is the B65
if grep -qE "^0 .*(B65|e222|Graphics)" "$OUT/probe.txt" && grep -q "True 1" "$OUT/probe.txt"; then
  echo "PROBE PASS -> $OUT"; else echo "PROBE FAIL (see $OUT/probe.txt)"; exit 1; fi
