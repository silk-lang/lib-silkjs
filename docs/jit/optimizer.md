# The optimizer on the baseline tier

Status on 2026-11-21: step 3 of the plan of 20 November. The SSA compiler
(`docs/jit/ssa.md`) now lowers for the baseline tier's frame (`docs/jit/baseline.md`) instead
of the compiled-entry ABI: optimized code is a second body of a function that already has
baseline code, on the same frame, and it leaves into that baseline code. It is opt-in
(`--jit-opt=N` in the JIT shell: optimize a function after N entries of its baseline code).

The gate of the step is Richards at 5x the interpreter on the clock, under 1 exit per 1,000
calls after warm-up, and no function refused for good. Where it stands:

| Richards, fixed work x20, CPU ms (medians of interleaved rounds) | Time | Against the interpreter |
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
| with the guarded chain, loops in inlined bodies, bodies up to 260 bytes | 209 | 3.6x |
| with callees tested by address, values kept in registers, owned cells, bodies up to 460 bytes five deep | 168 | 4.2x |
| with known methods, moved stores, preset closures, shape dispatch | 145 | 4.7x to 5.0x |
| with bodies seven deep, shapes kept over loop turns and shared between copies (this state) | 129 | 5.6x |
| V8 (node, JIT on) | 70 | 10x |

The rows were measured in different rounds against an interpreter between 667 and 861 ms; the
host swings 10 to 15 percent between runs and its runs fall in two clusters, so only rows of
one round compare exactly. The last three rounds, fifteen interleaved runs each:

| Round | Interpreter | Row before the last | This state | V8 | By medians | By fastest runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 (this state without its last two cuts) | 717 (581) | 146 (120) | 133 (110) | | 5.4x | 5.3x |
| 2 | 729 (601) | 145 (119) | 131 (109) | 72 (64) | 5.6x | 5.5x |
| 3 | 723 (591) | 145 (120) | 129 (108) | 70 (59) | 5.6x | 5.5x |

Medians, fastest runs in brackets. The row before the last was 4.7x in an earlier round and
5.0x in these.

Instruction counts do not swing (cachegrind, the whole process, release builds):

| Richards, fixed work x20 | Instructions | Against the interpreter |
| --- | ---: | ---: |
| Interpreter | 10,403M | 1.00x |
| Optimizer at 168 ms (`e9e831f5`) | 2,218M | 4.7x |
| with known methods | 2,118M | 4.9x |
| with moved stores, preset closures, shape dispatch, borrowed copies | 1,883M | 5.5x |
| with bodies seven deep | 1,728M | 6.0x |
| with shapes kept over loop turns and shared between copies (this state) | 1,680M | 6.2x |

The interpreter was 10,428M for the rows before the last; see Known methods for what changed
it.

In this state the long run has 114 call sites inlined, no real call left in the scheduler's
loop, no exit and no step after warm-up, nothing refused, 378 KB of code and 16 to 18 ms of
compiling. All three parts of the gate hold.

Single runs of optimized code swing more than the interpreter's: 24 runs of the 209 ms state
under one address layout took 172 to 288 ms in three clusters, with the same counters and the
same share of samples in every function. The cause is the host, not the code; rows are
medians, and a change is kept on its instruction count, not on one round of the clock.

