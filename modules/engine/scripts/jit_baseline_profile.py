#!/usr/bin/env python3
"""Where the instructions of baseline code go (docs/jit/baseline.md).

Runs a script in the JIT shell under callgrind with `--jit-baseline --jit-dump`, then joins
callgrind's count per machine instruction with the code map the shell dumps (`jit: baseline
map`: the code offset each bytecode instruction's template, the prologue, the shared tails,
every slow path and every exit starts at).

    python3 scripts/jit_baseline_profile.py <silkjs-jit-shell> <script.js>
        [--top N]            rows per table (default 40)
        [--show NAME]        disassemble the hottest part of that name with its counts
                             (an opcode name, or @prologue, @leave, @slow:call, ...)
        [--functions]        one row per compiled function as well
        [--time SAMPLER.so]  where the time goes instead: runs the script natively under an
                             LD_PRELOAD sampler that writes one program counter per line to
                             $SAMPLES_OUT, and prints each part's share of the samples.
                             Next to the instruction shares this shows what stalls; use a
                             script that runs for seconds (the sampler ticks every 4 ms).

Prints the run's total, the share spent in baseline code, then one row per kind of part:
instructions, share of baseline code, times entered and instructions per entry. A template's
row counts only its straight path; what it does out of line is in the @slow rows, and the row
`+slow` of an opcode adds the slow paths entered from it.
"""
import argparse, collections, os, re, subprocess, sys, tempfile

MARKS = {0x1000: "@prologue", 0x1001: "@leave", 0x1002: "@finish", 0x1003: "@overflow", 0x1004: "@exit"}
SLOW = {0: "release", 1: "release-object", 2: "helper", 3: "equal", 4: "truthy", 5: "back-edge", 6: "call",
        8: "variable", 9: "attached"}


def what_name(text):
    if not text.startswith("@"): return text
    value = int(text[1:])
    if value in MARKS: return MARKS[value]
    if value >= 0x1100: return "@slow:" + SLOW.get(value - 0x1100, str(value - 0x1100))
    return text


def compiled(stderr):
    """Each compiled function in a --jit-dump log: (address, bytes, [(offset, pc, part)])."""
    functions = []
    lines = stderr.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"jit: baseline code at (\d+) ([0-9a-f]+)$", line)
        if not m: continue
        start = int(m.group(1)); code = bytes.fromhex(m.group(2))
        entries = []
        for follow in lines[i + 1:i + 4]:
            if follow.startswith("jit: baseline map"):
                for item in follow.split()[3:]:
                    offset, pc, what = item.split(":", 2)
                    entries.append((int(offset), int(pc), what_name(what)))
                break
        functions.append((start, code, entries))
    functions.sort()
    return functions


