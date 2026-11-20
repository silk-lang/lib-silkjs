#!/usr/bin/env python3
"""Runs the scripts of tests/baseline on the JIT shell with and without baseline code.

    python3 scripts/baseline_scripts.py <silkjs-jit-shell> [script.js ...]

Each script prints what it computes. A script passes when --jit-baseline prints what the
interpreter prints, at hot thresholds 1, 5 and 60 (docs/jit/baseline.md). The scripts cover what
the tier does besides straight templates: deep recursion and the stack overflow, exceptions
through baseline frames and handlers in them, error stacks, closures, `arguments`, getters,
constructors, natives, mixed operand types, steps, and loops entered while they run.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THRESHOLDS = (1, 5, 60)


def output(command):
    try:
        run = subprocess.run(command, capture_output=True, timeout=120, check=False)
    except subprocess.TimeoutExpired:
        return None, b"timed out"
    return run.returncode, run.stdout + run.stderr


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    shell = sys.argv[1]
    folder = os.path.join(HERE, "tests", "baseline")
    scripts = sys.argv[2:] or sorted((os.path.join(folder, n) for n in os.listdir(folder) if n.endswith(".js")),
                                     key=lambda p: (len(os.path.basename(p)), p))
    failed = 0
    for script in scripts:
        expected = output([shell, script])
        for threshold in THRESHOLDS:
            got = output([shell, "--jit-baseline", "--jit-threshold=%d" % threshold, script])
            if got != expected:
                failed += 1
                print("FAIL %s at threshold %d (status %s, interpreter %s)" % (os.path.basename(script), threshold, got[0], expected[0]))
    print("%d scripts at thresholds %s: %s" % (len(scripts), ", ".join(map(str, THRESHOLDS)), "%d runs differ" % failed if failed else "all agree"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
