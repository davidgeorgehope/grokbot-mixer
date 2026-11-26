"""Resumable learned-pro-fade fitter on corpus_v2 dev pairs (27, none from split.json held-out mixes).
Per-pair rows -> nightly_1125_work/profade_fit/rows.jsonl."""
import json, os, sys, glob, time, numpy as np
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, '/workspace/mixes/protrans')
sys.path.insert(0, '/workspace/mixes/protrans/replica')
import st_pin
os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()

W = '/workspace/mixes/protrans/replica/nightly_1125_work/profade_fit'
DEV_PAIRS = json.load(open('/workspace/mixes/protrans/replica/nightly_1125_work/profade_fit/dev27_pairs.json'))
PICKS_CACHE = '/workspace/mixes/protrans/replica/nightly_1125_work/profade_fit/dev27_picks.json'

US = np.linspace(0.0, 1.0, 11)
PRO_TARGET = {
    'all':  {'a': np.array([-1.5, -1.5, -1.6, -1.6, -3.4, -7.8, -11.0, -11.1, -11.1, -12.4, -16.1]),
             'b': np.array([-8.4, -6.6, -4.7, -3.3, -2.5, -2.4,  -1.0,  -0.9,  -0.8,  -0.6,  -0.8])},
    'bass': {'a': np.array([-0.5, -1.3, -3.3, -3.1, -5.7, -3.6, -13.5, -14.0, -14.1, -14.6, -16.5]),
             'b': np.array([-8.7, -6.4, -3.7, -4.1, -1.0, -1.5,  -0.5,  -1.1,  -1.0,  -0.4,  -1.0])},
    'mids': {'a': np.array([-1.3, -1.2, -1.2, -1.6, -2.8, -6.8,  -8.3,  -8.6,  -8.1,  -9.4, -12.1]),
             'b': np.array([-7.7, -6.8, -6.1, -3.4, -2.6, -1.6,  -0.8,  -0.4,  -0.2,  -0.4,  -0.1])},
    'highs':{'a': np.array([-1.4, -0.9, -0.9, -0.3, -1.0, -0.5,  -2.6,  -4.1,  -2.7,  -3.7,  -4.8]),
             'b': np.array([-2.1, -1.6, -0.9, -0.7, -0.6, -0.2,  -0.8,  -0.5,  -0.4,  -0.5,  -0.2])},
}

def _eval_lane(pts, ts, default=1.0):
    if not pts: return np.full_like(ts, default, dtype=float)
    return np.interp(ts, [p[0] for p in pts], [p[1] for p in pts], left=pts[0][1], right=pts[-1][1])

def _curve_mae(M):
    t = M['trans'][0]
    s, e = int(round(float(t['start_bar']))), int(round(float(t['end_bar'])))
    if e - s < 4: return {}
    dA, dB = M['decks'][0]['auto'], M['decks'][1]['auto']
    bars = np.arange(s, e + 1)
    sub = np.linspace(0.0, 1.0, 16, endpoint=False)
    ts_u = np.linspace(0.0, 1.0, len(bars))
    maes = {}
    for band in ('all', 'bass', 'mids', 'highs'):
        ga_b = np.zeros(len(bars)); gb_b = np.zeros(len(bars))
        for idx, kb in enumerate(bars):
            ts = kb + sub
            ga = _eval_lane(dA.get('gain'), ts, 1.0); gb = _eval_lane(dB.get('gain'), ts, 1.0)
            la = _eval_lane(dA.get('low'), ts, 1.0);  lb = _eval_lane(dB.get('low'), ts, 1.0)
            ha = _eval_lane(dA.get('high'), ts, 1.0); hb = _eval_lane(dB.get('high'), ts, 1.0)
            fa = ga * (la if band=='bass' else (ha if band=='highs' else 1.0))
            fb = gb * (lb if band=='bass' else (hb if band=='highs' else 1.0))
            ga_b[idx] = float(np.clip(20*np.log10(np.sqrt(np.mean(fa**2))+1e-9), -30, 4))
            gb_b[idx] = float(np.clip(20*np.log10(np.sqrt(np.mean(fb**2))+1e-9), -30, 4))
        ua = np.interp(US, ts_u, ga_b); ub = np.interp(US, ts_u, gb_b)
        maes[band] = float(0.5 * (np.mean(np.abs(ua - PRO_TARGET[band]['a'])) + np.mean(np.abs(ub - PRO_TARGET[band]['b']))))
    return maes

