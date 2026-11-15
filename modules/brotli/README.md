# brotli

Brotli ([RFC 7932](https://www.rfc-editor.org/rfc/rfc7932)) in Silk: a port of the C sources of
[google/brotli](https://github.com/google/brotli) v1.2.0 (commit `028fb5a`), with the decoder of
upstream commit `0ed4268` ("Detect and report invalid stream earlier"), which is what Node 24
bundles. The SilkJS runtime's `node:zlib` Brotli is this package
([`../runtime/BROTLI_NOTES.md`](../runtime/BROTLI_NOTES.md)).

The port keeps the C library's algorithms, order of operations and arithmetic, so that it is
interchangeable with it:

- the encoder writes the same bytes as the C encoder for the same parameters and the same calls;
- the decoder returns the same result, consumes and writes the same number of bytes, and reports
  the same `BROTLI_DECODER_ERROR_*` code at every call.

The API is the C API's, in Silk:

| C | Silk |
| --- | --- |
| `BrotliDecoderCreateInstance`, `…SetParameter`, `…AttachDictionary`, `…DecompressStream`, `…GetErrorCode`, `…HasMoreOutput`, `…IsUsed`, `…IsFinished`, `…Version` | `decode.BrotliDecoder`: `make`, `setParameter`, `attachDictionary`, `decompressStream`, `errorCode`, `hasMoreOutput`, `isUsed`, `isFinished`, `version` |
| `BrotliEncoderCreateInstance`, `…SetParameter`, `…CompressStream`, `…IsFinished`, `…HasMoreOutput`, `…MaxCompressedSize` | `encode.BrotliEncoder`: `make`, `setParameter`, `compressStream`, `isFinished`, `hasMoreOutput`; `encode.maxCompressedSize` |
| `BrotliEncoderPrepareDictionary`, `…AttachPreparedDictionary` | `encode.PreparedDictionary.prepare`, `BrotliEncoder.attachPreparedDictionary` |

`decompressStream` and `compressStream` take the input and output as slices and return how much of
each they used, in place of the C API's pointer-and-length pairs. Storage comes from the ambient
`Allocator`; an allocation failure is reported the way the C library reports it (a decoder error
code, or a `false` result), not as an effect error.

The static dictionary and its transforms are the standard library's `silk.compress.brotli_tables`,
which holds the same data (checked by SHA-256 in the tests).

Nothing in the package knows about Node or the runtime.

## Status

See [`../runtime/BROTLI_NOTES.md`](../runtime/BROTLI_NOTES.md) for what is ported, what matches the
C library exactly, the measurements and the compiler walls.

## Tests

```sh
silk test src/tests.silk                         # fixed vectors

# Differential tests against the C library: the same driver on both sides
tests/reference/build.sh <google/brotli checkout at 028fb5a> /tmp/brref
(cd tests/tool && silk build --release)
tests/differential.py --ref /tmp/brref --tool tests/tool/build/llvm/<target>/release/brotli-tool all
```

`tests/reference` is the C side: a driver (`ref_tool.c`) and upstream `0ed4268`'s `decode.c` and
`decode.h` (`patched/`), compiled from a checkout of the pinned sources. It is a test oracle and is
not part of the package. `tests/differential.py` runs both drivers on the same inputs, parameters
and chunk sizes and compares the bytes they write, their exit status and the result of every
library call.

## License

MIT, as google/brotli ([`LICENSE`](LICENSE)).
