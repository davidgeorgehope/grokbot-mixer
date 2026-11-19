"""2026-11-19 day: NEW fresh pro liquid mix for the PLACE=safe planner, ingested fully ISOLATED in replica/fresh_work_s:
own work/lib/clips/mixes, own accepted/rejected ledgers and features (nothing appended to corpus_v2), sources KEPT locally until
the renders and hard checks are done (archive_mix is a no-op here; nothing shared is deleted). Pool = queued corpus-v2 mixes whose title
contains 'liquid', queue index >= 40, DJ not KushSessions/Liquicity*/Hospital (holdout), not in fresh_mixes.json tried/mixes, not in
corpus_v2/accepted.jsonl. Seed 20261119+1. Stops at the first mix with >= 3 admitted transitions. Scored once, then spent."""
import json, os, random, sys
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); sys.path.insert(0, P)
import corpus_v2_pipeline as CP
OUT = os.path.join(H, 'fresh_mixes.json'); FW = os.path.join(H, 'fresh_work_s')
CP.WORK = FW; CP.LIB = os.path.join(FW, 'lib'); CP.CLIPS = os.path.join(FW, 'clips'); CP.MIXES_DIR = os.path.join(FW, 'mixes')
CP.ACCEPTED = os.path.join(FW, 'accepted.jsonl'); CP.REJECTED = os.path.join(FW, 'rejected.jsonl'); CP.FEATURES = os.path.join(FW, 'features')
CP.PROGRESS = os.path.join(FW, 'progress.json'); CP.MANIFEST = os.path.join(FW, 'manifest.json'); CP.SUMMARY = os.path.join(FW, 'summary.json')
CP.archive_mix = lambda mix, rows: {}
for d in (CP.LIB, CP.CLIPS, CP.MIXES_DIR, CP.FEATURES): os.makedirs(d, exist_ok=True)
acc = {json.loads(l)['mix_id'] for l in open(os.path.join(P, 'corpus_v2', 'accepted.jsonl'))}
q = json.load(open(CP.QUEUE))['mixes']; queued = [m for m in q if m.get('status') == 'queued']
got = json.load(open(OUT)); used = set(got['tried']) | {m['mix_id'] for m in got['mixes']}
pool = [m for i, m in enumerate(queued) if i >= 40 and 'liquid' in (m.get('title') or '').lower()
        and not any(x in m['dj'] for x in ('KushSessions', 'Liquicity', 'Hospital')) and m['mix_id'] not in used and m['mix_id'] not in acc]
random.Random(20261120).shuffle(pool); print('pool', len(pool), [m['mix_id'] for m in pool[:10]], flush=True)
snap = CP.snapshot_protected()
for m in pool[:6]:
    got['tried'].append(m['mix_id'])
    try: u = CP.ingest_mix(dict(m), snap)
    except Exception as ex: print('FAILED', m['mix_id'], ex, flush=True); u = dict(m, status='failed')
    print('mix', m['mix_id'], m['dj'], u.get('status'), u.get('n_admit'), flush=True)
    if (u.get('n_admit') or 0) >= 3:
        got['mixes'].append(dict(mix_id=m['mix_id'], dj=m['dj'], url=m['url'], title=m.get('title'), n_admit=u.get('n_admit'), for_night='2026-11-19-day-safeplace'))
        json.dump(got, open(OUT, 'w'), indent=1); print('FRESH', json.dumps(got['mixes'][-1]), flush=True); break
    json.dump(got, open(OUT, 'w'), indent=1)
