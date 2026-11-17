# SilkJS JIT scorecard: silkjs-jit against V8 and JavaScriptCore

A running series. Each section is one measurement on one host, appended when a milestone 7
workstream lands, so progress shows as a sequence. Numbers from two hosts are never compared in
one table. [`scorecard.md`](scorecard.md) is the interpreter-only scorecard this extends.

The `silkjs-jit` column is `silkjs-jit-shell --jit` (modules/jit/shell): the engine plus the JIT,
compiling functions reported hot. `silkjs` is the plain engine. Every number is MEASURED on the
host of its section unless it says otherwise. Raw files are in
[`jit-scorecard-results/`](jit-scorecard-results/), one folder per section.

## Latest: integration 90f03c13 (2026-11-17 20:41 UTC, another host than the sections before it)

Read one column: **Slower than V8**, how many times slower silkjs-jit (`--jit`) is than V8's JIT (1x would be V8's speed; lower is better). JSC's JIT gives nearly the same numbers. The second column is what the JIT gains over our own interpreter.

| What | Slower than V8 | Gain from our JIT (vs our interpreter) |
|---|---:|---:|
| Simple loops (sum-calls, sum-long, nested, doubles) | 1.3x to 4.5x | 4.3x to 5.9x faster |
| Array loop (array-sum) | 5.9x | 3.6x faster |
| Function and method calls (calls, method) | 40.4x to 42.5x | none yet (0.8x to 1.0x) |
| Typed arrays (typed-array) | 35.0x | 1.1x faster |
| **All 8 kernels (geomean)** | **7.6x** | **2.7x faster** |
| **Octane, the real-world suite (geomean)** | **8.9x** | **none yet (1.0x)** |

Full table, every engine and benchmark. Kernel rows: ns per loop iteration, median of 7 processes, lower is better. Octane rows: score, median round, higher is better. Ratio columns: how many times faster the first engine is than the second. From `python3 docs/jit/perf_table.py [--simple] kernels.json octane.json`.

| Benchmark | silkjs (interp) | silkjs-jit | silkjs-jit --jit-calls | V8 jitless | V8 JIT | JSC jitless | JSC JIT | jit / interp | jit-calls / interp | V8 JIT / silkjs-jit | JSC JIT / silkjs-jit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kernel sum-calls (ns/iter) | 11.21 | 2.61 | 2.82 | 15.35 | 0.58 | 8.20 | 0.87 | 4.29x | 3.97x | 4.50x | 3.00x |
| kernel sum-long (ns/iter) | 11.73 | 1.98 | 2.28 | 21.89 | 1.33 | 9.73 | 0.93 | 5.92x | 5.14x | 1.49x | 2.14x |
| kernel nested (ns/iter) | 15.22 | 2.59 | 2.56 | 19.58 | 0.76 | 10.82 | 1.59 | 5.88x | 5.94x | 3.41x | 1.62x |
| kernel calls (ns/iter) | 29.08 | 28.57 | 20.51 | 35.87 | 0.71 | 34.37 | 1.07 | 1.02x | 1.42x | 40.39x | 26.60x |
| kernel method (ns/iter) | 39.42 | 49.16 | 8.88 | 53.52 | 1.16 | 47.92 | 2.38 | 0.80x | 4.44x | 42.49x | 20.61x |
| kernel doubles (ns/iter) | 18.97 | 3.31 | 3.25 | 34.76 | 2.48 | 15.01 | 2.45 | 5.74x | 5.84x | 1.34x | 1.35x |
| kernel array-sum (ns/iter) | 17.46 | 4.85 | 5.12 | 25.58 | 0.82 | 14.78 | 0.85 | 3.60x | 3.41x | 5.89x | 5.72x |
| kernel typed-array (ns/iter) | 49.16 | 42.89 | 43.61 | 73.56 | 1.23 | 74.30 | 1.25 | 1.15x | 1.13x | 34.96x | 34.37x |
| **kernels geomean (ns/iter)** | **20.97** | **7.74** | **6.20** | **30.88** | **1.02** | **19.78** | **1.31** | 2.71x | 3.38x | 7.57x | 5.92x |
| Octane Richards (score) | 1373 | 1596 | 1682 | 1274 | 35560 | 1140 | 37078 | 1.16x | 1.23x | 22.28x | 23.23x |
| Octane DeltaBlue (score) | 1818 | 1845 | 1641 | 1124 | 64115 | 969 | 37165 | 1.01x | 0.90x | 34.75x | 20.14x |
| Octane Crypto (score) | 1901 | 1910 | 1992 | 1145 | 39143 | 1420 | 46735 | 1.00x | 1.05x | 20.49x | 24.47x |
| Octane RayTrace (score) | 4456 | 4662 | 4422 | 3638 | 77033 | 2065 | 112256 | 1.05x | 0.99x | 16.52x | 24.08x |
| Octane EarleyBoyer (score) | 5717 | 5893 | 5379 | 5582 | 51651 | 2732 | 58983 | 1.03x | 0.94x | 8.76x | 10.01x |
| Octane RegExp (score) | 2347 | 1912 | 1877 | 2052 | 7969 | 537 | 7736 | 0.81x | 0.80x | 4.17x | 4.05x |
| Octane Splay (score) | 6112 | 6267 | 6120 | 5354 | 23323 | 3529 | 26819 | 1.03x | 1.00x | 3.72x | 4.28x |
| Octane SplayLatency (score) | 16771 | 17992 | 17905 | 9043 | 59029 | 13801 | 49891 | 1.07x | 1.07x | 3.28x | 2.77x |
| Octane NavierStokes (score) | 3790 | 4162 | 4058 | 1760 | 37508 | 2459 | 31367 | 1.10x | 1.07x | 9.01x | 7.54x |
| Octane PdfJS (score) | 8737 | 8269 | 8500 | 7722 | 37943 | 6045 | 32693 | 0.95x | 0.97x | 4.59x | 3.95x |
| Octane Mandreel (score) | 1339 | 1356 | 1369 | 1121 | 41013 | 840 | 52910 | 1.01x | 1.02x | 30.25x | 39.02x |
| Octane MandreelLatency (score) | 8350 | 8966 | 8172 | 6838 | 60063 | 3321 | 34145 | 1.07x | 0.98x | 6.70x | 3.81x |
| Octane Gameboy (score) | 9683 | 10809 | 10034 | 7377 | 79044 | 5886 | 92009 | 1.12x | 1.04x | 7.31x | 8.51x |
| Octane CodeLoad (score) | 31226 | 30738 | 30532 | 31020 | 30003 | 19958 | 24732 | 0.98x | 0.98x | 0.98x | 0.80x |
| Octane Box2D (score) | 6070 | 6185 | 4989 | 3951 | 92438 | 5150 | 79544 | 1.02x | 0.82x | 14.95x | 12.86x |
| Octane zlib (score) | 2859 | 2716 | 2675 | 2146 | 68404 | 1648 | 64533 | 0.95x | 0.94x | 25.19x | 23.76x |
| Octane Typescript (score) | 12621 | 12928 | 12443 | 16191 | 71034 | 11482 | 63278 | 1.02x | 0.99x | 5.49x | 4.89x |
| **Octane geomean (score)** | **4980** | **5082** | **4893** | **3893** | **45356** | **2972** | **43072** | 1.02x | 0.98x | 8.92x | 8.48x |

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

### Table

| Benchmark | silkjs (interp) | silkjs-jit | V8 jitless | V8 JIT | JSC jitless | JSC JIT | jit / interp | jit-calls / interp | V8 JIT / silkjs-jit | JSC JIT / silkjs-jit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kernel sum-calls (ns/iter) | 7.00 | 3.47 | 12.80 | 0.54 | 6.65 | 0.69 | 2.02x | - | 6.42x | 5.01x |
| kernel sum-long (ns/iter) | 10.12 | 10.22 | 17.65 | 1.10 | 8.39 | 0.77 | 0.99x | - | 9.28x | 13.30x |
| kernel nested (ns/iter) | 10.93 | 11.43 | 16.48 | 0.64 | 9.37 | 1.12 | 0.96x | - | 17.83x | 10.22x |
| kernel calls (ns/iter) | 22.59 | 23.16 | 26.23 | 0.57 | 27.65 | 1.12 | 0.98x | - | 40.83x | 20.74x |
| kernel method (ns/iter) | 32.76 | 31.26 | 42.82 | 0.94 | 40.63 | 1.49 | 1.05x | - | 33.13x | 20.94x |
| kernel doubles (ns/iter) | 15.50 | 16.97 | 26.13 | 1.66 | 13.02 | 1.98 | 0.91x | - | 10.21x | 8.56x |
| kernel array-sum (ns/iter) | 10.41 | 10.30 | 18.78 | 0.68 | 11.66 | 0.79 | 1.01x | - | 15.13x | 13.06x |
| kernel typed-array (ns/iter) | 41.93 | 44.59 | 57.67 | 1.07 | 60.62 | 1.12 | 0.94x | - | 41.79x | 39.69x |
| **kernels geomean (ns/iter)** | **15.80** | **14.79** | **24.22** | **0.84** | **16.47** | **1.07** | 1.07x | - | 17.62x | 13.80x |
| Octane Richards (score) | 1673 | 1603 | 1370 | 37628 | 1306 | 39937 | 0.96x | - | 23.47x | 24.91x |
| Octane DeltaBlue (score) | 2142 | 2162 | 1699 | 111329 | 1114 | 68333 | 1.01x | - | 51.49x | 31.61x |
| Octane Crypto (score) | 2427 | 2469 | 1505 | 49443 | 1743 | 57124 | 1.02x | - | 20.03x | 23.14x |
| Octane RayTrace (score) | 5354 | 5149 | 4427 | 96347 | 2427 | 141930 | 0.96x | - | 18.71x | 27.56x |
| Octane EarleyBoyer (score) | 6413 | 6507 | 6328 | 69441 | 2994 | 77463 | 1.01x | - | 10.67x | 11.90x |
| Octane RegExp (score) | 2664 | 2739 | 2577 | 8487 | 640 | 8637 | 1.03x | - | 3.10x | 3.15x |
| Octane Splay (score) | 7359 | 6967 | 6315 | 27348 | 4018 | 30160 | 0.95x | - | 3.93x | 4.33x |
| Octane SplayLatency (score) | 20490 | 20668 | 9463 | 66704 | 15321 | 60169 | 1.01x | - | 3.23x | 2.91x |
| Octane NavierStokes (score) | 4090 | 3924 | 1837 | 43586 | 2693 | 34394 | 0.96x | - | 11.11x | 8.77x |
| Octane PdfJS (score) | 10303 | 10255 | 8695 | 44240 | 6569 | 40099 | 1.00x | - | 4.31x | 3.91x |
| Octane Mandreel (score) | 1511 | 1439 | 1262 | 48091 | 942 | 57000 | 0.95x | - | 33.42x | 39.61x |
| Octane MandreelLatency (score) | 8950 | 9081 | 7531 | 70214 | 3729 | 33235 | 1.01x | - | 7.73x | 3.66x |
| Octane Gameboy (score) | 12976 | 13378 | 8323 | 96400 | 7302 | 128428 | 1.03x | - | 7.21x | 9.60x |
| Octane CodeLoad (score) | 38145 | 36905 | 34861 | 35287 | 22895 | 30278 | 0.97x | - | 0.96x | 0.82x |
| Octane Box2D (score) | 8029 | 7327 | 4984 | 109199 | 5998 | 104644 | 0.91x | - | 14.90x | 14.28x |
| Octane zlib (score) | 3266 | 3198 | 2482 | 85419 | 1964 | 79138 | 0.98x | - | 26.71x | 24.75x |
| Octane Typescript (score) | 16962 | 16372 | 19197 | 82688 | 13585 | 82904 | 0.97x | - | 5.05x | 5.06x |
| **Octane geomean (score)** | **5959** | **5858** | **4558** | **54836** | **3422** | **52714** | 0.98x | - | 9.36x | 9.00x |

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

### Table

