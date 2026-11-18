import os, subprocess, sys, re
HERE = os.path.dirname(os.path.abspath(__file__))
folder, title = sys.argv[1], sys.argv[2]
def run(*a): return subprocess.run(["python3", os.path.join(HERE, "perf_table.py"), *a], capture_output=True, text=True, check=True).stdout
k, o = HERE + "/jit-scorecard-results/%s/kernels.json" % folder, HERE + "/jit-scorecard-results/%s/octane.json" % folder
section = ("## Latest: %s\n\nRead one column: **Slower than V8**, how many times slower silkjs-jit (`--jit`) is than "
           "V8's JIT (1x would be V8's speed; lower is better). JSC's JIT gives nearly the same numbers. The second "
           "column is what the JIT gains over our own interpreter.\n\n%s\nFull table, every engine and benchmark. Kernel "
           "rows: ns per loop iteration, median of 7 processes, lower is better. Octane rows: score, median round, higher "
           "is better. Ratio columns: how many times faster the first engine is than the second. From "
           "`python3 docs/jit/perf_table.py [--simple] kernels.json octane.json`.\n\n%s\n") % (title, run("--simple", k, o), run(k, o))
doc = open(os.path.join(HERE, "jit-scorecard.md")).read()
doc = re.sub(r"## Latest: .*?(?=## How to rerun)", lambda m: section, doc, count=1, flags=re.S)
open(os.path.join(HERE, "jit-scorecard.md"), "w").write(doc)
head = "# SilkJS JIT against V8 and JSC\n\nCopied from docs/jit/jit-scorecard.md in silk-lang/lib-silkjs, branch claude/project-thread-6ys4ab. One host (x86-64 cloud container), every number MEASURED.\n\n"
open("/mnt/project-files/jit/scorecard.md", "w").write(head + section)
