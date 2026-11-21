import sys
sys.argv=[sys.argv[0]]+sys.argv[1:3]+['__none__']+sys.argv[3:]
exec(open(sys.argv[0].replace('fnstat.py','cgprof_core.py')).read().split("op=sys.argv[3]")[0])
K=int(sys.argv[4]); minex=int(sys.argv[5]) if len(sys.argv)>5 else 1
offs,end,insts=funcs[K]
for j,t in enumerate(insts):
    v=per.get(K,{}).get(j,0); e=cnt.get(regions[K][0]+offs[j],0)
    if e>=minex: print('%10d x%-9d %5.1f #%d %s'%(v,e,v/max(e,1),j,t[:110]))
