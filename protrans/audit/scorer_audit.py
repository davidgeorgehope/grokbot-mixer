"""Read-only scorer audit vs the listener's labels (2026-11-18). Scores delivered 'ours' clips against the pro clip.
Writes protrans/audit/scored_labels.json. Does not touch rules.json."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths, score
import run_admitted_tune as T
D = '/workspace/mixes/deliver/protrans/'
ITEMS = [
 # daily blind tests: (label id, pick, ours clip, rating, guessed pro correctly?)
 dict(id='daily_1109', pick='hybrid_minds_ukf__11', clip=D+'daily_2026-11-09_B.mp3', rating=None, spotted=False, note="couldn't tell; ours 'quite good'"),
 dict(id='daily_1110', pick='joe_syntax_hospital__01', clip=D+'daily_2026-11-10_A.mp3', rating=4, spotted=True),
 dict(id='daily_1111', pick='joe_syntax_hospital__08', clip=D+'daily_2026-11-11_A.mp3', rating=2, spotted=True),
 dict(id='daily_1112', pick='hybrid_minds_ukf__08', clip=D+'daily_2026-11-12_B.mp3', rating=4, spotted=False),
 dict(id='daily_1113', pick='hybrid_minds_ukf__12', clip=D+'daily_2026-11-13_A.mp3', rating=4, spotted=True),
 dict(id='daily_1114', pick='hybrid_minds_ukf__19', clip=D+'daily_2026-11-14_A.mp3', rating=2, spotted=True),
 dict(id='daily_1115', pick='hybrid_minds_ukf__25', clip=D+'daily_2026-11-15_A.mp3', rating=4, spotted=True),
 dict(id='daily_1116', pick='hybrid_minds_ukf__45', clip=D+'daily_2026-11-16_B.mp3', rating=None, spotted=False, note='cannot tell'),
 dict(id='daily_1117', pick='joe_syntax_hospital__11', clip=D+'daily_2026-11-17_B.mp3', rating=3, spotted=True),
 # follow-up variants the listener rated / compared
 dict(id='rca1111_engine', pick='joe_syntax_hospital__08', clip=D+'rca_2026-11-11_engine.mp3', rating=None, note="'pretty good, that will do it'"),
 dict(id='rca1111_phrase_cut', pick='joe_syntax_hospital__08', clip=D+'rca_2026-11-11_engine_phrase_cut.mp3', rating=None, note="'sounds off'"),
 dict(id='rca1111_long', pick='joe_syntax_hospital__08', clip=D+'rca_2026-11-11_long.mp3', rating=3.5),
 dict(id='rca1111_long_fix', pick='joe_syntax_hospital__08', clip=D+'rca_2026-11-11_long_fix.mp3', rating=4.25, note="'best one yet' (>4)"),
 dict(id='planner_ukf19', pick='hybrid_minds_ukf__19', clip=D+'planner_2026-11-15_hybrid_minds_ukf__19.mp3', rating=None, note="'really nice'"),
 dict(id='planner_ukf25', pick='hybrid_minds_ukf__25', clip=D+'planner_2026-11-15_hybrid_minds_ukf__25.mp3', rating=3.5),
 dict(id='planner_ukf25_v2', pick='hybrid_minds_ukf__25', clip=D+'planner_2026-11-15_ukf25_v2.mp3', rating=4),
 dict(id='ranker_A_default', pick='hybrid_minds_ukf__25', clip=D+'ranker_v0_hybrid_minds_ukf__25_A_default.mp3', rating=None, note="'super boring'"),
 dict(id='ranker_B_ranker', pick='hybrid_minds_ukf__25', clip=D+'ranker_v0_hybrid_minds_ukf__25_B_ranker.mp3', rating=None, note="'much much better'"),
 dict(id='rca1117_fix', pick='joe_syntax_hospital__11', clip=D+'rca_2026-11-17_fix.mp3', rating=None, note="'beat clash is gone'"),
]
# Pairwise preferences: (preferred, other)
PAIRS = [('rca1111_engine','rca1111_phrase_cut'), ('rca1111_long','daily_1111'), ('rca1111_long_fix','rca1111_long'),
         ('rca1111_long_fix','daily_1111'), ('rca1111_engine','daily_1111'), ('planner_ukf19','daily_1114'),
         ('planner_ukf25_v2','planner_ukf25'), ('ranker_B_ranker','ranker_A_default'), ('rca1117_fix','daily_1117')]
if __name__ == '__main__':
    recs = {r['id']: r for r in T.load_recs()}
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scored_labels.json')
    done = json.load(open(out_path)) if os.path.exists(out_path) else {}
    for it in ITEMS:
        if it['id'] in done: continue
        rec = recs[it['pick']]
        sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
        t = time.time()
        try:
            sc = score.score(rec['pro_clip'], it['clip'], src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
            b = sc['breakdown']
            row = dict(it, score=sc['score'], score_v2=sc['score_v2'], parts={k: b[k] for k in ('stem_curves','deck_curves','beat_align','bass_swap','outgoing_cut','blend_length','beat_identity','beat_align_v2','beat_off_ms')},
                       stems=b.get('stems'), events_pro=b.get('events_pro'), events_ours=b.get('events_ours'), align=b.get('align'))
        except Exception as e:
            row = dict(it, error=repr(e)[-300:])
        done[it['id']] = row
        json.dump(done, open(out_path, 'w'), indent=1, default=str)
        print(it['id'], row.get('score'), row.get('error'), f'{time.time()-t:.0f}s', flush=True)
    json.dump(dict(items=done, pairs=PAIRS), open(out_path, 'w'), indent=1, default=str) if False else None
