# JIT P1: jit package, code memory, x64 assembler

Historical task brief recovered verbatim on 2026-11-17. This is an archive, not an instruction to launch or restart work. Paths, measurements, task status, and operational rules may be outdated. See [the recovery index](../../README.md) and the newer coordination handoff before using it.

Source: <t3-thread://v2/df925567-22cf-40cf-9a2c-46fb2bd05b71/3d78b1cc-ea92-4e4d-9957-9b496b4a1270>, activity position 74, item `turn-item:provider:claudeAgent:native-item:toolu_01QfVotq1awuhCgMmXWtLi44`.

---

You are working in a git worktree of SilkJS: a JavaScript engine written in the Silk language plus a Node-compatible runtime. Layout: root `silk.toml` is a Silk workspace with members `modules/engine` (package `silkjs`) and `modules/runtime` (package `silkjsruntime`, which depends on the engine by path; read its `silk.toml` to see how). Read the root `README.md` first. Silk is a systems language with ownership, effects, `unsafe`, generics, `static if` on target (`Intrinsic.targetArchitecture()`, `Intrinsic.targetOperatingSystem()`), `extern "C"` declarations (see `modules/engine/src/cli_io.silk` and `js_atomics_native.silk`), inline assembly via `Intrinsic.assembly` (see `modules/engine/src/runtime_memory.silk` near `ticks` and `prefetch`), and native C sources via `[native] sources` in `silk.toml` (see `modules/engine/silk.toml`). Learn syntax from existing sources.

## Background
We are adding an optional JIT compiler to SilkJS. It must be a separate package so the engine builds and runs without it. Your job is to create that package and its lowest layer: executable memory, an x86-64 assembler, and proof that Silk code can call generated machine code. You do not compile JavaScript yet and you do not modify the engine.

The biggest unknown you must resolve: can Silk call into a raw executable buffer? Find out how to turn an address into a callable `extern "C" fn(...)` value (look at how function-pointer types such as `pub type WaitInterrupt = extern "C" fn(?*mut u8) -> u8` in `js_atomics_native.silk` are created and called, and at `Intrinsic.pointerReinterpret`). If the language cannot do it directly, write a minimal C trampoline as a native source in the new package (for example `uint64_t silk_jit_call(void *code, uint64_t a, uint64_t b, uint64_t c, uint64_t d)`), and say clearly in your report which route you took and why.

## What to build
1. **Package `modules/jit`** (package name `silkjsjit`), added to the workspace members in the root `silk.toml`, depending on the engine by path the way the runtime does (the dependency may be unused for now, but the wiring must build). Pin the same `silk-version` as the other packages. Add a short `modules/jit/README.md` stating what the package is and how to run its tests. Add a row for it in the root README table.
2. **Executable memory manager** (`code_memory.silk` or similar):
   - Reserve a code region with `mmap`; hand out code blocks from it; free blocks.
   - Strict write-xor-execute: a block is writable while being filled, then switched to read+execute with `mprotect` before it is ever called, and never writable and executable at once. Design the API so a caller cannot obtain an executable pointer to a block that is still writable (for example a `CodeWriter` that is consumed by `finish()` returning the executable `CodeBlock`).
   - Linux x86-64 is the required target. Structure the code with `static if` so macOS arm64 (`MAP_JIT`, `pthread_jit_write_protect_np`, `sys_icache_invalidate`) and Linux arm64 (`__builtin___clear_cache` equivalent) have clearly marked, compile-guarded places to go; implement them only if you can do so correctly from documentation, and mark anything untested as untested in comments and in your report. On WebAssembly and Windows the package should fail to compile with a clear `compileError`, not silently build.
   - Report allocation failure as an error value, never a trap.
3. **x86-64 assembler** (`asm_x64.silk`): a typed encoder writing into a growable byte buffer, with labels and forward/backward jump patching. Required instruction coverage for this task:
   - 64-bit and 32-bit `mov` reg/reg, reg/imm (32 and 64), load and store with base+disp8/disp32 and base+index*scale+disp addressing, including the RSP/R12 SIB and RBP/R13 displacement special cases and all REX cases for r8–r15.
   - `add sub and or xor cmp test` reg/reg, reg/imm8/imm32, reg/mem; `imul` reg/reg; `neg not`; `shl shr sar` by imm8 and by CL; `lea`.
   - `push pop call ret`, `call` reg, `jmp` rel32/rel8 and `jmp` reg, all `jcc` conditions (rel32; rel8 optional), `setcc`, `cmovcc`.
   - SSE2 scalar double: `movsd` reg/reg, load, store; `addsd subsd mulsd divsd sqrtsd ucomisd`; `cvtsi2sd` (32 and 64-bit source), `cvttsd2si`; `movq` between GPR and XMM; `xorpd`.
   - `int3`, `ud2`, multi-byte `nop` for alignment.
   Design the API around typed operands (`Reg64`, `Reg32`, `Xmm`, a `Mem` address type, `Label`), not raw bytes, so a later arm64 assembler can sit beside it under a shared, architecture-neutral macro layer. Do not build that macro layer now, but leave a short comment at the top of the file describing the intended split.
4. **Tests** (follow how the engine writes and registers tests: see `modules/engine/src/*_tests.silk`, the engine's `tests` export, and `modules/engine/scripts/check.py`; set up the equivalent minimal mechanism for the new package and document the command in the README):
   - Encoding tests: for every instruction form above, compare emitted bytes with known-good encodings. Generate the expected bytes with a real assembler rather than by hand: `clang` is at `/opt/llvm22/bin/clang` (use it with `llvm-objdump`/`llvm-mc` from the same directory if present, or `gcc`/`as` + `objdump`). Write a small script under `modules/jit/scripts/` that regenerates the expected-bytes table, and commit both the script and the table. Cover the awkward cases explicitly: r12/r13/rsp/rbp as base, r8–r15 in every operand position, disp8 vs disp32 boundaries, 64-bit immediates.
   - Execution tests, which are the real proof: assemble and run functions that (a) return a constant, (b) add two integer arguments, (c) loop summing 1..n with a backward conditional jump, (d) do double arithmetic taking and returning a double, (e) call back into a Silk `extern "C"` function passed as an address and use its result, (f) read and write memory through a pointer argument. Check results from Silk.
   - Memory tests: a finished block is not writable (verify with a fork-free method such as reading `/proc/self/maps` for the block's range and checking permissions `r-xp`); a block being written is not executable; freeing and reallocating reuses space; many blocks can be allocated.
5. Run `silk check --workspace` at the root and make sure the engine and runtime still check and that adding the workspace member did not change their builds.

## Rules
- Do not modify `modules/engine` or `modules/runtime` sources. The only edits outside `modules/jit` are the workspace member list in the root `silk.toml` and one row in the root `README.md`.
- No external dependencies beyond libc.
- Match the repo's comment style: comments explain why, in plain sentences.
- Every claim in your report must be backed by a command you ran. If something is untested (other OS or architecture), say so.
- Other agents are compiling on this machine; builds may be slow. That is expected.
- Commit on a new local branch `jit/p1-code-memory-asm` in small commits. Do NOT push, do NOT open a pull request.
- Do not start subagents.

## Final report (your last message)
- Branch and commits.
- How Silk calls generated code (direct function-pointer conversion or C trampoline), with the relevant snippet.
- Any Silk language or toolchain limitation you hit that the JIT will have to work around (calling conventions, callee-saved registers, stack alignment, unwinding through generated frames, effects/exceptions crossing generated code).
- The assembler's public API in outline and the instruction coverage achieved.
- Test command and results.
- What is implemented but untested.
