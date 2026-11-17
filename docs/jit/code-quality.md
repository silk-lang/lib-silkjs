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

A loop with more than one entry edge, or no `poll`, is left alone.

**Recompilation.** A deopt at a hoisted guard is recorded at the header's offset, which
says nothing about which instruction to widen. So a loop whose header is among the offsets
earlier code of the function deoptimized at (`jit_recompile` sites) is not hoisted from:
the guard stays in the loop, the next deopt names the instruction, and the compilation
after that widens it.

## In the backend

- **`add.i32` and `sub.i32` in place.** When the result takes the first operand's register
  the operation runs there, two instructions where there were four. The exit state reads
  the operand, so the overflow jump goes to a short piece after the blocks that undoes the
  operation and then jumps to the exit.
- **Typed arrays.** `get.elem` and `put.elem` on anything but a fast Array called the engine
  (about 100 instructions with the register saves). A function that has such an instruction
  now holds two routines (`x64_typed.silk`), emitted once after its blocks and called with a
  near call: what `quickRead` and `quickWrite` do for Int8 to Int32, Uint8, Uint16 and
  Float64 elements (and Uint32 stores), with an Int or, for Float64, a double value. Each
  answers 0 for everything else (another object, an index past the count, which is 0 once
  the buffer is detached, a shared buffer, the other kinds, a clamped or converting store),
  and the code then calls the engine as before.
- An Array's length is a number: its inline read took a count it never needed.

## What it is checked with

- `ssa_tests.goldenBorrowedElements`, `goldenHoistedLength`: the form after the passes.
- The differential's `aliases` flavour (modules/engine/scripts/differential.py): the array
  is the only owner of its strings and arrays, a store replaces the element just read (the
  same slot or another) before the value is used again, and the length changes inside the
  loop that reads it. `jit-stress` takes every guard's exit in turn, the hoisted ones
  included, so a wrong entry state shows as a wrong checksum.

## Measured

Callgrind instructions for the whole run over the kernel's units (`--jit`; x86-64, one
process, `--smc-check=all-non-file`), on the kernels of the scorecard. V8 is node 22 run the
same way, less an empty script's run; both columns include their warm-up.

| Kernel | Before | After | Without hoisting | Without borrowing | V8 | After / V8 |
| --- | --- | --- | --- | --- | --- | --- |
| array-sum (`s + a[i]` over 1000 ints) | 78.2 | 35.2 | 52.2 | 69.2 | 13.1 | 2.7 |
| sum-long (counted loop, one branch) | 15.4 | 11.4 | 11.4 | 11.4 | 16.5 | 0.7 |
| nested (`s + i * j`, two loops) | 26.6 | 24.6 | 24.6 | 24.6 | 13.1 | 1.9 |
| doubles (`s * 0.999 + i * 0.25`) | 20.4 | 18.4 | 18.4 | 18.4 | 17.3 | 1.1 |
| typed-array (Float64Array multiply-add) | 462.6 | 188.0 | 307.7 | 383.6 | 16.3 | 11.5 |

## What is left

- **array-sum, 35 against 13.** Each `a[i]` still tests the tag, the class and the fast
  flag of `a`, compares the index with the count, copies the element to a frame slot and
  tests its tag again. Splitting `get.elem` into a hoistable `check.array`, a bounds check
  and a typed load needs a value type for the element storage; the bounds check then goes
  when the loop's bound is the hoisted length.
- **typed-array, 188 against 16.** Three reads and a store through the routines cost about
  35 instructions each, and every element crosses a frame slot as a boxed double. The same
  split, with the element kind from feedback (js_feedback records no element sites yet),
  would make each read a load.
- **nested, 25 against 13.** `mul.i32` spends eight instructions on overflow and -0; the
  ranges of `i` and `j` (both counted up from 0) would drop the -0 test.
- A loop end costs four instructions (the conditional jump to the latch, the poll's two,
  the jump back); placing the latch after the loop's last block saves one.
- Hoisted instructions are not merged with equal ones that already ran before the loop
  (array-sum reads `a.length` in the pre-test and again in the front block).
