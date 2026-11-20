# The optimizer on the baseline tier

Status on 2026-11-20: step 3 of the plan of 20 November, in progress. The SSA compiler
(`docs/jit/ssa.md`) now lowers for the baseline tier's frame (`docs/jit/baseline.md`) instead
of the compiled-entry ABI: optimized code is a second body of a function that already has
baseline code, on the same frame, and it leaves into that baseline code. It is opt-in
(`--jit-opt=N` in the JIT shell: optimize a function after N entries of its baseline code).

The gate of the step is Richards at 5x the interpreter on the clock, under 1 exit per 1,000
calls after warm-up, and no function refused for good. Where it stands:

| Richards, fixed work x20, CPU ms (median of 7 interleaved rounds) | Time | Against the interpreter |
| --- | ---: | ---: |
| Interpreter | 798 | 1.00x |
| Baseline tier | 595 | 1.34x |
| Optimizer, first frame mode | 526 | 1.5x |
| with loop turns counted toward tier-up | 430 | 1.9x |
| with the shape pass | 348 | 2.3x |
| with steps and constructor calls on the frame (this state) | 345 | 2.3x |
| V8 (node, JIT on) | 81 | 9.9x |

The first three optimizer rows were measured in earlier rounds against an interpreter at 789 to
801 ms; the host swings 10 to 15 percent between runs, so only rows of one round compare
exactly. In this state Richards has 16 functions optimized, none refused, no exit and no step
after warm-up. The exit and refusal parts of the gate hold; the clock does not yet.

Code: `modules/jit/src/x64_backend.silk` (frame mode: `lowerOnFrame`, `callOnFrame`,
`stepOnFrame`), `x64_frame_exit.silk` (the exit helper), `x64_exits.silk` (exit records and
stubs), `ssa_shapes.silk` (shape facts), `jit_runtime.silk` (`jitTierUp`, `compileOptimized`,
`noteLeft`), `baseline.silk` (the stubs and tails optimized code uses).

## Frame mode

Optimized code enters through the baseline tier's shared prologue (`STUB_PROLOGUE`) and builds
the same frame record under rbp. r12 is the BaselineEnv and r13 the runtime, as in baseline
code; the register pool is rbx, r14 and r15. The SSA values' slots are a spill area below the
frame's cells. The frame's local cells stay undefined and its operand cells unused until the
code hands the frame over.

- Calls go through `STUB_CALL_KEEP` and `STUB_CALL_METHOD_KEEP`: the callee, receiver and
  arguments are lent to the operand cells the interpreter would have them in, the stub calls
  baseline or optimized code directly (or the engine for a native), and the owned result comes
  back in rax:rdx. Only rbx lives across a call.
- `new` goes through the engine's `SERVICE_CONSTRUCT` on the same cells, as baseline code does.
- Returns go through `STUB_LEAVE`.
- Helpers of the older ABI (`jit_helpers`) are reused on slow paths through a CompiledFrame
  built on demand.

The code's symbols are the shared stubs, then the function's baseline `moved` tail, `finish`
tail, entry and step tail (`MARK_MOVED`, `MARK_FINISH`, `MARK_STEP_ENDED`), then the inline
targets. No address is in the code.

## Exits

An exit is a record among the code bytes (`jit_exit_state` has the format) and a two
instruction stub. The function's one common stub dumps the pool registers and calls
`jitFrameExit`, which writes the interpreter state the record describes into the frame's
cells: locals, operands, and parameters when the function writes them. Then the frame is what
baseline code has at that instruction:

- A failed guard (`HOW_DEOPT`) and a declined call (`HOW_DECLINED`) jump to the baseline
  code's `moved` tail with `js_baseline.moved(pc, depth)`. Baseline code continues there when
  the instruction is in its resume table (loop targets); otherwise the interpreter finishes the
  activation, and hands loops back to baseline code at their back edges.
- A call that threw, a poll that threw and a poll that turned observation on go to the
  `finish` tail, where the interpreter takes the frame.