def time_shares(args):
    out = tempfile.mktemp(suffix=".samples")
    command = [args.shell, "--jit-baseline", "--jit-dump"]
    if args.threshold: command.append("--jit-threshold=" + args.threshold)
    run = subprocess.run(command + [args.script], capture_output=True, text=True,
                         env=dict(os.environ, LD_PRELOAD=os.path.abspath(args.time), SAMPLES_OUT=out))
    functions = compiled(run.stderr)
    samples = [int(line, 16) for line in open(out) if line.strip()]
    for leftover in (out, out + ".maps"):
        if os.path.exists(leftover): os.unlink(leftover)
    rows = collections.Counter()
    inside = 0
    for sample in samples:
        for start, code, entries in functions:
            if not start <= sample < start + len(code): continue
            name = "?"
            for offset, _, what in entries:
                if offset > sample - start: break
                name = what
            rows[name] += 1
            inside += 1
            break
    print("samples %d, baseline code %d (%.1f%%), %d functions" % (len(samples), inside, 100.0 * inside / max(len(samples), 1), len(functions)))
    print("%8s %7s  %s" % ("samples", "share", "part"))
    for name, count in rows.most_common(args.top): print("%8d %6.2f%%  %s" % (count, 100.0 * count / max(inside, 1), name))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("shell")
    parser.add_argument("script")
    parser.add_argument("--top", type=int, default=40)
    parser.add_argument("--show")
    parser.add_argument("--functions", action="store_true", help="also one row per compiled function")
    parser.add_argument("--threshold", default=None, help="pass --jit-threshold")
    parser.add_argument("--time", default=None, help="an LD_PRELOAD sampler: print time shares instead")
    args = parser.parse_args()
    if args.time: return time_shares(args)
    out = tempfile.mktemp(suffix=".cg")
    command = ["valgrind", "--tool=callgrind", "--dump-instr=yes", "--compress-pos=no", "--compress-strings=no",
               "--callgrind-out-file=" + out, args.shell, "--jit-baseline", "--jit-dump"]
    if args.threshold: command.append("--jit-threshold=" + args.threshold)
    run = subprocess.run(command + [args.script], capture_output=True, text=True)
    total = int(re.search(r"Collected : (\d+)", run.stderr).group(1))
    functions = compiled(run.stderr)
    counts = collections.Counter()
    for line in open(out, errors="replace"):
        if line.startswith("calls="):
            skip = True
            continue
        if line.startswith("0x"):
            if locals().get("skip"):
                skip = False
                continue
            parts = line.split()
            counts[int(parts[0], 16)] += int(parts[-1])
        else:
            skip = False
    os.unlink(out)
    rows = collections.defaultdict(lambda: [0, 0])      # name -> [instructions, entries]
    slow_of = collections.Counter()                      # opcode -> instructions of slow paths entered from it
    hottest = {}                                         # name -> (instructions, function index, entry index)
    inside = 0
    for f, (start, code, entries) in enumerate(functions):
        opcode_at = {pc: what for _, pc, what in entries if not what.startswith("@")}
        for k, (offset, pc, what) in enumerate(entries):
            end = entries[k + 1][0] if k + 1 < len(entries) else len(code)
            spent = sum(counts.get(start + a, 0) for a in range(offset, end))
            if end > offset:
                rows[what][0] += spent
                rows[what][1] += counts.get(start + offset, 0)
            inside += spent
            if what.startswith("@slow") and pc in opcode_at: slow_of[opcode_at[pc]] += spent
            if spent > hottest.get(what, (0,))[0]: hottest[what] = (spent, f, k)
    print("total %d, baseline code %d (%.1f%%), %d functions" % (total, inside, 100.0 * inside / max(total, 1), len(functions)))
    if args.functions:
        print("%14s %12s %8s %6s  %s" % ("instructions", "entered", "each", "bytes", "function (bytecode instructions, calls it makes)"))
        table = []
        for start, code, entries in functions:
            spent = sum(counts.get(start + a, 0) for a in range(len(code)))
            entered = counts.get(start, 0)
            ops = [what for _, _, what in entries if not what.startswith("@")]
            calls = sum(1 for what in ops if what.startswith("call"))
            table.append((spent, entered, len(code), len(ops), calls))
        for spent, entered, size, ops, calls in sorted(table, reverse=True):
            print("%14d %12d %8.1f %6d  %d instructions, %d call sites" % (spent, entered, spent / max(entered, 1), size, ops, calls))
    print("%14s %7s %12s %8s  %s" % ("instructions", "share", "entered", "each", "part"))
    ordered = sorted(rows.items(), key=lambda item: -item[1][0])
    for name, (spent, entered) in ordered[:args.top]:
        if spent == 0: continue
        extra = ""
        if slow_of.get(name): extra = "   +slow %d" % slow_of[name]
        print("%14d %6.2f%% %12d %8.1f  %s%s" % (spent, 100.0 * spent / max(inside, 1), entered, spent / max(entered, 1), name, extra))
    if args.show and args.show in hottest:
        _, f, k = hottest[args.show]
        start, code, entries = functions[f]
        offset = entries[k][0]
        end = entries[k + 1][0] if k + 1 < len(entries) else len(code)
        blob = tempfile.mktemp(suffix=".bin")
        open(blob, "wb").write(code[offset:end])
        dis = subprocess.run(["objdump", "-D", "-b", "binary", "-mi386:x86-64", "-M", "intel", "--adjust-vma=%d" % (start + offset), blob],
                             capture_output=True, text=True).stdout
        os.unlink(blob)
        print("\n%s at bytecode offset %d:" % (args.show, entries[k][1]))
        for line in dis.splitlines():
            m = re.match(r"\s*([0-9a-f]+):\s+(.*)$", line)
            if not m: continue
            address = int(m.group(1), 16)
            text = m.group(2).split("\t")
            print("%12d  %s" % (counts.get(address, 0), text[-1] if len(text) > 1 else m.group(2)))


if __name__ == "__main__":
    main()
