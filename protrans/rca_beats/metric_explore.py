import json,glob,sys,numpy as np
sys.path.insert(0,'/workspace/mixes/src2')
def m1(rows,cp_min=.2,gain=.1,off=25,rad=15):
    dd=[r for r in rows if 'lag_ms' in r]
    if len(dd)<3:return None
    o=[r['lag_ms'] for r in dd if r['c_peak']>=cp_min and r['c_peak']-r['c0']>=gain and abs(r['lag_ms'])>off]
    best=max([sum(1 for y in o if abs(((y-x)+172.4)%344.8-172.4)<=rad) for x in o],default=0)
    return round(best/len(dd),3)
def load():
    P,O={},{}
    for f in glob.glob('/workspace/mixes/protrans/rca_beats/cal_*.json'):
        r=json.load(open(f))
        if 'rows' in r.get('pro',{}):P[r['id']]=r['pro']['rows']
        if 'rows' in r.get('ours',{}):O[r['id']]=r['ours']['rows']
    return P,O
if __name__=='__main__':
    import drumclash as D
    P,O=load()
    known={}
    for a,b,w,lk,l in [('J3oTRY7AdE4','ksVDZt9_0J4',['n',208,None,48,16],0,'hm09'),('tCyYwek-o28','u6cggHmZEAs',['n',224,None,48,16],0,'js12 off'),('tCyYwek-o28','u6cggHmZEAs',['n',224,None,48,16],-66.8,'js12 lock'),('wUVt_GsvMzw','tCyYwek-o28',['n',240,None,24,16],0,'js11 off'),('wUVt_GsvMzw','tCyYwek-o28',['n',240,None,24,16],123.4,'js11 lock'),('zEvLsOVhg0I','W77cCOreg_0',['n',192,None,32,16],0,'hm13')]:
        known[l]=D.window_clash(a,b,w,lk)['rows']
    for cfg in [dict(),dict(cp_min=.25),dict(cp_min=.3),dict(gain=.15),dict(cp_min=.15,gain=.05)]:
        pv=sorted(v for v in (m1(r,**cfg) for r in P.values()) if v is not None)
        ov=sorted(v for v in (m1(r,**cfg) for r in O.values()) if v is not None)
        print(cfg,'pro n',len(pv),'p95',np.percentile(pv,95) if pv else None,'max',pv[-3:],'| ours >p95:',sum(v>np.percentile(pv,95) for v in ov),'/',len(ov),'| known',{k:m1(v,**cfg) for k,v in known.items()})