| Benchmark | silkjs (interp) | silkjs-jit | V8 jitless | V8 JIT | JSC jitless | JSC JIT | jit / interp | jit-calls / interp | V8 JIT / silkjs-jit | JSC JIT / silkjs-jit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kernel sum-calls (ns/iter) | 6.98 | 2.37 | 12.60 | 0.49 | 6.60 | 0.71 | 2.95x | - | 4.85x | 3.36x |
| kernel sum-long (ns/iter) | 10.03 | 9.89 | 17.18 | 1.03 | 8.09 | 0.74 | 1.01x | - | 9.57x | 13.34x |
| kernel nested (ns/iter) | 9.38 | 2.89 | 14.96 | 0.60 | 9.32 | 1.14 | 3.25x | - | 4.85x | 2.53x |
| kernel calls (ns/iter) | 22.31 | 24.33 | 26.64 | 0.65 | 29.04 | 0.90 | 0.92x | - | 37.53x | 26.98x |
| kernel method (ns/iter) | 30.73 | 31.32 | 40.78 | 0.91 | 39.42 | 1.59 | 0.98x | - | 34.26x | 19.67x |
| kernel doubles (ns/iter) | 16.41 | 5.43 | 25.71 | 1.66 | 12.51 | 1.97 | 3.02x | - | 3.27x | 2.75x |
| kernel array-sum (ns/iter) | 11.09 | 11.21 | 19.10 | 0.68 | 11.76 | 0.72 | 0.99x | - | 16.56x | 15.56x |
| kernel typed-array (ns/iter) | 41.69 | 42.92 | 57.34 | 1.02 | 62.00 | 0.96 | 0.97x | - | 42.02x | 44.72x |
| **kernels geomean (ns/iter)** | **15.55** | **10.38** | **23.68** | **0.82** | **16.39** | **1.02** | 1.50x | - | 12.66x | 10.18x |
| Octane Richards (score) | 1756 | 1760 | 1457 | 42348 | 1430 | 44791 | 1.00x | - | 24.06x | 25.45x |
| Octane DeltaBlue (score) | 2098 | 2255 | 1696 | 105888 | 1115 | 64842 | 1.07x | - | 46.96x | 28.75x |
| Octane Crypto (score) | 2438 | 2382 | 1484 | 49046 | 1743 | 55656 | 0.98x | - | 20.59x | 23.37x |
| Octane RayTrace (score) | 5364 | 5533 | 3964 | 94275 | 2219 | 143780 | 1.03x | - | 17.04x | 25.99x |
| Octane EarleyBoyer (score) | 6572 | 6598 | 6086 | 61073 | 3000 | 75613 | 1.00x | - | 9.26x | 11.46x |
| Octane RegExp (score) | 2603 | 2698 | 2496 | 8455 | 576 | 9237 | 1.04x | - | 3.13x | 3.42x |
| Octane Splay (score) | 7140 | 6910 | 6299 | 27992 | 4115 | 30910 | 0.97x | - | 4.05x | 4.47x |
| Octane SplayLatency (score) | 19898 | 18449 | 9757 | 72666 | 15571 | 58512 | 0.93x | - | 3.94x | 3.17x |
| Octane NavierStokes (score) | 3764 | 4430 | 1993 | 42993 | 2786 | 35622 | 1.18x | - | 9.70x | 8.04x |
| Octane PdfJS (score) | 10419 | 9897 | 8821 | 45245 | 7059 | 38018 | 0.95x | - | 4.57x | 3.84x |
| Octane Mandreel (score) | 1394 | 1460 | 1234 | 44424 | 891 | 51765 | 1.05x | - | 30.43x | 35.46x |
| Octane MandreelLatency (score) | 8536 | 8595 | 7342 | 66469 | 3521 | 33015 | 1.01x | - | 7.73x | 3.84x |
| Octane Gameboy (score) | 11560 | 11510 | 8241 | 86752 | 6712 | 126184 | 1.00x | - | 7.54x | 10.96x |
| Octane CodeLoad (score) | 34659 | 35585 | 34417 | 34496 | 22963 | 29047 | 1.03x | - | 0.97x | 0.82x |
| Octane Box2D (score) | 7761 | 7142 | 5101 | 120247 | 6287 | 113206 | 0.92x | - | 16.84x | 15.85x |
| Octane zlib (score) | 3332 | 3442 | 2568 | 89053 | 1987 | 78974 | 1.03x | - | 25.87x | 22.94x |
| Octane Typescript (score) | 16665 | 16881 | 19490 | 93274 | 14193 | 81997 | 1.01x | - | 5.53x | 4.86x |
| **Octane geomean (score)** | **5797** | **5853** | **4555** | **54900** | **3412** | **52633** | 1.01x | - | 9.38x | 8.99x |

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

## 2026-11-17 05:56 UTC: integration 34c3ae88 (H landed: compiled calls, `--jit-calls`)

### Table

| Benchmark | silkjs (interp) | silkjs-jit | silkjs-jit --jit-calls | V8 jitless | V8 JIT | JSC jitless | JSC JIT | jit / interp | jit-calls / interp | V8 JIT / silkjs-jit | JSC JIT / silkjs-jit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kernel sum-calls (ns/iter) | 6.75 | 1.91 | 1.87 | 12.59 | 0.56 | 6.51 | 0.69 | 3.54x | 3.62x | 3.41x | 2.76x |
| kernel sum-long (ns/iter) | 9.88 | 9.56 | 9.78 | 17.29 | 1.06 | 7.86 | 0.73 | 1.03x | 1.01x | 9.04x | 13.06x |
| kernel nested (ns/iter) | 10.52 | 2.54 | 2.50 | 15.08 | 0.62 | 9.04 | 1.15 | 4.14x | 4.20x | 4.11x | 2.22x |
| kernel calls (ns/iter) | 23.78 | 26.21 | 25.80 | 26.20 | 0.61 | 27.95 | 0.92 | 0.91x | 0.92x | 42.97x | 28.57x |
| kernel method (ns/iter) | 29.93 | 30.24 | 73.94 | 42.25 | 0.92 | 39.69 | 1.43 | 0.99x | 0.40x | 32.83x | 21.17x |
| kernel doubles (ns/iter) | 16.68 | 5.01 | 5.10 | 25.78 | 1.72 | 13.62 | 2.05 | 3.33x | 3.27x | 2.91x | 2.45x |
| kernel array-sum (ns/iter) | 11.70 | 10.52 | 10.39 | 19.32 | 0.68 | 12.57 | 0.73 | 1.11x | 1.13x | 15.48x | 14.45x |
| kernel typed-array (ns/iter) | 42.71 | 43.30 | 43.07 | 56.06 | 1.13 | 58.92 | 0.95 | 0.99x | 0.99x | 38.39x | 45.58x |
| **kernels geomean (ns/iter)** | **15.94** | **9.78** | **10.90** | **23.76** | **0.85** | **16.38** | **1.01** | 1.63x | 1.46x | 11.51x | 9.69x |
| Octane Richards (score) | 1726 | 1728 | 1479 | 1502 | 40643 | 1388 | 43340 | 1.00x | 0.86x | 23.52x | 25.08x |
| Octane DeltaBlue (score) | 2048 | 2142 | 786 | 1759 | 97253 | 1094 | 60610 | 1.05x | 0.38x | 45.40x | 28.30x |
| Octane Crypto (score) | 2344 | 2484 | 2400 | 1494 | 47371 | 1759 | 54752 | 1.06x | 1.02x | 19.07x | 22.04x |
| Octane RayTrace (score) | 5624 | 5338 | 5002 | 4099 | 98493 | 2356 | 148590 | 0.95x | 0.89x | 18.45x | 27.84x |
| Octane EarleyBoyer (score) | 6405 | 6340 | 6251 | 6081 | 57251 | 2926 | 73250 | 0.99x | 0.98x | 9.03x | 11.55x |
| Octane RegExp (score) | 2560 | 2603 | 2528 | 2284 | 8142 | 583 | 8883 | 1.02x | 0.99x | 3.13x | 3.41x |
| Octane Splay (score) | 6919 | 6804 | 6405 | 6055 | 25709 | 4148 | 29109 | 0.98x | 0.93x | 3.78x | 4.28x |
| Octane SplayLatency (score) | 19015 | 20225 | 19125 | 9343 | 65649 | 15558 | 53959 | 1.06x | 1.01x | 3.25x | 2.67x |
| Octane NavierStokes (score) | 4299 | 4118 | 4066 | 1839 | 42739 | 2778 | 35319 | 0.96x | 0.95x | 10.38x | 8.58x |
| Octane PdfJS (score) | 9726 | 9946 | 9358 | 8804 | 42725 | 6455 | 40419 | 1.02x | 0.96x | 4.30x | 4.06x |
| Octane Mandreel (score) | 1478 | 1477 | 1522 | 1197 | 46433 | 886 | 55778 | 1.00x | 1.03x | 31.44x | 37.76x |
| Octane MandreelLatency (score) | 8595 | 8902 | 9301 | 7021 | 67368 | 3668 | 36388 | 1.04x | 1.08x | 7.57x | 4.09x |
| Octane Gameboy (score) | 12284 | 12799 | 12004 | 8549 | 96304 | 7067 | 119257 | 1.04x | 0.98x | 7.52x | 9.32x |
| Octane CodeLoad (score) | 37317 | 36937 | 35251 | 34577 | 34739 | 22462 | 29764 | 0.99x | 0.94x | 0.94x | 0.81x |
| Octane Box2D (score) | 7063 | 7836 | 7251 | 4822 | 116262 | 6093 | 100507 | 1.11x | 1.03x | 14.84x | 12.83x |
| Octane zlib (score) | 3286 | 3217 | 3170 | 2470 | 80134 | 1904 | 74038 | 0.98x | 0.96x | 24.91x | 23.01x |
| Octane Typescript (score) | 14999 | 14488 | 13929 | 18220 | 78610 | 13500 | 77700 | 0.97x | 0.93x | 5.43x | 5.36x |
| **Octane geomean (score)** | **5763** | **5829** | **5287** | **4464** | **52964** | **3385** | **51590** | 1.01x | 0.92x | 9.09x | 8.85x |

Same host and versions. Branch merges integration `34c3ae88` (`d235d8d`) and adds a
`silkjs-jit-calls` column: `silkjs-jit-shell --jit --jit-calls` (harness, `jit_kernels.py`;
`jit_coverage.py --flags=--jit-calls`). Raw files:
[`jit-scorecard-results/2026-11-17-34c3ae88/`](jit-scorecard-results/2026-11-17-34c3ae88/).
The first `bench-octane` attempt refused to measure because a leftover `silkc task` process (from
compiling the edited task) was alive; it was rerun after that process exited. Nothing else ran.

### Kernels

Median ns per inner iteration over 7 processes (ratio to v8-jit / jsc-jit).

| Kernel | silkjs | silkjs-jit | silkjs-jit-calls | v8-jit | jsc-jit | outcome |
|---|---:|---:|---:|---:|---:|---|
| sum-calls | 6.75 | **1.91 (3.4/2.8)** | 1.87 | 0.56 | 0.69 | compiled, 73.1% of instructions compiled |
| sum-long | 9.88 | 9.56 | 9.78 | 1.06 | 0.73 | never hot |
| nested | 10.52 | **2.54 (4.1/2.2)** | 2.50 | 0.62 | 1.15 | compiled, 65.3% |
| calls | 23.78 | 26.21 | 25.80 | 0.61 | 0.92 | refused (`add` is a leaf, never hot; `loop` refused) |
| method | 29.93 | 30.24 | **73.94 (80.3/51.8)** | 0.92 | 1.43 | --jit-calls compiles both functions: 19.8M compiled runs, 0 deopts, 31.2% compiled, 2.4x slower than the interpreter |
| doubles | 16.68 | **5.01 (2.9/2.4)** | 5.10 | 1.72 | 2.05 | compiled, 78.2% |
| array-sum | 11.70 | 10.52 | 10.39 | 0.68 | 0.73 | refused |
| typed-array | 42.71 | 43.30 | 43.07 | 1.13 | 0.95 | refused |

### Box2D, independently

Callgrind, 3 fixed iterations ([`box2d-instructions.log`](jit-scorecard-results/2026-11-17-34c3ae88/box2d-instructions.log)):
no flag 2,508.1M; `--jit --jit-threshold=100000000` 0.9978x; `--jit` 1.0008x (nothing compiled:
the two small functions that cost +4.3% in the baseline now need `--jit-calls`); `--jit
--jit-calls` 1.0134x (3 compiled, 48,133 runs). Splay: `--jit` 1.0001x, `--jit --jit-calls`
1.0118x (8 compiled, 56 deopts, 7 unlinked, 3 recompiled). So the baseline regression is gone in
the default `--jit` configuration (CONFIRMED by instruction count); the wall-time Octane line below
(Box2D silkjs-jit 1.109x) is noise in the other direction, since nothing compiles there.

### Octane 2

| Engine | best round | median round | worst round |
|---|---:|---:|---:|
| silkjs | 5961 | 5763 | 5568 |
| silkjs-jit | 6010 | 5829 | 5569 |
| silkjs-jit-calls | 5447 | 5287 | 5150 |
| v8-jitless | 4638 | 4464 | 4285 |
| jsc-nojit | 3479 | 3385 | 3259 |
| qjs | 3197 | 3056 | 2924 |
| v8-jit | 55923 | 52964 | 51068 |
| jsc-jit | 54695 | 51590 | 48998 |

Geometric mean of per-benchmark medians against silkjs: silkjs-jit 1.012 (noise), silkjs-jit-calls
0.917. With `--jit-calls`, DeltaBlue drops to 0.384 (778 to 819 against 2017 to 2112) and
Richards to 0.857, the two benchmarks where it compiles the most (9.1% and 1.3% of instructions
in compiled code). Like the method kernel, compiled code that calls back into the engine is
currently slower than interpreting it, so `--jit-calls` is right to stay off by default.

### Coverage