Code: `modules/jit/src/x64_backend.silk` (frame mode: `lowerOnFrame`, `callOnFrame`,
`stepOnFrame`, `siteSlot`, `stored`), `x64_frame_exit.silk` (the exit helper), `x64_exits.silk`
(exit records and stubs), `ssa_shapes.silk` (shape facts and remembered properties),
`ssa_ownership.silk` (`borrowFields`), `jit_runtime.silk` (`jitTierUp`, `compileOptimized`,
`noteLeft`, `siteShapesOf`, `candidates`), `baseline.silk` (the stubs and tails optimized code uses); in the
engine `js_core_types.silk` (`SiteShapes`, `noteSiteShape`, the watch bits of `ObjectData`) and
`js_compiled_inline.silk` (`siteShapes`, `methodTargets`, `watchHolder`, `knownMethod`). Inlined bodies: `ssa_translate.silk` (`inlineOne`,
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
tail, entry and step tail (`MARK_MOVED`, `MARK_FINISH`, `MARK_STEP_ENDED`), then three per
inline target (its cell, its code, its closure), the owned variable cells, and one per target
for the prototype that holds it. No address is in the code as emitted: the symbols are
resolved when the code is placed.

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
that may change a shape (a call, a helper that can run a getter, setter or conversion).
Richards went from 430 to 371 ms and the optimized code from 85,001 to 61,943 bytes.

The pass walks the blocks twice. In the first walk a loop header starts with no shape, since
its back edge is not known yet; in the second it keeps what the code before the loop and the
end of every turn agree on. That a value is an object is kept in the first walk already: a
value never stops being one, so a header takes it from the blocks before the loop when the
only edges not walked yet are back edges (the header dominates their blocks,
`ssa_verify.dominators`).

What is known of an object is kept under the first value that was that object, with `retain`
copies and repeated reads seen through: a test of the inlined `this` proves the shape for the
caller's receiver and for every other copy, the ones made before the test too.

A poll changes no shape. What it runs when its counter is out is the host's interrupt callback
and the report of a hot function (`js_interrupts.handle`), which run no JavaScript (a rule for
hosts, stated there: a callback that has to run script needs the optimizer off); the report
compiles baseline code only. So the shapes a loop's turns agree on hold at its header, and the
scheduler's loop tests the shape of `this` once before the loop instead of once a turn. This
rests on where a prototype starts being watched (see Known methods): only in the optimizer's
compile at a function's entry, which is inside a call, where every fact has died. Optimized
code made from a poll, as on-stack replacement would, must not start a watch there.

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
helper and the step behind the tests.

A holder one further up, the prototype's own prototype (DeltaBlue's constraints read
`output`, `input` and `recalculate` from `BinaryConstraint.prototype` through
`EqualityConstraint.prototype`), is lowered too: the receiver's version fixes the prototype,
the prototype's version (`SiteShape.firstKeys`, read when the code is compiled while the
pair's epoch still holds) proves it lacks the name and fixes the holder, and the holder's
version fixes the slot. Such a site used to be refused whole, and read through the field
cache's one entry and the helper; DeltaBlue took 113M instructions less with it. Holders
further up, getters and absent properties are still not lowered, and such a site reads
through the helper.

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
twelve blocks on (512 for a copy of an argument or of a value the function owns, which no
store, call or poll in between can free: the receiver and the arguments of an inlined call are
such copies, and a body with inlined calls of its own is many blocks): the receiver, the method closure and the inlined `this` of an inlined call
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

A call whose target is known and short (460 bytes of bytecode, 24 blocks, seven bodies deep,
64 sites a function; the embedder looks up at most 128 candidates, six levels down) is its callee's body in the caller's code, behind a test of the callee
(`check.callee`: an object of the closure class with that bytecode). The body has no frame.
What makes that sound is what happens when the body has to stop being inlined.

The depth was three, then five, then seven: at five the scheduler's loop still made 0.87
million real calls a run from bodies at the fifth level, each about 70 instructions through
the stub and the prologue. At seven none is left, the code grew from 368 to 380 KB, and of the
other seven V8 benchmarks only Splay inlines more (33 sites for 27).

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

**Shape dispatch.** The chain's tests ask which closure the read returned, after a read that
already tested the receiver's shape against each recorded pair. When nothing but the fused
callee tests and their branches stands between the read and the arms (`shapeArms`), the read
does both at once: it loads the receiver's shape version, and for each arm compares it with
the shape that arm's method was recorded for (`Function.inlineShapes`), tests the watched bit
of the prototype that holds the method, puts the closure constant in the value's slot and
jumps into the arm's body. A shape of no arm, or a prototype no longer watched, falls to the
general read and the tests, which are still there. An argument worked out between the read
and the call (`o.run(i & 15)`) is code in between and keeps the tests; the scheduler's
`this.currentTcb.run()` and a call whose arguments are at hand dispatch.

