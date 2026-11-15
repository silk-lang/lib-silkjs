// Shared by the Brotli differential scenarios (tests/compat.mjs runs each under Node 24 and under
// the runtime and compares what they print). Inputs come from a fixed generator, so both runtimes
// compress the same bytes; results are printed as lengths and SHA-256 digests.
'use strict';
const crypto = require('node:crypto');

function random(seed) {
  let state = seed >>> 0 || 1;
  return () => { state ^= state << 13; state >>>= 0; state ^= state >>> 17; state ^= state << 5; state >>>= 0; return state; };
}
const words = ['the', 'of', 'and', 'compression', 'window', 'stream', 'value', 'function', 'return', 'const', 'error', 'buffer',
  '<div class="row">', '</div>', '"name":', 'true', 'null', 'https://example.org/', '\n', ' ', ', ', '. ', 'é', '流'];
function text(seed, size) {
  const next = random(seed); const parts = []; let length = 0;
  while (length < size) { const word = words[next() % words.length]; parts.push(word, ' '); length += word.length + 1; }
  return Buffer.from(parts.join('')).subarray(0, size);
}
function json(seed, size) {
  const next = random(seed); const rows = []; let length = 0;
  while (length < size) { const row = JSON.stringify({ id: next() % 100000, name: 'user' + next() % 500, active: next() % 2 === 0, score: (next() % 10000) / 100, tags: ['a', 'b', 'c'].slice(next() % 3) }); rows.push(row); length += row.length + 1; }
  return Buffer.from('[' + rows.join(',') + ']').subarray(0, size);
}
function noise(seed, size) {
  const next = random(seed); const out = Buffer.alloc(size);
  for (let i = 0; i < size; i++) out[i] = next() & 255;
  return out;
}
function binary(seed, size) {
  const next = random(seed); const out = Buffer.alloc(size);
  for (let i = 0; i + 4 <= size; i += 4) out.writeUInt32LE(i % 28 === 0 ? next() : Math.imul(i, 2654435761) >>> 0, i);
  return out;
}
const inputs = (scale = 1) => ({
  empty: Buffer.alloc(0),
  one: Buffer.from('a'),
  tiny: Buffer.from('hello hello hello hello'),
  text: text(1, 60000 * scale),
  json: json(2, 50000 * scale),
  noise: noise(3, 20000 * scale),
  binary: binary(4, 40000 * scale),
  zeros: Buffer.alloc(100000 * scale),
  mixed: Buffer.concat([text(5, 30000 * scale), noise(6, 3000), json(7, 30000 * scale), Buffer.alloc(5000), text(5, 30000 * scale)]),
});
const digest = bytes => bytes.length + ':' + crypto.createHash('sha256').update(bytes).digest('hex').slice(0, 16);
const failure = error => ({ name: error.name, code: error.code, errno: error.errno, message: error.message });
module.exports = { random, text, json, noise, binary, inputs, digest, failure };