| Benchmark | --jit hot / compiled | --jit compiled instr | --jit-calls compiled | runs | deopts | unlinked | --jit-calls compiled instr | top refusals with --jit-calls |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| octane/richards | 22 / 0 | 0.0000% | 1 | 3725696 | 0 | 0 | 1.3000% | `get_var` 5; `put_field` 5; `if_not_nullish8` 3 |
| octane/deltablue | 39 / 0 | 0.0001% | 9 | 20944894 | 16 | 2 | 9.1411% | `get_var` 20; `put_field` 6; deoptimized again where it was already widened 1 |
| octane/crypto | 25 / 0 | 0.0000% | 2 | 258786 | 0 | 0 | 0.0316% | `get_var` 9; `get_loc_el8` 4; `put_field` 4 |
| octane/raytrace | 25 / 0 | 0.0000% | 4 | 179448 | 24 | 3 | 0.0920% | `get_var` 18; `put_field` 3; `push_atom_value` 1 |
| octane/earley-boyer | 49 / 0 | 0.0000% | 0 | 0 | 0 | 0 | 0.0000% | `get_var` 20; a function scope: invalid 8; `if_not_null8` 5 |
| octane/regexp | 2 / 0 | 0.0000% | 0 | 0 | 0 | 0 | 0.0000% | `get_scope0` 1; `put_field` 1 |
| octane/splay | 14 / 0 | 0.0000% | 18 | 391340 | 136 | 17 | 0.1499% | `get_var` 7; `get_scope0` 2; deoptimized again where it was already widened 2 |
| octane/navier-stokes | 3 / 0 | 0.0000% | 0 | 0 | 0 | 0 | 0.0000% | `get_scope0` 3 |
| octane/pdfjs | 55 / 2 | 0.0000% | 2 | 10820 | 0 | 0 | 0.0000% | `get_scope0` 15; `get_var` 7; `push_atom_value` 7 |
| octane/mandreel | 48 / 0 | 0.0000% | 0 | 0 | 0 | 0 | 0.0000% | `get_var` 48 |
| octane/gbemu | 120 / 0 | 0.0000% | 1 | 25504 | 0 | 0 | 0.0081% | `put_field` 61; `get_array_el2` 41; `get_array_el` 12 |
| octane/code-load | 8 / 0 | 0.0003% | 0 | 0 | 0 | 0 | 0.0003% | `get_var` 3; `fclosure8` 2; `push_atom_value` 1 |
| octane/box2d | 122 / 0 | 0.0000% | 7 | 243823 | 0 | 0 | 0.1723% | `get_scope0` 38; `is_undefined` 21; `put_field` 19 |
| octane/zlib | 15 / 0 | 0.0000% | 0 | 0 | 0 | 0 | 0.0000% | `put_arg` 15 |
| octane/typescript | 332 / 0 | 0.0000% | 37 | 5615738 | 32 | 4 | 0.9110% | `get_scope0` 105; `put_field` 66; `get_var_ref` 32 |
| kernel/sum-calls | 1 / 1 | 73.1102% | 1 | 199000 | 0 | 0 | 73.1100% | - |
| kernel/sum-long | 0 / 0 | 0.0000% | 0 | 0 | 0 | 0 | 0.0000% | - |
| kernel/nested | 1 / 1 | 65.3110% | 1 | 19000 | 0 | 0 | 65.3108% | - |
| kernel/calls | 1 / 0 | 0.0000% | 0 | 0 | 0 | 0 | 0.0000% | `get_var` 1 |
| kernel/method | 1 / 0 | 0.0000% | 2 | 19841129 | 0 | 0 | 31.1741% | - |
| kernel/doubles | 1 / 1 | 78.1734% | 1 | 99000 | 0 | 0 | 78.1731% | - |
| kernel/array-sum | 1 / 0 | 0.0000% | 0 | 0 | 0 | 0 | 0.0000% | `get_arg_length8` 1 |
| kernel/typed-array | 1 / 0 | 0.0000% | 0 | 0 | 0 | 0 | 0.0000% | `get_var` 1 |

Refusals without `--jit-calls` (all rows): `get_var` 237, `put_field` 186, `get_scope0` 171, a
call (needs `--jit-calls`) 74, `get_array_el2` 41, `get_array_el` 38, `get_var_ref` 30. With
`--jit-calls`: `get_var` 232, `put_field` 186, `get_scope0` 171, `get_array_el2` 41,
`get_array_el` 40, `get_var_ref` 35, `get_length` 26. `push_this` no longer appears
(INFERRED from the counts, not read in code: the translator now takes `this`), so methods now stop at their first property write (`put_field`) or
global read (`get_var`).

## 2026-11-17 10:37 UTC: integration 4e5e3dba (K round 2, I OSR, J objects, H native nested calls)

### Table

| Benchmark | silkjs (interp) | silkjs-jit | silkjs-jit --jit-calls | V8 jitless | V8 JIT | JSC jitless | JSC JIT | jit / interp | jit-calls / interp | V8 JIT / silkjs-jit | JSC JIT / silkjs-jit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kernel sum-calls (ns/iter) | 5.42 | 1.03 | 1.05 | 10.49 | 0.49 | 5.39 | 0.62 | 5.27x | 5.18x | 2.12x | 1.66x |
| kernel sum-long (ns/iter) | 9.86 | 2.24 | 2.52 | 14.27 | 0.90 | 6.59 | 0.54 | 4.41x | 3.91x | 2.47x | 4.13x |
| kernel nested (ns/iter) | 9.21 | 1.59 | 1.52 | 12.45 | 0.57 | 7.73 | 1.37 | 5.79x | 6.08x | 2.77x | 1.16x |
| kernel calls (ns/iter) | 20.73 | 19.95 | 18.66 | 22.77 | 0.60 | 22.74 | 0.96 | 1.04x | 1.11x | 33.43x | 20.79x |
| kernel method (ns/iter) | 27.06 | 25.63 | 26.98 | 33.08 | 0.84 | 33.50 | 1.40 | 1.06x | 1.00x | 30.53x | 18.36x |
| kernel doubles (ns/iter) | 13.98 | 2.10 | 2.32 | 21.26 | 1.70 | 10.54 | 1.71 | 6.65x | 6.02x | 1.24x | 1.23x |
| kernel array-sum (ns/iter) | 9.31 | 5.39 | 4.67 | 15.83 | 0.59 | 9.66 | 0.63 | 1.73x | 1.99x | 9.13x | 8.55x |
| kernel typed-array (ns/iter) | 33.48 | 36.86 | 35.06 | 49.43 | 0.96 | 47.40 | 0.94 | 0.91x | 0.95x | 38.20x | 39.32x |
| **kernels geomean (ns/iter)** | **13.65** | **5.45** | **5.44** | **19.77** | **0.77** | **13.35** | **0.94** | 2.50x | 2.51x | 7.09x | 5.78x |
| Octane Richards (score) | 2038 | 2095 | 1860 | 1755 | 47209 | 1643 | 53218 | 1.03x | 0.91x | 22.53x | 25.40x |
| Octane DeltaBlue (score) | 2503 | 2470 | 1017 | 2010 | 105597 | 1193 | 73497 | 0.99x | 0.41x | 42.75x | 29.76x |
| Octane Crypto (score) | 2957 | 2782 | 2802 | 1753 | 52535 | 2194 | 65852 | 0.94x | 0.95x | 18.88x | 23.67x |
| Octane RayTrace (score) | 6406 | 6480 | 6700 | 5091 | 113884 | 2809 | 140228 | 1.01x | 1.05x | 17.57x | 21.64x |
| Octane EarleyBoyer (score) | 7901 | 7948 | 7905 | 7694 | 60613 | 3612 | 87380 | 1.01x | 1.00x | 7.63x | 10.99x |
| Octane RegExp (score) | 3257 | 3476 | 3434 | 3138 | 9910 | 749 | 9738 | 1.07x | 1.05x | 2.85x | 2.80x |
| Octane Splay (score) | 7758 | 7130 | 7042 | 5916 | 28473 | 4694 | 29100 | 0.92x | 0.91x | 3.99x | 4.08x |
| Octane SplayLatency (score) | 19147 | 19994 | 18460 | 8275 | 64157 | 16454 | 52511 | 1.04x | 0.96x | 3.21x | 2.63x |
| Octane NavierStokes (score) | 4579 | 5072 | 4619 | 2201 | 55205 | 3356 | 47346 | 1.11x | 1.01x | 10.88x | 9.33x |
| Octane PdfJS (score) | 12347 | 11671 | 10597 | 10792 | 46930 | 8043 | 46159 | 0.95x | 0.86x | 4.02x | 3.96x |
| Octane Mandreel (score) | 1957 | 1464 | 1383 | 1511 | 51816 | 1159 | 64930 | 0.75x | 0.71x | 35.39x | 44.35x |
| Octane MandreelLatency (score) | 11103 | 6271 | 5595 | 9388 | 80406 | 4812 | 42976 | 0.56x | 0.50x | 12.82x | 6.85x |
| Octane Gameboy (score) | 14838 | 12284 | 11400 | 9208 | 104423 | 8339 | 136155 | 0.83x | 0.77x | 8.50x | 11.08x |
| Octane CodeLoad (score) | 34515 | 34889 | 36478 | 40287 | 42423 | 24208 | 32176 | 1.01x | 1.06x | 1.22x | 0.92x |
| Octane Box2D (score) | 9287 | 8021 | 6305 | 5394 | 134733 | 6846 | 131473 | 0.86x | 0.68x | 16.80x | 16.39x |
| Octane zlib (score) | 4196 | 3473 | 3440 | 3016 | 99749 | 2303 | 82917 | 0.83x | 0.82x | 28.72x | 23.87x |
| Octane Typescript (score) | 16994 | 17369 | 16617 | 22520 | 83392 | 16232 | 59778 | 1.02x | 0.98x | 4.80x | 3.44x |
| **Octane geomean (score)** | **6832** | **6324** | **5702** | **5242** | **60125** | **4032** | **57486** | 0.93x | 0.83x | 9.51x | 9.09x |

Same host and versions. Branch merges integration `4e5e3dba` (`20785a3b`, keeping J's versions
of `jit_coverage.py`, with `--calls` and deopt-site sums, and `jit_kernels.py`). The deopt-site
lines (`jit: deoptimized at:`) are not printed by the 4e5e3dba shell, so this section has deopt
counts but no deopt opcodes. Raw files:
[`jit-scorecard-results/2026-11-17-4e5e3dba/`](jit-scorecard-results/2026-11-17-4e5e3dba/).
This host ran about 15% faster this time (silkjs Octane 6832 against 5763), so compare columns
within this section, not absolute values across sections.

### Kernels

Median ns per inner iteration over 7 processes (ratio to v8-jit / jsc-jit).

