# SilkJS JIT handoff

Updated 2026-11-16. Working branch: `claude/sweet-ptolemy-f5t7na`, based on `main` at `d1973537`.
It replaces `t3/jit-compiler-plan` (based on the older `86c3e4db`) as the coordination branch.

## Objective and standing constraints

Build an optional JIT that competes with V8 and JavaScriptCore on measured throughput, startup,
warmup, latency and memory. No result yet establishes JIT parity or a performance win: no
JavaScript is compiled to machine code anywhere in this repository.

- Interpreter-only SilkJS stays a first-class, easily embedded product. The engine does not import
  `modules/jit`; interpreter regressions are measured, not assumed away.
- The goal is better measured outcomes, not simplicity for its own sake. Tier count and memory
  model are decided by evidence.
- Ahead-of-time compilation must stay possible: relocatable code, serializable compiler inputs,
  runtime references through data-side tables.

## Starting from nothing

Nothing from the machine this was written on is needed or assumed: everything is in this branch
of `silk-lang/lib-silkjs`. No build output, log or toolchain carries over. On a fresh Linux x86-64
machine with at least 16 GB of RAM:

```sh
git clone --branch claude/sweet-ptolemy-f5t7na https://github.com/silk-lang/lib-silkjs
cd lib-silkjs

# Silk, at the version the workspace pins (silk.toml).
curl -fsSL https://raw.githubusercontent.com/silk-lang/silk/main/install.sh -o install-silk.sh
SILK_RELEASE='v0.1.0-dev.74+205aea3f5b2e' sh install-silk.sh
export PATH="$HOME/.silk/bin:$PATH"

# Clang 22.1.8 with llvm-mc. Silk rejects older Clang.
curl -fsSL https://raw.githubusercontent.com/silk-lang/silk/main/scripts/setup-linux-llvm.sh -o setup-llvm.sh
bash setup-llvm.sh "$HOME/llvm-22.1.8"
export SILK_CLANG="$HOME/llvm-22.1.8/bin/clang"

silk test --manifest-path modules/jit/silk.toml          # 28 tests, about 1 second
(cd modules/engine && silk build --release)              # about 5 minutes, 7.2 GiB peak
python3 modules/engine/scripts/differential.py --count 200
```

The Silk installer reads the GitHub release API of `silk-lang/silk`. An agent session therefore
needs `silk-lang/silk` reachable as well as `silk-lang/lib-silkjs`, and needs its user's
permission to attach it; a session with only `lib-silkjs` gets HTTP 403 from the installer.
`valgrind` is needed for the instruction-count benchmarks, Node for the `node` reference
configuration.

## State of each milestone

| Milestone | State |
| --- | --- |
| 1. Foundational validation | Done. Two native tests fail, on `main` too (see below) |
| 2. Scorecard | Done: [scorecard.md](scorecard.md), measured 2026-11-16, with startup, peak RSS, binary size and warmup added to the harness |
| 3. Differential harness | Done for the interpreter: widened generator, per-area self-test, `silk task differential`, a step in `silk task check` |
| 4. Engine seam | Mapped in [tier-seam.md](tier-seam.md); per-function hotness counting with an embedder slot is in the engine. Hook design beyond that is open |
| 5. Machine-code foundations | x86-64 encoder and executable memory done for Linux x86-64 |
| 6. Feedback and ownership-aware SSA | Feedback recorder ([feedback.md](feedback.md)) and SSA form with a bytecode translator ([ssa.md](ssa.md)) merged; the first compiled function with deoptimization is in progress in a separate session |
| 7. Optimizations | Not started |

## The plan as recovered (milestone definitions)

Copied unchanged on 2026-11-16 from the earlier handoff on `t3/jit-compiler-plan` (`95a03c95`),
which the first version of this file had shortened to milestone names. This is the fullest
surviving statement of the plan: the original HTML plan was lost with its machine. Where the
work done so far falls short of these definitions it is listed after them.

The initial four-tier plan and immediate tracing-GC replacement were superseded in discussion. The subsequent direction was interpreter plus one SSA compiler with quick and full optimization modes, subject to measured warmup needs. Deopt to interpreter frames at bytecode boundaries; make ownership reconstruction part of the deopt design. The user did not mandate a permanent tier count or memory model.

