"""Round 6 (2026-11-26): dev-27 rerun of base / fit2 / ex35 WITH early exit + ee_r7 flags + TAIL_EXIT,
and PRO_FADE_RESPECT_EXIT=1 (the path we ship). Own picks cache so r4/r5 dev27_picks.json is untouched.
Arm names are distinct (r6_ee_*), rows append to the same rows.jsonl.
The ee_r7 picker map only covers the official 33; on these 27 pairs it is a no-op inject and
EARLY_EXIT still reshapes eligible blends (drop-1 in the window). Picks are remade with the flags on
so recreate can choose an early-exit candidate when mix_simple offers one.
"""
import os, sys, glob
sys.path.insert(0, '/workspace/mixes/protrans/replica')
import pro_fade_fit as F
import st_pin

F.PICKS_CACHE = '/workspace/mixes/protrans/replica/nightly_1125_work/profade_fit/dev27_picks_ee_r7.json'
MAP = '/workspace/mixes/protrans/replica/picker_early_exit_r7_windows.json'
EE = {
    'EARLY_EXIT': 1,
    'PICKER_STYLE_GATED': 1,
    'PICKER_STYLE_GATED_MAP': MAP,
    'PICKER_INJECT_CS': 1,
    'TAIL_EXIT': 6,
    'PRO_FADE_RESPECT_EXIT': 1,
}
FIT2 = {
    'PRO_FADE': 1, 'PRO_FADE_ENTRY_DB': -8.5, 'PRO_FADE_SHELF_DB': -10.0,
    'PRO_FADE_EXIT_SLOPE': 2.5, 'PRO_FADE_HIGH_OFS': 7.0, 'PRO_FADE_BASS_CUT_DB': -24.0,
}


def c(**k):
    d = dict(EE)
    d.update(FIT2)
    d.update(k)
    return d


def _pick_one(args):
    p, idx = args
    os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
    os.environ['PRO_FADE_RESPECT_EXIT'] = '1'
    import paths, recreate
    os.chdir(paths.SRC2)
    rules = recreate.load_rules()
    rules['HARD_FALLBACK'] = 0
    rules.update(EE)
    tag = f'pk27ee_{idx}'
    try:
        res = recreate.recreate(p['a']['yt'], p['b']['yt'], p['sa'], p['sb'],
                                hint_a_played_sec=p['hint'], rules=rules, tag=tag)
        return p['id'], dict(fam=res['fam'], win=res['win'])
    finally:
        for fp in glob.glob(f'/tmp/protrans_bench/{tag}*'):
            try:
                os.remove(fp)
            except Exception:
                pass


F._pick_one = _pick_one

if __name__ == '__main__':
    os.environ['PRO_FADE_RESPECT_EXIT'] = '1'
    F.run_grid([
        ('r6_ee_base', dict(EE)),
        ('r6_ee_fit2', c()),
        ('r6_ee_ex35', c(PRO_FADE_EXIT_SLOPE=3.5)),
    ])
    print('DONE_R6', flush=True)
