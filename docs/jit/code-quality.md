# Code quality passes

What the JIT does to the SSA form between the ownership pass and the verifier, and what the
backend does beyond lowering one instruction at a time. The compile cost side is
[compile-cost.md](compile-cost.md); the form and its rules are [ssa.md](ssa.md).

`ssa_opt.pipeline` is the one entry: `ssa_ownership.optimize`, then each pass below, in this
order. Every pass lives in its own file (`ssa_opt_<pass>.silk`), has one bit in
`ssa_opt.PASS_*` and one shell flag that clears it, so a wrong answer or a slowdown is pinned
on a pass by turning it off. The verifier runs after the pipeline as before: a pass that
breaks a rule turns into a refused function, not into wrong code.

| Pass | File | Off with |
| --- | --- | --- |
| Reads without counts | `ssa_opt_borrow.silk` | `--jit-no-borrow` |
| Hoisting | `ssa_opt_hoist.silk` | `--jit-no-hoist` |
| Exits name the unboxed number | `ssa_opt_unboxed.silk` | `--jit-no-unboxed` |

## Reads without counts

`get.elem`, `get.length`, `get.var` and `get.scope` answer an owned value: the read takes a
count and a `release` drops it. For `s = s + a[i]` that is two tag tests around the element
and two more around `a.length`, on values that are numbers.

When the value is released in the block that read it and nothing between could let go of
what holds it, the read borrows: its result becomes `borrowed`, the read takes no count and
the `release` goes. This is the rule `ssa_ownership.borrowFields` has for `get.field`, with
what each read needs kept away:

