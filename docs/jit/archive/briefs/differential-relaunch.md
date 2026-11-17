# JIT P1: differential fuzzing harness (relaunch)

Historical task brief recovered verbatim on 2026-11-17. This is an archive, not an instruction to launch or restart work. Paths, measurements, task status, and operational rules may be outdated. See [the recovery index](../../README.md) and the newer coordination handoff before using it.

Source: <t3-thread://v2/df925567-22cf-40cf-9a2c-46fb2bd05b71/3d78b1cc-ea92-4e4d-9957-9b496b4a1270>, activity position 121, item `turn-item:provider:claudeAgent:native-item:toolu_01C5zDYMvgqWwVBVKp942MG6`.

---

You are working in a git worktree of SilkJS: a JavaScript engine written in the Silk language (a native port of QuickJS) plus a Node-compatible runtime. Layout: `modules/engine` (package `silkjs`, the engine and the `silkjs` CLI whose entry is `modules/engine/src/main.silk` with helpers in `cli_*.silk`), `modules/runtime`. Read the root `README.md` first. Learn Silk syntax from the existing sources (ownership, effects with `effect fn`/`run`, `unsafe`, `extern "C"` declarations as in `modules/engine/src/cli_io.silk`, `static if` on target).

## Background
We are adding an optional JIT compiler to SilkJS. The compiler has no reference implementation to translate from, so its correctness will rest on fuzzing and on differential testing against the interpreter. That harness must exist and be finding bugs in the interpreter before any compiled code exists. Your job is to build it. You write no JIT code.

Two execution configurations exist today and more will come: the dispatch loop in `modules/engine/src/js_vm.silk` is instantiated twice (`PlainRun` and `ObservedRun`; the observed copy runs when a debugger, coverage or CPU profiler observes instructions). Later there will be "interpreter only", "compile everything on first call", and "fail every speculation check on a schedule". The harness must be built so a new configuration is one more command line in a list.

## Environment facts
- Silk 0.1.0-dev.69 is installed; do NOT run `silk use` or `silk set`. Build the CLI with `silk build --release` in `modules/engine`; the binary lands under the worktree root in `build/llvm/x86_64-unknown-linux-gnu/release/silkjs` (confirm from build output).
- Other agents are compiling on this 8-CPU machine, so a release build can take a long time (tens of minutes). Run long commands with their output redirected to a log file inside the worktree (not `/tmp`), so the result survives if your shell session is lost, and check the log rather than rebuilding.
- `node` 24 is at `/usr/local/bin/node`, clang 22 at `/opt/llvm22/bin/clang`, `gcc`, `valgrind` and `perf` are installed. Swift may not be installed.
- Keep fuzzing runs you start to at most 2 worker processes and stop them before you finish.
- Existing correctness tooling to learn from: `modules/engine/scripts/check.py`, the `verify_*.py` scripts, the test262 runner (`run_test262`, `test262_runner` exports), `modules/engine/tests/`.

