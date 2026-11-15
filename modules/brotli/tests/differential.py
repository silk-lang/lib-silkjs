#!/usr/bin/env python3
"""Differential tests of the Silk Brotli against the C library (google/brotli v1.2.0 with upstream
0ed4268's decoder, as Node 24 bundles it).

Both sides are the same driver (tests/tool and tests/reference/ref_tool.c): for the same input,
parameters and chunk sizes they must write the same bytes, exit with the same status, and report the
same result for every library call (consumed, written, has-more-output, finished, error code).

  tests/differential.py --ref REF --tool TOOL [encode|decode|corrupt|params|dictionary|large|all]
                        [--seed N] [--rounds N] [--quality Q[,Q...]] [--file PATH ...] [--stop]

REF is tests/reference/build.sh's output; TOOL is the build of tests/tool.
"""
import argparse, os, random, subprocess, sys, tempfile, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
failures = 0
checks = 0


def run(tool, data, **env):
    environment = {k: str(v) for k, v in env.items()}
    p = subprocess.run([tool], input=data, capture_output=True, env=environment)
    return p.returncode, p.stdout, p.stderr


def compare(args, label, data, **env):
    """Runs both tools; returns the reference's (status, stdout) and counts a failure on any difference."""
    global failures, checks
    checks += 1
    ref = run(args.ref, data, **env)
    ours = run(args.tool, data, **env)
    if ref == ours:
        return ref
    failures += 1
    what = 'status' if ref[0] != ours[0] else 'bytes' if ref[1] != ours[1] else 'trace'
    detail = ''
    if what == 'status':
        detail = f' ref={ref[0]} ours={ours[0]} ref-trace-tail={ref[2][-120:]!r} ours-trace-tail={ours[2][-120:]!r}'
    elif what == 'bytes':
        at = next((i for i, (a, b) in enumerate(zip(ref[1], ours[1])) if a != b), min(len(ref[1]), len(ours[1])))
        detail = f' ref={len(ref[1])} ours={len(ours[1])} first-difference={at}'
    else:
        a, b = ref[2].split(b'\n'), ours[2].split(b'\n')
        at = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        detail = f' line {at}: ref={a[at] if at < len(a) else None!r} ours={b[at] if at < len(b) else None!r}'
    print(f'FAIL {label}: {what} differ{detail}', flush=True)
    if args.keep:
        d = Path(tempfile.mkdtemp(prefix='brotli-diff-'))
        (d / 'input').write_bytes(data)
        (d / 'env').write_text(' '.join(f'{k}={v}' for k, v in env.items()))
        (d / 'ref.out').write_bytes(ref[1]); (d / 'ours.out').write_bytes(ours[1])
        (d / 'ref.trace').write_bytes(ref[2]); (d / 'ours.trace').write_bytes(ours[2])
        print(f'  kept in {d}', flush=True)
    if args.stop:
        sys.exit(1)
    return ref


