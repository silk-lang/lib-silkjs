# Loops: polls, loop hotness and on-stack replacement (milestone 7, workstream I)

Built on [compiled-entry.md](compiled-entry.md) and [tier-seam.md](tier-seam.md). Statements
here are design unless marked measured or ran; numbers are in the last section.

## The problem

Before this, a compiled function's loop left for good at its first interrupt poll (the
interpreter finished the loop), and a function entered rarely that loops for long was never
reported hot, because only entries are counted. Most of the time of loop-heavy code
(navier-stokes, crypto, any benchmark's main loop) therefore stayed in the interpreter.

## One mechanism for all three

Everything happens at the interrupt poll on a backward jump, which the plain dispatch loop
already takes at most every `JS_INTERRUPT_COUNTER_INIT` (10000) back edges and calls. The
poll branch of each back-edge arm (ten arms in `js_vm.silk`: `if_false`, `if_true` and their
8-bit forms, `goto`, `goto8`, `goto16`, `if_nullish8`, `if_not_nullish8`, the fused loop
prefix) calls `js_compiled_osr.atPoll` after `interrupts.handle`, with the frame written
back. Nothing is added outside that branch, so the interpreter-only fast path is unchanged.
The observed loop never calls it (`!observe` is a constant there).

`atPoll` looks at the running frame, base or inline (`current` in `executeLoop`):

1. **Loop hotness.** No code linked (`FunctionBytecode.compiled == 0`): `js_hotness.loopPoll`
   reports the function at once, the way an exhausted entry budget does (parked in
   `hotPending`, budget `u32.MAX`, polls forced, delivered at the next poll). A poll that lands
   on a back edge of a frame means that frame has been looping; one is enough evidence, the
   compile is cheap, and a function already reported (budget at or above 2^31), or with no
   handler set, or while another function waits, is skipped. A refused function is not
   reported again (its budget stays parked), unless K's recompile rule resets it.
2. **On-stack replacement.** Code linked: if the entry has OSR code for the frame's pc and
   operand stack depth, run it on the live frame (below). After a poll exit, reset the
   counter, run `interrupts.handle` with the frame whole again, and enter again. So a long
   loop stays compiled across polls (step a of the brief) and the handler (debugger,
   hot-function delivery, compile and link) never sees a half-written frame.

A normal compiled entry that leaves through a poll exit (from `callInternal`) resumes in the
interpreter at the loop header with the counter at 0, so the interpreter polls at its next back
edge and enters the OSR code there: one interpreted iteration per call, not the rest of the
loop.

## The OSR artefact

One artefact per loop header (`ssa_translate.translateOsr`, `x64_lower.lowerOsr`), on the
unchanged compiled-entry ABI:

- **Inputs.** The function takes `argumentCount + localCount` arguments: the frame's arguments,
  then its locals (local `i` is argument `argumentCount + i`). The engine writes each as an
  argument word (Int and Bool unboxed, anything else named by its position, kind 6). The entry
  block makes each local an owner of the frame's value with a `retain` of that argument, exactly
  as `get_arg` does, so the ownership pass, verifier and backend need nothing new.
- **Only code reachable from the header** is translated (`shapeAt` walks from the header with an
  empty stack), so code before the loop never matters.
- **Side exits.** An opcode outside the subset does not refuse the artefact: the block ends
  with an exit there that is always taken (`sideExit`: an `unbox.i32` of `undefined`). Cold
  paths in or after a loop (a property write on the last iteration, the code after the loop)
  then cost nothing; a hot one costs one entry and one exit per poll until the deopt limit.
- **Headers** are the targets of backward jumps (`loopHeaders`, a linear decode). Only depth 0 is
  compiled; the engine checks the frame's depth before entering.

`jit_runtime.compileHot` compiles the loop headers of every function it is handed, next to the
normal entry. `CompiledEntry` gains `osr`/`osrCount` (an embedder array of `OsrEntry { pc,
depth, code }`, never moved while linked) and `osrRuns`/`osrDeopts`. A function whose normal
entry is refused but has OSR code is linked with `js_runtime.linkOsr`: the entry's `code` is
null, `js_compiled.enter` returns at once for it, and inline calls are not redirected (no
`frameCells` swap), so its calls keep interpreting and only its loops run compiled.

## Entering and leaving a live frame (`js_compiled_osr`)

Unlike a normal entry, the frame's locals hold owned values while the code runs.

- **Deopt and poll exits** (`restoreLive`): every exit word is materialized first (kind 6 is a
  retained copy of the named argument or local, read from cells the code never wrote), then each
  local that changes is written and its old value released. A word naming the local's own cell
  leaves it alone. Operand stack slots are pushed; the stack was empty at entry.
- **Return.** The backend now also writes the return instruction's pc to `state[1]` on
  `EXIT_RETURNED` (a normal entry ignores it). The engine pushes the result (for `OP_return`)
  or drops it (`OP_return_undef`) and sets the pc there, and the interpreter executes the return.
  The frame's locals still hold their entry values, which that return releases. Base frames and
  inline frames (`finishInline`) need nothing of their own, and construct frames keep their
  return rule.
- **Deopt limit.** OSR deopts are counted apart: at `deoptLimit` the entry's `osrCount` is set to 0
  (OSR off for that function); the normal entry stays linked.

## Ahead of time

The OSR artefact is the same compiler run with a different entry, keyed by the bytecode and the
header pc. It has no relocation and names no runtime address (the interrupt counter and stress
word are arguments, as before). `OsrEntry` tables are runtime state, never stored.

## Limits

- Depth-0 headers only (for-in and for-of keep their iterator on the stack; those loops use
  opcodes outside the subset anyway).
- A loop in a generator, async function or module body is never entered (the translator refuses
  them; `vm.resume` frames would need their own transfer).
- Loop hotness reports at the first back-edge poll in a frame. Calls also charge the counter, so a
  function that only calls in a loop can be reported by a poll on its back edge too; that is
  still a function spending its time in a loop.
- What the hot loops of navier-stokes and crypto need is outside this workstream: element reads
  and writes, closure scope reads (`get_scope0`), bit operations, doubles (see Measurements).
