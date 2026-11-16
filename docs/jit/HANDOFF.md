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
| 2. Scorecard | In progress in a separate session (see "Work in progress") |
| 3. Differential harness | Done for the interpreter: widened generator, per-area self-test, `silk task differential`, a step in `silk task check` |
| 4. Engine seam | In progress in a separate session (see "Work in progress") |
| 5. Machine-code foundations | x86-64 encoder and executable memory done for Linux x86-64 |
| 6. Feedback and ownership-aware SSA | Not started |
| 7. Optimizations | Not started |

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

Not rerun by the lead: `silk check --workspace` and the full `silk task check` (the worker for
the differential harness ran `python3 scripts/check.py --skip-native --skip-bench`: 271 PASS).
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
- `silk check` can leave a `silkc check` process alive after its parent exits, reparented to init
  and holding about 4.8 GiB. Look for it with `ps` and kill it before the next heavy step. Several
  of these across worktrees would explain the memory pressure that stalled the previous VM; that
  link is a hypothesis.
- A second `silk check` on changed source once replayed a stale diagnostic in 0.00 s. `silk test
  --no-cache` did not. Treat a suspiciously instant check result as stale.
- Do not benchmark while a compiler runs.

## Work in progress

Since 2026-11-16 the work is split across sessions. The lead session integrates into
`claude/sweet-ptolemy-f5t7na`, reruns each worker's key commands before merging, and is the only
one that edits this file. The worker briefs (setup, machine rules, scope) are kept in the Silk
UI project's shared files under `jit/briefs/` and repeat what this file says.

| Workstream | State |
| --- | --- |
| A. Scorecard (`docs/jit/scorecard.md`, harness additions for startup, peak RSS, binary size, warmup) | Running in its own session; nothing merged yet |
| B. Tier seam (`docs/jit/tier-seam.md`) and the per-function hotness hook with its cost measurement | Running in its own session; nothing merged yet |
| C. Differential harness widening | Merged (`dfcd50a`, `b4fbe1b`), validated above |

## Next steps

1. Merge A and B after rerunning their key commands. For B that means
   `python3 scripts/v8bench.py --instructions old new` (target under 0.5 percent),
   `python3 scripts/differential.py --count 500`, `silk task check`, and the test that fails
   when the hook stops firing.
2. Decide the hook design from the tier-seam document and its instruction-count measurements.
3. Then milestone 6: call and type feedback, an ownership-aware SSA form on the existing
   reference counting, and one narrow function compiled end to end (integer arithmetic and a
   loop) using `modules/jit`'s encoder and code memory, with deoptimization to an interpreter
   frame at a bytecode boundary, run through the differential harness as a new configuration.

Every session doing this work needs `silk-lang/silk` attached with GitHub API access as well as
`silk-lang/lib-silkjs`: the Silk installer reads the release API and gets HTTP 403 otherwise
(two earlier sessions failed on exactly this).

## Research

See [the memory and feedback report](memory-feedback-research.md). It is code inspection and
history, with no instrumentation measurements; its source links refer to `86c3e4db`. Its
recommendation stands as a hypothesis: start with ownership-aware SSA on the existing reference
counting; treat a nursery, a tracing collector and globally packed values as separate experiments.

The Bun AOT material cited in the earlier handoff ([Bun PR 45631](https://github.com/oven-sh/bun/pull/45631),
[WebKit PR 757](https://github.com/oven-sh/WebKit/pull/757)) has not been revalidated.
