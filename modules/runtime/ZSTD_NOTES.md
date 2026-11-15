# Zstandard in Silk: notes

The runtime's Zstandard (`node:zlib` `zstdCompress`, `zstdDecompress`, their streams, and what is
built on them: `fetch` content decoding, `node:zlib/iter`) is the Silk package
[`../zstd`](../zstd), a port of Zstandard 1.5.7. This file records what the pinned standard
library had, why the port exists, what differs from the C library, and what the compiler or the
standard library would have to gain.

Status of each part is in "State" below; it is updated as the work lands.

## What uses Zstandard in this repository

| Consumer | How | Links the C library? |
| --- | --- | --- |
| `node:zlib` (`src/ext/compression_native.silk`) | `ZSTD_createCStream`, `ZSTD_createDStream`, `ZSTD_freeCStream`, `ZSTD_freeDStream`, `ZSTD_CCtx_setParameter`, `ZSTD_CCtx_setPledgedSrcSize`, `ZSTD_CCtx_loadDictionary`, `ZSTD_CCtx_reset`, `ZSTD_compressStream2`, `ZSTD_DCtx_setParameter`, `ZSTD_DCtx_loadDictionary`, `ZSTD_DCtx_reset`, `ZSTD_decompressStream`, `ZSTD_isError`, `ZSTD_getErrorCode`, `ZSTD_getErrorName`, `ZSTD_getErrorString` | yes, before this change |
| `process.versions.zstd` (`src/ext/os_native.silk`) | `ZSTD_versionString` | yes, before this change |
| `node:zlib/iter`, `internal/streams/iter` | JavaScript on the same native binding | no |
| `fetch` / undici content decoding | JavaScript: `zlib.createZstdDecompress` | no |
| `CompressionStream` (`ext/web/compression.js`) | no Zstandard format | no |
| OpenSSL (`../native/openssl`) | built with `OPENSSL_NO_ZSTD`; `crypto/comp/c_zstd.c` compiles to stubs | no |
| TLS certificate compression (`internal/tls/context.js`) | names `zstd` only to reject it: OpenSSL is built without it | no |
| `../pm`, `../engine` | none | no |
| `../benchkit` `offline-deps` | unpacks a prepared `libzstd.a` for networks that block the build's downloads | no longer needed for the runtime |

So the C library goes when `compression_native.silk` and `os_native.silk` stop naming it.

## What the pinned standard library has (0.1.0-dev.74+205aea3f5b2e)

| Module | What it is | Finding |
| --- | --- | --- |
| `silk.compress.zstd` + `zstd_block` | A streaming decoder with fixed memory and limits | Correct on every reference frame tried (levels 1 to 19, four corpora). No dictionaries. 10 to 15 times slower than libzstd (text, level 1 frame: 310 ms against 22 ms for 16 MiB). Its errors are its own enum, not the reference's codes. |
| `silk.compress.zstd_encode` | A streaming encoder, levels 1 to 22 | Valid frames that the reference decodes; ratio within about 1% of the reference. Not the reference's bytes (documented as such). 1.6 to 3 times slower at levels 1 to 9, about the same at 19. No negative levels, no dictionaries, no parameters beyond level, window log, checksum and content size, no long-distance matching. |
| `silk.compress.zstd_checksum` | XXH64 | Correct; byte at a time. |

Measured on this machine with a standalone program on the standard library (`ZstdEncoder.encode`,
`Zstd.step`) against the reference `zstd` 1.5.7 command (`--single-thread`), wall time for the
whole process, one run each, while another build was running (so: order of magnitude only):

