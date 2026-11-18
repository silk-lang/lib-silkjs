# HTTP strict-equality and compiled-call controls

The service reads a 64-line JSON order over one persistent HTTP connection and returns the computed total. The Python client checks the complete response against its independently computed result. The comparison uses an x86_64 release embedding host built from production source `b52550c7` plus the local diagnostic patch. Four diagnostic SilkJS conditions use that same executable. Two further conditions run the unmodified production executable on the same service.

Unset `SILKJS_BENCH_ABLATE_STRICT_EQUALITY` to exercise the production policy. Set it to `1` to refuse nonnumeric strict comparisons during initial feedback planning. The patch covers strict equality, strict inequality and their immediate forms. Each condition runs with and without `--jit-calls`. The ordinary Node process runs the same service with its default JIT.

## Reproduction

Use the pinned toolchain and native runtime archives specified in the milestone. Start from a worktree at production commit `b52550c71a2d08f4dd89b37163e0c3af07df0836`. Set `RECEIPT` to this directory in the results checkout, `RESULTS` to a fresh output directory and `NODE` to the Node reference executable. Both scripts use the benchmark client from `--repo`.

```sh
mkdir -p "$RESULTS"
silk build --release --manifest-path modules/jit/embed-smoke/silk.toml
release="$PWD/build/llvm/x86_64-unknown-linux-gnu/release/silkjs-jit-embed-smoke"
cp "$release" "$RESULTS/production"
prod_digest=$(sha256sum "$RESULTS/production" | cut -d' ' -f1)
git apply "$RECEIPT/strict-equality-control.patch"
silk build --release --manifest-path modules/jit/embed-smoke/silk.toml
host="$PWD/build/llvm/x86_64-unknown-linux-gnu/release/silkjs-jit-embed-smoke"
digest=$(sha256sum "$host" | cut -d' ' -f1)
for warm in 1200 4800; do
    python3 "$RECEIPT/profile.py" --repo "$PWD" --host "$host" --host-sha "$digest" \
        --out "$RESULTS/profile-$warm" --warmup "$warm"
done
python3 "$RECEIPT/wall.py" --repo "$PWD" --host "$host" --host-sha "$digest" \
    --source 16d52a4cac3445ed5338d6be6e6de290dd7f813e \
    --production-source b52550c71a2d08f4dd89b37163e0c3af07df0836 \
    --production-host "$RESULTS/production" --production-sha "$prod_digest" \
    --node "$NODE" --server-cpu 0 --client-cpu 4 --json "$RESULTS/wall.json"
```

The fixed-work profile requires `valgrind`, `callgrind_control` and the matching release `.symbols` sidecar. Each fresh server handles 1,200 or 4,800 verified warmup orders with instrumentation off. The client turns on and zeros Callgrind, verifies 400 orders, captures a dump, then turns instrumentation off and checks a clean shutdown. Self instruction counts for generated code use anonymous executable guest mappings. Named self counts for VM, JSON parsing, GC, JIT helpers and compiler passes use the host's symbol sidecar. The JIT counters cover warmup, the measured requests and shutdown.

The wall measurement pins the client and server separately. Each fresh server handles a first verified response, 1,200 warmup orders, a three-second sequential throughput interval and 400 scheduled orders at 100/s before shutdown. The CPU value counts server user and system CPU per sequential order. Latency starts at the intended arrival and includes queue delay. Each of the seven conditions appears in five different positions across five rounds. Ratios in `wall.json` are computed per round before taking their median.

The 1,200-warm fixed-work profile was run twice. With calls enabled, admitting nonnumeric strict equality raised Ir/order by 4.7% and 11.1% at 1,200 warmup orders, and by 3.9% at 4,800. Compiler passes accounted for 1.4%, 6.2% and 7.4% of the admitted profiles, respectively. At 4,800 warmup orders the ablated calls-on profile spent 5.0% of its instructions in compiler passes as well.

The separate debugger traces record 6,927 compiled entries and zero deoptimizations in the native parser’s `event` callback with admitted equality and calls enabled. Ablating equality kept this callback interpreted. `parserOnIncoming` entered 24 times and exited to the interpreter eight times. The event emitter entered 32 times and exited 32 times across four installs. Individual function counts, bytecode exit sites and the process totals are in `callback-attribution.json`.

`nexttick-trials.json` records an earlier callback probe on `c39cc03d` and two discarded runtime JavaScript variants. Each change moved fixed-work instructions by less than 0.23%. Neither change was included in the equality experiment.
