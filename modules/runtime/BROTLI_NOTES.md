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
| The runtime as a whole | Matches Node 24 | `silk task compat` (Node 24.22.1 as the reference), 2026-11-15, on the final build: 79/79, including `brotli-decode`, `brotli-oneshot` (every quality, parameter, bound and dictionary), `brotli-streams` and `brotli-corrupt`. The C-library build fails `brotli-streams` on `reset()`, the bug fixed above. `tests/web-boundaries-smoke.cjs` and `tests/iterable-streams-smoke.cjs` pass on both builds. |
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

## Runtime measurements (before and after)

`bench/brotli/compare.py --a <runtime on the C library> --b <runtime on this package> --rounds 5`,
Linux x86-64, 4 CPUs, 2026-11-15, nothing else running; medians of 5 interleaved rounds; MB/s of
input (compress) or output (decompress); `SILKJS_PREPARSE_THREADS=0`, `NODE_OPTIONS` unset. The
compressed output was byte-identical in every case. These numbers are from before the speed work
that follows the port; see below for that.

| Case | Input | Quality | C MB/s | Silk MB/s | Silk/C | C peak MiB | Silk peak MiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| compress | text | 1 | 150.1 | 106.6 | 0.71 | 45 | 48 |
| compress | text | 4 | 63.0 | 58.5 | 0.93 | 52 | 54 |
| compress | text | 6 | 36.2 | 32.4 | 0.89 | 53 | 56 |
| compress | text | 9 | 17.6 | 16.6 | 0.95 | 81 | 83 |
| compress | text | 11 | 0.6 | 0.6 | 1.00 | 66 | 69 |
| decompress | text | 5 | 347.2 | 277.2 | 0.80 | 51 | 53 |
| compress | html | 1 | 172.9 | 167.8 | 0.97 | 51 | 53 |
| compress | html | 4 | 70.0 | 69.8 | 1.00 | 60 | 63 |
| compress | html | 6 | 41.3 | 31.7 | 0.77 | 61 | 64 |
| compress | html | 9 | 18.0 | 19.0 | 1.06 | 87 | 90 |
| compress | html | 11 | 0.6 | 0.6 | 0.95 | 81 | 83 |
| decompress | html | 5 | 423.1 | 397.4 | 0.94 | 59 | 62 |
| compress | json | 1 | 148.4 | 153.0 | 1.03 | 53 | 56 |
| compress | json | 4 | 68.3 | 65.2 | 0.95 | 62 | 65 |
| compress | json | 6 | 42.8 | 36.6 | 0.86 | 63 | 66 |
| compress | json | 9 | 19.8 | 17.0 | 0.86 | 89 | 92 |
| compress | json | 11 | 0.6 | 0.5 | 0.93 | 81 | 84 |
| decompress | json | 5 | 448.8 | 409.4 | 0.91 | 61 | 64 |
| compress | random | 1 | 186.0 | 187.5 | 1.01 | 50 | 52 |
| compress | random | 4 | 106.4 | 101.7 | 0.96 | 55 | 58 |
| compress | random | 6 | 91.6 | 87.3 | 0.95 | 56 | 59 |
| compress | random | 9 | 48.3 | 41.5 | 0.86 | 84 | 86 |
| compress | random | 11 | 2.1 | 2.0 | 0.93 | 60 | 62 |
| decompress | random | 5 | 526.2 | 420.2 | 0.80 | 56 | 58 |
| compress | binary (16 MB) | 1 | 6.0 | 5.9 | 0.98 | 109 | 112 |
| compress | binary | 4 | 6.6 | 6.1 | 0.93 | 121 | 123 |
| compress | binary | 6 | 7.3 | 6.9 | 0.94 | 119 | 122 |
| compress | binary | 9 | 3.5 | 3.5 | 1.01 | 145 | 148 |
| compress | binary | 11 | 0.5 | 0.5 | 0.96 | 127 | 130 |
| decompress | binary | 5 | 7.6 | 7.5 | 0.99 | 116 | 119 |
| compress, 4 KiB writes | text | 1 / 4 / 6 / 9 | 29.5 / 27.6 / 16.0 / 12.1 | 28.6 / 31.2 / 15.3 / 11.2 | 0.97 / 1.13 / 0.96 / 0.92 | 46–81 | 48–84 |
| compress, 4 KiB writes | html | 11 | 0.6 | 0.5 | 0.96 | 81 | 84 |
| decompress, 1 KiB writes | text / binary | 5 | 45.9 / 29.5 | 42.8 / 27.2 | 0.93 / 0.92 | 51 / 116 | 53 / 119 |
| compress, 8 at once on the pool | json q5 / text q9 | | 130.4 / 53.0 | 116.5 / 50.1 | 0.89 / 0.95 | 133 / 336 | 134 / 339 |
| `fetch` of a `Content-Encoding: br` response, 40 times | html | 5 | 109.1 | 106.3 | 0.97 | 72 | 77 |

