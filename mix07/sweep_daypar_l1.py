#!/usr/bin/env python3
import json, os, sys, traceback, copy
import numpy as np, librosa
from scipy.signal import butter, sosfiltfilt
HERE='/workspace/mixes/src2'
sys.path[:0]=[HERE,'/workspace/mixes/src/tests','/workspace/mixes/mix07']
os.chdir(HERE)
os.environ.update(LOOP32='0', ECHO_MAX='2', STRUCT='1', FADE='tail', SWAP_PHRASE='1',
                  HIGH_SWAP='1', NUDGE='nudge07.json', PYTHONUNBUFFERED='1',
                  BB_SCRATCH='/tmp/bb_daypar2', SOFT='0')
os.environ.pop('PAIR_TABLE', None)
import blend_bench as BB
import bassgap as G
import checks as C
import engine
from sweep_daypar_phase import shift_meta, phase_on_snip
DAY,PAR='MoYkYkoeb84','2s3M6oX2lfo'
os.makedirs(BB.SCR, exist_ok=True)
OUT='/workspace/mixes/mix07/sweep_daypar_l1.json'
SR=44100; BAR=C.BAR
LP=butter(4,120,'low',fs=SR,output='sos')
db=lambda s:20*np.log10(np.sqrt(np.mean(s**2))+1e-9) if len(s) else -120

def l1_on(M):
    D=M['decks']; t=M['trans'][0]
    A=next(d for d in D if d['id']==t['a'] and not d.get('acap'))
    B=next(d for d in D if d['id']==t['b'] and not d.get('acap'))
    ya=engine.render_deck(A).mean(1).astype(np.float32); engine._cache.clear()
    yb=engine.render_deck(B).mean(1).astype(np.float32); engine._cache.clear()
    def bar_seg(y,d,bar,n=1):
        i=int(round((bar-d['start_bar'])*BAR*SR)); return y[max(0,i):i+int(n*BAR*SR)]
    s=int(t['start_bar']); sw=int(t['swap_bar']); e=int(min(A['end_bar'], max(t['end_bar'], sw+1)))
    refA=np.median([db(bar_seg(ya,A,b)) for b in range(max(int(A['start_bar']),s-8),s)] or [-20])
    nfail=0; worst=0.0
    for b in range(s-4, max(e,sw+8)+1):
        sa=bar_seg(ya,A,b) if A['start_bar']<=b<A['end_bar'] else np.zeros(0)
        sb=bar_seg(yb,B,b) if B['start_bar']<=b<B['end_bar'] else np.zeros(0)
        la,lb=db(sa),db(sb)
        if not (len(sa)>1000 and len(sb)>1000 and la>refA-14 and lb>refA-14 and abs(la-lb)<14):
            continue
        n=min(len(sa),len(sb))
        sa_,sb_=sosfiltfilt(LP,sa[:n]),sosfiltfilt(LP,sb[:n])
        lsa,lsb,lsum=db(sa_),db(sb_),db(sa_+sb_)
        over=lsum-max(lsa,lsb)
        if over>worst: worst=over
        if lsum>max(lsa,lsb)+3 and lsum>refA-25: nfail+=1
        if lsa>la-6 and lsb>lb-6 and min(lsa,lsb)>refA-12: nfail+=1
    return nfail, round(float(worst),2)

def main():
    raw=BB.cands_for(DAY,PAR,'dump')
    allowed={tuple(c['win']) for c in raw}
    cands=[]
    def add(fam,win,env=None):
        win=list(win)
        if tuple(win) not in allowed: return
        cands.append(dict(fam=fam,win=win,env=dict(env or {})))
    add('n128_32_16', ['n',128,None,32,16], {})
    for sp in ('0.15','0.25','0.35','0.45','0.55','0.65','0.75'):
        add(f'sw{sp}', ['n',128,None,32,16], {'SWAP_POS':sp})
    add('n128_48_16', ['n',128,None,48,16], {})
    add('n128_64_16', ['n',128,None,64,16], {})
    add('n128_16_16', ['n',128,None,16,16], {})
    add('la_sw25', ['la',128,112,32,16], {'SWAP_POS':'0.25'})
    add('la_sw65', ['la',128,112,32,16], {'SWAP_POS':'0.65'})
    print('cands', len(cands), flush=True)
    results=[]
    for i,c in enumerate(cands):
        tag=f'x{i}_{c["fam"]}'
        print(f'\n=== {i+1}/{len(cands)} {c["fam"]} {c["win"]} {c["env"]} ===', flush=True)
        rec=dict(fam=c['fam'], win=c['win'], env=c['env'])
        try:
            dk,M=BB.render(c,DAY,PAR,tag)
            wav=f'{BB.SCR}/{tag}_master.wav'
            s0=c['snip']['s0']
            Ms=shift_meta(M,s0)
            gaps=G.check(Ms, wav)
            rows,bad=phase_on_snip(M, wav, s0)
            nL1, worst=l1_on(M)
            rec.update(bassgap=gaps, n_phase=len(rows), n_fail=len(bad),
                       n_l1=nL1, l1_worst=worst,
                       pass_phase=not bad, pass_bg=not gaps, pass_l1=nL1==0,
                       ok=not bad and not gaps and nL1==0)
            print('  bg',gaps,'phase',len(bad),'L1',nL1,'worst',worst,'ok',rec['ok'], flush=True)
            if bad: print('   phase e.g.', bad[0], flush=True)
        except Exception:
            rec['error']=traceback.format_exc()[-400:]; rec['ok']=False
            print('  ERR', rec['error'][:240], flush=True)
        results.append(rec)
        json.dump(results, open(OUT,'w'), indent=1, default=float)
    ok=[r for r in results if r.get('ok')]
    print('\nPASSING', len(ok), '/', len(results))
    for r in ok:
        print(' ', r['fam'], r['win'], r['env'], 'l1', r.get('l1_worst'))
    json.dump(dict(passing=ok, all=results), open(OUT,'w'), indent=1, default=float)

if __name__=='__main__':
    main()
