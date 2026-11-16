#!/usr/bin/env bash
# Phase 9: build llama.cpp v1.0.0 (b12359, b1b770d90) for SYCL (JIT, as Phase 2) and Vulkan, in its own tree so the
# b11574 builds (~/src/llama.cpp/build-sycl, vendor/llama.cpp/build) stay untouched for a same-day A/B.
# Usage: SRC=~/src/llama.cpp-1.0.0 ./build.sh [sycl|vulkan|both]
set -euo pipefail
cd "$(dirname "$0")"; ROOT="$(cd .. && pwd)"; MAIN="${MAIN:-$HOME/Projects/b65-benchmarks}"
SRC="${SRC:-$HOME/src/llama.cpp-1.0.0}"; WHAT="${1:-both}"
export PATH="$MAIN/.venv/bin:$PATH"   # cmake/ninja from the project venv, as Phase 2
echo "source: $(git -C "$SRC" describe --tags) $(git -C "$SRC" rev-parse --short HEAD)"
TARGETS=(--target llama-bench llama-server llama-completion)
if [ "$WHAT" = sycl ] || [ "$WHAT" = both ]; then
  ( set +u; source /opt/intel/oneapi/setvars.sh --force >/dev/null; set -u
    echo "icpx: $(icpx --version | head -n1)"
    cmake -S "$SRC" -B "$SRC/build-sycl" -G Ninja -DGGML_SYCL=ON -DGGML_SYCL_F16=ON \
      -DCMAKE_C_COMPILER=icx -DCMAKE_CXX_COMPILER=icpx -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF \
      -DGGML_SYCL_DNN=OFF   # b11574 also built without it (DNNL_DIR-NOTFOUND, then silent); 1.0.0 makes that an error
    cmake --build "$SRC/build-sycl" -j"$(nproc)" "${TARGETS[@]}"
    "$SRC/build-sycl/bin/llama-bench" --version ) 2>&1 | tee build_sycl.log
fi
if [ "$WHAT" = vulkan ] || [ "$WHAT" = both ]; then
  P="$MAIN/vendor/prefix"
  ( cmake -S "$SRC" -B "$SRC/build-vulkan" -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=ON -DGGML_CUDA=OFF \
      -DGGML_NATIVE=ON -DLLAMA_CURL=OFF -DCMAKE_PREFIX_PATH="$P" -DVulkan_INCLUDE_DIR="$P/include"
    cmake --build "$SRC/build-vulkan" -j"$(nproc)" "${TARGETS[@]}"
    "$SRC/build-vulkan/bin/llama-bench" --version ) 2>&1 | tee build_vulkan.log
fi
