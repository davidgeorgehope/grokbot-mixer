#!/usr/bin/env python3
"""Pinned-33 check for PRO_FADE (learned pro fade shape) on top of base and ee_r7.

usage: pro_fade_pinned.py <params.json> [tag]
Arms rendered (resumable jsonl in nightly_1125_work/):
  pinned_pf_base_<tag>.jsonl   : base rules + PRO_FADE on all 33 pairs
  pinned_pf_ee_r7_<tag>.jsonl  : ee_r7 map (+EARLY_EXIT) + PRO_FADE on the 15 pairs ee_r7 renders
ee_r7+fade = pf_ee_r7 where ee_r7 rendered, else pf_base (same abstain rule as the ee_r7 eval).
Compares against pinned_base_hc.jsonl and picker_1125_ee_r7_pinned.json. Higher v1/v2 = better.
Never writes rules.json or defaults.
"""
import json, os, sys, collections, multiprocessing as mp
import numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P0 = os.path.dirname(H)
W = os.path.join(H, 'nightly_1125_work')
R7_MAP = os.path.join(H, 'picker_early_exit_r7_windows.json')
sys.path.insert(0, H); sys.path.insert(0, P0)


def _worker(payload):
    arm, map_path, i, rec, pf = payload
    os.environ['HARD_FALLBACK'] = '0'
    os.environ.pop('HARDCHECK_TEST_FORCE_WIN', None)
    os.environ.setdefault('PROTRANS_SRC2', '/workspace/mixes/src2_pin_n1121')
    src2 = os.environ['PROTRANS_SRC2']; os.chdir(src2)
    for k in ('PICKER_STYLE_GATED', 'PICKER_STYLE_GATED_MAP', 'PICKER_INJECT_CS', 'EARLY_EXIT'):
        os.environ.pop(k, None)
    import paths, recreate, score, score_v2 as S2, hardcheck as HC, shutil
    rules = json.load(open(paths.RULES))
    if map_path:
        os.environ.update(PICKER_STYLE_GATED='1', PICKER_STYLE_GATED_MAP=map_path, PICKER_INJECT_CS='1', EARLY_EXIT='1')
        rules.update(PICKER_STYLE_GATED=1, PICKER_INJECT_CS=1, EARLY_EXIT=1, PICKER_STYLE_GATED_MAP=map_path)
    rules.update(pf)
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    try:
        info = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                                 hint_a_played_sec=rec['window'].get('hint_a_played_sec'), rules=rules, tag=f'pf_{arm[-6:]}{i}')
        d = os.path.join(W, 'pinned_renders', arm); os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, rec['id'] + '.mp3'); shutil.copy(info['ours'], dst)
        v1 = score.score(rec['pro_clip'], dst, src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
        r2 = S2.score_v2(rec['pro_clip'], dst, sa, sb, v1=v1)
        hc = HC.check(info['meta_path']) if info.get('meta_path') else None
        ee = None
        if info.get('meta_path'):
            M = json.load(open(info['meta_path'])); shutil.copy(info['meta_path'], dst[:-4] + '_meta.json')
            t = M['trans'][0]; ee = bool(t.get('early_exit')); pfi = bool(t.get('pro_fade'))
        return dict(id=rec['id'], split=rec['split'], arm=arm, fam=info['fam'], win=info['win'], v1=v1['score'],
                    v2=r2['official_v2'], placement=r2['placement'], hardcheck=hc, early_exit=ee, pro_fade_on=pfi,
                    picker_info=info.get('picker'), ours=dst)
    except Exception:
        import traceback
        return dict(id=rec['id'], split=rec['split'], arm=arm, error=traceback.format_exc()[-600:])


def _run(arm, map_path, recs, pf, only=None):
    ck = os.path.join(W, f'pinned_{arm}.jsonl'); have = {}
    if os.path.exists(ck):
        for l in open(ck):
            r = json.loads(l)
            if not r.get('error'): have[r['id']] = r
    todo = [(arm, map_path, i, r, pf) for i, r in enumerate(recs) if r['id'] not in have and (only is None or r['id'] in only)]
    if todo:
        with mp.get_context('spawn').Pool(int(os.environ.get('PINW', 4)), maxtasksperchild=4) as pool:
            for row in pool.imap_unordered(_worker, todo):
                with open(ck, 'a') as fh: fh.write(json.dumps(row, default=str) + '\n')
                print(arm, row['id'], 'v1=', row.get('v1'), 'v2=', row.get('v2'), 'hf=', (row.get('hardcheck') or {}).get('hard_fail'),
                      'ee=', row.get('early_exit'), row.get('error', '')[-200:], flush=True)
                if not row.get('error'): have[row['id']] = row
    return have


def summarize(rows):
    out = {}
    for sp in ('train', 'test', 'all'):
        rs = [r for r in rows if sp == 'all' or r['split'] == sp]
        out[f'v1_{sp}'] = round(float(np.mean([r['v1'] for r in rs])), 2)
        out[f'v2_{sp}'] = round(float(np.mean([r['v2'] for r in rs])), 2)
    hc = [r.get('hardcheck') or {} for r in rows]
    out['hard_fails'] = sum(bool(h.get('hard_fail')) for h in hc)
    for k in ('beat_clash', 'bass_hole', 'pumping', 'incoming_vanish'):
        out[k] = sum(bool(h.get(k)) for h in hc)
    out['n'] = len(rows)
    return out


def main():
    pf = json.load(open(sys.argv[1])); tag = sys.argv[2] if len(sys.argv) > 2 else 'v1'
    import st_pin
    os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
    import run_admitted_tune as T
    recs = T.load_recs()
    base = {json.loads(l)['id']: json.loads(l) for l in open(os.path.join(W, 'pinned_base_hc.jsonl')) if l.strip()}
    r7 = {r['id']: r for r in json.load(open(os.path.join(H, 'picker_1125_ee_r7_pinned.json')))['ee_r7_rows']}
    r7_rendered = {i for i, r in r7.items() if not r.get('abstained_to_base')}
    pf_base = _run(f'pf_base_{tag}', None, recs, pf)
    pf_r7 = _run(f'pf_ee_r7_{tag}', R7_MAP, recs, pf, only=r7_rendered)
    ids = [r['id'] for r in recs]
    combo = [pf_r7[i] if i in pf_r7 else pf_base[i] for i in ids]
    def ee_fires(rows): return sum(1 for r in rows if r.get('early_exit') or (r.get('picker_info') or {}).get('applied') and r.get('fam') == 'picker_style_gated')
    res = dict(params=pf, tag=tag,
               base=summarize([base[i] for i in ids]),
               ee_r7=summarize([r7[i] for i in ids]),
               base_fade=summarize([pf_base[i] for i in ids]),
               ee_r7_fade=summarize(combo),
               fires=dict(ee_r7=sum(1 for i in ids if r7[i].get('fam') == 'picker_style_gated'),
                          ee_r7_fade=sum(1 for r in combo if r.get('fam') == 'picker_style_gated'),
                          ee_r7_fade_early_exit_meta=sum(1 for r in combo if r.get('early_exit')),
                          pro_fade_applied=sum(1 for r in combo if r.get('pro_fade_on'))),
               per_pair=[dict(id=i, split=base[i]['split'], base_v2=base[i]['v2'], ee_r7_v2=r7[i]['v2'], ee_r7_fade_v2=c['v2'],
                              base_hf=(base[i].get('hardcheck') or {}).get('hard_fail'), ee_r7_hf=(r7[i].get('hardcheck') or {}).get('hard_fail'),
                              ee_r7_fade_hf=(c.get('hardcheck') or {}).get('hard_fail'), ee_r7_fade_pump=(c.get('hardcheck') or {}).get('pump_db'))
                         for i, c in zip(ids, combo)])
    outp = os.path.join(H, f'pro_fade_pinned_{tag}.json'); json.dump(res, open(outp, 'w'), indent=1)
    print('PF_PINNED', json.dumps({k: v for k, v in res.items() if k != 'per_pair'}), flush=True)


if __name__ == '__main__':
    main()
