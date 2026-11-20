#!/usr/bin/env python3
"""Blind A/B for joe_syntax_hospital__12 (Ghetto Blaster -> Seconds To Midnight):
current default vs SLOWPAIR exit-only. Requested even though the 33-pair exit-only
arm lost on held-out. Key goes only to /workspace/private/.
Usage: python3 protrans/render_spex_js12_clips.py
"""
import copy, json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import paths, render_planner_clips as RP
import run_admitted_tune as T

DAY = '2026-11-20'
PID = 'joe_syntax_hospital__12'
OUT = paths.DELIVER  # already deliver/protrans
KEY = f'/workspace/private/research_{DAY}_spex_js12_key.json'
# Pro blend start in the set is 34:52; put that in the public stem so both sides share it.
STEM = f'spex_{DAY}_js12_3452'


def main():
    os.makedirs(OUT, exist_ok=True)
    RP.OUT_DIR = OUT
    RP.DIAG_DIR = OUT
    sys.path.insert(0, paths.SRC2)
    import blend_diag as BD
    _fig = BD.figure
    def _blind(M, i, png, title, **kw):
        return _fig(M, i, png, os.path.basename(png).rsplit('.', 1)[0], **kw)
    BD.figure = _blind
    recs = {r['id']: r for r in T.load_recs()}
    rec = recs[PID]
    rules = json.load(open(paths.RULES))
    assert 'SLOWPAIR' not in rules and 'SLOWPAIR_EXIT' not in rules
    trial = copy.deepcopy(rules)
    trial['SLOWPAIR'] = 1
    trial['SLOWPAIR_EXIT'] = 1
    rng = random.SystemRandom()
    flip = rng.random() < 0.5
    sides = {'A': ('exit_only', trial), 'B': ('default', rules)} if flip else {'A': ('default', rules), 'B': ('exit_only', trial)}
    key = dict(pick=PID, pair=rec['pair'], day=DAY)
    for ab, (name, rr) in sides.items():
        stem = f'{STEM}_{ab}'
        meta = RP.render_one(rec, rr, f'js12{ab}', stem_name=stem)
        key[ab] = dict(variant=name, win=meta['win'], fam=meta['fam'],
                       bass_swap=meta.get('bass_swap'), mp3=meta['mp3'], png=meta['png'])
        pub = {kk: vv for kk, vv in meta.items() if kk not in ('env', 'win', 'fam', 'start_bar', 'end_bar', 'bass_swap', 'src', 'planner')}
        json.dump(pub, open(os.path.join(OUT, stem + '.json'), 'w'), indent=2, default=str)
        wav = os.path.join(OUT, stem + '.wav')
        if os.path.exists(wav):
            os.remove(wav)
        print('CLIP', ab, meta['mp3'], meta['png'], meta.get('tick_timestamp'), meta.get('duration_s'), meta.get('lufs'), flush=True)
    # placement comparison + PNG (pro vs default vs exit-only)
    try:
        import provsours as PV
        def_win = key['A']['win'] if key['A']['variant'] == 'default' else key['B']['win']
        arm_win = key['A']['win'] if key['A']['variant'] == 'exit_only' else key['B']['win']
        PV.make(PID, f'{STEM}_place', {'default': def_win, 'exit_only': arm_win}, OUT)
        print('PROVSOURS', os.path.join(OUT, f'{STEM}_place_provsours.md'), flush=True)
    except Exception as ex:
        print('PROVSOURS_FAIL', type(ex).__name__, ex, flush=True)
    os.makedirs(os.path.dirname(KEY), exist_ok=True)
    json.dump(key, open(KEY, 'w'), indent=2, default=str)
    print('KEY', KEY, flush=True)
    BD.figure = _fig
    # confirm rules unchanged
    rules2 = json.load(open(paths.RULES))
    assert 'SLOWPAIR' not in rules2 and 'SLOWPAIR_EXIT' not in rules2


if __name__ == '__main__':
    main()