Reading it:

- (This table is from before the speed work.) Host noise is about 8%. Several rows are within it.
  Real gaps, confirmed by instruction counts:
  the **decoder** executes 14 to 25% more instructions than C on literal- and command-heavy
  streams (768 KB of JavaScript: 17.5M against 15.3M at quality 1, 13.8M against 11.5M at 5,
  12.9M against 10.3M at 11; in the runtime, `processCommands` 255M against C's `ProcessCommands`
  198M for 20 decodes). The earlier tool-level comparison showed parity because its input was one
  file repeated 40 times, which decodes mostly as long copies. In the encoder, the gaps measured by
  the porting runs above. Both gaps were then closed (next sections).
- **Peak RSS is 2 to 3 MiB higher in every row, and already at a bare start** (`-e 0`: 34.5 MiB on
  the C library, 37.1 to 37.5 MiB on the port, stable to 0.1 MiB). It is not allocation: the
  executable is 467 KB larger (`.text` +277 KB, `.rodata` +193 KB, `.data` unchanged), and the
  resident pages of a start, counted per section from `/proc/self/pagemap`, are `.text` 22.9 MiB
  against 21.5, `.rodata` 2.9 against 2.5, the writable image 11.7 against 11.2. A start already
  keeps two thirds of the 32 MiB code section resident in both builds because the startup
  function order that `tools/build.py` hands the linker is stale: only 38 of the 896 Silk names in
  `tools/startup-order.txt` exist in either executable. With the startup code scattered, the new
  code changes which pages a start touches. Regenerating the order is a change for the whole
  runtime and is left to a separate task.
- The asynchronous form still runs on the thread pool (`compress, 8 at once on the pool`): eight
  compressions at once go at the same rate as with the C library.

### After the decoder's speed work

Instruction counts of the decoder (the differential tools, whole process, 16 KiB outputs), C
against Silk: 768 KB of JavaScript at quality 1, 5, 11: 15.3M / 14.8M, 11.6M / 11.8M, 10.3M /
10.5M; 2 MB of JSON at 5 and 11: 48.0M / 48.4M, 46.5M / 45.6M; 2 MB of HTML: 44.9M / 44.9M,
42.6M / 42.7M; 16 MB binary at 5: 398M / 416M (+4.6%, mostly reading and building Huffman
tables). Wall time 0.95 to 1.04 of C on all of these; peak RSS unchanged.

### After the encoder's speed work

Instruction counts against the C library (the differential tools, whole process): quality 1 on
the runtime benchmark's text 27.5M against 26.8M (was 1.29x, now 1.03x), quality 6 1.01x,
quality 10 1.04x; across qualities 0 to 9 on text, JSON, HTML, random and binary, and 10 and 11
on HTML, random and binary, 0.91 to 1.02x, except qualities 2 to 5 on binary (1.03 to 1.08x) and
3 and 5 on text and JSON (1.03 to 1.06x). Time follows the instruction counts within this host's
noise, except binary at quality 6 (equal instructions and simulated cache behaviour, about 6%
slower; see the `Slice.copyInto` wall). Peak RSS equal within 0.3 to 2.2 MB.

### After the speed work (final build)

The same comparison on the final build (compat 79/79), 9 interleaved rounds; Silk/C is the
median of the per-round ratios. Compressed bytes identical in every row. **Median Silk/C 1.00.**