def _pick_one(args):
    p, idx = args
    os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
    import paths, recreate
    os.chdir(paths.SRC2)
    rules = recreate.load_rules()
    rules['HARD_FALLBACK'] = 0
    tag = f'pk27_{idx}'
    try:
        res = recreate.recreate(p['a']['yt'], p['b']['yt'], p['sa'], p['sb'],
                                hint_a_played_sec=p['hint'], rules=rules, tag=tag)
        return p['id'], dict(fam=res['fam'], win=res['win'])
    finally:
        for fp in glob.glob(f'/tmp/protrans_bench/{tag}*'):
            try: os.remove(fp)
            except Exception: pass

def ensure_picks():
    if os.path.exists(PICKS_CACHE):
        return json.load(open(PICKS_CACHE))
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=4) as ex:
        res = dict(ex.map(_pick_one, [(p, i) for i, p in enumerate(DEV_PAIRS)]))
    json.dump(res, open(PICKS_CACHE, 'w'), indent=1)
    print(f"Cached 27 picks in {time.time()-t0:.1f}s", flush=True)
    return res

def _eval_one(args):
    p, pick_info, env_delta, tag, idx = args
    os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
    import paths, recreate, score, score_v2 as S2, hardcheck as HC, blend_diag as BD, blend_bench as BB
    from engine import BS
    os.chdir(paths.SRC2)
    BB.SCR = '/tmp/protrans_bench'
    os.makedirs(BB.SCR, exist_ok=True)
    rules = recreate.load_rules()
    rules['HARD_FALLBACK'] = 0
    rules.update(env_delta)
    env = recreate.apply_rules(rules)
    t_tag = f'{tag}_{idx}'
    try:
        c = dict(fam=pick_info['fam'], win=pick_info['win'], env=env)
        dk, M = BB.render(c, p['a']['yt'], p['b']['yt'], t_tag)
        ours = f'{BB.SCR}/{t_tag}.mp3'
        meta = f'{BB.SCR}/{t_tag}_meta.json'
        json.dump(M, open(meta, 'w'), default=str)
        v1 = score.score(p['pro_clip'], ours, src_a=p['sa'], src_b=p['sb'], use_demucs=False, cache=paths.CACHE)
        v2 = S2.score_v2(p['pro_clip'], ours, p['sa'], p['sb'], v1=v1, use_demucs=False, cache=paths.CACHE)
        hc = HC.check(meta)
        t = M['trans'][0]
        s0, A, B = BD.crop_decks(M, 0); n = int(round(len(A) / BS))
        s, e = max(0, int(float(t['start_bar']) - s0)), min(n, int(float(t['end_bar']) - s0))
        loA, loB = BD.band_bar_db(A, n, BS, 'low', 120), BD.band_bar_db(B, n, BS, 'low', 120)
        sumlo = BD.band_bar_db(A + B, n, BS, 'low', 120)
        l1_ex = float(np.max(sumlo[s:e] - np.maximum(loA[s:e], loB[s:e]))) if e > s else 0.0
        refA = float(np.median(loA[:max(1, s)])) if s >= 2 else float(np.percentile(loA, 80))
        refB = float(np.median(loB[e:])) if n - e >= 2 else float(np.percentile(loB, 80))
        dbl_bass = int(np.sum((loA[s:e] > refA - 6.0) & (loB[s:e] > refB - 6.0)))
        # audible-L1: same excess, only on bars whose summed lows sit within 12 dB of the louder body
        aud = sumlo[s:e] >= max(refA, refB) - 12.0
        l1_aud = float(np.max((sumlo[s:e] - np.maximum(loA[s:e], loB[s:e]))[aud])) if e > s and aud.any() else 0.0
        cmae = _curve_mae(M)
        out = dict(id=p['id'], v1=float(v1['score']), v2=float(v2['official_v2']), hc=hc,
                   l1_ex=round(l1_ex, 2), l1_fail=(l1_ex > 3.0), l1_aud=round(l1_aud, 2), l1a_fail=(l1_aud > 3.0), dbl_bass=dbl_bass, cmae=cmae,
                   pf=(t.get('pro_fade') or {}).get('info'), se=[float(t['start_bar']), float(t['end_bar'])], fam=pick_info['fam'])
    except Exception as ex:
        out = dict(id=p['id'], error=f'{type(ex).__name__}: {ex}'[-250:])
    finally:
        for fp in glob.glob(f'/tmp/protrans_bench/{t_tag}*'):
            try: os.remove(fp)
            except Exception: pass
    return out

