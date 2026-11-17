# SilkJS JIT scorecard: silkjs-jit against V8 and JavaScriptCore

A running series. Each section is one measurement on one host, appended when a milestone 7
workstream lands, so progress shows as a sequence. Numbers from two hosts are never compared in
one table. [`scorecard.md`](scorecard.md) is the interpreter-only scorecard this extends.

The `silkjs-jit` column is `silkjs-jit-shell --jit` (modules/jit/shell): the engine plus the JIT,
compiling functions reported hot. `silkjs` is the plain engine. Every number is MEASURED on the
host of its section unless it says otherwise. Raw files are in
[`jit-scorecard-results/`](jit-scorecard-results/), one folder per section.

## How to rerun

From `modules/engine`, with `PATH="$HOME/.silk/bin:$PATH"`, `SILK_CLANG=$HOME/llvm-22.1.8/bin/clang`,
`NODE_REFERENCE=<Node 24>/bin/node`:

```sh
silk build --release                                  # plain engine
(cd ../jit/shell && silk build --release)             # silkjs-jit-shell, lands beside it
silk task bench-setup node jsc octane quickjs         # once
E=silkjs,silkjs-jit,v8-jitless,jsc-nojit,qjs,v8-jit,jsc-jit
python3 scripts/jit_kernels.py --rounds 7 --json kernels.json       # kernel table
python3 scripts/jit_coverage.py --instructions --kernels --json coverage.json
silk task bench-octane --engines $E --out OUT         # 3 interleaved rounds, ~30 min
silk task bench-startup --engines $E --out OUT
silk task bench-warmup richards deltablue --engines $E --out OUT
silk task bench-micro --engines $E --out OUT          # ~17 min
silk task bench-report --native --out OUT             # table with silkjs-jit and jit/plain
python3 ../../docs/jit/summary_jit.py OUT/octane.json # geomeans per engine
```

What the tools measure:

- `silkjs-jit` in the harness (`modules/benchkit/src/engines.silk`): `$SILKJS_JIT`, else
  `silkjs-jit-shell` beside the silkjs executable, run with `--jit`. It is in the default column
  set; a missing shell is printed as `SKIPPED` (or aborts when named in `--engines`).
- `scripts/jit_kernels.py`: `bench/kernels/*.js`, one feature each, fixed work. One `kernel()`
  call is timed inside the process (startup excluded, compilation and warmup included). Rounds are
  processes interleaved across engines; every engine must return the same checksum. ns per unit is
  the median time divided by the kernel's inner iterations (`UNITS`).
- `scripts/jit_coverage.py`: per benchmark, the shell's own `--jit-stats` and `--jit-dump`
  counters on the score runner (hot reports, compiled, refused by first refused opcode or reason,
  compiled runs, deopts, poll exits), and with `--instructions` the share of executed machine
  instructions that ran in compiled code: fixed iterations under callgrind, counting the
  instructions callgrind attributes to object `???` (the anonymous executable mapping holding
  compiled code). No engine counter is involved, so its cost when off is zero. Floor: code-load
  shows 0.0003% with nothing compiled (other anonymous code), so values below about 0.001% are noise.
- `--jit-dump` refusals name the bytecode the translator stopped at
  (`jit: refused: opcode outside the subset: push_this`).

## 2026-11-17 baseline: integration head 14e41811

### Host and versions

- Shared cloud VM (KVM guest), Ubuntu 24.04.5 LTS, Linux 6.18.44-fc-v553 x86_64, 4 vCPUs
  `Intel(R) Xeon(R) Processor @ 2.10GHz`, 15.7 GiB RAM, no swap. Nothing else ran while measuring;
  the tools refuse to measure while a compiler runs.
- lib-silkjs branch `claude/project-thread-6ys4ab` at `0fd4841`, which is integration
  `14e41811` plus the measuring tools and the `--jit-dump` opcode name (no engine or code
  generation change). Silk `v0.1.0-dev.74+205aea3f5b2e`, Clang 22.1.8. Plain release builds
  (`silk build --release`), not PGO.
