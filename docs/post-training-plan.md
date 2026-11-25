# Post-training plan for Bro's local planner

Started 2026-11-25.

## Goal

Make Bro's local planner (Qwen3.6-35B-A3B, served as `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q2_K_XL` via Splash) faster and more accurate in Bro's own harness. Speed first, pass rate as a guardrail, same as the benchmarks.

## Decisions

- **Train bf16 LoRA, then quantize.** Train on the bf16 model, merge, re-quantize to UD-Q2_K_XL, serve via Splash as today. Every eval reports base 2-bit, tuned bf16 and tuned 2-bit, so we know whether the gain survives quantization.
- **No benchmark tasks in training.** Never train on Emergence WebVoyager or Online-Mind2Web tasks or trajectories. Any third-party env must have those tasks (and their sites, for live-site envs) removed.
- **WebArena first.** Self-hosted sites, programmatic rewards, resettable. Its sites (shop, shop admin, Reddit clone, GitLab, map, Wikipedia) don't overlap Emergence or OM2W. Train on the ~650 non-Lite tasks, keep WebArena-Lite (165) as the held-out eval.
- **Reward = success − step penalty** (plus a penalty for no-op / repeated actions, which Bro already detects).
- **Train through Bro's harness.** The policy sees Bro's observer output and emits Bro's action DSL, so we train the agent we ship. The main build is an env ↔ Bro adapter, not a new env.

## Prior art (checked 2026-11-25)

Nobody has published a Qwen3.6-35B-A3B tuned for browser tasks.

| Work | Base | Note |
|---|---|---|
| [browser-use BU-30B-A3B-Preview](https://huggingface.co/browser-use/bu-30b-a3b-preview) | Qwen3-VL-30B-A3B | Closest match; tuned for browser-use's harness. No recipe or benchmarks published. GGUFs exist, so it's a cheap local comparison. |
| [Qwen-AgentWorld-35B-A3B](https://arxiv.org/html/2606.24597) | Qwen3.5-35B-A3B | Qwen's RL in simulated agent envs; possible alternative starting model if it beats ours in Bro's harness. |
| [Prequential test-time learning](https://arxiv.org/pdf/2609.35911) | Qwen3.5-35B-A3B | SFT + rejection sampling on WebArena. Read before building the loop. |
| [Structured distillation of web agents](https://arxiv.org/pdf/2604.07776) | Qwen3.5-9B | Distillation with WebArena gains. |
| [GRPO null result for small web agents](https://arxiv.org/pdf/2607.12640) | Small LM/VLM | GRPO failure depending on learning rate. Read for failure modes. |
| [WebGym](https://arxiv.org/html/2601.02439) | Qwen3-VL-8B | ~300k rubric-scored live-site tasks; 26% → 43% OOD. Later option, needs filtering against our benchmarks. |

## Environments

| Env | Reward | Hosting | Role |
|---|---|---|---|
| MiniWoB++ (via BrowserGym) | Programmatic | Static HTML, runs anywhere | Smoke-test the RL loop |
| WebShop | Programmatic | One Python server, fine under Singularity | Smoke test with more realistic pages |
| WebArena | Programmatic | Docker services (see below) | Main training env |
| WebGym / own env | Judge / rubric | Live sites | Only if WebArena gains don't carry over to live sites |

## Compute

### School cluster (preferred)

3× RTX A6000 (48 GB) on one node, 24 h job limit, no Docker, Singularity only.

- **Model fits, with time-sharing.** bf16 weights ≈ 70 GB. Rollouts: vLLM with TP=2 (16 attention heads, so TP=3 doesn't split evenly). Training: LoRA with FSDP over all 3 GPUs. Alternate between them (verl and ms-swift support colocated sleep mode).
- **24 h limit.** Each job saves LoRA weights, optimizer state and task-list position; the next job resumes.
- **Risks.** Qwen3.6's hybrid-attention MoE is new: LoRA training support and loading the adapter into vLLM are unproven ([known MoE LoRA issue](https://forums.developer.nvidia.com/t/anyone-have-a-solution-for-lora-training-of-recent-moe-models-like-qwen3-5-35b-a3b-or-gemma-4-26b-a4b-and-successfully-running-in-vllm/366223)). Ampere has no FP8. Rough speed: ~30 min per RL step at 128 trajectories.

### WebArena hosting (open problem)

| Site | Stack | Under Singularity |
|---|---|---|
| Shopping, Shopping admin | Magento + MySQL | Fiddly but doable |
| Reddit | Postmill + Postgres | Fiddly but doable |
| Wikipedia | Kiwix | Easy |
| GitLab | GitLab Omnibus | Hard |
| Map | OSM tiles, search, routing | Heavy |

Singularity issues: no root, read-only filesystem, no ports below 1024, and every episode needs a state reset (restore a clean data directory).

Options:
1. Singularity on the cluster, starting with Shopping, Shopping admin, Reddit, Wikipedia.
2. WebArena's AWS image on a cloud box (Docker works, resets are container restarts); the cluster runs browsers and training and connects over the network. Roughly tens of dollars per training day.

### Tinker (fallback)

Qwen3.6-35B-A3B prices per 1M tokens, as of 2026-10-19 ([pricing](https://thinkingmachines.ai/tinker/pricing/)): prefill $0.45, cached prefill $0.09, sample $1.335, train $1.177 (64K).

Assuming ~3.5k prompt tokens and ~50 output tokens per step, ~15 steps per task, every step trained as its own sequence: **~$0.08 per trajectory** (~80% of it training).

| Run (GRPO, 8 rollouts per task) | Trajectories | Approx. cost |
|---|---|---|
| Pilot: 16 tasks/batch × 25 steps | 3,200 | ~$250 |
| Real: 32 tasks/batch × 40 steps | 10,240 | ~$800 |
| Big: 64 tasks/batch × 50 steps | 25,600 | ~$2,000 |

Steps per task is the biggest unknown; the baseline pass measures it.

## Phases

0. **Feasibility checks (half a day each, in parallel)**
   - Cluster: LoRA training step on Qwen3.6-35B-A3B (verl or ms-swift); adapter loads into vLLM.
   - Hosting: Shopping + Reddit under Singularity; scripted resets.
   - Ask admins: is `--fakeroot` enabled? Do compute nodes have outbound internet?
1. **Baselines**
   - Bro ↔ BrowserGym adapter (observer output in, action DSL out).
   - Current 2-bit and bf16 on MiniWoB and WebArena-Lite; record steps per task.
   - Optional comparisons: BU-30B-A3B-Preview, Qwen-AgentWorld-35B-A3B.
2. **RL loop on MiniWoB / WebShop**
   - GRPO, step-penalty reward, checkpoint/resume across 24 h jobs.
   - Goal: debug the pipeline end to end (train → merge → quantize → Splash → bench), not scores.
3. **RL on WebArena** (non-Lite tasks)
   - Eval on WebArena-Lite, then on the live-site benchmarks (Emergence held-out runs, OM2W) to check transfer.
   - Fall back to Tinker if the cluster path fails.
4. **Only if needed:** live-site RL with a judge reward (WebGym, filtered) or our own env.

## Open questions

- Cluster: `--fakeroot`? Outbound internet from compute nodes?
- Does the gain survive 2-bit quantization?
- Does WebArena training transfer to live sites?