An arm whose method is known for one receiver shape starts with `check.shape` of the
receiver, which the dispatch has just proved: the dispatch jumps past it, also when the
arm's `inline.frame`s (no code) stand before it (`armShapeAt`). In DeltaBlue's plan loop that
test ran every turn before.

Larger bodies without the chain were slower (342 ms against 239): the last target of
`task.run` was inlined behind a `check.callee` inside `run` inside `schedule`, the test failed
for three tasks in four, and each failure left `schedule` in baseline code for the rest of its
activation, which is one loop of ten thousand turns. See on-stack replacement under Open.

## Exact targets and known methods

**Exact targets.** A target the embedder knows as one closure (`ssa.TARGET_EXACT`) is tested by
the closure's address, a symbol of the code, instead of by class and bytecode. The closure is
kept alive for the code (`inline.keepClosure`).

**A function's own methods.** `Strength.stronger(a, b)` reads a method that is an own
property of the object a variable holds, which no site cache entry names as a target (it
is not a prototype hit). When the read comes straight after the `get_var`, the compile
reads the variable through the function's closure (`js_baseline.variableMethod`) and takes
the closure the property holds as an exact target, tested against the callee as any other.
A read off `this` inside such a method (`this.weaker` in `Strength.weakestOf`) is not
resolved yet.
The prologue passes its closure to the optimizer for this (`jitTierUp`'s third argument,
null for a known local function). On DeltaBlue this inlined 23 more calls and took 77M
instructions off.

**Known methods.** A method read through the prototype cost about twenty instructions: the
receiver's shape, the prototype's shape, the slot's two words, then the callee test. When the
prototype is watched, the read is the receiver's tag, its shape version, its exotic bit and
one byte test of the prototype, and the closure is a constant: no load from the prototype and
no callee test (`knownRead`, `TARGET_KNOWN`, `Function.inlineSites`).

- `watchHolder` marks a plain prototype object (`OBJECT_ROLE_WATCHED`) and gives it a shape of
  its own with a new version, so that no store key filled before can prove a store to it. The
  field caches that name it as a direct prototype by the old version are moved to the new one.
- Every write of a slot of the object (`ObjectData.setSlot*`) and every change of its shape
  clears the bit. The compiled test reads the bit each time, so code compiled for the method
  falls to the general read from the first write on, and the callee test after it decides.
- An object is watched at most once in its life (`OBJECT_ROLE_WAS_WATCHED`): after a write,
  store keys may hold its version, and a second watch would need a third version.
- A store compiled code makes with a constant key tests the shape version, which the watch
  changed, so it leaves to the interpreter's store, which clears the bit. A store whose shape
  test a fact removed would not: hence the rule under Shape facts about where a watch starts.
- The receiver's shape names its prototype (as the interpreter's cached read relies on), so
  another prototype, an own property of that name or a prototype in between is another shape
  and misses the first test.

**Preset closures.** Where the callee test follows the read at once and the closure has no
other reader than the inlined frame, the exits and its release (`presets`), the value's slot
is written once at function entry. The known path then writes nothing and counts nothing; the
general path gives the count it took back once the test has passed; the release is no code;
an exit that names the value takes a count of its own for the interpreter's cell.

**What the interpreter pays.** The watch is a test of the roles byte in the slot writers the
interpreter does not reach by a key: `setSlot`, `setSlotUnchecked` and the list accessors.
The others have none:

- a store proved by a key: the inline key of a store instruction (`setSlotKeyedUnchecked`),
  and the site entry `define_field` fills for itself (`setSlotKeyed`). A key is filled only
  after a tested store, and a watched object's version is in no key filled before its watch;
- an object that is being made (`setSlotFresh`, `setSlotFreshUnchecked`, `setSlotsFresh`:
  constructor plans, literals, new arrays), and one being destroyed (`takeSlotsLast`);
- a change of shape, which tests the bit under the prototype mark it tested already
  (`noteShapeChange`, `swapAdd`): only a marked prototype is watched.

