#!/usr/bin/env python3
"""One markdown table of the JIT against V8 and JSC, from jit_kernels.py --json and bench-octane's octane.json.

    python3 docs/jit/perf_table.py kernels.json octane.json
    python3 docs/jit/perf_table.py --simple kernels.json octane.json   # the short table

Kernel rows are ns per loop iteration (median process, lower is better). Octane rows are scores
(median round, higher is better). Ratio columns read the same way for both: how many times faster
the left engine is, so "V8 / jit 3.0x" means V8's JIT is three times faster than silkjs-jit.
"""
import json, math, statistics, sys

COLUMNS = [("silkjs", "silkjs (interp)"), ("silkjs-jit", "silkjs-jit"), ("silkjs-jit-calls", "silkjs-jit --jit-calls"),
           ("v8-jitless", "V8 jitless"), ("v8-jit", "V8 JIT"), ("jsc-nojit", "JSC jitless"), ("jsc-jit", "JSC JIT")]
# (name, faster engine, slower engine): the ratio is how many times faster the first is.
RATIOS = [("jit / interp", "silkjs-jit", "silkjs"), ("jit-calls / interp", "silkjs-jit-calls", "silkjs"),
          ("V8 JIT / silkjs-jit", "v8-jit", "silkjs-jit"), ("JSC JIT / silkjs-jit", "jsc-jit", "silkjs-jit")]


def geomean(values):
    return math.exp(sum(map(math.log, values)) / len(values)) if values else None


def speed_ratio(row, fast, slow, lower_is_better):
    a, b = row.get(fast), row.get(slow)
    if not a or not b:
        return "-"
    return "%.2fx" % ((b / a) if lower_is_better else (a / b))


GROUPS = [("Simple loops (sum-calls, sum-long, nested, doubles)", ["sum-calls", "sum-long", "nested", "doubles"]),
          ("Array loop (array-sum)", ["array-sum"]), ("Function and method calls (calls, method)", ["calls", "method"]),
          ("Typed arrays (typed-array)", ["typed-array"])]


def span(values):
    lo, hi = min(values), max(values)
    return "%.1fx" % lo if "%.1f" % lo == "%.1f" % hi else "%.1fx to %.1fx" % (lo, hi)


def gain(values):
    if max(values) < 1.1:
        return "none yet (%s)" % span(values)
    return span(values) + " faster"


def simple(kernels, octane):
    """The short table: how many times slower than V8's JIT silkjs-jit is, what the JIT gains over the
    interpreter, and the same two with --jit-calls when that column was measured."""
    ns = {n: {k: statistics.median(v) * 1e6 / kernels["units"][n] for k, v in per.items() if v} for n, per in kernels["ms"].items()}
    calls = all("silkjs-jit-calls" in ns[n] for n in ns)
    head = "| What | Slower than V8 | Gain from our JIT (vs our interpreter) |"
    if calls:
        head += " Slower than V8, `--jit-calls` | Gain, `--jit-calls` |"
    print(head)
    print("|---|" + "---:|" * (4 if calls else 2))

    def cells(slow, gains):
        return "%s | %s" % (slow, gains)

    def row(label, rows, bold=False):
        b = "**" if bold else ""
        out = "| %s%s%s | %s%s%s | %s%s%s |" % (b, label, b, b, span([r["silkjs-jit"] / r["v8-jit"] for r in rows]), b,
                                               b, gain([r["silkjs"] / r["silkjs-jit"] for r in rows]), b)
        if calls:
            out += " %s%s%s | %s%s%s |" % (b, span([r["silkjs-jit-calls"] / r["v8-jit"] for r in rows]), b,
                                           b, gain([r["silkjs"] / r["silkjs-jit-calls"] for r in rows]), b)
        print(out)
    for label, names in GROUPS:
        row(label, [ns[n] for n in names if n in ns])
    keys = ("silkjs", "silkjs-jit", "v8-jit") + (("silkjs-jit-calls",) if calls else ())
    row("All %d kernels (geomean)" % len(ns), [{k: geomean([ns[n][k] for n in ns]) for k in keys}], True)
    if octane:
        # scores: higher is better, so invert to a time-like value for the same formulas
        med = {k: 1 / geomean([statistics.median(r[k]) for r in octane.values()]) for k in keys}
        row("Octane, the real-world suite (geomean)", [med], True)


def main():
    if sys.argv[1] == "--simple":
        kernels = json.load(open(sys.argv[2]))
        return simple(kernels, json.load(open(sys.argv[3])) if len(sys.argv) > 3 else {})
    kernels = json.load(open(sys.argv[1]))
    octane = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else {}
    columns = [(k, t) for k, t in COLUMNS if any(k in kernels["ms"][n] and kernels["ms"][n][k] for n in kernels["ms"])
               or any(row.get(k) for row in octane.values())]
    head = ["Benchmark"] + [t for _, t in columns] + [r[0] for r in RATIOS]
    print("| " + " | ".join(head) + " |")
    print("|---|" + "---:|" * (len(head) - 1))

    def emit(label, row, lower, fmt):
        cells = [fmt % row[k] if row.get(k) else "-" for k, _ in columns]
        ratios = [speed_ratio(row, fast, slow, lower) for _, fast, slow in RATIOS]
        print("| " + " | ".join([label] + cells + ratios) + " |")

    krows = []
    for name, per in kernels["ms"].items():
        units = kernels["units"][name]
        row = {k: statistics.median(v) * 1e6 / units for k, v in per.items() if v}
        krows.append(row)
        emit("kernel %s (ns/iter)" % name, row, True, "%.2f")
    emit("**kernels geomean (ns/iter)**", {k: geomean([r[k] for r in krows if r.get(k)]) for k, _ in columns
                                         if all(r.get(k) for r in krows)}, True, "**%.2f**")
    orows = []
    for name, per in octane.items():
        row = {k: statistics.median(v) for k, v in per.items() if v}
        orows.append(row)
        emit("Octane %s (score)" % name, row, False, "%.0f")
    if orows:
        emit("**Octane geomean (score)**", {k: geomean([r[k] for r in orows if r.get(k)]) for k, _ in columns
                                           if all(r.get(k) for r in orows)}, False, "**%.0f**")


if __name__ == "__main__":
    main()
