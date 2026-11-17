# JIT P0: scorecard and re-measure

Historical task brief recovered verbatim on 2026-11-17. This is an archive, not an instruction to launch or restart work. Paths, measurements, task status, and operational rules may be outdated. See [the recovery index](../../README.md) and the newer coordination handoff before using it.

Source: <t3-thread://v2/df925567-22cf-40cf-9a2c-46fb2bd05b71/3d78b1cc-ea92-4e4d-9957-9b496b4a1270>, activity position 70, item `turn-item:provider:claudeAgent:native-item:toolu_011h1FeCrkhuXAS3ES4QudJu`.

---

You are working in a git worktree of SilkJS: a JavaScript engine written in the Silk language (a native port of QuickJS) plus a Node-compatible runtime. Repo layout: `modules/engine` (package `silkjs`, the engine and the `silkjs` CLI), `modules/runtime` (Node-compatible runtime). Read the root `README.md` and `modules/engine/bench/README.md` first.

## Background
We are starting a multi-month project to add an optional JIT compiler to SilkJS that should reach V8 and JavaScriptCore on peak throughput and beat them on warmup, pause time, memory and startup. Before any compiler work we need a trustworthy scorecard. Your job is Phase 0: build that scorecard and record current numbers. You do not write any JIT code.

What is already known (from a stale Nov 6 binary, single runs, 8-CPU Linux x86-64): on the V8 suite in `modules/engine/bench/v8`, SilkJS scored 2960, `node --jitless` 3674, `node --no-opt --no-maglev` 5157, full Node 24.22.1 scored 25194. These must be re-measured on current head. JavaScriptCore has never been measured.

## Environment facts
- Silk toolchain 0.1.0-dev.69 is already installed (`silk` on PATH). Do NOT run `silk use` or `silk set`.
- Build the release CLI from `modules/engine` with `silk build --release`. The binary lands under the worktree root at `build/llvm/x86_64-unknown-linux-gnu/release/silkjs` (confirm the path from build output).
- `node` v24.22.1 is at `/usr/local/bin/node`. `valgrind` and `perf` are installed. `d8` and `jsc` are NOT installed.
- Existing tools: `modules/engine/scripts/v8bench.py` (suite scores, and `--instructions` for callgrind instruction counts), `scripts/bench.py` (macro + micro benchmarks, `silk task bench`), `scripts/ab.py` (A/B of two binaries), `scripts/pgo_build.py`.
- Other agents are compiling on this machine at the same time, so wall-clock numbers will be noisy. Take the best of several runs, record how many runs, and say so in the output. Use `--instructions` where a deterministic figure is needed.

## Tasks, in order
1. Build head with `silk build --release` in `modules/engine`. If it fails, report the exact error and stop; do not try to fix engine code.
2. Get standalone `d8` (V8) and `jsc` (JavaScriptCore) binaries. Preferred: `npx jsvu` (or `npm i -g jsvu`) with `--os=linux64 --engines=v8,javascriptcore`, which installs to `~/.jsvu/bin`. If jsvu cannot fetch JSC for Linux, try the WebKitGTK `jsc` from the distro packages (do not use sudo if it prompts; report instead). If an engine cannot be obtained, say exactly what you tried and carry on with the others; never invent numbers.
3. Extend `scripts/v8bench.py` so any number of engines can be given, each as `label=command with args` (for example `v8-jitless="d8 --jitless"`), while keeping the current positional-path form working. The suite uses `print`; check the existing `PRINT` shim works under d8 and jsc.
4. Write `modules/engine/scripts/scorecard.py`. For each configured engine it measures and prints one table, and writes the same data as JSON:
   - Throughput: the V8 suite score per test and the suite score.
   - Time to peak: for each V8-suite test, run a fixed number of iterations in one process, timing each iteration inside JS (use `performance.now()` where available, else `Date.now()`; check what each shell offers), and report iteration 1 time, steady-state time (median of the last third), and how many iterations until within 10% of steady state.
   - Startup: wall time of an empty script and of `bench/macro/startup.js`, best of 20.
   - Peak memory: max RSS (from `/usr/bin/time -v` or `resource.getrusage` on the child) for each V8-suite test.
   - Pause proxy: within the time-to-peak run, the worst single iteration divided by the steady-state median, for Splay.
   - Binary size of the engine executable.
   Default engine set: silkjs (head release build), node, `node --jitless`, `node --no-opt --no-maglev`, d8, `d8 --jitless`, jsc, and jsc with its JIT disabled (find the right flag, likely `--useJIT=false`; verify it by checking the option exists in `jsc --options` or equivalent). Missing engines are skipped with a printed note, not an error.
   Follow the code style of the existing scripts (plain Python 3 standard library, argparse, no new dependencies).
5. Run the scorecard and save the JSON as `modules/engine/bench/results/scorecard-<short git sha>.json`. Include host info, date, engine versions, run counts.
6. Add a short section to `modules/engine/bench/README.md` documenting `scorecard.py` (how to run it, what each column means, the noise caveat). Match the README's existing tone: plain, factual, no marketing.
7. Larger suites: check whether JetStream 2 (or 3) and the Web Tooling Benchmark can run under the `silkjs` CLI shell. Do not vendor them into the repo in this task. Clone them somewhere under `/tmp`, try to run their CLI drivers under silkjs and node, and report which tests run, which fail and why (missing shell globals, unsupported features, crashes). This is a feasibility report only.

## Rules
- Do not modify anything under `modules/engine/src` or `modules/runtime`. Scripts, bench results and the bench README only.
- Never fabricate or estimate a measurement. Every number you report must come from a run you made; if a run failed, say so.
- Commit your work on a new local branch named `jit/p0-scorecard` in this worktree, in small commits with plain descriptive messages. Do NOT push and do NOT open a pull request.
- Do not start subagents.

## Final report (your last message)
- Branch name and commit list.
- The scorecard table as measured, plus how many runs and how noisy they looked.
- Which engines you obtained, their versions and paths, and what failed.
- The JetStream / Web Tooling feasibility findings.
- Anything in the instructions that turned out to be wrong or impossible.
