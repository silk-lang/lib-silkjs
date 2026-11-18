# Following one HTTP order through SilkJS

The service receives one POST over a persistent connection, decodes its body, parses the order, sums the line items and writes a JSON response. The Python client independently computes the expected response bytes for four alternating orders. It checks every response, including the shutdown request. The application and the runtime's Node-compatible JavaScript modules are identical across these experiments.

## Original request path

A debugger followed 1,600 requests on the original production engine with compiled calls enabled. Counts include warmup and shutdown. The debugger did not supply timing data.

| Function or site | What the original binary did |
| --- | --- |
| Native HTTP parser `event` | Stayed compiled on 6,917 entries. |
| Native HTTP parser `callback` | All eight compiled entries stopped at the initial `parser[index]` read. All eight indices named own data properties of ordinary parser objects. |
| `parserOnMessageComplete` | Stopped at a symbol lookup on all eight entries. The symbol was absent across the ordinary prototype chain. |
| `parserOnIncoming` | Eight exits at the inherited `needDrain` accessor. Calling the getter is observable. |
| `EventEmitter.emit` | Four installs and 32 compiled entries, all exiting at `events[type]`. The receiver was ordinary and the key was a flat event-name string each time. Nineteen returned an own listener and thirteen missed, including three with a non-null prototype. |
| Application data listener | Its `body += chunk` requires string addition. |
| Application end listener | All 1,600 orders reached the native JSON parser. Eight arrived from compiled code and 1,592 through the interpreter. Each compiled invocation reached `response.setHeader('content-type', 'application/json')` and deoptimized there. The response then reached the already-compilable `totalCents` loop, stringify and `response.end`. |

The single-listener branch loads the actual `handler.apply` method at bytecode PC 130 and calls it at PC 138. An isolated check allowed the unmodified emitter body to reach this branch using a dense array and integer key. It completed 1,476 compiled invocations with zero exits while the listener ran interpreted. Getter and overridden-method tests checked the receiver, argument identity, side effects and exceptions. [Production trace](baseline-route.json) · [Isolated listener call](listener-call.json)

## What stayed compiled

On production source `62790abf`, feedback for reads on ordinary objects selects an x86-64 operation with a boxed key. Its helper uses the interpreter's non-calling lookup for flat strings, symbols and nonnegative integer keys. It returns an owned value for data properties or a proven miss. Accessors, coercions and unsupported receivers resume at the same bytecode. Existing numeric array and typed-array reads retain their fast lowering. The helper lives in the runtime table, so the generated code embeds no key or heap address. [Implementation](../../../../modules/engine/src/js_compiled_objects.silk)

| Compiled entries / exits in 1,600 verified requests, calls enabled | Original | Candidate |
| --- | ---: | ---: |
| Native parser `event` | 6,917 / 0 | 6,916 / 0 |
| Native parser `callback` | 8 / 8 | 8 / 8 |
| `parserOnMessageComplete` | 8 / 8 | 1,728 / 0 |
| `parserOnIncoming` | 24 / 8 | 24 / 8 |
| `EventEmitter.emit` | 32 / 32 | 14,813 / 1 |
| Application `end` listener | 8 / 8 | 24 / 8 |

`emit` stayed installed. Its sole remaining exit was the multi-listener branch at PC 171. The end listener reached JSON.parse from compiled code for eight orders in a separate 1,600-order trace. Its call to `setHeader` still exited. An isolated trial allowed the real header setter to reach the next observable operation. Fresh response objects stopped at a symbol-keyed write, while reused objects reached the string method read. The string-method trial is outside the candidate. [Candidate routes and builtin stacks](candidate-route.json) · [Header setter control](set-header-exits.json)

The native parser's `callback` compiled before its recorder saw the first instruction. In a same-binary debugger experiment, marking just that read as an observed ordinary-object lookup eliminated its original exit. The callback then exited eight times on an object used as a boolean at PC 23 and unlinked. In a separate run, the function's recorder stopped with 275 of its 296 instructions still available when the shared recording budget reached zero. Instructions in other functions count against that shared budget. A deployment profile that records from the next entry into the intended function could observe several related guards at once. Its impact on CPU per order still needs measuring. [Feedback control](callback-feedback-control.json) · [Recording window](callback-window.json)

A separate JS function performing a single `table[type]` read used about 939 instructions per incremental call when linked, versus 893 with the earlier JIT. The generated body contributed 36 instructions, the keyed-read helper 157 and the VM's compiled-entry routine 159 in its own code. On the service, all flat-string lookup work reached from the new helper cost at most 0.19% of the measured calls-on instructions. The largest opportunity at this site is the surrounding code that can continue executing after the lookup. [Isolated call costs](own-key-cost.json) · [Actual service budget](service-key-cost.json)

## Locating the V8 gap

After 4,800 warmup orders, a 400-order fixed window took approximately 767,000 x86-64 instructions per order on the original default SilkJS and 217,000–220,000 on Node v24.19.0. The complete call to JSON.parse accounted for about 205,000 on SilkJS and 112,000 on Node. Subtracting these inclusive parser counts from each process total leaves about 83% of the instruction gap outside parsing. Cycles per instruction and operating-system costs can differ between runtimes. Server CPU and throughput come from separate processes running without instrumentation. [Node profiles](node-fixed-work.json)

The original server's default-JIT count fell from 761,000 instructions per 64-line order to 543,000 per four-line order after 1,200 warmup requests. Parsing fell from 205,000 to 16,400 instructions. The line count explains most of the change in parsing work. Roughly 527,000 instructions per small order remained outside the parser.

## Reproducing the Node profile and dispatch count

Run the following commands from the repository root. The first command needs Node 24.19.0, Valgrind and `callgrind_control`. The output directory must be new. Repeat with `--warmup 1200` for the shorter warmup.

```sh
results=docs/jit/jit-scorecard-results/2026-11-18-http-service
python3 "$results/profile_node.py" --repo . --node "$(command -v node)" --warmup 4800 --out /tmp/node-http-4800
python3 "$results/dispatch.py" /path/to/silkjs-jit-embed-smoke /path/to/400-order/profile.PID.1
```

The dispatch counter uses the release ELF and its matching `.symbols` file. In each specialization of the main interpreter loop and leaf evaluator, it locates the 256-entry opcode jump table and counts executed jumps to that table in the instruction-address dump. A fused bytecode group can execute in a single dispatch. The count includes interpreter execution throughout the server and excludes transitions within emitted JIT code.
