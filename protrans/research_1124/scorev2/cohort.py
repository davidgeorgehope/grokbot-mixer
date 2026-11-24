"""official_v2 validation: render the 33 admitted pairs under rules.json (base) and the two rejected 11-24 daily arms,
score each render with v1 and official_v2. Pinned st grids, HARD_FALLBACK off (like1124). Resumable jsonl per arm.
Does not write rules.json or any default."""
import os, sys, json, shutil, traceback
os.environ['HARD_FALLBACK'] = '0'
os.environ.pop('HARDCHECK_TEST_FORCE_WIN', None); os.environ.pop('PICKER_STYLE_GATED', None)
HERE = os.path.dirname(os.path.abspath(__file__)); PT = os.path.abspath(os.path.join(HERE, '..', '..')); sys.path.insert(0, PT)
import st_pin; os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
import paths, score, score_v2 as S2, run_admitted_tune as T
ARMS = [('base', {}), ('replica_x16', {'REPLICA': 1, 'REPLICA_X': 16}), ('dropcand_exit', {'DROPCAND': 'exit'})]

def work(p):
    arm, delta, i, rec = p
    os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
    import recreate
    rules = json.load(open(paths.RULES)); rules.update(delta)
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    try:
        info = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb, hint_a_played_sec=rec['window'].get('hint_a_played_sec'), rules=rules, tag=f'sv2{arm[:3]}{i}')
        dst = os.path.join(HERE, 'renders', arm, rec['id'] + '.mp3'); os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy(info['ours'], dst)
        v1 = score.score(rec['pro_clip'], dst, src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
        r = S2.score_v2(rec['pro_clip'], dst, sa, sb, v1=v1)
        return dict(id=rec['id'], split=rec['split'], dj=rec['dj'], arm=arm, fam=info['fam'], win=info['win'], v1=v1['score'],
                    v1_breakdown={k: v1['breakdown'][k] for k in ('stem_curves','deck_curves','beat_align','bass_swap','outgoing_cut','blend_length')},
                    v2=r['official_v2'], placement=r['placement'], ours=dst)
    except Exception as e:
        return dict(id=rec['id'], split=rec['split'], arm=arm, error=traceback.format_exc()[-600:])

def work_and_write(p):
    import fcntl
    row = work(p)
    ck = os.path.join(HERE, f'cohort_{p[0]}.jsonl')
    with open(ck, 'a') as fh:
        fcntl.flock(fh, fcntl.LOCK_EX); fh.write(json.dumps(row, default=str) + '\n'); fcntl.flock(fh, fcntl.LOCK_UN)
    print(p[0], row['id'], row.get('v1'), row.get('v2'), row.get('error', '')[-200:], flush=True)
    return row['id']

if __name__ == '__main__':
    # 2026-11-24: fork-pool result delivery hung (20 renders done, 0 results returned); spawn workers that write their own rows
    import multiprocessing as mp
    recs = T.load_recs()
    for arm, delta in ARMS:
        ck = os.path.join(HERE, f'cohort_{arm}.jsonl')
        have = {json.loads(l)['id'] for l in open(ck)} if os.path.exists(ck) else set()
        todo = [(arm, delta, i, r) for i, r in enumerate(recs) if r['id'] not in have]
        print(arm, len(have), 'cached', len(todo), 'todo', flush=True)
        with mp.get_context('spawn').Pool(2, maxtasksperchild=4) as pool:
            for _ in pool.imap_unordered(work_and_write, todo): pass
    print('COHORT DONE', flush=True)
