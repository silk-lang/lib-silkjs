# SilkJS on x86-64 Linux

## Decision

Keep the optional JIT and its shared compiler for eventual AOT. Change how we select compiler work. Run the application or CLI workload on which a proposed change should pay for itself, measure its time against default Node/V8, and identify where SilkJS spends the extra time. Use kernels to isolate the mechanism afterwards. Keep correctness and the cost of interpreter-only operation as independent release gates.

The [original plan](https://github.com/silk-lang/lib-silkjs/blob/8237a590/docs/jit/archive/2026-11-12-plan.html) set a first throughput target within 1.3× of V8 and JSC on the suite geometric mean. Its longer-term ambition was parity on the mean with the slowest workload within about 1.3×. For this milestone use the first target on x86-64 with default V8 in a pinned Node release. Report the slowest workload and each suite separately. For the server, propose the same 1.3× budget independently on CPU-bound request time and p99 under agreed load, and report startup and RSS alongside them. Preserve the longer-term ambition. A geometric mean that includes cold startup, request latency and throughput makes it impossible to tell which target the engine met.

## What the earlier measurements establish

| Evidence | Consequence |
| --- | --- |
| On `d82fa5e8`, Octane scored 5,261 for the interpreter, 5,377 for the JIT, 5,332 with compiled calls and 49,435 for Node/V8. The aggregate includes two latency scores. | Default JIT was 9.19× behind V8 on the historical score. Restricting the geomean to the 15 throughput scores gives 4,767 versus 47,814, a 10.03× gap. Moving every benchmark just below interpreter instruction count would still leave most of this gap. |
| In the same scorecard, six warmed Octane workloads took 10.0–24.4× as long as V8. The empty JIT shell started in 3.4 ms versus 26.0 ms for Node. | The shell has a cold-start advantage. A server can spend that entire saving many times over processing requests. Measure from launch to first successful request, then at steady load. |
| The ungated inlining preview `6623564` narrowed the eight-kernel geomean with compiled calls to 2.3× V8. RayTrace executed 1.429× the interpreter’s instructions. | Keep call inlining as an experiment. Its admission policy, code size, compilation time and repeated exits matter as much as the fast call itself. |
| On `d82fa5e8`, compiled calls increased fixed-work instruction counts on Box2D (1.250×), RegExp (1.193×) and TypeScript (1.095×). TypeScript ran 2,003 deopts and unlinked code 246 times. | Keep calls opt-in until the full-suite regressions have been addressed. Count compiler instructions and transitions alongside time spent running useful compiled code. |

The pause report and the measurement branch contain different kernel runs. Use ratios from a single run, with its own host and configuration. The 31 output comparisons in the historical record span Octane, the V8 benchmark scripts and kernels. [Integration scorecard and preview](https://github.com/silk-lang/lib-silkjs/blob/b3ca2f88/docs/jit/jit-scorecard.md) · [Pause record](pause-2026-11-18.md)

## Candidate measurements

We built `9c7cb585` in release mode on Linux x86-64 with the pinned Silk dev.74 and Clang 22.1.8. The host was a KVM guest on AMD EPYC 9V74 with a four-CPU quota. Node was 24.19.0 with V8 13.6.233.17. The table gives the median paired ratio of SilkJS time to Node time over five fresh process pairs. The cold measurement includes process startup and the entire script. The repeated measurement runs two untimed invocations then five timed invocations per process. Every invocation has a checked result. Ratios below 1 favor SilkJS.

| CLI workload | Cold, default JIT | Repeated, default JIT | Cold, compiled calls | Repeated, compiled calls |
| --- | ---: | ---: | ---: | ---: |
| Nested JSON round trip | 0.42× | 1.16× | 0.38× | 1.17× |
| Dynamic function construction | 0.98× | 20.42× | 0.88× | 23.05× |
| String/integer Map and Set operations | 0.45× | 0.83× | 0.41× | 1.15× |
| RegExp matching, replace and split | 0.17× | 1.62× | 0.19× | 1.60× |

The parse workload regenerates the same three 238 KB function bodies on every invocation. In a paired diagnostic, adding a distinct trailing comment to each body changed the repeated default-JIT gap from 14.98× to 1.91×. Median SilkJS time changed from 35.1 to 30.0 ms, and Node time from 2.48 to 16.1 ms. Reusing identical source accounts for much of the gap on this fixture. Investigate reusable compilation data on a real loader workload before treating this result as evidence for a parser rewrite. [Diagnostic samples and exact source change](jit-scorecard-results/2026-11-18-9c7cb585/parse-reuse.json)

On eight fixed-work kernels (seven fresh processes per engine), the default JIT took 7.99× Node’s time on the geometric mean. Compiled calls brought this to 5.28×. The doubles kernel was 1.33× with calls, the typed-array kernel 44.88×. A typed-array benchmark this far behind earns a separate profile of compilation versus steady-state element access. The earlier preview on a different branch and host reached 7.5× on the typed-array kernel and still needs independent application-level validation.

[CLI runner and reproduction](../../modules/engine/bench/README.md) · [Default JIT samples](jit-scorecard-results/2026-11-18-9c7cb585/cli-jit.json) · [Compiled-calls samples](jit-scorecard-results/2026-11-18-9c7cb585/cli-calls.json) · [Kernel samples and counters](jit-scorecard-results/2026-11-18-9c7cb585/candidate-kernels.json)

## Server milestone

1. **Test the real host.** Run the same unchanged Node-compatible program in both full runtimes. Start with JSON over `node:http` and a callback-heavy application using the module loader. Verify response contents and request counts. Record wall time to first response in fresh processes, sustained successful requests/s, p99 at the same offered load below saturation, CPU/request and peak RSS. Record concurrency, warmup, client placement, versions, flags and binary identities. Publish the two workloads individually. The runtime bench currently defaults to Bun with its JIT disabled. [Runtime benchmark configuration](../../modules/runtime/bench/README.md)
2. **Spend CPU where it matters.** Profile the hot service interval with diagnostics separate from timing. Distinguish compiled bodies, interpreter, compiler, builtins, allocation/destruction and host I/O. When most excess CPU sits in a builtin, profile that builtin before broadening bytecode coverage. When it sits on call or field exits, group by function and site, and estimate the time recovered after compilation cost. Confirm each change with fixed-work interpreter and JIT A/B runs on the workload that motivated it.
3. **Use deployment information the host actually has.** The loader already owns module identity, bootstrap and bytecode caching. A stable deployment can seed a profile at restart, specialize a known callee behind an identity guard, or prebuild hot code before serving requests. Measure time-to-first-request, cumulative CPU through warmup and post-warmup throughput with those features independently enabled. Dynamic import, eval, monkey-patching and invalidation still require working fallback paths. [Runtime bytecode cache](../../modules/runtime/src/ext/script_cache.silk)
4. **Keep production integration close.** Main at `719650d1` has the composable runtime on Silk dev.86. This JIT branch uses dev.74 and forked at `d1973537`. A trial Git merge of the candidate and that main revision reports conflicts in the workspace manifest, engine tasks and benchmark engine registry. A clean textual merge of the VM files still requires compiling the new package graph and rerunning differential and host tests. Move the tested tier seam to main’s embedding API before accumulating another independent runtime.

### Integration queue

The next narrow iteration patch is `3da9846b` on top of the candidate’s iteration changes. Its recorded win is per-element cost in an array `for-of` loop. Verify it on iteration-heavy application code. The O2 branch has advanced to `25e45217`, which includes the recorder fix `a2fa3354`, K’s `d0a0f6d5` and J’s `db75ee41`. This supersedes the pause-time concern that the fixes had never been pushed. Recheck both previously failing tests, then test the typed-array kernel and the workloads hurt by speculative compilation. Preserve the separate call-inlining experiment through `ab69c4d`. Its successor `366f0b61` is a WIP re-entry prototype with additional recursion, throw and lifetime requirements.

A faster kernel, a passing differential or an unchanged interpreter instruction count can each justify a narrowly scoped integration decision. A V8 milestone decision needs full representative timings on the same revision. [Iteration patch](https://github.com/silk-lang/lib-silkjs/commit/3da9846b) · [O2 fixes](https://github.com/silk-lang/lib-silkjs/commit/25e45217) · [Call experiment](https://github.com/silk-lang/lib-silkjs/commit/ab69c4d)

### AOT follow-up

The two-runtime tests already take generated code for arithmetic and object/element/global operations, install it at a different address and exercise deopt. Both runtimes live in one process. Inlined targets are bound to live bytecode and callee identities. The existing Linux heap image depends on fixed addresses and its own executable. [Relocation tests](../../modules/jit/src/jit_engine_tests.silk) · [Installation](../../modules/jit/src/jit_runtime.silk) · [Heap image](../../modules/runtime/src/ext/heap_image.silk)

The first deliverable is a fresh-process round trip on one hot function through the existing compiler. Store code and the symbolic dependencies needed by its guards, deopt exits and inline callees. Validate the module and function contents, target CPU features and engine/helper ABI before publishing executable code. Resolve live references into runtime-owned data. Test a matching image at a new address, a changed module, a changed ABI and a changed callee. A rejected entry should take the ordinary interpreter/JIT path and produce the same result. Measure startup and first useful work against both a cold JIT and the existing bytecode cache before extending the format.