| Input | Level | Reference compress | Standard library compress | Sizes (ref / std) | Reference decompress | Standard library decompress |
| --- | --- | --- | --- | --- | --- | --- |
| text 16 MiB | 1 | 0.060 s | 0.114 s | 3586529 / 3589525 | 0.022 s | 0.327 s |
| text 16 MiB | 3 | 0.072 s | 0.132 s | 3556326 / 3554032 | | |
| text 16 MiB | 9 | 0.279 s | 0.769 s | 2958410 / 2963394 | | |
| text 16 MiB | 19 | 7.18 s | 8.92 s | 2573306 / 2601015 | 0.050 s | 0.227 s |
| binary 32 MiB | 1 | 0.129 s | 0.334 s | 15873663 / 15888007 | 0.051 s | 0.774 s |
| binary 32 MiB | 9 | 0.905 s | 2.517 s | 11615585 / 11632717 | | |
| binary 32 MiB | 19 | 17.1 s | 18.1 s | 10405461 / 10541206 | 0.074 s | 0.689 s |
| json 12 MiB | 3 | 0.013 s | 0.023 s | 273007 / 266470 | 0.010 s | 0.132 s |

### Why the runtime does not use those modules as they are

The task was to use the standard library where it is right and fast, and to fix a local copy
where it is not. The decoder's slowness and the encoder's different bytes are not local defects:
the decoder decodes Huffman and sequences a symbol at a time through checked slices, and the
encoder is its own design (its own block cutting, match finders and table choices), so making
either match libzstd means replacing its core. The port in `../zstd` is therefore new code that
follows the reference file by file, and the pinned modules were used for comparison and as a
second decoder in tests, not copied. Nothing of it is specific to Node or to SilkJS: the
runtime's adapter is `src/ext/compression_native.silk`, and the package has no dependency but the
C allocator and `memcpy`/`memmove`/`memset`. Whether it should replace the standard library's
modules is the owner's decision (see "Upstreaming").

## State

First release build of the runtime on the Silk package (no `ZSTD_*` symbol is linked), against
Node 24 with the cases of `tests/compat-zstd.mjs`:

| Case | C library build of `main` | Silk build |
| --- | --- | --- |
| zstd-levels-small, -fast, -lazy, -optimal (every level on 14 inputs) | pass | pass |
| zstd-round-trips-a, -b (120 fuzzed round trips) | pass | pass |
| zstd-parameters (bounds and errors of every parameter, overrides, pledged size, `info`) | pass | pass |
| zstd-streams (pieces, flushes, windows, async) | fails: Node's empty trailing frame | pass |
| zstd-decoding (skippable, concatenated, corrupt, truncated, window limits) | pass | pass |
| zstd-dictionaries | fails: one error message | fails: the compressor has no dictionaries yet |
| zstd-workers-ldm | pass (Node's own stream truncation excepted) | fails: 16 of 54, all `nbWorkers` > 0 |

The compressor's own differential test (`../zstd/tests/compress_diff.py`, every call's return
value and positions as well as the bytes) covers levels -131072 to 4 exactly; the lazy and
optimal parsers, long-distance matching, workers and compressor dictionaries are being finished.
The C library stays in `../native/zstd` until those pass.

## Compiler walls

Each is reduced to what the port needed. None was worked around with C.

1. **No integer-to-pointer conversion, and pointer offsets only through `Pointer.at`.**
   `zstd` addresses a window as `base + index` where `base` may lie before the buffer (after the
   window slides, or with a dictionary). The port keeps a base pointer and a `usize` index and
   forms `Pointer.at(base, index)` with an index that can be "negative" (wrapped). It works, but
   whether an offset outside the allocation is defined is not stated anywhere.
   Proposed: `Pointer.fromAddress<T>(address: usize) -> ?*mut T` and
   `Pointer.offset<T>(pointer: [*]const T, delta: isize) -> [*]const T` documented as plain address
   arithmetic (no in-bounds assumption).
2. **No prefetch.** The reference prefetches hash rows, the match candidate of the next position
   and, in the decoder, far match sources. Proposed: `Intrinsic.prefetch(pointer: ?*const u8,
   locality: u32) -> ()`, a no-op where the target has none.
3. **No branch hints.** `LIKELY`/`UNLIKELY` shape the reference's hot loops (sequence execution,
   the lazy parser). `@cold` on a function exists; a hint on a condition does not. Proposed:
   `Intrinsic.likely(condition: bool) -> bool` / `Intrinsic.unlikely`.
