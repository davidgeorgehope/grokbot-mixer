"""After a local repair miss: take the next r5-pool plan that avoids the unresolved
pairs and also passes entry_cliff / does not expose Hayling 111-127 as solo.
If the pool has none (the 11/23 scan found 0), exit 2 so the caller can
search with --exclude 3cOEsXf-ic0. Does not loosen any check."""
import json,sys,os
sys.path.insert(0,'/workspace/mixes/src2')
os.chdir('/workspace/mixes/src2')
import plan_search as PS
import numpy as np

HAY='3cOEsXf-ic0'
HOLE=set(range(111,128))
POOL='plan_mix10_r5.pool.json'
OUT='plan_mix10_r6.json'

def als(tid, cache={}):
    if tid not in cache:
        cache[tid]=np.array(json.load(open(f'st/{tid}.json'))['bar']['all'],float)
    return cache[tid]

def cliffs(bl):
    out=[]
    for w in bl:
        kind,e,p,ib,X=w['w']
        wa,_=PS.windows(kind,e,p,ib,X,w['a'])
        c=PS.entry_cliff(als(w['a']),PS.entry_prev(kind,e,wa))
        if c>PS.ENTRY_CLIFF_DB:
            out.append((w['a'],w['b'],c))
    return out

def hayling_solo_hole(seq,bl):
    if HAY not in seq: return False
    inn=('n',0,0)
    for i,tid in enumerate(seq):
        if i>=len(bl): break
        kind,e,p,ib,X=bl[i]['w']
        m=PS._deck(inn,e,p, X if p is not None else 0, kind, tid)
        Xin=inn[2]
        if tid==HAY:
            solo=set(m[Xin:max(Xin,len(m)-X)])
            return bool(solo & HOLE)
        inn=(kind,ib,X)
    return False

def avoid_from_argv_or_hist():
    if len(sys.argv)>1 and sys.argv[1] not in('-',):
        p=sys.argv[1]
        if p.endswith('.json') and os.path.exists(p):
            d=json.load(open(p))
            hist=d.get('hist') or d
            avoid=set()
            for h in hist:
                if h.get('action') in('unresolved','budget'):
                    a,b=h['pair'].split('>')
                    avoid.add((a,b))
            return avoid
        # a>b,a>b
        avoid=set()
        for x in p.split(','):
            a,b=x.split('>')
            avoid.add((a,b))
        return avoid
    return set()

def main():
    avoid=avoid_from_argv_or_hist()
    pool=json.load(open(POOL))
    hits=[]
    for i,d in enumerate(pool):
        pairs={(w['a'],w['b']) for w in d['bl']}
        if pairs & avoid: continue
        if hayling_solo_hole(d['seq'],d['bl']): continue
        if cliffs(d['bl']): continue
        hits.append((i,d))
    print(f'pool={len(pool)} avoid={len(avoid)} safe={len(hits)}',flush=True)
    if not hits:
        return 2
    i,d=hits[0]
    # rebuild a plan_search plan from seq+windows via to_plan if available
    if hasattr(PS,'to_plan'):
        P=PS.to_plan(d['seq'],[w['w'] for w in d['bl']])
    else:
        P=[dict(id=t, out_win=(d['bl'][k]['w'] if k<len(d['bl']) else None)) for k,t in enumerate(d['seq'])]
    json.dump(P,open(OUT,'w'),indent=1)
    print('wrote',OUT,'from pool',i,'pred',d.get('pred'),flush=True)
    return 0

if __name__=='__main__':
    sys.exit(main())
