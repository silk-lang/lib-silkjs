// Invalid input: flipped bits, cut and spliced streams, random bytes. The error (code, errno,
// message) of the sync, callback and stream forms, and what a stream emitted before it failed.
'use strict';
const zlib = require('node:zlib');
const { inputs, digest, failure, random } = require('./common.cjs');
const C = zlib.constants;
const out = [];

function viaStream(bytes, size, options) {
  return new Promise(resolve => {
    const stream = zlib.createBrotliDecompress(options); const chunks = [];
    stream.on('data', chunk => chunks.push(chunk));
    stream.on('error', error => resolve([digest(Buffer.concat(chunks)), failure(error)]));
    stream.on('end', () => resolve([digest(Buffer.concat(chunks)), 'end']));
    let offset = 0;
    (function next() { if (offset >= bytes.length) { stream.end(); return; } const piece = bytes.subarray(offset, offset + size); offset += piece.length; stream.write(piece, () => next()); })();
  });
}
const viaCallback = bytes => new Promise(resolve => zlib.brotliDecompress(bytes, (error, result) => resolve(error ? failure(error) : digest(result))));

(async () => {
  const data = inputs();
  const next = random(29);
  const streams = [];
  for (const [name, bytes] of Object.entries(data)) for (const quality of [0, 1, 2, 5, 9, 11]) {
    streams.push(zlib.brotliCompressSync(bytes, { params: { [C.BROTLI_PARAM_QUALITY]: quality, [C.BROTLI_PARAM_LGWIN]: 10 + next() % 15 } }));
  }
  streams.push(zlib.brotliCompressSync(data.mixed, { params: { [C.BROTLI_PARAM_LARGE_WINDOW]: 1, [C.BROTLI_PARAM_LGWIN]: 28 } }));
  for (let round = 0; round < 1500; round++) {
    const source = streams[next() % streams.length];
    let bad = Buffer.from(source);
    const kind = next() % 6;
    if (kind === 0) { for (let i = 1 + next() % 3; i > 0 && bad.length; i--) bad[next() % bad.length] ^= 1 << (next() % 8); }
    else if (kind === 1) bad = bad.subarray(0, next() % (bad.length + 1));
    else if (kind === 2 && bad.length) { const at = next() % bad.length; for (let i = 0; i < 1 + next() % 7 && at + i < bad.length; i++) bad[at + i] = next() & 255; }
    else if (kind === 3 && bad.length) bad[Math.min(bad.length - 1, next() % 40)] = next() & 255;
    else if (kind === 4) { bad = Buffer.alloc(1 + next() % 64); for (let i = 0; i < bad.length; i++) bad[i] = next() & 255; }
    else if (bad.length) { const at = next() % bad.length; bad = Buffer.concat([bad.subarray(0, at), bad.subarray(at + 1 + next() % 4)]); }
    let sync; try { sync = digest(zlib.brotliDecompressSync(bad)); } catch (error) { sync = failure(error); }
    const line = [round, kind, bad.length, sync];
    if (round % 3 === 0) line.push(await viaStream(bad, [1, 7, 64, 4096][next() % 4], round % 2 ? { chunkSize: 64 + next() % 2000 } : {}));
    if (round % 7 === 0) line.push(await viaCallback(bad));
    if (round % 11 === 0) { try { line.push(digest(zlib.brotliDecompressSync(bad, { params: { [C.BROTLI_DECODER_PARAM_LARGE_WINDOW]: 1 } }))); } catch (error) { line.push(failure(error)); } }
    out.push(line);
  }
  for (const line of out) console.log(JSON.stringify(line));
})();
