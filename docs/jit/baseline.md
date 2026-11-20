# The baseline tier

Status on 2026-11-20: a spike on x86-64 that runs Richards and DeltaBlue end to end. It answers
step 2 of the plan of 20 November (one vertical at a time, Richards first): is a tier that
compiles every bytecode instruction to a fixed template, on the interpreter's own frame, a
better base than the SSA compiler's separate frame world?

Everything here was measured on the JIT shell (`modules/jit/shell`) in release mode unless it
says otherwise. Code: `modules/jit/src/baseline.silk` (the compiler), `baseline_env.silk` (what
the code reaches at run time), `modules/engine/src/js_baseline.silk` (the engine's side) and
`js_vm.silk` (`enterBaseline`, `baselineService`, `baselineFinish`).

## Result

Richards, fixed work, marginal instructions for 20 runs of the benchmark (40 runs minus 20, so
startup and compilation cancel):

| Build | Instructions | Against the interpreter | Instructions per call |
| --- | ---: | ---: | ---: |
| Interpreter | 512.7M | 1.00x | 157 to 335 |
| SSA tier, `--jit --jit-calls` | 385.1M | 1.33x fewer | |
| Baseline, first complete (`0f3925af`) | 313.3M | 1.64x fewer | 103 |
| Baseline, lazy frames and trimmed checks | 260.8M | 1.97x fewer | 75 |
| Baseline, second pass (this state) | 240.0M | 2.14x fewer | 63 |

On the clock, 400 runs in one process, user time, 15 paired rounds on a shared 4-core host: the
interpreter's median is 0.780 s and baseline's 0.510 s, 1.53x. The SSA tier with compiled calls
takes 0.60 to 0.66 s on the same script.

Against the spike's gate (Richards at 1.5x or better, zero departures, 25 instructions or fewer
per call):

- **1.5x: met, narrowly.** 1.53x on medians, 2.14x in instructions.
- **Zero departures: met.** All 17 hot functions compile, no reachable instruction lacks a
  template, and the run records no departure to the interpreter. In a 20-run script 772,322
  calls go straight from baseline code to baseline code and 8,933 go through the engine
  (callees that are not hot yet).
- **25 instructions per call: not met.** A call costs 63: 29.5 at the call site, 17.3 in the
  prologue, 12.8 leaving and 3 for the return. The 25 came from the SSA tier's 18-instruction
  call, which passes values in registers, has no frame record and drops no counts. A tier that
  keeps the interpreter's frame and counted 16-byte cells cannot get there; the anatomy below
  says where the 63 go and what a higher tier removes.

86.7% of the run's instructions are in baseline code. The rest is the engine's helpers for
polymorphic field reads (about 4%) and startup.

### DeltaBlue

The second vertical. With Richards' templates alone DeltaBlue ran slower than the interpreter:
368,055 activations left baseline code in a fixed run, and each departure costs about 380
instructions before the interpreter runs its first one. Templates for the nine opcodes it
departed on (below) bring that to 103.

| DeltaBlue, marginal instructions for 20 runs | Instructions | Against the interpreter |
| --- | ---: | ---: |
| Interpreter | 739.3M | 1.00x |
| Baseline with Richards' templates | slower than the interpreter | |
| Baseline, this state | 579.3M | 1.28x fewer |

51 functions compile, none is refused and none has an instruction without a template. 2.0M
calls go straight from baseline code to baseline code and 110,254 through the engine: about
75,000 calls of natives (`Array.prototype.push` and `pop`, `Function.prototype.call`), 12,600
constructions, and calls of functions that are not hot yet. 56% of the run's instructions are
in baseline code. What keeps it from Richards' ratio:

- Constructors run interpreted (a construction's `new.target` has no place in a bare frame
  yet), and so do the test drivers, whose loops are entered once per run. About 15% of the run
  is still the interpreter.
- `get_field2` misses its one-entry site cache 160,000 times (method lookups on receivers of
  several shapes), each a helper call of about 120 instructions.
- Field reads and calls cost what they cost on Richards: 38 instructions for a prototype
  method lookup, 60 for a call.

### The other six

A fixed run of each remaining V8 benchmark, whole process, before any work on them:

