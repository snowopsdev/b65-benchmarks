#!/usr/bin/env bash
# Build llama.cpp SYCL at the SAME commit as the Vulkan build (8bb3cf0d2). JIT only (no AOT: AOT builds have produced gibberish on Battlemage).
# Needs Intel oneAPI DPC++ + oneMKL SYCL and Level Zero. Arch no longer ships intel-oneapi-basekit; this machine uses
# intel-oneapi-dpcpp-cpp intel-oneapi-mkl-sycl level-zero-loader level-zero-headers intel-compute-runtime (see README.md).
# Local changes: clone from the local vendor checkout (no network, Vulkan tree untouched), cmake/ninja from the project
# .venv, setvars fallback, full output logged to build_sycl.log.
set -euo pipefail
cd "$(dirname "$0")"
SRC="${LLAMA_SRC:-$HOME/src/llama.cpp}"; COMMIT="${COMMIT:-8bb3cf0d2}"; LOG="${LOG:-$PWD/build_sycl.log}"
export PATH="$PWD/../.venv/bin:$PATH"
exec > >(tee "$LOG") 2>&1
[ -d "$SRC/.git" ] || git clone --quiet "$PWD/../vendor/llama.cpp" "$SRC"
git -C "$SRC" checkout --quiet "$COMMIT"; echo "source commit: $(git -C "$SRC" rev-parse --short HEAD)"
ENV="/opt/intel/oneapi/setvars.sh"; [ -f "$ENV" ] || ENV="/opt/intel/oneapi/oneapi-vars.sh"
# shellcheck disable=SC1090
source "$ENV" --force >/dev/null
echo "icpx: $(icpx --version | head -n1)"
cmake -S "$SRC" -B "$SRC/build-sycl" -G Ninja -DGGML_SYCL=ON -DGGML_SYCL_F16=ON \
      -DCMAKE_C_COMPILER=icx -DCMAKE_CXX_COMPILER=icpx -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF
cmake --build "$SRC/build-sycl" -j"$(nproc)" --target llama-bench llama-server
"$SRC/build-sycl/bin/llama-bench" --version
sycl-ls || true
"$SRC/build-sycl/bin/llama-bench" --list-devices || true
echo "SYCL bins: $SRC/build-sycl/bin"
