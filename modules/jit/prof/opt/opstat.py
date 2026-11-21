import sys,re,bisect,collections
# opstat.py DUMP CGOUT OP [N]: every instance of OP across optimized functions, by Ir, with executions and Ir/exec.
exec(open(sys.argv[0].replace('opstat.py','cgprof_core.py')).read())
