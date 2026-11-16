# SilkJS JIT handoff

Verified 2026-11-16. Recovery branch: `t3/jit-compiler-plan` at `86c3e4db`.
Workspace: `/home/user/.t3/worktrees/silkjs/t3-d319cd44`.

## Objective and standing user constraints

Build an optional JIT that competes with V8 and JavaScriptCore on measured throughput, startup, warmup, latency, and memory. No current result establishes JIT parity or a performance win.

- Interpreter-only SilkJS must remain a first-class, easily embeddable product. Keep the engine independent of the optional `modules/jit` package and measure interpreter regressions.
- The goal is better measured outcomes, not simplicity for its own sake. Tier count and memory model remain evidence-driven decisions.
- Keep ahead-of-time compilation possible, even though it is outside the first milestones. Design relocatable code, serializable compiler inputs, and runtime references through data-side tables. These are proposed implementation rules supporting the user's AOT requirement, not implemented capabilities.
- Earlier authorization was for local commits in isolated worktrees, without pushes or PRs. This recovery did not merge or cherry-pick implementation branches.

## VM recovery and execution policy

The host has 8 CPUs and approximately 15 GiB usable RAM (a 16 GB VM). The user supplied a process listing showing five old Silk/Clang compiler processes using approximately 9.2 GiB combined RSS, three in uninterruptible kernel waits. Their ages were approximately 46 minutes. Their precise blocking cause was not diagnosed.

After the user terminated the old compiler jobs, command access recovered. A new release-build retry was observed in the memory-research worktree. Recovery called `task_cancel` for all seven historical task roots, including superseded differential-testing attempts, to stop running/queued continuations. Six returned completed and the rejected replacement returned failed. A subsequent process scan found no Silk/Clang jobs. No infrastructure services were killed.

The recovered VM snapshot showed approximately 3.4 GiB used and 12 GiB available RAM. This is a point-in-time observation, not a claim about steady state. The earlier gRPC failures stopped even no-op tool calls; their causal relation to VM load remains unproven.

For continuation, run one memory-heavy build/check at a time, preserve logs in the worktree, and use bounded commands. Do not automatically restart the old agent wave. Worktree presence does not mean a worker is active. Do not remove worktrees to clear process load.

## Verified branches and saved implementation

All six worktrees below were clean at initial recovery inspection. Paths are relative to `/home/user/.t3/worktrees/silkjs/`.

| Workstream | Branch | Worktree | Head / implementation |
| --- | --- | --- | --- |
| Coordination | `t3/jit-compiler-plan` | `t3-d319cd44` | `86c3e4db`; recovery documentation added here |
| Scorecard | `jit/p0-scorecard` | `t3-db1fac48` | `86c3e4db`; no task-specific commit or source changes |
| Tier seam | `jit/p1-tier-seam` | `t3-4bc12667` | `86c3e4db`; no hook implementation or source changes |
| Code memory | `jit/p1-code-memory-asm` | `t3-756f8a37` | `82349ee1a04dd5456e7cedfbfb958192e2c4eee8` |
| Differential testing | `jit/p1-differential` | `t3-336fba2c` | `c1c688908f5f2caa0876cb0815a8d8bf5aef07eb` |
| Memory research | `t3/jit-refcount-memory-research` | `t3-b15e66d7` | `86c3e4db`; report only, recovered separately |

Both implementation branches contain exactly one commit beyond the common base. Neither commit has been integrated into the coordination branch.

### Code memory: implemented subset

Commit `82349ee1` adds an optional workspace package, Linux x86-64 executable memory, and a direct-call test. The engine/runtime do not import the JIT package. `CodeMemory` reserves PROT_NONE memory; writers own whole RW pages; consuming `finish()` publishes RX pages; dropping leases revokes access before recycling pages. Blocks retain the region beyond the owner's lifetime. Review of the source establishes the intended mechanism, not comprehensive correctness.

The generated constant-return function is invoked directly through an unsafe C-ABI function pointer read from an address slot. No C trampoline is required for this proof.

Recovery validation, executed in `t3-756f8a37`:

```sh
timeout --signal=TERM --kill-after=5s 60s silk test --manifest-path modules/jit/silk.toml --no-cache
```

Result: **1 passed, 0 failed, 0 cached, 1 executed**; the function returned 42. This only validates the constant-call path. The earlier delegated workspace check exited 143 (SIGTERM), not a successful check or a compiler diagnostic.

Recovery also ran `timeout --signal=TERM --kill-after=5s 60s silk check --workspace` from the same worktree. It produced no diagnostic output and reached the timeout (exit 124). Engine/runtime compatibility therefore remains unverified. The final process scan found no remaining `silkc` or `clang-22` processes; no heavy check was left running.

Still missing: x86-64 encoder, instruction fixtures, permission/reuse/exhaustion/many-block tests, callback ABI tests, arm64 support, macOS MAP_JIT support, unwind metadata, and effects/exceptions across generated frames. `src/asm_x64.silk` is a one-line placeholder. The package README incorrectly describes a typed encoder and references nonexistent `scripts/check.py` and `scripts/encodings.py`; correct those claims before integration.

