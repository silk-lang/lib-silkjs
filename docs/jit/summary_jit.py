#!/usr/bin/env python3
"""Geometric means over Octane score lines per engine (best, median, worst round), from octane.json."""
import json, math, sys
table = json.load(open(sys.argv[1]))
engines = list(next(iter(table.values())).keys())
def g(v): return math.exp(sum(map(math.log, v)) / len(v))
print("%-11s %8s %8s %8s" % ("engine", "best", "median", "worst"))
for e in engines:
    cols = [sorted(row[e]) for row in table.values() if row.get(e)]
    print("%-11s %8.0f %8.0f %8.0f" % (e, g([c[-1] for c in cols]), g([c[len(c)//2] for c in cols]), g([c[0] for c in cols])))
# per-benchmark silkjs-jit / silkjs ratio of medians
r = []
for name, row in table.items():
    a, b = sorted(row["silkjs"]), sorted(row["silkjs-jit"])
    r.append(b[1] / a[1])
    print("  %-16s jit/plain median %.3f  plain [%g..%g] jit [%g..%g]" % (name, b[1]/a[1], a[0], a[-1], b[0], b[-1]))
print("geomean jit/plain of medians %.3f" % g(r))
