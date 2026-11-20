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
| with steps and constructor calls on the frame | 345 | 2.3x |
| with method reads against recorded shapes | 322 | 2.4x |
| with shorter tag tests and counts, slow paths out of line | 314 | 2.6x |
| with repeated reads as copies | 308 | 2.8x |
| with borrows across blocks, copies without code, fused tag tests | 269 | 3.2x |
| with exits and calls inside inlined bodies | 237 | 3.2x |
| with the guarded chain, loops in inlined bodies, bodies up to 260 bytes (this state) | 209 | 3.6x |
| V8 (node, JIT on) | 75 | 10x |

The rows were measured in different rounds against an interpreter between 709 and 861 ms; the
host swings 10 to 15 percent between runs, so only rows of one round compare exactly (the
last round, nine interleaved runs: interpreter 709 then 755 over six more, the row before 237,
this state 209, V8 75). In this state the long run has 23 functions optimized, none refused,
59 call sites inlined, 2.66 million calls left of 7.95 million, no exit and no step after
warm-up. The exit and refusal parts of the gate hold; the clock does not yet.

Single runs of optimized code swing more than the interpreter's: 24 runs of this state under
one address layout took 172 to 288 ms in three clusters, with the same counters and the same
share of samples in every function. The cause is the host, not the code; rows are medians.

Code: `modules/jit/src/x64_backend.silk` (frame mode: `lowerOnFrame`, `callOnFrame`,
`stepOnFrame`, `siteSlot`, `stored`), `x64_frame_exit.silk` (the exit helper), `x64_exits.silk`
(exit records and stubs), `ssa_shapes.silk` (shape facts and remembered properties),
`ssa_ownership.silk` (`borrowFields`), `jit_runtime.silk` (`jitTierUp`, `compileOptimized`,
`noteLeft`, `siteShapesOf`), `baseline.silk` (the stubs and tails optimized code uses); in the
engine `js_core_types.silk` (`SiteShapes`, `noteSiteShape`) and `js_compiled_inline.silk`
(`siteShapes`, `methodTargets`). Inlined bodies: `ssa_translate.silk` (`inlineOne`,
`callChain`, `inlineExit`), `x64_backend.silk` (`callInBody`, `bodyRecords`, `calleeFlags`),
`x64_frame_exit.silk` (the frames of an exit), and the engine's `js_baseline.Inlined`,
`callInlined` and `resumeInlined`.

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
  Its arguments own a count in their cells: a planned constructor moves them into the object
  and leaves the cell undefined, so the code releases the cells after the call on both ways
  out.
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

## Recorded shapes

A cached field site (`get_field2`: method reads, reads through the prototype) has no key in the
bytecode. The engine records, for each such site, the shapes its site cache entries were filled
for: `SiteShapes` in a table the embedder lends (`CompiledTable.siteShapes`, 2,048 entries, lent
only with the optimizer on), written where a cache miss fills an entry. An entry holds up to
four pairs: the receiver's shape version and slot for an own property, or the receiver's
version and the holder's version and slot for a property of the direct prototype.

`siteSlot` lowers the read against the pairs as constants: the receiver's shape, then for a
prototype pair the holder's shape (the receiver's shape fixes its prototype, as the
interpreter's own cached read relies on). A miss is an exit; a site that left once keeps the
helper and the step behind the tests. Deeper chains, getters and absent properties are not
recorded, and such a site reads through the helper.

## Remembered properties

`ssa_shapes` also remembers which value holds a property of an object: after a read or a store
of `o.p`, the value read or stored. A later plain read of the same property of the same object
is that value again (`Shapes.sameAs`). A store of a property forgets every entry of that name
and remembers its own value; anything that may run other code clears them all. The pass walks
the blocks twice: the second walk gives a loop header what the code before the loop and the
end of every turn agree on.

## Copies and borrows

In frame mode a copy has no slot of its own (`Emitter.stored`). A `retain` and a repeated read
are read from the slot of their source: the source's definition dominates the copy, and a slot
is written only where its value is defined, so the source's slot holds the copy's bits wherever
the copy is read. What the copy owns stays its own: an owned copy is one count on the source's
slot, a borrowed copy is no code.

`borrowFields` lets a field read or a copy borrow until its release in a later block, at most
twelve blocks on: the receiver, the method closure and the inlined `this` of an inlined call
are released where the body's paths meet, and none of the three takes a count now. A call, a
poll or a way back to the definition ends the attempt. A store crossed by the borrow leaves the
code before it would take a field's last count, and that alone was not enough: another owner of
the same object, counted by that test, could let go later inside the borrow. A release of
another value after such a store now refuses the borrow, unless the value is the one the last
store put in its field. The pass runs first to last and then last to first while either finds
any: a read borrows from its object's root once the object borrows, and a read's window is free
of the releases of later reads once those are borrows.

A `tag.is` whose only reader is the branch after it is that branch's flags (`fusedTag`).

## Inlined bodies

A call whose target is known and short (260 bytes of bytecode, 24 blocks, three bodies deep,
32 sites a function) is its callee's body in the caller's code, behind a test of the callee
(`check.callee`: an object of the closure class with that bytecode). The body has no frame.
What makes that sound is what happens when the body has to stop being inlined.