## Part A: differential runner (required)
Write `modules/engine/scripts/differential.py` (Python 3 standard library only, style of the existing scripts):
- Input: a list of JS files or directories, and a list of named configurations, each a command line (default set below).
- For each program, run it under every configuration with a timeout and a memory limit, capture stdout, stderr, exit status and whether it timed out, and compare all configurations against the first (the reference). Report any difference.
- Normalize only what must be normalized, and document each rule in the script: for example stack-trace text and error-message wording differ between engines, so when comparing SilkJS with Node compare a canonical outcome (printed values plus the error's constructor name) rather than raw stderr. Between two SilkJS configurations compare everything byte for byte.
- Programs whose output legitimately depends on timing, randomness, memory addresses or GC timing produce false alarms. Provide a prelude (prepended to every program) that makes `Math.random` deterministic from a seed and pins `Date.now`/`new Date()`; and detect and skip programs that still vary by running the reference configuration twice.
- On a difference, save a self-contained reproducer directory (program, both outputs, both command lines) and try to minimize the program with a simple line/statement delta reduction that keeps the difference.
- Exit status nonzero when any difference is found; a summary line with counts.
Default configurations: SilkJS plain; SilkJS with the observed loop forced on for the whole run (find what turns observation on from the CLI, for example coverage or CPU-profile options in `cli_options.silk`; if there is no CLI switch that forces it without changing output, add a minimal hidden debug option to the CLI and say so in your report); and Node as an optional third reference that is off by default.
Run it over `modules/engine/tests/silkjs/`, `modules/engine/bench/macro/` and the V8 suite files in `modules/engine/bench/v8/` (see `scripts/v8bench.py` for how those are concatenated with `base.js` and a runner), fix harness false alarms, and report every real difference you find with its reproducer. Do not fix engine bugs you find; report them precisely.

## Part B: program generator (required)
A fuzzer needs inputs that reach optimizable code. Write `modules/engine/scripts/jsgen.py`: a seeded random generator of terminating, deterministic JS programs aimed at what a JIT will speculate on. Each program must print a checksum of everything it computed so wrong results are visible. Cover at least: int32 arithmetic including overflow to double and `-0`; double arithmetic including NaN and infinities; bitwise and shift operators; comparisons across mixed types; objects with stable shapes, then shape changes mid-loop (add, delete, reorder properties, change prototype, define accessors); monomorphic call sites that turn polymorphic and megamorphic; arrays that change element kind (integers, doubles, holes, mixed, strings), out-of-bounds reads and writes, `length` changes; typed arrays; closures capturing loop variables; `arguments`; getters/setters and proxies that mutate the receiver during access; exceptions thrown from inside hot loops and from callees; `try/finally`; generators and async functions; string concatenation and indexing; `switch`; recursion. Structure every program as a hot phase that runs a function many thousands of times with stable types followed by a phase that breaks one assumption and then keeps running, since that is the pattern that exposes bad speculation and bad deoptimization. All loops must have fixed bounds. Wire it into `differential.py` (`--generate N --seed S`), run at least a few thousand programs across the default configurations, and report results.

## Part C: Fuzzilli feasibility (investigate, implement only if cheap)
Fuzzilli (github.com/googleprojectzero/fuzzilli) is the standard coverage-guided JS engine fuzzer. It needs (1) the target shell to implement its REPRL protocol (commands over file descriptors 100–103, a `fuzzilli` builtin with a crash and a print operation, resetting engine state between executions), (2) edge coverage via clang's `-fsanitize-coverage=trace-pc-guard` with the shared-memory bitmap from Fuzzilli's `Targets/` examples, and (3) a Swift toolchain to build Fuzzilli, plus a target profile. Find out and report, with evidence:
- whether the Silk build can pass `-fsanitize-coverage=trace-pc-guard` (or any coverage instrumentation) through to LLVM for Silk code; look at how `scripts/pgo_build.py` passes instrumentation flags to clang, since PGO instrumentation already works;
- whether a REPRL mode can be added to the CLI as a separate entry point without touching the hot paths (look at how the CLI creates and destroys a runtime and context, and whether a fresh context per execution is cheap);
- whether Swift can be installed on this machine without sudo.
If all three are straightforward, implement the REPRL entry point and a Fuzzilli profile, and run a short session. If any is blocked, stop at the report; do not spend most of your time here. Parts A and B are the deliverable.

## Part D: make it a task
Add the differential run over the fixed corpus (not the generator) to the engine's task list so it can be run as one command; look at how `silk task check` and `silk task bench` are defined (the `tasks` build in the engine) and follow that pattern. Document both scripts briefly in a new `modules/engine/tests/README.md` or the nearest existing README, in the repo's plain factual tone.

## Rules
- Engine source edits are limited to CLI code needed for a debug switch or a REPRL entry point. Do not touch `js_vm.silk`, `js_core_types.silk`, `js_gc.silk` or the bytecode/compiler files; another agent is editing those.
- Never report a result you did not run. Give the command and the counts. If the generator finds nothing, say that, along with how many programs ran and what they covered.
- Commit on a new local branch `jit/p1-differential-fuzz` in small commits with plain messages, and commit as you go so work survives an interrupted session. Do NOT push, do NOT open a pull request.
- Do not start subagents.

## Final report (your last message)
- Branch and commits.
- How to run each tool, and the default configuration list.
- Every real difference or crash found, each with a minimized reproducer path and one-line description.
- Normalization rules and skipped-program counts.
- Fuzzilli findings for the three questions, and what was implemented.
- What a future agent must do to add a new configuration (for example "compile everything").
