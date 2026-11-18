#!/usr/bin/env python3
"""Cold and warm table from the logs of `silk task bench-warmup` and `silk task bench-startup`.

    python3 docs/jit/warm_table.py bench-warmup.log [bench-startup.log]

Cold is the first iteration in a fresh process (ms, median of the harness's processes); warm is
the harness's steady value (median of the last third of the iterations). Ratios: how many times
slower silkjs-jit is than V8's and JSC's JIT (lower is better, 1x is the same speed).
"""
import re, sys

ROW = re.compile(r"^(first iteration ms|steady ms|empty wall ms)\s+(\S+)\s+\d+\s+[\d.]+\s+([\d.]+)\s+[\d.]+$")


def parse(path):
    out, bench = {}, "startup"
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"^-- (\S+)", line)
        if m:
            bench = m.group(1)
            continue
        m = ROW.match(line.rstrip())
        if m:
            out.setdefault(bench, {}).setdefault(m.group(1), {})[m.group(2)] = float(m.group(3))
    return out


def x(a, b):
    return "%.1fx" % (a / b) if a and b else "-"


def main():
    warm = parse(sys.argv[1])
    print("| Benchmark | silkjs cold ms | silkjs-jit cold ms | V8 cold ms | JSC cold ms | cold: slower than V8 | cold: slower than JSC "
          "| silkjs warm ms | silkjs-jit warm ms | V8 warm ms | JSC warm ms | warm: slower than V8 | warm: slower than JSC |")
    print("|---|" + "---:|" * 12)
    for bench, rows in warm.items():
        c, w = rows.get("first iteration ms", {}), rows.get("steady ms", {})
        cells = ["%.2f" % c.get(e, 0) for e in ("silkjs", "silkjs-jit", "v8-jit", "jsc-jit")]
        cells += [x(c.get("silkjs-jit"), c.get("v8-jit")), x(c.get("silkjs-jit"), c.get("jsc-jit"))]
        cells += ["%.3f" % w.get(e, 0) for e in ("silkjs", "silkjs-jit", "v8-jit", "jsc-jit")]
        cells += [x(w.get("silkjs-jit"), w.get("v8-jit")), x(w.get("silkjs-jit"), w.get("jsc-jit"))]
        print("| %s | %s |" % (bench, " | ".join(cells)))
    if len(sys.argv) > 2:
        s = parse(sys.argv[2]).get("startup", {}).get("empty wall ms", {})
        print()
        print("Startup of an empty script, wall ms (median): " + ", ".join("%s %.1f" % kv for kv in s.items()))


if __name__ == "__main__":
    main()
