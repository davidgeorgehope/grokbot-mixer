"""Render-level check of JOINT_PICKER=1 vs the current default on dev-27 (pro clips -> official v1/v2,
hard checks, 90 Hz hole sensor). Base arm reuses nightly_1128_work/measure_base.json (current default,
rendered 11-27 6:27 AM ET, same rules). Writes joint_work/measure_dev27_<tag>.json."""
import json, os, sys, time
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, '/workspace/mixes/protrans'); sys.path.insert(0, '/workspace/mixes/protrans/replica')
import measure_bass_wait_1128 as M
OUT = '/workspace/mixes/protrans/replica/joint_work'


def _pick(args):
    p, idx, delta = args
    import st_pin
    os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
    import paths, recreate, glob as G
    os.chdir(paths.SRC2)
    rules = recreate.load_rules(); rules['HARD_FALLBACK'] = 0; rules.update(delta)
    tag = f'jp27_{idx}'
    try:
        res = recreate.recreate(p['a']['yt'], p['b']['yt'], p['sa'], p['sb'], hint_a_played_sec=p['hint'], rules=rules, tag=tag)
        return p['id'], dict(fam=res['fam'], win=res['win'], rg=(res.get('ridegate') or res.get('ridegate_info')))
    except Exception as ex:
        return p['id'], dict(error=f'{type(ex).__name__}: {ex}'[-200:])
    finally:
        for fp in G.glob(f'/tmp/protrans_bench/{tag}*'):
            try: os.remove(fp)
            except Exception: pass


def _eval_wrap(args):
    p, pick_info, env_delta, tag, idx = args
    os.environ['RIDEGATE_WIN'] = json.dumps(list(pick_info['win']))  # render the window recreate chose (also non-16/32 lengths)
    for k, v in env_delta.items():
        os.environ[k] = str(v)
    return _ORIG(args)


_ORIG = M._eval_one
M._eval_one = _eval_wrap

if __name__ == '__main__':
    tag = sys.argv[1]
    delta = {'JOINT_PICKER': 1} if not os.environ.get('BASE_ARM') else {}
    pairs = M.DEV_PAIRS
    if os.environ.get('ONLY_N'):
        pairs = pairs[:int(os.environ['ONLY_N'])]
    with ProcessPoolExecutor(int(os.environ.get('PFW', 3))) as ex:
        picks = dict(ex.map(_pick, [(p, i, delta) for i, p in enumerate(pairs)]))
    ok = {k: v for k, v in picks.items() if 'error' not in v}
    print('picks', len(ok), 'errors', {k: v['error'] for k, v in picks.items() if 'error' in v}, flush=True)
    M.W = OUT
    summ, rows = M.run_arm(f'joint_{tag}', delta, [p for p in pairs if p['id'] in ok], ok)
    json.dump(dict(picks=picks, summary=summ, rows=rows), open(os.path.join(OUT, f'measure_dev27_{tag}.json'), 'w'), indent=1, default=str)
