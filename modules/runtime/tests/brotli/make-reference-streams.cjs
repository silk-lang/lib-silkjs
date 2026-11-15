// Writes reference-streams.json: streams compressed by Node 24's Brotli (the C library 1.2.0) at
// every quality and window size, over the inputs of common.cjs. decode.cjs decodes them, clean and
// corrupted, so the decoder is tested on reference streams whatever the encoder under test does.
//   node tests/brotli/make-reference-streams.cjs     (with Node 24; the file is committed)
'use strict';
const zlib = require('node:zlib');
const fs = require('node:fs');
const path = require('node:path');
const { inputs } = require('./common.cjs');
const C = zlib.constants;
const data = inputs();
const streams = [];
const add = (input, slice, params) => {
  const bytes = data[input].subarray(0, slice);
  streams.push({ input, slice, params, stream: zlib.brotliCompressSync(bytes, { params }).toString('base64') });
};
for (const input of Object.keys(data)) for (let quality = 0; quality <= 11; quality++) add(input, 6000, { [C.BROTLI_PARAM_QUALITY]: quality });
for (let lgwin = 10; lgwin <= 24; lgwin++) for (const quality of [1, 5, 11]) add('mixed', 24000, { [C.BROTLI_PARAM_QUALITY]: quality, [C.BROTLI_PARAM_LGWIN]: lgwin });
for (const lgwin of [25, 26, 28, 30]) for (const quality of [1, 5, 11]) add('mixed', 24000, { [C.BROTLI_PARAM_QUALITY]: quality, [C.BROTLI_PARAM_LGWIN]: lgwin, [C.BROTLI_PARAM_LARGE_WINDOW]: 1 });
for (const mode of [C.BROTLI_MODE_TEXT, C.BROTLI_MODE_FONT]) for (const quality of [4, 9, 11]) add('text', 20000, { [C.BROTLI_PARAM_QUALITY]: quality, [C.BROTLI_PARAM_MODE]: mode });
for (const [postfix, direct] of [[1, 2], [3, 120]]) for (const quality of [5, 11]) add('binary', 20000, { [C.BROTLI_PARAM_QUALITY]: quality, [C.BROTLI_PARAM_NPOSTFIX]: postfix, [C.BROTLI_PARAM_NDIRECT]: direct });
add('mixed', 24000, { [C.BROTLI_PARAM_QUALITY]: 11, [C.BROTLI_PARAM_DISABLE_LITERAL_CONTEXT_MODELING]: 1 });
add('json', 20000, { [C.BROTLI_PARAM_QUALITY]: 11, [C.BROTLI_PARAM_LGBLOCK]: 16 });
fs.writeFileSync(path.join(__dirname, 'reference-streams.json'), JSON.stringify({ node: process.version, brotli: process.versions.brotli, streams }) + '\n');
