# Compiled-code entry and deoptimization (milestone 6, part 3)

Design written before the code, on top of [tier-seam.md](tier-seam.md). It is the smallest
mechanism that runs one compiled function inside the engine and falls back to the interpreter
at a bytecode boundary. Measurements are in the last section once they exist; anything not
marked measured or ran is a design statement.

## 1. Where the JIT attaches

The engine never imports `modules/jit`. A JIT-enabled executable is a separate package,
`modules/jit/shell` (binary `silkjs-jit-shell`), that links the engine, `modules/jit` and the same
libc session as `qjs`. It parses its own `--jit*` flags, then runs the ordinary `qjs` launch
with a runtime setup callback that installs three things:

- the hot-function handler (`js_runtime.setHotFunctionHandler`) with the libc host id
  `LIBC_HOT_FUNCTION_C`; `LibcServices.hotFunction` forwards it to a C-ABI function pointer
  in the hook's `opaque`. The handler runs at an interrupt poll and never runs JavaScript: it
  reads the bytecode, compiles or refuses, and links.
- a compiled-code table (`js_runtime.setCompiledTable`): an embedder-owned array of
  `js_compiled.CompiledEntry` (machine-code entry, embedder data word, deopt limit, counters).
- optionally a lower first hot budget (`js_runtime.setHotEntryBudget`, read when a function is
  created; default `HOT_ENTRY_BUDGET` = 1000) so tests and stress runs compile early.

The entry slot is `FunctionBytecode.compiled: u32`, an index into that table plus one (0 =
none). It is runtime state like `hotness`: the binary writer never writes it, the reader and
the compiler initialise it to 0. It is an index, not a pointer, so nothing that could be
stored refers to process memory, and it fits in the struct's existing padding after
`hotness` (to be confirmed by the instruction counts: a grown `FunctionBytecode` moved heap
addresses enough to cost earley-boyer 0.6 percent last time).

Which entries check the slot:

- `callInternal` and `callKnown` (native-stack entries) run the compiled code. The check reads
  a field `describe` already loads.
- `enterFrame` (every inline entry) never takes a linked function, at no cost of its own:
  `js_runtime.linkCompiled` keeps the function's `frameCells` in its `CompiledEntry` and sets
  the field to `STUB_FRAME_CELLS`, the sentinel lazily compiled stubs already use, so the
  existing room check fails and the call falls back through `callInline` to `callInternal`.
  Unlinking restores it. (Ran: a first version that tested `compiled` in `enterFrame` cost
  richards +0.98% instructions; this one +0.02%, see Measurements.)
- Leaf runs, generator and async frames, `vm.resume` and the observed loop never run compiled
  code. While instructions are observed (`observeInstructions`, the debugger) the compiled
  entry is skipped and the interpreter runs.

## 2. Calling convention and where a compiled frame lives

For this milestone the compiled function makes no calls and cannot fail, so a compiled frame is
a native-stack frame nested inside an ordinary interpreter frame: `callInternal` builds the
interpreter frame exactly as it always does (arguments, locals set to undefined, operand stack
empty), then, out of line in `js_compiled.enter`, calls

```
extern "C" fn(arguments: *const ValueBits, state: *mut u64, counter: *mut i32, data: ?*mut u8,
  env: ?*mut u8, frame: *const CompiledFrame) -> u32        (js_compiled.CompiledCode)
```

(Milestone 7 changed this ABI, workstream J: before it arguments and exit slots were 64-bit
"frame-state words", kind << 32 | payload, which cannot hold a heap reference or a double.)

- `arguments`: the frame's argument cells, one `ValueBits` per declared parameter, borrowed.
  The code copies them and never writes them or relies on their address (an OSR entry may pass
  a temporary copy). `js_compiled.runCode` pads a short argument list with `Undefined` in a
  copy. Type guards are in the machine code.