- Node v24.22.3 (V8 13.6.233.17-node.63, nodejs.org tarball, SHA-256 checked); jsc from Ubuntu
  `libjavascriptcoregtk-bin` 2.52.6-0ubuntu0.24.04.1; QuickJS `e585640f`; Octane `570ad1cc`.
- Omissions: the wasm columns were not run (not part of this series).

### Kernels

Median ns per inner iteration over 7 processes, then the ratio to v8-jit / jsc-jit (above 1 means
slower than that engine). Full min/median/max in
[`kernels.log`](jit-scorecard-results/2026-11-17-baseline/kernels.log).

| Kernel | silkjs | silkjs-jit | v8-jitless | jsc-nojit | qjs | v8-jit | jsc-jit | silkjs-jit outcome |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| sum-calls: `sum(100)` called 200k times | 7.00 (12.9/10.1) | **3.47 (6.4/5.0)** | 12.80 | 6.65 | 10.15 | 0.54 | 0.69 | compiled; 199,000 runs, 0 deopts, 1,979 polls; 76.7% of instructions in compiled code |
| sum-long: one 5M-iteration loop per call, 4 calls | 10.12 (9.2/13.2) | 10.22 (9.3/13.3) | 17.65 | 8.39 | 13.84 | 1.10 | 0.77 | never hot (4 entries; needs OSR) |
| nested: 30x30 loops, 20k calls | 10.93 (17.0/9.8) | 11.43 (17.8/10.2) | 16.48 | 9.37 | 16.20 | 0.64 | 1.12 | refused: retain of a value that is not an argument |
| calls: `add(s, i)` in a loop | 22.59 (39.8/20.2) | 23.16 (40.8/20.7) | 26.23 | 27.65 | 27.78 | 0.57 | 1.12 | refused: `get_var` (the global `add`) |
| method: `p.dot(i)` reading `this.x`, `this.y` | 32.76 (34.7/21.9) | 31.26 (33.1/20.9) | 42.82 | 40.63 | 45.61 | 0.94 | 1.49 | refused: `get_field2` |
| doubles: `s * 0.999 + i * 0.25` | 15.50 (9.3/7.8) | 16.97 (10.2/8.6) | 26.13 | 13.02 | 25.33 | 1.66 | 1.98 | refused: `push_const8` (a double constant) |
| array-sum: `a[i]` over 1000 ints | 10.41 (15.3/13.2) | 10.30 (15.1/13.1) | 18.78 | 11.66 | 16.58 | 0.68 | 0.79 | refused: `get_arg_length8` |
| typed-array: Float64Array multiply-add | 41.93 (39.3/37.3) | 44.59 (41.8/39.7) | 57.67 | 60.62 | 50.94 | 1.07 | 1.12 | refused: `get_var` |

Reading: on the one kernel it compiles the JIT halves the interpreter's time and is 6.4x behind
V8 and 5.0x behind JSC there. Every other kernel stops at its first non-integer opcode and runs at
interpreter speed, 9x to 42x behind the JITs. Where a kernel is not compiled, silkjs-jit and silkjs
differ by noise and code layout (spread up to 1.3x between processes; see the log).

### Octane 2

3 interleaved rounds, one process per benchmark, engine and round. Score, higher is better.
Geometric mean over the 17 score lines ([`summary_jit.py`](summary_jit.py) on
[`octane.json`](jit-scorecard-results/2026-11-17-baseline/octane.json)):

| Engine | best round | median round | worst round |
|---|---:|---:|---:|
| silkjs | 6091 | 5959 | 5672 |
| silkjs-jit | 6033 | 5858 | 5709 |
| v8-jitless | 4678 | 4558 | 4416 |
| jsc-nojit | 3528 | 3422 | 3352 |
| qjs | 3192 | 3112 | 2994 |
| v8-jit | 57500 | 54836 | 52105 |
| jsc-jit | 56007 | 52714 | 50126 |

