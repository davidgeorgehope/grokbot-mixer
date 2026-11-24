"""Score the exact clips the listener rated (v1 vs official_v2) against the pro clip of the same pair."""
import os, sys, json
PT = '/workspace/mixes/protrans'; sys.path.insert(0, PT)
import st_pin; os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
import paths, score_v2 as S2, run_admitted_tune as T
DL = '/workspace/mixes/deliver/protrans'
ITEMS = [  # (pair, clip the listener heard as "ours", his 1-5 rating, source of the rating in log.jsonl)
    ('joe_syntax_hospital__01', 'daily_2026-11-10_A.mp3', 4.0, '11-10 daily'),
    ('joe_syntax_hospital__08', 'daily_2026-11-11_A.mp3', 2.0, '11-11 daily'),
    ('hybrid_minds_ukf__09', 'ab2_2026-11-20_hm09_A.mp3', 2.5, '11-20 ab2 default'),
    ('hybrid_minds_ukf__09', 'ab2_2026-11-20_hm09_B.mp3', 3.5, '11-20 ab2 breakdown_exit'),
    ('hybrid_minds_ukf__09', 'rca_2026-11-20_hm09_fixed.mp3', 4.0, '11-20 15:44 "more like a 4"'),
    ('pola_bryson_puzzlewood__04', 'diagnostics/rca_2026-11-20_pola04_land_160_40_16.mp3', 4.0, '11-20 16:54'),
    ('joe_syntax_hospital__13', 'daily_2026-11-23_B.mp3', 2.0, '11-23 daily'),
    ('hybrid_minds_ukf__10', 'daily_2026-11-24_B.mp3', 4.0, '11-24 daily'),
]
recs = {r['id']: r for r in T.load_recs()}
rows = []
for pid, clip, rating, src in ITEMS:
    rec = recs[pid]; p = os.path.join(DL, clip)
    if not os.path.exists(p): print('missing', p); continue
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    r = S2.score_v2(rec['pro_clip'], p, sa, sb)
    row = dict(pair=pid, clip=clip, rating=rating, src=src, v1=r['score'], v2=r['official_v2'], v1_breakdown={k: r['breakdown'][k] for k in ('stem_curves','deck_curves','beat_align','bass_swap','outgoing_cut','blend_length')}, place=r['placement']['parts'],
               ours_events={k: r['placement']['ours'].get(k) for k in ('entry', 'gone', 'swap')}, pro_events={k: r['placement']['pro'].get(k) for k in ('entry', 'gone', 'swap')})
    rows.append(row); print(json.dumps(row), flush=True)
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ratings.json'), 'w'), indent=1)