1. **Finish foundational validation.** Correct overstated package docs; review the two saved commits; test memory permissions/lifetimes and the observed-dispatch option. Complete a bounded workspace check and relevant engine/runtime checks, recording commands and results. Integrate only validated changes.
2. **Establish a scorecard.** Extend existing benchmark tooling for configurable SilkJS, Node, d8, and JSC commands. Record versions, host, source revision, binary provenance, repetitions, throughput, warmup, startup, per-process peak RSS, binary size, and an explicitly labeled pause proxy. Missing engines are explicit omissions. Keep benchmark runs isolated from builds. A worst-iteration ratio is not a measured GC pause or p99 latency.
3. **Finish the differential harness.** Deterministic seeded programs; plain versus observed interpreter configurations; optional external reference engines; normalized output and exit classification; timeouts, reproducible failures, minimization, and explicit unsupported-case reporting. Generate stable hot calls followed by changed types/shapes/call targets. Add future JIT/deopt configurations through the same interface.
4. **Implement the engine seam.** Define hotness and native-entry hooks with zero/verified-minimal interpreter-only cost. Cover normal calls, leaf paths, constructors, loops, exceptions, and invalidation; do not serialize process-local pointers. Prove frame and ownership contracts before compiled JavaScript entry.
5. **Finish machine-code foundations.** Typed x64 operands and labels, relocation records, ABI handling, encoding comparisons against a real assembler, executable tests, and platform-gated extension points. One constant byte string is not an assembler.
6. **Add feedback and ownership-aware SSA.** Begin with call/type feedback; specify safepoints, guards, deoptimization state, native helper effects, and roots. Keep compiler inputs serializable for background compilation/AOT. Build a narrow end-to-end compiled function before broad optimization passes.
7. **Broaden optimizations from measurements.** Inlining, unboxed arithmetic, load/check elimination, register allocation, OSR, and allocation/RC optimizations. Evaluate background compilation, persisted profiles/code, cross-module optimization, and regexp compilation with correctness and performance gates.

The historical phase durations were estimates, not delivery commitments. Define progress through tests and measured gates.

### AOT context and historical artifacts

The original HTML plan at `/tmp/silkjs-jit-plan/silkjs-jit-plan.html` no longer exists on this VM. The design above was recovered from conversation and the saved notes at `/home/user/.claude/projects/-home-user-silkjs/memory/`.