| Benchmark | Compiled | Departures | Against the interpreter | Departs on |
| --- | ---: | ---: | ---: | --- |
| Crypto | 15 | 294,103 | 0.94x | the fused local and argument arithmetic, `step_loc8`, element reads from locals |
| RayTrace | 29 | 406,452 | 0.40x | fused arithmetic, `put_arg`, `neg`, `push_const8`, `put_var`, `arguments` |
| EarleyBoyer | 21 | 976,919 | 0.63x | `instanceof`, null tests, `typeof`; most of its functions are closures |
| RegExp | 2 | 32,059 | 0.98x | scope reads, `array_from` |
| Splay | 13 | 537,613 | 0.76x | object literals, scope reads, `put_var`, `throw` |
| NavierStokes | 1 | 1 | 1.00x | nothing compiles: its functions read a scope |

A departure is expensive, so a function that departs on most calls is a loss. The list is the
work for the next gate (no benchmark above the interpreter's count): templates for the hot
fused opcodes, scope reads and captured variables, constructors, and one engine service that
runs any single rare instruction and returns to the code.

## How to run it

```sh
silkjs-jit-shell --jit-baseline script.js          # hot functions get baseline code
    --jit-threshold=N                              # entries before a function is hot
    --jit-stats=FILE                               # counters, among them baseline-*
    --jit-dump                                     # code bytes and the code map on stderr
```

`--jit-baseline` implies `--jit` and replaces the SSA compiler: a hot function gets baseline
code or stays interpreted.

## Design

### One template per instruction

`compile` walks the bytecode once to find the depth of the operand stack at every reachable
instruction, then emits one template per instruction in bytecode order. Every value lives in its
cell, exactly where the interpreter keeps it: a template loads its operands from their cells
into scratch registers and stores its result back. Nothing is cached in registers between
instructions, so the frame is a valid interpreter frame at every instruction boundary.

An instruction without a template is an exit: it jumps to a block that hands the activation to
the interpreter (`SERVICE_FINISH`), which runs the rest of the function on the same cells and
returns its result. The compiler reports such opcodes (`Outcome.uncovered`,
`baseline-uncovered`), and each use counts as a departure (`baseline-departures`).

Work that is rare stays out of the straight path as a slow path (`Slow`, emitted after the
body): a count that drops to zero, a cache miss, a call of a function without baseline code, a
poll.

Two adjacent instructions compile as one where the second only consumes what the first makes
and no branch reaches it (`fused`): `push_this; put_loc`, `is_undefined_or_null` followed by a
branch, and a comparison followed by a branch.

Numbers: two Ints compute inline. An overflow, a product of 0, a division, a remainder or any
other pair of numbers goes to one helper (`arithmetic`, the interpreter's `numericFast`), and
only what is not a pair of numbers leaves to the interpreter.

### Frame

The code runs on the native stack:

```
[rbp + 8]        return address
[rbp]            the caller's rbp
[rbp - R, rbp)   the BaselineFrame record (js_baseline); its last word is the state
below it         the cells: [arguments][locals][operand stack], 16 bytes each, ascending
```

The record holds a `StackFrame`, which is what the engine reads when it walks frames, plus the
caller's `argv` and `argc`, the bytecode's address and a slot for a service's result.

A frame starts **bare**. The prologue stores only what a call needs: the function, the
receiver, the arguments, the locals as undefined and the bytecode's address. When the code asks
the engine for anything (every `SERVICE_*` request), `js_baseline.build` first completes the
bare frames from the innermost outwards and publishes them as the runtime's current frame
chain. It finds the callers through the saved rbp chain; the entry stub keeps two zero words
where a record's state would be, which ends the walk. A frame that was built is unlinked when
it returns; a frame that stayed bare just pops. Anything that reads the frame chain (error
stacks, closures attaching to a frame, the debugger) therefore sees every frame, and a call that
never leaves baseline code pays for none of it.

### Registers and calls

r12 is the `BaselineEnv` and r13 the runtime for the whole run of baseline code. rbp is the
frame. Everything else is scratch; rbx, r14 and r15 are never touched.

A call passes rdi the function (the closure object's cell), r11 its bytecode object, rsi argv,
rdx argc and rcx:r8 the receiver. Arguments stay in the caller's operand cells and are borrowed:
the callee copies them only when it writes a parameter or was passed fewer than it declares.
The result returns in rax:rdx (tag word, payload); the Exception tag means the call threw and
the exception is pending in the runtime.

A call site checks that the callee is a bytecode function with baseline code
(`FunctionBytecode.baseline`, one plus an index into a table the embedder lends) and calls
through the table. Anything else goes through the engine (`SERVICE_CALL`).

The engine enters baseline code from `callInternal` through a stub (`entryStub`) that turns the
C ABI into this one. It does so only for a plain call: no `new.target`, no resumed generator,
and no instruction observer (debugger, coverage, profiler).

### What the code asks the engine for

One entry, `baselineService(hooks, allocator, record, request, base, count)`, reached through
the runtime:

| Request | Meaning |
| --- | --- |
| `SERVICE_FINISH` | The interpreter finishes this activation from the published bytecode offset, with `count` operands on the stack; with `FINISH_THROWING` an exception is pending and it unwinds first |
| `SERVICE_CALL` | Call the value at `base` on `count` arguments; with `CALL_METHOD` the cell before it is the receiver |
| `SERVICE_CONSTRUCT` | Construct with the function at `base`, `new.target` after it, then `count` arguments |
| `SERVICE_POLL` | The interrupt counter ran out |
| `SERVICE_OVERFLOW` | No room on the native stack: throw the RangeError |

Helpers (`BaselineEnv.helpers`, C functions named by index) cover the misses that run no user
code: field reads and writes that miss their cache, `get_var`, loose equality, truthiness,
`!`, arithmetic and comparisons of numbers, string constants, element reads and stores. A helper that would have to run user code returns 0 and the template
exits to the interpreter instead, so user code never runs under a bare frame.

### Fields, variables, elements

- `get_field`, `get_loc_field8`, `get_arg_field8`, `put_field`, `put_loc_field_loc8` use the
  interpreter's inline key in the bytecode (`version << 16 | slot` at the operand + 4): shape
  version shifted and xored against the key leaves the slot index or a miss.
- `get_field2` uses the interpreter's site cache (`RuntimeState.fieldCache`), own and prototype
  entries.
- `get_var` reads the closure's variable cell inline, detached or attached to a frame.
- `get_array_el` and `put_array_el` handle a fast Array with an Int index in bounds.

The code and the interpreter share these caches, so either one warms them for the other.

### Counts

Cells are counted as in the interpreter. A copy adds a count when the tag is a heap tag (one
byte compare, since the heap tags are 0 to 6). A drop subtracts first and takes the slow path
when the result is zero or below; the slow path adds the count back and calls the engine's
release through a stub that preserves every register.

### Polls

A taken backward branch charges the realm's interrupt counter and polls when it runs out. A
function entry does not: recursion is bounded by the stack check, so every unbounded run passes
a backward branch or interpreted code.

### No addresses in the code

The code holds no process-local address. Helpers are reached by index through the environment,
the engine's service and the code table through the runtime, bytecode and caches through the
frame. Inline caches stay in the bytecode and the runtime, where the interpreter keeps them.
This is what ahead-of-time compilation needs.

### What the interpreter pays

A linked function sets `FunctionBytecode.baseline` and reuses the frame-cells sentinel, so the
interpreter's inline call finds no room for it and the call reaches `callInline`, which enters
the code. The interpreter gains no check on its fast paths. Its instruction counts on the eight
V8 benchmarks, against the build before the tier (`74490486`, `scripts/v8bench.py
--instructions`), moved by at most 0.03%:

| Benchmark | Before | With the tier |
| --- | ---: | ---: |
| richards | 521,963,323 | 521,950,931 |
| deltablue | 749,732,780 | 749,759,390 |
| crypto | 3,021,285,126 | 3,020,824,446 |
| raytrace | 1,244,834,173 | 1,245,128,329 |
| earley-boyer | 1,153,452,879 | 1,153,447,065 |
| regexp | 1,367,268,925 | 1,367,522,673 |
| splay | 1,319,620,930 | 1,319,645,730 |
| navier-stokes | 1,100,563,324 | 1,100,548,265 |

One exception keeps its interpreter path: a leaf the interpreter runs without a frame
(`js_vm_leaf`) whose runs were never declined stays frameless for interpreted callers, which
costs less than any entry into machine code; baseline callers reach its code through the table.
Any other function has its leaf credits cleared when it is linked. Without that, a small
function the interpreter had tried as a leaf kept running interpreted after it had code.

### What compiling costs

Richards' 17 functions (409 bytecode instructions) compile in 0.64 ms in total and take 57,041
bytes of code, about 140 bytes per bytecode instruction with slow paths and exits included.

## Where a call's 63 instructions go

| Part | Instructions | What it does |
| --- | ---: | --- |
| Call site | 29.5 | Callee is an object, a bytecode function, has code (9). Publish the bytecode offset (1). Arguments, receiver, table (6). Call and check for a throw (3). Drop the callee's count, the receiver's and each argument's (8 and up). Store the result (2) |
| Prologue | 17.3 | Frame and stack check (5). State, function, receiver, argv, argc, arguments pointer (8). Bytecode address (2). One store per local |
| Leave | 12.8 | Drop the frame's own arguments and locals, check the state, pop |
| Return | 3 | Result into rax:rdx, jump to leave |

About 20 of the 63 are count traffic for the callee, the receiver and the locals, and about 10
are the frame record. Those are what an optimizing tier removes with values in registers and
calls it can see through; the remaining checks (callee kind, stack, throw) cost about 15.

## Where the rest goes

Shares of baseline code on Richards (40 runs, 443M instructions), and of time from 1,400
samples:

| Part | Instructions each | Share of instructions | Share of time |
| --- | ---: | ---: | ---: |
| `get_loc_field8` | 19.6 | 23.2% | 26.8% |
| `get_field2` | 37.6 | 15.2% | 12.7% |
| `call_method` | 29.5 | 10.6% | 10.2% |
| `put_field` | 22.4 | 9.8% | 12.4% |
| `get_var` | 17.0 | 6.2% | 2.4% |
| prologue | 17.3 | 6.2% | 5.0% |
| leave | 12.8 | 4.6% | 3.8% |
| `get_field` | 21.4 | 3.2% | 7.2% |

Field access is half of the instructions and almost 60% of the time. Time follows instructions
closely, so there is no single stall to remove; the code is bound by loads that depend on loads
(cell, object, slots, value, cell again), and fewer instructions is what makes it faster.

## Checks

- `scripts/differential.py --configs plain,baseline,baseline-eager`: generated programs agree
  with the interpreter at thresholds 20 and 1. 1,500 of 1,500 agree, run on the build with the
  leaf fix and again on the build with DeltaBlue's templates.
- `silk test` in `modules/jit`: 94 of 94, with `hotFunctionsRunBaselineCode` running a linked
  list, field stores, a throw through two baseline frames, deep recursion, and the operators,
  keep branches, `length`, string constants and a construction DeltaBlue added.
- Hand tests for deep recursion and the stack overflow, exceptions through baseline frames,
  error stacks from frames built lazily, closures, `arguments`, getters, and every comparison
  on mixed operand types, at thresholds 1, 5 and 60.
- Richards and DeltaBlue print the interpreter's output at every threshold.

## Tools

`scripts/jit_baseline_profile.py <shell> <script.js>` runs the script under callgrind and joins
the count of every machine instruction with the code map that `--jit-dump` prints: one row per
kind of part (opcode, prologue, leave, each slow path), with instructions, share, entries and
instructions per entry. `--show NAME` disassembles the hottest instance with its counts,
`--functions` adds a row per function, and `--time SAMPLER.so` prints time shares from an
LD_PRELOAD program-counter sampler instead.

## Not done

- Opcodes beyond what Richards and DeltaBlue use: see the table of the other six benchmarks.
  93 of the interpreter's 250 opcodes have a template.
- Only plain functions compile: no scope of their own, no captured locals, not a known local
  function, not async or a generator. Constructors run interpreted.
- Calls of natives go through the engine's generic call, without the interpreter's quick
  paths for `push`, `pop`, `charCodeAt` and the like.
- A function that keeps departing is never given back to the interpreter.
- Exceptions leave to the interpreter, which unwinds and finishes the activation. Handlers
  never run in baseline code.
- No entry into a running loop.
- Code is never freed, and the table holds 4,096 functions.
- x86-64 only.

## Next cuts, measured or estimated on Richards

| Change | Saves |
| --- | --- |
| The top of the operand stack in a register pair between templates | About 4 instructions per pushed value, 10% |
| `get_loc_field8; get_field` as one template, without the middle count | 9 per pair, 1.2% |
| Callee count elided between `get_field2` and its call when the arguments run no user code | 6 per method call, 2% |
| A stub in table slot 0 instead of the has-code test | 2 per call, 0.7% |
| Bytecode offset from the return address instead of a store per call | 1 per call, and the table an optimizing tier needs anyway |