def run_cfg(name, env_delta, picks):
    t0 = time.time()
    tasks = [(p, picks[p['id']], env_delta, f'pf_{name}', i) for i, p in enumerate(DEV_PAIRS)]
    with ProcessPoolExecutor(max_workers=int(os.environ.get('PFW', 4))) as ex:
        rows = list(ex.map(_eval_one, tasks))
    ok = [r for r in rows if 'error' not in r]
    summ = dict(
        name=name, n=len(ok), err=len(rows)-len(ok), sec=round(time.time()-t0, 1),
        v1=round(float(np.mean([r['v1'] for r in ok])), 2),
        v2=round(float(np.mean([r['v2'] for r in ok])), 2),
        hf=sum(1 for r in ok if r['hc']['hard_fail']),
        beat=sum(1 for r in ok if r['hc']['beat_clash']),
        hole=sum(1 for r in ok if r['hc']['bass_hole']),
        pump=sum(1 for r in ok if r['hc']['pumping']),
        van=sum(1 for r in ok if r['hc']['incoming_vanish']),
        l1_fail=sum(1 for r in ok if r['l1_fail']),
        max_l1=round(max(r['l1_ex'] for r in ok), 2),
        l1a_fail=sum(1 for r in ok if r.get('l1a_fail')),
        dbl_bass=round(float(np.mean([r['dbl_bass'] for r in ok])), 2),
        mae_all=round(float(np.mean([r['cmae']['all'] for r in ok if r['cmae']])), 2),
        mae_bass=round(float(np.mean([r['cmae']['bass'] for r in ok if r['cmae']])), 2),
        mae_mids=round(float(np.mean([r['cmae']['mids'] for r in ok if r['cmae']])), 2),
        mae_high=round(float(np.mean([r['cmae']['highs'] for r in ok if r['cmae']])), 2),
    )
    print("RESULT:", json.dumps(summ), flush=True)
    with open(f'{W}/rows.jsonl', 'a') as f:
        f.write(json.dumps(dict(summary=summ, env=env_delta, rows=rows), default=str) + '\n')
    return summ

def done_names():
    if not os.path.exists(f'{W}/rows.jsonl'): return {}
    return {json.loads(l)['summary']['name']: json.loads(l)['summary'] for l in open(f'{W}/rows.jsonl')}

def run_grid(cands):
    """Resumable: skips configs already in rows.jsonl."""
    picks = ensure_picks(); done = done_names(); out = []
    for nm, ed in cands:
        out.append(done[nm] if nm in done else run_cfg(nm, ed, picks))
    return out

if __name__ == '__main__' and False:
    picks = ensure_picks()
    run_cfg('bb_base', {}, picks)
    run_cfg('C0_bass40', {'PRO_FADE': 1, 'PRO_FADE_ENTRY_DB': -10, 'PRO_FADE_SHELF_DB': -11, 'PRO_FADE_EXIT_SLOPE': 2.0, 'PRO_FADE_HIGH_OFS': 6.5, 'PRO_FADE_BASS_CUT_DB': -40}, picks)
    run_cfg('C1_bass24', {'PRO_FADE': 1, 'PRO_FADE_ENTRY_DB': -10, 'PRO_FADE_SHELF_DB': -11, 'PRO_FADE_EXIT_SLOPE': 2.0, 'PRO_FADE_HIGH_OFS': 6.5, 'PRO_FADE_BASS_CUT_DB': -24}, picks)
    run_cfg('C2_bass18', {'PRO_FADE': 1, 'PRO_FADE_ENTRY_DB': -10, 'PRO_FADE_SHELF_DB': -11, 'PRO_FADE_EXIT_SLOPE': 2.0, 'PRO_FADE_HIGH_OFS': 6.5, 'PRO_FADE_BASS_CUT_DB': -18}, picks)
    run_cfg('C3_bass14', {'PRO_FADE': 1, 'PRO_FADE_ENTRY_DB': -10, 'PRO_FADE_SHELF_DB': -11, 'PRO_FADE_EXIT_SLOPE': 2.0, 'PRO_FADE_HIGH_OFS': 6.5, 'PRO_FADE_BASS_CUT_DB': -14}, picks)
    run_cfg('C4_nohigh', {'PRO_FADE': 1, 'PRO_FADE_ENTRY_DB': -10, 'PRO_FADE_SHELF_DB': -11, 'PRO_FADE_EXIT_SLOPE': 2.0, 'PRO_FADE_HIGH_OFS': 0.0, 'PRO_FADE_BASS_CUT_DB': -24}, picks)
