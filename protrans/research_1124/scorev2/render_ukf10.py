"""Re-render the ukf__10 candidates (default, replica_on, replica_x16, dropcand_exit) for score decomposition."""
import os, sys, json, shutil
os.environ['HARD_FALLBACK'] = '0'
HERE = os.path.dirname(os.path.abspath(__file__)); PT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, PT)
import st_pin
os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
import paths, recreate, score
import run_admitted_tune as T
rec = {r['id']: r for r in T.load_recs()}['hybrid_minds_ukf__10']
rules = json.load(open(paths.RULES))
ARMS = [('default', {}), ('replica_on', {'REPLICA': 1}), ('replica_x16', {'REPLICA': 1, 'REPLICA_X': 16}), ('dropcand_exit', {'DROPCAND': 'exit'})]
out = {}
for name, d in ARMS:
    r = dict(rules); r.update(d)
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    info = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb, hint_a_played_sec=rec['window'].get('hint_a_played_sec'), rules=r, tag=f'sv2u{name[:5]}')
    dst = os.path.join(HERE, 'renders', f'ukf10_{name}.mp3'); shutil.copy(info['ours'], dst)
    if info.get('meta_path'): shutil.copy(info['meta_path'], os.path.join(HERE, 'renders', f'ukf10_{name}_meta.json'))
    sc = score.score(rec['pro_clip'], dst, src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
    out[name] = dict(win=info['win'], fam=info['fam'], score=sc['score'], breakdown={k: sc['breakdown'][k] for k in ('stem_curves','deck_curves','beat_align','bass_swap','outgoing_cut','blend_length','events_pro','events_ours','align')})
    print(name, info['fam'], info['win'], sc['score'], flush=True)
json.dump(out, open(os.path.join(HERE, 'ukf10_rerender.json'), 'w'), indent=1)
