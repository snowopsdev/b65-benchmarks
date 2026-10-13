#!/usr/bin/env bash
# Build llama.cpp SYCL at the SAME commit as the Vulkan build (8bb3cf0d2). JIT only (no AOT: AOT builds have produced gibberish on Battlemage).
# Needs Intel oneAPI Base Toolkit (Arch: `intel-oneapi-basekit`) and Level Zero (`level-zero-loader`, `intel-compute-runtime`).
set -euo pipefail
SRC="${LLAMA_SRC:-$HOME/src/llama.cpp}"; COMMIT="${COMMIT:-8bb3cf0d2}"
[ -d "$SRC/.git" ] || git clone https://github.com/ggml-org/llama.cpp "$SRC"
git -C "$SRC" fetch --quiet origin && git -C "$SRC" checkout --quiet "$COMMIT"
# shellcheck disable=SC1091
source /opt/intel/oneapi/setvars.sh --force >/dev/null
cmake -S "$SRC" -B "$SRC/build-sycl" -DGGML_SYCL=ON -DGGML_SYCL_F16=ON \
      -DCMAKE_C_COMPILER=icx -DCMAKE_CXX_COMPILER=icpx -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF
cmake --build "$SRC/build-sycl" -j"$(nproc)" --target llama-bench llama-server
"$SRC/build-sycl/bin/llama-bench" --version
sycl-ls || true
echo "SYCL bins: $SRC/build-sycl/bin"
