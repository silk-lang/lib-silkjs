# The baseline tier

Status on 2026-11-20: a tier on x86-64 that runs the eight V8 benchmarks end to end. It answers
step 2 of the plan of 20 November (one vertical at a time, Richards first): is a tier that
compiles every bytecode instruction to a fixed template, on the interpreter's own frame, a
better base than the SSA compiler's separate frame world? Both gates of that step are measured
below: Richards first, then all eight benchmarks.

Everything here was measured on the JIT shell (`modules/jit/shell`) in release mode unless it
says otherwise. Code: `modules/jit/src/baseline.silk` (the compiler), `baseline_env.silk` (what
the code reaches at run time), `modules/engine/src/js_baseline.silk` (the engine's side) and
`js_vm.silk` (`enterBaseline`, `baselineService`, `baselineFinish`, `baselineStep`,
`baselineNative`, `baselineLoop`).

## Result

### The first gate: Richards

The numbers of this part are the state at the first gate (commit `6afdf7ec`). Richards, fixed work, marginal instructions for 20 runs of the benchmark (40 runs minus 20, so
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

### The second gate: all eight

The gate: no benchmark above the interpreter's instruction count, and 95% of bytecode
instructions in machine code. A fixed run of each benchmark, whole process, compilation
included:

| Benchmark | Runs | Interpreter | Baseline | Fewer | In machine code, whole run | Runs 22 to 27 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Richards | 20 | 521.9M | 258.9M | 2.02x | 99.6% | 100.0% |
| DeltaBlue | 20 | 750.1M | 627.6M | 1.20x | 95.0% | 98.6% |
| Crypto | 4 | 3,020.9M | 1,379.9M | 2.19x | 99.5% | 100.0% |
| RayTrace | 8 | 1,245.6M | 1,175.8M | 1.06x | 99.2% | 99.9% |
| EarleyBoyer | 2 | 1,153.4M | 1,110.3M | 1.04x | 97.4% | 97.9% |
| RegExp | 2 | 1,367.5M | 1,244.5M | 1.10x | 88.8% | 99.7% |
| Splay | 4 | 1,320.3M | 1,272.3M | 1.04x | 98.5% | 99.2% |
| NavierStokes | 2 | 1,100.5M | 669.8M | 1.64x | 97.3% | 100.0% |

- **No benchmark above the interpreter: met.** The margin is 4% or more everywhere. Whole-run
  counts of the baseline column move by 1% to 2% from build to build (placement of code and of
  collections), so the three smallest ratios are not ranked against each other.
- **95% in machine code: met in steady state on all eight, and on seven in the short runs.**
  "In machine code" counts bytecode instructions: entries into templates, less the steps,
  against the interpreter's dispatches (`jit_baseline_profile.py --coverage`). The last column
  is runs 22 to 27 of a 27-run process (the difference of two processes), which is the tier
  without its warm-up. RegExp's fixed run is two runs of the benchmark. Its twelve block
  functions are entered once per run, so they never count 100 entries and get their code
  through loop entry, which needs three polls of a loop that is running; much of the first run
  is over by then. Over 27 runs the whole process is at 95.0%. What stays interpreted in
  steady state is the functions the tier refuses (four in EarleyBoyer, most of its 2%) and
  steps.
- No function departs: every reachable instruction has a template or runs as a step.

How much the tier can take out depends on where the interpreter spends its instructions. Per
bytecode instruction executed, in the same runs:

| Benchmark | Interpreter, instructions per bytecode instruction | Baseline takes out | Calls through the engine | Steps |
| --- | ---: | ---: | ---: | ---: |
| Crypto | 24 | 13 | 18,466 | 15,936 |
| NavierStokes | 23 | 9 | 13 | 496 |
| Richards | 38 | 19 | 970 | 0 |
| DeltaBlue | 36 | 6 | 118,153 | 187 |
| EarleyBoyer | 51 | 2 | 529,713 | 52,636 |
| RayTrace | 65 | 4 | 615,096 | 11,356 |
| Splay | 83 | 3 | 41,938 | 201 |
| RegExp | 87 | 8 | 350,832 | 13,610 |

Where the interpreter spends 23 to 38 instructions per bytecode instruction the work is the
bytecode itself, and templates remove a third to a half of it. Where it spends 51 to 87 the
work is in the runtime (allocation, collection, natives, the regular expression engine), which
this tier calls exactly as the interpreter does. There a template can only remove dispatch and
operand traffic, and each call that still goes through the engine (a native, a construction, a
callee that is not hot yet) and each step (about 450 instructions) gives some of that back.

## How to run it

```sh
silkjs-jit-shell --jit-baseline script.js          # hot functions get baseline code
    --jit-threshold=N                              # entries before a function is hot (default 100)
    --jit-stats=FILE                               # counters, among them baseline-*
    --jit-dump                                     # code bytes and the code map on stderr
```

`--jit-baseline` implies `--jit` and replaces the SSA compiler: a hot function gets baseline
code or stays interpreted. The HTTP embedding host (`modules/jit/embed-smoke`) takes the same
flag, and `modules/runtime/bench/jit_http.py --jit-baseline` runs the order service on it.

A function is hot after 100 entries with this tier, where the engine's default for the SSA
compiler is 1,000 (`jit_runtime.BASELINE_ENTRIES`). Baseline code costs about 4,700
instructions to make per bytecode instruction and saves about 20 each time one runs, so it has
paid for itself after a few hundred executions. Whole fixed runs at thresholds 20, 50, 100 and
200 differ by less than the build-to-build noise on six benchmarks; Richards runs 4% fewer
instructions at any of them than at 1,000 and DeltaBlue 3% to 6% fewer.

## Design

### One template per instruction

`compile` walks the bytecode once to find the depth of the operand stack at every reachable
instruction, then emits one template per instruction in bytecode order. Every value lives in its
cell, exactly where the interpreter keeps it: a template loads its operands from their cells
into scratch registers and stores its result back. Nothing is cached in registers between
instructions, so the frame is a valid interpreter frame at every instruction boundary.

An instruction without a template is a **step**: the code asks the engine to run that one
instruction in the interpreter, on the same cells, and goes on after it (`SERVICE_STEP`,
`js_vm.baselineStep`, which runs a copy of the dispatch loop that stops before the frame's
next instruction). A template that meets a case it does not handle, such as an element read on
something that is not a fast Array, steps the same way. A step costs about 450 instructions:
75 to build the frame, 110 to describe the activation and make the interpreter's state, 170 in
the one-instruction loop, 45 in the trampolines and 15 in the code. The compiler reports
stepped opcodes (`Outcome.stepped`, and `step:<opcode>` counts in `--jit-stats`).

The interpreter may leave the frame somewhere else than the next instruction: at a branch
target, after a pair it runs as one, or at a handler that took what the instruction threw. The
service then answers where the frame is (`js_baseline.moved`: bytecode offset and operands on
the stack), and the code looks that offset up in the function's **resume table**, one word per
bytecode byte after the code, with the distance to the instruction's template and the operand
depth it expects. If the table has it, the code jumps there (`baseline-resumes`). If not, the
interpreter finishes the activation (`SERVICE_FINISH`), which is the only way an activation
still leaves baseline code and counts as a departure (`baseline-departures`). No benchmark of
the eight departs.

Work that is rare stays out of the straight path as a slow path (`Slow`, emitted after the
body): a count that drops to zero, a cache miss, a call of a function without baseline code, a
poll.

Two adjacent instructions compile as one where the second only consumes what the first makes
and no branch reaches it (`fused`): `push_this; put_loc`, `is_undefined_or_null` followed by a
branch, and a comparison followed by a branch.

Numbers: two Ints compute inline, and so do two Float64 and an Int with a Float64 for `+`, `-`,
`*` and the orderings. An overflow, a product of 0, a remainder or any other pair of numbers
goes to one helper (`arithmetic`, the interpreter's `numericFast`), and only what is not a pair
of numbers is a step.

Truthiness is inline for booleans, Ints, undefined, null, flat strings (by length) and objects
(true unless the object is one of the falsy kind); a flat string's `length` is one load.

Object and array literals, `define_field` and the `+` of a string with a string or a number go
through services that build no frame (`SERVICE_QUICK`, `SERVICE_CONCAT`): they only allocate,
so nothing can read the frame chain meanwhile.

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
it returns; a frame that stayed bare just pops. A frame entered through the function's
construct entry is in the construct state of each (`FRAME_BARE_CONSTRUCT`,
`FRAME_BUILT_CONSTRUCT`), which is where `new.target` lives: it is the function itself. Anything that reads the frame chain (error
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
C ABI into this one. It does so for a plain call and for a `new` of the function itself
(through the construct entry, the second table slot of each function), never for a resumed
generator or under an instruction observer (debugger, coverage, profiler).

A known local function (`js_compiler_known`) has no closure object. Its frame names its
bytecode as the function, and the caller passes the scope it runs in where a closure's caller
passes the object (rdi). A call site reaches one out of line (`S_KNOWN`).

A native callee is called without any frame of the engine's (`CALL_NATIVE`,
`js_vm.baselineNative`), as the interpreter's call instruction calls one: first the answers
that need no native frame (Math on numbers, `push` and `pop`, the string methods with a
primitive entry, `String(int)`, regular expression `exec` and `replace`, the collection
reads), then the native itself. The call charges the interrupt counter as the interpreter's
does.

### What the code asks the engine for

One entry, `baselineService(hooks, allocator, record, request, base, count)`, reached through
the runtime:

| Request | Meaning |
| --- | --- |
| `SERVICE_FINISH` | The interpreter finishes this activation from the published bytecode offset, with `count` operands on the stack. With `FINISH_THROWING` an exception is pending and it unwinds first: when a handler of the frame takes it, the answer is `moved` to the handler and the code goes on there |
| `SERVICE_CALL` | Call the value at `base` on `count` arguments; with `CALL_METHOD` the cell before it is the receiver, with `CALL_NATIVE` the callee is a native and gets no engine frame |
| `SERVICE_CONSTRUCT` | Construct with the function at `base`, `new.target` after it, then `count` arguments |
| `SERVICE_POLL` | The interrupt counter ran out |
| `SERVICE_OVERFLOW` | No room on the native stack: throw the RangeError |
| `SERVICE_STEP` | Run the one instruction at the published offset in the interpreter |
| `SERVICE_QUICK` | An allocating instruction (`object`, `define_field`, `array_from`) without a frame; the engine may decline, and the instruction is a step then |
| `SERVICE_CONCAT` | The `+` of a string and a string or number, without a frame |
| `SERVICE_RESUME` | Only from a resume entry: fill the new frame from an interpreter activation (below) |

The first five and the step build the bare frames first; the last three do not.

Helpers (`BaselineEnv.helpers`, C functions named by index) cover the misses that run no user
code: field reads and writes that miss their cache, `get_var`, loose equality, truthiness,
`!`, arithmetic and comparisons of numbers, string constants, element reads and stores. A helper that would have to run user code returns 0 and the template
steps instead, so user code never runs under a bare frame.

### Exceptions

A throw in baseline code, or in anything it called, reaches the code as a service or a call
that answers "threw". The code asks the engine to unwind (`FINISH_THROWING`). The interpreter's
unwinder runs on the frame's cells, where the catch markers are operands as in any frame: with
a handler in this frame the code goes on at the handler through the resume table, and without
one the cells are released and the caller sees the exception. Handlers therefore run in
baseline code.

### Entering a running loop

A function that is called once and loops for long is hot before it is ever entered again. The
interpreter reports it at a back-edge poll (`js_hotness.loopPoll`), it compiles at the next
poll, and from the poll after that the running activation moves over (`js_vm.baselineLoop`,
called from `backEdgePoll`, which only runs when the interrupt counter is out):

1. The function has a **resume entry**, a third way into its code next to the plain and the
   construct entries. Its distance from the construct entry is in the four bytes before that
   entry (0 for none), so the table needs no third slot.
2. The engine calls the resume entry through the usual stub with a `js_baseline.Resume` in
   place of the arguments: the activation's argument cells, locals, operand stack, bytecode
   offset and operand depth.
3. The resume entry makes the frame as the prologue does, then asks `SERVICE_RESUME`. The
   engine fills the cells: arguments as the prologue would (the frame's own copies when the
   function writes a parameter), locals and operands moved out of the interpreter's frame. It
   answers `moved` to the back edge's target, and the code goes on there through the resume
   table.
4. When the code returns, the interpreter's activation holds no values. It gets the result on
   its stack and its instruction pointer at a `return` of the function, so it ends as any
   activation does. An exception the code let out is raised with the activation's operand
   stack empty, so no handler of it sees the exception a second time.

While the code runs, its frame stands in the frame chain where the activation's did, so an
error stack shows the function once. A function gets a resume entry unless it reads how it was
called (`arguments`, a rest parameter) or has no `return` instruction to end at. Only a plain
call's activation moves: not a construction, not a setter's.

On NavierStokes, whose `lin_solve` runs for about 10M instructions per call, this took the
share of bytecode instructions in machine code from 76% to 96% and the run from 1.43x to 1.63x
fewer instructions than the interpreter (both at the 1,000-entry threshold the tier had then).

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

A taken backward branch charges the realm's interrupt counter and polls when it runs out, and
so does a call of a native. A function entry does not: recursion is bounded by the stack check,
so every unbounded run passes a backward branch or interpreted code.

### No addresses in the code

The code holds no process-local address. Helpers are reached by index through the environment,
the engine's service and the code table through the runtime, bytecode and caches through the
frame. Inline caches stay in the bytecode and the runtime, where the interpreter keeps them.
This is what ahead-of-time compilation needs.

### What the interpreter pays

A linked function sets `FunctionBytecode.baseline` and reuses the frame-cells sentinel, so the
interpreter's inline call and inline construction find no room for it and the call reaches
`callInline` or `constructWith`, which enter the code. The interpreter gains no check on its
fast paths; the checks sit where an inline frame was already refused. Its instruction counts on
the eight V8 benchmarks, against the build before the tier (`74490486`, `scripts/v8bench.py
--instructions`):

| Benchmark | Before | With the tier | |
| --- | ---: | ---: | ---: |
| richards | 521,963,339 | 521,920,059 | 1.000x |
| deltablue | 749,732,780 | 750,203,328 | 1.001x |
| crypto | 3,020,678,796 | 3,019,926,091 | 1.000x |
| raytrace | 1,245,110,287 | 1,249,627,662 | 1.004x |
| earley-boyer | 1,153,452,637 | 1,153,416,570 | 1.000x |
| regexp | 1,367,250,776 | 1,367,498,331 | 1.000x |
| splay | 1,319,620,824 | 1,320,347,019 | 1.001x |
| navier-stokes | 1,100,563,338 | 1,100,521,749 | 1.000x |

Two rows of this tool move with things that are not the tier, in either build:

- RayTrace swings by 4M (0.3%) with the script's path, which decides where bytecode lands and
  so which sites share a slot of the prototype field cache. At another path of the same length
  the build before the tier counts 1,249.35M and this one 1,245.57M. By function, the tier's
  own cost there is 0.73M in `constructInline` and 0.16M in `executeLoop`, 0.07%.
- RegExp has two levels, 1,367M and 1,390M, picked by the size of the process environment
  (it moves the native stack, and with it the alignment of the matcher's buffers). Each build
  hits the high level at some sizes: the old one with 5 or 13 more bytes of environment, this
  one with 64. The row above is from a run where both sit on the low level.

An earlier state of this branch did break the 0.5% budget on RayTrace (0.57%), with a test for
baseline code on every construction. The test now runs only after an inline frame was refused.
`joinText` is marked `@inlineAlways` for the same reason: a second caller (the tier's concat
service) had moved it out of line under the interpreter's `+`.

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
  with the interpreter at thresholds 20 and 1. 1,500 of 1,500 agree on the final state, with
  3.8M resumes through the resume table, 158M steps and 0.7M departures among them (generated
  programs use what the benchmarks do not: generators, `for-of`, private fields, `try`).
- `silk test` in `modules/jit`: 94 of 94. `hotFunctionsRunBaselineCode` runs a linked list,
  field stores, a throw through two baseline frames, deep recursion, operators, keep branches,
  `length`, string constants, constructions, handlers that catch in baseline code, steps that
  move the frame, and three loops that are entered while they run.
- `python3 modules/jit/scripts/baseline_scripts.py <shell>`: the 20 scripts of
  `modules/jit/tests/baseline` print the interpreter's output at thresholds 1, 5 and 60. They
  cover deep recursion and the stack overflow, exceptions through baseline frames, error
  stacks from frames built lazily, closures, `arguments`, getters, constructors, natives, every
  comparison on mixed operand types, and loop entry with live operands. Fixed-work Richards
  and DeltaBlue pass the same way.
- All eight benchmarks print the interpreter's output with baseline code.

## Tools

`scripts/jit_baseline_profile.py <shell> <script.js>` runs the script under callgrind and joins
the count of every machine instruction with the code map that `--jit-dump` prints: one row per
kind of part (opcode, prologue, leave, each slow path, each entry), with instructions, share,
entries and instructions per entry. `--show NAME` disassembles the hottest instance with its
counts, `--functions` adds a row per function, and `--time SAMPLER.so` prints time shares from
an LD_PRELOAD program-counter sampler instead.

`--coverage` prints the gate's measure: bytecode instructions run by templates (entries into
templates, less the steps) against the interpreter's dispatches in `executeLoop` and the
frameless leaf evaluator. Steady state is the difference of two processes that run the
benchmark a different number of times (22 and 27 here).

`--jit-stats=FILE` has the tier's counters: `baseline-compiled`, `-refused`, `-departures`,
`-resumes`, `-service-calls`, `-direct-calls`, `-steps`, and `step:<opcode>` and
`exit:<opcode>` per opcode.

## Not done

- Functions the tier refuses: one with a scope of its own or with locals an inner function
  captures, a known local function that has either, a derived class constructor, async
  functions and generators. EarleyBoyer has four such functions, and they are most of what it
  still interprets.
- Instructions without a template run as steps, and so do the cases a template does not
  handle. The benchmarks step most on the `regexp` literal (RegExp), on `get_length`,
  `special_object` and element reads (EarleyBoyer), on element reads and stores outside the
  fast case (Crypto) and on `mod` (RayTrace).
- A call that leaves baseline code for a native, a construction or a callee without code
  goes through the engine. RayTrace and EarleyBoyer make half a million of those per run.
- A function that keeps stepping or departing is never given back to the interpreter.
- A loop is entered only from a plain call's activation, and only in a function that has a
  `return` and does not read `arguments`.
- Code is never freed, and the table holds 4,096 functions.
- No feedback is recorded for a higher tier yet.
- x86-64 only.

## Next cuts

For the six benchmarks where the runtime dominates, in the order the tables above suggest:

| Change | What it reaches |
| --- | --- |
| Functions with a scope of their own and captured locals | EarleyBoyer's four refused functions and 5,000 `get_var_ref` steps; the same shape is every closure-heavy program |
| A frameless path for constructions and for natives without a quick answer | RayTrace's 615,000 and EarleyBoyer's 530,000 calls through the engine per run |
| `regexp` literals without a step | 13,000 steps per RegExp run, 450 instructions each, 0.5% of the run |
| The cases `mod`, `add_imm`, `get_array_el` and `put_array_el` still step on | RayTrace's 11,000 and Crypto's 16,000 steps per run |
| A step that does not describe the activation for instructions that cannot throw | Every step: 110 of its 450 instructions |

Measured or estimated on Richards:

| Change | Saves |
| --- | --- |
| The top of the operand stack in a register pair between templates | About 4 instructions per pushed value, 10% |
| `get_loc_field8; get_field` as one template, without the middle count | 9 per pair, 1.2% |
| Callee count elided between `get_field2` and its call when the arguments run no user code | 6 per method call, 2% |
| A stub in table slot 0 instead of the has-code test | 2 per call, 0.7% |
| Bytecode offset from the return address instead of a store per call | 1 per call, and the table an optimizing tier needs anyway |
