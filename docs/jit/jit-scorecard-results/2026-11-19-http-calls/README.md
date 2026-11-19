# Compiled calls on the x86-64 HTTP order service

The same release host, source `62790abf`, served 4,235 verified 64-item orders/s with the default JIT and 2,936/s with compiled calls enabled. Node v24.19.0 served 9,544/s. The default SilkJS host used 4.20× Node’s server CPU per order. The benchmark includes the parser, JavaScript event and listener dispatch, JSON parsing, application arithmetic and the response on one persistent connection.

## Where the extra CPU goes

Kernel task-clock sampling covered 97.3–100.4% of the independently measured user CPU across ten runs. In the pair with clear CPU lanes, compiled calls raised total CPU from 226.8 to 340.7 µs/order. Across the three longer pairs, the median change was −8.3 µs in interpreter dispatch, +34.4 µs executing generated code, +22.4 µs in other VM functions and +13.2 µs in JIT helpers. These are exclusive samples. The newly generated code executes operations that the interpreter previously performed, so its entire cost cannot be counted as transition overhead. [CPU measurements and reproduction](cpu/README.md)

## Three independent release experiments

Each row is the median of six fresh processes. The same server and client ran on separate cores, with 1,200 verified warmup orders per process and a three-second sequential timing window. Each process then handled 40 scheduled orders and a verified shutdown. The 13 conditions were interleaved across rounds. The CPU and throughput figures below cover the sequential window only. The client verified 1,071,985 orders across all phases, excluding shutdowns. [Raw timings and binary hashes](wall-64.json.gz) · [Driver](compare.py)

| 64-item service | Default orders/s | Default CPU, µs/order | Compiled calls, orders/s | Compiled calls CPU, µs/order |
| --- | ---: | ---: | ---: | ---: |
| Same-source baseline | 4,235 | 228.54 | 2,936 | 328.76 |
| Shorter linked-call entry, `a86b1dec` | 4,346 | 224.00 | 2,848 | 336.66 |
| Packed call blocks, `2718638e` | 4,177 | 231.86 | 2,746 | 350.19 |
| Guarded field definition, `5ddda6ed` | 4,155 | 233.85 | 2,907 | 331.95 |

On these runs the baseline with the JIT disabled served 4,133 orders/s at 233.87 µs/order. Node served 9,544/s at 54.36 µs/order. Percentages comparing individual trials below are medians of within-round ratios.

* **Shorter linked-call entry.** The interpreter can reuse the interrupt charge and published continuation when entering linked code. With compiled calls enabled the entry routine fell from 96 to 87 instructions per invocation and activation startup from 220 to 195. On 64-item orders the default policy used 4.2% less paired CPU, with four of six pairs improving. The calls-enabled policy used 1.6% more paired CPU. [Instruction counts](linked-entry.json)
* **Packed call blocks.** Each call site saved only its live values contiguously. The run-weighted average call-block size fell from 1,598 to 906 bytes and the largest observed block fell from 6,536 to 1,112 bytes. All 94 JIT tests passed, including a new test for a double used only by a throw exit. The compiled-call configuration used more CPU in all six pairs, a median increase of 3.5%. The experiment is preserved on `work/x86-packed-resume`. [Block sizes and use counts](call-blocks.json)
* **Guarded field definition.** The JIT defined an ordinary own data property directly when the receiver, descriptor and ownership checks succeeded. Generic field-definition exits fell from 676 to 24 in a 24-order debugger window. Calls-enabled instructions per order fell 1.9% after 1,200 warmups and 1.0% after 4,800 relative to the archived baseline. Paired CPU changed by +3.2% with mixed signs. All 93 JIT tests passed, and the JavaScript controls matched Node for proxies, setters, descriptors and reference ownership. The change is available on `work/jit-define-field`. [Opcode census and semantic checks](define-field.json) · [Matched instruction windows](fixed-orders.json)

The longer fixed-work profiles still include some compilation. Two baseline runs with compiled calls enabled used 924,531 and 946,782 instructions per order, so a small difference in a single 400-order window is insufficient for a service-wide speed claim.

A second six-round comparison on four-item orders gave the shorter linked-entry path 4,712 orders/s at 206.90 µs/order under default settings, compared with 4,714/s at 205.79 µs for the baseline. Paired CPU changed by +1.4% under default settings and +10.4% with compiled calls. The two JIT-disabled builds also differed by +3.3% paired CPU on this sweep. The 64-item default improvement did not repeat. This trial remains on `work/http-linked-entry`. All 93 of its native JIT tests passed. [Four-item timings](wall-4.json.gz)

## Compiling the request path selectively

On the unchanged release, the compiler admitted calls only for 15 selected functions along the parser and application path. The emitter completed 4,000 compiled invocations in the 400-order window without deoptimizing. The application request and end listeners remained interpreted. Selecting the path used 769,581 instructions/order against 760,422 at default settings and 926,163 with global calls. An independent run reproduced the ordering. It found a 1.63% increase over default for the selected path and a 22.08% increase for global calls. Both runs verified every response. [Function-level evidence and reproduction](selective/README.md)
