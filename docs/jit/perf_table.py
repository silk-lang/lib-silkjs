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
    """The short table: how many times slower than V8's JIT silkjs-jit is, and what the JIT gains over the interpreter."""
    ns = {n: {k: statistics.median(v) * 1e6 / kernels["units"][n] for k, v in per.items() if v} for n, per in kernels["ms"].items()}
    print("| What | Slower than V8 | Gain from our JIT (vs our interpreter) |")
    print("|---|---:|---:|")
    for label, names in GROUPS:
        names = [n for n in names if n in ns]
        print("| %s | %s | %s |" % (label, span([ns[n]["silkjs-jit"] / ns[n]["v8-jit"] for n in names]),
                                    gain([ns[n]["silkjs"] / ns[n]["silkjs-jit"] for n in names])))
    g = {k: geomean([ns[n][k] for n in ns]) for k in ("silkjs", "silkjs-jit", "v8-jit")}
    print("| **All %d kernels (geomean)** | **%.1fx** | **%s** |" % (len(ns), g["silkjs-jit"] / g["v8-jit"], gain([g["silkjs"] / g["silkjs-jit"]])))
    if octane:
        med = {k: geomean([statistics.median(row[k]) for row in octane.values()]) for k in ("silkjs", "silkjs-jit", "v8-jit")}
        print("| **Octane, the real-world suite (geomean)** | **%.1fx** | **%s** |" % (
            med["v8-jit"] / med["silkjs-jit"], gain([med["silkjs-jit"] / med["silkjs"]])))


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
