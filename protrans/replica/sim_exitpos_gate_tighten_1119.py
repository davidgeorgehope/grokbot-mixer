#!/usr/bin/env python3
"""Train-only (no held-out tuning) simulation of tighter EXITPOS_GATE hard checks.
Dumps EXITPOS (ungated) family cands, then applies candidate rules.
rules.json is not written."""
import os, sys, json, copy
H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(H))
sys.path.insert(0, os.path.join(H, 'halftime'))
import paths, recreate, run_admitted_tune as T
import exitpos_gate as EG
os.makedirs('/tmp/protrans_bench', exist_ok=True)
os.environ['BB_SCRATCH'] = '/tmp/protrans_bench'
os.environ['PREF_W'] = '0'
sys.path.insert(0, paths.SRC2)
import blend_bench as BB

base_rules = json.load(open(paths.RULES))
assert not base_rules.get('EXITPOS') and not base_rules.get('EXITPOS_GATE')
recs = T.load_recs()
floor = {json.loads(l)['id']: json.loads(l) for l in open(os.path.join(paths.RESULTS, 'score_ckpt', 'cb1119_base.jsonl'))}
epg = {json.loads(l)['id']: json.loads(l) for l in open(os.path.join(paths.RESULTS, 'score_ckpt', 'cs_epg2_1119.jsonl'))}
epgs = {json.loads(l)['id']: json.loads(l) for l in open(os.path.join(paths.RESULTS, 'score_ckpt', 'cs_epgs2_1119.jsonl'))}

def hard_ok(alt, default, sa, sb, full_before=False, cap=None):
    ae, ac, aX = alt; be, bc, bX = default
    if ae >= be: return False
    ld = EG.last_drop_end(sa)
    if ld is not None:
        if full_before:
            if ae - aX < ld: return False
        elif ae < ld:
            return False
    if cap is not None and (be - ae) > cap: return False
    if not EG.drop1_in(ac, aX, sb): return False
    return True

def decide(cs, sa, sb, ya, dj, full_before, cap):
    """Pick nat_short / nat_long under a candidate hard_ok, using EXITPOS costs in cs."""
    def fam(xpred):
        n = [c for c in cs if c['win'][0]=='n' and xpred(c['win'][4])]
        if not n: return None
        # default cost is not in this dump (these are EXITPOS costs). Reconstructing default
        # is what mix_simple _dcost does; for simulation we take the already-known floor
        # window as the default of that family, and the min-EXITPOS hard_ok alt.
        return n
    return None  # filled below per pair with floor default

# First dump EXITPOS-only cands for all 33
os.environ.update(recreate.apply_rules({**base_rules, 'EXITPOS': 1}))
os.chdir(paths.SRC2)
dumps = {}
for rec in recs:
    i = rec['id']
    ya, yb = rec['a']['yt'], rec['b']['yt']
    tag = 'epgtight_' + i.replace('/', '_')[-20:]
    cs = BB.cands_for(ya, yb, tag)
    dumps[i] = cs
    print('dumped', i, 'n', len(cs), flush=True)

# Helper: default window of a family from floor pick if same family, else min among 16-aligned
# We use the scored floor window as default (eval path), and only consider kind n.

def win_tuple(w):
    return (w[1], w[3], w[4])

variants = {
    'current': dict(full_before=False, cap=None),
    'full_before': dict(full_before=True, cap=None),
    'cap16': dict(full_before=False, cap=16),
    'full_before_cap16': dict(full_before=True, cap=16),
}

