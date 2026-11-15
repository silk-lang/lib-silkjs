// One Brotli measurement in one process: `<runtime> case.cjs <case> <input> [quality]`.
// Prints {case, input, quality, ms, bytesIn, bytesOut, mbPerSecond}. compare.py runs it under two
// builds of the runtime in interleaved rounds and reads the peak RSS of each process.
'use strict';
const zlib = require('node:zlib');
const fs = require('node:fs');
const path = require('node:path');
const C = zlib.constants;
const [kind, inputName, qualityText] = process.argv.slice(2);
const quality = Number(qualityText || 11);
const runtimeRoot = path.resolve(__dirname, '../..');

function random(seed) { let s = seed >>> 0 || 1; return () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s; }; }
function input(name) {
  const next = random(7);
  if (name === 'text') {
    // Source code and prose from the repository.
    return Buffer.concat(['vendor/wamr/core/iwasm/interpreter/wasm_loader.c', 'ext/node/internal/deps/undici/undici.js', 'README.md', 'ext/node/zlib.js']
      .map(file => fs.readFileSync(path.join(runtimeRoot, file))));
  }
  if (name === 'html') {
    const words = ['compression', 'window', 'stream', 'the', 'of', 'and', 'to', 'in', 'value', 'response', 'request', 'header', 'body', 'content'];
    const parts = ['<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Listing</title></head><body><table class="listing">'];
    let length = 0;
    for (let row = 0; length < 2 << 20; row++) {
      let cells = '';
      for (let cell = 0; cell < 5; cell++) { let text = ''; for (let w = 1 + next() % 9; w > 0; w--) text += words[next() % words.length] + ' '; cells += `<td class="c${cell}"><a href="/item/${next() % 100000}">${text.trim()}</a></td>`; }
      const line = `<tr id="row-${row}" class="${row % 2 ? 'odd' : 'even'}">${cells}</tr>\n`; parts.push(line); length += line.length;
    }
    parts.push('</table></body></html>');
    return Buffer.from(parts.join(''));
  }
  if (name === 'json') {
    const rows = []; let length = 0;
    while (length < 2 << 20) { const row = JSON.stringify({ id: next() % 1000000, name: 'user' + next() % 5000, email: `user${next() % 5000}@example.org`, active: next() % 2 === 0, score: (next() % 100000) / 1000, tags: ['alpha', 'beta', 'gamma', 'delta'].slice(next() % 4), created: new Date(1600000000000 + (next() % 100000000) * 1000).toISOString() }); rows.push(row); length += row.length + 1; }
    return Buffer.from('[' + rows.join(',') + ']');
  }
  if (name === 'random') { const out = Buffer.alloc(2 << 20); for (let i = 0; i < out.length; i += 4) out.writeUInt32LE(next(), i); return out; }
  if (name === 'binary') {
    // A large executable: the file BROTLI_BENCH_BINARY names (compare.py passes the same one to both builds).
    const file = process.env.BROTLI_BENCH_BINARY;
    if (!file) throw new Error('set BROTLI_BENCH_BINARY to a large binary file');
    const fd = fs.openSync(file, 'r'); const out = Buffer.alloc(16 << 20); const n = fs.readSync(fd, out, 0, out.length, 0); fs.closeSync(fd);
    return out.subarray(0, n);
  }
  throw new Error('unknown input ' + name);
}
const params = { [C.BROTLI_PARAM_QUALITY]: quality };
const now = () => Number(process.hrtime.bigint()) / 1e6;
function report(ms, bytesIn, bytesOut, measured) {
  console.log(JSON.stringify({ case: kind, input: inputName, quality, ms: +ms.toFixed(3), bytesIn, bytesOut, mbPerSecond: +(measured / 1048576 / (ms / 1000)).toFixed(2) }));
}
function through(stream, bytes, size) {
  return new Promise((resolve, reject) => {
    let total = 0; stream.on('data', chunk => { total += chunk.length; }); stream.on('end', () => resolve(total)); stream.on('error', reject);
    let offset = 0;
    (function next() { if (offset >= bytes.length) { stream.end(); return; } const piece = bytes.subarray(offset, offset + size); offset += piece.length; if (stream.write(piece)) setImmediate(next); else stream.once('drain', next); })();
  });
}

(async () => {
  let bytes = input(inputName);
  // The slowest qualities get less input, so a round stays short.
  if (kind.startsWith('compress') && quality >= 10) bytes = bytes.subarray(0, Math.min(bytes.length, inputName === 'binary' ? 4 << 20 : 1 << 20));
  if (kind === 'compress') {
    const start = now(); const packed = zlib.brotliCompressSync(bytes, { params }); report(now() - start, bytes.length, packed.length, bytes.length);
  } else if (kind === 'compress-async') {
    // Eight at once, on the thread pool.
    const start = now();
    const sizes = await Promise.all(Array.from({ length: 8 }, () => new Promise((resolve, reject) => zlib.brotliCompress(bytes, { params }, (error, packed) => error ? reject(error) : resolve(packed.length)))));
    report(now() - start, bytes.length * 8, sizes[0] * 8, bytes.length * 8);
  } else if (kind === 'compress-stream') {
    // 4 KiB writes.
    const start = now(); const total = await through(zlib.createBrotliCompress({ params }), bytes, 4096); report(now() - start, bytes.length, total, bytes.length);
  } else if (kind === 'decompress') {
    const packed = zlib.brotliCompressSync(bytes, { params: { [C.BROTLI_PARAM_QUALITY]: Math.min(quality, 9) } });
    const rounds = Math.max(1, Math.round((64 << 20) / Math.max(1, bytes.length)));
    const start = now(); let total = 0; for (let i = 0; i < rounds; i++) total += zlib.brotliDecompressSync(packed).length; report(now() - start, packed.length * rounds, total, total);
  } else if (kind === 'decompress-stream') {
    // 1 KiB writes of compressed input.
    const packed = zlib.brotliCompressSync(bytes, { params: { [C.BROTLI_PARAM_QUALITY]: Math.min(quality, 9) } });
    const start = now(); const total = await through(zlib.createBrotliDecompress(), packed, 1024); report(now() - start, packed.length, total, total);
  } else if (kind === 'fetch') {
    // An HTTP response with Content-Encoding: br, fetched and read 40 times.
    const http = require('node:http');
    const packed = zlib.brotliCompressSync(bytes, { params: { [C.BROTLI_PARAM_QUALITY]: 5 } });
    const server = http.createServer((request, response) => { response.writeHead(200, { 'content-type': 'text/html', 'content-encoding': 'br', 'content-length': packed.length }); response.end(packed); });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const url = `http://127.0.0.1:${server.address().port}/`;
    const start = now(); let total = 0;
    for (let i = 0; i < 40; i++) { const body = Buffer.from(await (await fetch(url)).arrayBuffer()); if (body.length !== bytes.length) throw new Error('fetch decoded ' + body.length + ' of ' + bytes.length); total += body.length; }
    report(now() - start, packed.length * 40, total, total);
    server.close(); server.closeAllConnections && server.closeAllConnections();
  } else throw new Error('unknown case ' + kind);
})().catch(error => { console.error(error); process.exit(1); });
