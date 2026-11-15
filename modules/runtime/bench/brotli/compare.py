#!/usr/bin/env python3
"""Brotli throughput and peak memory of two builds of the runtime, side by side.

  bench/brotli/compare.py --a build/silkjs-before --b build/silkjs [--rounds 5] [--out results.json]
                          [--only REGEX] [--binary FILE]

Every round runs each case once under each build, in shuffled order, so host noise (about 8% of
wall time) falls on both alike; the table shows medians. As for the other benchmarks: do not build
while this runs, and it sets SILKJS_PREPARSE_THREADS=0 and drops NODE_OPTIONS itself.
"""
import argparse, json, os, random, re, statistics, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = []
for name in ['text', 'html', 'json', 'random', 'binary']:
    for quality in [1, 4, 6, 9, 11]:
        CASES.append(('compress', name, quality))
    CASES.append(('decompress', name, 5))
for quality in [1, 4, 6, 9]:
    CASES.append(('compress-stream', 'text', quality))
CASES += [('compress-stream', 'html', 11), ('decompress-stream', 'text', 5), ('decompress-stream', 'binary', 5),
          ('compress-async', 'json', 5), ('compress-async', 'text', 9), ('fetch', 'html', 5)]


def run_one(executable, case, binary):
    """Runs the case and returns (result, peak RSS in MiB) of that one process."""
    environment = {k: v for k, v in os.environ.items() if k not in ('NODE_OPTIONS', 'BUN_OPTIONS')}
    environment['SILKJS_PREPARSE_THREADS'] = '0'
    environment['BROTLI_BENCH_BINARY'] = binary
    read, write = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.dup2(write, 1); os.close(read); os.close(write)
        os.execve(executable, [executable, str(HERE / 'case.cjs'), case[0], case[1], str(case[2])], environment)
    os.close(write)
    chunks = []
    while True:
        chunk = os.read(read, 65536)
        if not chunk: break
        chunks.append(chunk)
    os.close(read)
    _, status, usage = os.wait4(pid, 0)
    if status != 0:
        raise SystemExit(f'{executable} {case}: wait status {status}')
    return json.loads(b''.join(chunks)), usage.ru_maxrss / 1024


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--a', required=True); parser.add_argument('--b', required=True)
    parser.add_argument('--rounds', type=int, default=5); parser.add_argument('--out')
    parser.add_argument('--only', default=''); parser.add_argument('--binary', default='/opt/node24/bin/node')
    args = parser.parse_args()
    builds = {'a': str(Path(args.a).resolve()), 'b': str(Path(args.b).resolve())}
    cases = [case for case in CASES if re.search(args.only, ' '.join(map(str, case)))]
    samples = {(case, build): [] for case in cases for build in builds}
    rng = random.Random(1)
    for round in range(args.rounds):
        order = [(case, build) for case in cases for build in builds]
        rng.shuffle(order)
        for case, build in order:
            result, rss = run_one(builds[build], case, args.binary)
            samples[(case, build)].append((result['mbPerSecond'], rss, result['bytesOut'], result['ms']))
        print(f'round {round + 1}/{args.rounds} done', file=sys.stderr, flush=True)
    rows = []
    print(f'| case | input | quality | a MB/s | b MB/s | b/a | a peak MiB | b peak MiB | output bytes a / b |')
    print('| --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for case in cases:
        a, b = samples[(case, 'a')], samples[(case, 'b')]
        speed = [statistics.median(x[0] for x in s) for s in (a, b)]
        rss = [statistics.median(x[1] for x in s) for s in (a, b)]
        sizes = f'{a[0][2]}' if a[0][2] == b[0][2] else f'{a[0][2]} / {b[0][2]}'
        print(f'| {case[0]} | {case[1]} | {case[2]} | {speed[0]:.1f} | {speed[1]:.1f} | {speed[1] / speed[0]:.2f} | {rss[0]:.0f} | {rss[1]:.0f} | {sizes} |')
        rows.append(dict(case=case[0], input=case[1], quality=case[2], a=[list(x) for x in a], b=[list(x) for x in b]))
    if args.out:
        Path(args.out).write_text(json.dumps(dict(builds=builds, rounds=args.rounds, rows=rows), indent=1))


main()