def corpus(args, rng):
    """Named inputs: text, HTML, JSON, source code, binary, random, repetitive and tiny ones."""
    if args.file:
        return [(Path(f).name, Path(f).read_bytes()) for f in args.file]
    out = []
    runtime = REPO / 'modules/runtime'
    for name, path, limit in [
        ('markdown', runtime / 'README.md', 60000),
        ('javascript', runtime / 'ext/node/zlib.js', 200000),
        ('silk', runtime / 'src/ext/compression_native.silk', 80000),
        ('c', ROOT / 'reference/patched/dec/decode.c', 120000),
    ]:
        if path.exists():
            out.append((name, path.read_bytes()[:limit]))
    words = [b'the', b'of', b'and', b'compression', b'<div class="', b'</div>', b'"name":', b'true', b'null', b'https://', b'\n', b' ']
    html = b'<!DOCTYPE html><html><head><title>Test</title></head><body>' + b''.join(
        b'<p id="p%d">%s</p>' % (i, b' '.join(rng.choice(words) for _ in range(rng.randrange(3, 40)))) for i in range(600)) + b'</body></html>'
    out.append(('html', html))
    json = b'[' + b','.join(b'{"id":%d,"name":"user%d","active":%s,"score":%d.%d,"tags":["a","b","c"]}' % (
        i, rng.randrange(1000), rng.choice([b'true', b'false']), rng.randrange(100), rng.randrange(100)) for i in range(1500)) + b']'
    out.append(('json', json))
    out.append(('random', rng.randbytes(70000)))
    out.append(('zeros', bytes(300000)))
    out.append(('run-mix', b''.join(bytes([rng.randrange(256)]) * rng.randrange(1, 400) for _ in range(800))))
    binary = bytearray()
    for i in range(20000):
        binary += (i * 2654435761 % (1 << 32)).to_bytes(4, 'little') if i % 7 else rng.randbytes(4)
    out.append(('binary', bytes(binary)))
    out.append(('compressed', zlib.compress(html * 3, 9)))
    out.append(('empty', b''))
    out.append(('one', b'a'))
    out.append(('tiny', b'hello hello hello hello'))
    big = (html + json + rng.randbytes(5000)) * 6
    out.append(('large', big))
    return out


def qualities(args):
    return [int(q) for q in args.quality.split(',')] if args.quality else list(range(12))


def encode(args, rng):
    for name, data in corpus(args, rng):
        for q in qualities(args):
            compare(args, f'encode {name} q{q}', data, BR_MODE=0, BR_PARAMS=f'1={q}')
    for round in range(args.rounds):
        name, data = rng.choice(corpus(args, rng))
        q = rng.choice(qualities(args))
        lgwin = rng.randrange(10, 25)
        params = [f'1={q}', f'2={lgwin}']
        if rng.random() < 0.3: params.append(f'0={rng.randrange(3)}')
        if rng.random() < 0.3: params.append(f'3={rng.choice([0, 16, 18, 20, 22, 24])}')
        if rng.random() < 0.2: params.append(f'4={rng.randrange(2)}')
        if rng.random() < 0.3: params.append(f'5={rng.choice([0, 1, len(data), len(data) * 2, 1 << 20, 1 << 25])}')
        if rng.random() < 0.15: params[1] = f'2={rng.randrange(10, 31)}'; params.append('6=1')
        if rng.random() < 0.2:
            postfix = rng.randrange(4)
            params.append(f'7={postfix}'); params.append(f'8={rng.randrange(16) << postfix}')
        env = dict(BR_MODE=0, BR_PARAMS=','.join(params))
        if rng.random() < 0.6: env['BR_IN'] = rng.choice([1, 7, 100, 4096, 65536, 100000, 1 << 20])
        if rng.random() < 0.6: env['BR_OUT'] = rng.choice([1, 3, 64, 1000, 65536, 1 << 20])
        if rng.random() < 0.4: env['BR_FLUSH'] = rng.choice([1, 2, 5, 17])
        if rng.random() < 0.15: env['BR_META'] = rng.choice([1, 3, 11])
        if env.get('BR_IN') == 1 and len(data) > 20000: data = data[:20000]
        compare(args, f'encode {name} {env}', data, **env)


def streams(args, rng, count):
    """Reference streams: (label, compressed bytes, original)."""
    out = []
    inputs = corpus(args, rng)
    for index in range(count):
        name, data = inputs[index % len(inputs)]
        q = rng.choice(qualities(args))
        params = [f'1={q}', f'2={rng.randrange(10, 25)}']
        if rng.random() < 0.15: params[1] = f'2={rng.randrange(16, 31)}'; params.append('6=1')
        env = dict(BR_MODE=0, BR_PARAMS=','.join(params), BR_TRACE=0)
        if rng.random() < 0.3: env['BR_IN'] = rng.choice([100, 4096, 65536]); env['BR_FLUSH'] = rng.choice([1, 3])
        if rng.random() < 0.1: env['BR_IN'] = 4096; env['BR_META'] = 2
        status, compressed, _ = run(args.ref, data, **env)
        assert status == 0
        out.append((f'{name} {env["BR_PARAMS"]}', compressed, data, '6=1' in params))
    return out


