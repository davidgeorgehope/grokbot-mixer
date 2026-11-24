import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); PT = os.path.abspath(os.path.join(HERE, '..', '..')); sys.path.insert(0, PT)
import st_pin; os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
import paths, score_v2 as S2, run_admitted_tune as T
rec = {r['id']: r for r in T.load_recs()}['hybrid_minds_ukf__10']
sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
D = json.load(open(os.path.join(HERE, 'decomp_ukf10.json')))
ev = S2.placement_events(rec['pro_clip'], rec['a']['yt'], rec['b']['yt']); print('pro', json.dumps(ev))
for n in ('default', 'replica_on', 'replica_x16', 'dropcand_exit'):
    r = S2.score_v2(rec['pro_clip'], os.path.join(HERE, 'renders', f'ukf10_{n}.mp3'), sa, sb, v1=D[n]['free'])
    print(n, 'v1', r['score'], 'v2', r['official_v2'], r['placement']['parts'], json.dumps({k: r['placement']['ours'].get(k) for k in ('entry','gone','swap','clip_bars')}))
