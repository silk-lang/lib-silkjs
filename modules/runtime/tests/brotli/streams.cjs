// The BrotliCompress and BrotliDecompress streams: write and output chunk sizes, flush() with
// PROCESS, FLUSH, FINISH and EMIT_METADATA, parameters, bytesWritten, pipelines and web streams.
'use strict';
const zlib = require('node:zlib');
const { pipeline } = require('node:stream/promises');
const { Readable, Writable } = require('node:stream');
const { inputs, digest, failure, random } = require('./common.cjs');
const C = zlib.constants;
const out = [];

// Writes `bytes` in `size` pieces, calling flush(kind) after every `every`-th write, and returns
// the lengths of the chunks the stream produced with a digest of their concatenation.
function drive(stream, bytes, size, every, kind) {
  return new Promise(resolve => {
    const chunks = []; const events = [];
    stream.on('data', chunk => chunks.push(chunk));
    stream.on('error', error => { events.push(failure(error)); finish(); });
    stream.on('end', () => { events.push('end'); finish(); });
    let done = false;
    function finish() {
      if (done) return; done = true;
      const lengths = chunks.map(chunk => chunk.length);
      resolve({ count: lengths.length, head: lengths.slice(0, 12), total: digest(Buffer.concat(chunks)), events, bytesWritten: stream.bytesWritten });
    }
    let offset = 0, index = 0;
    function next() {
      if (offset >= bytes.length) { stream.end(); return; }
      const piece = bytes.subarray(offset, offset + size); offset += piece.length; index++;
      stream.write(piece, () => {
        if (every && index % every === 0) stream.flush(kind, next); else next();
      });
    }
    next();
  });
}

(async () => {
  const data = inputs();
  const next = random(11);
  for (const [name, bytes] of Object.entries(data)) {
    for (const quality of [0, 1, 4, 6, 9, 11]) {
      for (const [size, every, kind, options] of [
        [1 << 20, 0, 0, {}], [4096, 0, 0, {}], [1000, 3, C.BROTLI_OPERATION_FLUSH, {}], [777, 5, C.BROTLI_OPERATION_PROCESS, {}],
        [16384, 2, C.BROTLI_OPERATION_FLUSH, { chunkSize: 64 }], [5000, 0, 0, { chunkSize: 1024 }], [3000, 4, C.BROTLI_OPERATION_EMIT_METADATA, {}],
        [65536, 1, undefined, {}], [1 + next() % 9000, 1 + next() % 4, C.BROTLI_OPERATION_FLUSH, { chunkSize: 64 + next() % 5000 }],
      ]) {
        if (bytes.length / size > 3000) continue;
        const params = { [C.BROTLI_PARAM_QUALITY]: quality };
        const label = [name, 'q' + quality, size, every, kind, JSON.stringify(options)].join(' ');
        const encoded = await drive(zlib.createBrotliCompress({ ...options, params }), bytes, size, every, kind);
        out.push(['compress ' + label, encoded]);
      }
    }
    const compressed = zlib.brotliCompressSync(bytes, { params: { [C.BROTLI_PARAM_QUALITY]: 5 } });
    for (const [size, options] of [[1 << 20, {}], [1, {}], [3, { chunkSize: 64 }], [100, {}], [4096, { chunkSize: 100 }], [1 + next() % 500, { chunkSize: 64 + next() % 3000 }],
      [50, { flush: C.BROTLI_OPERATION_FLUSH }], [50, { finishFlush: C.BROTLI_OPERATION_FLUSH }], [1000, { maxOutputLength: 5000 }]]) {
      if (compressed.length / size > 4000) continue;
      const decoded = await drive(zlib.createBrotliDecompress(options), compressed, size, 0, 0);
      out.push(['decompress ' + [name, size, JSON.stringify(options)].join(' '), decoded]);
    }
    // Input that ends early, and input that goes on after the stream.
    for (const cut of [0, 1, compressed.length >> 1, compressed.length - 1]) {
      if (cut > compressed.length) continue;
      out.push(['truncated ' + name + ' ' + cut, await drive(zlib.createBrotliDecompress(), compressed.subarray(0, cut), 64, 0, 0)]);
      out.push(['truncated flush ' + name + ' ' + cut, await drive(zlib.createBrotliDecompress({ finishFlush: C.BROTLI_OPERATION_FLUSH }), compressed.subarray(0, cut), 64, 0, 0)]);
    }
    out.push(['trailing ' + name, await drive(zlib.createBrotliDecompress(), Buffer.concat([compressed, Buffer.from('trailing bytes')]), 100, 0, 0)]);
    out.push(['two streams ' + name, await drive(zlib.createBrotliDecompress(), Buffer.concat([compressed, compressed]), 1 << 20, 0, 0)]);
  }
  // A pipeline through both, and the classes' own bookkeeping.
  {
    const chunks = [];
    await pipeline(Readable.from([data.text, data.json, data.noise]), zlib.createBrotliCompress({ params: { [C.BROTLI_PARAM_QUALITY]: 4 } }), zlib.createBrotliDecompress(),
      new Writable({ write(chunk, encoding, callback) { chunks.push(chunk); callback(); } }));
    out.push(['pipeline', digest(Buffer.concat(chunks)), Buffer.concat(chunks).equals(Buffer.concat([data.text, data.json, data.noise]))]);
  }
  {
    const stream = zlib.createBrotliCompress();
    out.push(['class', stream.constructor.name, stream instanceof zlib.BrotliCompress, typeof stream.params, typeof stream.reset, stream.bytesWritten]);
    const result = await new Promise(resolve => { const chunks = []; stream.on('data', c => chunks.push(c)); stream.on('end', () => resolve(Buffer.concat(chunks)));
      stream.write('first '); stream.flush(() => { stream.write('second'); stream.flush(C.BROTLI_OPERATION_FLUSH, () => { stream.end('third'); }); }); });
    out.push(['flush sequence', digest(result), zlib.brotliDecompressSync(result).toString()]);
    const closed = zlib.createBrotliCompress(); closed.close();
    try { closed.write('x', error => {}); closed.on('error', error => {}); out.push(['write after close', 'no throw']); } catch (error) { out.push(['write after close', failure(error)]); }
    const reset = zlib.createBrotliCompress({ params: { [C.BROTLI_PARAM_QUALITY]: 3 } });
    const first = await new Promise(resolve => { const chunks = []; reset.on('data', c => chunks.push(c)); reset.write(data.tiny); reset.flush(() => { const a = Buffer.concat(chunks); chunks.length = 0; reset.reset(); reset.write(data.tiny); reset.flush(() => resolve([digest(a), digest(Buffer.concat(chunks))])); }); });
    out.push(['reset', first]);
  }
  // Web streams.
  for (const format of ['brotli']) {
    try {
      const packed = Buffer.from(await new Response(new Blob([data.text]).stream().pipeThrough(new CompressionStream(format))).arrayBuffer());
      const back = Buffer.from(await new Response(new Blob([packed]).stream().pipeThrough(new DecompressionStream(format))).arrayBuffer());
      out.push(['web ' + format, digest(packed), back.equals(data.text)]);
      let bad; try { await new Response(new Blob([packed.subarray(0, packed.length - 3)]).stream().pipeThrough(new DecompressionStream(format))).arrayBuffer(); bad = 'no error'; } catch (error) { bad = [error.name, error.code]; }
      out.push(['web truncated ' + format, bad]);
    } catch (error) { out.push(['web ' + format, failure(error)]); }
  }
  for (const line of out) console.log(JSON.stringify(line));
})();
