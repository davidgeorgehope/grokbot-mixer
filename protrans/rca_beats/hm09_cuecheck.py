"""Light check (the listener 3:18 PM follow-up): does a cue nearer the pro's (B in at ~52, A out around 136-152) close the gap?
Renders a handful of natural windows with current rules + DRUMCLASH=1; reports pro-match + rendered verdict. No sweep."""
import json, os, sys
sys.path[:0] = ['/workspace/mixes/protrans', '/workspace/mixes/src2', '/workspace/mixes/protrans/rca_beats']
os.environ['BB_SCRATCH'] = '/tmp/protrans_bench'; os.makedirs('/tmp/protrans_bench', exist_ok=True)
import paths, recreate, score as S, cleanup
import run_admitted_tune as T
rec = {r['id']: r for r in T.load_recs()}['hybrid_minds_ukf__09']; a, b = rec['a']['yt'], rec['b']['yt']
rules = json.load(open(paths.RULES)); rules['DRUMCLASH'] = 1; created = []
for x in (a, b): recreate._prep_track(x, os.path.join(paths.LIB, x + '.m4a'), created)
env = recreate.apply_rules(rules); os.environ.update(env); os.chdir(paths.SRC2)
import blend_bench as BB
WINS = [['n', 144, None, 32, 32], ['n', 144, None, 48, 16], ['n', 140, None, 52, 16], ['n', 148, None, 52, 16], ['n', 152, None, 52, 16], ['n', 152, None, 48, 32]]
out = []
for i, w in enumerate(WINS):
    try:
        c = dict(fam='cue', win=w, env=dict(env)); dk, M = BB.render(c, a, b, f'cuechk{i}')
        h = M['trans'][0].get('drumclash') or {}; fin = h.get('after') or h.get('before') or {}
        sc = S.score(rec['pro_clip'], c['mp3'], src_a=os.path.join(paths.LIB, a + '.m4a'), src_b=os.path.join(paths.LIB, b + '.m4a'), use_demucs=False, cache=paths.CACHE)
        r = dict(win=w, pro_match=sc['score'], level=h.get('level'), kind=h.get('kind'), lattice=(fin.get('lattice') or {}).get('confidence'), pulse=(fin.get('pulse') or {}).get('confidence'))
    except Exception as e:
        r = dict(win=w, error=f'{type(e).__name__}: {str(e)[-200:]}')
    out.append(r); print('WIN', json.dumps(r, default=str), flush=True)
json.dump(out, open('/workspace/mixes/protrans/rca_beats/hm09_cuecheck.json', 'w'), indent=1, default=str)
cleanup.drop_our_src2(created)
