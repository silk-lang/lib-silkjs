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
| 2. Scorecard | Not started. `modules/benchkit` on `main` already compares engines; see next steps |
| 3. Differential harness | Runner, generator, minimizer and self-test done; not wired into `silk task` |
| 4. Engine seam | Not started; design leads only |
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

Limits: the generator covers arithmetic, comparisons, property and element reads, calls, and
prototype changes. It does not generate closures, generators, async code, exceptions thrown from
generated functions, typed arrays, or property writes inside the hot functions. It found no bug,
which says the two interpreter loops agree on this slice, not that the slice is wide.
`--debug-observed` is confirmed to change the dispatch loop (the same script runs about 3x
slower); that every path enters observed dispatch is still not established.

## Validation record

These were run once, on a 4-CPU, 15 GiB Linux x86-64 cloud container that no longer exists, with
Silk 0.1.0-dev.74+205aea3f5b2e and Clang 22.1.8. Their logs were not kept; rerun to check them.

| Command | Result |
| --- | --- |
| `silk test --manifest-path modules/jit/silk.toml --no-cache` | 28 passed, 0 failed |
| `python3 modules/jit/scripts/encodings.py --check` | fixtures current |
| `silk check --workspace` on `jit/p1-code-memory-asm` (dev.69), after `python3 modules/runtime/tools/embed.py` | 3 packages pass, 15 s warm, 43 s cold |
| `silk build --release` in `modules/engine` | 4 m 48 s, peak 7.2 GiB |
| `silk task check` in `modules/engine` | 271 script steps pass; native suite 562 passed, 2 failed |
| `python3 scripts/differential.py --count 3000 --configs plain,observed,node` | 3000 agree |
| `python3 scripts/differential.py --self-test` | pass |

The 60 s workspace-check timeout in the previous handoff was a slow host, not a hang. Without
`embed.py` the runtime member fails with `Unknown module runtime.embedded`; that file is generated
and ignored by git.

### Two native tests fail on `main` as well

`silk test src/tests.silk -o build/core-tests --optimization speed --debug false` (step 1 of
`silk task check`) reports 562 passed, 2 failed, both in `js_for_in_tests`:

- `forInAllocationFailuresReleaseInputSnapshotsAndVisitedState`: fatal trap "QuickJS invariant
  violated" at `js_array_storage_test_support:32`.
- `forInFailSafeAndFastCompletionAreNotPermanentlyLatched`: assertion "iteration yields the
  independently expected property name" at `js_for_in_tests:141`.

The same command on untouched `main` at `d1973537` gives the same two failures with the same
messages, so they predate this branch and are not caused by it. They are not fixed here.

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

## Next steps

1. Scorecard. `modules/engine/bench/README.md` documents `silk task bench-setup`, `bench-octane
   --jit`, `bench-micro --jit` and `bench-report`. Run them on an idle machine and add what the
   harness lacks: startup of an empty script, peak RSS per process, binary size, warmup. Record
   host, revision and every engine version. A worst-iteration time is not a GC pause or a p99.
   Tier seam. Document every way a function body starts executing and every back-edge, then
   prototype per-function hotness counting with an embedder-set callback slot and measure its
   interpreter-only cost with `scripts/v8bench.py --instructions` (target under 0.5 percent).
   Two cloud sessions were created for these (branches `claude/jit-scorecard` and
   `claude/jit-tier-seam`, both still equal to `cc1ed33a`) and did nothing: they could not
   install the Silk toolchain because the installer needs the GitHub release API of
   `silk-lang/silk`, which a session attached only to `lib-silkjs` cannot reach. A session doing
   this work needs both repositories attached.
2. Wire `differential.py` into `silk task`, and widen the generator (closures, property writes,
   exceptions, typed arrays).
3. Decide the hook design from the tier-seam document and its instruction-count measurements.
4. Then milestone 6: call and type feedback, an ownership-aware SSA form, and one narrow function
   compiled end to end (integer arithmetic and a loop) with deoptimization to the interpreter,
   run through the differential harness as a new configuration.

## Research

See [the memory and feedback report](memory-feedback-research.md). It is code inspection and
history, with no instrumentation measurements; its source links refer to `86c3e4db`. Its
recommendation stands as a hypothesis: start with ownership-aware SSA on the existing reference
counting; treat a nursery, a tracing collector and globally packed values as separate experiments.

The Bun AOT material cited in the earlier handoff ([Bun PR 45631](https://github.com/oven-sh/bun/pull/45631),
[WebKit PR 757](https://github.com/oven-sh/WebKit/pull/757)) has not been revalidated.