- `state`: `js_compiled.stateWords(locals, stackSize)` words, written on every exit.
- `counter`: the context's interrupt counter (`ContextState.interruptCounter`); compiled loops
  decrement it on every back edge like the interpreter and leave through a poll exit at zero.
- `data`: the entry's embedder word (the stress counter of the deopt-stress configuration).
- `env`: the entry's environment word, the JIT's `jit_helpers.CompiledEnv` (the runtime and
  the table of runtime helpers compiled code calls by index, never by address).
- `frame`: what the function runs for (`js_compiled.CompiledFrame`, a C-layout struct of
  pointers, all borrowed for the call): the receiver cell, the `FunctionBytecode` cell, the
  context, the runtime, the closure's captured variable cells and the running scope.
- Result 0: returned; `state` words 0-1 hold the result `ValueBits`, owned (the caller takes
  the count), word 2 the bytecode offset of the `return`. Result 1: deoptimization. Result 2:
  interrupt poll (an exit that is not counted as a deopt).

**Values in compiled code.** Every SSA value has a 16-byte slot; a boxed `value` is a
`ValueBits` in the engine's own layout. Silk does not promise a union layout, so the JIT reads it
from the engine at compile time (`value_layout.probe`: it writes each variant over zeros and over
ones and finds the tag and payload bytes). On the build measured, the tag is the first word's low
byte (Silk writes the whole word, so compiled code reads one byte and writes the word with zero
upper bytes) and the payload the second word; the seven heap variants have consecutive tags, so
"is a heap reference" is one range check. An unexpected layout refuses every function. The
layout is a property of one engine build: a stored artefact must key on it.

What this choice costs later: a compiled function always pays the interpreter frame setup and a
native call, inline call sites lose their inline frame, and once compiled code calls other
functions or can fail it needs either unwind information through generated frames or a
frame in the call-frame region that `unwind` understands (open question 5 of the seam stays
open). It needs no stack map for this milestone because compiled code holds no heap reference.

## 3. Deoptimization

Every guard and every poll exit jumps to a per-exit stub that writes the frame state as
immediates and returns 1 (or 2). The state is:

- `state[0]`: the bytecode offset to resume at, from the start of `FunctionBytecode.code`, at
  the start of the instruction to re-execute (the state before it);
- `state[1]`: operand stack depth;
- then one `ValueBits` (two words) per local and per stack slot, bottom first. Each owns one
  count, which the interpreter frame takes over as it is: the exit stub has already added the
  count of every `dup` slot and of every deferred `move` (below). Arguments are not written: the
  SSA subset never writes one.

`js_compiled.restore` copies those into the interpreter frame's locals, pushes the stack slots,
sets `ip`, and `callInternal` continues into its ordinary `execute` loop, so everything after a
deopt (exceptions, calls, polls, the debugger) is the interpreter's own. The interpreter
re-executes the instruction that failed its guard (an `add` that overflowed makes its
`Float64` there). `enter` is `runCode` (no `Machine`), then `result` or `restore`.

Ownership: the frame's locals still hold what `callInternal` put there (`Undefined`), so writing
over them needs no release. Retains of argument values are deferred to the consumption: the
only owned values the integer subset makes are `retain`s of an argument, which the backend holds
as the argument's bits with no count, `release` emits nothing, and each consumption that hands
one to the engine (a `move` slot, `return`) adds the count inline (`add dword [ref], 1` when the
tag is a heap variant, which is all `HeapCell.retain` does). That is exact because G's verifier
proves every owned value is consumed exactly once on every path. The backend refuses a `retain`
of anything but an argument.

After a deopt the function is kept: the entry counts deopts and the engine unlinks it
(`FunctionBytecode.compiled = 0`) after `deoptLimit` deopts, since a guard that failed that
often will keep failing until feedback recompiles it. The code itself stays with the embedder,
which frees all of it when the session ends. Poll exits do not count. Each `CompiledEntry`
counts runs, deopts and poll exits; the JIT sums them, with compile counts, code bytes and
compile time, for `silkjs-jit-shell --jit-stats`.

