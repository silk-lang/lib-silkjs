# Brotli in Silk

The runtime's Brotli is to become (`node:zlib`'s `brotliCompress`, `brotliDecompress`, their sync forms and
streams, and through them `fetch`'s `Content-Encoding: br`, undici and `CompressionStream`) the
Silk package [`../brotli`](../brotli), a port of google/brotli v1.2.0 with upstream commit 0ed4268
in the decoder, which is what Node 24 bundles.

**State: work in progress.** The port is being written; the runtime still links the C library
(`../native/brotli`) until the port passes the differential suites. `src/ext/compression_brotli.silk`
is the adapter that will replace the C symbols; it is not imported or compiled yet.

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
| Encoder, qualities 0 and 1 | Done | `encode --quality 0,1` byte-equal to the C library (130/130 and more seeds). |
| Encoder, qualities 2 to 11 | Being ported | (placeholder output: valid streams, not the C library's bytes) |
| Encoder, prepared dictionaries | Not ported yet | |
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

## Compiler walls

(Filled in as the port proceeds.)

- **No `f64.log2`.** The encoder's cost model calls `log2` on values of 256 and above
  (`FastLog2`). The standard library has `f64.log` only, and `log(x) / ln 2` does not round the way
  `log2(x)` does, which changes which match or block split wins and so the output bytes. The port
  declares libm's `log2` (`unsafe extern "C" fn log2(value: f64) -> f64`), which is also what makes
  it agree with a C build on the same machine. Proposed: `pub fn log2(value: f64) -> f64` in
  `silk.num.f64`, lowered to the `llvm.log2.f64` intrinsic.