| Read | Borrows from | Ends at |
| --- | --- | --- |
| `get.elem a, i` | `a`, or what `a` borrows from | a call, a `put.elem` (the store's slow path releases the element it replaces, and a string is freed at once), the release of `a` |
| `get.length a` | the same | a call, the release of `a` (a length is a number, or the length of a string `a` keeps) |
| `get.var k`, `get.scope k` | the binding (`RootKind.Binding`, printed `borrowed(binding)`) | a call, `put.var`, `put.scope` (a captured variable and a global can be one cell), `put.field` (a global is a property of the global object) |

An element or a length read from an object that itself borrows from a binding borrows from
the binding too, and ends at both lists.

"A call" is any instruction not listed in `ssa_opt_borrow.quiet`: the instructions known not
to run the program's code or free a holder. An instruction a stream adds later ends every
borrow and stops hoisting in its loop until it is listed there.

The helpers follow: `get_var` and `get_scope` take a flag (bit 31 of the index, bit 29 of
the site) and do not retain; `get_elem_borrowed` (helper 121) gives its count back, and
answers 0 when the element is a cell only the read holds (nothing would keep it alive for a
borrower), so the code deoptimizes there. Exits write a borrowed value as `dup`, which
takes the count the interpreter needs.

## Hoisting

A loop is a header block with a back edge from a latch, the block the translator makes to
poll and jump back. An instruction in the loop whose operands are all defined outside it,
and whose answer nothing in the loop can change, moves to a new block on the loop's one
entry edge. One call moves instructions out of one loop level; the pipeline calls it twice.

What moves:

- `unbox.*`, `check.tag` and the exiting arithmetic (`add.i32` and the like) of invariant
  operands, when their block runs on every iteration (it dominates every latch). A guard the
  loop would not have reached must not fail in front of it.
- `get.length`, `get.field`, `get.var` and `get.scope` whose result is a borrow, under the
  same condition, in a loop that holds nothing that could change the answer: a call,
  `put.elem` (for a length: an append), `put.field`, and for bindings `put.var` and
  `put.scope`. An owned result stays: its `release` would have to move too.
- Arithmetic and comparisons that cannot fail, from anywhere in the loop.

**The exit of a moved guard.** A guard that fails in front of the loop resumes the
interpreter at the loop's header, before the first iteration. Its state is the state at the
header as the entry edge carries it. The latch's `poll` already names the state at the
header as the back edge carries it; the entry state is built from it slot by slot:

- a slot whose block parameter the header kept takes that parameter's argument on the entry
  edge. Parameters are matched by `ValueInfo.state`, the place among the block's parameters
  the translator gave each one (locals, then the operand stack), which stays true when
  passes remove other parameters. Matching by value would be wrong: two locals can hold one
  value at the latch and different values at entry.
- any other slot lost its parameter because it holds one value around the loop; the latch's
  slot names it. If that value is defined inside the loop the pass gives the loop up.

A loop with more than one entry edge, or no `poll`, is left alone. So is the loop of an
inlined body (docs/jit/inlining.md), and an instruction of an inlined body stays in its loop:
it may read the frame `inline.frame` builds there.

**Code entered at the loop.** In an OSR artefact (docs/jit/osr.md) the entry edge comes from
the entry block, so the front block sits between the entry and the header and a moved guard
exits with the values the entry brought (`ssa_tests.goldenHoistedInLoopEntry`).

**Recompilation.** A deopt at a hoisted guard is recorded at the header's offset, which
says nothing about which instruction to widen. So a loop whose header is among the offsets
earlier code of the function deoptimized at (`jit_recompile` sites) is not hoisted from:
the guard stays in the loop, the next deopt names the instruction, and the compilation
after that widens it.

**Counters that enter boxed.** A header parameter the loop unboxes as an i32 on every
iteration and passes back as `box.i32` of a number (an index, a counter, an accumulator)
would still be a boxed value if its entry value is no box, typically an argument: the
ownership pass unboxes only parameters fed by boxes. So the pass puts that unbox on the
entry edge too, with the moved guards' exit, and has the edge pass `box.i32` of its
number; the ownership pass then runs again (`ssa_opt.pipeline`) and unboxes the parameter,
which ends the boxing at the latch and the unbox at the top of each iteration
(`ssa_tests.argumentCounterUnboxedOnEntry`; Crypto's `am3` carries `i`, `j` and `c` so).
An entry value the code owns (an argument copied into a local, as in Crypto's
`bnpDRShiftTo`) is no longer passed on, so the front block releases it after its last exit
(`ssa_tests.ownedCounterReleasedOnEntry`, `tests/baseline/t68.js`). Without that release
the verifier refused bnpDRShiftTo, montReduce and bnpFromString from the change that brought
these unboxes in until this one: montReduce ran its baseline code, and half of `am3`'s calls
went through the baseline call stubs.
The entry unbox takes a Float64 holding an exact int32 too (`ssa.UNBOX_EXACT`, x64_backend):
a value of double arithmetic that is an integer runs the loop as an Int instead of failing
in front of it. What it refuses exits at the header and costs the one more compile above.
The latch's state names a box's number where the latch passes the box (an exit writes
`int x` for `box.i32 x`), and the entry state maps such a slot through the box.

**Locals a block does not read.** An edge passes a local as `undefined` when no path from
its target's offset reads the local before writing it (the translator's liveness), and its
value holds no count (a number, an immediate, a borrow: an owned value would need a release
on the edge alone). A temporary written at the top of each iteration (`var l = a[i]`) was a
header parameter for its exits only, boxed at every latch; a loop counter dead after the
loop was passed to the exit block. Both go.

**Boxes for one exit edge.** A loop's exit edge often passes its numbers boxed, to a block
whose parameters stay boxed because it is also reached from in front of the loop. Those
boxes ran on every iteration, between the loop's compare and its branch, which then could
not branch on the compare's flags. `sinkBoxes` moves a box whose one reader is an argument
of one edge of a branch onto that edge, in a new block (Crypto's `am3`: five boxes and the
compare's setcc, store and test per iteration).

## Array checks in front of the loop

An element access (`get.elem` with `k` 0, `put.elem`) of an Array the loop does not
define tests the object's tag, its class and its fast flag on every turn: seven
instructions before the index test. `ssa_opt_hoist` puts one `check.array` per such Array
on the loop's entry edge, with an exit of its own at the header, and marks the accesses
trusted (`Inst.trusted`): they load the object, compare the index with the count and leave
where it is not below it. Their helper never runs, but a trusted store of a counted value
below the count, which keeps the Array fast.

Nothing else in the loop may change what kind of object the Array is: no call and no
stepped read (they run the program's code), no store of a field or a binding, and every
element store is trusted (an untrusted store's helper may append past the end, and an
append far enough out ends the fast kind; it could be this Array under another name). The
access must run on every turn and its site must never have left compiled code. With
recorded kinds (code made off a baseline frame) the site saw fast Arrays alone; on a
baseline frame, where no kinds are recorded, it saw no keyed reads (ELEMENT_ORDINARY).

A `check.array` that fails (a typed array, a string, `arguments`) leaves at the header
with a record that says so (`jit_exit_state.CODE_ARRAY_CHECK`). `jit_runtime.noteLeft`
remembers the header's pc with `ssa.SITE_ARRAY`, and the next compile trusts nothing in
that loop but keeps the rest of its hoisting, where a failure of the other hoisted guards
keeps all of them in the loop. `tests/baseline/t67.js` runs such loops on arrays, typed
arrays, strings, `arguments`, frozen, holey and getter-holding arrays, past the end and
with stores that append.

A borrowed copy of the Array (`this_array` read from a local the loop's front block
copied) is checked as what it copies: one `check.array` per object.

Crypto's `am3`: 143 instructions an iteration where there were 164; Crypto at scale 4,
3.26G instructions where there were 3.48G. At scale 20 the optimizer takes 1,019 ms (V8:
325), where before this and the fragile registers it took 1,256.

## Repeated element reads

`a[i]` read twice in one block, with nothing between that could change an array (only
arithmetic, compares, boxes, unboxes and tag tests), reads the same element: the second read
and its `unbox.i32` take the first's (`ssa_opt_unboxed.repeatedReads`,
`ssa_tests.repeatedElementReadOnce`). Only a plain read (`k` 0, whose misses exit: no getter
runs in it) of a borrowed result; the array is matched through borrowed copies of it, so
`this_array[i]` read once from the local and once from the copy the loop's front block made
is one read.

## Exits name the unboxed number

After `u = unbox.i32 v` passed, `v` is an Int and `u` is its number. An exit later in the
block that writes `v` to the interpreter's frame writes `int u` instead: the same value. `v`
then has no reader past its unbox, which is what lets the backend load an element's number
straight from the array (below). Only a borrowed `v` (an owned one is moved by the exit, and
the ownership rules count that), and only exits one instruction uses: an exit shared with an
instruction in front of the unbox (the front block of a hoist) runs before `u` exists.

## In the backend

- **Constant operands are immediates.** `and`, `or` and `xor` with a constant, and
  shifts by a constant, read it as an immediate (`sar eax, 28`); such a shift needs no
  `cl` and no save of `rcx`; `x >>> c` with a count that is not 0 has no sign test, as its
  result is below 2^31. `mul.i32` by a positive constant is `imul` with an immediate and
  no -0 test. A `const.i32` takes no register (x64_regalloc): its readers take it as an
  immediate, or from its slot, so the three integer registers of code on a baseline frame
  go to values.

- **Two more registers on a baseline frame.** Code on a baseline frame had three integer
  registers (rbx, r14, r15). rsi and rdi join them as fragile registers (`Pool.fragile`):
  only a value whose interval holds nothing but gentle instructions (integer arithmetic,
  compares, constants, boxes and unboxes of numbers, jumps and branches, none of which
  touch rsi or rdi or call out) takes one. The temporaries of a loop's arithmetic go there,
  the callee-saved three to the values that live across element accesses and polls. On
  Crypto's `am3` loop: 164 instructions an iteration where there were 168 (Crypto in all:
  3.47G instructions at scale 4, from 3.57G). Keeping rsi and
  rdi over the slow paths of element accesses and polls (so longer values could take them
  too) measured worse, 167, and is not done.

- **`mul.i32` tests for -0 out of line.** The product is taken from the second operand's
  register or slot (`imul eax, [slot]`); a zero product jumps to a piece after the blocks
  that ors the operands, still in their places, and leaves when that is negative, so a
  nonzero product runs `imul`, `jo`, `test` and a branch not taken. Operands known never
  to be negative (a constant that is not, an `and` with one, `>>>` by a nonzero constant)
  need no test at all.
- **A store of an immediate skips its heap test.** `put.elem` of a value that is
  `Own.Imm` (a boxed number, undefined, a boolean) does not test whether the new value is
  counted.
- **`add.i32` and `sub.i32` in place.** When the result takes the first operand's register
  the operation runs there, two instructions where there were four. The exit state reads
  the operand, so the overflow jump goes to a short piece after the blocks that undoes the
  operation and then jumps to the exit.
- An Array's length is a number: its inline read took a count it never needed.
- **One test for an Array.** The flags byte and the 16-bit class of an object share a
  32-bit word, so "class Array and fast" is one masked compare, where it was two loads and
  two compares.
- **`get.elem` followed by its unbox.** When the element's only reader is the `unbox.i32`
  next to it (and that unbox's own exit), an Int goes from the array to the number's
  register and the unbox is skipped; anything else is copied to its frame slot as before
  and the unbox refuses it. No exit changes.

## What it is checked with

- `ssa_tests.goldenBorrowedElements`, `goldenHoistedLength`, `goldenHoistedInLoopEntry`: the
  form after the passes.
- The differential (modules/engine/scripts/differential.py):
  - flavour `aliases`: the array is the only owner of its strings and arrays, a store
    replaces the element just read (the same slot or another) before the value is used
    again, and the length changes inside the loop that reads it;
  - flavour `hoists`: a loop reads a field, a global, a length or a typed array element that
    does not change, and then it does, at one iteration or at every one: the shape through a
    call (`__poke`: add, delete and re-add, a getter, a double) or a store, the binding, the
    array's length, the typed array's buffer (`__cut`: detached, shrunk, grown);
  - flavour `conversions`: conversions of loop-invariant values on -0, NaN, doubles and
    non-numbers, with the sign of zero in the checksum;
  - the long loops read an array's length and a global's field, in code entered at the loop;
  - configurations `jit-no-hoist` and `jit-no-borrow` run without one pass each, so a
    mismatch is pinned on a pass. `jit-stress` takes every guard's exit in turn, the hoisted
    ones included, so a wrong entry state shows as a wrong checksum.

## Measured

Callgrind instructions for the whole run over the kernel's units (`--jit`; x86-64, one
process, `--smc-check=all-non-file`), on the kernels of the scorecard. Before is the tree
without this work (for typed-array: both passes off, with the doubles stream's inline
element code). V8 is node 22 run the same way, less an empty script's run; both columns
include their warm-up.

| Kernel | Before | After | Without hoisting | Without borrowing | V8 | After / V8 |
| --- | --- | --- | --- | --- | --- | --- |
| array-sum (`s + a[i]` over 1000 ints) | 78.2 | 29.3 | 46.2 | 67.2 | 13.1 | 2.2 |
| sum-long (counted loop, one branch) | 15.4 | 11.4 | 11.4 | 11.4 | 16.5 | 0.7 |
| nested (`s + i * j`, two loops) | 26.6 | 24.6 | 24.6 | 24.6 | 13.1 | 1.9 |
| doubles (`s * 0.999 + i * 0.25`) | 20.4 | 18.3 | 18.3 | 18.3 | 17.3 | 1.1 |
| typed-array (Float64Array multiply-add) | 373.7 | 182.0 | 301.8 | 377.7 | 16.3 | 11.2 |

## What is left

- **array-sum, 29 against 13.** Each `a[i]` still tests the tag of `a`, its class and fast
  flag (seven instructions), compares the index with the count (three) and jumps over the
  code for the other kinds of object (one). A `check.array` guard in front of the loop and
  an element read that trusts it need the element kind each site saw (now recorded in js_feedback): without it a loop over a typed array would deoptimize at
  its entry. The bounds check then goes when the loop's bound is the hoisted length.
  Monomorphic typed-array sites now try the recorded class before the Array path.
- **typed-array, 178 against 16.** Every element crosses a frame slot as a boxed double, and each access
  tests the class and the count again. The recorded kind now selects the typed arm. Keeping an unboxed double in the
  arithmetic path and safely reusing the view checks are the next candidates.
- **nested, 25 against 13.** `mul.i32` spends eight instructions on overflow and -0; the
  ranges of `i` and `j` (both counted up from 0) would drop the -0 test.
- A loop end costs four instructions (the conditional jump to the latch, the poll's two,
  the jump back); placing the latch after the loop's last block saves one.
- Hoisted instructions are not merged with equal ones that already ran before the loop
  (array-sum reads `a.length` in the pre-test and again in the front block).
