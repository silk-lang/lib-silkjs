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
