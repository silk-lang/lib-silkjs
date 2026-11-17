#!/usr/bin/env python3
"""How much of each benchmark the JIT covers, from silkjs-jit-shell's own counters.

For every Octane benchmark (from `silk task bench-setup`, in <work>/octane) and every v8bench
script (bench/v8), two runs of the JIT shell:

1. the benchmark's own score runner with --jit --jit-dump --jit-stats: functions reported hot,
   compiled and refused (by reason), runs of compiled code, deopts, poll exits, unlinked
   functions, compile time;
2. with --instructions, fixed iterations (as `v8bench.py --instructions`) under callgrind
   with --jit --jit-stats: the fraction of executed machine instructions that ran in compiled
   code. Compiled code lives in an anonymous executable mapping, which callgrind attributes to
   the object `???`; every other instruction is the engine's own (interpreter, runtime, GC).
   This needs no counter in the engine, so its cost when off is zero by construction.

    python3 scripts/jit_coverage.py                       # every benchmark, counters only
    python3 scripts/jit_coverage.py --instructions        # plus the compiled-code fraction
    python3 scripts/jit_coverage.py --only richards,box2d --json out.json
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jit_kernels  # noqa: E402  (engine lookup and kernel sources)

V8 = os.path.join(ROOT, "bench", "v8")
OCTANE = {
    "richards": ["richards"], "deltablue": ["deltablue"], "crypto": ["crypto"], "raytrace": ["raytrace"],
    "earley-boyer": ["earley-boyer"], "regexp": ["regexp"], "splay": ["splay"], "navier-stokes": ["navier-stokes"],
    "pdfjs": ["pdfjs"], "mandreel": ["mandreel"], "gbemu": ["gbemu-part1", "gbemu-part2"], "code-load": ["code-load"],
    "box2d": ["box2d"], "zlib": ["zlib", "zlib-data"], "typescript": ["typescript", "typescript-input", "typescript-compiler"],
}
# Fixed iterations under callgrind: v8bench.py's for its eight, one for the rest.
FIXED = {"richards": 20, "deltablue": 20, "crypto": 4, "raytrace": 8, "earley-boyer": 2, "regexp": 2,
         "splay": 4, "navier-stokes": 2}
PRINT = "var __print = (typeof print === 'function') ? print : console.log.bind(console);\n"
SCORE_RUNNER = PRINT + """BenchmarkSuite.RunSuites({
  NotifyResult: function(name, result) { __print(name + ': ' + result); },
  NotifyError: function(name, error) { __print(name + ': ERROR ' + error); },
  NotifyScore: function(score) { }
});
"""
FIXED_RUNNER = PRINT + """for (var s = 0; s < BenchmarkSuite.suites.length; s++) {
  var suite = BenchmarkSuite.suites[s];
  for (var i = 0; i < suite.benchmarks.length; i++) {
    var b = suite.benchmarks[i];
    BenchmarkSuite.ResetRNG(); b.Setup();
    for (var k = 0; k < %d; k++) b.run();
    b.TearDown();
  }
  __print(suite.name + ' done');
}
"""
STAT = re.compile(r"(\S+) (\d+)")


def source(directory, files):
    out = []
    for name in ["base"] + files:
        with open(os.path.join(directory, name + ".js"), encoding="utf-8") as f:
            out.append(f.read())
    return "if (typeof read === 'undefined') var read = function(){ throw new Error('no read'); };\n" + "".join(out)


def parse_stats(text):
    for line in text.splitlines():
        if line.startswith("jit: reported "):
            return {k: int(v) for k, v in STAT.findall(line[5:])}
    return {}


EXTRA = []  # --calls: ["--jit-calls"]


def counters(shell, path, cwd, timeout):
    env = dict(os.environ, SILKJS_PREPARSE_THREADS="0")
    done = subprocess.run([shell, "--jit", *EXTRA, "--jit-dump", "--jit-stats", path], capture_output=True, text=True,
                          timeout=timeout, env=env, cwd=cwd)
    refused = collections.Counter(line[len("jit: refused: "):] for line in done.stderr.splitlines()
                                  if line.startswith("jit: refused: "))
    deopted = collections.Counter(line[len("jit: deoptimized at: "):] for line in done.stderr.splitlines()
                                  if line.startswith("jit: deoptimized at: "))
    errors = [line for line in done.stdout.splitlines() if "ERROR" in line]
    return {"exit": done.returncode, "stats": parse_stats(done.stderr), "refused": dict(refused), "deopted": dict(deopted),
            "errors": errors}


def compiled_fraction(shell, path, cwd, timeout):
    with tempfile.NamedTemporaryFile(suffix=".callgrind") as out:
        env = dict(os.environ, SILKJS_PREPARSE_THREADS="0")
        done = subprocess.run(["valgrind", "--tool=callgrind", "--smc-check=all-non-file", "--callgrind-out-file=" + out.name,
                               shell, "--jit", *EXTRA, "--jit-stats", path], capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
        if done.returncode != 0 or " done" not in done.stdout:
            return {"exit": done.returncode, "error": (done.stdout + done.stderr)[-600:]}
        total, unknown = per_object(out.name)
    return {"exit": 0, "instructions": total, "compiled": unknown, "fraction": unknown / total if total else 0.0,
            "stats": parse_stats(done.stderr)}


def per_object(path):
    """Total self Ir, and self Ir in object ??? (anonymous executable memory), of a callgrind file."""
    names = {}
    total = unknown = 0
    current = None
    after_call = False
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            head = line[:1]
            if head.isdigit() or head in "+-*":
                if after_call:
                    after_call = False  # the inclusive cost of a call, not self cost
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    cost = int(parts[1])
                    total += cost
                    if current == "???":
                        unknown += cost
                continue
            key, _, value = line.rstrip("\n").partition("=")
            if key in ("ob", "cob"):
                found = re.match(r"\((\d+)\)(?: (.*))?$", value)
                name = value
                if found:
                    if found.group(2) is not None:
                        names[found.group(1)] = found.group(2)
                    name = names.get(found.group(1))
                if key == "ob":
                    current = name
            elif key == "calls":
                after_call = True
    return total, unknown


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", default="", help="benchmarks, comma-separated; v8/<name> selects the v8bench copy")
    parser.add_argument("--work", default=os.environ.get("SILKJS_BENCH_WORK") or os.path.join(ROOT, "build", "bench"))
    parser.add_argument("--instructions", action="store_true", help="also run fixed iterations under callgrind")
    parser.add_argument("--kernels", action="store_true", help="also measure bench/kernels")
    parser.add_argument("--calls", action="store_true", help="run the JIT with --jit-calls")
    parser.add_argument("--json", default="")
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()
    if args.calls: EXTRA.append("--jit-calls")
    found, missing = jit_kernels.commands(args.work)
    if "silkjs-jit" not in found:
        sys.exit("silkjs-jit: " + missing["silkjs-jit"])
    shell = found["silkjs-jit"][0]
    octane_dir = os.path.join(args.work, "octane")
    targets = []
    for name, files in OCTANE.items():
        targets.append(("octane/" + name, octane_dir, files))
    for name in FIXED:
        targets.append(("v8/" + name, V8, [name]))
    if args.kernels:
        for name in jit_kernels.ORDER:
            targets.append(("kernel/" + name, None, name))
    if args.only:
        wanted = set(args.only.split(","))
        targets = [t for t in targets if t[0] in wanted or t[0].split("/", 1)[1] in wanted]
    results = {}
    with tempfile.TemporaryDirectory() as directory:
        for label, where, files in targets:
            kind, name = label.split("/", 1)
            if kind == "kernel":
                with open(os.path.join(jit_kernels.KERNELS, name + ".js"), encoding="utf-8") as f:
                    text = jit_kernels.PRELUDE + f.read() + jit_kernels.EPILOGUE + "__say('kernel done');\n"
                score_text = fixed_text = text
                cwd = directory
            else:
                if not os.path.isdir(where):
                    print("%-22s OMITTED, %s is missing; run `silk task bench-setup octane`" % (label, where))
                    continue
                text = source(where, files)
                score_text = text + SCORE_RUNNER
                fixed_text = text + FIXED_RUNNER % FIXED.get(name, 1)
                cwd = where
            score_path = os.path.join(directory, label.replace("/", "-") + "-score.js")
            fixed_path = os.path.join(directory, label.replace("/", "-") + "-fixed.js")
            with open(score_path, "w", encoding="utf-8") as f:
                f.write(score_text)
            with open(fixed_path, "w", encoding="utf-8") as f:
                f.write(fixed_text)
            entry = {"counters": counters(shell, score_path, cwd, args.timeout)}
            if args.instructions:
                entry["callgrind"] = compiled_fraction(shell, fixed_path, cwd, args.timeout)
            results[label] = entry
            s = entry["counters"]["stats"]
            line = "%-22s exit %d hot %s compiled %s refused %s runs %s deopts %s polls %s unlinked %s" % (
                label, entry["counters"]["exit"], s.get("reported"), s.get("compiled"), s.get("refused"), s.get("runs"),
                s.get("deopts"), s.get("polls"), s.get("unlinked"))
            if "callgrind" in entry:
                c = entry["callgrind"]
                line += " compiled-instr %s" % ("%.4f%%" % (100 * c["fraction"]) if c.get("exit") == 0 else "FAILED")
            print(line, flush=True)
            top = sorted(entry["counters"]["refused"].items(), key=lambda kv: -kv[1])[:4]
            if top:
                print("%-22s   refused: %s" % ("", "; ".join("%s x%d" % kv for kv in top)), flush=True)
    total = collections.Counter()
    for entry in results.values():
        total.update(entry["counters"]["refused"])
    print("\nrefusal reasons over all benchmarks (hot functions refused):")
    for reason, count in total.most_common(12):
        print("  %5d  %s" % (count, reason))
    sites = collections.Counter()
    for entry in results.values():
        sites.update(entry["counters"].get("deopted", {}))
    if sites:
        print("\ndeoptimization sites over all benchmarks (sites of recompiled functions, by opcode):")
        for name, count in sites.most_common(12):
            print("  %5d  %s" % (count, name))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"shell": shell, "results": results}, f, indent=1)


if __name__ == "__main__":
    main()
