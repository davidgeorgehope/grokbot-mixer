import os, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); PT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, PT); sys.path.insert(0, os.path.join(PT, '..', 'src', 'eval'))
import paths, score, version_match as VM, control_curves as CC, run_admitted_tune as T
rec = {r['id']: r for r in T.load_recs()}['hybrid_minds_ukf__10']
srcs = {s: score._load(os.path.join(paths.LIB, rec[s]['yt'] + '.m4a')) for s in 'ab'}
Ft = {s: CC.bandpow(y) for s, y in srcs.items()}
for n in ('pro','default','replica_on','replica_x16','dropcand_exit'):
    p = rec['pro_clip'] if n == 'pro' else os.path.join(HERE, 'renders', f'ukf10_{n}.mp3')
    y = score._load(p); Fm = CC.bandpow(y)
    out = []
    for s in 'ab':
        h, _ = CC.locate(Fm, Ft[s], chunk_s=6.0, hop_s=2.0)
        line = score._fit_chunks(h)
        single = VM.locate_in(y, srcs[s])
        # track bar at clip t=0
        tb0 = None if not line else round((0 - line['a']) / line['s'] / score.BAR_SEC, 1)
        tb0s = round((single['track_t'] - single['mix_t']) / score.BAR_SEC, 1)
        out.append(f"{s}: line tb0={tb0} n={line and line['n']} s={line and round(line['s'],3)} | single tb0={tb0s} z={single['z']}")
    print(n, ' || '.join(out))
