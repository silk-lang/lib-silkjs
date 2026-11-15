// The decoder on reference streams (reference-streams.json, written by Node 24's Brotli): every
// quality, window size and large window, decoded one-shot, by the callback form and as a stream
// with small writes and outputs; then corrupted (flipped bits, cuts, spliced bytes), with the
// errors each form reports. Independent of the encoder under test.
'use strict';
const zlib = require('node:zlib');
const { inputs, digest, failure, random } = require('./common.cjs');
const C = zlib.constants;
const fixture = require('./reference-streams.json');
const data = inputs();
const out = [];
const large = { params: { [C.BROTLI_DECODER_PARAM_LARGE_WINDOW]: 1 } };

function viaStream(bytes, size, options) {
  return new Promise(resolve => {
    const stream = zlib.createBrotliDecompress(options); const chunks = [];
    stream.on('data', chunk => chunks.push(chunk));
    stream.on('error', error => resolve([digest(Buffer.concat(chunks)), failure(error), stream.bytesWritten]));
    stream.on('end', () => resolve([digest(Buffer.concat(chunks)), 'end', stream.bytesWritten]));
    let offset = 0;
    (function next() { if (offset >= bytes.length) { stream.end(); return; } const piece = bytes.subarray(offset, offset + size); offset += piece.length; stream.write(piece, () => next()); })();
  });
}
const sync = (bytes, options) => { try { return digest(zlib.brotliDecompressSync(bytes, options)); } catch (error) { return failure(error); } };
const viaCallback = (bytes, options) => new Promise(resolve => zlib.brotliDecompress(bytes, options || {}, (error, result) => resolve(error ? failure(error) : digest(result))));

(async () => {
  const next = random(41);
  const streams = fixture.streams.map(entry => ({ ...entry, bytes: Buffer.from(entry.stream, 'base64') }));
  for (const entry of streams) {
    const expected = data[entry.input].subarray(0, entry.slice);
    const options = entry.params[C.BROTLI_PARAM_LARGE_WINDOW] ? large : {};
    const label = entry.input + ' ' + JSON.stringify(entry.params);
    let ok; try { ok = zlib.brotliDecompressSync(entry.bytes, options).equals(expected); } catch (error) { ok = failure(error); }
    const line = [label, ok];
    if (entry.params[C.BROTLI_PARAM_LARGE_WINDOW]) line.push(sync(entry.bytes));
    line.push(await viaCallback(entry.bytes, options));
    line.push(await viaStream(entry.bytes, 1 + next() % 300, { ...options, chunkSize: 64 + next() % 4000 }));
    out.push(line);
  }
  // BROTLI_DECODER_ERROR_FORMAT_BLOCK_SWITCH (upstream 0ed4268): a command of 2^24 + 1 zero-bit
  // literals in a meta-block with one literal block type runs out the block length; it needs a
  // large window and no ring buffer reallocation, or the ring buffer wraps first.
  {
    const bytes = Buffer.from('115a00000080080bfc02e0f7f41f', 'hex');
    const fixed = { params: { [C.BROTLI_DECODER_PARAM_LARGE_WINDOW]: 1, [C.BROTLI_DECODER_PARAM_DISABLE_RING_BUFFER_REALLOCATION]: 1 } };
    out.push(['block switch', sync(bytes, fixed), sync(bytes, large), sync(bytes), await viaCallback(bytes, fixed), await viaStream(bytes, 3, fixed)]);
  }
  for (let round = 0; round < 2500; round++) {
    const entry = streams[next() % streams.length];
    let bad = Buffer.from(entry.bytes);
    const kind = next() % 6;
    if (kind === 0) { for (let i = 1 + next() % 3; i > 0 && bad.length; i--) bad[next() % bad.length] ^= 1 << (next() % 8); }
    else if (kind === 1) bad = bad.subarray(0, next() % (bad.length + 1));
    else if (kind === 2 && bad.length) { const at = next() % bad.length; for (let i = 0; i < 1 + next() % 7 && at + i < bad.length; i++) bad[at + i] = next() & 255; }
    else if (kind === 3 && bad.length) bad[Math.min(bad.length - 1, next() % 40)] = next() & 255;
    else if (kind === 4) { bad = Buffer.alloc(1 + next() % 64); for (let i = 0; i < bad.length; i++) bad[i] = next() & 255; }
    else if (bad.length) { const at = next() % bad.length; bad = Buffer.concat([bad.subarray(0, at), bad.subarray(at + 1 + next() % 4)]); }
    const options = entry.params[C.BROTLI_PARAM_LARGE_WINDOW] || round % 9 === 0 ? large : {};
    const line = [round, kind, bad.length, sync(bad, options)];
    if (round % 3 === 0) line.push(await viaStream(bad, [1, 7, 64, 4096][next() % 4], round % 2 ? { ...options, chunkSize: 64 + next() % 2000 } : options));
    if (round % 7 === 0) line.push(await viaCallback(bad, options));
    out.push(line);
  }
  for (const line of out) console.log(JSON.stringify(line));
})();
