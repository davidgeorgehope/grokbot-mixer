import sys, json, os, glob
sys.path.insert(0, '/workspace/mixes/protrans/replica')
import pro_fade_fit as F
from concurrent.futures import ProcessPoolExecutor
import numpy as np
IDS = sys.argv[2].split(',')
ED = json.loads(sys.argv[1])
def one(pid):
    os.environ['PROTRANS_SRC2'] = F.st_pin.ensure_shadow()
    import paths, recreate, score, hardcheck as HC0, blend_diag as BD, blend_bench as BB, hardcheck as HC
    from engine import BS
    os.chdir(paths.SRC2); BB.SCR = '/tmp/protrans_bench'; os.makedirs(BB.SCR, exist_ok=True)
    p = [x for x in F.DEV_PAIRS if x['id'] == pid][0]; pk = json.load(open(F.PICKS_CACHE))[pid]
    rules = recreate.load_rules(); rules['HARD_FALLBACK'] = 0; rules.update(ED); env = recreate.apply_rules(rules)
    tag = 'dg_' + pid[-12:]
    dk, M = BB.render(dict(fam=pk['fam'], win=pk['win'], env=env), p['a']['yt'], p['b']['yt'], tag)
    t = M['trans'][0]; s0, A, B = BD.crop_decks(M, 0); n = int(round(len(A) / BS))
    s, e = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0)
    al, alA, alB = BD.band_bar_db(A + B, n, BS), BD.band_bar_db(A, n, BS), BD.band_bar_db(B, n, BS)
    loA, loB = BD.band_bar_db(A, n, BS, 'low', 120), BD.band_bar_db(B, n, BS, 'low', 120); sl = BD.band_bar_db(A + B, n, BS, 'low', 120)
    for fp in glob.glob(f'/tmp/protrans_bench/{tag}*'): os.remove(fp)
    r = lambda v: [round(float(x), 1) for x in v[max(0, s - 2):e + 2]]
    return pid, dict(s=s, e=e, s0=s0, al=r(al), alA=r(alA), alB=r(alB), loA=r(loA), loB=r(loB), l1x=r(sl - np.maximum(loA, loB)), bass_swap=t.get('bass_swap'), swap_w=t.get('swap_w'), pf=(t.get('pro_fade') or {}).get('info'))
with ProcessPoolExecutor(min(4, len(IDS))) as ex:
    for pid, d in ex.map(one, IDS):
        print(pid, json.dumps(d), flush=True)
