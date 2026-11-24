import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); PT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, PT); sys.path.insert(0, os.path.join(PT, 'replica'))
import st_pin; os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
import extract_protrans as X, run_admitted_tune as T, score
rec = {r['id']: r for r in T.load_recs()}['hybrid_minds_ukf__10']
K = ('in_entry_clip_bar','out_gone_clip_bar','bass_swap_clip_bar','in_bar_at_entry','out_bar_at_entry','out_bar_at_gone','in_bar_at_swap','overlap_bars')
for n in ('pro','default','replica_on','replica_x16','dropcand_exit'):
    r = dict(rec)
    if n != 'pro': r['pro_clip'] = os.path.join(HERE, 'renders', f'ukf10_{n}.mp3')
    d = X.run_one(r)
    dur = len(score._load(r['pro_clip']))/score.SR
    print(n, round(dur,1), {k: d.get(k) for k in K}, d.get('error'), flush=True)
