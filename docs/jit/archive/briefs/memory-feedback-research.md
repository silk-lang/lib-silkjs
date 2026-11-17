# JIT P1: memory model and feedback research

Historical task brief recovered verbatim on 2026-11-17. This is an archive, not an instruction to launch or restart work. Paths, measurements, task status, and operational rules may be outdated. See [the recovery index](../../README.md) and the newer coordination handoff before using it.

Source: <t3-thread://v2/df925567-22cf-40cf-9a2c-46fb2bd05b71/3d78b1cc-ea92-4e4d-9957-9b496b4a1270>, activity position 76, item `turn-item:provider:claudeAgent:native-item:toolu_013nb5v7Am9jrjWcjTnSBc7j`.

---

You are working in a git worktree of SilkJS: a JavaScript engine written in the Silk language (a native port of QuickJS) plus a Node-compatible runtime. Layout: `modules/engine` (package `silkjs`), `modules/runtime`. Read the root `README.md` and `modules/engine/bench/README.md` first. Learn Silk syntax from the sources.

## Background
We are adding an optional JIT compiler to SilkJS that should reach V8 and JavaScriptCore on peak throughput. Three design decisions depend on facts nobody has gathered yet. This is a research and measurement task: your output is a written report in your final message, backed by measurements and file:line references. You may write throwaway instrumentation in this worktree to measure things, but you ship no production change and you do not need to keep the instrumentation tidy. Do not create documents in the repo; the report goes in your final message.

Relevant facts already known:
- Values are `ValueBits` (`modules/engine/src/js_value.silk`): a 16-byte tagged union. Heap values are reference counted (`HeapHeader.referenceCount` in `js_heap.silk`), with a cycle collector that has a young generation (`js_gc.silk`). Cells do not move. Memory comes from pooled size-class arenas (`runtime_memory.silk`).
- Property lookups use inline caches kept in runtime-wide side tables keyed by bytecode site address (`RuntimeState.fieldCache: [FieldCacheEntry; 4096]` and others in `js_core_types.silk` around lines 700–1060; users in `js_vm_property_ops.silk`, `js_vm_object_ops.silk`).
- Shapes (`js_shapes.silk`) carry a `version` and the runtime has a `shapeEpoch`.
- Object property slots were once stored as one NaN-boxed word and that was reverted: commits titled "Store property slots as one NaN-boxed word (#779)", "its packed-word drain (#799)" and "Revert NaN-boxed property slots (#779) and its packed-word drain (#799) (#802)", all around 2026-11-08.
- Silk 0.1.0-dev.69 is installed; do not run `silk use`. Build with `silk build --release` in `modules/engine`. Benchmark tools: `scripts/v8bench.py` (has `--instructions` using callgrind), `scripts/bench.py`, `scripts/ab.py`. `perf` and `valgrind` are installed. Other agents are compiling on this machine, so prefer instruction counts and counters over wall-clock.

## Question 1: what does reference counting cost today, and what would a JIT have to elide?
- Find every retain and release primitive the interpreter uses (in `js_owned_value.silk`, `js_gc.silk`, `js_vm_values.silk`, `js_vm_locals.silk` and wherever else) and explain the ownership rules the interpreter follows for operand-stack slots, locals, arguments and borrowed values (the codebase has "lend"/"borrow" notions; document them precisely with references).
- Measure, per V8-suite benchmark (`bench/v8`: richards, deltablue, crypto, raytrace, earley-boyer, regexp, splay, navier-stokes): the number of retain and release operations executed, how many of them are on values that are immediately released again without escaping (retain/release pairs within one bytecode instruction or between adjacent stack operations), and the share of total instructions spent in counting and in freeing. Use temporary counters compiled into a release build, callgrind function attribution, or both; state the method and its limits.
- Classify where counts change: local-to-stack copies, stack-to-local stores, property loads, property stores, calls (arguments, `this`, callee), returns, closure variable access. For each class say whether a compiler that keeps values in registers and treats them as borrowed could skip it, and what invariant makes that safe (who else holds the reference for the duration).
- Identify the hazards: places where JS code or a helper can drop the last other reference to a value the compiled code is still using (for example a getter that overwrites the property the value was loaded from, or a callee that reassigns a captured variable). Explain how the interpreter stays safe today in those cases.