| Case | Input | Quality | C MB/s | Silk MB/s | Silk/C | C peak MiB | Silk peak MiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| compress | text | 1 | 154.9 | 152.4 | 0.97 | 45 | 48 |
| compress | text | 4 | 59.4 | 61.8 | 1.02 | 52 | 54 |
| compress | text | 6 | 35.9 | 36.2 | 1.01 | 53 | 56 |
| compress | text | 9 | 17.5 | 18.1 | 1.00 | 81 | 83 |
| compress | text | 11 | 0.6 | 0.6 | 1.03 | 66 | 69 |
| decompress | text | 5 | 344.2 | 325.3 | 0.95 | 51 | 53 |
| compress | html | 1 | 177.5 | 186.9 | 1.06 | 51 | 53 |
| compress | html | 4 | 73.0 | 74.2 | 1.03 | 60 | 63 |
| compress | html | 6 | 43.4 | 44.1 | 1.04 | 61 | 64 |
| compress | html | 9 | 19.3 | 20.0 | 1.06 | 87 | 90 |
| compress | html | 11 | 0.6 | 0.6 | 1.00 | 81 | 83 |
| decompress | html | 5 | 436.9 | 394.8 | 0.93 | 59 | 62 |
| compress | json | 1 | 162.9 | 162.3 | 1.00 | 53 | 55 |
| compress | json | 4 | 63.7 | 70.9 | 1.14 | 62 | 64 |
| compress | json | 6 | 41.5 | 42.3 | 0.98 | 63 | 66 |
| compress | json | 9 | 20.4 | 22.6 | 1.06 | 89 | 92 |
| compress | json | 11 | 0.6 | 0.6 | 0.98 | 81 | 83 |
| decompress | json | 5 | 440.2 | 395.2 | 0.92 | 61 | 64 |
| compress | random | 1 | 181.8 | 190.5 | 1.05 | 50 | 52 |
| compress | random | 4 | 110.2 | 109.9 | 0.95 | 55 | 57 |
| compress | random | 6 | 91.6 | 89.5 | 0.94 | 57 | 59 |
| compress | random | 9 | 46.6 | 48.2 | 1.02 | 83 | 86 |
| compress | random | 11 | 2.4 | 2.7 | 1.12 | 60 | 62 |
| decompress | random | 5 | 540.8 | 537.1 | 0.97 | 56 | 58 |
| compress | binary | 1 | 6.3 | 6.2 | 0.93 | 109 | 112 |
| compress | binary | 4 | 6.6 | 6.6 | 0.98 | 121 | 123 |
| compress | binary | 6 | 7.7 | 7.7 | 1.02 | 119 | 121 |
| compress | binary | 9 | 3.6 | 3.6 | 1.00 | 145 | 147 |
| compress | binary | 11 | 0.6 | 0.6 | 1.04 | 127 | 129 |
| decompress | binary | 5 | 7.5 | 7.4 | 0.97 | 116 | 119 |
| compress-stream | text | 1 | 35.0 | 30.6 | 0.88 | 46 | 48 |
| compress-stream | text | 4 | 32.3 | 26.6 | 0.93 | 49 | 52 |
| compress-stream | text | 6 | 19.9 | 22.5 | 1.05 | 51 | 54 |
| compress-stream | text | 9 | 11.3 | 12.5 | 0.99 | 81 | 83 |
| compress-stream | html | 11 | 0.6 | 0.6 | 1.06 | 81 | 84 |
| decompress-stream | text | 5 | 46.2 | 45.3 | 0.95 | 51 | 53 |
| decompress-stream | binary | 5 | 32.5 | 28.2 | 0.91 | 116 | 119 |
| compress-async | json | 5 | 128.3 | 131.9 | 1.02 | 133 | 135 |
| compress-async | text | 9 | 54.5 | 52.8 | 1.01 | 336 | 339 |
| fetch | html | 5 | 114.3 | 117.2 | 1.01 | 72 | 74 |

- Every row is within this host's noise (about 8% per sample, more in the streamed rows, whose
  time is mostly JavaScript stream overhead: the encoder is about 20 of their 44 ms). The rows
  that read lowest were measured again alone: decompressing the 2 MB of JSON 30 times takes
  74.8 ms against 97.1 ms (best of 15 paired runs; the port is faster here, and executes 974M
  instructions against 1,142M), and quality 6 on text is 0.99 of C.
- Quality 6 had been about 15% slower with equal instruction counts and cache behaviour. The
  cause: the port had left out the C encoder's `PREFETCH_L1` of the bucket and tag lines in the
  H5, H6, H58 and H68 searches. A prefetch lets the cache miss overlap the search of the last
  distances; cachegrind counts it as one instruction and does not model the overlap. A C build
  with the prefetch made a no-op was as slow as the port (1.049x C over 301 paired rounds). The
  port now prefetches where C does (see the walls).
