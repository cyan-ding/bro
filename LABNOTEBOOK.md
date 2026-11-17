# Bro lab notebook

Every experiment behind the results in [README.md](README.md), in the order it was run: setups, numbers, dead ends and caveats. The README is the summary; this is the record.

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

### Working while it works: memory budget

MLX wires the whole model into memory (the 4-bit 35B planner holds about 21 GB), which leaves nothing for other apps on a 36 GB Mac. When the full model does not fit, Bro now serves a 2-bit build of the same model through [Splash](https://github.com/incoai/splash) with a memory cap (`BRO_SPLASH_CAP_GB`, default 10), which keeps the hot experts in RAM and streams the rest from SSD. Measured with ~16 GB of other apps open (28 tasks):

| planner build | cap | pass | median task | per call (1.7k-token prompt) | peak wired | memory compressed |
|---|---|---|---|---|---|---|
| 4-bit, MLX, apps closed | none | 26/28 | 4.6 s | 1.08 s | ~22 GB | ~2 GB |
| 4-bit, Splash | 14 GB | 28/28 | 10.3 s | 2.76 s | 17.3 GB | 5.4 GB |
| 2-bit, Splash | 12 GB | 28/28 | 7.0 s | 1.17 s | 15.3 GB | 6.0 GB |
| 2-bit, Splash | 10 GB | 28/28 | 7.2 s | 1.62 s | 13.4 GB | 3.2 GB |
| 2-bit, Splash | 8 GB | 28/28 | 8.4 s | 4.02 s | 11.2 GB | 3.1 GB |

The 2-bit build (`unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q2_K_XL`) lost no accuracy on either task set; capping the 4-bit build instead only starves it. `bro/bench/memsweep.py` prints this table from the per-run memory samples.

### Emergence WebVoyager (535 tasks)

Two full passes with the memory-safe configuration above (2-bit planner, 12 GB cap, other apps open, no reflex, text-only LLM judge over the benchmark's own annotator questions). `bro/bench/tasks_emergence.json` is generated from the benchmark's templates by its own `instantiate_tasks.py`.

| budget | pass | median task | tasks that hit the step cap |
|---|---|---|---|
| 15 steps, 20 s navigation timeout | 212/535 (39.6%) | 27 s | 274 |
| 25 steps, 45 s navigation timeout | 218/535 (40.7%) | 38 s | 216 |

Raising the budgets changed little: 67 tasks flipped to pass and 61 flipped to fail, which is the run-to-run noise of live websites, and most failing tasks still ran to the cap, so the limit is the agent (text-only, no vision), not the budget. Per site the range is Amazon and Cambridge Dictionary at 27/35 down to Booking 6/35 and Google Flights 0/35 (the site never loads in the automation browser). For reference, the benchmark's authors report 68.6% for OpenAI's Operator and 81% for Agent-E with human annotators.

### Closing the feedback loop

Two generic fixes to the agent loop, measured on a fixed 150-task Emergence subset (`tasks_emergence_150.json`, ten per site) against the previous night's run on the same tasks:

- **Effect detection.** After every action the page is observed again; the model is told "nothing on the page changed" instead of "ok", elements that did nothing twice are dropped from the menu, two stalled steps trigger a replan prompt, four trigger a return to the start page. A click that only toggles the page back to a state already seen counts as no progress.
- **A real browser.** `BRO_BROWSER=patchright` launches Chrome through Patchright instead of attaching to a bare `--remote-debugging-port` profile. Google properties never finished loading in the bare profile; they load normally this way.

| arm | pass | tasks with 8+ identical repeated actions |
|---|---|---|
| previous loop, bare Chrome profile | 65/150 (43.3%) | 23 |
| effect detection, bare profile | 72/150 (48.0%) | 7 |
| effect detection, Patchright Chrome | 76/150 (50.7%) | 8 |
| + oscillation detection, Patchright | 72/150 (48.0%) | 2 |

The feedback loop is worth about five points and the browser about three (Google Flights went from 0/10 to 6/10). Oscillation detection removes the last loops but did not raise the pass rate: when the agent cannot find what it needs, it now explores instead of repeating, and still runs out of steps. Run-to-run noise on 150 live tasks is about four points, so smaller effects need repeated runs.

### Vision on demand and the browser-use-inspired changes (paired results)

Measured on the same 150-task subset against the previous best (effect detection + Patchright, 76/150):

| arm | pass | median task | notes |
|---|---|---|---|
| stable ids, click pre-checks, typing recipe, network-aware settle, `find`/`read`, delivery turn | 68/150 | 48 s | Hugging Face 4→9, arXiv 5→7; Google Flights 6→0 and Booking 5→2 |
| the same plus a screenshot before every `done` and on stalls | 66/150 | 64 s | Booking 2→7; BBC 6→1, Wolfram 3→0 |

Neither arm beat the baseline in aggregate, and the per-site swings show why. The first arm's oscillation rule counted any return to a previously seen page state as a no-op and dropped the element, which on dynamic sites removed the controls the agent needed (softened since: only an identical repeated action that bounces the page counts). The click pre-check refused 100 clicks, half of them false positives (a "Featured" badge overlapping a product card) and a quarter cookie-consent iframes whose buttons the observer cannot see because they are cross-origin; in both cases the agent repeated the click. The vision arm's losses were mostly not vision: three Wolfram tasks hit connection timeouts, and the BBC consent dialog became unpassable once clicks through it were refused. A vision call costs about 7 s on this hardware, so the arm was also the slowest. The mechanisms are kept, with two fixes queued: observe cross-origin iframes through Playwright frames, and retry a covered click at another point of the target before refusing.

### Background Chrome, headless mode, and the paired results (2026-11-15)

**Goal: the agent must never take the keyboard away from you.** Measured with a sampler that records the
frontmost macOS app every 10 s while the 150-task paired subset runs.

What is in the tree now (`bro/fast/browser.py`):

- One Chrome per benchmark run, launched through Patchright and sent behind the app you were using; one tab reused
  between tasks (opening a tab over the DevTools protocol raises the window on macOS); focus emulation instead of
  `bring_to_front`; tracker, font and media requests blocked at the network layer; 1440x1100 window, `en-US`,
  reduced motion.
- `FocusWatch`: every agent operation (action, screenshot, tab reset) samples the frontmost app before and after
  itself. If the agent's own Chrome (matched by PID) took the front and there was no human input in the last 1.5 s,
  focus is handed back and the action is named in the step log (`StepRecord.focus`). Your own switches into Chrome
  (click, cmd-tab, trackpad gesture) are left alone. No macOS permission beyond the one-time "control app X" prompt
  for re-activating your app. `BRO_FOCUS_GUARD=0` disables it.
- `BRO_HEADLESS=1`: `--headless=new` with the normal Chrome user-agent (the headless build announces itself as
  `HeadlessChrome`) on its own profile. No window exists, so nothing can take focus; Google Flights, Booking,
  Amazon, BBC load and bot.sannysoft.com shows no failed checks.

Paired results on `tasks_emergence_150.json` (local 2-bit Qwen3.6-35B under Splash, 12 GB cap, 25 steps):

| arm | config | pass | median s | Chrome frontmost |
|---|---|---|---|---|
| A | Pillar 1 loop, headful | 76/150 | 36.5 | not measured |
| p3_vision | all of the above, headful, `--vision` | 65/150 | 59.6 | 43 of 945 samples (4 episodes, longest 5.7 min) |
| p3_novision | headless, fresh profile, no vision | 70/150 | 49.7 | 0 of 741 samples |

Two sites were lost to the environment rather than the agent: Cambridge Dictionary now serves a Cloudflare
challenge to this machine (0/10 and 1/10 vs 8-9/10 on earlier nights; a fresh profile passes one task and is then
challenged too), and Wolfram Alpha refused TCP connections for most of the night (0/10 in the headful arm, 6/10
once the block lifted during the headless arm). On the other 130 tasks the three arms are flat: 65, 65 and 63.
Vision therefore still does not pay for its ~7 s per screenshot at this model size; the browser fixes are neutral
on pass rate and solve the focus problem outright in headless mode.

Where headful Chrome took focus, by the `FocusWatch` log: clicks on Cloudflare's "verify you are human" checkbox
(cross-origin challenge iframe, 36 of 39 attributed events) and clicks on Coursera course cards. The agent does not
try to solve bot challenges; the practical answer is headless mode.

Also new: click refusals (covered, disabled, hidden targets) now count as no-ops, so a target that cannot be
clicked is flagged after one attempt and dropped after two (`_refuse`); the observer survives documents without a
`<body>`; `bro/bench/run.py` keeps one browser for the whole run and logs per-task focus events.

### Full Emergence WebVoyager rerun, Pillar 3, and a head-to-head with browser-use (2026-11-16)

**Full 535, headless.** Same local 2-bit Qwen3.6-35B (Splash, 12 GB cap), 25 steps, 240 s, headless Chrome, no
vision, code frozen at `232b2fb`, tasks in a fixed-seed shuffled order. **242/535 = 45.2%**, up from 218/535 =
40.7% on the earlier full run (104 tasks won, 80 lost); median 45.6 s per task. Chrome was never the frontmost app
(0 of 2,624 samples); peak compressed memory 10.7 GB. Without Cambridge Dictionary and Wolfram Alpha, whose
results tonight depended on bot checks and connection blocks aimed at this machine, 181/465 -> 214/465 (38.9% ->
46.0%). Biggest gains: Google Flights 0 -> 16/35 (the site now loads), Wolfram 10 -> 22, Huggingface 15 -> 24,
GitHub 12 -> 20. Biggest losses: Cambridge 27 -> 6 (Cloudflare challenge) and Amazon 27 -> 13 (CAPTCHA pages in most
Amazon failures; whether headless mode or traffic from this IP triggers it is not yet separated).

**Pillar 3, a cached-prefix "is the answer already on this page?" gate on the planner, was measured offline and not
shipped.** On 2,396 logged states, the planner's own weights (Qwen3.6-35B on OpenRouter, the agent's exact prompt
plus a YES/NO question) agreed with a criteria-aware judge at precision 0.66 and recall 0.32. Of the 45 tasks that
ran out of steps or gave no answer, the gate fired on 4, while it fired prematurely on 13 tasks that passed. The
same model cannot recognise, when asked, what it missed while acting.

**Head-to-head with browser-use 1.0.3** on 30 tasks (the first two of each site), both on `qwen3.6-35b-a3b` via
OpenRouter, both in headless Chrome with the same user-agent, recorded with one CDP screencast recorder:

| agent | pass | median time | total time |
|---|---|---|---|
| Bro fast loop | 15/30 | 18.2 s | 11.8 min |
| browser-use 1.0.3 | 12/30 | 85.4 s | 50.4 min ($0.50) |

On the 7 tasks both passed, browser-use took a median 6.8x as long. Each passed tasks the other missed (Bro only 8,
browser-use only 5), so the speed gap is the robust result and the accuracy gap is within noise at n = 30.

`bro/fast/llm.py` now disables hidden reasoning for `openrouter/` models: Qwen3.6 thinks by default there and used
the whole 400-token budget, returning nothing.

### Fastest local browser agent: Bro vs browser-use on the same local model (2026-11-17)

Both agents on the same machine (M4 Max, 36 GB), the same local 2-bit Qwen3.6-35B-A3B served by Splash under a
12 GB cap, headless Chrome with the same user-agent, the same 150 Emergence WebVoyager tasks (10 per site), 25 steps
and a 240 s limit, judged by the same judge. Bro ran as designed (one-line actions, no thinking); browser-use 1.0.3
ran at its defaults with a fresh browser profile per task.

| | Bro fast loop | browser-use 1.0.3 |
|---|---|---|
| tasks solved | **70/150** | 53/150 |
| median time per task | **43.7 s** | 113.0 s |
| median time on a solved task | **33.9 s** | 111.7 s |
| solved within 30 s / 60 s / 120 s | **30 / 53 / 70** | 2 / 7 / 31 |
| total wall clock for 150 tasks | **2.0 h** | 4.9 h |

On the 30 tasks both solved, browser-use took a median 3.3x as long (40.3 s vs 114.0 s). Bro alone solved 40,
browser-use alone 23. Caveats: Bro's numbers come from the 2026-11-16 full run, browser-use's from the following
night; Cambridge Dictionary favours browser-use (8/10 vs 1/10) because Bro's run reused a profile with a flagged
Cloudflare cookie, since fixed by clearing cookies per task (without Cambridge: 69/140 vs 45/140); three browser-use
tasks ended on its own per-run request limit.
