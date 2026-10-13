# Phase 3 quality summary

| Model | Coding | Tools | Notes recall | Total s |
|---|---|---|---|---|
| gemma-4-31b-qat | 9/10 | 10/10 | 5/5 | 708 |
| muse-glimmer | 10/10 | 10/10 | 5/5 | 492 |
| qwen3.8-27b | 9/10 | 10/10 | 5/5 | 610 |

Failures:
- gemma-4-31b-qat c08: //x.com/a"></head>')=='https://x.com/a'
           ^^^^^^^^^^^^^^^^^
NameError: name 'extract_canonical' is not defined

- qwen3.8-27b c08: //x.com/a"></head>')=='https://x.com/a'
           ^^^^^^^^^^^^^^^^^
NameError: name 'extract_canonical' is not defined