## 4. Ahead of time

Machine code is emitted with `asm_x64` and its relocation records only. The compiled function
refers to nothing outside its arguments (the interrupt counter and the data word arrive as
arguments), so its bytes contain no process-local pointer and could be stored and linked
elsewhere. The table index in `FunctionBytecode` is runtime state and never serialized.

Ran (`jit_engine_tests.compiledCodeLoadsIntoAnotherRuntime`): `sum` is lowered in one runtime,
its `Code` (bytes and relocation records) is copied as plain data, and a second, fresh runtime
in the same process checks that its own `sum` has the same bytecode, links the copy at a
different address (`jit_runtime.install`), runs it and deopts it. What the artefact depends on,
all of it data a loader can check rather than identities:

- the bytecode it was translated from (offsets in exit stubs, local and stack counts): a loader
  keys the code by the function's bytecode bytes and counts, as the test does;
- nothing else. The code has no relocation, names no atom, shape, cell or function address,
  and reads the interrupt counter and the stress word from its arguments. The table index and
  the saved `frameCells`/`leaf` are runtime state written at link time.

So for this subset "compile ahead, load later" is the same compiler run at another time plus a
key match. It stops being free when compiled code calls a function, reads a property through a
shape or uses an atom: those would need relocations against symbols the loader resolves per
runtime (the `asm_x64` relocation records and `Code.link`'s symbol table are that mechanism).

## 5. Limits as built

- Leaf functions (`FunctionBytecode.leaf`, run frameless by `js_vm_leaf`) are never compiled:
  leaf runs are not counted, so they never get hot. Linking clears `leaf` anyway (restored on
  unlink) so a linked function is never run frameless.
- A poll exit ends compiled execution for the rest of that call; the interpreter finishes the
  loop (no re-entry, no OSR). The interrupt counter is shared with the interpreter and runs at
  most 10000 back edges, so a compiled loop runs at most that many iterations per call.
- Lowering: `ssa_input.inputOf |> ssa_translate.translate |> ssa_ownership.optimize |>
  ssa_verify.verify |> x64_backend.lower`; the first stage that declines gives the refusal.

## 6. Measurements

All on the cloud container (x86-64 Linux), release builds.

- Interpreter-only cost, no JIT attached (measured, `v8bench.py --instructions`): against a
  4bd0ef29 build, all eight benchmarks 1.000x (largest change crypto +0.02%). Against 6341d15
  with the first hook (a `compiled != 0` test in `enterFrame`): richards 1.010x, raytrace
  1.004x; moving that refusal into the room check brought richards to 1.000x.
- Differential (ran, `differential.py --count 3000 --configs plain,observed,jit,jit-stress,node`
  on d07f63a): 3000 agree, 0 mismatch. `jit`: 994 programs ran compiled code, 978 deopted,
  1166 functions compiled, 32468 refusals, 167839 compiled runs, 8560 deopts, 49 poll exits,
  1025 unlinks. `jit-stress` (threshold 1, a guard fails every 3rd check, never unlinked): 1035
  programs ran compiled code, 905772 runs, 859202 deopts. Refusals in 200 sampled programs
  (ran, `--jit-dump`): opcode outside the subset 1801, a function scope 257, retain of a value
  that is not an argument (backend) 71, closure variables 58.
- Timing (measured on the 7f19981 shell and the 6341d15 engine, wall clock of the whole process, 5 runs each, 2,000,000 calls of `sum(100)`
  from an interpreted loop): plain engine 1013-1328 ms (median 1279), JIT shell without `--jit`
  1250-1336 ms (median 1276), with `--jit` 657-749 ms (median 695). Startup is 5-6 ms for all
  three. Of the 1,999,000 compiled runs, 19,889 left through a poll exit (ran, d07f63a).
- Code size and compile time (measured, `--jit-stats`): `sum` is 989 bytes and took 162-283 µs
  to compile (first compile includes reserving code memory). Over the differential run, 1916
  bytes per compiled function on average and 13.7 µs per hot report, refusals included.

## 7. Calls and frames (milestone 7, workstream H)

Design written before the code of each step; "measured" and "ran" mark what was checked.

### 7.1 Entering compiled code from a call site, before any frame

A call made by the dispatch loop to a linked function no longer goes through `callInternal`.
`enterCallWith` (and `enterKnownCall` for known local functions) still refuses a linked callee
for free (its `frameCells` is the stub sentinel, section 1); the refusal branch, which runs only
when `enterFrame` refused, re-decodes the call out of line (`linkedCall`) and, when the callee is
linked, runs the machine code on the caller's operand cells (`enterCompiled`): no frame, no
`activation.publish`, no debugger activation. The interrupt counter is charged as for an inline
entry.

- **Return**: the operands from the callee's cell up are released and replaced by the result;
  the caller continues at the next instruction, as after a leaf run.
- **Deopt or poll exit**: the exit already carries the whole interpreter state, so only now is a
  frame built: an *inline* frame (`activation.enterResumed`: `enterFrame` with the frame size
  the link saved in `CompiledEntry.frameCells`, not counted, without the `push_this` prologue),
  into which `js_compiled.restore` writes the exit state. The dispatch loop then simply runs that
  frame; its return goes through `finishInline` like any inline call.
- **Skipped**: while instructions are observed, or when the region has no room for the frame a
  deopt would need (checked before running the code, `activation.linkedRoom`), the call falls
  back to `callInline`, which runs the code too (`callCompiled`) and on a deopt continues in a
  base frame: `callInternal` is a wrapper of `callResuming`, whose extra `Resume` argument (a
  constant "none" at every other call site, so the inlined copies fold it away) makes the new
  frame restore an exit instead of starting at offset 0. `callKnown` takes the same argument.

Why the refusal is decoded again instead of passing its values on (measured): passing the
already decoded function, callee, arguments and receiver to the out-of-line path from the
refusal branch kept them live across the inlined `enterFrame` in every call arm and cost the
interpreter-only micro loop below 2.2 percent more instructions; re-decoding cost 0.1 percent.

### 7.2 Leaf functions

A leaf (`FunctionBytecode.leaf`) runs frameless and uncounted from interpreted callers, and
counting leaf runs cost up to 0.9 percent of all instructions (tier-seam.md). The trigger chosen
is "the caller is compiled": a call made by compiled code goes through the runtime call (7.3),
which enters callees through `callInternal`'s `describe` and therefore counts them, leaves
included. A hot leaf called from compiled code is reported, compiled and linked (linking already
clears `leaf`); from then on interpreted callers reach it through 7.1 and compiled callers
through 7.4. A leaf called only from interpreted code stays an interpreter leaf, which is the
cheap case the leaf runner exists for; the interpreter-only cost of this choice is zero.

### 7.3 Calls from compiled code: the generic runtime call

SSA: `call v_function, v_this, (v_args...)` produces an owned `value`, is `mayReenter`, and has
two exits: none for the ordinary path, and a **throw exit** naming the frame state *before* the
call (the call's operands still on the operand stack, as the interpreter holds them while a call
runs). The translator emits it for `call0..3`, `call` and `call_method` (the callee and receiver
come from the operand stack like any other value); every value live across it is either owned,
an immediate, an unboxed `i32`/`bool`, or a borrow of an argument cell.

Backend: the operands are written as `ValueBits` into a stack area (function, this, arguments),
and the code calls the helper `jit_helpers.CALL` (H's index range) through the environment's
table with `(env, frame, area, count, result)`. The helper is ordinary Silk in modules/jit; it
makes the call through the engine's own catching entry (`vm.call`-like, which runs bytecode in
`callInternal`, natives through their class, linked callees through `js_compiled.runCode`
directly) and returns 0 with the owned result written, or 1 when the call threw (the exception
is pending in `RuntimeState.currentException`, exactly where the interpreter leaves it).
Compiled code tests the status and on 1 jumps to the throw exit.

What the rest of the engine sees, case by case:

- **The callee throws.** No unwinding through generated code ever happens: the helper returns.
  The throw exit is a deopt stub returning `EXIT_THROW` (3) with the state before the call. The
  engine restores that state into a frame and, instead of executing, takes the branch the
  `callInternal` loop takes when `execute` fails at the call instruction (`exceptionBoundary`,
  then `unwindFrames`), so handlers in the compiled function (`catch`, `finally`) and the
  release of the call's operands are the interpreter's own. The first version translates no
  `catch`/`gosub`, so every throw leaves the function; the restore is still the general
  mechanism. From a frameless entry (7.1) the engine builds the frame first (base frame through
  `callResuming`, which can fail), so functions that make calls are entered through
  `callCompiled`, never `enterCompiled`.
- **The callee polls, collects garbage, or reenters the engine.** The engine reference-counts
  and never moves objects. Values the compiled frame holds across the call are owned (one count
  each, invisible to the cycle collector's internal-reference subtraction, so they are treated as
  external roots), immediates, or borrows of the frame's argument cells. Argument cells are the
  caller's operands or the frame's own copies; nothing else writes them while the function runs
  (the translator refuses `arguments` and argument writes, `Function.prototype.arguments` is a
  poison pill, and observation runs interpreted code only), so an argument borrow survives a
  call. Any other borrow ends at a `mayReenter` instruction (the ownership pass retains it before
  the call if it is used after). No stack map is needed.
- **The callee reads the stack** (an `Error` captures its stack, a backtrace is built at unwind,
  `Error.prepareStackTrace`). Backtraces walk `RuntimeState.currentStackFrame`. A function entered
  through `callInternal` already has its published `StackFrame`; one entered frameless publishes
  a minimal `StackFrame` record on the native stack for the duration of the run
  (`previous`, `currentFunction`, `mode`, `debuggerId` 0, empty locals, the argument cells), and
  the compiled code writes the call's bytecode offset to its `currentPc` before each call
  (`CompiledFrame` gains a `stackFrame` pointer at its end). The backtrace then shows the
  compiled function at the right line, exactly as the interpreter would.
- **The debugger.** Compiled code never runs while instructions are observed. When a callee
  turns observation on, the compiled caller continues until its next poll or exit; the debugger
  sees it as a frame without locals (the record above) until it deoptimizes.

AOT: the helper is named by its table index; the area, the status and the record offsets are
fixed by the ABI. No per-runtime value enters the code bytes.

### 7.4 Direct calls to a known compiled callee

`js_feedback` records call targets (94 percent of call sites are monomorphic). When a site's
feedback names one closure, the call is lowered as: compare the callee's `FunctionBytecode`
(loaded from the function object) with the bytecode the feedback named (passed through a
per-compilation constant table, never as an address in the code), and when it is linked, call
`js_compiled.runCode`'s machine code directly with the argument area as its `arguments` and a
`CompiledFrame` built in the caller's frame; any other callee takes the generic helper. A
callee deopt returns `EXIT_DEOPT` to the caller's call site, which then runs the helper's
"resume" entry (build the callee's base frame from its exit state and finish it interpreted).

### 7.5 Inlining (design only unless time allows)

A small monomorphic callee is translated into the caller's SSA at the call (its `arg n` are the
call's operands). Every exit inside the inlined body carries two frame states, the caller's
(at the call, its operands on the stack) and the callee's; the engine rebuilds the caller's frame,
then the callee's frame inline above it, so the interpreter returns into the caller normally.