### Differential branch: implemented subset

Commit `c1c68890` adds hidden `--debug-observed` parsing and configures the existing debugger API at interpreter startup. Only `cli_options.silk` and `qjs_launch.silk` changed. Review did not establish that all execution paths enter observed dispatch.

Runner, generator, minimization, task integration, and documentation are unfinished. The worker reported **zero programs tested**. Its build log path is `t3-336fba2c/build/differential/release-build.log`; log existence and build completion must be checked before relying on it.

### Tier seam

No code landed. The worker identified the existing interrupt-poll path as a possible back-edge counting hook. Frameless leaf calls and constructor shortcuts require explicit treatment so native entry gets a valid frame. These are design leads, not tested changes.

### Scorecard

No scorecard implementation, competitor installation, measurements, or larger-suite feasibility runs completed in that task. Earlier numbers in conversation came from a stale November 6 binary and single runs; do not publish them as current-head results.

### Research

See [the recovered memory and feedback report](memory-feedback-research.md). It contains code inspection and historical evidence, but no completed instrumentation measurements. Key findings:

- RC elision must preserve independent ownership/rooting across reentrant calls. Keeping an object alive does not keep a property value alive after replacement.
- The existing young collector is a cycle collector that relies on counts, not an uncounted allocation nursery. Nursery/tracing alternatives require root and barrier work, including native temporaries and embedding handles.
- Own-field caches already include inline bytecode keys as well as runtime side tables. Do not blindly migrate them all to feedback vectors; measure the existing fast paths.
- The previous packed-property-slot revert was attributed to conversion overhead. This does not settle the performance of a globally packed value representation.
- Start with ownership-aware SSA and existing RC as an implementation hypothesis. Collector replacement and global packing remain experiments, not settled decisions.

## Recovered design and next milestones

The initial four-tier plan and immediate tracing-GC replacement were superseded in discussion. The subsequent direction was interpreter plus one SSA compiler with quick and full optimization modes, subject to measured warmup needs. Deopt to interpreter frames at bytecode boundaries; make ownership reconstruction part of the deopt design. The user did not mandate a permanent tier count or memory model.

1. **Finish foundational validation.** Correct overstated package docs; review the two saved commits; test memory permissions/lifetimes and the observed-dispatch option. Complete a bounded workspace check and relevant engine/runtime checks, recording commands and results. Integrate only validated changes.
2. **Establish a scorecard.** Extend existing benchmark tooling for configurable SilkJS, Node, d8, and JSC commands. Record versions, host, source revision, binary provenance, repetitions, throughput, warmup, startup, per-process peak RSS, binary size, and an explicitly labeled pause proxy. Missing engines are explicit omissions. Keep benchmark runs isolated from builds. A worst-iteration ratio is not a measured GC pause or p99 latency.
3. **Finish the differential harness.** Deterministic seeded programs; plain versus observed interpreter configurations; optional external reference engines; normalized output and exit classification; timeouts, reproducible failures, minimization, and explicit unsupported-case reporting. Generate stable hot calls followed by changed types/shapes/call targets. Add future JIT/deopt configurations through the same interface.
4. **Implement the engine seam.** Define hotness and native-entry hooks with zero/verified-minimal interpreter-only cost. Cover normal calls, leaf paths, constructors, loops, exceptions, and invalidation; do not serialize process-local pointers. Prove frame and ownership contracts before compiled JavaScript entry.
5. **Finish machine-code foundations.** Typed x64 operands and labels, relocation records, ABI handling, encoding comparisons against a real assembler, executable tests, and platform-gated extension points. One constant byte string is not an assembler.
6. **Add feedback and ownership-aware SSA.** Begin with call/type feedback; specify safepoints, guards, deoptimization state, native helper effects, and roots. Keep compiler inputs serializable for background compilation/AOT. Build a narrow end-to-end compiled function before broad optimization passes.
7. **Broaden optimizations from measurements.** Inlining, unboxed arithmetic, load/check elimination, register allocation, OSR, and allocation/RC optimizations. Evaluate background compilation, persisted profiles/code, cross-module optimization, and regexp compilation with correctness and performance gates.

The historical phase durations were estimates, not delivery commitments. Define progress through tests and measured gates.

## AOT context and historical artifacts

The original HTML plan at `/tmp/silkjs-jit-plan/silkjs-jit-plan.html` no longer exists on this VM. The design above was recovered from conversation and the saved notes at `/home/user/.claude/projects/-home-user-silkjs/memory/`.

Earlier Bun research cited [Bun PR 45631](https://github.com/oven-sh/bun/pull/45631), [WebKit PR 757](https://github.com/oven-sh/WebKit/pull/757), and [Bun AOT documentation](https://bun.com/docs/compiler/aot). Those sources and historical numerical claims were **not revalidated during this recovery**. The useful design hypotheses are immutable file-backed code, runtime data-side references, generic entry fallback, and opt-in closed-world assumptions. Preserve ordinary JS semantics by default. Do not assume static TypeScript annotations are sound runtime facts.

No JavaScript JIT compiler, validated x64 assembler, current benchmark scorecard, or engine-wide JIT integration is complete at this handoff.
