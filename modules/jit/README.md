# silkjs-jit

Foundations for an optional native JIT, kept apart from the engine. The engine and the runtime do
not import this package, so an interpreter-only build never compiles it.

It does not compile JavaScript yet. What exists is listed below; everything else is not there.

| Module | What it holds |
| --- | --- |
| `code_memory` | W^X executable memory for Linux x86-64: reserve a range, write code into whole pages, publish them as executable, free them |

Only Linux x86-64 compiles. Every other target stops with a compile error: Linux arm64 (needs an
instruction-cache flush), macOS arm64 (needs `MAP_JIT`) and Windows are not implemented or tested.

## Running the tests

From the repository root:

```sh
silk test --manifest-path modules/jit/silk.toml
```

The tests read `/proc/self/maps` to check page protections, so they need Linux `procfs`.

## Executable memory

`CodeMemory.reserve` reserves address space with no access. `allocate` returns a `CodeWriter` that
owns whole read-write pages; `append` copies bytes in without handing out a writable pointer.
`finish` consumes the writer and returns a `CodeBlock` whose pages are read-execute: pages the code
did not reach go back to the region, and the rest of the last page is filled with `int3`. Dropping
a writer or a block removes all access to its pages, returns their physical memory to the kernel
and makes them reusable. A block keeps the region mapped after its `CodeMemory` has dropped.

No page is writable and executable at the same time, and a page has one owner, so publishing one
block cannot change another writer's protection. The price is that every block takes at least one
page (4 KiB): a compiler that emits many small functions must put several in one writer, and then
frees them together. Whether that, or a different scheme such as a dual mapping, gives the better
memory and publish cost is not measured yet.

All owners of one region must stay on one thread; the bookkeeping is not synchronized.

## Calling generated code

Calling a block is unsafe and uses the platform C ABI. Read the entry address as an
`extern "C" fn` through `Pointer.read`, as `call` in `src/code_memory_tests.silk` does. The block
must outlive every call and every function pointer made from it. Generated code must preserve the
callee-saved registers and keep the stack aligned. There is no unwind metadata and there are no
stack maps: Effects, failures and garbage-collector scans cannot cross a generated frame.
