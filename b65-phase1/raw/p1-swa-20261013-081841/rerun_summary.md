# Gemma llama-server rerun: p1-swa-20261013-081841

2026-10-13T08:18:41-04:00 · version: 0.6.0-dev (build 11574, commit 8bb3cf0d2) · fa=0 · ctx 32768 · median of reps

| Config | Prompt | TTFT s | Prompt tok/s | Gen tok/s | Board W | Reps |
|---|---|---|---|---|---|---|
| baseline (p1-20261012-180308) | 512 | 25.25 | 20 | 17.58 | 86 | 3 |
| baseline (p1-20261012-180308) | 4096 | 108.30 | 38 | 16.52 | 72 | 3 |
| baseline (p1-20261012-180308) | 16384 | 146.58 | 112 | 13.64 | 93 | 3 |
| ckpt-off (--ctx-checkpoints 0) | 512 | 1.36 | 377 | 17.57 | 167 | 3 |
| ckpt-off (--ctx-checkpoints 0) | 4096 | 11.08 | 370 | 16.52 | 158 | 3 |
| ckpt-off (--ctx-checkpoints 0) | 16384 | 49.36 | 332 | 13.64 | 155 | 3 |
| swa-full (--swa-full) | 512 | not run | | | | |
| swa-full (--swa-full) | 4096 | not run | | | | |
| swa-full (--swa-full) | 16384 | not run | | | | |
| default (defaults) | 512 | 25.29 | 20 | 17.57 | 85 | 3 |
| default (defaults) | 4096 | 108.49 | 38 | 16.52 | 71 | 3 |
| default (defaults) | 16384 | 146.75 | 112 | 13.63 | 92 | 3 |

## Loaded idle (30 s) and VRAM

| Variant | Status | Idle W | VRAM MiB |
|---|---|---|---|
| ckpt-off | ok | 42.8 | 24244 |
| swa-full | oom |  |  |
| default | ok | 44.8 | 24244 |
