# JIT P1: engine tier seam

Historical task brief recovered verbatim on 2026-11-17. This is an archive, not an instruction to launch or restart work. Paths, measurements, task status, and operational rules may be outdated. See [the recovery index](../../README.md) and the newer coordination handoff before using it.

Source: <t3-thread://v2/df925567-22cf-40cf-9a2c-46fb2bd05b71/3d78b1cc-ea92-4e4d-9957-9b496b4a1270>, activity position 72, item `turn-item:provider:claudeAgent:native-item:toolu_01UEQu8XVwYb7jAjTRknmJJ1`.

---

You are working in a git worktree of SilkJS: a JavaScript engine written in the Silk language (a native port of QuickJS) plus a Node-compatible runtime. Layout: `modules/engine` (package `silkjs`), `modules/runtime`. Read the root `README.md` first. Silk is a systems language with ownership, effects (`effect fn`, `run`), `unsafe`, generics with interface bounds, `static if`, and attributes such as `@inlineAlways`, `@inlineNever`, `@cold`. Learn its syntax from the existing sources; there is no separate manual in this repo.

## Background
We are adding an optional JIT compiler to SilkJS. Hard requirement from the project owner: the engine must stay usable with no JIT at all (embedders and WebAssembly builds), and the interpreter-only build must not get slower or bigger. So the JIT will live in a separate package (`modules/jit`, created by another agent) and the engine exposes exactly one seam. Your job is that seam, inside the engine only. You do not generate machine code.

## Code you need to understand first
- `modules/engine/src/js_vm.silk`: the interpreter. `executeLoop<H, O: Observation>` is the dispatch loop; it is instantiated twice through the `Observation` interface (`PlainRun`, `ObservedRun`) so that `mode.observes()` is a compile-time constant in each copy. This is the pattern to copy for the tier hook: a type parameter whose no-JIT implementation folds to nothing.
- `modules/engine/src/js_vm_state.silk`: `Machine`, the interpreter's register state (ip, stackTop, locals, arguments, frame).
- `modules/engine/src/js_vm_activation.silk`: how calls enter bytecode functions, including inline call frames (`InlineFrame`, `callInline`) and `js_vm_leaf.silk` frameless leaf calls.
- `modules/engine/src/js_core_types.silk`: `FunctionBytecode` (fields read on call entry come first, deliberately, for cache locality), `StackFrame`, `RuntimeState`.
- `modules/engine/src/js_bytecode.silk`, `js_opcode_data.silk`: opcodes. Find the backward-jump opcodes (loops) and where the dispatch loop polls interrupts on jumps (`interruptCounter`).
- `modules/engine/src/js_gc.silk`: how `FunctionBytecode` cells are traced and destroyed (`destroyBytecode`), since you add state to them.
- `modules/engine/src/js_binary_object_reader.silk` / `_writer.silk`: bytecode serialization. New per-function runtime state must NOT be serialized and must be initialized correctly when bytecode is read from a cache.

## What to build
1. **Hotness counter per function.** Add a small counter to `FunctionBytecode` (a `u32` is fine; place it with the call-entry fields). It is charged on function entry and on loop back-edges. Design goals, in priority order: (a) negligible interpreter cost, (b) one counter that both entry and back-edges feed, with back-edges weighted so a single long-running loop gets hot. Look for a way to piggyback the back-edge charge on the existing interrupt-poll path on jumps rather than adding a new load/store to every backward jump; measure before and after either way.
2. **Native entry slot per function.** Add a field to `FunctionBytecode` holding an opaque machine-code entry address (null when none) plus an opaque pointer-sized `tierData` owned by the tier backend. Nothing in the engine dereferences these except through the hook.
3. **The tier hook.** Define an interface (suggested file `modules/engine/src/js_tier_host.silk`, exported from `silk.toml`) following how the other `js_*_host.silk` hook interfaces are declared. Suggested methods; adjust names to local conventions:
   - `enabled() -> bool`: compile-time constant; false for the no-JIT implementation.
   - `threshold() -> u32`.
   - `functionHot(runtime, bytecode, atLoopPc: Option<usize>)`: called when the counter crosses the threshold, from function entry (None) or a back-edge (the bytecode pc). The backend may install a native entry. Must not run JS and must tolerate being called again.
   - `enter(...)`: called on function entry when the native entry slot is non-null; returns either a completed value or "not taken, interpret". For now pass what the interpreter has at entry (runtime, context, the `Machine`/frame) and document the contract precisely in comments. Do not over-design the calling convention: the first compiler will use the interpreter's own frame layout and read/write the same slots.
   - `functionDestroyed(bytecode, tierData)`: called from bytecode destruction so the backend can free code.
   Provide a `NoTier` implementation where every method is `@inlineAlways` and `enabled()` returns false, so all hook call sites sit behind `if tier.enabled()` and vanish. Decide whether the hook is a new type parameter on `executeLoop` or folded into the existing hooks bundle `H`; pick whichever causes the least churn at call sites and explain your choice. The default CLI and every existing embedder path must use `NoTier` with no source changes on their side.
4. **A test backend, inside engine tests only.** A hook implementation that records calls (which function got hot, entry vs back-edge, at which pc) and never installs code, used by new tests that assert: a function called N times crosses the threshold exactly once per threshold period; a single call containing a long loop crosses via the back-edge path with a pc inside the loop; generators, async functions, leaf calls and inline calls are all counted; destroying a function calls `functionDestroyed`. Look at existing `*_tests.silk` files and `scripts/check.py` for how tests are written and registered.
5. **No-regression proof.** Build `silk build --release` on the commit before your changes and after (copy the binaries aside), then run `python3 modules/engine/scripts/v8bench.py --instructions <before> <after>` and `python3 modules/engine/scripts/ab.py <before> <after> --instructions`. With `NoTier`, instruction counts must be within noise (target: under 0.3% on every V8-suite test) and the binary must not grow by more than a few KB. If the counter itself costs more than that, try alternatives (charge only on the frame-building call path, not leaf calls; fold into the interrupt counter decrement; charge every Nth) and report the measured cost of each. Other agents are compiling on this machine, so rely on instruction counts, not wall-clock.
6. Run the correctness gate: `silk check --workspace` at the repo root, and in `modules/engine` `silk build --release` then `silk task check`. Everything that passed before must pass after. If something already fails before your change, record it as pre-existing with evidence.

## Rules
- Touch only `modules/engine`. Do not create `modules/jit`. Do not change bytecode format, opcode numbering or serialized layout.
- Keep existing comment style: comments explain why, in plain sentences. No decorative banners.
- `scripts/check_opcode_dispatch.py` checks the opcode match in `js_vm.silk`; keep it passing.
- Never claim a measurement you did not run. Paste the actual before/after figures in your report.
- Commit on a new local branch `jit/p1-tier-seam` in small commits with plain messages. Do NOT push, do NOT open a pull request.
- Do not start subagents.

## Final report (your last message)
- Branch and commits.
- The hook interface as finally written (paste it), and where each call site is (file:line).
- Before/after instruction counts per benchmark and binary sizes.
- Test results, including anything pre-existing that fails.
- Open questions for whoever writes the compiler next (for example what `enter` should receive, how on-stack replacement at a loop pc should hand over).