- Peak RSS is 2 to 3 MiB higher in every row: the startup cost described above, not Brotli's
  allocations (the codecs' own peak memory matches C's within 0.3 to 2.2 MB at tool level).

## Upstreaming

No standard library file was copied or changed: the runtime does not use the standard library's
Brotli decoder or encoder, only `silk.compress.brotli_tables` (unchanged; its dictionary is the C
library's by SHA-256). So there is no fix to upstream and no pull request on silk-lang/silk.
`../brotli` is a new implementation, written to be movable (it knows nothing of Node or the
runtime); whether it should replace or join `silk.compress.brotli` and
`silk.compress.brotli_encode` is the owner's decision. The compiler walls below are the
requests for the compiler.

## Open

- The startup function order (`tools/startup-order.txt`, `tools/server-order.txt`) is stale for
  every build (38 of 896 names match), which costs every start several MiB of resident code and
  makes the port's start 2 to 3 MiB heavier than the C library's. Regenerating it
  (`tools/startup_order.py`) is a change for the whole runtime.
- The decoder's distance tables are padded to 1,024 entries so a masked symbol needs no check:
  4.3 KB more decoder state than C. Revert it if exact sizing matters more than two instructions
  per command.
- `differential.py`'s `dictionary` suite drives one dictionary per stream; several dictionaries,
  attaching after the start and the serialized kind were checked with a private driver during
  the port (1,549/1,549 for each of four seeds) and are not in the committed one.

## Compiler walls: fixes in Silk, and what the port does when they are released

The walls below are addressed by two compiler pull requests:
[silk-lang/silk#3126](https://github.com/silk-lang/silk/pull/3126) (merged: `Intrinsic.prefetch`
and `silk.mem.prefetch`) and [silk-lang/silk#3128](https://github.com/silk-lang/silk/pull/3128)
(`f64.log2`, one-instruction narrow signed widenings, `silk.core.hint` with `likely`, `unlikely`,
`assume` and `unreachable`, unchecked float-to-integer conversions and shifts, inlining of
functions that call `extern "C"`, `r` and `m` constraints in `Intrinsic.assembly`, and
`Intrinsic.sliceCopy`; `Slice.copyInto` moves onto it after the next seed bump). When a release
with them is pinned (`silk set <version>` at the repository root), the port should:

- Replace the inline-assembly prefetch of `enc/memory.silk` with `Prefetch.hint`, and keep the
  same places and locality (`High`, as `PREFETCH_L1`).
- Replace the masked shifts, the xor-and-subtract sign extension and the checked
  float-to-integer conversion in `BrotliPopulationCost` with the unchecked forms, and the
  `@inlineNever` helper around `log2` in `enc/fast_log.silk` with a plain inline call.
- Try `hint.likely`/`hint.unlikely` where C has `BROTLI_PREDICT_TRUE`/`FALSE` in the decoder's
  `processCommands` and the encoder's searches, and `hint.assume` for the facts checked once at
  entry, and keep only what measures better (both are sensitive to register allocation).
- **Check `log2` before replacing libm's.** The encoder's output depends on `log2` (block
  splitting and cost comparisons). Today the port calls the same glibc `log2` as the C library
  in Node, so they agree on any host. The new `f64.log2` is bit-identical to glibc's non-FMA
  path; glibc's FMA path rounds about 1 in 20,000 results the other way. Switching could change
  compressed bytes on hosts where glibc takes the FMA path, so run `tests/differential.py` (all
  suites, qualities 10 and 11 above all) on such a host before switching, and keep libm's `log2`
  if any byte differs. The runtime itself binds glibc's current `log2`, not the compatibility
  entry, so it gains nothing there.
- Re-run `bench/brotli/compare.py` and the instruction counts, and update this file.

Checked again on the released v0.1.0-dev.82+26eee9dbea76 (Linux x86-64, minimal cases):
`log2` now binds `GLIBC_2.29`; `silk check` works in a library package without `main.silk`;
static evaluation of an `unsafe` call gives `SEM0176` instead of an internal error; loops over
plain `&mut [T]`/`&[T]` parameters keep their pointers in registers. Still open, filed on
silk-lang/silk:

- [silk#3147](https://github.com/silk-lang/silk/issues/3147): readable symbol names for
  profilers, and stable names for linker order files (the runtime's `tools/startup-order.txt`
  matches 38 of its 896 names).
- [silk#3148](https://github.com/silk-lang/silk/issues/3148): partial borrows across calls, or
  alias information, for buffers held in struct fields (the decoder's `detach`/`detachMut`).
- [silk#3149](https://github.com/silk-lang/silk/issues/3149): warnings in path dependencies are
  not reported by `silk build`.
- [silk#3150](https://github.com/silk-lang/silk/issues/3150): the `--clang <wrapper>` version
  probe ignores `SILK_CLANG`.
- Not filed yet: register-allocation instability in `processCommandsInternal` and the H6 bucket
  loop. Re-measure it once the port is on dev.82 with `silk.core.hint` and `noalias`, and file
  it if it still holds.
- `Slice.copyInto` as one `memmove` is silk#3141, after dev.82.

The individual walls, as found:


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
- **No way to state a fact the optimizer can use, or to weight a branch.** The decoder's
  `processCommands` is one large state machine, as in C. Its instruction count moves by 5 to 9%
  on edits that change nothing (replacing a checked subtraction with `usize.wrappingSubtract`,
  marking the block-switch functions cold), because register allocation in it is unstable: in
  the bad variants the state pointer itself spills, and field addresses (`&s.distRb`) are hoisted
  out of the loop and spilled where the good ones fold them into the address. A length test made
  at entry (`src.length >= 8`) is not reused by the inlined refills inside the loop. Neither
  reduced to a small case (small functions of the same shape fold correctly); the evidence is the
  disassembly of `processCommands` in several variants, kept with the port's scratch notes.
  Proposed: `Intrinsic.assume(condition: bool)` (LLVM `assume`), to state such facts without a
  branch, and `Intrinsic.expect(condition: bool, likely: bool) -> bool` (branch weights), to fix
  block frequencies in state machines like this one, which is what C's `BROTLI_PREDICT_FALSE`
  does in the same function.
- **A standalone Silk program binds an old libm `log2`.** A Silk executable that declares
  `unsafe extern "C" fn log2(value: f64) -> f64` binds `log2@GLIBC_2.2.5`, glibc's compatibility
  entry with its errno wrapper (about 5 instructions more per call), where a C program binds
  `log2@GLIBC_2.29` (`objdump -T`). The runtime executable binds `GLIBC_2.29`, the same as C, so
  this costs the runtime nothing; it showed in the standalone differential tool (0.2 to 0.7% at
  qualities 10 and 11). Proposed: link against the default symbol version, or let an extern
  declaration name one.
- **A loop-invariant local can make LLVM rotate registers every iteration.** In the H6 bucket
  loop (two back edges), keeping the 4-byte comparison word in a local compiled to about ten
  register-to-register moves per iteration; reloading it each time, as C does, avoids it. Not
  reduced to a small case; the port keeps the reload.
- **`Slice.copyInto` is a 16-byte move loop.** For copies of megabytes (the encoder's ring buffer)
  it does not call `memcpy`, whose ERMS path may be faster at that size. Not measured precisely:
  it is about 10% of sampled time on binary input at quality 6, where the encoder is 6% slower
  than C with the same instruction count.
- **No prefetch.** Neither the standard library nor `Intrinsic` has a prefetch, and binding
  `llvm.prefetch.p0` as an extern function is rejected (`SEM0190 A native symbol that is not an
  ASCII identifier`). The encoder's searches need C's `PREFETCH_L1` to match its speed (about 5%
  at qualities 5 to 9), so the port issues `prefetcht0` (x86-64) or `prfm pldl1keep` (AArch64)
  through `Intrinsic.assembly` in `enc/memory.silk`, and nothing on other targets. Proposed:
  `pub fn prefetch<T>(pointer: ?*const T, locality: PrefetchLocality) -> ()` in `silk.mem.pointer`
  (safe: a prefetch never faults), lowered to `llvm.prefetch`.
- **`Intrinsic.assembly` takes no register-class constraints.** `"r"` (and `"=r,0"`, `"r,r"`) is
  rejected with `SEM0214`; only fixed registers such as `"{rdi}"` are accepted, so the prefetch
  above pins its address in `rdi` (`x0`) inside a loop that is short of registers, which costs
  about 1.5% of the instructions at quality 6. Proposed: accept the LLVM constraint classes `r`
  and `m`.