rows = []
for rec in recs:
    i = rec['id']
    ya, yb = rec['a']['yt'], rec['b']['yt']
    sa = json.load(open(os.path.join(paths.SRC2, 'st', ya + '.sections.json')))
    sb = json.load(open(os.path.join(paths.SRC2, 'st', yb + '.sections.json')))
    fw = floor[i]['pick']['win']
    default = win_tuple(fw)
    cs = dumps[i]
    # EXITPOS-cost nat windows of the same X as the floor family (the scored family)
    X = fw[4]
    nat = [c for c in cs if c['win'][0]=='n' and c['win'][4]==X]
    out = dict(id=i, split=rec['split'], dj=rec['dj'], floor_win=fw,
               floor_score=floor[i]['score']['score'],
               epg_win=epg[i]['pick']['win'], epg_score=epg[i]['score']['score'],
               epgs_win=epgs[i]['pick']['win'], epgs_score=epgs[i]['score']['score'])
    for name, kw in variants.items():
        alts = [c for c in nat if hard_ok(win_tuple(c['win']), default, sa, sb, **kw)]
        take, info, altw = False, dict(reason='no_alt'), None
        if alts:
            ac = min(alts, key=lambda c: c['cost'])
            altw = win_tuple(ac['win'])
            # LODO: pass dj, not ya, so we do not use in-sample per-track weights when choosing a rule
            take, info = EG.should_switch(default, altw, sa, sb, dj=rec['dj'])
            # should_switch still uses current hard_ok; override with our hard_ok already filtered,
            # but should_switch will re-check current hard_ok (exit>=ld) which is weaker, so a
            # full_before-legal alt also passes current hard_ok. Cap is not in should_switch;
            # we already filtered. Re-apply take only if our hard_ok holds (it does).
            if not hard_ok(altw, default, sa, sb, **kw):
                take, info = False, dict(reason='hard')
        # If should_switch uses current hard_ok only, take may be True. Good.
        # But should_switch may also reject on model. Keep that.
        # One issue: should_switch current hard_ok allows past=0, we already filtered those out
        # for full_before, so take refers to the mid-outro alt.
        picked = list(altw) if (take and altw and altw != default) else list(default)
        out[name] = dict(take=bool(take and altw and altw != default), reason=info.get('reason'),
                         p=info.get('p'), alt=list(altw) if altw else None, picked=picked, **{k:v for k,v in info.items() if k not in ('reason','p')})
    rows.append(out)
    sh = out['full_before']
    print(f"{i:40} {rec['split']:5} full_before take={sh['take']} {sh['reason']} {default} -> {sh['alt']} picked={sh['picked']}", flush=True)

# Score implication: if picked equals epg/epgs/floor window, we know the score; else unknown (need render)
def score_of(win, i):
    win = list(win)
    # normalize to [kind, e, None, cue, X] if needed
    if len(win)==3:
        w = ['n', win[0], None, win[1], win[2]]
    else:
        w = win
    for src, key in ((floor, 'floor'), (epg, 'epg'), (epgs, 'epgs')):
        pw = src[i]['pick']['win']
        if pw == w or pw[1:]==w[1:] or (len(w)==3 and pw[1]==w[0] and pw[3]==w[1] and pw[4]==w[2]):
            return src[i]['score']['score'], key
        if list(pw)[1:5:2]+[pw[4]]==w or False:
            return src[i]['score']['score'], key
    # compare (e,cue,X)
    def ecx(ww):
        if len(ww)==3: return tuple(ww)
        return (ww[1], ww[3], ww[4])
    for src, key in ((floor, 'floor'), (epg, 'epg'), (epgs, 'epgs')):
        if ecx(src[i]['pick']['win'])==ecx(w):
            return src[i]['score']['score'], key
    return None, None

print('\n=== train means if we could score known windows ===')
for name in variants:
    tr = [r for r in rows if r['split']=='train']
    te = [r for r in rows if r['split']=='test']
    def mean_split(L):
        scs, missing=[], []
        for r in L:
            s, src = score_of(r[name]['picked'], r['id'])
            if s is None: missing.append((r['id'], r[name]['picked']))
            else: scs.append(s)
        return (sum(scs)/len(scs) if scs else None), len(scs), missing
    tm, tn, tmiss = mean_split(tr)
    xm, xn, xmiss = mean_split(te)
    ntake=sum(r[name]['take'] for r in rows)
    ntake_tr=sum(r[name]['take'] for r in tr)
    print(f"{name}: take {ntake} (train {ntake_tr})  train_mean={tm} n={tn} miss={tmiss}  test_mean={xm} n={xn} miss={xmiss}  [test is confirmation only, not used to choose]")

outp = os.path.join(H, 'sim_exitpos_gate_tighten_1119.json')
json.dump(dict(rows=rows, variants=list(variants)), open(outp,'w'), indent=1)
print('wrote', outp)