Earlier Bun research cited [Bun PR 45631](https://github.com/oven-sh/bun/pull/45631), [WebKit PR 757](https://github.com/oven-sh/WebKit/pull/757), and [Bun AOT documentation](https://bun.com/docs/compiler/aot). Those sources and historical numerical claims were **not revalidated during this recovery**. The useful design hypotheses are immutable file-backed code, runtime data-side references, generic entry fallback, and opt-in closed-world assumptions. Preserve ordinary JS semantics by default. Do not assume static TypeScript annotations are sound runtime facts.

### Where the work so far falls short of these definitions

- Milestone 2: `d8` is not a column (V8 is measured through Node 24, with and without
  `--jitless`), and there is no pause proxy of any kind in the scorecard.
- Milestone 4: only hotness counting exists. It does not cover leaf paths, loops (back edges)
  or generator resumption, and there is no native-entry hook, no frame or ownership contract
  for compiled entry yet (in progress in milestone 6's sessions).
- Ahead-of-time compilation: nothing is implemented. What exists is the rule and two places
  that follow it: the encoder emits relocation records instead of addresses, and the hotness
  counter is not serialized with bytecode. No persisted code or profile format, no
  closed-world mode, and no plan for when AOT work starts has been written.

## What is on this branch

| Commit | Content |
| --- | --- |
| `2f2e2495` | The recovered handoff and research report (cherry-picked from `95a03c95`) |
| `f9825d88` | The `modules/jit` package with W^X executable memory (cherry-picked from `82349ee1`, adapted to `main`: package `silkjs-jit`, Silk dev.74) |
| `1827a101` | The hidden `--debug-observed` switch (cherry-picked from `c1c68890`) |
| `e801def7` | Code memory hardened and tested |
| `cc1ed33a` | The x86-64 encoder, its llvm-mc fixtures and executable tests |
| `b6ee60e6` | `modules/engine/scripts/differential.py` |

### Executable memory (`modules/jit/src/code_memory.silk`)

Reserve an inaccessible range, write into whole read-write pages, publish them read-execute, free
them. Publishing returns the pages the code did not reach and fills the rest of the last page
with `int3`; freeing gives the physical memory back with `MADV_DONTNEED`. Nine tests read
`/proc/self/maps` and `mincore`: no page is writable and executable at once, drops revoke
access, a block outlives its region owner, and exhaustion, fragmentation, overflow and empty
publication fail with documented codes. Each property was also checked by breaking the
implementation and seeing the test fail.

Known limit: a block takes at least one 4 KiB page. A compiler emitting many small functions must
batch them per writer and then frees them together. Whether that or a dual mapping is better for
memory and publish cost is not measured.

### x86-64 encoder (`modules/jit/src/asm_x64.silk`)

Typed registers and memory operands; integer moves, loads and stores of 1 to 8 bytes, the eight
two-operand arithmetic operations, `imul`, unary group, shifts, `setcc`, `cmovcc`, SSE2 scalar
doubles and conversions, jumps, calls, labels. External references are relocation records
(`Absolute64`, `Relative32`) applied by `Code.link(base, addresses)`, so assembled bytes contain no
process-local pointer.

`scripts/encodings.py` generates `src/asm_x64_fixtures.silk`: 1,717 encoder calls, each compared
with the bytes llvm-mc 22.1.8 assembles. All match. `src/asm_x64_tests.silk` runs assembled code,
including a call back into Silk through a relocation.

Not there: short (8-bit) jumps, AVX, 8/16-bit arithmetic, atomics, a frame layout, a register
allocator, arm64, macOS, Windows, unwind metadata, stack maps.

### Differential harness (`modules/engine/scripts/differential.py`)

One program per seed: functions called hot with stable types, then with changed types, shapes,
call targets and prototypes; a checksum is printed per phase. Configurations are command
templates (`plain`, `observed`, `node`, or `--config NAME=TEMPLATE`), so a JIT or deopt-stress
flag joins later through the same interface. Failing programs are written with seed and results
and reduced by deleting lines. A missing reference engine is reported as skipped.

Result on this branch: seeds 1..3000 agree across plain, `--debug-observed` and Node 22.23.4.
`--self-test` finds a planted disagreement in 3 of 40 programs and reduces 60 lines to 12.

Since `dfcd50a` the generator also covers closures (captured variables read and written, closures
made in loops), property and element writes inside the hot functions (shape-changing adds,
deletes, `length` writes), exceptions (thrown late in a hot loop through intermediate frames,
local catch and rethrow, `finally` overriding the result) and typed arrays (nine element kinds,
NaN, -0, out-of-range stores, an aliasing view). `--self-test` plants one source-level miscompile
per area and requires that it is found and minimized. `silk task differential` wraps the script,
and `silk task check` runs 200 programs, plain against observed, as its fifth step.

Limits: it does not generate generators, async code, getters or setters defined in hot functions,
Proxy, named writes on typed arrays, or strict mode. It found no bug, which says the two
interpreter loops agree on this slice, not that the slice is wide. `--debug-observed` is
confirmed to change the dispatch loop (the same script runs about 3x slower); that every path
enters observed dispatch is still not established. A JIT joins as
`--config jit='{engine} --jit {file}'`; it is not a reference engine, so any disagreement with
`plain` is a mismatch.

## Validation record

Rerun on 2026-11-16 by the lead session on a fresh 4-CPU, 15 GiB Linux x86-64 cloud container
(Silk 0.1.0-dev.74+205aea3f5b2e, Clang 22.1.8, Node 22.23.4), at `b4fbe1b` unless noted. Every
row was run there; the exit status is given. Logs were not kept beyond the session.

| Command | Exit | Result |
| --- | --- | --- |
| `silk test --manifest-path modules/jit/silk.toml` | 0 | 28 passed, 0 failed |
| `python3 modules/jit/scripts/encodings.py --check` | 0 | `src/asm_x64_fixtures.silk is current` |
| `silk build --release` in `modules/engine` | 0 | 5 m 33 s |
| native suite (command below) at `42b98426` | 1 | 562 passed, 2 failed, 13 m 10 s |
| native suite at `main` `d1973537` (separate worktree) | 1 | 562 passed, 2 failed, same two tests and messages |
| `python3 scripts/differential.py --self-test` | 0 | PASS: prototypes 9 of 40, closures 21, property writes 12, exceptions 34, typed arrays 8 |
| `python3 scripts/differential.py --count 3000 --configs plain,observed,node` | 0 | agree 3000, mismatch 0, reference-only 0 |
| `silk task differential --count 20` | 0 | agree 20 |
| `silk task bench-setup`, `bench-startup --jit`, `bench-octane --jit richards deltablue splay`, `bench-warmup --jit richards` (with the scorecard harness merged) | 0 | see the cross-check table in scorecard.md |
| `silk build --release` with the hotness hook merged | 0 | 4 m 35 s |
| `python3 scripts/v8bench.py --instructions BASE HOT` | 0 | ratios above; earley-boyer 1.008x |
| `python3 scripts/differential.py --count 500 --configs plain,observed,node` on the hook binary | 0 | agree 500 |
| `silk test --file src/js_hotness_tests.silk --optimization debug` | 0 | 1 passed (exit 1 with the hook broken) |
| `silk task check` on the hook binary | 1 | native suite 563 passed, 2 failed (the count is the 562 plus the new hotness test; `check.py` does not print the failing names); all 314 other steps PASS |

Not rerun by the lead: `silk check --workspace`.
The native suite needs `modules/engine/build/` to exist: without it `silk test ... -o
build/core-tests` exits 1 with `silk: cannot create temporary directory: not found`
(`mkdir -p build`, or run the release build first). `/usr/bin/time` is not installed on these
containers. Peak memory of the largest single process was 5.3 GiB for the native suite build
and 3.1 GiB for the release build (`getrusage`, one process, not the sum of the build's
processes; the 13.9 GiB and 7.2 GiB figures elsewhere in this file came from the earlier
machine and were not reproduced as totals).

### Two native tests fail on `main` as well

`silk test src/tests.silk -o build/core-tests --optimization speed --debug false` (step 1 of
`silk task check`) reports 562 passed, 2 failed, both in `js_for_in_tests`:

- `forInAllocationFailuresReleaseInputSnapshotsAndVisitedState`: fatal trap "QuickJS invariant
  violated" at `js_array_storage_test_support:32`.
- `forInFailSafeAndFastCompletionAreNotPermanentlyLatched`: assertion "iteration yields the
  independently expected property name" at `js_for_in_tests:141`.

The same command on untouched `main` at `d1973537` gives the same two failures with the same
messages (rerun by the lead session on 2026-11-16, both revisions on one machine), so they
predate this branch and are not caused by it. They are not fixed here, by decision: the
programme moves on without them.

## Operating notes for this kind of host

- One memory-heavy command at a time. The native test suite build peaks near 13.9 GiB, the release
  build at 7.2 GiB.
- `silk task` leaves a `silkc task` process (about 2.6 GiB, parent 1) after compiling the task
  program, and `silk test` and `silk build` leave a `silkc` too. The benchmark harness refuses
  to measure while it sees one. Kill it by PID before benchmarking.
- `silk check` can leave a `silkc check` process alive after its parent exits, reparented to init
  and holding about 4.8 GiB. Look for it with `ps` and kill it before the next heavy step. Several
  of these across worktrees would explain the memory pressure that stalled the previous VM; that
  link is a hypothesis.
- A second `silk check` on changed source once replayed a stale diagnostic in 0.00 s. `silk test
  --no-cache` did not. Treat a suspiciously instant check result as stale.
- Do not benchmark while a compiler runs.

## Scorecard (measured 2026-11-16)

[scorecard.md](scorecard.md) has the host, every engine version, the commands, the tables, the
spread between rounds and the raw results. The harness (`modules/benchkit`, `silk task`) gained
`bench-startup`, `bench-warmup`, per-process peak RSS in `bench-octane`, and
`bench-report --spread`. Headline, all measured on one host: Octane geometric mean of median
rounds silkjs 6019, v8-jitless 4695, jsc-nojit 3626, qjs 3243, v8-jit 53956, jsc-jit 53180, so
the JIT engines are about 9x ahead of the interpreter. Empty-script startup: silkjs 3.4 ms, qjs
2.1 ms, jsc 8.6 ms, node 26.7 ms. Octane peak RSS geometric mean: silkjs 54 MB, qjs 18 MB.
The JIT engines' first iteration is 20x to 50x slower than their steady state, yet they pass
SilkJS in cumulative time after 2 or 3 iterations. The lead reran startup, three Octane
benchmarks and the richards warmup on a second host: engine ratios agree, absolute scores were
about 20 percent higher there (table at the end of the scorecard). No GC pause or p99 figure
exists yet.

`silk task bench-setup` failed at its `wasm` step on dev.74 until `20600651` added
`HostInput.variableNames` to `bench/wasm/src/main.silk`. The comparison harness wants Node 24
(`NODE_REFERENCE`; v24.22.3 from nodejs.org was used), the differential harness used Node 22.

## Tier seam and the hotness hook

[tier-seam.md](tier-seam.md) lists, with file:line references at `42b98426`, every way a function
body starts executing, every back edge and its interrupt poll in both dispatch loops, how
exceptions unwind, and what invalidates shape assumptions, and ends with eight open questions.

In the engine (`c56dd8d`): `FunctionBytecode.hotness` counts entries down from
`HOT_ENTRY_BUDGET` (1000). At zero, if the embedder set `RuntimeState.hotFunctions` with
`js_runtime.setHotFunctionHandler` (default none), the function is parked in
`RuntimeState.hotPending` and reported at the next interrupt poll through
`InterruptHooks.hotFunction`. The engine does not import `modules/jit`. Not counted: leaf runs,
generator and async resumption, back edges. So a function entered rarely that loops for long is
never reported; on-stack replacement is open.

Interpreter-only cost, `python3 scripts/v8bench.py --instructions` against the binary without
the hook, measured twice (by the worker and again by the lead on another host, same ratios):
richards 0.999x, deltablue 1.000x, crypto 1.000x, raytrace 0.999x, earley-boyer 1.008x, regexp
1.001x, splay 1.001x, navier-stokes 1.000x. The 0.5 percent target is met on seven of eight
and MISSED on earley-boyer (+0.8 percent). The worker measured that +0.58 of it appears in a
control build that has the new fields but counts nothing, and traced it with callgrind to an
address-keyed 4-way cache on the call path that takes more probes once heap cells move
(tier-seam.md, open question 7). The lead did not rerun the control build. Whether to accept
this, shrink the field, or fix that cache is undecided.

`src/js_hotness_tests.silk` fails when the hook stops firing: with `deliverHot` commented out in
`js_interrupts.handle` it fails with "an inline frame's function is reported once" (the lead
reran both the passing and the broken case).

## Feedback (milestone 6, part 1)

[feedback.md](feedback.md): inventory of what the interpreter already records, the design, costs
and what the benchmarks record. `modules/engine/src/js_feedback.silk` records, per bytecode site
of a function the embedder starts recording for (from the hot report): operand classes and
int32 overflow for arithmetic and comparisons, up to two call targets, up to four receiver
shapes. It records only in the observed dispatch loop (recording switches
`observeInstructions` on); the plain loop has no new code. Read API: `start`, `stop`,
`snapshot` (plain data). Hidden CLI switches `--debug-feedback`, `--debug-feedback-stats`.

Measured: with no handler, `v8bench.py --instructions` is 1.000x on all eight (worker, and
rerun by the lead against the hotness-hook binary). While recording, the worker measured a
one-time cost of 70 to 185 M instructions per run, about 82 percent of it from functions that
are not being recorded but run in the observed loop meanwhile (not rerun by the lead). Site
fractions over the seven benchmarks that report functions (worker's measurement):
arithmetic/compare int32-only 55 percent, with a double 37; calls monomorphic 94; property
sites with one shape 87. navier-stokes reports no function at all: its time is in loops of
functions entered rarely, the on-stack-replacement case.

Open: budget (20,000 observed instructions) and window are guesses; element access,
`instanceof` and branch counts are not recorded; no serializer; always-on recording was judged
too costly and not prototyped.

## SSA form (milestone 6, part 2)

[ssa.md](ssa.md): the design and the backend interface. In `modules/jit/src`: `ssa.silk` (blocks
with parameters, deoptimization exits that name the bytecode offset and the value and
ownership of every local and operand slot), `ssa_translate.silk` (bytecode to SSA for integer
arithmetic, comparisons, branches, loops, return; everything else is refused with a reason),
`ssa_verify.silk` (every owned value consumed exactly once on every path, exits included),
`ssa_ownership.silk` (removes the interpreter's redundant retain and release). The only engine
change is exporting `js_opcode_data` from `modules/engine/silk.toml`.

Run by the lead: `silk test --manifest-path modules/jit/silk.toml --no-cache` exit 0, 47 passed
(was 28). The opt-in census (`cd modules/jit && mkdir -p build && touch build/ssa-census &&
silk test --file src/ssa_census_tests.silk --optimization debug`) exit 0: of 429 finished
functions after one run of each v8 benchmark the translator accepts 28, the verifier rejects
none. First refusals, largest first (worker's count): `push_this` 190, `get_var` 80, function
scopes and scope reads 52.

## Ahead-of-time compilation: what is known

Julia's direction (2026-11-16): start AOT only if it is cheap, meaning the same compiler run at
a different time; otherwise keep it possible. The SSA side passes its check: the same function
translated in two runtime instances gives byte-identical translator input and IR
(`independentOfTheRuntimeInstance`). That holds because the subset has no atom, constant,
closure or realm operand. As it grows these need re-resolving at load time: atom numbers in
the code bytes are per runtime, constants and function constants need table indices, shape
versions are runtime ids. The machine-code side (link compiled code at another address in a
second runtime and run it, deoptimization included) is being checked with the first compiled
function. No file format or cache exists.

## Engine restructuring is allowed

Julia (2026-11-16): the engine and its bytecode compiler are unreleased; that they must keep
working without a JIT is no reason to avoid changing them, including large restructures, when
integration is better for it. Restructures the workers proposed and did not do:

- compiler-assigned feedback slot numbers per site (also names sites for deoptimization);
- choosing the dispatch loop per frame, so recording one function does not run everything in
  the observed loop;
- moving the inline field key out of the bytecode into a per-function slot vector, which makes
  the code bytes pure and serializable (to be measured against today's inline hit);
- atom operands as indices into a per-function atom list, so code bytes do not depend on the
  runtime;
- fixed-layout captured-variable slots (about 12 percent of translator refusals);
- redesigning the address-keyed call cache (tier-seam.md, open question 7).

## How the work was split

On 2026-11-16 worker sessions ran in parallel (three, then four more), each on its own machine, and a lead session
reran each one's key commands before merging into `claude/sweet-ptolemy-f5t7na`. The lead is the
only one that edits this file. The briefs are in the Silk UI project's shared files under
`jit/briefs/`, the workers' reports under `jit/reports/`; neither is needed to continue.

| Workstream | Worker branch | Merged |
| --- | --- | --- |
| A. Scorecard | `claude/project-thread-0jp1hn` (`f9ca0ee`) | yes |
| B. Tier seam and hotness hook | `claude/project-thread-br37a3` (`b9afce9`) | yes |
| C. Differential harness widening | `claude/project-thread-sisu3y` (`b4fbe1b`) | yes |
| F. Call and type feedback | `claude/project-thread-kuzo60` (`5569a15`) | yes |
| G. SSA form and translator | `claude/project-thread-38jcx9` (`1fe07af`) | yes |
| D. Call cache behind the earley-boyer cost | running | no |
| E. Compiled entry, deoptimization, first compiled function | `claude/project-thread-do7odg`, running | no |

## Next steps

1. Decide what to do about the earley-boyer miss (accept, or fix the address-keyed cache), and
   whether to count back edges or sample at the interrupt poll for loops (tier-seam.md).
2. Milestone 6: call and type feedback, an ownership-aware SSA form on the existing reference
   counting, and one narrow function compiled end to end (integer arithmetic and a loop) using
   `modules/jit`'s encoder and code memory, with deoptimization to an interpreter frame at a
   bytecode boundary. Add it to `scripts/differential.py` as a new configuration
   (`--config jit=...` or a `BUILTIN` entry) before trusting it. Open design point from the seam
   document: whether a compiled frame lives in the call-frame region like an inline frame or on
   the native stack (open question 5), and how it presents itself to `unwind`.

Every session doing this work needs `silk-lang/silk` attached with GitHub API access as well as
`silk-lang/lib-silkjs`: the Silk installer reads the release API and gets HTTP 403 otherwise
(two earlier sessions failed on exactly this). In a Claude cloud session, read-only access is
not enough; attaching it with push access is what enables the API.

## Research

See [the memory and feedback report](memory-feedback-research.md). It is code inspection and
history, with no instrumentation measurements; its source links refer to `86c3e4db`. Its
recommendation stands as a hypothesis: start with ownership-aware SSA on the existing reference
counting; treat a nursery, a tracing collector and globally packed values as separate experiments.

The Bun AOT material cited in the earlier handoff ([Bun PR 45631](https://github.com/oven-sh/bun/pull/45631),
[WebKit PR 757](https://github.com/oven-sh/WebKit/pull/757)) has not been revalidated.
