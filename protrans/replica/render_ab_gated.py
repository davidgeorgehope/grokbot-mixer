#!/usr/bin/env python3
"""Blind A/B (FYI, not a decision step): REPLICA=gated (pro-replication window) vs current default, on pairs the listener has rated.
Same clip convention as daily clips; key to /workspace/private only. Defaults untouched (flag in a rules copy).
usage: python3 protrans/replica/render_ab.py <tag> <pair_id> [...]"""
import copy, json, os, random, sys
P = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, P)
import paths, render_planner_clips as RP, score
import run_admitted_tune as T
DAY = '2026-11-18'

def main(tag, pids):
    OUT = f'/workspace/mixes/deliver/research/{DAY}/replica_{tag}'; KEY = f'/workspace/private/research_{DAY}_replica_{tag}_key.json'
    os.makedirs(OUT, exist_ok=True); RP.OUT_DIR = OUT; RP.DIAG_DIR = OUT
    sys.path.insert(0, paths.SRC2); import blend_diag as BD
    _fig = BD.figure
    BD.figure = lambda M, i, png, title, **kw: _fig(M, i, png, os.path.basename(png).rsplit('.', 1)[0], **kw)
    recs = {r['id']: r for r in T.load_recs()}
    rules = json.load(open(paths.RULES)); assert not rules.get('REPLICA')
    trial = copy.deepcopy(rules); trial['REPLICA'] = 'gated'
    key = {}; rng = random.SystemRandom()
    for n, pid in enumerate(pids, 1):
        rec = recs[pid]; sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
        sides = [('replica_gated', trial), ('default', rules)]
        if rng.random() < 0.5: sides.reverse()
        k = {}
        for ab, (name, rr) in zip('AB', sides):
            stem = f'replica_{DAY}_{tag}_pair{n}_{ab}'
            meta = RP.render_one(rec, rr, f'rp{tag}{n}{ab}', stem_name=stem)
            sc = score.score(rec['pro_clip'], meta['mp3'], src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
            k[ab] = dict(variant=name, win=meta['win'], fam=meta['fam'], mp3=meta['mp3'], png=meta['png'], score=sc['score'],
                         parts={kk: sc['breakdown'][kk] for kk in ('stem_curves','deck_curves','beat_align','bass_swap','outgoing_cut','blend_length')})
            pub = {kk: vv for kk, vv in meta.items() if kk not in ('env', 'win', 'fam', 'start_bar', 'end_bar', 'bass_swap', 'src', 'planner')}
            json.dump(pub, open(os.path.join(OUT, stem + '.json'), 'w'), indent=2, default=str)
            w = os.path.join(OUT, stem + '.wav')
            if os.path.exists(w): os.remove(w)
            print('CLIP', pid, ab, name, meta['fam'], meta['win'], sc['score'], meta['mp3'], flush=True)
        key[f'pair{n}'] = dict(pick=pid, pair=rec['pair'], **k)
        json.dump(key, open(KEY, 'w'), indent=2, default=str)
    print('KEY', KEY)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