A leaf function's store (`js_vm_leaf.store`) probed the shape by name and so needed the test;
it now goes by the instruction's key first, as the interpreter's own `put_field` does, and
probes only when the key misses. That is fewer instructions than before the watch.

Interpreter instruction counts, fixed work, against the build before the JIT work began and
against the one before the watch (`e9e831f5`):

| Benchmark | Since before the JIT work | Since before the watch |
| --- | ---: | ---: |
| Richards | +0.02% | -0.15% |
| DeltaBlue | +0.16% | -0.21% |
| Crypto | +0.01% | +0.01% |
| RayTrace | +0.21% | +0.05% |
| EarleyBoyer | +0.12% | 0.00% |
| RegExp | +0.20% | +0.15% |
| Splay | +0.27% | +0.07% |
| NavierStokes | +0.01% | 0.00% |

The rule is 0.5 percent. With the test in every writer EarleyBoyer was at +0.55 percent since
before the watch and Splay at +0.49. One caution for later measurements: the dispatch loop's
code on DeltaBlue's paths comes out 0.19 percent (1.48M instructions) longer or shorter from
one build to the next after edits elsewhere in the loop, so a single benchmark that moves by
that much with no change on its path is the compiler's layout, not the change.

`modules/jit/tests/baseline/t40.js` goes through every way a method stops being the function
compiled code knows: assignment, `defineProperty`, a getter, deletion, `Object.assign`,
`Reflect.set`, a swap between two prototypes, an own method on the receiver, another
prototype, one in between, a method that replaces itself while its caller's loop runs.

## Array push in place

A method call under the name of Array.prototype's push whose callee is that native
(`arrayCall`) pushes in place when it can (`pushInPlace`, as `arraySupport.pushInto` does):
the receiver is a fast Array, extensible and not watched, of a fresh array's shape
(`js_compiled_inline.arrayShapeVersion`, in `Function.arrayShape`: `length` is its writable
slot 0, the realm's Array.prototype its prototype), the prototype still leaves element
reads to arrays' own elements (`ObjectData.isStandardArrayPrototype`), the length is the
element count and the elements have room for one more. The element takes a count of its
own and a heap value clears the plain flag (`FieldLayout.elementMeta`, `elementPlain`,
`standardPrototype`). About 40 instructions where the helper and `pushOne` were about 100;
a push that needs more room goes to the helper and the engine as before.

## Watched records

`var Direction = new Object()` with three numbers in it, read as `Direction.FORWARD` by
`input()` and `output()` in every turn of DeltaBlue's plan, is a record: an ordinary plain
object of at most eight data properties, each an int32, a boolean, null or undefined,
whose prototype is a plain object without one. When a compile finds one in a variable cell
of a target's closure (`jit_runtime.watchRecords`, `js_compiled_inline.cellRecord`), it is
watched as prototypes are: it takes the prototype role, whose only cost is epoch bumps, so
that every path that ends a prototype's watch ends its own (`js_shapes.noteShapeChange`
tests that role), and `watchHolder` gives it a shape of its own. No interpreter path
changed.

A keyed read whose inline key names a slot of a record's shape (as it is, or as it was
before the watch: keys filled earlier hold that) is `check.shape` of the record's shape,
which names the record alone while it is watched, `check.watched` (the watched bit, two
instructions) and the slot's value as a constant: an unboxed i32 for a number, so the
comparison after it is with an immediate. A changed record leaves at the test, and the
next compile reads it again. `Jit.records` keeps what each compile found; a record no
longer watched (`recordHolds`) gives no constants.

On DeltaBlue x20 this took 83M instructions out of optimized code. A read of
`Direction.FORWARD` and its `==` went from about 26 instructions to 19: the cell read and
the two guards are what is left.

## Values in registers, cells and stores

- **Fresh values.** A read leaves its value's two words in rax and r9 as well as in the slot
  (`setFresh`, `isFresh`). The next instruction takes them from there when no code and no jump
  target came between: a tag test, an unboxing, the object of the next read, the value of a
  store. A read from the slot right after its store would wait for the store.
