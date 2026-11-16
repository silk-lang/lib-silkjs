#!/usr/bin/env python3
"""Differential testing: run generated JavaScript under several engine configurations and
report every program on which they disagree.

A program is generated from a seed alone, so a failure is reproduced by its seed. Each program
calls a few functions in a hot loop with stable argument types, then changes the types, the
object shapes and the call targets, printing a checksum after every phase. That is the pattern
a tiering compiler has to get right: specialise on what the loop saw, then give the
specialisation up.

    python3 scripts/differential.py                          # 200 programs, plain vs observed
    python3 scripts/differential.py --seed 7 --count 1 --show    # print one program
    python3 scripts/differential.py --configs plain,observed,node
    python3 scripts/differential.py --config jit='{engine} --jit {file}'
    python3 scripts/differential.py --self-test              # check the harness itself

Configurations are command templates; `{engine}` is the engine executable and `{file}` the
program. The first configuration named is the baseline the others are compared with.

  plain      {engine} {file}                    the interpreter's ordinary dispatch loop
  observed   {engine} --debug-observed {file}   the instruction-observing loop of the debugger
  node       node {file}                        a reference engine ($NODE_REFERENCE or `node`)

A reference engine that is not installed is reported as skipped, never as passing. A program on
which two SilkJS configurations agree and only a reference engine differs is counted apart, as
`reference`, because it is a conformance question and not a tiering bug.

Exit status: 0 when every compared configuration agreed, 1 on a mismatch, 2 on a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

BUILTIN = {
    "plain": "{engine} {file}",
    "observed": "{engine} --debug-observed {file}",
    "node": "{node} {file}",
}
REFERENCES = {"node"}

PRELUDE = """\
var __out = typeof print === 'function' ? print : console.log;
var __sum = 0;
function __show(v) {
  if (typeof v === 'number') return Object.is(v, -0) ? '-0' : String(v);
  if (typeof v === 'string') return JSON.stringify(v);
  if (typeof v === 'function') return 'function';
  if (v === null || typeof v !== 'object') return String(v);
  if (Array.isArray(v)) return '[' + v.map(__show).join(',') + ']';
  return '{' + Object.keys(v).map(function (k) { return k + ':' + __show(v[k]); }).join(',') + '}';
}
function __mix(v) {
  var s = __show(v);
  for (var i = 0; i < s.length; i++) __sum = (Math.imul(__sum, 31) + s.charCodeAt(i)) | 0;
}
function __try(f, a, b) {
  try { __mix(f(a, b)); } catch (e) { __mix('throw ' + (e && e.constructor ? e.constructor.name : typeof e)); }
}
function __phase(name) { __out(name + ' ' + __sum); }
"""


class Generator:
    """One program per seed. Every statement is one line, so the minimizer can delete lines."""

    def __init__(self, seed: int, hot: int):
        self.random = random.Random(seed)
        self.seed = seed
        self.hot = hot
        self.functions = 0

    def pick(self, values):
        return self.random.choice(values)

    def integer(self) -> str:
        return str(self.pick([0, 1, 2, 3, 7, -1, -8, 31, 32, 255, 65535, 1073741823, 2147483647, -2147483648]))

    def atom(self, depth: int) -> str:
        choices = ["a", "b", "a", "b", self.integer(), "a.x", "b.y", "a[0]", "b.length", "a.x"]
        if self.functions and depth < 2:
            choices.append(f"f{self.random.randrange(self.functions)}(b, a)")
        return self.pick(choices)

    def expression(self, depth: int = 0) -> str:
        if depth >= 3 or self.random.random() < 0.25:
            return self.atom(depth)
        kind = self.random.random()
        left, right = self.expression(depth + 1), self.expression(depth + 1)
        if kind < 0.55:
            op = self.pick(["+", "-", "*", "/", "%", "|", "&", "^", "<<", ">>", ">>>", "+", "-", "*"])
            return f"({left} {op} {right})"
        if kind < 0.75:
            op = self.pick(["<", "<=", ">", ">=", "==", "===", "!=", "!=="])
            return f"({left} {op} {right} ? {self.expression(depth + 1)} : {self.expression(depth + 1)})"
        if kind < 0.85:
            return f"({self.pick(['-', '~', '!', '+', 'typeof '])}{left})"
        if kind < 0.93:
            return f"Math.{self.pick(['abs', 'floor', 'sqrt', 'trunc', 'fround'])}({left})"
        return f"({left} {self.pick(['&&', '||', '??'])} {right})"

    def function(self) -> str:
        name = f"f{self.functions}"
        shape = self.random.random()
        if shape < 0.5:
            body = f"return {self.expression()};"
        elif shape < 0.8:
            body = (f"var t = {self.expression()}; for (var i = 0; i < {self.pick([1, 2, 3, 5])}; i++) "
                    f"{{ t = {self.pick(['t + i', 't ^ i', '(t * 3) | 0', 't + a', 't - b'])}; }} return t;")
        else:
            body = f"if ({self.expression(1)}) {{ return {self.expression(1)}; }} return {self.expression(1)};"
        line = f"function {name}(a, b) {{ {body} }}"
        self.functions += 1
        return line

    def value(self, kind: str) -> str:
        r = self.random
        if kind == "int":
            return self.pick(["i", "i + 1", "i * 3", "i & 7", "(i << 3) | 1", "100 - i"])
        if kind == "big":
            return self.pick(["2147483647 - i", "i * 1073741824", "-2147483648 + i", "4294967295 + i"])
        if kind == "double":
            return self.pick(["i + 0.5", "i / 3", "-0", "0.1 * i", "1e300 * (i + 1)", "NaN", "Infinity"])
        if kind == "string":
            return self.pick(["'s' + i", "''", "String(i)", "'12'", "'x'.repeat(i % 5)"])
        if kind == "objectA":
            return "{x: i, y: i + 1}"
        if kind == "objectB":
            return self.pick(["{y: i, x: i * 2}", "{x: i + 0.5, y: 's', z: 1}", "{x: 'p' + i}"])
        if kind == "array":
            return self.pick(["[i, i + 1]", "[i + 0.5]", "[]", "[, i]", "['a', i]"])
        if kind == "odd":
            return self.pick(["null", "undefined", "true", "{valueOf: function () { return i; }}", "Symbol.iterator"])
        raise ValueError(kind)

    def loop(self, phase: str, count: int, target: str, kinds: tuple[str, str]) -> list[str]:
        a, b = self.value(kinds[0]), self.value(kinds[1])
        return [f"for (var i = 0; i < {count}; i++) {{ __try({target}, {a}, {b}); }}", f"__phase('{phase}');"]

    def program(self) -> str:
        lines = [f"// differential.py seed {self.seed} hot {self.hot}"]
        count = self.random.randrange(2, 6)
        for _ in range(count):
            lines.append(self.function())
        names = [f"f{n}" for n in range(count)]
        stable = self.pick([("int", "int"), ("int", "int"), ("objectA", "objectA"), ("double", "double"), ("array", "int")])
        # Stable types, hot enough for a tiering engine to specialise each function.
        for name in names:
            lines += self.loop(f"hot {name}", self.hot, name, stable)
        # Changed types and shapes: what was specialised must be given up.
        kinds = ["int", "big", "double", "string", "objectA", "objectB", "array", "odd"]
        for name in names:
            changed = (self.pick(kinds), self.pick(kinds))
            lines += self.loop(f"types {name}", self.pick([3, 17, 64]), name, changed)
        # Changed call targets: a call site that saw one function sees others.
        lines.append(f"var table = [{', '.join(self.random.sample(names, len(names)))}];")
        lines += [f"for (var i = 0; i < {self.hot}; i++) {{ __try(table[0], {self.value(stable[0])}, {self.value(stable[1])}); }}",
                  "__phase('target stable');"]
        lines += [f"for (var i = 0; i < 64; i++) {{ __try(table[i % table.length], {self.value(stable[0])}, {self.value(stable[1])}); }}",
                  "__phase('target mixed');"]
        # Changed objects: prototype, accessor and deleted properties behind the same sites.
        victim = self.pick(names)
        lines.append(f"var proto = {{x: 5, y: 6}}; var holder = Object.create(proto); holder.length = 2; holder[0] = 9;")
        lines += [f"for (var i = 0; i < {self.hot}; i++) {{ __try({victim}, holder, holder); }}", "__phase('proto stable');"]
        lines.append(self.pick([
            "proto.x = 'changed';",
            "Object.defineProperty(proto, 'x', {get: function () { return __sum & 3; }, configurable: true});",
            "delete proto.x;",
            "holder.x = 1.5;",
            "Object.setPrototypeOf(holder, {x: [1], y: null});",
        ]))
        lines += [f"for (var i = 0; i < 32; i++) {{ __try({victim}, holder, holder); }}", "__phase('proto changed');"]
        # Back to the stable types: code that deoptimised must still be right, and may tier up again.
        for name in names[:2]:
            lines += self.loop(f"again {name}", self.hot, name, stable)
        lines.append("__phase('end');")
        return PRELUDE + "\n".join(lines) + "\n"


def classify(returncode: int | None, stderr: str) -> str:
    """The comparable part of how a run ended. Error text differs between engines; its class is kept."""
    if returncode is None:
        return "timeout"
    if returncode < 0:
        return "signal " + signal.Signals(-returncode).name
    if returncode == 0:
        return "ok"
    for word in ("SyntaxError", "ReferenceError", "TypeError", "RangeError", "InternalError", "Error"):
        if word in stderr:
            return "uncaught " + word
    return f"exit {returncode}"


def run(command: list[str], timeout: float) -> tuple[str, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, errors="replace",
                                env={**os.environ, "SILKJS_PREPARSE_THREADS": "0"})
        return classify(result.returncode, result.stderr), result.stdout
    except subprocess.TimeoutExpired as expired:
        output = expired.stdout or b""
        return "timeout", output.decode(errors="replace") if isinstance(output, bytes) else output


def outcomes(configs: dict[str, list[str]], path: Path, timeout: float) -> dict[str, tuple[str, str]]:
    return {name: run([part.replace("{file}", str(path)) for part in template], timeout)
            for name, template in configs.items()}


def disagreements(results: dict[str, tuple[str, str]]) -> list[str]:
    names = list(results)
    return [name for name in names[1:] if results[name] != results[names[0]]]


def minimize(source: str, differs, budget: int = 400) -> str:
    """Delta debugging over lines: delete chunks while `differs` still holds."""
    lines = source.splitlines()
    chunk = max(1, len(lines) // 2)
    spent = 0
    while chunk >= 1 and spent < budget:
        index, changed = 0, False
        while index < len(lines) and spent < budget:
            candidate = lines[:index] + lines[index + chunk:]
            spent += 1
            if candidate and differs("\n".join(candidate) + "\n"):
                lines, changed = candidate, True
            else:
                index += chunk
        if not changed:
            chunk //= 2
    return "\n".join(lines) + "\n"


def default_engine() -> Path:
    sys.path.insert(0, str(ROOT / "scripts"))
    import toolchain
    return toolchain.release_binary()


def self_test(engine: Path, timeout: float) -> int:
    """The harness must find a planted disagreement and reduce it, and must not invent one."""
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        # A stand-in "engine" that is wrong only for programs that delete a prototype property.
        broken = work / "broken.py"
        broken.write_text(
            "import subprocess, sys\n"
            "source = open(sys.argv[2]).read()\n"
            "result = subprocess.run([sys.argv[1], sys.argv[2]], capture_output=True, text=True)\n"
            "out = result.stdout.replace('end ', 'end 1') if 'delete proto.x' in source else result.stdout\n"
            "sys.stdout.write(out); sys.stderr.write(result.stderr); sys.exit(result.returncode)\n")
        configs = {"plain": [str(engine), "{file}"], "broken": [sys.executable, str(broken), str(engine), "{file}"]}
        found = clean = 0
        failing = None
        for seed in range(40):
            path = work / f"{seed}.js"
            path.write_text(Generator(seed, 50).program())
            if disagreements(outcomes(configs, path, timeout)):
                found += 1
                failing = failing or path
            else:
                clean += 1
        if not found or not clean:
            print(f"self-test: FAIL planted bug seen in {found} of 40 programs, expected some and not all")
            return 1

        def differs(text: str) -> bool:
            probe = work / "probe.js"
            probe.write_text(text)
            return bool(disagreements(outcomes(configs, probe, timeout)))

        reduced = minimize(failing.read_text(), differs)
        before, after = len(failing.read_text().splitlines()), len(reduced.splitlines())
        if "delete proto.x" not in reduced or after >= before / 2:
            print(f"self-test: FAIL minimizer kept {after} of {before} lines")
            return 1
        same = Generator(3, 50).program() == Generator(3, 50).program()
        other = Generator(3, 50).program() != Generator(4, 50).program()
        if not same or not other:
            print("self-test: FAIL generation is not a function of the seed")
            return 1
        print(f"self-test: PASS planted bug found in {found} of 40 programs, reduced {before} lines to {after}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--engine", help="the SilkJS engine executable (default: $SILKJS_ENGINE, else this host's release build)")
    parser.add_argument("--configs", default="plain,observed", help="comma-separated configurations; the first is the baseline")
    parser.add_argument("--config", action="append", default=[], metavar="NAME=TEMPLATE",
                        help="define a configuration, e.g. jit='{engine} --jit {file}'; repeatable")
    parser.add_argument("--seed", type=int, default=1, help="first seed (default 1)")
    parser.add_argument("--count", type=int, default=200, help="number of programs (default 200)")
    parser.add_argument("--hot", type=int, default=300, help="iterations of each stable loop (default 300)")
    parser.add_argument("--timeout", type=float, default=20.0, help="seconds per run (default 20)")
    parser.add_argument("--out", default=str(ROOT.parents[1] / "build/differential"),
                        help="where failing programs are written (default build/differential)")
    parser.add_argument("--no-minimize", action="store_true", help="keep failing programs as generated")
    parser.add_argument("--show", action="store_true", help="print the generated programs instead of running them")
    parser.add_argument("--self-test", action="store_true", help="check that the harness finds and reduces a planted bug")
    args = parser.parse_args()

    if args.show:
        for seed in range(args.seed, args.seed + args.count):
            sys.stdout.write(Generator(seed, args.hot).program())
        return 0

    engine = Path(args.engine or os.environ.get("SILKJS_ENGINE") or default_engine())
    if not engine.exists():
        print(f"differential.py: no engine at {engine}; build it with `silk build --release` or pass --engine", file=sys.stderr)
        return 2
    if args.self_test:
        return self_test(engine, args.timeout)

    templates = dict(BUILTIN)
    for definition in args.config:
        name, _, template = definition.partition("=")
        if not template:
            print(f"differential.py: --config {definition!r} is not NAME=TEMPLATE", file=sys.stderr)
            return 2
        templates[name] = template
        if name not in args.configs.split(","):
            args.configs += "," + name
    node = os.environ.get("NODE_REFERENCE") or "node"
    configs: dict[str, list[str]] = {}
    skipped: dict[str, str] = {}
    for name in args.configs.split(","):
        if name not in templates:
            print(f"differential.py: unknown configuration {name!r}; known: {', '.join(templates)}", file=sys.stderr)
            return 2
        command = [part.replace("{engine}", str(engine)).replace("{node}", node) for part in shlex.split(templates[name])]
        if shutil.which(command[0]) is None and not Path(command[0]).exists():
            skipped[name] = f"{command[0]} is not installed"
            continue
        configs[name] = command
    if len(configs) < 2:
        print(f"differential.py: need two runnable configurations; skipped: {skipped}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    baseline = next(iter(configs))
    tally = {"agree": 0, "mismatch": 0, "reference": 0}
    endings: dict[str, int] = {}
    failures = []
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for seed in range(args.seed, args.seed + args.count):
            path = work / f"seed-{seed}.js"
            path.write_text(Generator(seed, args.hot).program())
            results = outcomes(configs, path, args.timeout)
            endings[results[baseline][0]] = endings.get(results[baseline][0], 0) + 1
            wrong = disagreements(results)
            if not wrong:
                tally["agree"] += 1
                continue
            kind = "reference" if all(name in REFERENCES for name in wrong) else "mismatch"
            tally[kind] += 1
            source = path.read_text()
            if not args.no_minimize:
                pair = {baseline: configs[baseline], wrong[0]: configs[wrong[0]]}

                def differs(text: str) -> bool:
                    probe = work / "probe.js"
                    probe.write_text(text)
                    return bool(disagreements(outcomes(pair, probe, args.timeout)))

                source = minimize(source, differs)
            saved = out / f"seed-{seed}.js"
            saved.write_text(source)
            (out / f"seed-{seed}.json").write_text(json.dumps({
                "seed": seed, "hot": args.hot, "kind": kind, "baseline": baseline, "differs": wrong,
                "commands": {name: " ".join(command) for name, command in configs.items()},
                "results": {name: {"ending": ending, "stdout": stdout} for name, (ending, stdout) in results.items()},
            }, indent=2) + "\n")
            failures.append((seed, kind, wrong, saved))
            print(f"seed {seed}: {kind}: {', '.join(wrong)} differ from {baseline}; {saved}")

    print(f"{args.count} programs, seeds {args.seed}..{args.seed + args.count - 1}, hot {args.hot}, configurations: {', '.join(configs)}")
    for name, reason in skipped.items():
        print(f"skipped {name}: {reason}")
    print(f"baseline endings: {', '.join(f'{count} {ending}' for ending, count in sorted(endings.items()))}")
    print(f"agree {tally['agree']}, mismatch {tally['mismatch']}, reference-only {tally['reference']}")
    return 1 if tally["mismatch"] else 0


if __name__ == "__main__":
    sys.exit(main())