def decode(args, rng):
    for label, compressed, data, large in streams(args, rng, max(24, args.rounds // 4)):
        base = dict(BR_MODE=1)
        if large: base['BR_PARAMS'] = '1=1'
        status, out, _ = compare(args, f"decode {label}", compressed, **base)
        if status != 0 or out != data:
            print(f'NOTE reference failed to round-trip {label}: status {status}')
        for _ in range(3):
            env = dict(base, BR_IN=rng.choice([1, 2, 3, 13, 100, 4096, 1 << 20]), BR_OUT=rng.choice([1, 2, 17, 1000, 65536, 1 << 22]))
            if rng.random() < 0.2: env['BR_PARAMS'] = (env.get('BR_PARAMS', '') + ',0=1').lstrip(',')
            if env['BR_IN'] <= 3 and len(compressed) > 30000: continue
            compare(args, f'decode {label} {env}', compressed + (b'trailing' if rng.random() < 0.2 else b''), **env)


def corrupt(args, rng):
    made = streams(args, rng, 16)
    for round in range(args.rounds):
        label, compressed, data, large = rng.choice(made)
        bad = bytearray(compressed)
        kind = rng.randrange(6)
        if not bad: bad = bytearray(b'\x00')
        if kind == 0:
            for _ in range(rng.randrange(1, 4)): bad[rng.randrange(len(bad))] ^= 1 << rng.randrange(8)
        elif kind == 1:
            bad = bad[:rng.randrange(len(bad) + 1)]
        elif kind == 2:
            at = rng.randrange(len(bad)); bad[at:at + rng.randrange(1, 8)] = rng.randbytes(rng.randrange(1, 8))
        elif kind == 3:
            at = min(len(bad) - 1, rng.randrange(0, 40)); bad[at] = rng.randrange(256)
        elif kind == 4:
            bad = bytearray(rng.randbytes(rng.randrange(1, 64)))
        else:
            at = rng.randrange(len(bad)); del bad[at:at + rng.randrange(1, 5)]
        env = dict(BR_MODE=1)
        if large or rng.random() < 0.1: env['BR_PARAMS'] = '1=1'
        if rng.random() < 0.5: env['BR_IN'] = rng.choice([1, 2, 5, 64, 4096])
        if rng.random() < 0.5: env['BR_OUT'] = rng.choice([1, 7, 512, 65536])
        if env.get('BR_IN', 99) <= 5 and len(bad) > 20000: bad = bad[:20000]
        compare(args, f'corrupt #{round} kind {kind} of {label} {env}', bytes(bad), **env)


def params(args, rng):
    data = b'parameter bounds ' * 200
    for key, values in [(0, range(0, 5)), (1, range(0, 14)), (2, range(8, 33)), (3, range(14, 27)), (4, range(0, 3)),
                        (5, [0, 1, 1 << 30, (1 << 32) - 1]), (6, range(0, 3)), (7, range(0, 6)), (8, range(0, 130)), (9, range(0, 3)), (10, [0, 1])]:
        for value in values:
            compare(args, f'encoder parameter {key}={value}', data, BR_MODE=0, BR_PARAMS=f'{key}={value}')
            compare(args, f'encoder parameter {key}={value} large window', data, BR_MODE=0, BR_PARAMS=f'6=1,{key}={value}')
            compare(args, f'encoder parameter 7=2,{key}={value}', data, BR_MODE=0, BR_PARAMS=f'7=2,{key}={value}')
    stream = run(args.ref, data, BR_MODE=0, BR_TRACE=0)[1]
    for key in range(0, 4):
        for value in range(0, 3):
            compare(args, f'decoder parameter {key}={value}', stream, BR_MODE=1, BR_PARAMS=f'{key}={value}')


def dictionary(args, rng):
    inputs = corpus(args, rng)
    with tempfile.TemporaryDirectory() as folder:
        for round in range(max(8, args.rounds // 8)):
            name, data = rng.choice(inputs)
            source = rng.choice(inputs)[1]
            size = rng.choice([0, 1, 10, 500, 5000, 70000])
            dict_bytes = source[:size] if rng.random() < 0.7 else (data[len(data) // 3:][:size] or b'x')
            if not dict_bytes: dict_bytes = b'd'
            path = Path(folder) / f'dict{round}'
            path.write_bytes(dict_bytes)
            q = rng.choice(qualities(args))
            env = dict(BR_MODE=0, BR_PARAMS=f'1={q},2={rng.randrange(10, 25)}', BR_DICT=str(path))
            status, compressed, _ = compare(args, f"dictionary encode {name} q{q} dict {len(dict_bytes)}", data, **env)
            if status == 0:
                env = dict(BR_MODE=1, BR_DICT=str(path), BR_IN=rng.choice([1 << 20, 100, 7]), BR_OUT=rng.choice([65536, 100]))
                compare(args, f'dictionary decode {name} q{q} dict {len(dict_bytes)}', compressed, **env)
                compare(args, f'dictionary decode without it {name} q{q}', compressed, BR_MODE=1)


def large(args, rng):
    """Inputs of several MB, so the ring buffer wraps, with small and large windows (up to 30 bits
    with LARGE_WINDOW), one-shot and streamed with flushes, then decoded back by both sides."""
    runtime = REPO / 'modules/runtime'
    text = b''.join((runtime / f).read_bytes() for f in ['ext/node/internal/deps/undici/undici.js', 'vendor/wamr/core/iwasm/interpreter/wasm_loader.c'] if (runtime / f).exists())
    binary = Path('/opt/node24/bin/node').read_bytes()[:6 << 20] if Path('/opt/node24/bin/node').exists() else rng.randbytes(6 << 20)
    inputs = [('text', (text * 6)[:8 << 20]), ('binary', binary), ('mixed', (text[:1 << 20] + rng.randbytes(1 << 20) + binary[:2 << 20]) * 2)]
    choices = qualities(args) if args.quality else [0, 1, 2, 4, 5, 7, 9]
    for round in range(max(6, args.rounds // 20)):
        name, data = rng.choice(inputs)
        q = rng.choice(choices)
        lgwin = rng.choice([16, 18, 20, 22, 24])
        params = [f'1={q}', f'2={lgwin}']
        if rng.random() < 0.3: params = [f'1={q}', f'2={rng.choice([25, 26, 28, 30])}', '6=1']
        if q >= 10: data = data[:2 << 20]
        env = dict(BR_MODE=0, BR_PARAMS=','.join(params))
        if rng.random() < 0.5: env.update(BR_IN=rng.choice([65536, 100000, 1 << 20]), BR_FLUSH=rng.choice([0, 3, 7]))
        status, compressed, _ = compare(args, f'large encode {name} {env}', data, **env)
        if status == 0:
            denv = dict(BR_MODE=1, BR_OUT=rng.choice([65536, 1 << 20]), BR_IN=rng.choice([4096, 1 << 20]))
            if '6=1' in params: denv['BR_PARAMS'] = '1=1'
            compare(args, f'large decode {name} {env}', compressed, **denv)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('what', nargs='?', default='all')
    parser.add_argument('--ref', required=True); parser.add_argument('--tool', required=True)
    parser.add_argument('--seed', type=int, default=1); parser.add_argument('--rounds', type=int, default=200)
    parser.add_argument('--quality'); parser.add_argument('--file', action='append')
    parser.add_argument('--stop', action='store_true'); parser.add_argument('--keep', action='store_true')
    args = parser.parse_args()
    suites = dict(encode=encode, decode=decode, corrupt=corrupt, params=params, dictionary=dictionary, large=large)
    for name, suite in suites.items():
        if args.what in ('all', name):
            suite(args, random.Random(args.seed))
    print(f'{checks - failures}/{checks} passed')
    sys.exit(1 if failures else 0)


main()