- **Owned cells.** A variable of an enclosing scope whose cell is detached and initialized
  (`ssa.VAR_OWNED`) is read by the cell's address, a symbol of the code: two loads.
- **Moved stores.** A store followed by the release of the value it stored takes the value's
  own count: no count up, no release (`movedInto`). Taking the old value's last count is out
  of line (`OUT_PUT_LAST`), and the old value's words stay in registers for it.
- **Dead stores.** A backward liveness pass over the bytecode (`ssa_translate.livenessOf`, one
  bit per local, for code with at most 64 locals and no catch, finally or references to
  locals) tells, at each instruction, which locals some path still reads. A `put_loc` or
  `set_loc` to a local no path reads again stores undefined: `var c = list[i]; c.run()` is a
  `set_loc` whose value stays on the stack, and the store's retain, the release of the old
  value and the local's loop parameter all go. The pass runs on the function's own code and
  on each inlined body. An exit names undefined for such a local, which nothing reads.
  Two other uses of the same liveness measured no gain on DeltaBlue: releasing a local where
  it dies (the release only moves), and taking the local's count at its last `get_loc` (on
  a path that reads it last, while another path keeps it, the merge gets a new parameter
  that costs more than the retain saved).

## Leaving too often

`jitFrameLeft` counts guard failures per function and remembers the bytecode offsets
(`Jit.leftAt`). At 8 failures, when that is more than 1 per 1,000 entries, the function's
table slot goes back to its baseline code and its count is set to 8 times the entries it had
before. The next compilation gets the remembered sites as `doubleSites`, which the translator
already knew how to widen: arithmetic to doubles, a store to a helper call, an equality to
the general one, a call to one that is not inlined. The wait tops out near sixteen million
entries and there is no last compilation: no function keeps its baseline code for good.

Every such round compiles a function again, and on DeltaBlue at `--jit-opt=20` compiling
is about 8 percent of the run. Two kinds of site are widened from the first compilation,
where an exit is certain or likely:

- A `+` with a string constant operand (`"v" + i`) is the engine's concatenation at once.
  It used to leave as an int32 add, then again as a double add, before it was stepped: two
  recompiles of the function per site.
- A field store whose inline key is an add key (its last run added the property) is the
  helper call with a step behind it, which adds in place first as `put.field` does. A
  constructor run for several subclasses (`BinaryConstraint` through
  `superConstructor.call`) adds from starting shapes the site's memo does not cover, and
  `put.field` left for each.

A method call the function's code has not run yet when it is first optimized (no shape
recorded for its read, the field cache entry another site's: `jit_runtime.unseenCalls`)
stays a call in that code for good, since no exit there teaches a later compile its
target. The first optimization waits for it, at most twice (`UNSEEN_WAITS`), four times
longer each time, while baseline code runs it: in DeltaBlue, `addConstraintsConsumingTo`
runs `c.isSatisfied()` and `coll.add(c)` only once a variable has a constraint besides
the one that determines it.

A method read whose value is held through an inlined call's arms (`this.take(d.out(), k)`
with `d.out()` a chain) reaches the call as the parameter of the block where the arms
meet, and of the blocks of each arm's body. `readOf` follows such parameters to the one
value every edge passes (`sourceOf`), so the call still finds its target.

DeltaBlue x60 went from 79 compilations, 29 unlinks and 234 exits to 67, 18 and 144. The
exits left are mostly method calls inlined for one receiver shape, whose `check.shape`
fails for a subclass seen later: going on with the call there would save the recompile
but keep the call for good.

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

