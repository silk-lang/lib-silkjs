# Inlining

A call from compiled code costs far more than the few instructions a small callee runs:
the call area, the frame, the entry ABI, the exit state and the return. Inlining translates
the callee's bytecode into the caller's SSA function at the call site, so the call
disappears and the callee's values flow into the caller's as ordinary SSA values (an
unboxed `i32` argument stays unboxed, a returned comparison stays a `bool`).

This page describes what is built. The files are `ssa_translate.silk` (the translator's
inline mode), `ssa.silk` (`Exit.drops`, `Inst.frame`, `check.callee`, `inline.frame`),
`x64_backend.silk` (their lowering), `jit_runtime.silk` (candidates, symbols) and the
engine's `js_compiled_inline.silk` (what the engine tells the compiler).

## 1. Which calls

A `call_method` whose function operand is the value of a `get_field2` of the same code, when
the embedder found a target for that `get_field2`:

- the interpreter's site cache entry for the `get_field2` is current (its site, a prototype
  key, the runtime's shape epoch) and the slot it names holds a bytecode closure;
- the closure's function is a plain function (`FunctionKind.Normal`) of the caller's realm,
  with no closure variables and no scope of its own, at most 96 bytes of code;
- its code is in the translator's subset and has no branch (it runs straight to one
  `return`).

The target is a snapshot taken when the caller is compiled (`js_compiled_inline.methodTarget`):
what the site called last. It is a hint. The code checks the callee's identity every time
(section 3), so a wrong hint costs a deoptimization, never a wrong result.

Candidates nest: a target's own `get_field2` sites are looked up too, two levels down, and
the translator inlines at most three bodies deep and sixteen sites per function.

A call site at whose pc compiled code deoptimized before (`jit_recompile`'s sites) is not
inlined again: the next compilation makes an ordinary call there.

`--jit-no-inline` turns all of it off.

## 2. The SSA

At the call site, with the function value `f`, the receiver and the arguments on the
translator's operand stack:

```
check.callee f, k        exit: the caller's state before the call
inline.frame f, k
...the callee's instructions, `frame k + 1`...
```

then the call's operands are released and the body's return value is pushed in their
place. `k` indexes `Function.inlineTargets`.

Inside the body the translator's locals and operand stack are the callee's (locals start
undefined). The differences from translating a function's own code:

- `get_arg n` is the caller's operand `n` (retained when it holds a count, as the
  interpreter's `get_arg` does), or undefined past the arguments passed; the fused forms that
  read an argument cell read that operand;
- `push_this` is the receiver operand, guarded to be an object as in a function's own code;
- `return` ends the body with its value; the callee's locals and leftover operands are
  released first;
- a call inside the body is inlined in turn or fails the attempt.

`Inst.frame` tells the backend whose `CompiledFrame` an instruction reads: field sites,
variables, scopes and atoms of an inlined body belong to the callee's code, closure and
scope. `inline.frame` builds that frame on the native stack exactly as a direct call builds
one (compiled-entry.md 7.7): the closure's bytecode cell, captured cells and scope, the
caller's realm and runtime, and the callee's code address.

## 3. Guards and exits

Every guard inside an inlined body, and `check.callee` itself, exits to **the caller's state
before the call**: the call's pc, the caller's locals and its operand stack with the call's
operands still on it. The interpreter then makes the call itself. No engine structure
changes: exit codes, the state words and the call block are as before.

That is sound only if the body has changed nothing the interpreter's own run of the callee
would change again. So:

- an operation is either on the translator's list of operations without effect
  (`withoutEffect`: constants, arithmetic, guards, reads, counts) or it is an effect
  (`put.field`, `put.var`, `put.scope`, `put.elem`, `call`, and anything added later until
  it is put on the list);
- when a guard is requested after an effect of the same attempt, the attempt fails. An
  operation's own guard comes before its own effect, so a body may end in one store.

A failed attempt is rolled back (`Function.mark` and `rollback`: the instruction, value,
exit and slot lists are truncated; an inlined body makes no block) and the site is
translated as an ordinary call.

Counts: a body owns values the interpreter frame will not receive (its retained copies of
arguments, the results of its reads). An exit lists them after the frame's slots
(`Exit.drops`, `Function.slotCount`). The exit writes the frame's slots first, then
releases each drop slot whose mode is `move`; a drop slot the ownership pass turned into a
borrow or an unboxed value has another mode and is ignored. The verifier counts a `move`
drop slot as the one move of its value.

`check.callee f, k` passes when `f` is a bytecode closure (object tag, class) whose
FunctionBytecode cell is target `k`'s. The cell's address reaches the code as relocation
symbol `2k` (`2k + 1` is the first byte of its code, for the frame): `Code.link` fills both
when the code is installed, so stored code holds no address. The runtime retains each target
until it is destroyed (`js_compiled_inline.keep`), so the address cannot come to name
another function.

## 4. What is not done yet

- Callees with branches (the body becomes blocks; the continuation takes the result as a
  parameter).
- A guard after an effect: an exit that names two frames, so the interpreter resumes inside
  the callee.
- Targets of plain calls (`get_var` of a global function), natives, constructors.
- A site with more than one target falls back to a deoptimization and an ordinary call on
  recompilation, instead of a second guarded body or a call on the miss path.
