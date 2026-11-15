# Brotli in Silk

The runtime's Brotli (`node:zlib`'s `brotliCompress`, `brotliDecompress`, their sync forms and
streams, and through them `fetch`'s `Content-Encoding: br`, undici and `CompressionStream`) is the
Silk package [`../brotli`](../brotli), a port of google/brotli v1.2.0 with upstream commit 0ed4268
in the decoder, which is what Node 24 bundles. No Brotli C is compiled or linked.

This file records what was found, what was decided and why, and what is still open.

## What used the C library

Every use went through 15 symbols:

| Symbol | Declared in | Called from |
| --- | --- | --- |
| `BrotliEncoderCreateInstance`, `BrotliEncoderDestroyInstance`, `BrotliEncoderSetParameter`, `BrotliEncoderCompressStream`, `BrotliEncoderIsFinished`, `BrotliEncoderHasMoreOutput`, `BrotliEncoderPrepareDictionary`, `BrotliEncoderDestroyPreparedDictionary`, `BrotliEncoderAttachPreparedDictionary` | `src/ext/compression_abi.silk` | `src/ext/compression_native.silk` |
| `BrotliDecoderCreateInstance`, `BrotliDecoderDestroyInstance`, `BrotliDecoderSetParameter`, `BrotliDecoderDecompressStream`, `BrotliDecoderGetErrorCode`, `BrotliDecoderAttachDictionary` | `src/ext/compression_abi.silk` | `src/ext/compression_native.silk` |
| `BrotliDecoderVersion` | `src/ext/os_abi.silk` | `src/ext/os_native.silk` (`process.versions.brotli`) |

Nothing else linked against it:

- `fetch` (`ext/web/fetch/transport.js`), the bundled undici, `CompressionStream` and
  `DecompressionStream` (`ext/node/internal/webstreams/compression.js`) and the iterable streams
  (`ext/node/internal/streams/iter/compression.js`) all go through `node:zlib`.
- OpenSSL is built with `OPENSSL_NO_BROTLI` (`../native/openssl/generated/include/openssl/configuration.h`);
  `crypto/comp/c_brotli.c` compiles to stubs. TLS certificate compression with Brotli is rejected
  in JavaScript (`ext/node/internal/tls/context.js`).
- nghttp2 does not reference Brotli.
- The package manager (`../pm`) reads tarballs with the standard library's `silk.compress.inflate`
  and `silk.compress.tar`; it has no Brotli.
- `../benchkit/src/runtimes.silk` (`offline-deps`) fetched the Brotli sources for the C build.

## What the standard library had (Silk 0.1.0-dev.74+205aea3f5b2e)

| Module | What it is | Verdict |
| --- | --- | --- |
| `silk.compress.brotli_tables` | The static dictionary (122,784 bytes), the 121 transforms and the context lookup, generated from google/brotli v1.1.0 | Used as it is. The dictionary is the same in v1.2.0; a test checks its SHA-256 against the reference. |
| `silk.compress.brotli` | A decoder for all of RFC 7932 | Not used: see below. |
| `silk.compress.brotli_encode` | An encoder, qualities 0 to 11 | Not used: see below. |

Measured against Node 24.22.1 (Brotli 1.2.0) on Linux x86-64, 2026-11-15, one process per run:

- **The encoder is valid but never byte-equal.** Every stream it wrote decoded correctly with the
  C library. At no quality did a non-trivial input compress to the same bytes: it is a different
  encoder that borrows the reference's hash tables and shortest-path search, with its own
  meta-block layout. Sizes ranged from 12% smaller (quality 0 and 1, where it does more work than
  the reference's one-pass and two-pass compressors) to 2.4% larger (quality 2), and within 1.3%
  from quality 5. It was 2 to 5 times slower than C at qualities 0 to 9 (768 KB of JavaScript at
  quality 5: 75 ms against 18 ms; 30 MB: 290 ms against 58 ms) and up to 9 times slower at
  quality 11 on incompressible input (3.5 s against 0.38 s for 1 MB). It takes only a quality and
  a window size: no mode, `LGBLOCK`, `SIZE_HINT`, `NPOSTFIX`/`NDIRECT`, large window,
  `DISABLE_LITERAL_CONTEXT_MODELING`, `EMIT_METADATA` or dictionaries. It allocates everything
  when it is made (quality 9 on an empty input costs 35 ms of allocation and zeroing).
- **The decoder is fast and decodes everything the reference encoder wrote, but is a different
  design.** It reports 14 reasons where the C library has 30 error codes that Node exposes by name
  (`ERR__ERROR_FORMAT_PADDING_1` and so on), allocates its whole window when made (16 MiB, where C
  allocates the ring buffer when the stream's window is known and grows it with the data), and has
  no large window, no compound dictionary, no `DISABLE_RING_BUFFER_REALLOCATION`. Which error a
  corrupt stream gets, at which call, and how much output each call writes all follow from the
  order in which the C decoder reads and checks, including its two paths (the "safe" one near the
  end of the input).

Node's users compare and hash compressed bytes, and see the decoder's error codes, so the target
is the C library's exact behaviour. Reaching it from these two modules would have meant replacing
their internals with the reference's algorithms piece by piece. So `../brotli` is a direct port of
the C sources instead (same algorithms, same order of operations, same integer and floating-point
arithmetic), behind an API shaped like the C one, and the two standard library modules were left
alone: there is no local copy of them and no fix to upstream.

Whether `../brotli` should replace or join the standard library's Brotli is the owner's decision.
It is written to be movable: nothing in it knows about Node or the runtime.

## Status

| Part | State | Verified by |
| --- | --- | --- |
| Decoder | Done | `modules/brotli/tests/differential.py` against the C library: `decode` 355/355 and `corrupt` 2000/2000 (new seeds), plus 939 dictionary and large-window cases; every call's result, consumed and written bytes and error code match. In the runtime, `tests/brotli/decode.cjs` (177 reference streams at every quality and window size, 2,500 corrupted ones, and a hand-built `FORMAT_BLOCK_SWITCH` stream) prints the same 2,678 lines as Node 24. Same speed and peak memory as the C library (table below). |
| Encoder, qualities 0 to 11 | Done: the C library's bytes | `differential.py` against the C library on the whole package: `encode` at qualities 0 to 11 480/480, at 10 and 11 230/230, `params` 636/636 (every parameter and bound at the default quality 11, with and without large window), `large` 16/16 (6 to 8 MB inputs, windows of 16 to 30 bits, streamed with flushes). While porting, seeds 1 to 5 at 600 rounds for qualities 2 to 9 and at 300 rounds for 10 and 11, a parameter matrix at every quality (9,312 cases), and inputs up to 36 MB. |
| Encoder, prepared dictionaries | Done: the C library's bytes | `dictionary` 300/300 at every quality (seed 401; seeds 1 to 6 while porting), a stress run of 2 to 20 attached dictionaries of 0 B to 16 MiB attached before and after the stream starts (1,549/1,549 for each of four seeds), and Node 24's `brotliCompressSync(data, { dictionary })` writing the same bytes in 720/720 cases. With a 64 KiB dictionary the search adds 6 to 9 ms where C adds 4 to 6 (4 MB input at quality 5). One deliberate deviation: where C reads past an empty chunk attached after a non-empty one (undefined behaviour), the copy stops. |
| The runtime as a whole | All non-dictionary Brotli behaviour matches Node 24 | `silk task compat` (Node 24.22.1 as the reference), 2026-11-15: 78 of 79 cases pass on the Silk Brotli build, and the 75 cases that are not about Brotli pass on both builds. `brotli-decode`, `brotli-streams` and `brotli-corrupt` pass, so every compressed digest at every quality and parameter, every stream's chunking and every decoder error matches Node; `brotli-oneshot` fails only on its dictionary lines (`ERR_ZLIB_INITIALIZATION_FAILED`, the stage still being ported). The C-library build fails `brotli-streams` on `reset()`, the bug fixed above. `tests/web-boundaries-smoke.cjs` and `tests/iterable-streams-smoke.cjs` pass on both. |
| Runtime | Links no Brotli C | `modules/native/brotli` is gone; the release build compiles 70 fewer C objects and none of its objects defines a C Brotli function. |

`reset()` on a Brotli stream now drops its parameters and dictionary, as Node's
`ResetStream()` does (it calls `Init()` with no dictionary and sets no parameters). Before, the
runtime re-applied them and differed from Node after a reset.

### Decoder speed (Silk tool against the C tool, the same driver, Linux x86-64)

Wall time of three runs each; peak RSS was 12 to 13 MB for both everywhere.

| Stream | C | Silk |
| --- | --- | --- |
| 30 MB of JavaScript at quality 1 (7.3 MB) | 0.108–0.115 s | 0.109–0.134 s |
| the same at quality 5 (143 KB) | 0.053–0.077 s | 0.047–0.051 s |
| at quality 9 | 0.058–0.061 s | 0.045–0.050 s |
| at quality 11 | 0.052–0.078 s | 0.057–0.063 s |
| 564 KB binary at quality 5 | 0.005–0.008 s | 0.005–0.007 s |
| 1 MB random at quality 5 | 0.004 s | 0.004 s |

The runtime-level before/after table (`bench/brotli/compare.py`) is below once the encoder is done.

### Encoder speed (Silk tool against the C tool, the same driver, Linux x86-64)

Measured by the porting runs on a shared 4-core machine (best CPU time of several interleaved
runs; peak RSS). The output is identical in every row.

| Input | Quality | Silk / C time, one-shot | 4 KiB writes | Peak RSS C / Silk (MB) |
| --- | --- | --- | --- | --- |
| text 8 MB (undici.js) | 4 / 6 / 9 | 0.98 / 1.06 / 1.09 | 0.94 / 1.03 / 1.10 | 35.6 / 35.6, 42.5 / 42.8, 66.5 / 66.7 |
| C source 4 MB | 4 / 6 / 9 | 1.00 / 1.06 / 0.98 | 1.01 / 0.99 / 0.95 | 16.7 / 16.7, 16.7 / 16.7, 43.2 / 43.5 |
| JSON and HTML 8 MB | 4 / 6 / 9 | 0.93 / 1.03 / 1.00 | 0.92 / 1.01 / 1.07 | 37.4 / 37.4, 36.8 / 37.0, 61.2 / 61.6 |
| random 8 MB | 4 / 6 / 9 | 1.10 / 1.05 / 1.13 | 0.97 / 1.00 / 1.19 | 30.6 / 30.5, 25.8 / 25.9, 52.7 / 52.8 |
| binary 16 MB (node) | 4 / 6 / 9 | 1.12 / 1.15 / 1.02 | 1.07 / 1.20 / 1.01 | 36.5 / 36.5, 45.8 / 46.0, 74.1 / 74.5 |
| text 768 KB (undici.js) | 10 / 11 | 1.10 / 1.05 | 1.08 / 1.05 | 16.0 / 16.3, 22.1 / 22.2 |
| C source 651 KB | 10 / 11 | 1.08 / 1.06 | 1.04 / 1.12 | 15.0 / 15.2, 21.8 / 22.0 |
| JSON and HTML 2 MB | 10 / 11 | 1.04 / 1.04 | 1.04 / 1.06 | 31.7 / 31.9, 40.6 / 40.8 |
| random 1 MB | 10 / 11 | 1.06 / 0.95 | 1.02 / 0.97 | 18.5 / 18.7, 19.5 / 19.7 |
| binary 1 MB (node) | 10 / 11 | 1.12 / 1.07 | 1.13 / 1.07 | 36.5 / 36.8, 28.3 / 28.5 |
| binary 4 MB (node) | 10 / 11 | 1.17 / 1.05 | | 64.6 / 66.4, 67.4 / 67.7 |

Qualities 0 and 1 are within noise of C. The encoder is slower than C by up to 10% at most
qualities, and up to 15 to 20% on binary input at qualities 6 and 10 and on random input at 9.
Instruction counts are within 2 to 8% of C (callgrind: quality 11 on text is 3% below C); cache
misses and branch mispredictions are the same or fewer. What is left is spread over the bounds
and overflow checks of ordinary arithmetic, loop invariants reloaded after stores the compiler
cannot prove do not alias, and the walls below.

## Compiler walls

Each one was checked on a minimal case compiled with `silk build --release` (Silk
0.1.0-dev.74+205aea3f5b2e, x86-64) and read in the disassembly. None of them blocks the port;
together they are most of the encoder's remaining time gap.

- **No `f64.log2`.** The encoder's cost model calls `log2` on values of 256 and above
  (`FastLog2`). The standard library has `f64.log` only, and `log(x) / ln 2` does not round the way
  `log2(x)` does, which changes which match or block split wins and so the output bytes. The port
  declares libm's `log2` (`unsafe extern "C" fn log2(value: f64) -> f64`), which is also what makes
  it agree with a C build on the same machine. Proposed: `pub fn log2(value: f64) -> f64` in
  `silk.num.f64`, lowered to the `llvm.log2.f64` intrinsic.
- **Every float-to-integer conversion is range-checked.** `f64.toI64`, `f64.toUsize` and the
  `Intrinsic.f64To*` they use emit two comparisons and a trap branch before `cvttsd2si`. The
  encoder's `BrotliPopulationCost` does `(size_t)(log2p + 0.5)` in its innermost loop, on values
  that are in range by construction. Minimal case:
  `fn round(x: f64) -> usize { return f64.toUsize(x + 0.5) }` compiles to a compare-and-trap
  sequence and the conversion, where C's `(size_t)(x + 0.5)` is the conversion alone. Proposed:
  `pub unsafe fn toUsizeUnchecked(value: f64) -> usize` (and the other widths) in `silk.num.f64`,
  lowered to a plain `fptoui`/`fptosi`.
- **A function that calls an `extern "C"` function is not inlined, even with `@inlineAlways`.**
  `FastLog2` looks up a table below 256 and calls `log2` above; the call kept the table lookup
  from inlining into its callers. The port moves the `log2` call into an `@inlineNever` helper so
  the rest inlines. Minimal case: `@inlineAlways fn f(x: u32) -> f64 { if x < 256 { return T[x] }
  return unsafe log2(u32.toF64(x)) }` stays a call at every use. Proposed: inline such functions
  as other ones are, keeping the extern call as a call.
- **`i32.wrappingToUsize` is five instructions.** It compiles to `mov`, `movabs`, `or`, `test`,
  `cmovns` where C's `(size_t)(int)` sign extension is one `movslq`. The port uses an xor-and-subtract helper.
  Proposed: lower it to `sext`.
- **Shift counts are range-checked unless masked.** `u32.shiftLeft(a, b)` compares `b` with 32
  and traps on every shift; the port masks counts (`& 31`, `& 63`) where C relies on them being in range.
  Proposed: an unchecked shift (`unsafe fn shiftLeftUnchecked`), or dropping the check when the
  count is provably in range.