silkjs-jit/silkjs, geometric mean of per-benchmark medians: 0.983. silkjs-jit is 9.4x behind
v8-jit and 9.0x behind jsc-jit on the median round. Per benchmark the ratio of medians runs from
0.913 (Box2D) to 1.031 (Gameboy); every line except Box2D has overlapping plain and jit ranges, so
apart from Box2D the JIT column is the interpreter within noise. Per-benchmark best scores with
silkjs-jit and jit/plain are in
[`report--native.log`](jit-scorecard-results/2026-11-17-baseline/report--native.log).

Box2D is slower with the JIT, and that is real: under callgrind (3 fixed iterations) the shell
executes 2,507.7M instructions without `--jit`, 2,501.3M with `--jit --jit-threshold=100000000`
(hook attached, nothing compiled) and 2,614.5M with `--jit` (+4.3%). Two tiny functions were
compiled (80 bytes of code) and ran 45,589 times, so the cost is about 2,300 instructions per
compiled run. The extra instructions are in the generic call path, not in compiled code or the
compiler: `callArguments`, `js_arguments.construct`, `apply`, `buildArgList`, `denseArguments`,
GC `drainZeroFrom` and `fromShape` grow, and `lazyArgumentsSlot` shrinks
([`box2d-jit-instruction-delta.txt`](jit-scorecard-results/2026-11-17-baseline/box2d-jit-instruction-delta.txt)).
READ in code, not yet proved: linking makes `enterFrame` refuse the inline call (the frame-cells
stub), so callers that used the lazy-arguments fast path fall back to materializing an
`arguments` object. Splay, with nothing compiled, is 1.0000x (1,373.0M either way).

### Micro, startup, memory, size, warmup

- microbench.js (72 tests, best ns of 3 rounds): silkjs-jit/silkjs geometric mean 1.010 (0.849 to
  1.239 per test, code layout and noise; nothing in microbench is compiled). Engine ns over
  silkjs-jit ns: v8-jit 0.160, jsc-jit 0.165, v8-jitless 1.379, jsc-nojit 1.666, qjs 2.081.
