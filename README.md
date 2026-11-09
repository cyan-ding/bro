# Bro

Bro is a locally run browser-use agent inspired by [Browser-Use](https://github.com/browser-use/browser-use).

## Functions

Bro is model agnostic and you can use the dashboard to start and view runs.
- Onboarding sets up Chrome, API keys, storage, and which models to use (from providers your keys unlock).
- There is an optional Supabase integration to store data in the cloud. All data flows to your own account.
- The other option is local storage on disk.

## Tools Used

- Bro connects to your installed Chrome over CDP (via Patchright) and uses the DOM to find clickable elements.
- Frontend is Next.js in an Electron app; backend is a FastAPI agent loop.

## Fast mode (local models)

Fast mode is a second agent loop built for latency. Instead of a screenshot plus a long reasoning JSON every step, it sends the model a compact text view of the page (visible text and interactive elements) and asks for one to three one-line actions (`click 12`, `type 7 "query"`, `done "answer"`). The system prompt never changes, so a local server can serve it from its prefix cache; only the page changes each step.

- Fast mode is the default for new runs. Tick "Classic loop" in Run Settings to use the original screenshot loop.
- Local models run through [mlx-lm](https://github.com/ml-explore/mlx-lm) on Apple Silicon. Install it with `uv sync --extra local`, then pick any `local/...` model in settings; Bro starts the server on demand. `mlx-community/Qwen3.6-35B-A3B-4bit` (about 21 GB, 3B active parameters) was the best speed and accuracy trade-off on an M4 Max.
- Set `BRO_LOCAL_BASE_URL` to point at an already running OpenAI-compatible server (default `http://127.0.0.1:8080/v1`).

### Benchmark

`bro/bench` runs both loops against the same task list and records per-step timing and token usage.

```bash
uv run python -m bro.bench.run --agent fast --model local/mlx-community/Qwen3.6-35B-A3B-4bit --out results.jsonl
uv run python -m bro.bench.run --agent legacy --model openrouter/google/gemini-2.5-flash --out legacy.jsonl
```

`tasks.json` holds 28 checkable tasks across arXiv, Wikipedia, GitHub, Cambridge Dictionary, Hugging Face, Wolfram Alpha, Allrecipes, Apple, Coursera, Hacker News, Amazon, ESPN, BBC and Google Maps; `tasks_webvoyager.json` is a 26-task subset of WebVoyager scored by an LLM judge. Results on an M4 Max (36 GB), November 2026, live websites:

| loop | model | 28 tasks: pass | median time | WebVoyager subset: pass | median time |
|---|---|---|---|---|---|
| classic (screenshots) | Gemini 2.5 Flash | 25/28 | 22.8 s | 10/26 | 58.3 s |
| fast | Gemini 2.5 Flash | 25/28 | 2.8 s | 19/26 | 9.2 s |
| fast | local Qwen3.6-35B-A3B (4-bit) | 28/28 | 5.1 s | 16/26 | 10.2 s |

The local model spends about 1.2 s per step in the LLM (almost all of it prompt prefill at roughly 1,300 tokens/s), 0.6 s acting and settling, and under 10 ms observing the page.

### System 1 / System 2

`bro/fast/system1.py` adds a reflex layer in the style of [Jev](https://docs.typesafe.ai/api/): before each planner step the page is turned into a fixed menu (click one of the listed elements, scroll, go back, or hand over to the planner) and a decision model returns a probability for every option. A confident pick is executed without calling the planner; anything else escalates to System 2. Decisions come either from a local model's first-token logprobs (`--s1 local/<model>`) or from Jev through OpenRouter's decisions endpoint (`--s1 jev`). `bro/bench/replay_s1.py` and `bro/bench/calib.py` score candidate System 1s offline on logged page states (`--log-states`), one model in memory at a time.

What the calibration and live runs showed (28 tasks, GitHub tasks excluded because of an outage that night):

| planner | System 1 | pass | median | s/step | S1 share |
|---|---|---|---|---|---|
| local Qwen3.6-35B-A3B | none | 23/24 | 4.9 s | 2.11 | |
| local Qwen3.6-35B-A3B | Jev, threshold 0.7 | 23/24 | 4.6 s | 1.80 | 23% |
| local Qwen3.6-35B-A3B | itself as reflex, 0.7 | 24/24 | 6.3 s | 2.14 | 30% |
| Gemini 2.5 Flash | none | 21/24 | 3.1 s | 0.93 | |
| Gemini 2.5 Flash | Jev, 0.8 | 22/24 | 3.3 s | 1.26 | 22% |

Jev agrees with the planner on about 55% of click/scroll states at 180 ms per decision; Qwen3.5-0.8B and 2B pick at chance level, 4B and 9B are too weak and too slow to help. The reflex only pays off when the planner is expensive: it saves 15% per step with the local planner and loses time with the cloud one.