| Kernel | silkjs | silkjs-jit | silkjs-jit-calls | v8-jit | jsc-jit | outcome (--jit) |
|---|---:|---:|---:|---:|---:|---|
| sum-calls | 5.42 | **1.03 (2.1/1.7)** | 1.05 | 0.49 | 0.62 | compiled + OSR, 67.6% compiled |
| sum-long | 9.86 | **2.24 (2.5/4.1)** | 2.52 | 0.90 | 0.54 | OSR now enters the long loop: 99.3% compiled |
| nested | 9.21 | **1.59 (2.8/1.2)** | 1.52 | 0.57 | 1.37 | 95.7% compiled |
| calls | 20.73 | 19.95 (33.4/20.8) | 18.66 (31.3/19.4) | 0.60 | 0.96 | needs --jit-calls; with it 10.1M runs, 9,988,091 direct calls, 48.7% compiled, still interpreter speed |
| method | 27.06 | 25.63 | 26.98 (32.1/19.3) | 0.84 | 1.40 | --jit-calls: compiled, 36.7% compiled, no longer 2.4x slower |
| doubles | 13.98 | **2.10 (1.2/1.2)** | 2.32 | 1.70 | 1.71 | 68.2% compiled; level with JSC, 1.2x V8 |
| array-sum | 9.31 | **5.39 (9.1/8.5)** | 4.67 | 0.59 | 0.63 | now compiled (J's element reads), 53.1% |
| typed-array | 33.48 | 36.86 (38.2/39.3) | 35.06 | 0.96 | 0.94 | compiles, then 24 deopts unlink 3 functions |

### Octane 2

| Engine | best round | median round | worst round |
|---|---:|---:|---:|
| silkjs | 7069 | 6832 | 6524 |
| silkjs-jit | 6595 | 6324 | 6012 |
| silkjs-jit-calls | 5893 | 5702 | 5295 |
| v8-jitless | 5394 | 5242 | 5017 |
| jsc-nojit | 4199 | 4032 | 3740 |
| qjs | 3733 | 3614 | 3458 |
| v8-jit | 63056 | 60125 | 55543 |
| jsc-jit | 61911 | 57486 | 54141 |

Geometric mean of per-benchmark medians against silkjs: silkjs-jit **0.926**, silkjs-jit-calls
0.835. The default JIT is now slower than the interpreter on Octane. Lines with non-overlapping
ranges: MandreelLatency 0.565, Mandreel 0.748, Gameboy 0.828, zlib 0.828, Box2D 0.864 (with
`--jit-calls`: DeltaBlue 0.406, Box2D 0.679, MandreelLatency 0.504).

The cause is compile time, MEASURED with callgrind on one fixed iteration
([`compile-cost.txt`](jit-scorecard-results/2026-11-17-4e5e3dba/compile-cost.txt)):

- zlib: 56.10G instructions without `--jit`, 83.66G with it (+49%). Engine instructions are the
  same (55.96G); the extra 27.6G are the compiler: `ssa_ownership` 14.64G, `ssa_translate` 8.58G,
  `ssa` 2.02G, `x64_backend` 0.70G. 85 OSR compilations produced 23.9 MB of code; 123 of the 125
  OSR runs deoptimized.
- mandreel: 23.21G to 35.93G (+55%), `ssa_ownership` 9.56G of the extra 12.7G; 121 OSR
  compilations, 22.5 MB of code, 158 of 160 OSR runs deoptimized.

So the ownership pass is superlinear on zlib's and mandreel's large functions, and OSR compiles
them repeatedly only to deopt almost every entry. Compiled code itself is under 0.04% of the
instructions on both.

### Coverage

`--jit` columns from `jit_coverage.py --instructions --kernels`; `--jit-calls` from the same with
`--calls`.

| Benchmark | hot / compiled | deopts / unlinked | OSR compiled / runs / deopts | compiled instr | --jit-calls: compiled, deopts / unlinked, compiled instr | top refusals (--jit) |
|---|---:|---:|---:|---:|---:|---|
| octane/richards | 26 / 0 | 0 / 0 | 4 / 32 / 32 | 0.0008% | 7, 24 / 3, 3.0308% | `if_not_nullish8` 9; `call_constructor` 8; a call (calls from compiled code need --jit-calls) 4 |
| octane/deltablue | 69 / 12 | 96 / 12 | 32 / 133 / 133 | 0.0013% | 159, 1088 / 136, 15.7770% | a call (calls from compiled code need --jit-calls) 28; `call_constructor` 15; deoptimized again where it was already widened 9 |
| octane/crypto | 57 / 11 | 64 / 8 | 65 / 166 / 165 | 0.1479% | 31, 216 / 27, 0.5996% | a call (calls from compiled code need --jit-calls) 16; deoptimized again where it was already widened 7; `call_constructor` 6 |
| octane/raytrace | 39 / 5 | 40 / 5 | 12 / 66 / 66 | 0.0009% | 19, 152 / 19, 0.0026% | `call_constructor` 24; a call (calls from compiled code need --jit-calls) 5; deoptimized again where it was already widened 2 |
| octane/earley-boyer | 69 / 2 | 16 / 2 | 30 / 96 / 96 | 0.0003% | 18, 144 / 18, 0.0005% | `instanceof` 24; a call (calls from compiled code need --jit-calls) 7; `if_not_null8` 6 |
| octane/regexp | 19 / 3 | 16 / 2 | 87 / 69 / 69 | 0.9620% | 5, 32 / 4, 0.9757% | `regexp` 12; a call (calls from compiled code need --jit-calls) 2; deoptimized again where it was already widened 1 |
| octane/splay | 65 / 5 | 24 / 3 | 52 / 389 / 389 | 0.1713% | 22, 144 / 18, 0.3227% | `call_constructor` 49; a call (calls from compiled code need --jit-calls) 6; `if_not_nullish8` 3 |
| octane/navier-stokes | 27 / 0 | 0 / 0 | 60 / 152 / 139 | 0.6791% | 3, 24 / 3, 0.6824% | `insert3` 7; `get_array_el3` 5; deoptimized again where it was already widened 4 |
| octane/pdfjs | 115 / 10 | 48 / 6 | 121 / 292 / 291 | 0.0051% | 63, 395 / 49, 0.1562% | a call (calls from compiled code need --jit-calls) 31; `array_from` 16; deoptimized again where it was already widened 12 |
| octane/mandreel | 113 / 27 | 192 / 24 | 148 / 262 / 257 | 0.0363% | 86, 607 / 75, 0.2007% | a call (calls from compiled code need --jit-calls) 33; `get_array_el2` 28; deoptimized again where it was already widened 14 |
| octane/gbemu | 207 / 62 | 295 / 24 | 152 / 577 / 449 | 1.2908% | 118, 683 / 68, 1.4290% | `get_array_el2` 60; a call (calls from compiled code need --jit-calls) 31; `insert2` 11 |
| octane/code-load | 29 / 6 | 40 / 5 | 23 / 3 / 2 | 0.0003% | 11, 56 / 7, 0.0003% | `special_object` 6; `get_var_ref` 5; `call_constructor` 4 |
| octane/box2d | 176 / 34 | 240 / 30 | 157 / 190 / 187 | 0.1577% | 76, 539 / 67, 0.1244% | a call (calls from compiled code need --jit-calls) 32; `is_undefined` 29; `call_constructor` 22 |
| octane/zlib | 37 / 0 | 0 / 0 | 104 / 157 / 156 | 0.0008% | 0, 0 / 0, 0.0008% | `put_arg` 28; deoptimized again where it was already widened 8; recompiled too often 1 |
| octane/typescript | 509 / 164 | 1256 / 156 | 131 / 258 / 242 | 0.5245% | 665, 5156 / 642, 0.6931% | a call (calls from compiled code need --jit-calls) 135; `get_var_ref` 67; `call_constructor` 47 |
| kernel/sum-calls | 4 / 1 | 0 / 0 | 3 / 1958 / 16 | 67.6125% | 2, 0 / 0, 67.5511% | a call (calls from compiled code need --jit-calls) 2; deoptimized again where it was already widened 1 |
| kernel/sum-long | 1 / 1 | 0 / 0 | 1 / 2000 / 0 | 99.3311% | 1, 0 / 0, 99.3310% | - |
| kernel/nested | 2 / 1 | 0 / 0 | 3 / 1798 / 2 | 95.6915% | 2, 0 / 0, 95.5802% | a call (calls from compiled code need --jit-calls) 1 |
| kernel/calls | 5 / 0 | 0 / 0 | 4 / 24 / 24 | 0.0001% | 2, 0 / 0, 48.6695% | a call (calls from compiled code need --jit-calls) 4; deoptimized again where it was already widened 1 |
| kernel/method | 5 / 0 | 0 / 0 | 4 / 24 / 24 | 0.0001% | 2, 0 / 0, 36.7112% | a call (calls from compiled code need --jit-calls) 2; `call_constructor` 2; deoptimized again where it was already widened 1 |
| kernel/doubles | 4 / 1 | 0 / 0 | 3 / 988 / 16 | 68.1536% | 2, 0 / 0, 67.9962% | a call (calls from compiled code need --jit-calls) 2; deoptimized again where it was already widened 1 |
| kernel/array-sum | 2 / 1 | 0 / 0 | 2 / 1997 / 3 | 53.0618% | 2, 0 / 0, 53.0462% | a call (calls from compiled code need --jit-calls) 1 |
| kernel/typed-array | 5 / 3 | 24 / 3 | 4 / 3 / 3 | 0.0002% | 4, 24 / 3, 0.0002% | recompiled too often 1; a call (calls from compiled code need --jit-calls) 1 |

Refusals with `--jit` (all rows): a call (needs `--jit-calls`) 420, `call_constructor` 304,
deoptimized again where it was already widened 125, `get_var_ref` 90, `get_array_el2` 88,
`instanceof` 55, `if_not_nullish8` 50, `put_arg` 50. With `--jit-calls`: `call_constructor` 304,
deoptimized again where it was already widened 265, `get_var_ref` 92, `get_array_el2` 77,
`instanceof` 53, recompiled too often 41. `get_var`, `put_field` and `get_scope0` (the top three
last time) are out of the top twelve. Compiled share rose most on deltablue with `--jit-calls` (15.8%), richards
(3.0%) and gbemu (1.3% default), but deopt churn is now large: typescript 1,256 deopts and 156
unlinked by default, 5,156 and 642 with `--jit-calls`.

## 2026-11-17 12:08 UTC: integration ea9965d0 (H constructors and cheaper entry, J inline field reads and transition stores)

### Table

| Benchmark | silkjs (interp) | silkjs-jit | silkjs-jit --jit-calls | V8 jitless | V8 JIT | JSC jitless | JSC JIT | jit / interp | jit-calls / interp | V8 JIT / silkjs-jit | JSC JIT / silkjs-jit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kernel sum-calls (ns/iter) | 5.23 | 1.04 | 1.03 | 10.78 | 0.46 | 5.29 | 0.60 | 5.02x | 5.07x | 2.27x | 1.75x |
| kernel sum-long (ns/iter) | 8.29 | 2.21 | 2.20 | 14.93 | 0.97 | 6.56 | 0.55 | 3.75x | 3.76x | 2.28x | 4.01x |
| kernel nested (ns/iter) | 9.24 | 1.76 | 1.76 | 12.45 | 0.58 | 7.77 | 1.11 | 5.24x | 5.24x | 3.03x | 1.59x |
| kernel calls (ns/iter) | 19.13 | 18.75 | 18.19 | 22.57 | 0.66 | 23.36 | 0.80 | 1.02x | 1.05x | 28.35x | 23.59x |
| kernel method (ns/iter) | 26.29 | 27.16 | 19.75 | 37.77 | 0.81 | 32.59 | 1.29 | 0.97x | 1.33x | 33.41x | 21.04x |
| kernel doubles (ns/iter) | 12.41 | 2.11 | 2.08 | 21.26 | 1.68 | 12.99 | 1.71 | 5.89x | 5.96x | 1.26x | 1.23x |
| kernel array-sum (ns/iter) | 9.56 | 3.06 | 3.28 | 15.64 | 0.58 | 9.77 | 0.61 | 3.12x | 2.91x | 5.26x | 5.03x |
| kernel typed-array (ns/iter) | 34.24 | 32.53 | 32.47 | 47.03 | 0.97 | 49.82 | 0.90 | 1.05x | 1.05x | 33.48x | 36.21x |
| **kernels geomean (ns/iter)** | **13.01** | **5.07** | **4.88** | **20.11** | **0.78** | **13.78** | **0.88** | 2.57x | 2.67x | 6.52x | 5.78x |
| Octane Richards (score) | 2081 | 2125 | 1936 | 1765 | 47764 | 1702 | 47499 | 1.02x | 0.93x | 22.48x | 22.35x |
| Octane DeltaBlue (score) | 2592 | 2585 | 1217 | 2039 | 111217 | 1355 | 70436 | 1.00x | 0.47x | 43.02x | 27.25x |
| Octane Crypto (score) | 2824 | 2797 | 2895 | 1781 | 53790 | 2256 | 66214 | 0.99x | 1.03x | 19.23x | 23.67x |
| Octane RayTrace (score) | 6438 | 6412 | 5794 | 4894 | 103524 | 2816 | 167682 | 1.00x | 0.90x | 16.15x | 26.15x |
| Octane EarleyBoyer (score) | 7860 | 7591 | 7150 | 7657 | 71873 | 3861 | 89768 | 0.97x | 0.91x | 9.47x | 11.83x |
| Octane RegExp (score) | 3179 | 3276 | 3441 | 3064 | 10001 | 735 | 9991 | 1.03x | 1.08x | 3.05x | 3.05x |
| Octane Splay (score) | 7147 | 7538 | 7359 | 6700 | 27299 | 4726 | 28286 | 1.05x | 1.03x | 3.62x | 3.75x |
| Octane SplayLatency (score) | 16739 | 20690 | 18322 | 9167 | 63933 | 16600 | 48011 | 1.24x | 1.09x | 3.09x | 2.32x |
| Octane NavierStokes (score) | 5163 | 4981 | 4854 | 2236 | 55539 | 3627 | 44875 | 0.96x | 0.94x | 11.15x | 9.01x |
| Octane PdfJS (score) | 12126 | 11376 | 11115 | 11198 | 46884 | 8352 | 45381 | 0.94x | 0.92x | 4.12x | 3.99x |
| Octane Mandreel (score) | 1901 | 1649 | 1471 | 1577 | 59465 | 1214 | 69104 | 0.87x | 0.77x | 36.06x | 41.91x |
| Octane MandreelLatency (score) | 11621 | 6603 | 6014 | 9737 | 87460 | 5051 | 48875 | 0.57x | 0.52x | 13.25x | 7.40x |
| Octane Gameboy (score) | 15710 | 12700 | 12319 | 10800 | 101209 | 8763 | 143155 | 0.81x | 0.78x | 7.97x | 11.27x |
| Octane CodeLoad (score) | 39184 | 41185 | 43713 | 43263 | 43638 | 26583 | 35651 | 1.05x | 1.12x | 1.06x | 0.87x |
| Octane Box2D (score) | 9208 | 8255 | 6329 | 5611 | 139079 | 7501 | 124411 | 0.90x | 0.69x | 16.85x | 15.07x |
| Octane zlib (score) | 3909 | 3713 | 3709 | 3065 | 102492 | 2395 | 89366 | 0.95x | 0.95x | 27.60x | 24.07x |
| Octane Typescript (score) | 17830 | 18119 | 15420 | 22941 | 94100 | 16353 | 72323 | 1.02x | 0.86x | 5.19x | 3.99x |
| **Octane geomean (score)** | **6848** | **6514** | **5885** | **5440** | **62027** | **4213** | **59014** | 0.95x | 0.86x | 9.52x | 9.06x |

Same host and versions. New in the tools: `jit_coverage.py` prints a compile-cost line per
benchmark (compile time from `--jit-stats`, code bytes, OSR compilations, runs and deopts, and
from callgrind the share of instructions in compiled code and in the JIT compiler's own
functions, matched by package in `silkjs-jit-shell.symbols`); [`jit_tables.py`](jit_tables.py)
turns the JSON into the tables below. Raw files:
[`jit-scorecard-results/2026-11-17-ea9965d0/`](jit-scorecard-results/2026-11-17-ea9965d0/).

### Kernels

| Kernel | silkjs | silkjs-jit | silkjs-jit-calls | v8-jit | jsc-jit |
|---|---:|---:|---:|---:|---:|
| sum-calls | 5.23 | 1.04 (2.3/1.7) | 1.03 | 0.46 | 0.60 |
| sum-long | 8.29 | 2.21 (2.3/4.0) | 2.20 | 0.97 | 0.55 |
| nested | 9.24 | 1.76 (3.0/1.6) | 1.76 | 0.58 | 1.11 |
| calls | 19.13 | 18.75 | 18.19 (27.5/22.9) | 0.66 | 0.80 |
| method | 26.29 | 27.16 | **19.75 (24.3/15.3)** | 0.81 | 1.29 |
| doubles | 12.41 | 2.11 (1.3/1.2) | 2.08 | 1.68 | 1.71 |
| array-sum | 9.56 | **3.06 (5.3/5.0)** | 3.28 | 0.58 | 0.61 |
| typed-array | 34.24 | 32.53 (33.5/36.2) | 32.47 | 0.97 | 0.90 |

Median ns per inner iteration, 7 processes (ratio to v8-jit / jsc-jit). New: array-sum 5.39 to
3.06 (inline element reads), method with `--jit-calls` now faster than the interpreter (19.75
against 26.29; it was 2.4x slower at 34c3ae88).

### Octane 2

| Engine | best round | median round | worst round |
|---|---:|---:|---:|
| silkjs | 7074 | 6848 | 6495 |
| silkjs-jit | 6717 | 6514 | 6206 |
| silkjs-jit-calls | 6143 | 5885 | 5585 |
| v8-jitless | 5603 | 5440 | 5302 |
| jsc-nojit | 4305 | 4213 | 4095 |
| qjs | 3829 | 3773 | 3645 |
| v8-jit | 65185 | 62027 | 59466 |
| jsc-jit | 62864 | 59014 | 56370 |

Against silkjs, geometric mean of per-benchmark medians: silkjs-jit 0.951 (0.926 at 4e5e3dba),
silkjs-jit-calls 0.859. Still below the interpreter, with non-overlapping ranges: MandreelLatency
0.568, Gameboy 0.808, Mandreel 0.867, Box2D 0.897, zlib 0.950. With `--jit-calls`: DeltaBlue
0.470, Box2D 0.687.

### Coverage and compile cost

`compiler instr` is the share of all executed instructions spent in the JIT compiler (callgrind,
fixed iterations); `compiled instr` the share in compiled code. Wherever the first is larger than
the second, the JIT costs more than it runs.

| Benchmark | hot / compiled / refused | deopts / unlinked | OSR compiled / runs / deopts | compile ms | code MB | compiled instr | compiler instr | top refusals |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| octane/richards | 26 / 0 / 26 | 0 / 0 | 4 / 32 / 32 | 1.7 | 0.01 | 0.001% | 0.193% | a call (calls from compiled code need --jit-calls) 11; `if_not_nullish8` 9; `is_undefined_or_null` 2 |
| octane/deltablue | 72 / 17 / 55 | 136 / 17 | 33 / 123 / 123 | 8.1 | 0.09 | 0.033% | 0.450% | a call (calls from compiled code need --jit-calls) 42; deoptimized again where it was already widened 7; `if_nullish8` 4 |
| octane/crypto | 56 / 10 / 46 | 52 / 6 | 62 / 159 / 158 | 28.5 | 0.71 | 0.185% | 2.104% | a call (calls from compiled code need --jit-calls) 20; deoptimized again where it was already widened 8; `perm3` 5 |
| octane/raytrace | 37 / 4 / 33 | 24 / 3 | 10 / 81 / 67 | 5.3 | 0.14 | 0.258% | 1.294% | a call (calls from compiled code need --jit-calls) 27; `throw` 2; `special_object` 1 |
| octane/earley-boyer | 68 / 2 / 66 | 16 / 2 | 29 / 93 / 93 | 6.1 | 0.06 | 0.000% | 0.090% | `instanceof` 25; a call (calls from compiled code need --jit-calls) 8; `if_not_null8` 6 |
| octane/regexp | 19 / 3 / 16 | 16 / 2 | 87 / 70 / 70 | 6.8 | 0.22 | 0.977% | 1.715% | `regexp` 12; a call (calls from compiled code need --jit-calls) 2; deoptimized again where it was already widened 1 |
| octane/splay | 58 / 4 / 54 | 24 / 3 | 46 / 343 / 343 | 31.5 | 0.90 | 0.171% | 0.849% | a call (calls from compiled code need --jit-calls) 48; `if_not_nullish8` 3; `throw` 2 |
| octane/navier-stokes | 27 / 2 / 25 | 0 / 0 | 60 / 152 / 139 | 30.7 | 1.39 | 0.941% | 12.538% | `insert3` 8; `get_array_el3` 5; deoptimized again where it was already widened 4 |
| octane/pdfjs | 113 / 10 / 103 | 48 / 6 | 116 / 272 / 271 | 55.6 | 1.07 | 0.005% | 5.795% | a call (calls from compiled code need --jit-calls) 34; `array_from` 16; deoptimized again where it was already widened 12 |
| octane/mandreel | 117 / 27 / 90 | 192 / 24 | 149 / 283 / 278 | 955.5 | 25.73 | 0.038% | 34.015% | a call (calls from compiled code need --jit-calls) 37; `get_array_el2` 29; deoptimized again where it was already widened 17 |
| octane/gbemu | 207 / 62 / 145 | 295 / 24 | 152 / 577 / 449 | 133.6 | 4.00 | 1.491% | 13.217% | `get_array_el2` 60; a call (calls from compiled code need --jit-calls) 31; `insert2` 11 |
| octane/code-load | 28 / 6 / 22 | 40 / 5 | 21 / 3 / 2 | 5.7 | 0.08 | 0.000% | 0.000% | `special_object` 8; a call (calls from compiled code need --jit-calls) 4; `for_in_start` 4 |
| octane/box2d | 165 / 30 / 135 | 198 / 24 | 132 / 178 / 173 | 76.7 | 3.78 | 0.205% | 23.731% | a call (calls from compiled code need --jit-calls) 54; `is_undefined` 28; `special_object` 16 |
| octane/zlib | 37 / 0 / 37 | 0 / 0 | 104 / 157 / 156 | 3240.7 | 33.78 | 0.001% | 32.176% | `put_arg` 28; deoptimized again where it was already widened 8; recompiled too often 1 |
| octane/typescript | 521 / 185 / 336 | 1397 / 172 | 131 / 244 / 222 | 214.7 | 5.91 | 0.839% | 12.567% | a call (calls from compiled code need --jit-calls) 217; `is_undefined_or_null` 29; `if_not_nullish8` 24 |
| kernel/sum-calls | 4 / 1 / 3 | 0 / 0 | 3 / 1958 / 16 | 0.9 | 0.00 | 67.410% | 0.215% | a call (calls from compiled code need --jit-calls) 2; deoptimized again where it was already widened 1 |
| kernel/sum-long | 1 / 1 / 0 | 0 / 0 | 1 / 2000 / 0 | 0.4 | 0.00 | 99.331% | 0.079% | - |
| kernel/nested | 2 / 1 / 1 | 0 / 0 | 3 / 1798 / 2 | 0.9 | 0.01 | 95.665% | 0.493% | a call (calls from compiled code need --jit-calls) 1 |
| kernel/calls | 5 / 0 / 5 | 0 / 0 | 4 / 24 / 24 | 0.5 | 0.00 | 0.000% | 0.015% | a call (calls from compiled code need --jit-calls) 4; deoptimized again where it was already widened 1 |
| kernel/method | 5 / 0 / 5 | 0 / 0 | 4 / 24 / 24 | 0.7 | 0.00 | 0.000% | 0.013% | a call (calls from compiled code need --jit-calls) 4; deoptimized again where it was already widened 1 |
| kernel/doubles | 4 / 1 / 3 | 0 / 0 | 3 / 988 / 16 | 0.6 | 0.00 | 67.947% | 0.497% | a call (calls from compiled code need --jit-calls) 2; deoptimized again where it was already widened 1 |
| kernel/array-sum | 2 / 1 / 1 | 0 / 0 | 2 / 1997 / 3 | 0.4 | 0.01 | 98.683% | 0.054% | a call (calls from compiled code need --jit-calls) 1 |
| kernel/typed-array | 5 / 3 / 2 | 24 / 3 | 4 / 3 / 3 | 1.4 | 0.03 | 0.000% | 0.089% | recompiled too often 1; a call (calls from compiled code need --jit-calls) 1 |

With `--jit-calls`:

| Benchmark | hot / compiled / refused | deopts / unlinked | compile ms | code MB | compiled instr | compiler instr | top refusals |
|---|---:|---:|---:|---:|---:|---:|---|
| octane/richards | 36 / 19 / 17 | 96 / 12 | 4.1 | 0.09 | 4.266% | 0.967% | `if_not_nullish8` 9; deoptimized again where it was already widened 4; `is_undefined_or_null` 2 |
| octane/deltablue | 213 / 186 / 27 | 1296 / 162 | 38.5 | 1.16 | 25.952% | 6.079% | deoptimized again where it was already widened 16; `if_nullish8` 5; a body too short to gain from compiling 3 |
| octane/crypto | 76 / 40 / 36 | 280 / 34 | 56.5 | 1.60 | 0.753% | 4.492% | deoptimized again where it was already widened 15; `perm3` 5; `step_arg8` 4 |
| octane/raytrace | 93 / 67 / 26 | 528 / 66 | 79.3 | 3.19 | 0.216% | 23.361% | deoptimized again where it was already widened 14; recompiled too often 7; `throw` 2 |
| octane/earley-boyer | 76 / 18 / 58 | 130 / 16 | 8.1 | 0.14 | 0.081% | 0.332% | `instanceof` 25; deoptimized again where it was already widened 11; `if_null8` 5 |
| octane/regexp | 18 / 5 / 13 | 32 / 4 | 7.3 | 0.24 | 0.974% | 1.948% | `regexp` 11; deoptimized again where it was already widened 1; recompiled too often 1 |
| octane/splay | 302 / 289 / 13 | 2280 / 285 | 274.9 | 11.64 | 0.397% | 12.259% | deoptimized again where it was already widened 5; `throw` 3; `if_not_nullish8` 3 |
| octane/navier-stokes | 27 / 5 / 22 | 24 / 3 | 38.8 | 1.59 | 0.945% | 12.087% | `insert3` 8; `get_array_el3` 5; deoptimized again where it was already widened 4 |
| octane/pdfjs | 146 / 72 / 74 | 459 / 57 | 51.9 | 1.68 | 0.177% | 8.060% | `array_from` 15; deoptimized again where it was already widened 15; `typeof_is_undefined` 7 |
| octane/mandreel | 151 / 88 / 63 | 607 / 75 | 1148.9 | 32.80 | 0.217% | 31.927% | `get_array_el2` 28; deoptimized again where it was already widened 18; recompiled too often 12 |
| octane/gbemu | 224 / 118 / 106 | 683 / 68 | 215.2 | 4.70 | 1.641% | 31.030% | `get_array_el2` 49; deoptimized again where it was already widened 12; `insert2` 11 |
| octane/code-load | 33 / 14 / 19 | 88 / 11 | 6.6 | 0.11 | 0.000% | 0.000% | `special_object` 7; deoptimized again where it was already widened 3; `fclosure8` 2 |
| octane/box2d | 216 / 119 / 97 | 858 / 106 | 351.9 | 11.52 | 0.153% | 63.992% | `is_undefined` 25; `special_object` 15; deoptimized again where it was already widened 15 |
| octane/zlib | 37 / 0 / 37 | 0 / 0 | 3573.7 | 33.78 | 0.001% | 32.198% | `put_arg` 28; deoptimized again where it was already widened 8; recompiled too often 1 |
| octane/typescript | 1268 / 1034 / 234 | 7892 / 979 | 1092.7 | 31.63 | 1.453% | 34.220% | deoptimized again where it was already widened 123; `is_undefined_or_null` 29; `if_not_nullish8` 24 |
| kernel/sum-calls | 2 / 2 / 0 | 0 / 0 | 0.5 | 0.00 | 67.348% | 0.279% | - |
| kernel/sum-long | 1 / 1 / 0 | 0 / 0 | 0.4 | 0.00 | 99.331% | 0.079% | - |
| kernel/nested | 2 / 2 / 0 | 0 / 0 | 0.9 | 0.01 | 95.554% | 0.566% | - |
| kernel/calls | 2 / 2 / 0 | 0 / 0 | 0.4 | 0.00 | 52.183% | 11.175% | - |
| kernel/method | 2 / 2 / 0 | 0 / 0 | 0.4 | 0.00 | 66.701% | 3.674% | - |
| kernel/doubles | 2 / 2 / 0 | 0 / 0 | 0.7 | 0.01 | 67.784% | 0.668% | - |
| kernel/array-sum | 2 / 2 / 0 | 0 / 0 | 0.6 | 0.01 | 98.644% | 0.079% | - |
| kernel/typed-array | 5 / 4 / 1 | 24 / 3 | 1.4 | 0.04 | 0.000% | 0.098% | recompiled too often 1 |

The compiler outweighs the compiled code on every Octane benchmark. The worst are mandreel (34.0%
of instructions compiling, 27.0 MB of code, 955 ms), zlib (32.2%, 35.4 MB, 3.2 s, with nothing
but OSR entries compiled: 156 of 157 OSR runs deopt), box2d (23.7%), gbemu (13.2%), typescript
(12.6%) and navier-stokes (12.5%). OSR runs deopt on almost every entry everywhere (2,576 of
2,767 over the 15 Octane rows).

Refusals (`--jit`): a call (needs `--jit-calls`) 723, deoptimized again where it was already
widened 118, `get_array_el2` 89, `instanceof` 57, `if_not_nullish8` 54, `put_arg` 53. Deopt sites
of recompiled functions, by opcode: `put_array_el` 116, `call_method` 80, `call2` 39, `add` 37,
`put_field` 29, `mul` 26.

## 2026-11-17 13:18 UTC: integration da86b81c (H machine-code leaf calls, J stores to a second shape and array appends)

### Table

| Benchmark | silkjs (interp) | silkjs-jit | silkjs-jit --jit-calls | V8 jitless | V8 JIT | JSC jitless | JSC JIT | jit / interp | jit-calls / interp | V8 JIT / silkjs-jit | JSC JIT / silkjs-jit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kernel sum-calls (ns/iter) | 5.74 | 1.04 | 1.05 | 10.78 | 0.45 | 5.28 | 0.59 | 5.51x | 5.48x | 2.32x | 1.76x |
| kernel sum-long (ns/iter) | 7.97 | 2.23 | 2.20 | 14.46 | 0.90 | 6.69 | 0.54 | 3.57x | 3.62x | 2.48x | 4.17x |
| kernel nested (ns/iter) | 8.36 | 1.75 | 1.75 | 12.67 | 0.58 | 7.75 | 1.35 | 4.78x | 4.78x | 3.04x | 1.29x |
| kernel calls (ns/iter) | 19.22 | 18.65 | 13.15 | 21.22 | 0.59 | 22.38 | 0.79 | 1.03x | 1.46x | 31.82x | 23.71x |
| kernel method (ns/iter) | 25.53 | 25.83 | 16.94 | 32.77 | 0.95 | 33.34 | 1.27 | 0.99x | 1.51x | 27.05x | 20.29x |
| kernel doubles (ns/iter) | 12.55 | 2.12 | 2.12 | 20.80 | 1.60 | 10.15 | 1.70 | 5.92x | 5.93x | 1.33x | 1.25x |
| kernel array-sum (ns/iter) | 8.35 | 3.09 | 3.13 | 15.48 | 0.61 | 9.86 | 0.68 | 2.70x | 2.67x | 5.10x | 4.55x |
| kernel typed-array (ns/iter) | 34.88 | 33.47 | 33.28 | 47.15 | 1.02 | 48.97 | 0.94 | 1.04x | 1.05x | 32.83x | 35.46x |
| **kernels geomean (ns/iter)** | **12.72** | **5.06** | **4.59** | **19.49** | **0.77** | **13.34** | **0.91** | 2.51x | 2.77x | 6.54x | 5.56x |
| Octane Richards (score) | 2204 | 2150 | 1989 | 1857 | 47432 | 1730 | 54026 | 0.98x | 0.90x | 22.06x | 25.13x |
| Octane DeltaBlue (score) | 2375 | 2470 | 1324 | 2129 | 110563 | 1367 | 67579 | 1.04x | 0.56x | 44.76x | 27.36x |
| Octane Crypto (score) | 2979 | 2973 | 2838 | 1820 | 52862 | 2179 | 67075 | 1.00x | 0.95x | 17.78x | 22.56x |
| Octane RayTrace (score) | 6521 | 6454 | 6882 | 5197 | 96347 | 2684 | 168495 | 0.99x | 1.06x | 14.93x | 26.11x |
| Octane EarleyBoyer (score) | 8049 | 7885 | 7407 | 7580 | 69977 | 3865 | 91343 | 0.98x | 0.92x | 8.87x | 11.58x |
| Octane RegExp (score) | 3341 | 3351 | 3270 | 3114 | 10856 | 766 | 10494 | 1.00x | 0.98x | 3.24x | 3.13x |
| Octane Splay (score) | 7872 | 7196 | 7579 | 6152 | 25922 | 4531 | 31586 | 0.91x | 0.96x | 3.60x | 4.39x |
| Octane SplayLatency (score) | 18055 | 20482 | 19160 | 8771 | 66704 | 15888 | 51592 | 1.13x | 1.06x | 3.26x | 2.52x |
| Octane NavierStokes (score) | 4711 | 5041 | 4858 | 2205 | 55650 | 3492 | 47292 | 1.07x | 1.03x | 11.04x | 9.38x |
| Octane PdfJS (score) | 11638 | 11716 | 11188 | 11005 | 48310 | 8540 | 42517 | 1.01x | 0.96x | 4.12x | 3.63x |
| Octane Mandreel (score) | 1948 | 1669 | 1519 | 1588 | 56438 | 1218 | 73472 | 0.86x | 0.78x | 33.82x | 44.02x |
| Octane MandreelLatency (score) | 12129 | 6963 | 6185 | 9680 | 87460 | 5182 | 52476 | 0.57x | 0.51x | 12.56x | 7.54x |
| Octane Gameboy (score) | 15094 | 13680 | 12700 | 10453 | 110081 | 8662 | 140831 | 0.91x | 0.84x | 8.05x | 10.29x |
| Octane CodeLoad (score) | 37902 | 44537 | 39678 | 41270 | 41461 | 24971 | 34080 | 1.18x | 1.05x | 0.93x | 0.77x |
| Octane Box2D (score) | 8967 | 8131 | 6339 | 5549 | 144512 | 7306 | 129584 | 0.91x | 0.71x | 17.77x | 15.94x |
| Octane zlib (score) | 3948 | 3779 | 3785 | 3096 | 102837 | 2370 | 89313 | 0.96x | 0.96x | 27.21x | 23.63x |
| Octane Typescript (score) | 17870 | 17256 | 15589 | 23374 | 87094 | 16295 | 81787 | 0.97x | 0.87x | 5.05x | 4.74x |
| **Octane geomean (score)** | **6900** | **6611** | **6010** | **5428** | **61738** | **4163** | **61045** | 0.96x | 0.87x | 9.34x | 9.23x |

Same host, versions and tools (plus J's "refused after deoptimizing at" table in
`jit_coverage.py`, empty in this run). Raw files:
[`jit-scorecard-results/2026-11-17-da86b81c/`](jit-scorecard-results/2026-11-17-da86b81c/).

### Kernels

| Kernel | silkjs | silkjs-jit | silkjs-jit-calls | v8-jit | jsc-jit |
|---|---:|---:|---:|---:|---:|
| sum-calls | 5.74 | 1.04 (2.3/1.8) | 1.05 | 0.45 | 0.59 |
| sum-long | 7.97 | 2.23 (2.5/4.2) | 2.20 | 0.90 | 0.54 |
| nested | 8.36 | 1.75 (3.0/1.3) | 1.75 | 0.58 | 1.35 |
| calls | 19.22 | 18.65 | **13.15 (22.4/16.7)** | 0.59 | 0.79 |
| method | 25.53 | 25.83 | **16.94 (17.7/13.3)** | 0.95 | 1.27 |
| doubles | 12.55 | 2.12 (1.3/1.2) | 2.12 | 1.60 | 1.70 |
| array-sum | 8.35 | 3.09 (5.1/4.5) | 3.13 | 0.61 | 0.68 |
| typed-array | 34.88 | 33.47 (32.8/35.5) | 33.28 | 1.02 | 0.94 |

With `--jit-calls`, calls and method are now clearly faster than the interpreter (13.15 against
19.22, 16.94 against 25.53) but still 17x to 22x behind V8. Without `--jit-calls` nothing changed
from ea9965d0 beyond noise.

### Octane 2

| Engine | best round | median round | worst round |
|---|---:|---:|---:|
| silkjs | 7141 | 6900 | 6678 |
| silkjs-jit | 6819 | 6611 | 6159 |
| silkjs-jit-calls | 6183 | 6010 | 5731 |
| v8-jitless | 5595 | 5428 | 5245 |
| jsc-nojit | 4246 | 4163 | 3957 |
| qjs | 3862 | 3761 | 3640 |
| v8-jit | 64587 | 61738 | 58822 |
| jsc-jit | 62917 | 61045 | 57393 |

Against silkjs: silkjs-jit 0.958 (0.951 at ea9965d0), silkjs-jit-calls 0.871 (0.859). Clearly
below with non-overlapping ranges: MandreelLatency 0.574, Mandreel 0.857, Gameboy 0.906, Box2D
0.907, Splay 0.914. With `--jit-calls`: DeltaBlue 0.557 (0.470 before), Box2D 0.707, Richards
0.902. The compile-cost picture is unchanged, so the default JIT stays below the interpreter until
the OSR backoff (I) and compile budget (K) land.

### Coverage and compile cost

| Benchmark | hot / compiled / refused | deopts / unlinked | OSR compiled / runs / deopts | compile ms | code MB | compiled instr | compiler instr | top refusals |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| octane/richards | 26 / 0 / 26 | 0 / 0 | 4 / 32 / 32 | 1.3 | 0.01 | 0.001% | 0.193% | a call (calls from compiled code need --jit-calls) 11; `if_not_nullish8` 9; `is_undefined_or_null` 2 |
| octane/deltablue | 72 / 17 / 55 | 136 / 17 | 33 / 125 / 125 | 6.2 | 0.09 | 0.033% | 0.455% | a call (calls from compiled code need --jit-calls) 42; deoptimized again where it was already widened 7; `if_nullish8` 4 |
| octane/crypto | 58 / 10 / 48 | 56 / 7 | 66 / 164 / 162 | 24.7 | 0.76 | 0.185% | 2.079% | a call (calls from compiled code need --jit-calls) 22; deoptimized again where it was already widened 8; `perm3` 5 |
| octane/raytrace | 37 / 4 / 33 | 24 / 3 | 10 / 83 / 69 | 5.5 | 0.14 | 0.258% | 1.298% | a call (calls from compiled code need --jit-calls) 27; `throw` 2; `special_object` 1 |
| octane/earley-boyer | 66 / 1 / 65 | 0 / 0 | 29 / 166 / 99 | 5.3 | 0.06 | 0.000% | 0.091% | `instanceof` 25; a call (calls from compiled code need --jit-calls) 9; `if_not_null8` 6 |
| octane/regexp | 20 / 3 / 17 | 16 / 2 | 93 / 70 / 70 | 7.3 | 0.23 | 0.977% | 1.716% | `regexp` 13; a call (calls from compiled code need --jit-calls) 2; deoptimized again where it was already widened 1 |
| octane/splay | 62 / 5 / 57 | 24 / 3 | 49 / 361 / 361 | 28.9 | 0.97 | 0.171% | 0.849% | a call (calls from compiled code need --jit-calls) 51; `if_not_nullish8` 3; `throw` 2 |
| octane/navier-stokes | 27 / 2 / 25 | 0 / 0 | 60 / 152 / 139 | 29.8 | 1.39 | 0.941% | 12.531% | `insert3` 8; `get_array_el3` 5; deoptimized again where it was already widened 4 |
| octane/pdfjs | 115 / 10 / 105 | 48 / 6 | 118 / 280 / 279 | 32.4 | 1.08 | 0.005% | 5.793% | a call (calls from compiled code need --jit-calls) 34; `array_from` 17; deoptimized again where it was already widened 11 |
| octane/mandreel | 117 / 27 / 90 | 192 / 24 | 149 / 283 / 278 | 898.9 | 25.73 | 0.038% | 34.016% | a call (calls from compiled code need --jit-calls) 37; `get_array_el2` 29; deoptimized again where it was already widened 17 |
| octane/gbemu | 210 / 65 / 145 | 212 / 25 | 153 / 652 / 460 | 117.9 | 3.81 | 2.046% | 13.456% | `get_array_el2` 62; a call (calls from compiled code need --jit-calls) 30; `insert2` 11 |
| octane/code-load | 27 / 6 / 21 | 40 / 5 | 21 / 3 / 2 | 5.7 | 0.08 | 0.000% | 0.000% | a call (calls from compiled code need --jit-calls) 5; `for_in_start` 5; `special_object` 5 |
| octane/box2d | 162 / 29 / 133 | 171 / 21 | 128 / 171 / 167 | 76.2 | 3.74 | 0.205% | 23.734% | a call (calls from compiled code need --jit-calls) 54; `is_undefined` 27; `special_object` 16 |
| octane/zlib | 37 / 0 / 37 | 0 / 0 | 104 / 157 / 156 | 3227.8 | 33.78 | 0.001% | 32.177% | `put_arg` 28; deoptimized again where it was already widened 8; recompiled too often 1 |
| octane/typescript | 519 / 184 / 335 | 1388 / 172 | 129 / 246 / 229 | 219.0 | 5.89 | 0.839% | 12.578% | a call (calls from compiled code need --jit-calls) 216; `is_undefined_or_null` 29; `if_not_nullish8` 24 |
| kernel/sum-calls | 4 / 1 / 3 | 0 / 0 | 3 / 1958 / 16 | 0.4 | 0.00 | 67.410% | 0.215% | a call (calls from compiled code need --jit-calls) 2; deoptimized again where it was already widened 1 |
| kernel/sum-long | 1 / 1 / 0 | 0 / 0 | 1 / 2000 / 0 | 0.5 | 0.00 | 99.331% | 0.079% | - |
| kernel/nested | 2 / 1 / 1 | 0 / 0 | 3 / 1798 / 2 | 0.8 | 0.01 | 95.665% | 0.493% | a call (calls from compiled code need --jit-calls) 1 |
| kernel/calls | 5 / 0 / 5 | 0 / 0 | 4 / 24 / 24 | 0.5 | 0.00 | 0.000% | 0.015% | a call (calls from compiled code need --jit-calls) 4; deoptimized again where it was already widened 1 |
| kernel/method | 5 / 0 / 5 | 0 / 0 | 4 / 24 / 24 | 0.6 | 0.00 | 0.000% | 0.013% | a call (calls from compiled code need --jit-calls) 4; deoptimized again where it was already widened 1 |
| kernel/doubles | 4 / 1 / 3 | 0 / 0 | 3 / 988 / 16 | 0.5 | 0.00 | 67.946% | 0.497% | a call (calls from compiled code need --jit-calls) 2; deoptimized again where it was already widened 1 |
| kernel/array-sum | 2 / 1 / 1 | 0 / 0 | 2 / 1997 / 3 | 0.4 | 0.01 | 98.683% | 0.054% | a call (calls from compiled code need --jit-calls) 1 |
| kernel/typed-array | 5 / 3 / 2 | 24 / 3 | 4 / 3 / 3 | 1.6 | 0.03 | 0.000% | 0.089% | recompiled too often 1; a call (calls from compiled code need --jit-calls) 1 |

With `--jit-calls`:

| Benchmark | hot / compiled / refused | deopts / unlinked | compile ms | code MB | compiled instr | compiler instr | top refusals |
|---|---:|---:|---:|---:|---:|---:|---|
| octane/richards | 36 / 19 / 17 | 96 / 12 | 4.9 | 0.10 | 4.859% | 0.849% | `if_not_nullish8` 9; deoptimized again where it was already widened 4; `is_undefined_or_null` 2 |
| octane/deltablue | 151 / 128 / 23 | 803 / 100 | 37.8 | 0.96 | 31.577% | 5.489% | deoptimized again where it was already widened 13; `if_nullish8` 4; a body too short to gain from compiling 3 |
| octane/crypto | 72 / 37 / 35 | 264 / 33 | 49.6 | 1.41 | 0.752% | 4.880% | deoptimized again where it was already widened 13; `perm3` 7; `step_arg8` 4 |
| octane/raytrace | 94 / 68 / 26 | 536 / 67 | 77.2 | 3.38 | 0.216% | 23.543% | deoptimized again where it was already widened 14; recompiled too often 7; `throw` 2 |
| octane/earley-boyer | 74 / 17 / 57 | 114 / 14 | 8.9 | 0.15 | 0.081% | 0.347% | `instanceof` 24; deoptimized again where it was already widened 10; `if_null8` 5 |
| octane/regexp | 18 / 5 / 13 | 32 / 4 | 7.3 | 0.24 | 0.974% | 1.951% | `regexp` 11; deoptimized again where it was already widened 1; recompiled too often 1 |
| octane/splay | 302 / 289 / 13 | 2280 / 285 | 270.4 | 11.76 | 0.422% | 12.307% | deoptimized again where it was already widened 5; `throw` 3; `if_not_nullish8` 3 |
| octane/navier-stokes | 27 / 5 / 22 | 24 / 3 | 39.7 | 1.59 | 0.945% | 12.080% | `insert3` 8; `get_array_el3` 5; deoptimized again where it was already widened 4 |
| octane/pdfjs | 146 / 69 / 77 | 434 / 54 | 56.0 | 1.76 | 0.181% | 8.087% | `array_from` 17; deoptimized again where it was already widened 14; `typeof_is_undefined` 7 |
| octane/mandreel | 151 / 88 / 63 | 607 / 75 | 1239.6 | 32.89 | 0.222% | 31.933% | `get_array_el2` 28; deoptimized again where it was already widened 18; recompiled too often 12 |
| octane/gbemu | 217 / 113 / 104 | 534 / 63 | 185.0 | 4.46 | 2.074% | 31.280% | `get_array_el2` 49; deoptimized again where it was already widened 12; `insert2` 11 |
| octane/code-load | 33 / 13 / 20 | 80 / 10 | 6.1 | 0.12 | 0.000% | 0.000% | `special_object` 8; deoptimized again where it was already widened 3; `for_in_start` 3 |
| octane/box2d | 213 / 116 / 97 | 813 / 101 | 371.9 | 11.64 | 0.156% | 64.015% | `is_undefined` 25; `special_object` 15; deoptimized again where it was already widened 15 |
| octane/zlib | 37 / 0 / 37 | 0 / 0 | 3256.4 | 33.78 | 0.001% | 32.198% | `put_arg` 28; deoptimized again where it was already widened 8; recompiled too often 1 |
| octane/typescript | 1316 / 1085 / 231 | 8280 / 1030 | 1045.5 | 31.92 | 1.396% | 35.163% | deoptimized again where it was already widened 119; `is_undefined_or_null` 29; `if_not_nullish8` 24 |
| kernel/sum-calls | 2 / 2 / 0 | 0 / 0 | 0.5 | 0.01 | 67.345% | 0.282% | - |
| kernel/sum-long | 1 / 1 / 0 | 0 / 0 | 0.3 | 0.00 | 99.331% | 0.079% | - |
| kernel/nested | 2 / 2 / 0 | 0 / 0 | 0.9 | 0.01 | 95.551% | 0.568% | - |
| kernel/calls | 2 / 2 / 0 | 0 / 0 | 0.4 | 0.00 | 87.633% | 8.364% | - |
| kernel/method | 2 / 2 / 0 | 0 / 0 | 0.6 | 0.01 | 96.769% | 0.029% | - |
| kernel/doubles | 2 / 2 / 0 | 0 / 0 | 0.6 | 0.01 | 67.773% | 0.681% | - |
| kernel/array-sum | 2 / 2 / 0 | 0 / 0 | 0.5 | 0.01 | 98.643% | 0.080% | - |
| kernel/typed-array | 5 / 4 / 1 | 24 / 3 | 1.5 | 0.04 | 0.000% | 0.099% | recompiled too often 1 |

Refusals (`--jit`): a call (needs `--jit-calls`) 729, deoptimized again where it was already
widened 115, `get_array_el2` 91, `instanceof` 56, `if_not_nullish8` 53, `put_arg` 53, `array_from`
40. Deopt sites of recompiled functions: `put_array_el` 114, `call_method` 76, `call2` 43, `add`
37, `mul` 26, `put_field` 21.

## 2026-11-17 20:41 UTC: integration 90f03c13 (P exceptions, I OSR calls, O1 method inlining, J equality, O2 exit tables and backoff)

**Another host.** The container restarted at 19:05 UTC, and every engine runs at a different speed
here (silkjs interpreter about 1.65x slower on the kernels geomean than in the da86b81c section, V8 about
1.3x slower, Octane geomeans about 0.72x for every engine). Compare the ratios inside this section
with each other, not its absolute numbers with earlier sections. Engines: silkjs, silkjs-jit,
silkjs-jit-calls, v8-jitless, v8-jit, jsc-nojit, jsc-jit (qjs left out of Octane this time).

### Table

Short form (`perf_table.py --simple`):

| What | Slower than V8 | Gain from our JIT (vs our interpreter) |
|---|---:|---:|
| Simple loops (sum-calls, sum-long, nested, doubles) | 1.3x to 4.5x | 4.3x to 5.9x faster |
| Array loop (array-sum) | 5.9x | 3.6x faster |
| Function and method calls (calls, method) | 40.4x to 42.5x | none yet (0.8x to 1.0x) |
| Typed arrays (typed-array) | 35.0x | 1.1x faster |
| **All 8 kernels (geomean)** | **7.6x** | **2.7x faster** |
| **Octane, the real-world suite (geomean)** | **8.9x** | **none yet (1.0x)** |

Full:

| Benchmark | silkjs (interp) | silkjs-jit | silkjs-jit --jit-calls | V8 jitless | V8 JIT | JSC jitless | JSC JIT | jit / interp | jit-calls / interp | V8 JIT / silkjs-jit | JSC JIT / silkjs-jit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kernel sum-calls (ns/iter) | 11.21 | 2.61 | 2.82 | 15.35 | 0.58 | 8.20 | 0.87 | 4.29x | 3.97x | 4.50x | 3.00x |
| kernel sum-long (ns/iter) | 11.73 | 1.98 | 2.28 | 21.89 | 1.33 | 9.73 | 0.93 | 5.92x | 5.14x | 1.49x | 2.14x |
| kernel nested (ns/iter) | 15.22 | 2.59 | 2.56 | 19.58 | 0.76 | 10.82 | 1.59 | 5.88x | 5.94x | 3.41x | 1.62x |
| kernel calls (ns/iter) | 29.08 | 28.57 | 20.51 | 35.87 | 0.71 | 34.37 | 1.07 | 1.02x | 1.42x | 40.39x | 26.60x |
| kernel method (ns/iter) | 39.42 | 49.16 | 8.88 | 53.52 | 1.16 | 47.92 | 2.38 | 0.80x | 4.44x | 42.49x | 20.61x |
| kernel doubles (ns/iter) | 18.97 | 3.31 | 3.25 | 34.76 | 2.48 | 15.01 | 2.45 | 5.74x | 5.84x | 1.34x | 1.35x |
| kernel array-sum (ns/iter) | 17.46 | 4.85 | 5.12 | 25.58 | 0.82 | 14.78 | 0.85 | 3.60x | 3.41x | 5.89x | 5.72x |
| kernel typed-array (ns/iter) | 49.16 | 42.89 | 43.61 | 73.56 | 1.23 | 74.30 | 1.25 | 1.15x | 1.13x | 34.96x | 34.37x |
| **kernels geomean (ns/iter)** | **20.97** | **7.74** | **6.20** | **30.88** | **1.02** | **19.78** | **1.31** | 2.71x | 3.38x | 7.57x | 5.92x |
| Octane Richards (score) | 1373 | 1596 | 1682 | 1274 | 35560 | 1140 | 37078 | 1.16x | 1.23x | 22.28x | 23.23x |
| Octane DeltaBlue (score) | 1818 | 1845 | 1641 | 1124 | 64115 | 969 | 37165 | 1.01x | 0.90x | 34.75x | 20.14x |
| Octane Crypto (score) | 1901 | 1910 | 1992 | 1145 | 39143 | 1420 | 46735 | 1.00x | 1.05x | 20.49x | 24.47x |
| Octane RayTrace (score) | 4456 | 4662 | 4422 | 3638 | 77033 | 2065 | 112256 | 1.05x | 0.99x | 16.52x | 24.08x |
| Octane EarleyBoyer (score) | 5717 | 5893 | 5379 | 5582 | 51651 | 2732 | 58983 | 1.03x | 0.94x | 8.76x | 10.01x |
| Octane RegExp (score) | 2347 | 1912 | 1877 | 2052 | 7969 | 537 | 7736 | 0.81x | 0.80x | 4.17x | 4.05x |
| Octane Splay (score) | 6112 | 6267 | 6120 | 5354 | 23323 | 3529 | 26819 | 1.03x | 1.00x | 3.72x | 4.28x |
| Octane SplayLatency (score) | 16771 | 17992 | 17905 | 9043 | 59029 | 13801 | 49891 | 1.07x | 1.07x | 3.28x | 2.77x |
| Octane NavierStokes (score) | 3790 | 4162 | 4058 | 1760 | 37508 | 2459 | 31367 | 1.10x | 1.07x | 9.01x | 7.54x |
| Octane PdfJS (score) | 8737 | 8269 | 8500 | 7722 | 37943 | 6045 | 32693 | 0.95x | 0.97x | 4.59x | 3.95x |
| Octane Mandreel (score) | 1339 | 1356 | 1369 | 1121 | 41013 | 840 | 52910 | 1.01x | 1.02x | 30.25x | 39.02x |
| Octane MandreelLatency (score) | 8350 | 8966 | 8172 | 6838 | 60063 | 3321 | 34145 | 1.07x | 0.98x | 6.70x | 3.81x |
| Octane Gameboy (score) | 9683 | 10809 | 10034 | 7377 | 79044 | 5886 | 92009 | 1.12x | 1.04x | 7.31x | 8.51x |
| Octane CodeLoad (score) | 31226 | 30738 | 30532 | 31020 | 30003 | 19958 | 24732 | 0.98x | 0.98x | 0.98x | 0.80x |
| Octane Box2D (score) | 6070 | 6185 | 4989 | 3951 | 92438 | 5150 | 79544 | 1.02x | 0.82x | 14.95x | 12.86x |
| Octane zlib (score) | 2859 | 2716 | 2675 | 2146 | 68404 | 1648 | 64533 | 0.95x | 0.94x | 25.19x | 23.76x |
| Octane Typescript (score) | 12621 | 12928 | 12443 | 16191 | 71034 | 11482 | 63278 | 1.02x | 0.99x | 5.49x | 4.89x |
| **Octane geomean (score)** | **4980** | **5082** | **4893** | **3893** | **45356** | **2972** | **43072** | 1.02x | 0.98x | 8.92x | 8.48x |

### Output check and instructions per plain

New columns. **output**: the benchmark's score runner under the JIT shell against the plain run of
the same shell: same exit status, no `ERROR` line, same stdout with scores masked. **31 of 31 pass
with `--jit` and 31 of 31 with `--jit --jit-calls`** (15 Octane, 8 v8bench copies, 8 kernels).
This catches a crash or a wrong result that Octane's own checks see; it does not prove every value
right. **instr / plain**: callgrind instructions of the fixed iterations, JIT shell against the
same shell with no flag (MEASURED, one run each, deterministic to about 0.1%).

| Benchmark | output | instr / plain | hot / compiled / refused | deopts / unlinked | OSR compiled / runs / deopts | compile ms | code MB | compiled instr | compiler instr | top refusals |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| octane/richards | pass | 1.010 | 17 / 2 / 15 | 8 / 1 | 0 / 0 / 0 | 1.8 | 0.01 | 1.113% | 0.208% | a call (calls from compiled code need --jit-calls) 15 |
| octane/deltablue | pass | 1.005 | 42 / 2 / 40 | 0 / 0 | 2 / 10 / 10 | 3.3 | 0.01 | 0.076% | 0.225% | a call (calls from compiled code need --jit-calls) 40 |
| octane/crypto | pass | 1.004 | 37 / 7 / 30 | 32 / 4 | 16 / 436 / 38 | 16.6 | 0.09 | 0.169% | 0.302% | a call (calls from compiled code need --jit-calls) 20; deoptimized again where it was already widened 3; `step_arg8` 2 |
| octane/raytrace | pass | 1.021 | 30 / 4 / 26 | 24 / 3 | 1 / 0 / 0 | 5.2 | 0.02 | 0.175% | 0.765% | a call (calls from compiled code need --jit-calls) 23; `special_object` 1; `set_arg` 1 |
| octane/earley-boyer | pass | 1.012 | 50 / 6 / 44 | 0 / 0 | 2 / 65 / 8 | 3.5 | 0.01 | 0.371% | 0.271% | a call (calls from compiled code need --jit-calls) 23; `fclosure8` 6; `get_scope0_el` 4 |
| octane/regexp | pass | 0.985 | 11 / 2 / 9 | 16 / 2 | 0 / 0 / 0 | 1.7 | 0.01 | 0.001% | 0.100% | `regexp` 7; `array_from` 1; a call (calls from compiled code need --jit-calls) 1 |
| octane/splay | pass | 1.002 | 18 / 4 / 14 | 24 / 3 | 1 / 1 / 1 | 2.9 | 0.02 | 0.000% | 0.130% | a call (calls from compiled code need --jit-calls) 13; `object` 1 |
| octane/navier-stokes | pass | 1.000 | 19 / 4 / 15 | 8 / 1 | 27 / 940 / 77 | 20.2 | 0.24 | 6.962% | 4.616% | a call (calls from compiled code need --jit-calls) 12; recompiled too often 2; `get_scope0_el` 1 |
| octane/pdfjs | pass | 1.007 | 93 / 18 / 75 | 64 / 8 | 23 / 505 / 76 | 22.1 | 0.10 | 1.164% | 2.646% | a call (calls from compiled code need --jit-calls) 36; `array_from` 15; `get_scope0_el` 4 |
| octane/mandreel | pass | 0.991 | 78 / 18 / 60 | 80 / 10 | 33 / 2707 / 74 | 74.1 | 0.83 | 6.296% | 7.356% | a call (calls from compiled code need --jit-calls) 51; a boolean operand of a bitwise operator: and_imm 3; `put_arg` 2 |
| octane/gbemu | pass | 0.960 | 154 / 55 / 99 | 32 / 4 | 28 / 714 / 80 | 40.6 | 0.47 | 7.697% | 6.788% | a call (calls from compiled code need --jit-calls) 78; `array_from` 6; `put_arg` 6 |
| octane/code-load | pass | 1.000 | 17 / 3 / 14 | 24 / 3 | 2 / 2 / 0 | 2.2 | 0.01 | 0.000% | 0.000% | a call (calls from compiled code need --jit-calls) 5; `special_object` 5; `fclosure8` 2 |
| octane/box2d | pass | 1.082 | 137 / 26 / 111 | 136 / 17 | 21 / 27 / 23 | 38.0 | 0.53 | 0.217% | 5.560% | a call (calls from compiled code need --jit-calls) 57; `put_arg` 29; `special_object` 15 |
| octane/zlib | pass | 0.985 | 26 / 0 / 26 | 0 / 0 | 29 / 351 / 56 | 127.9 | 1.08 | 1.192% | 1.153% | `put_arg` 21; deoptimized again where it was already widened 2; `fclosure8` 1 |
| octane/typescript | pass | 1.016 | 367 / 50 / 317 | 288 / 36 | 7 / 24 / 23 | 47.2 | 0.22 | 0.665% | 0.827% | a call (calls from compiled code need --jit-calls) 252; `array_from` 15; `put_arg` 14 |
| kernel/sum-calls | pass | 0.168 | 2 / 1 / 1 | 0 / 0 | 1 / 1973 / 0 | 0.6 | 0.00 | 66.475% | 0.230% | a call (calls from compiled code need --jit-calls) 1 |
| kernel/sum-long | pass | 0.091 | 1 / 1 / 0 | 0 / 0 | 1 / 1998 / 0 | 0.7 | 0.00 | 97.664% | 0.282% | - |
| kernel/nested | pass | 0.162 | 1 / 1 / 0 | 0 / 0 | 2 / 1796 / 0 | 1.0 | 0.00 | 95.373% | 0.398% | - |
| kernel/calls | pass | 1.000 | 2 / 0 / 2 | 0 / 0 | 0 / 0 / 0 | 0.2 | 0.00 | 0.000% | 0.003% | a call (calls from compiled code need --jit-calls) 2 |
| kernel/method | pass | 1.000 | 2 / 0 / 2 | 0 / 0 | 0 / 0 / 0 | 0.2 | 0.00 | 0.000% | 0.002% | a call (calls from compiled code need --jit-calls) 2 |
| kernel/doubles | pass | 0.100 | 2 / 1 / 1 | 0 / 0 | 1 / 986 / 0 | 0.6 | 0.00 | 66.891% | 0.460% | a call (calls from compiled code need --jit-calls) 1 |
| kernel/array-sum | pass | 0.427 | 1 / 1 / 0 | 0 / 0 | 1 / 1996 / 0 | 0.9 | 0.00 | 98.596% | 0.065% | - |
| kernel/typed-array | pass | 0.842 | 2 / 2 / 0 | 8 / 1 | 2 / 998 / 1 | 1.5 | 0.01 | 49.607% | 49.882% | - |

With `--jit-calls`:

| Benchmark | output | instr / plain | hot / compiled / refused | deopts / unlinked | compile ms | code MB | compiled instr | compiler instr | top refusals |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| octane/richards | pass | 0.823 | 18 / 18 / 0 | 41 / 5 | 5.8 | 0.12 | 63.820% | 6.471% | - |
| octane/deltablue | pass | 1.166 | 94 / 75 / 19 | 340 / 42 | 41.8 | 0.97 | 27.301% | 9.139% | deoptimized again where it was already widened 13; a body too short to gain from compiling 3; recompiled too often 3 |
| octane/crypto | pass | 1.030 | 59 / 40 / 19 | 264 / 33 | 56.8 | 0.88 | 0.584% | 2.486% | deoptimized again where it was already widened 10; `step_arg8` 2; `put_arg` 2 |
| octane/raytrace | pass | 1.125 | 76 / 55 / 21 | 427 / 53 | 37.7 | 1.09 | 0.177% | 8.079% | deoptimized again where it was already widened 12; recompiled too often 7; `special_object` 1 |
| octane/earley-boyer | pass | 1.044 | 84 / 51 / 33 | 310 / 38 | 28.2 | 0.59 | 0.453% | 2.267% | deoptimized again where it was already widened 8; `fclosure8` 6; recompiled too often 5 |
| octane/regexp | pass | 1.189 | 13 / 5 / 8 | 32 / 4 | 7.7 | 0.13 | 9.232% | 2.957% | `regexp` 7; `array_from` 1 |
| octane/splay | pass | 1.026 | 42 / 32 / 10 | 224 / 28 | 19.4 | 0.37 | 0.129% | 1.492% | recompiled too often 6; deoptimized again where it was already widened 3; `object` 1 |
| octane/navier-stokes | pass | 1.051 | 17 / 15 / 2 | 57 / 7 | 37.4 | 0.53 | 1.419% | 5.201% | `get_scope0_el` 1; recompiled too often 1 |
| octane/pdfjs | pass | 1.064 | 108 / 63 / 45 | 287 / 34 | 80.7 | 1.13 | 4.792% | 8.722% | `array_from` 13; deoptimized again where it was already widened 10; `get_scope0_el` 4 |
| octane/mandreel | pass | 1.003 | 127 / 101 / 26 | 595 / 73 | 458.8 | 8.50 | 33.508% | 33.280% | recompiled too often 12; deoptimized again where it was already widened 8; a boolean operand of a bitwise operator: and_imm 3 |
| octane/gbemu | pass | 1.023 | 169 / 141 / 28 | 255 / 29 | 94.3 | 1.75 | 11.820% | 10.783% | deoptimized again where it was already widened 8; `array_from` 7; `put_arg` 7 |
| octane/code-load | pass | 1.000 | 17 / 8 / 9 | 56 / 7 | 4.1 | 0.06 | 0.000% | 0.000% | `special_object` 6; `fclosure8` 2; `for_in_start` 1 |
| octane/box2d | pass | 1.544 | 174 / 102 / 72 | 650 / 81 | 210.0 | 4.62 | 0.255% | 29.785% | `put_arg` 31; `special_object` 15; deoptimized again where it was already widened 8 |
| octane/zlib | pass | 0.985 | 26 / 0 / 26 | 0 / 0 | 145.1 | 1.26 | 1.165% | 1.174% | `put_arg` 21; deoptimized again where it was already widened 2; `fclosure8` 1 |
| octane/typescript | pass | 1.196 | 654 / 486 / 168 | 3487 / 431 | 544.1 | 14.24 | 2.835% | 12.225% | deoptimized again where it was already widened 91; recompiled too often 25; `array_from` 15 |
| kernel/sum-calls | pass | 0.168 | 2 / 2 / 0 | 0 / 0 | 1.1 | 0.01 | 66.304% | 0.397% | - |
| kernel/sum-long | pass | 0.091 | 1 / 1 / 0 | 0 / 0 | 0.5 | 0.00 | 97.664% | 0.282% | - |
| kernel/nested | pass | 0.162 | 1 / 1 / 0 | 0 / 0 | 1.0 | 0.00 | 95.374% | 0.398% | - |
| kernel/calls | pass | 0.648 | 3 / 3 / 0 | 0 / 0 | 1.1 | 0.01 | 89.578% | 8.896% | - |
| kernel/method | pass | 0.289 | 3 / 3 / 0 | 0 / 0 | 1.3 | 0.01 | 94.401% | 0.156% | - |
| kernel/doubles | pass | 0.100 | 2 / 2 / 0 | 0 / 0 | 1.0 | 0.01 | 66.519% | 0.830% | - |
| kernel/array-sum | pass | 0.427 | 1 / 1 / 0 | 0 / 0 | 0.7 | 0.00 | 98.596% | 0.065% | - |
| kernel/typed-array | pass | 0.842 | 2 / 2 / 0 | 8 / 1 | 1.3 | 0.01 | 49.607% | 49.882% | - |

### Reading

- Octane `--jit` is now 1.02x plain (geomean of medians; 0.96x at da86b81c, other host). Compile
  cost fell: zlib compile 128 ms (3,228 ms before), mandreel 74 ms (899 ms); on Octane the compiler share is at
  most 7.4% of instructions with `--jit` (34% before). Only box2d still runs more instructions with
  `--jit` (1.082x).
- `--jit-calls` now compiles most of the hot functions of richards (18 of 18, 63.8% of instructions
  in compiled code, 0.823x the instructions of plain) and mandreel (33.5%), but costs more than it
  gains on box2d (1.544x instructions, compiler 29.8%), typescript (1.196x), regexp (1.189x) and
  deltablue (1.166x): deopt churn on `call_method` (437 sites), `put_field` (226), `if_false8` (122).
- Kernels with `--jit-calls`: method 8.88 ns (4.4x faster than plain, 7.7x behind V8 JIT), calls
  20.5 ns (1.4x faster than plain). With plain `--jit` both stay at interpreter speed (method 0.80x
  plain).
- typed-array is compiled now (49.6% of instructions in compiled code) but its compiler share is
  as large (49.9%), so the kernel gains only 1.15x.
- Refusals with `--jit`: a call (needs `--jit-calls`) 781, `put_arg` 85, `array_from` 40,
  `fclosure8` 28, `special_object` 26. With `--jit-calls`: deoptimized again where already widened
  219, recompiled too often 95, `put_arg` 86. Functions refused after deoptimizing (unlinked after
  their deopt limit), by site, with `--jit-calls`: `call_method` 94, `put_field` 38,
  `call_constructor` 31, `put_array_el` 18. Deopt operand kinds with `--jit` (decisive/next):
  `add int/int` 32, `put_field int/object` 31, `put_field object/object` 14, `put_field null/object` 13.
