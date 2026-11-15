// zlib.brotliCompress/brotliDecompress and their sync forms over inputs, every quality, window
// sizes and the other parameters Node exposes; parameter bounds; maxOutputLength; dictionaries.
'use strict';
const zlib = require('node:zlib');
const { promisify } = require('node:util');
const { inputs, digest, failure } = require('./common.cjs');
const C = zlib.constants;
const compress = promisify(zlib.brotliCompress), decompress = promisify(zlib.brotliDecompress);
const out = [];
const attempt = (label, run) => { try { out.push([label, run()]); } catch (error) { out.push([label, failure(error)]); } };

(async () => {
  const data = inputs();
  for (const [name, bytes] of Object.entries(data)) {
    for (let quality = 0; quality <= 11; quality++) {
      const compressed = zlib.brotliCompressSync(bytes, { params: { [C.BROTLI_PARAM_QUALITY]: quality } });
      const back = zlib.brotliDecompressSync(compressed);
      out.push([name, quality, digest(compressed), back.equals(bytes)]);
    }
    const viaPool = await compress(bytes);
    out.push([name, 'async', digest(viaPool), (await decompress(viaPool)).equals(bytes)]);
  }
  const sample = data.mixed;
  const variants = [];
  for (const lgwin of [10, 11, 13, 16, 18, 20, 22, 24]) for (const quality of [1, 4, 6, 9, 11]) variants.push({ [C.BROTLI_PARAM_QUALITY]: quality, [C.BROTLI_PARAM_LGWIN]: lgwin });
  for (const quality of [0, 2, 5, 9, 10, 11]) {
    for (const mode of [C.BROTLI_MODE_GENERIC, C.BROTLI_MODE_TEXT, C.BROTLI_MODE_FONT]) variants.push({ [C.BROTLI_PARAM_QUALITY]: quality, [C.BROTLI_PARAM_MODE]: mode });
    for (const lgblock of [0, 16, 18, 21, 24]) variants.push({ [C.BROTLI_PARAM_QUALITY]: quality, [C.BROTLI_PARAM_LGBLOCK]: lgblock });
    for (const hint of [0, 1, sample.length, 1 << 21, 1 << 26]) variants.push({ [C.BROTLI_PARAM_QUALITY]: quality, [C.BROTLI_PARAM_SIZE_HINT]: hint });
    variants.push({ [C.BROTLI_PARAM_QUALITY]: quality, [C.BROTLI_PARAM_DISABLE_LITERAL_CONTEXT_MODELING]: 1 });
    for (const [postfix, direct] of [[0, 0], [1, 2], [2, 16], [3, 120], [3, 64]]) variants.push({ [C.BROTLI_PARAM_QUALITY]: quality, [C.BROTLI_PARAM_NPOSTFIX]: postfix, [C.BROTLI_PARAM_NDIRECT]: direct });
    for (const lgwin of [16, 25, 28, 30]) variants.push({ [C.BROTLI_PARAM_QUALITY]: quality, [C.BROTLI_PARAM_LARGE_WINDOW]: 1, [C.BROTLI_PARAM_LGWIN]: lgwin });
  }
  for (const params of variants) {
    const label = JSON.stringify(params);
    attempt(label, () => {
      const compressed = zlib.brotliCompressSync(sample, { params });
      const large = params[C.BROTLI_PARAM_LARGE_WINDOW] === 1;
      const back = zlib.brotliDecompressSync(compressed, large ? { params: { [C.BROTLI_DECODER_PARAM_LARGE_WINDOW]: 1 } } : {});
      let plain = 'same';
      if (large) { try { plain = zlib.brotliDecompressSync(compressed).equals(sample); } catch (error) { plain = failure(error); } }
      return [digest(compressed), back.equals(sample), plain];
    });
  }
  // Parameter bounds and their errors.
  const keys = [C.BROTLI_PARAM_MODE, C.BROTLI_PARAM_QUALITY, C.BROTLI_PARAM_LGWIN, C.BROTLI_PARAM_LGBLOCK, C.BROTLI_PARAM_DISABLE_LITERAL_CONTEXT_MODELING,
    C.BROTLI_PARAM_SIZE_HINT, C.BROTLI_PARAM_LARGE_WINDOW, C.BROTLI_PARAM_NPOSTFIX, C.BROTLI_PARAM_NDIRECT, 9, 10, 99, -1];
  for (const key of keys) for (const value of [-1, 0, 1, 2, 3, 4, 9, 10, 12, 15, 16, 24, 25, 30, 31, 121, 1 << 30, 2 ** 32, 1.5, NaN, 'x', true, null]) {
    attempt(`encoder ${key}=${String(value)}`, () => digest(zlib.brotliCompressSync(data.text.subarray(0, 4000), { params: { [key]: value } })));
  }
  const stream = zlib.brotliCompressSync(data.text);
  for (const key of [C.BROTLI_DECODER_PARAM_DISABLE_RING_BUFFER_REALLOCATION, C.BROTLI_DECODER_PARAM_LARGE_WINDOW, 2, 99, -1]) for (const value of [-1, 0, 1, 2, 'x', true]) {
    attempt(`decoder ${key}=${String(value)}`, () => digest(zlib.brotliDecompressSync(stream, { params: { [key]: value } })));
  }
  for (const options of [{ chunkSize: 16 }, { chunkSize: 64 }, { chunkSize: 1 << 20 }, { chunkSize: 0 }, { maxOutputLength: 10 }, { maxOutputLength: data.text.length }, { maxOutputLength: data.text.length - 1 },
    { flush: C.BROTLI_OPERATION_FLUSH }, { finishFlush: C.BROTLI_OPERATION_FLUSH }, { finishFlush: C.BROTLI_OPERATION_PROCESS }, { flush: 9 }, { finishFlush: -1 }, { info: true }]) {
    attempt('compress ' + JSON.stringify(options), () => { const r = zlib.brotliCompressSync(data.text, options); return options.info ? [digest(r.buffer), r.engine.constructor.name, r.engine.bytesWritten] : digest(r); });
    attempt('decompress ' + JSON.stringify(options), () => { const r = zlib.brotliDecompressSync(stream, options); return options.info ? [digest(r.buffer), r.engine.constructor.name, r.engine.bytesWritten] : digest(r); });
  }
  for (const options of [{ maxOutputLength: 10 }, { chunkSize: 100 }]) {
    try { out.push(['async decompress ' + JSON.stringify(options), digest(await decompress(stream, options))]); } catch (error) { out.push(['async decompress ' + JSON.stringify(options), failure(error)]); }
  }
  // Dictionaries.
  for (const dictionary of [data.text.subarray(1000, 9000), data.json.subarray(0, 300), Buffer.from('d'), data.noise.subarray(0, 70000)]) {
    for (const quality of [0, 1, 3, 5, 9, 11]) {
      attempt(`dictionary ${dictionary.length} q${quality}`, () => {
        const compressed = zlib.brotliCompressSync(data.mixed, { dictionary, params: { [C.BROTLI_PARAM_QUALITY]: quality } });
        let without; try { without = zlib.brotliDecompressSync(compressed).equals(data.mixed); } catch (error) { without = failure(error); }
        return [digest(compressed), zlib.brotliDecompressSync(compressed, { dictionary }).equals(data.mixed), without];
      });
    }
  }
  for (const dictionary of ['text', 5, {}, new Uint16Array(4), new ArrayBuffer(8), Buffer.alloc(0)]) {
    attempt('dictionary type ' + Object.prototype.toString.call(dictionary), () => digest(zlib.brotliCompressSync(data.tiny, { dictionary })));
  }
  for (const input of ['string input', new Uint8Array([1, 2, 3]), new Uint16Array([1, 2, 3]).buffer, new DataView(new ArrayBuffer(5)), 5, null]) {
    attempt('input ' + Object.prototype.toString.call(input), () => digest(zlib.brotliCompressSync(input)));
  }
  for (const line of out) console.log(JSON.stringify(line));
})();