- `modules/jit/tests/baseline/*.js` (42 scripts) through
  `modules/jit/scripts/baseline_scripts.py <shell>`: each script's output and exit status under
  baseline and under the optimizer at three thresholds against the interpreter's. `t30` and
  `t31` cover shape misses and recompiles, `t32` steps and throws inside them, `t33`
  constructors that keep or throw with object arguments and sites with one to six receiver
  shapes, `t34` borrowed fields with stores and other owners around them, `t35` exits after effects in
  inlined bodies, `t36` calls made by inlined methods (throws, stack traces, depth), `t37`
  loops in inlined methods, `t38` chains of two to four targets, late callees of other kinds,
  arms that leave or throw, chains two bodies deep, `t39` exact targets and owned cells, `t40`
  known methods (above), `t41` shape dispatch over four classes with every change of `t40`,
  receivers the site never saw and a scheduler loop, `t42` loops whose object changes shape or
  prototype in a turn, and a prototype that starts being watched while a loop stores to it,
  `t50` watched records changed under inlined reads (a write, a getter, a delete, an add,
  the variable set to another object), `t51` reads whose holder is the prototype's
  prototype while the chain changes (the middle prototype gains the property, the holder's
  is replaced, the middle prototype's prototype changes, a receiver shadows it), `t52` a
  function's own methods called through a variable while they are replaced, deleted, made
  a getter and the variable is set to another object.
- `silk test` in `modules/jit`: 94 tests.
- `modules/engine/scripts/differential.py --configs plain,baseline,opt,opt-eager`.
- For a change in the engine (the watch bits, the slot writers): `python3 scripts/check.py`
  in `modules/engine` after its release build, and the interpreter's instruction counts on
  the eight V8 benchmarks against the build before the JIT work (see Known methods). Its
  native suite passes 566 of 568: `forInAllocationFailuresReleaseInputSnapshotsAndVisitedState`
  and `forInFailSafeAndFastCompletionAreNotPermanentlyLatched` fail on main too (0c137cf1),
  since own-only for-in.
- The eight V8 benchmarks at fixed work with `--jit-opt=20 --jit-threshold=20 --jit-stats`:
  each must print its `done` line. The long Richards run caught a count bug the scripts and
  the differential did not.

Instruction counts of optimized code by SSA operation: run the dev shell under
`valgrind --tool=callgrind --dump-instr=yes` with `--jit-dump`, and join the counts with the
dump's `jit: optimized code at` addresses and `jit: optimized map` offsets. A dev shell emits
the same code as a release one, but its own total includes a slow compiler: compare the
optimized code's count between dev shells, and whole-process totals between release builds.

## Where the time is

Instructions of Richards in this state, by SSA operation, in the optimized code (1,423M of the
run's 1,680M): field reads 39 percent, field stores 18, unboxing 8, branches 6, releases 6,
variable reads 6, jumps 4, element reads 2. A turn of the scheduler's loop with the task it
runs is about 335 instructions and 30 ns, against V8's 17 ns.

What a turn still pays for:

- Every value read from a field is stored to its slot, because any exit after it may name the
  slot. An int32 read to be unboxed is two stores and a tag test from memory before the
  register has it (113M a run for the unboxings, more for the stores).
- Some arms of the task's body read or write an element, which is not known to keep shapes:
  what was proved of other objects before such an arm is tested again after it.
- The four-way dispatch is about 21 instructions a call (49M), the known read of
  `isHeldOrSuspended` 12 (46M), a field store 9 to 16.
- A bitwise operation on registers is three instructions where one would do, and a comparison
  whose result is passed to the next block is made into a value and tested again.

## Open

In the order they are planned:

1. On-stack replacement into optimized code. An exit in a long loop leaves the activation in
   baseline code until it returns, and a function entered once is optimized only at its next
   entry. A watch must not start at a poll (Shape facts).
2. Unboxed reads: an int32 field read whose only reader unboxes it, without the slot stores
   (the exits after it name the int32 instead).
3. Element reads and writes that leave on a miss instead of calling a helper, so that shapes
   survive them.
4. Shape dispatch when code stands between the read and the call; a preset closure for a read
   that is not directly before its test.
5. Feedback for guards inside inlined bodies. A failure is recorded at the outer function's
   call instruction, so the recompile stops inlining the call instead of widening the one site
   in the body.
6. Compile time and code size: the scheduler's function is 150 KB of code, and four functions
   carry most of 380 KB.
7. `SERVICE_QUICK` for literals; holders more than two prototypes up in `SiteShapes`.
