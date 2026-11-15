// fs.read and fs.write of 1 KiB through a Buffer whose ArrayBuffer also backs many other live
// Buffer views. Each async call leases the ArrayBuffer's bytes for the blocking pool; the per-call
// cost must not grow with the number of views.
//
//   build/silkjs bench/scripts/fs-read-views.cjs [calls] [views...]
//
// Prints one line per operation and view count: the mean microseconds per call.
'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const calls = Number(process.argv[2] || 10000);
const counts = process.argv.length > 3 ? process.argv.slice(3).map(Number) : [0, 1000, 10000];
const CHUNK = 1024;

const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'fs-read-views-')), 'data');
fs.writeFileSync(file, Buffer.alloc(1024 * 1024, 7));
const fd = fs.openSync(file, 'r+');

function run(operation, views, done) {
  // One ArrayBuffer: the read target is its first KiB, the other views its following KiBs.
  const backing = Buffer.allocUnsafeSlow(CHUNK * (views + 1));
  const target = backing.subarray(0, CHUNK).fill(7);
  const held = [];
  for (let i = 1; i <= views; i++) held.push(backing.subarray(i * CHUNK, (i + 1) * CHUNK));
  let left = calls, position = 0;
  const start = process.hrtime.bigint();
  const next = () => {
    if (left-- === 0) {
      const micros = Number(process.hrtime.bigint() - start) / 1000 / calls;
      console.log(`${operation.padEnd(5)} views ${String(held.length).padStart(6)}  calls ${calls}  ${micros.toFixed(2)} us/call`);
      done();
      return;
    }
    fs[operation](fd, target, 0, CHUNK, position, (error, count) => {
      if (error) throw error;
      if (count !== CHUNK || target[0] !== 7) throw new Error(`short ${operation}`);
      position = (position + CHUNK) % (1024 * 1024);
      next();
    });
  };
  next();
}

const plan = [];
for (const operation of ['read', 'write']) for (const views of counts) plan.push([operation, views]);
let index = 0;
const step = () => {
  if (index === plan.length) { fs.closeSync(fd); fs.rmSync(path.dirname(file), { recursive: true }); return; }
  const [operation, views] = plan[index++];
  run(operation, views, step);
};
// A warm-up pass, then the measured ones.
run('read', 0, step);