4. **A parameter of type reference-to-raw-pointer does not parse** (`current: &mut [*]const u8`
   is read as the start of a slice type). Minimal case:
   `unsafe fn set(target: &mut [*]const u8, value: [*]const u8) -> () { target.* = value }`.
5. **No symbol alias for a foreign function.** Two Silk declarations of one C symbol with
   different parameter lists (a variadic `printf` in a test tool) are rejected, and there is no
   variadic foreign declaration. Only the test tools wanted it.
6. **A function that calls a foreign function is never inlined, and `@inlineAlways` on it is
   ignored without a diagnostic.** The function is emitted `noinline` with a foreign personality.
   Found when a `@features("bmi2")` wrapper around the sequence decoder's body ran the generic
   body: the body called `memmove` for the rare match that reaches into a dictionary. 43.2 M
   instructions for a 4 MB text frame became 37.6 M once the calls went through plain Silk
   wrappers (`mem.copyBytes`, `mem.moveBytes`, `mem.fillBytes`); the C library takes 35.3 M.
   Minimal case:
   ```silk
   unsafe extern "C" fn labs(v: i64) -> i64
   @inlineAlways
   unsafe fn body(a: u64, n: u64) -> u64 {
     if n == 9 { return i64.toU64(unsafe labs(u64.wrappingToI64(a))) }
     return u64.shiftRight(u64.shiftLeft(a, n & 63), (64 - n) & 63)
   }
   ```
   `silk build --emit llvm-ir` shows `define internal ... noinline ... personality ptr
   @__silk_foreign_personality` for `body`; without the `labs` call it is `alwaysinline`.
   Wanted: either inline it (calls that cannot unwind, such as libc's, need no personality), or
   report that the attribute cannot be honoured.
7. **The check server replays stale diagnostics** (silk-lang/silk#3116): `silk check` kept
   reporting an unused import after the file changed; `--no-server` is right.

## Found in the runtime's binding, not in the codec

Seen while measuring the build of `main` with the C library; they are in
`ext/node/internal/compression/handle.js` and `src/ext/compression_native.silk`, which zlib and
Brotli share.

1. **The default chunk size costs about 2 ms per output chunk, for every codec.** 16 MiB of text,
   release build of `main`, `SILKJS_PREPARSE_THREADS=0`:

   | Call | `chunkSize` 16384 (default) | `chunkSize` 1 MiB | Node 24, default |
   | --- | --- | --- | --- |
   | `zstdDecompressSync` | 2308 ms | 74 ms | 48 ms |
   | `zstdCompressSync`, level 3 | 2300 ms | 142 ms | 88 ms |
   | `gzipSync` level 1 + `gunzipSync` | 5193 ms | | 254 ms |

   The time grows with input size times the number of output chunks. The likely cause, not yet
   verified: `_write()` in `handle.js` takes a snapshot of the remaining input on every write, and
   `zlib.js` writes again each time the 16 KiB output buffer fills. Not fixed here: it is shared
   with the zlib and Brotli work. Until it is, a codec's speed shows through the runtime only at
   slow levels or with a large `chunkSize`; the benchmark table gives both.
2. **Node appends an empty frame** (9 bytes; 13 with a dictionary identifier) when a
   `ZstdCompress` stream's last chunk is written after `end()` was called: the chunk goes out with
   `ZSTD_e_end`, then `_flush` asks for `ZSTD_e_end` again and libzstd starts and ends a new
   frame. The binding held a finished compressor back and did not. Fixed in
   `compression_native.silk`.
3. **A rejected Zstandard dictionary** reported "Initialization failed" where Node reports
   "Failed to load zstd dictionary". Fixed in `handle.js`.
4. **Node loses output with `ZSTD_c_nbWorkers` on a stream**: `ZSTD_compressStream2` returns
   before the workers finish and Node's stream stops asking, so the result is cut short or empty,
   depending on timing. The runtime gives the whole frame, and keeps doing so.

## Differences from the C library

(filled in as parts land)

## Upstreaming

(filled in at the end)
