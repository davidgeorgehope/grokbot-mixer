#!/usr/bin/env python3
"""Blind A/B clips for DROP_SWAP (2026-11-18 research): same pair, current default vs DROP_SWAP=1.
Same snippet convention as the daily clips (8 bars pre-roll, blend, 8 after; short tick at the blend start),
-14 LUFS, blend_diag PNG per side. A/B order is random; the key goes to /workspace/private only.
Usage: python3 protrans/render_dropswap_clips.py <pair_id> [<pair_id> ...]"""
import copy, json, os, random, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import paths, render_planner_clips as RP
import run_admitted_tune as T

DAY = '2026-11-18'
OUT = '/workspace/mixes/deliver/research/' + DAY
KEY = f'/workspace/private/research_{DAY}_dropswap_key.json'


def main(pids):
    os.makedirs(OUT, exist_ok=True); RP.OUT_DIR = OUT; RP.DIAG_DIR = OUT
    sys.path.insert(0, paths.SRC2); import blend_diag as BD
    _fig = BD.figure
    def _blind(M, i, png, title, **kw):  # PNG title without window/family (would reveal the variant)
        return _fig(M, i, png, os.path.basename(png).rsplit('.', 1)[0], **kw)
    BD.figure = _blind
    recs = {r['id']: r for r in T.load_recs()}
    rules = json.load(open(paths.RULES)); assert not rules.get('DROP_SWAP')
    trial = copy.deepcopy(rules); trial['DROP_SWAP'] = 1
    key = json.load(open(KEY)) if os.path.exists(KEY) else {}
    rng = random.SystemRandom()
    for n, pid in enumerate(pids, 1):
        flip = rng.random() < 0.5
        sides = {'A': ('dropswap', trial), 'B': ('default', rules)} if flip else {'A': ('default', rules), 'B': ('dropswap', trial)}
        k = {}
        for ab, (name, rr) in sides.items():
            stem = f'dropswap_{DAY}_pair{n}_{ab}'
            meta = RP.render_one(recs[pid], rr, f'dsclip{n}{ab}', stem_name=stem)
            k[ab] = dict(variant=name, win=meta['win'], fam=meta['fam'], bass_swap=meta['bass_swap'], mp3=meta['mp3'], png=meta['png'])
            # strip variant-revealing fields from the public sidecar json
            pub = {kk: vv for kk, vv in meta.items() if kk not in ('env', 'win', 'fam', 'start_bar', 'end_bar', 'bass_swap', 'src', 'planner')}
            json.dump(pub, open(os.path.join(OUT, stem + '.json'), 'w'), indent=2, default=str)
            for f in (os.path.join(OUT, stem + '.wav'),):
                if os.path.exists(f): os.remove(f)
            print('CLIP', ab, meta['mp3'], meta['png'], meta['tick_timestamp'], meta['duration_s'], meta.get('lufs'), flush=True)
        key[f'pair{n}'] = dict(pick=pid, pair=recs[pid]['pair'], **k)
    os.makedirs(os.path.dirname(KEY), exist_ok=True)
    json.dump(key, open(KEY, 'w'), indent=2, default=str)
    print('KEY', KEY)


if __name__ == '__main__':
    main(sys.argv[1:])