## Question 2: which memory model should the JIT assume?
Compare three candidates specifically for this codebase and give a recommendation with your confidence:
 (a) keep reference counting and elide counts in compiled code;
 (b) reference counting with a bump-allocated, uncounted young generation (objects not counted until they escape to the heap; see the LXR paper, "Low-Latency, High-Throughput Garbage Collection", PLDI 2022, and deferred reference counting generally);
 (c) replace counting with a non-moving tracing collector.
For each: what in `js_gc.silk`, `js_heap.silk`, `runtime_memory.silk` and the embedding API (`js_owned_value.silk`, `js_engine*.silk`) would have to change, roughly how many call sites are affected (count them), what it means for the WebAssembly build (no native stack scanning; note the interpreter keeps JS values in explicit frame slots, not on the native stack, and check whether that is fully true by looking for JS values held in native locals across calls that can collect), what it means for finalizers, WeakRef and FinalizationRegistry timing, and the expected effect on Splay and EarleyBoyer (allocation-heavy) versus Richards and DeltaBlue. Use the measurements from Question 1 plus allocation counts and object lifetimes if you can gather them (how many objects die before the first young collection). If you make a claim about published results, name the source; if you are unsure of a detail, say so rather than guess.

## Question 3: why was NaN-boxing of property slots reverted, and should values become 8 bytes?
- Read the three commits and their PR descriptions (`git log --all --grep`, `git show`; `gh pr view 779`, `802`, `799` on the repo may give discussion, read-only). Report the stated and the actual reason for the revert, with measurements if any were recorded.
- Assess what an 8-byte NaN-boxed `ValueBits` everywhere would require: how the 16 variants would encode (pointer tags for BigInt, Symbol, String, Rope, Module, FunctionBytecode, Object; int32; double; ShortBigInt needs 48 bits today; the special values), which code depends on the 16-byte layout (for example the SIMD `anyHeap` scan in `js_value.silk`, `SlotBits`, frame slot sizes, serialization), and the likely effect on memory traffic and on generated code (an 8-byte value fits one register). Count the affected sites. Say whether this should happen before the compiler is written, after, or never, and why.

## Question 4: design input for per-function feedback vectors
- Inventory every site-keyed or runtime-wide cache the interpreter uses today: name, key, entry layout, size, collision behaviour, invalidation rule, which opcodes use it (with file:line). Include field caches, typed-array length cache, receiver/instance/literal/construct caches, transition caches, regexp caches and any others in `RuntimeState` and `ContextState`.
- Measure hit, miss and collision-eviction rates of the field cache on the V8 suite and on one large program (for example `bench/macro/parse.js`), using temporary counters.
- Propose a per-function feedback vector layout: one slot per feedback-relevant bytecode site, allocated lazily when a function first runs or gets warm, owned by `FunctionBytecode`, never serialized. Specify slot kinds (property load/store with shape version and slot index and prototype-chain validity; call target; arithmetic operand types seen; array element kind; comparison types; branch taken counts if cheap), how a site maps to its slot (operand in bytecode versus side table from pc; note that bytecode can be read-only and shared), how slots are traced and invalidated by the collector and by shape changes, and the migration order that keeps the interpreter at least as fast at every step. State what a compiler needs from each slot kind to speculate.
- List the opcodes that would carry feedback, with how hot each is on the V8 suite (dynamic counts from a temporary counter in the dispatch loop).

## Rules
- Do not commit production changes. If you want to preserve instrumentation for others, commit it on a local branch `jit/research-instrumentation` clearly marked as throwaway; do NOT push and do NOT open a pull request.
- Every number in the report must come from a run you made; give the command. Separate measured facts, facts read from code (with file:line), and your own inference, and label each.
- Do not start subagents.

## Final report (your last message)
Four sections matching the four questions, each ending with a recommendation and a confidence level, then a list of what you could not determine and what experiment would settle it.
