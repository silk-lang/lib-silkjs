# silkjsjit

Optional native JIT foundations, separate from the engine: page-granular executable
memory and a typed x86-64 encoder. It does not compile JavaScript. The engine and
runtime do not depend on this package.

From the repository root, run `python3 modules/jit/scripts/check.py`. This checks the
workspace, checks the assembler-generated fixture table, and runs the Silk tests.
To run just the native tests: `silk test --manifest-path modules/jit/silk.toml`.
Regenerate encoding fixtures with `python3 modules/jit/scripts/encodings.py`.

Only Linux x86-64 is supported. Other targets deliberately fail compilation;
Linux arm64 cache maintenance and macOS arm64 MAP_JIT publication remain marked
extension points. No implementation for those targets is claimed.

`CodeMemory.reserve` reserves a PROT_NONE region. `allocate` returns a non-copyable
`CodeWriter` owning whole RW pages. `append` copies bytes without exposing a writable
pointer; consuming `finish` publishes RX pages and returns a `CodeBlock`. Dropping a
writer or block revokes access and recycles its pages. Blocks keep the region alive
after its `CodeMemory` owner drops. These owners are confined to one thread.

Calling generated code is unsafe and uses the platform C ABI. Read the address's
pointer representation as an `extern "C" fn` through `Pointer.read`; see the
execution tests. The block must outlive every call and retained function pointer.
Generated functions must preserve callee-saved registers and align the stack before
calling Silk. Effects, exceptions and unwinding through generated frames are not
supported by this package; callbacks must complete normally. It supplies no unwind
metadata or garbage-collector stack maps.
