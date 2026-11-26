#!/usr/bin/env python3
"""Blind A/B on pola02: ee_r7 (the listener's blind winner, win n/144/24/32) vs ee_r7 + PRO_FADE.
usage: pro_fade_ab_pola02.py <params.json> <out_dir_name>
Renders both, hard-checks both, writes A.mp3/B.mp3 + diag PNGs in nightly_1125_work/<out_dir_name>/,
answer key ONLY in /workspace/private/<out_dir_name>_key.json. Refuses to write A/B if the fade version fails a hard check.
"""
import json, os, sys, random, shutil, multiprocessing as mp
H = os.path.dirname(os.path.abspath(__file__)); P0 = os.path.dirname(H); W = os.path.join(H, 'nightly_1125_work')
sys.path.insert(0, H); sys.path.insert(0, P0)
PID = 'pola_bryson_puzzlewood__02'; WIN = ['n', 144, None, 24, 32]
SRC2 = '/workspace/mixes/src2_pin_n1121'


def _render(args):
    tag, rec, pf, map_path, out = args
    os.environ['HARD_FALLBACK'] = '0'; os.environ['PROTRANS_SRC2'] = SRC2
    os.environ.update(EARLY_EXIT='1', PICKER_INJECT_CS='1', PICKER_STYLE_GATED_MAP=map_path)
    os.chdir(SRC2)
    import paths, blend_bench as BB, recreate as R, score, score_v2 as S2, hardcheck as HC
    a, b = rec['a']['yt'], rec['b']['yt']
    sa, sb = os.path.join(paths.LIB, a + '.m4a'), os.path.join(paths.LIB, b + '.m4a')
    R._prep_track(a, sa, []); R._prep_track(b, sb, [])
    rules = R.load_rules(); rules.update(EARLY_EXIT=1, PICKER_INJECT_CS=1); rules.update(pf)
    env = R.apply_rules(rules); env.update(EARLY_EXIT='1', PICKER_INJECT_CS='1', PICKER_STYLE_GATED_MAP=map_path)
    for k, v in pf.items(): env[k] = str(v)
    os.environ.update(env)
    pick = dict(fam=tag, win=list(WIN), env=env)
    _, M = BB.render(pick, a, b, f'pfab_{tag}')
    mp3 = os.path.join(out, f'_{tag}.mp3'); meta = os.path.join(out, f'_{tag}_meta.json')
    shutil.copy(pick['mp3'], mp3); json.dump(M, open(meta, 'w'), default=str)
    v1 = score.score(rec['pro_clip'], mp3, src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
    v2 = S2.score_v2(rec['pro_clip'], mp3, sa, sb, v1=v1)
    hc = HC.check(meta, png=os.path.join(out, f'_{tag}_diag.png'), title='pola02 blend')
    t = M['trans'][0]
    return tag, dict(v1=v1['score'], v2=v2['official_v2'], hc=hc, placement=v2['placement'],
                     early_exit=t.get('early_exit'), pro_fade=(t.get('pro_fade') or {}).get('info'),
                     start_bar=t.get('start_bar'), end_bar=t.get('end_bar'))


def main():
    pf = json.load(open(sys.argv[1])); name = sys.argv[2]
    out = os.path.join(W, name); os.makedirs(out, exist_ok=True)
    import st_pin; os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
    import run_admitted_tune as T
    rec = {r['id']: r for r in T.load_recs()}[PID]
    mpth = os.path.join(out, '_map.json')
    json.dump({'by_yt': {f"{rec['a']['yt']}|{rec['b']['yt']}": WIN}}, open(mpth, 'w'))
    tasks = [('ee_r7', rec, {}, mpth, out), ('ee_r7_profade', rec, pf, mpth, out)]
    with mp.get_context('spawn').Pool(2) as pool:
        res = dict(pool.map(_render, tasks))
    for k, v in res.items():
        print('AB', k, json.dumps({x: v[x] for x in ('v1', 'v2')}), json.dumps({x: v['hc'][x] for x in v['hc'] if x != 'png'}), flush=True)
    if res['ee_r7_profade']['hc']['hard_fail']:
        print('PROFADE_FAILS_HARDCHECK: no A/B written', flush=True)
        json.dump(res, open(os.path.join(out, '_results_nokey.json'), 'w'), default=str, indent=1)
        return 2
    tags = ['ee_r7', 'ee_r7_profade']; random.SystemRandom().shuffle(tags)
    assign = {'A.mp3': tags[0], 'B.mp3': tags[1]}
    for slot, tag in assign.items():
        shutil.move(os.path.join(out, f'_{tag}.mp3'), os.path.join(out, slot))
        shutil.move(os.path.join(out, f'_{tag}_diag.png'), os.path.join(out, slot[0] + '_diag.png'))
        shutil.move(os.path.join(out, f'_{tag}_meta.json'), os.path.join('/workspace/private', f'{name}_{slot[0]}_meta.json'))
    os.remove(mpth)
    key = dict(pair=PID, folder=out, win=WIN, params=pf, assignment=assign, results=res)
    os.makedirs('/workspace/private', exist_ok=True)
    json.dump(key, open(f'/workspace/private/{name}_key.json', 'w'), default=str, indent=1)
    print('AB_WRITTEN', out, 'key in /workspace/private', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
