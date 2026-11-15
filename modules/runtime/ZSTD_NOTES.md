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

Everything the runtime asks of Zstandard is the Silk package; `../native/zstd`, which compiled
the C library, is removed, and the runtime links no `ZSTD_*` symbol.

### Verified

| What | How | Result |
| --- | --- | --- |
| Decoder | `../zstd/tests/decode_diff.py`: the bytes, the status and every `ZSTD_decompressStream` call's positions and return value, against libzstd 1.5.7 in the same call pattern; frames of every level, skippable and concatenated frames, window limits, dictionaries, 3000 mutated and truncated frames | 5351 comparisons, 0 differences |
| Compressor, no dictionary | `../zstd/tests/compress_diff.py`: the bytes and every `ZSTD_compressStream2` call's result and positions; levels -131072 to 22, every strategy, parameter overrides and bounds, one-shot and streamed with flushes, windows smaller than the input, checksum, pledged sizes, several frames per context | 2489 cases, 0 failures |
| Compressor, dictionaries | the same with raw, trained and corrupt dictionaries of 1 B to 3 MB, input sizes on both sides of every attach/copy/reload cut-off | 5668 cases, 0 failures (and 2739 one-shot cases identical to Node) |
| Long-distance matching, `nbWorkers` | the ports' own harnesses against a multithreaded build of 1.5.7 | 268 and 371 cases, bytes identical (call traces differ with workers: Differences 1) |
| Runtime against Node 24 | `silk task compat` (`tests/compat.mjs` with `tests/compat-zstd.mjs`: every level on 14 inputs, 120 fuzzed round trips, every parameter's bounds and errors, streams, async, decoding of corrupt input, dictionaries, workers, LDM) | 86 passed, 0 failed |
| `node:zlib/iter` | `tests/iterable-streams-smoke.cjs` | ok |

### Measurements

Release builds of `main` with the C library (`C`) and of this branch (`Silk`), interleaved in
shuffled order, three rounds, `SILKJS_PREPARSE_THREADS=0`, `NODE_OPTIONS` unset, nothing compiling;
`bench/scripts/zstd.cjs` (one case per process; MB/s of uncompressed data, the median of the runs
of a case, then the median over the rounds; peak RSS of the process). Host noise is about 8%.

One-shot `zstdCompressSync`/`zstdDecompressSync` with `chunkSize` 8 MiB (`ZSTD_CHUNK=8388608`),
which shows the codec. The compressed sizes are the same in every row (the bytes are compared by
the tests above):

| case | C MB/s | Silk MB/s | Silk/C | C RSS MiB | Silk RSS MiB | sizes C / Silk |
| --- | --- | --- | --- | --- | --- | --- |
| c:text:-5 | 225.4 | 220.8 | 0.98 | 136 | 139 | 5896760 / 5896760 |
| c:text:1 | 211.1 | 186.9 | 0.89 | 123 | 123 | 3586493 / 3586493 |
| c:text:3 | 165.8 | 162.2 | 0.98 | 124 | 127 | 3549252 / 3549252 |
| c:text:9 | 51.0 | 39.4 | 0.77 | 116 | 119 | 2958542 / 2958542 |
| c:text:19 | 3.1 | 2.8 | 0.90 | 116 | 119 | 447687 / 447687 |
| c:json:-5 | 488.0 | 477.8 | 0.98 | 79 | 82 | 526950 / 526950 |
| c:json:1 | 484.0 | 423.2 | 0.87 | 79 | 82 | 309338 / 309338 |
| c:json:3 | 422.9 | 408.2 | 0.97 | 82 | 85 | 272294 / 272294 |
| c:json:9 | 125.5 | 95.4 | 0.76 | 91 | 94 | 277236 / 277236 |
| c:json:19 | 2.0 | 1.9 | 0.95 | 110 | 113 | 117074 / 117074 |
| c:random:-5 | 302.8 | 311.0 | 1.03 | 115 | 118 | 8388810 / 8388810 |
| c:random:1 | 287.8 | 315.7 | 1.10 | 115 | 118 | 8388810 / 8388810 |
| c:random:3 | 321.5 | 288.5 | 0.90 | 117 | 120 | 8388810 / 8388810 |
| c:random:9 | 214.4 | 198.9 | 0.93 | 136 | 139 | 8388810 / 8388810 |
| c:binary:1 | 193.8 | 177.7 | 0.92 | 137 | 140 | 7954313 / 7954313 |
| c:binary:3 | 121.6 | 130.8 | 1.08 | 135 | 138 | 6816591 / 6816591 |
| c:binary:9 | 37.0 | 28.4 | 0.77 | 143 | 146 | 5996711 / 5996711 |
| c:binary:19 | 3.2 | 2.9 | 0.91 | 141 | 145 | 1291911 / 1291911 |
| d:text:1 | 365.1 | 418.7 | 1.15 | 128 | 131 | 3586493 / 3586493 |
| d:text:3 | 381.0 | 377.2 | 0.99 | 129 | 132 | 3549252 / 3549252 |
| d:text:19 | 390.0 | 420.1 | 1.08 | 180 | 183 | 2573302 / 2573302 |
| d:json:3 | 1460.4 | 1556.1 | 1.07 | 129 | 132 | 272294 / 272294 |
| d:json:19 | 1621.7 | 1588.4 | 0.98 | 164 | 167 | 191189 / 191189 |
| d:random:3 | 534.6 | 513.3 | 0.96 | 114 | 117 | 8388810 / 8388810 |
| d:binary:1 | 312.2 | 316.2 | 1.01 | 137 | 140 | 7954313 / 7954313 |
| d:binary:3 | 333.3 | 332.0 | 1.00 | 134 | 137 | 6816591 / 6816591 |
| d:binary:19 | 253.4 | 286.8 | 1.13 | 204 | 208 | 5409670 / 5409670 |

Level 1 was measured before the BMI2 sequence encoder (`262f19f`), which took the compressor's
CLI from 11-13% behind the C library to 2-6%. Level 9 (and 5 to 12) is the row match finder,
which has no prefetch (Compiler walls 2). Peak RSS is 3 MiB higher in every case, the size of
the package's code and tables in the executable, not of a buffer.

The default `chunkSize` (16 KiB), the streams (`cs`, `ds`: 1 KiB writes) and the thread-pool
calls (`ca`, `da`: four at a time). The one-shot rows here are dominated by the binding's cost per
output chunk (Found in the runtime's binding, 1), for both builds alike. The 9 more bytes of the
`cs` rows are Node's empty trailing frame, which the C build did not write:

| case | C MB/s | Silk MB/s | Silk/C | C RSS MiB | Silk RSS MiB | sizes C / Silk |
| --- | --- | --- | --- | --- | --- | --- |
| c:text:3 | 10.3 | 10.9 | 1.06 | 115 | 118 | 3556322 / 3556322 |
| d:text:3 | 9.7 | 9.5 | 0.98 | 108 | 111 | 3556322 / 3556322 |
| c:binary:1 | 4.6 | 4.6 | 1.00 | 138 | 141 | 7954313 / 7954313 |
| d:binary:1 | 4.7 | 4.6 | 0.98 | 136 | 138 | 7954313 / 7954313 |
| cs:text:3 | 14.9 | 13.4 | 0.90 | 77 | 80 | 655020 / 655029 |
| ds:text:3 | 56.5 | 51.9 | 0.92 | 76 | 79 | 655024 / 655024 |
| cs:json:3 | 18.2 | 16.5 | 0.91 | 76 | 78 | 148683 / 148692 |
| ds:json:3 | 141.0 | 124.7 | 0.88 | 72 | 76 | 148687 / 148687 |
| cs:binary:3 | 15.3 | 13.9 | 0.91 | 95 | 94 | 1561230 / 1561239 |
| ds:binary:3 | 33.5 | 34.0 | 1.01 | 92 | 94 | 1561234 / 1561234 |
| ca:text:3 | 10.3 | 10.3 | 1.00 | 305 | 301 | 3556321 / 3556321 |
| da:text:3 | 9.1 | 9.5 | 1.04 | 229 | 232 | 3556322 / 3556322 |
| ca:binary:1 | 4.4 | 4.4 | 1.00 | 392 | 378 | 7954312 / 7954312 |
| da:binary:1 | 4.4 | 4.2 | 0.95 | 296 | 324 | 7954313 / 7954313 |

An HTTP server that compresses each response (1 MiB at the level shown) with
`Content-Encoding: zstd`, and a client that decodes it (`http.get` piped into
`createZstdDecompress`, five rounds):

| case | C MB/s | Silk MB/s | Silk/C | C RSS MiB | Silk RSS MiB | sizes C / Silk |
| --- | --- | --- | --- | --- | --- | --- |
| http:json:3 | 65.1 | 62.3 | 0.96 | 69 | 72 | 97337 / 97337 |
| http:text:3 | 44.1 | 40.7 | 0.92 | 72 | 74 | 194578 / 194578 |
| http:binary:1 | 41.3 | 40.6 | 0.98 | 86 | 89 | 404568 / 404568 |

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
   and, in the decoder, far match sources. Measured cost: the row match finder (levels 5 to 12) is 1.18 to 1.30 times
   the C library's time; the reference itself built with `NO_PREFETCH` is 1.27 times slower at level
   9 (321 to 331 ms against 250 to 256 ms), which accounts for the gap. A dummy read of the row a few
   positions ahead (`rowTouch` in `../zstd/src/zlazy.silk`) brought level 9 from 1.5 to 1.2 times. Proposed: `Intrinsic.prefetch(pointer: ?*const u8,
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

1. **`ZSTD_c_nbWorkers` >= 1 runs the jobs on the calling thread.** The C build is
   multithreaded; its output depends only on the parameters, the input and where the caller's
   flushes fall, not on thread timing (checked: six runs each at levels 1 to 19 with 2 and 4
   workers gave the same bytes, also between 2 and 4 workers). The port cuts the same jobs,
   with the same overlap, round buffer, serial XXH64 and serial long-distance matching, and
   compresses each job in the call that creates it, so the frame is the same bytes. What each
   call consumes, writes and returns is not: the threaded library returns 1 ("a job is
   running") where the port can already return what is left to flush. The async API still runs
   on the runtime's thread pool, so a worker setting never blocks the loop; it only does not
   make one call faster. Measured with 4 workers on 41 MB: level 3 242 ms (zstd -T4: 88 ms),
   level 19 21.8 s (14.9 s). Using real threads needs a thread pool inside the package; the job
   code is already separate (`../zstd/src/zmt.silk`), so that is a contained change.
2. **Row match finder levels (5 to 12) are 18 to 30% slower** than the C library, for want of a
   prefetch (Compiler walls).


## Upstreaming

No standard library file was copied or changed, so there is nothing to upstream as a fix and no
pull request on silk-lang/silk. The pinned `silk.compress.zstd`, `zstd_block`, `zstd_encode` and
`zstd_checksum` are correct as far as tried; they are slower than the C library and the encoder
does not write its bytes, by design (What the pinned standard library has).

`../zstd` is a complete port of Zstandard 1.5.7 that could replace them: it has no dependency on
the runtime or on Node (only the C allocator and `memcpy`/`memmove`/`memset`), its API is the
reference's (`ZSTD_compressStream2`, `ZSTD_decompressStream`, parameters, dictionaries, error
codes), and its tests compare it with the reference library call by call. Moving it into the
standard library would need its API wrapped in the standard library's style (effects, `Result`,
an `Allocator` in place of `calloc`) and its tests turned into that repository's tests. Whether
to do that is the owner's decision; nothing here depends on it.
