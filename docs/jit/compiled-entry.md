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
extern "C" fn(arguments: *const u64, state: *mut u64, counter: *mut i32, data: ?*mut u8) -> u32
```

- `arguments`: one word per declared parameter, in the frame-state word encoding below: an
  `Int` is kind 1 with its bits, any other value is kind 6 naming its own parameter cell.
  Unboxing is in the engine; the type guard is in the machine code.
- `state`: `2 + locals + stackSize` words, written on every exit.
- `counter`: the context's interrupt counter (`ContextState.interruptCounter`); compiled loops
  decrement it on every back edge like the interpreter and leave through a poll exit at zero.
- `data`: the entry's embedder word (the stress counter of the deopt-stress configuration).
- Result 0: returned; `state[0]` is the result as a frame-state word (an owned value: kind 6
  hands the caller a retained copy of that argument). Result 1: deoptimization. Result 2:
  interrupt poll (an exit that is not counted as a deopt).

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
- then one word per local and per stack slot (bottom first). A word is a kind in bits 32..39
  and a payload in bits 0..31: 0 leave the cell as it is, 1 `Int` (payload), 2 `Undefined`,
  3 `Uninitialized`, 4 `Bool` (bit 0), 5 `Null`, 6 a retained copy of parameter `payload`
  (G's `dup` of an argument). Arguments are not written: the SSA subset never writes one.

`js_compiled.enter` writes those into the interpreter frame's locals, pushes the stack slots, sets `ip`, and `callInternal` continues into its ordinary
`execute` loop, so everything after a deopt (exceptions, calls, polls, the debugger) is the
interpreter's own. The interpreter re-executes the instruction that failed its guard (an `add`
that overflowed makes its `Float64` there).

Ownership: int code holds only immediates, and the frame's locals still hold what `enterFrame`
put there (`Undefined`), so writing an immediate over them needs no release; kind 6 is the only
retain. Boxed values (G's `Move`) need a kind that transfers a count; added when the backend
produces them.

After a deopt the function is kept: the entry counts deopts and the engine unlinks it
(`FunctionBytecode.compiled = 0`) after `deoptLimit` deopts, since a guard that failed that
often will keep failing until feedback recompiles it. The code itself stays with the embedder,
which frees all of it when the session ends. Poll exits do not count. `RuntimeState` keeps
runtime-wide counters (runs, deopts, poll exits, unlinks) that `silkjs-jit-shell --jit-stats` prints.

## 4. Ahead of time

Machine code is emitted with `asm_x64` and its relocation records only. The compiled function
refers to nothing outside its arguments (the interrupt counter and the data word arrive as
arguments), so its bytes contain no process-local pointer and could be stored and linked
elsewhere. The table index in `FunctionBytecode` is runtime state and never serialized.
