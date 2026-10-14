<!--
Article version of recommended-settings.md, for X Articles and LinkedIn articles.
- Neither editor renders Markdown tables, so there are none. Paste the text section by section.
- Insert each [IMAGE] from charts/conclusion/ (use the -wide.png versions) where it appears, and delete the marker line.
- Cover image: b65-sum-banner.png on X (3000×1200, exactly 5:2; it shows the ASRock card, from ASRock's product photo). LinkedIn's cover is 1.91:1, so use b65-sum-recipe-wide.png there and check the crop.
- If an editor doesn't offer code blocks, paste the command as its own paragraph.
- The sources are in recommended-settings.md and the phase findings. Every number here comes from them.
-->

# Title options
- **X (Articles):** The best llama.cpp settings for Intel's Arc Pro B65: what 7 rounds of testing found
- **LinkedIn:** I spent two days benchmarking local AI on Intel's Arc Pro B65. Here's the setup I'd actually run.
- **Short:** Running 30B models on a 32 GB Intel Arc Pro B65: the settings that matter

---

# The best llama.cpp settings for Intel's Arc Pro B65

Intel's Arc Pro B65 has 32 GB of VRAM, enough to run today's ~30B open models locally at 32K context. But the setup you choose makes a huge difference. On the same card, the same model can be 2× faster or 19× slower depending on a few flags.

Over two days I ran seven rounds of benchmarks on it with three models and two llama.cpp backends. This is where I landed.

[IMAGE: b65-sum-recipe-wide.png]

## The short answer

Run llama.cpp's **SYCL** backend (Intel oneAPI), not Vulkan, with:
- flash attention **on**
- a micro-batch of **2048** (`-b 2048 -ub 2048`)
- every layer on the GPU
- 32K context
- context checkpoints at their default
- **thinking off** for Qwen when it's coding

```
llama-server -m model.gguf -ngl 99 -c 32768 --jinja -fa on -b 2048 -ub 2048
```

For Qwen on coding work, add `--reasoning-budget 0`. For Gemma in agent loops that only ever append to the conversation, add `--ctx-checkpoints 0`.

## What I tested

- **Card:** ASRock Arc Pro B65 Creator, 32 GB, a blower-cooled card with a 200 W board power cap.
- **Host:** Ryzen 7 5700X, 48 GB RAM, Arch Linux (Omarchy), kernel 7.2.5.
- **Models:** Qwen 3.8 27B, Gemma 4 31B QAT and Muse Glimmer 28B, all 4-bit GGUFs from lmstudio-community.
- **Engines:** llama.cpp build 11574, built twice from the same commit: Vulkan (Mesa 26.2.2) and SYCL (oneAPI 2026.0).
- **Speed tests:** llama-bench (5 runs each) and llama-server (time to first token on 512, 4K and 16K-token prompts).
- **Quality checks:** coding tasks scored by running tests on the code, tool calling, recall over notes, and a blind writing ranking.
- **Power:** GPU board power from the driver's sensor. There's no wall meter, so every power figure here is the card's, not the whole PC's.

## 1. Use SYCL, not Vulkan

On the same llama.cpp commit, SYCL with flash attention on was **21.8% faster at generating text** and **31.2% faster at reading prompts** than Vulkan, averaged over all three models.
- **Efficiency:** generation went from 0.100 to 0.115 tokens per joule.
- **Memory:** all three models used 1.5–3.3 GiB less VRAM at 32K context.
- **The one exception:** Qwen at 32K context generates 5% slower on SYCL (15.3 vs 16.1 tok/s). Everywhere else SYCL wins.

[IMAGE: b65-sum-decode-wide.png]

Speed also holds up better as context grows. At 32K tokens of context, Muse generates 22.3 tok/s on SYCL, against 14.7 on Vulkan, and Gemma 16.1 against 12.8. All three stay above 15 tok/s.

## 2. Flash attention: on for SYCL, off for Vulkan

This one flips between backends, and getting it wrong is costly.
- **On SYCL,** flash attention adds 18.5% to generation speed on average. For Gemma at 32K context it's the difference between 10.0 and 16.1 tok/s.
- **On Vulkan,** it does the opposite. With it on, Gemma read a 16K-token prompt at 38 tok/s; with it off, 335 tok/s.

## 3. Raise the micro-batch to 2048 (on SYCL)

llama.cpp processes prompts in chunks of 512 tokens by default. Raising that to 2048 made prompt reading 35–55% faster on SYCL, with no real change to generation speed (within about 1%). It costs about 0.5–0.7 GiB of extra VRAM.

[IMAGE: b65-sum-ttft-wide.png]

On a 16K-token prompt, the first word now arrives in:
- **Qwen:** 20.5 s, against 42 s on Vulkan.
- **Muse:** 20.5 s, against 42 s.
- **Gemma:** 31 s, against 49 s.

Short prompts were already fast. Qwen and Muse answer a 512-token prompt in under a second.

Don't do this on Vulkan: there, a 2048 micro-batch made Muse's prompt reading 36% *slower*.

## 4. Leave context checkpoints on

llama-server keeps checkpoints of the conversation cache, so it can roll back when you regenerate a reply or edit an earlier message. Turning them off (`--ctx-checkpoints 0`) looked like a free speedup when I only tested chats that append new turns. Then I tested regenerating and editing:
- **Qwen with checkpoints off** re-read the entire 9,400-token chat every time I hit regenerate: 11.3 s before the first word, against 0.17 s with checkpoints on.
- **Every model with checkpoints off** re-read the whole chat when I edited an earlier message.

There are two exceptions where off is better:
- **Gemma on Vulkan:** with the default checkpoints, a 512-token prompt took 25 s to first word; with them off, 1.4 s.
- **Gemma in agent loops that only append:** 3.2 s per turn instead of 6.0 s.

## 5. Turn thinking off for Qwen when it's coding

With thinking on and a 2K-token cap, Qwen failed one of ten coding tasks: it was still thinking when it ran out of tokens.

With thinking off (`--reasoning-budget 0`), it passed **10 out of 10**, and **30 out of 30** over three tries per task. The median answer was 130 tokens, and the whole set ran about 4× faster.

Two caveats:
- **Muse ignored the thinking-off switches** and thought anyway. It still passed every task.
- **If you leave thinking on,** give coding tasks at least 4K tokens. With more room, Gemma solved the task it had failed at 2K.

## Settings that cost you

Here are the five that hurt most in my testing, each one measured:

[IMAGE: b65-sum-traps-wide.png]

- **Flash attention on, with Vulkan:** Gemma's prompt reading was 89% slower.
- **Default context checkpoints, with Vulkan:** Gemma took 19× longer to start answering.
- **Flash attention off, with SYCL:** Gemma's generation at 32K context was 38% slower.
- **A 2048 micro-batch, with Vulkan:** Muse's prompt reading was 36% slower.
- **Context checkpoints off:** Qwen took 67× longer to regenerate a reply.

## Which model for what

[IMAGE: b65-sum-models-wide.png]

- **Muse Glimmer 28B, the all-rounder.** It has the fastest generation (25.7 tok/s on an empty context, 22.3 at 32K) and the smallest footprint (16.4 GiB at 32K context). It scored 10/10 on the coding tasks and finished the 30 quality tasks quickest.
- **Qwen 3.8 27B, for quick coding answers.** With thinking off it scored 30/30, at about 130 tokens per answer.
- **Gemma 4 31B QAT, for writing.** It won my blind writing ranking, first on 3 of 5 prompts. It's the slowest to start answering and needs the most memory (20.4 GiB at 32K).

All three got every tool call and every recall question right, so those didn't separate them.

## Power

- **Generating text:** the card draws 165–199 W, close to its 200 W cap but with no sign of throttling.
- **Idle:** about 45 W with a model loaded.

These are GPU board power, not wall power.

## What this doesn't cover

- **Scale:** the quality checks are small and self-made. Treat them as sanity checks, not a leaderboard. The writing ranking had one rater and five prompts.
- **Versions:** every number is for these driver and llama.cpp versions. Updates can change them, so re-measure after upgrading.
- **The slot:** the card sat in a PCIe 4.0 x4 slot. I didn't measure the effect, which should mostly be on model load time.
- **Not tested:** other engines such as vLLM, and Muse with thinking actually off.
- **Unexplained:** Gemma on SYCL has a floor of about 1.1 s per request, so on tiny prompts Vulkan answers 0.3–0.6 s sooner.

## The bottom line

On the Arc Pro B65, the backend and four flags matter more than which of these three models you pick:
- llama.cpp on SYCL, flash attention on, a 2048 micro-batch and 32K context
- context checkpoints left alone, and thinking off for Qwen's code

With that setup, a 32 GB Intel card runs 30B-class models at 15–26 tokens per second, and starts answering a 16K-token prompt in 20–31 seconds.

What are you running locally, and on what hardware?

---

## Post to share the article (≤280 characters)

I benchmarked local AI on Intel's 32 GB Arc Pro B65 for two days: 3 models, 2 llama.cpp backends, 7 rounds.

The setup I'd run, and the five settings that cost the most speed:

[link]

What's on your local AI rig?