**Leaving.** An exit before the body's first effect restarts the call in baseline code: the
state of the call instruction is written and nothing is lost. After an effect (a store, a
count the caller cannot give back, a call) the body must be finished, not restarted. Such an
exit names its bodies (`ssa.ExitFrame`: the body's method, argument count, locals, operand
depth and instruction). `jitFrameExit` writes one `js_baseline.Inlined` record per body into
the frame's leave area and answers `INLINED | depth`; the stub calls the engine's
`SERVICE_INLINED`, which finishes each body in an interpreter frame from the innermost out
(`callInlined`, `resumeInlined`), pushing each result where its caller's instruction expects
it. Baseline code continues the outer function at `SYMBOL_MOVED`.

**Calls.** A call inside a body (`callInBody`) writes a bare frame record per body
(`FRAME_BARE_INLINED`: closure, receiver, instruction) on the frame chain, so a stack trace,
a throw and the collector see the frames the interpreter would have, and calls with rbp at the
innermost record. A throw unwinds through the records to the caller's handler.

**Loops.** A body may loop. Every exit inside a body that loops is a frames exit, since an
earlier turn may have had an effect; the latch block takes the body's held values, locals and
stack parameters; the loop's poll writes the body records, with the loop's target as the
innermost instruction, before it calls `SERVICE_POLL`.

**Shape facts.** `ssa_shapes` finds the recorded shapes, names and keys of a site in a body
through the chain of inline targets (`inlinedSite`), at any depth. Before that only bodies one
level deep had them, and reads two levels deep went through the helper: 20 percent of the
code and a visible share of the time.

## The guarded chain

A method call whose site saw a few receiver shapes with different methods (Richards'
`this.task.run`, four tasks) is a chain: for each known target a test of the callee and its
body, then a plain call for anything else, and the paths meet with the result. Nothing leaves
when the callee is the fifth one.

The targets come from the site's recorded shapes. `SiteShapes` keeps, with each shape pair of
a prototype property, the holder object and the engine's shape epoch at the time. At compile
time `inline.methodTargets` reads the method out of each holder whose epoch is still the
current one and keeps the distinct closures of the function's realm, four at most. The holder
is not counted by the table. The epoch makes that sound: it moves whenever a prototype object
is destroyed (`js_gc.destroyObject`, one byte test per destroyed object), so an entry that
could name freed memory is an entry of an older epoch. An entry the cache refreshed after an
epoch change is noted again (`noteRefreshed`).

In SSA the test is `is.callee v, k` (a bool; fused into the branch after it), each hit block
inlines its target without a `check.callee`, and the last miss block makes the call. A target
that cannot be inlined (too long, or the limits) leaves its callee to the plain call; a chain
with no arm at all is a plain call. A site with one target and no other shape keeps the single
`check.callee` form, whose miss is an exit.

Larger bodies without the chain were slower (342 ms against 239): the last target of
`task.run` was inlined behind a `check.callee` inside `run` inside `schedule`, the test failed
for three tasks in four, and each failure left `schedule` in baseline code for the rest of its
activation, which is one loop of ten thousand turns. See on-stack replacement under Open.

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

- `modules/jit/tests/baseline/*.js` (38 scripts) through
  `modules/jit/scripts/baseline_scripts.py <shell>`: each script's output and exit status under
  baseline and under the optimizer at three thresholds against the interpreter's. `t30` and
  `t31` cover shape misses and recompiles, `t32` steps and throws inside them, `t33`
  constructors that keep or throw with object arguments and sites with one to six receiver
  shapes, `t34` borrowed fields with stores and other owners around them, `t35` exits after effects in
  inlined bodies, `t36` calls made by inlined methods (throws, stack traces, depth), `t37`
  loops in inlined methods, `t38` chains of two to four targets, late callees of other kinds,
  arms that leave or throw, chains two bodies deep.
- `silk test` in `modules/jit`: 94 tests.
- `modules/engine/scripts/differential.py --configs plain,baseline,opt,opt-eager`.

## Where the time is

Samples of Richards in this state (24 runs, 209 ms median): 85 percent in optimized code, 5
percent in baseline code, 9 percent in the engine and the compiler (compiling is 18 ms of a
run, three times what it was before the bodies grew). `schedule` with its loop, the task
control block's `run`, three of the four task `run` methods and what they call inlined is 44
percent; the handler task's `run`, too long to inline and reached through the chain's call, is
19 percent. A turn of the scheduler's loop is about 49 ns against V8's 18.

The loop's code is straight but long. Every value read from a field is stored to its slot and
read back by the next instruction (a tag byte from the slot, the payload from the slot), which
puts a store and a load on every step of the pointer chains the benchmark is made of. A global
read is eleven instructions, a method read through the prototype about twenty with its callee
test, and the four-way read of `task.run` repeats the prototype test in each arm before the
chain tests the callee three times.

Earlier measurements still hold: the time follows the number of instructions, and the counts
more than their share (taking six count updates out of the loop's short path gave 9 percent).

## Open

In the order they are planned:

1. Code volume: values kept in registers between a read and its test, a chain that tests the
   receiver's shape once instead of the shape and then the callee, global reads.
2. On-stack replacement into optimized code. An exit in a long loop leaves the activation in
   baseline code until it returns, and a function entered once is optimized only at its next
   entry.
3. Feedback for guards inside inlined bodies. A failure is recorded at the outer function's
   call instruction, so the recompile stops inlining the call instead of widening the one site
   in the body.
4. Compile time and code size: `schedule` is 60 KB of code with a 6.5 KB frame, and four
   functions carry most of 251 KB.
5. The interpreter's cost of the epoch change in `destroyObject` (a byte test per destroyed
   object) has to be measured against the 0.5 percent rule.
6. The call path: 70 instructions from the site through the stub and the prologue to the body.
7. `SERVICE_QUICK` for literals; deeper prototype chains in `SiteShapes`.
