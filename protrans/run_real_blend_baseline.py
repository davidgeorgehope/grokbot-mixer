"""Fresh baseline on the real-blend cohort; no rules or weights changed."""
import glob
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import paths, recreate, score, cleanup
import run_admitted_tune as T


def worker(rec):
    info = None
    tag = 'realblend_' + rec['id']
    try:
        sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
        sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
        info = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                                 hint_a_played_sec=rec['window']['hint_a_played_sec'],
                                 rules=recreate.load_rules(), tag=tag)
        sc = score.score(rec['pro_clip'], info['ours'], sa, sb, use_demucs=False)
        return dict(id=rec['id'], split=rec['split'], dj=rec['dj'], pair=rec['pair'], score=sc)
    finally:
        if info:
            cleanup.drop_our_src2(info.get('created') or [])
        for p in glob.glob('/tmp/protrans_bench/' + tag + '*'):
            if os.path.isfile(p): os.remove(p)


if __name__ == '__main__':
    recs = T.load_recs()
    rows = []
    with ProcessPoolExecutor(max_workers=3) as ex:
        for f in as_completed([ex.submit(worker, r) for r in recs]):
            row = f.result()  # fail the job rather than average over survivors
            rows.append(row)
            print(row['id'], row['score']['score'], flush=True)
    result = dict(summary=T.summarize(rows), rows=T.slim(rows),
                  rules=recreate.load_rules(), scorer_version=score.SCORER_VERSION,
                  note='Fresh renders and scores; real-blend-filtered cohort. Rules and score weights unchanged.')
    json.dump(result, open(os.path.join(paths.RESULTS, 'baseline_real_blend.json'), 'w'), indent=2)
    print(json.dumps(result['summary']), flush=True)
