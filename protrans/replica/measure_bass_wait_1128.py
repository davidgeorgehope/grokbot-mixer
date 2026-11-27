"""Measure current default vs BASS_WAIT on dev-27 (same ridegate windows) plus any extra pair lists.

Official v1/v2 are higher-is-better. Also official hard checks, the 90 Hz lows_hole sensor,
and official bass-stem similarity. Keeps renders under /tmp/protrans_bench and a work dir
so holes can be checked against the actual audio. Does not write rules.json.
"""
from __future__ import annotations
import json, os, sys, time, glob, shutil
from concurrent.futures import ProcessPoolExecutor
import numpy as np

sys.path.insert(0, '/workspace/mixes/protrans')
sys.path.insert(0, '/workspace/mixes/protrans/replica')
import st_pin
os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()

W = '/workspace/mixes/protrans/replica/nightly_1128_work'
DEV_PAIRS = json.load(open('/workspace/mixes/protrans/replica/nightly_1125_work/profade_fit/dev27_pairs.json'))
PICKS = os.path.join(W, 'dev27_picks_ridegate.json')
KEEP = os.path.join(W, 'renders')
os.makedirs(KEEP, exist_ok=True)


def _pick_one(args):
    p, idx = args
    os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
    import paths, recreate, glob as G
    os.chdir(paths.SRC2)
    rules = recreate.load_rules()
    rules['HARD_FALLBACK'] = 0
    tag = f'pk28_{idx}'
    try:
        res = recreate.recreate(p['a']['yt'], p['b']['yt'], p['sa'], p['sb'],
                                hint_a_played_sec=p['hint'], rules=rules, tag=tag)
        return p['id'], dict(fam=res['fam'], win=res['win'])
    finally:
        for fp in G.glob(f'/tmp/protrans_bench/{tag}*'):
            try:
                os.remove(fp)
            except Exception:
                pass


def ensure_picks(pairs):
    if os.path.exists(PICKS):
        return json.load(open(PICKS))
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=int(os.environ.get('PFW', 3))) as ex:
        res = dict(ex.map(_pick_one, [(p, i) for i, p in enumerate(pairs)]))
    json.dump(res, open(PICKS, 'w'), indent=1)
    print(f'Cached {len(res)} ridegate picks in {time.time()-t0:.1f}s', flush=True)
    return res


def _eval_one(args):
    p, pick_info, env_delta, tag, idx = args
    os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
    import paths, recreate, score, score_v2 as S2, hardcheck as HC, blend_diag as BD, blend_bench as BB, lows_hole as LH
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
        s0, A, B = BD.crop_decks(M, 0)
        n = int(round(len(A) / BS))
        s, e = max(0, int(float(t['start_bar']) - s0)), min(n, int(float(t['end_bar']) - s0))
        hole = LH.measure_sumlo(A, B, n, BS, s, e)
        bass = None
        try:
            bass = ((v1.get('breakdown') or {}).get('stems') or {}).get('bass')
        except Exception:
            bass = None
        wait = t.get('bass_wait')
        out = dict(id=p['id'], v1=float(v1['score']), v2=float(v2['official_v2']),
                   bass_stem=None if bass is None else float(bass),
                   hc=dict(hard_fail=bool(hc.get('hard_fail')), beat_clash=bool(hc.get('beat_clash')),
                           bass_hole=bool(hc.get('bass_hole')), pumping=bool(hc.get('pumping')),
                           pump_db=hc.get('pump_db'), lows_dip_db=hc.get('lows_dip_db')),
                   lows_hole=hole['lows_hole'], lows_hole_flag=bool(hole['lows_hole_flag']),
                   bass_wait=wait, se=[float(t['start_bar']), float(t['end_bar'])],
                   ours=ours, meta=meta, fam=pick_info.get('fam'))
        # keep a copy of flagged (or waited) audio for ear checks
        if hole['lows_hole_flag'] or wait or hc.get('hard_fail'):
            for src, ext in ((ours, '.mp3'), (meta, '_meta.json')):
                dest = os.path.join(KEEP, os.path.basename(src))
                try:
                    shutil.copy2(src, dest)
                    if ext == '.mp3':
                        out['kept'] = dest
                except Exception:
                    pass
    except Exception as ex:
        out = dict(id=p['id'], error=f'{type(ex).__name__}: {ex}'[-300:])
    return out


def run_arm(name, env_delta, pairs, picks):
    t0 = time.time()
    tasks = [(p, picks[p['id']], env_delta, f'n28{name[:6]}', i) for i, p in enumerate(pairs) if p['id'] in picks]
    with ProcessPoolExecutor(max_workers=int(os.environ.get('PFW', 3))) as ex:
        rows = list(ex.map(_eval_one, tasks))
    ok = [r for r in rows if 'error' not in r]
    def m(xs):
        return None if not xs else round(float(np.mean(xs)), 2)
    summ = dict(
        name=name, n=len(ok), err=len(rows) - len(ok), sec=round(time.time() - t0, 1),
        v1=m([r['v1'] for r in ok]), v2=m([r['v2'] for r in ok]),
        bass_stem=m([r['bass_stem'] for r in ok if r.get('bass_stem') is not None]),
        hf=sum(1 for r in ok if r['hc']['hard_fail']),
        clash=sum(1 for r in ok if r['hc']['beat_clash']),
        hole=sum(1 for r in ok if r['hc']['bass_hole']),
        pump=sum(1 for r in ok if r['hc']['pumping']),
        lows_hole_flags=sum(1 for r in ok if r.get('lows_hole_flag')),
        lows_hole_mean=m([r['lows_hole'] for r in ok]),
        n_waited=sum(1 for r in ok if (r.get('bass_wait') or {}).get('delayed')),
        hole_ids=[r['id'] for r in ok if r.get('lows_hole_flag')],
        hf_ids=[r['id'] for r in ok if r['hc']['hard_fail']],
    )
    print('RESULT', json.dumps(summ), flush=True)
    json.dump(dict(summary=summ, env=env_delta, rows=rows),
              open(os.path.join(W, f'measure_{name}.json'), 'w'), indent=1, default=str)
    return summ, rows


def main():
    pairs = DEV_PAIRS
    picks = ensure_picks(pairs)
    print('picks', len(picks), 'pairs', len(pairs), flush=True)
    base, _ = run_arm('base', {}, pairs, picks)
    arm, _ = run_arm('bass_wait', {'BASS_WAIT': 1}, pairs, picks)
    print('DONE', json.dumps(dict(base=base, bass_wait=arm)), flush=True)

if __name__ == '__main__':
    main()
