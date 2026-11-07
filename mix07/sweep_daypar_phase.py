#!/usr/bin/env python3
"""Bench Daydreaming→Parallel windows and score them with the new phase check."""
import copy, json, os, sys, traceback
import numpy as np, librosa
HERE='/workspace/mixes/src2'
sys.path.insert(0, HERE)
sys.path.insert(0, '/workspace/mixes/src/tests')
os.chdir(HERE)
os.environ.update(LOOP32='0', ECHO_MAX='2', STRUCT='1', FADE='tail', SWAP_PHRASE='1',
                  HIGH_SWAP='1', NUDGE='nudge07.json', PYTHONUNBUFFERED='1',
                  BB_SCRATCH='/tmp/bb_daypar')
os.environ.pop('PAIR_TABLE', None); os.environ.pop('SOFT', None)
import blend_bench as BB
import bassgap as G
import checks as C

DAY,PAR='MoYkYkoeb84','2s3M6oX2lfo'
DAY_EMIN=96
OUT='/workspace/mixes/mix07/sweep_daypar_phase.json'
os.makedirs(BB.SCR, exist_ok=True)

def shift_meta(M,s0):
    M=copy.deepcopy(M)
    def sh(pts):
        return [[p[0]-s0,p[1]]+list(p[2:]) for p in pts] if pts else pts
    for d in M['decks']:
        d['start_bar']-=s0; d['end_bar']-=s0
        au=d.get('auto') or {}
        for k,v in list(au.items()):
            if isinstance(v,list) and v and isinstance(v[0],(list,tuple)): au[k]=sh(v)
    for t in M['trans']:
        for k in ('start_bar','end_bar','swap_bar','high_bar'):
            if t.get(k) is not None: t[k]-=s0
        if t.get('bass_swap'): t['bass_swap']=[x-s0 for x in t['bass_swap']]
    return M

def phase_on_snip(M, wav, s0):
    y,_=librosa.load(wav, sr=22050, mono=True)
    o=librosa.onset.onset_strength(y=y, sr=22050, hop_length=64); fr=22050/64
    pad=int(round(s0*C.BAR*fr))
    o_pad=np.concatenate([np.zeros(pad, dtype=o.dtype), o])
    if hasattr(C.onset,"cache_clear"): C.onset.cache_clear()
    C.onset=lambda: (o_pad, fr)
    # decks in M are unshifted (absolute mix bars of the 2-track dry render, first track at 0)
    # snippet wav starts at s0 of that dry mix. Pad onset so bar indices match M.
    rows=C.bar_alignment_report(deck_pair=(M['decks'][0], M['decks'][1]))
    bad=C.alignment_failures(rows)
    return rows, bad

def main():
    raw=BB.cands_for(DAY,PAR,'dump_daypar')
    allowed={tuple(c['win']) for c in raw}
    extras=[
        ('r12', ['la',128,112,0,16]),
        ('n128_0_16', ['n',128,None,0,16]),
        ('drop16_e128', ['n',128,None,16,16]),
        ('drop32_e128', ['n',128,None,0,32]),
        ('drop16_e112', ['n',112,None,16,16]),
        ('drop32_e112', ['n',112,None,0,32]),
        ('n128_32_16', ['n',128,None,32,16]),
        ('lb128_16', ['lb',128,None,16,16]),
        ('n112_0_16', ['n',112,None,0,16]),
        ('n96_16_16', ['n',96,None,16,16]),
    ]
    fams=BB.families(raw, ['la',128,112,0,16])
    cands=[]
    seen=set()
    def add(fam,win,env=None):
        win=list(win)
        if tuple(win) not in allowed or win[1]<DAY_EMIN: return
        if win[4]>16 and win[0] in ('la','lx'): return
        key=(tuple(win), tuple(sorted((env or {}).items())))
        if key in seen: return
        seen.add(key)
        cands.append(dict(fam=fam,win=win,env=dict(env or {})))
    for c in fams: add(c['fam'], c['win'], c.get('env'))
    for fam,win in extras: add(fam,win,{})
    print('cands', len(cands), flush=True)
    results=[]
    for i,c in enumerate(cands):
        tag=f'dp_{i}_{c["fam"]}'
        print(f'\n=== {i+1}/{len(cands)} {c["fam"]} {c["win"]} {c["env"]} ===', flush=True)
        rec=dict(fam=c['fam'], win=c['win'], env=c['env'])
        try:
            dk,M=BB.render(c,DAY,PAR,tag)
            wav=f'{BB.SCR}/{tag}_master.wav'
            s0=c['snip']['s0']
            Ms=shift_meta(M,s0)
            gaps=G.check(Ms, wav)
            rows,bad=phase_on_snip(M, wav, s0)
            rec.update(bassgap=gaps, n_phase=len(rows), n_fail=len(bad),
                        fails=bad[:8], pass_phase=not bad, pass_bg=not gaps,
                        ok=not bad and not gaps, mp3=c.get('mp3'),
                        start=int(M['trans'][0]['start_bar']), end=int(M['trans'][0]['end_bar']))
            print('  bg', gaps, 'phase_fail', len(bad), 'ok', rec['ok'], flush=True)
            if bad:
                print('   e.g.', bad[0], flush=True)
        except Exception:
            rec['error']=traceback.format_exc()[-400:]; rec['ok']=False
            print('  ERR', rec['error'][:200], flush=True)
        results.append(rec)
        json.dump(results, open(OUT,'w'), indent=1, default=float)
    ok=[r for r in results if r.get('ok')]
    print('\nPASSING', len(ok), '/', len(results))
    for r in ok:
        print(' ', r['fam'], r['win'], r['env'])
    pick=ok[0] if ok else None
    # prefer natural drop-landing
    def score(r):
        w=r['win']
        drop = (w[3]+w[4]==32) or (w[0]=='lb' and w[3]==16)
        return (0 if drop else 1, 0 if w[0]=='n' else 1, -w[4])
    if ok:
        ok.sort(key=score); pick=ok[0]
    json.dump(dict(pick=pick, passing=ok, all=results), open(OUT,'w'), indent=1, default=float)
    print('PICK', pick)

if __name__=='__main__':
    main()
