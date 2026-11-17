# JIT P1: differential test runner

Historical task brief recovered verbatim on 2026-11-17. This is an archive, not an instruction to launch or restart work. Paths, measurements, task status, and operational rules may be outdated. See [the recovery index](../../README.md) and the newer coordination handoff before using it.

Source: <t3-thread://v2/df925567-22cf-40cf-9a2c-46fb2bd05b71/3d78b1cc-ea92-4e4d-9957-9b496b4a1270>, activity position 127, item `turn-item:provider:claudeAgent:native-item:toolu_01SLjo2VDghDpBS3DRCeiX5y`.

---

You are working in a git worktree of SilkJS, our own open-source JavaScript engine written in the Silk language (a native port of QuickJS), plus a Node-compatible runtime. Layout: `modules/engine` (package `silkjs`, the engine and the `silkjs` command line whose entry is `modules/engine/src/main.silk` with helpers in `cli_*.silk`), `modules/runtime`. Read the root `README.md` first. Learn Silk syntax from the existing sources.

## Background
We are adding an optional JIT compiler to SilkJS. Its correctness will be checked by running the same JavaScript program under several execution configurations of our engine and comparing the results (differential testing). This task builds that test tooling for the engine's own test suite. It is ordinary correctness testing of our own code. You write no JIT code.

Two execution configurations exist today and more will come: the dispatch loop in `modules/engine/src/js_vm.silk` is instantiated twice (`PlainRun` and `ObservedRun`; the observed copy runs when a debugger, coverage or CPU profiler observes instructions). Later configurations will include "interpreter only", "compile every function on first call", and "make every type guard fail on a schedule". The tooling must be built so a new configuration is one more command line in a list.

## Environment facts
- Silk 0.1.0-dev.69 is installed; do NOT run `silk use` or `silk set`. Build the command-line binary with `silk build --release` in `modules/engine`; it lands under the worktree root in `build/llvm/x86_64-unknown-linux-gnu/release/silkjs` (confirm from build output).
- Other agents are compiling on this 8-CPU machine, so a release build can take tens of minutes. Run long commands with output redirected to a log file inside the worktree (not `/tmp`), so the result survives if your shell session is lost, and check the log rather than rebuilding.
- `node` 24 is at `/usr/local/bin/node`.
- Use at most 2 worker processes for test runs, and stop them before you finish.
- Existing correctness tooling to learn from: `modules/engine/scripts/check.py`, the `verify_*.py` scripts, `modules/engine/tests/`.

## Part A: differential runner
Write `modules/engine/scripts/differential.py` (Python 3 standard library only, in the style of the existing scripts):
- Input: a list of JS files or directories, and a list of named configurations, each a command line (default set below).
- For each program, run it under every configuration with a timeout and a memory limit, capture stdout, stderr, exit status and whether it timed out, and compare all configurations against the first (the reference). Report any difference.
- Normalize only what must be normalized, and document each rule in the script. Between two SilkJS configurations compare everything byte for byte. When Node is the reference, error-message wording and stack-trace text differ between engines, so compare a canonical outcome (printed values plus the error's constructor name).
- Programs whose output depends on timing, randomness, memory addresses or collector timing give false alarms. Provide a prelude (prepended to every program) that makes `Math.random` deterministic from a seed and pins `Date.now`/`new Date()`; and detect and skip programs that still vary by running the reference configuration twice.
- On a difference, save a self-contained reproducer directory (program, both outputs, both command lines) and try to shrink the program with a simple line/statement reduction that keeps the difference.
- Exit status nonzero when any difference is found; a summary line with counts.
Default configurations: SilkJS plain; SilkJS with the observed loop on for the whole run (find what turns observation on from the command line, for example coverage or CPU-profile options in `cli_options.silk`; if no existing switch does it without changing program output, add a minimal hidden debug option and say so in your report); and Node as an optional third reference that is off by default.
Run it over `modules/engine/tests/silkjs/`, `modules/engine/bench/macro/` and the benchmark files in `modules/engine/bench/v8/` (see `scripts/v8bench.py` for how those are concatenated with `base.js` and a runner). Fix false alarms in the tool, and report every real difference with its reproducer. Do not fix engine bugs you find; describe them precisely.

## Part B: test program generator
Write `modules/engine/scripts/jsgen.py`: a seeded random generator of terminating, deterministic JavaScript test programs aimed at the cases a JIT specializes on. Each program must print a checksum of everything it computed so a wrong result is visible. Cover at least: int32 arithmetic including overflow to double and `-0`; double arithmetic including NaN and infinities; bitwise and shift operators; comparisons across mixed types; objects with stable shapes, then shape changes mid-loop (add, delete, reorder properties, change prototype, define accessors); call sites that go from one callee to several to many; arrays that change element kind (integers, doubles, holes, mixed, strings), reads and writes past the length, `length` changes; typed arrays; closures capturing loop variables; `arguments`; getters, setters and proxies that modify the receiver during access; exceptions thrown inside hot loops and from callees; `try/finally`; generators and async functions; string concatenation and indexing; `switch`; recursion. Structure every program as a phase that runs a function many thousands of times with stable types, followed by a phase that changes one assumption and keeps running. All loops must have fixed bounds. Wire it into `differential.py` (`--generate N --seed S`), run at least a few thousand generated programs across the default configurations, and report results.

## Part C: make it a task
Add the differential run over the fixed corpus (not the generator) to the engine's task list so it runs as one command; look at how `silk task check` and `silk task bench` are defined and follow that pattern. Document both scripts briefly in `modules/engine/tests/README.md` (create it if absent) in the repo's plain factual tone.

## Rules
- Engine source edits are limited to command-line code needed for a debug switch. Do not touch `js_vm.silk`, `js_core_types.silk`, `js_gc.silk` or the bytecode/compiler files; another agent is editing those.
- Never report a result you did not run. Give the command and the counts. If the generator finds nothing, say so, with how many programs ran.
- Commit on a new local branch `jit/p1-differential` in small commits with plain messages, and commit as you go. Do NOT push, do NOT open a pull request.
- Do not start subagents.

## Final report (your last message)
- Branch and commits.
- How to run each tool, and the default configuration list.
- Every real difference found, each with a reproducer path and a one-line description.
- Normalization rules and skipped-program counts.
- What a future agent must do to add a new configuration.