An exit that is always taken (the translator's `sideExit`, used for `throw`) leaves with
`HOW_DECLINED`: no speculation failed.

## Tier-up

Linking baseline code sets the function's count to N entries. The shared prologue counts down
and reports the function to `jitTierUp` when the count runs out; baseline back edges count
down too, to a floor, so a function that is entered once and loops is optimized at its next
entry. There is no on-stack replacement into optimized code yet. `compileOptimized` relinks
the function's table slot; the construct and resume entries stay baseline's.

## Shape facts

A field site whose inline key held a shape version when the function was compiled is lowered
against that version and slot as constants, and a miss is an exit: no helper answers it, so
what the test proved stays true after it. `ssa_shapes.analyze` runs forward over the blocks
and gives each site what earlier sites and tag checks proved of its object: that it is an
object (no tag test) and that it has the key's shape (no shape test). A fact dies at anything
that may change a shape (a call, a helper that can run a getter, setter or conversion), and a
loop header starts with none. Richards went from 430 to 371 ms and the optimized code from
85,001 to 61,943 bytes.

## Leaving too often

`jitFrameLeft` counts guard failures per function and remembers the bytecode offsets
(`Jit.leftAt`). At 8 failures, when that is more than 1 per 1,000 entries, the function's
table slot goes back to its baseline code and its count is set to 8 times the entries it had
before. The next compilation gets the remembered sites as `doubleSites`, which the translator
already knew how to widen: arithmetic to doubles, a store to a helper call, an equality to
the general one, a call to one that is not inlined. The wait tops out near sixteen million
entries and there is no last compilation: no function keeps its baseline code for good.

## Steps

A site that left once must not leave again, and an instruction without a template must not
keep a function out of the optimizer. Both are served by one mechanism, `stepOnFrame`: the
interpreter runs that one bytecode instruction on the frame (`STUB_STEP`, the baseline tier's
own fallback) and the optimized code goes on.

1. `jitFrameExit` with `HOW_STEP` writes the state of the instruction's exit into the cells,
   each value with a count of the cells' own. The code keeps what it owns.
2. `STUB_STEP` runs the instruction.
3. When the code goes on, `HOW_STEPPED` gives the cells' counts back, moves the instruction's
   first value to the code's slot and leaves the local cells undefined again. Other values of
   a multi-value instruction stay in their cells for `call.result` to take.
4. When the step ended the activation or moved the frame to a handler of its own,
   `HOW_STEP_LEFT` drops what the code owned and the code jumps to the baseline step tail.

What is stepped:

- Every `call` flagged generic (`typeof`, `in`, `delete`, object, array and regexp literals,
  closures, for-in and for-of, and the rest of `ssa_translate.genericOpcode`). Frame mode used
  to refuse these functions.
- A field read that left before (`FIELD_STEPS` on `get.field`): the inline test and the helper
  first, the step for what the helper declines (a primitive's property, a getter). Its result
  is always owned.
- A store and an equality that left before (`SITE_PUT_FIELD`, `SITE_EQUAL`): the helper
  first, the step for a setter, a new property, a coercion.

A step costs a state write and an interpreter entry. Literals in a hot optimized function are
slower this way than through baseline's `SERVICE_QUICK`; that path is open work.

## Checks

- `modules/jit/tests/baseline/*.js` (32 scripts) through
  `modules/jit/scripts/baseline_scripts.py <shell>`: each script's output under baseline and
  under the optimizer at three thresholds against the interpreter's. `t30` and `t31` cover
  shape misses and recompiles, `t32` steps and throws inside them.
- `silk test` in `modules/jit`: 94 tests.
- `modules/engine/scripts/differential.py --configs plain,baseline,opt,opt-eager`.

## Where the time is

Samples of Richards in this state: 79 percent in optimized code, 13 percent in the shared
stubs (calls, prologues, returns), 6 percent in the engine's prototype read behind method
lookups whose shared site cache entry was taken by another site. The hottest body, the
scheduler's loop with `isHeldOrSuspended` inlined, is flat: its cost is the volume of code per
operation, not one slow spot.

## Open

In the order they are planned:

1. Method lookups without the shared site cache: receiver shape and holder shape as constants.
2. Exits inside inlined bodies after an effect, through the callee's baseline resume entry
   (`js_baseline.resumeOf`); calls inside inlined bodies; a guarded chain for a call with a few
   targets (Richards' `task.run`). Seven Richards call sites are not inlined for the first
   reason alone.
3. Code volume: values kept in registers between a read and its test, borrows across blocks,
   slow paths out of line.
4. On-stack replacement into optimized code; `SERVICE_QUICK` for literals.