- Empty-script startup, 30 starts, median wall: silkjs 3.27 ms, silkjs-jit 3.02 ms, qjs 2.02,
  jsc 8.2 to 8.5, node 25.7 to 26.2. Peak RSS: silkjs 19.48 MB, silkjs-jit 21.37 MB (+1.9 MB:
  the JIT's reserved code memory and tables), jsc 22.0 to 23.5, node 41.4 to 43.7, qjs 3.9.
- Octane peak RSS per process, geometric mean of medians: silkjs 54.6 MB, silkjs-jit 55.8 MB
  (per benchmark 1.002x to 1.041x), jsc-nojit 57.0, v8-jitless 93.3, v8-jit 130.3, jsc-jit 135.1.
- Executable size stripped: silkjs 21.67 MB, silkjs-jit-shell 22.11 MB (+0.44 MB for the JIT),
  node 103.68 MB, jsc 0.35 MB shell plus 30.60 MB library, qjs 2.75 MB.
- Warmup (200 iterations in one process, 3 processes, median): richards steady 2.006 ms silkjs,
  1.942 silkjs-jit, 0.093 v8-jit, 0.075 jsc-jit; deltablue steady 3.028, 3.026, 0.122, 0.172.
  Nothing in either is compiled, so the JIT column has no warmup curve yet.

### Coverage

Score runner under `--jit --jit-dump --jit-stats`; compiled share from fixed iterations under
callgrind. `v8/` rows are the v8bench copies of the same eight benchmarks. Hot counts vary a
little between runs because hot reports are delivered at interrupt polls.

| Benchmark | hot | compiled | refused | runs | deopts | polls | compiled instr | top refusals (first refused opcode or reason, count) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| octane/richards | 16 | 0 | 16 | 0 | 0 | 0 | 0.0000% | `push_this` 16 |
| octane/deltablue | 39 | 0 | 39 | 0 | 0 | 0 | 0.0000% | `push_this` 36; `get_arg_field8` 1; `get_var` 1 |
| octane/crypto | 25 | 0 | 25 | 0 | 0 | 0 | 0.0000% | `push_this` 18; `get_var` 5; `get_arg_length8` 1 |
| octane/raytrace | 25 | 0 | 25 | 0 | 0 | 0 | 0.0000% | `push_this` 14; `get_var` 8; `lnot` 1 |
| octane/earley-boyer | 49 | 0 | 49 | 0 | 0 | 0 | 0.0000% | `get_var` 19; a function scope: invalid 8; `if_not_null8` 5 |
| octane/regexp | 2 | 0 | 2 | 0 | 0 | 0 | 0.0000% | `get_scope0` 1; `put_field` 1 |
| octane/splay | 14 | 0 | 14 | 0 | 0 | 0 | 0.0000% | `push_this` 7; `get_var` 4; `get_scope0` 2 |
| octane/navier-stokes | 3 | 0 | 3 | 0 | 0 | 0 | 0.0000% | `get_scope0` 2; `strict_eq_imm8` 1 |
| octane/pdfjs | 55 | 0 | 55 | 0 | 0 | 0 | 0.0000% | `push_this` 30; `get_scope0` 12; `get_var` 3 |
| octane/mandreel | 48 | 0 | 48 | 0 | 0 | 0 | 0.0000% | `sar_imm` 38; `get_var` 10 |
| octane/gbemu | 120 | 0 | 120 | 0 | 0 | 0 | 0.0000% | `get_arg_field8` 77; `push_this` 25; `get_field2` 16 |
| octane/code-load | 8 | 0 | 8 | 0 | 0 | 0 | 0.0003% | `get_var` 3; `fclosure8` 1; `push_atom_value` 1 |
| octane/box2d | 122 | 4 | 118 | 224734 | 0 | 0 | 0.0137% | `push_this` 98; `get_scope0` 9; `is_undefined` 6 |
| octane/zlib | 15 | 0 | 15 | 0 | 0 | 0 | 0.0000% | `or_imm` 15 |
| octane/typescript | 332 | 1 | 331 | 68325 | 0 | 0 | 0.0010% | `push_this` 266; `get_arg_field8` 29; `get_scope0` 16 |
| v8/richards | 16 | 0 | 16 | 0 | 0 | 0 | 0.0000% | `push_this` 16 |
| v8/deltablue | 39 | 0 | 39 | 0 | 0 | 0 | 0.0000% | `push_this` 36; `get_arg_field8` 1; `get_var` 1 |
| v8/crypto | 25 | 0 | 25 | 0 | 0 | 0 | 0.0000% | `push_this` 18; `get_var` 5; `get_arg_length8` 1 |
| v8/raytrace | 25 | 0 | 25 | 0 | 0 | 0 | 0.0000% | `push_this` 14; `get_var` 8; `lnot` 1 |
| v8/earley-boyer | 49 | 0 | 49 | 0 | 0 | 0 | 0.0000% | `get_var` 19; a function scope: invalid 8; `if_not_null8` 5 |
| v8/regexp | 2 | 0 | 2 | 0 | 0 | 0 | 0.0000% | `get_scope0` 1; `put_field` 1 |
| v8/splay | 14 | 0 | 14 | 0 | 0 | 0 | 0.0000% | `push_this` 7; `get_var` 4; `get_scope0` 2 |
| v8/navier-stokes | 3 | 0 | 3 | 0 | 0 | 0 | 0.0000% | `get_scope0` 2; `strict_eq_imm8` 1 |

Refusals over all rows including the kernels (hot functions refused, first refused opcode):
`push_this` 602, `get_arg_field8` 107, `get_var` 94, `get_scope0` 48, `sar_imm` 38, a function
scope: invalid 26, `get_field2` 25, `or_imm` 16 (every hot zlib function), `get_arg_length8` 11,
`put_field` 10, `if_not_null8` 10.
The counts are of functions, not of time: the shell cannot attribute interpreter time to a
function. Since at most 0.014% of any benchmark's instructions run compiled, every refused
function is the time; `push_this` (methods and constructors, J's area) blocks the most functions
on 8 of the 15 Octane benchmarks, then `get_var` (globals, which calls to other functions need:
H) and `get_arg_field8`/`get_field2` (property reads: J). Integer bit operations (`sar_imm`,
`or_imm`, `shr`) block all of mandreel's and zlib's hot functions.

## 2026-11-17 04:27 UTC: integration 8e5a87b3 (K landed: f64, register allocation, recompile)

Same host, tools and versions as the baseline section; branch `claude/project-thread-6ys4ab`
fast-forwarded to integration `8e5a87b3` (which contains the tools). Engine and shell rebuilt
from it. Raw files: [`jit-scorecard-results/2026-11-17-8e5a87b3/`](jit-scorecard-results/2026-11-17-8e5a87b3/).
Startup, RSS, size, warmup and micros were not rerun (K changes no engine or shell startup path).

### Kernels

Median ns per inner iteration over 7 processes, then the ratio to v8-jit / jsc-jit. Baseline
silkjs-jit value in brackets.

| Kernel | silkjs | silkjs-jit | v8-jit | jsc-jit | silkjs-jit outcome |
|---|---:|---:|---:|---:|---|
| sum-calls | 6.98 (14.3/9.9) | **2.37 (4.9/3.4)** [3.47] | 0.49 | 0.71 | compiled; 683 code bytes (989 before); 62.1% of instructions in compiled code |
| sum-long | 10.03 | 9.89 (9.6/13.3) [10.22] | 1.03 | 0.74 | never hot (needs OSR) |
| nested | 9.38 | **2.89 (4.8/2.5)** [11.43] | 0.60 | 1.14 | now compiled; 19,000 runs, 1,708 polls; 64.4% compiled |
| calls | 22.31 | 24.33 (37.5/27.0) [23.16] | 0.65 | 0.90 | refused: `get_var` |
| method | 30.73 | 31.32 (34.3/19.7) [31.26] | 0.91 | 1.59 | refused: `get_field2` |
| doubles | 16.41 | **5.43 (3.3/2.8)** [16.97] | 1.66 | 1.97 | now compiled (f64); 99,000 runs, 984 polls; 69.8% compiled |
| array-sum | 11.09 | 11.21 (16.6/15.6) [10.30] | 0.68 | 0.72 | refused: `get_arg_length8` |
| typed-array | 41.69 | 42.92 (42.0/44.7) [44.59] | 1.02 | 0.96 | refused: `get_var` |

Three kernels now compile, each about 3x faster than the interpreter, and they are 2.5x to 4.9x
behind the JITs. No deopts anywhere. The compiled share fell on sum-calls (76.7% to 62.1%)
because the compiled loop now executes fewer instructions; the rest is the interpreter's outer
loop and call entry. `calls` is 9% slower in the JIT column with nothing compiled (ranges
[240.2, 250.7] against [221.3, 244.9]); with no compiled code involved this is most likely code
layout, not yet checked with instruction counts.

### Octane 2

| Engine | best round | median round | worst round |
|---|---:|---:|---:|
| silkjs | 5955 | 5797 | 5605 |
| silkjs-jit | 6048 | 5853 | 5381 |
| v8-jitless | 4704 | 4555 | 4355 |
| jsc-nojit | 3507 | 3412 | 3284 |
| qjs | 3182 | 3114 | 3014 |
| v8-jit | 56750 | 54900 | 52397 |
| jsc-jit | 55311 | 52633 | 49425 |

silkjs-jit/silkjs, geometric mean of per-benchmark medians: 1.010 (baseline 0.983). This round
was noisier: per-benchmark ratios run from 0.920 to 1.177, and NavierStokes (1.177) and
SplayLatency (0.927) move although nothing in them compiles, so differences under about 10% are
noise here. Box2D is again slower with the JIT (0.920, ranges do not overlap), the cost found in
the baseline (callers of linked functions take the arguments path); it is unchanged by K.

### Coverage

Octane rows and kernels (the v8bench rows match their Octane rows; see `coverage.log`).

| Benchmark | hot | compiled | refused | runs | deopts | polls | compiled instr | top refusals |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| octane/richards | 16 | 0 | 16 | 0 | 0 | 0 | 0.0000% | `push_this` 16 |
| octane/deltablue | 39 | 0 | 39 | 0 | 0 | 0 | 0.0000% | `push_this` 36; `get_arg_field8` 1; `get_var` 1 |
| octane/crypto | 25 | 0 | 25 | 0 | 0 | 0 | 0.0000% | `push_this` 18; `get_var` 5; `get_arg_length8` 1 |
| octane/raytrace | 25 | 0 | 25 | 0 | 0 | 0 | 0.0000% | `push_this` 14; `get_var` 8; `push_atom_value` 1 |
| octane/earley-boyer | 49 | 0 | 49 | 0 | 0 | 0 | 0.0000% | `get_var` 20; a function scope: invalid 8; `if_not_null8` 5 |
| octane/regexp | 2 | 0 | 2 | 0 | 0 | 0 | 0.0000% | `get_scope0` 1; `put_field` 1 |
| octane/splay | 14 | 0 | 14 | 0 | 0 | 0 | 0.0000% | `push_this` 7; `get_var` 4; `get_scope0` 2 |
| octane/navier-stokes | 3 | 0 | 3 | 0 | 0 | 0 | 0.0000% | `get_scope0` 3 |
| octane/pdfjs | 55 | 0 | 55 | 0 | 0 | 0 | 0.0000% | `push_this` 30; `get_scope0` 12; `get_var` 3 |
| octane/mandreel | 48 | 0 | 48 | 0 | 0 | 0 | 0.0000% | `get_var` 48 |
| octane/gbemu | 120 | 0 | 120 | 0 | 0 | 0 | 0.0000% | `get_arg_field8` 74; `push_this` 25; `get_field2` 16 |
| octane/code-load | 8 | 0 | 8 | 0 | 0 | 0 | 0.0003% | `get_var` 3; `fclosure8` 1; `push_atom_value` 1 |
| octane/box2d | 122 | 4 | 118 | 208401 | 0 | 0 | 0.0213% | `push_this` 98; `get_scope0` 9; `is_undefined` 6 |
| octane/zlib | 15 | 0 | 15 | 0 | 0 | 0 | 0.0000% | `put_arg` 15 |
| octane/typescript | 332 | 1 | 331 | 68325 | 0 | 0 | 0.0016% | `push_this` 266; `get_arg_field8` 29; `get_scope0` 16 |
| kernel/sum-calls | 1 | 1 | 0 | 199000 | 0 | 1979 | 62.1470% | - |
| kernel/sum-long | 0 | 0 | 0 | 0 | 0 | 0 | 0.0000% | - |
| kernel/nested | 1 | 1 | 0 | 19000 | 0 | 1708 | 64.4036% | - |
| kernel/calls | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000% | `get_var` 1 |
| kernel/method | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000% | `get_field2` 1 |
| kernel/doubles | 1 | 1 | 0 | 99000 | 0 | 984 | 69.8342% | - |
| kernel/array-sum | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000% | `get_arg_length8` 1 |
| kernel/typed-array | 1 | 0 | 1 | 0 | 0 | 0 | 0.0000% | `get_var` 1 |

Refusals over all rows: `push_this` 602, `get_var` 134, `get_arg_field8` 107, `get_scope0` 50,
a function scope: invalid 26, `get_field2` 25, `put_arg` 17, `put_field` 11, `get_arg_length8`
11. K's integer bit operations removed the first refusal of every hot zlib and mandreel function,
which now stop one opcode later: zlib at `put_arg` (all 15), mandreel at `get_var` (all 48,
up from 10). Still at most 0.021% of any Octane benchmark's instructions run compiled (Box2D).
`push_this` (J) remains the reason that blocks the most functions; `get_var` (H) is second and
now blocks all of mandreel.
