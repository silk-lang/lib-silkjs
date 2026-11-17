#!/usr/bin/env python3
"""Markdown coverage and compile-cost tables for docs/jit/jit-scorecard.md, from the --json output
of scripts/jit_coverage.py (default run, and optionally the --calls run)."""
import json, sys


def pct(entry, key="fraction"):
    c = entry.get("callgrind", {})
    return "%.3f%%" % (100 * c[key]) if c.get("exit") == 0 and key in c else "-"


def ratio(entry, base):
    c, p = entry.get("callgrind", {}), base.get("callgrind_plain", {})
    return "%.3f" % (c["instructions"] / p["instructions"]) if c.get("exit") == 0 and p.get("exit") == 0 and p.get("instructions") else "-"


def output(entry):
    v = entry.get("verdict", "-")
    return v if v == "pass" or v == "-" else "**FAIL**"


def top(counter, n=3):
    items = sorted(counter.items(), key=lambda kv: -kv[1])[:n]
    return "; ".join("%s %d" % (("`%s`" % r.split(": ", 1)[1]) if r.startswith("opcode") else r, c) for r, c in items) or "-"


def main():
    plain = json.load(open(sys.argv[1]))["results"]
    calls = json.load(open(sys.argv[2]))["results"] if len(sys.argv) > 2 else {}
    rows = [k for k in plain if not k.startswith("v8/")]
    print("| Benchmark | output | instr / plain | hot / compiled / refused | deopts / unlinked | OSR compiled / runs / deopts | compile ms | code MB | compiled instr | compiler instr | top refusals |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for k in rows:
        e = plain[k]; s = e["counters"]["stats"]
        print("| %s | %s | %s | %d / %d / %d | %d / %d | %d / %d / %d | %.1f | %.2f | %s | %s | %s |" % (
            k, output(e), ratio(e, e), s.get("reported", 0), s.get("compiled", 0), s.get("refused", 0), s.get("deopts", 0), s.get("unlinked", 0),
            s.get("osr-compiled", 0), s.get("osr-runs", 0), s.get("osr-deopts", 0), s.get("compile-ns", 0) / 1e6,
            s.get("code-bytes", 0) / 1048576, pct(e), pct(e, "compiler_fraction"), top(e["counters"]["refused"])))
    if calls:
        print()
        print("With `--jit-calls`:")
        print()
        print("| Benchmark | output | instr / plain | hot / compiled / refused | deopts / unlinked | compile ms | code MB | compiled instr | compiler instr | top refusals |")
        print("|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
        for k in rows:
            e = calls[k]; s = e["counters"]["stats"]
            print("| %s | %s | %s | %d / %d / %d | %d / %d | %.1f | %.2f | %s | %s | %s |" % (
                k, output(e), ratio(e, plain[k]), s.get("reported", 0), s.get("compiled", 0), s.get("refused", 0), s.get("deopts", 0), s.get("unlinked", 0),
                s.get("compile-ns", 0) / 1e6, s.get("code-bytes", 0) / 1048576, pct(e), pct(e, "compiler_fraction"), top(e["counters"]["refused"])))


    for name, results in (("--jit", plain), ("--jit --jit-calls", calls)):
        for k, e in results.items():
            if e.get("verdict", "pass") != "pass":
                print("\nOutput check failed with `%s` on %s: %s" % (name, k, e["verdict"]))


if __name__ == "__main__":
    main()
