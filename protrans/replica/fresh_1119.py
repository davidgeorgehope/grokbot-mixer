"""Fresh-mix test for the 2026-11-19 nightly picker: ingest ONE new randomly chosen (seed 20261119) queued liquid DnB pro mix
with the normal corpus_v2 pipeline in replica/fresh_work (isolated). Pool = queued, title contains 'liquid', queue index >= 40
(far from the running corpus-v2 job's front), DJ not KushSessions/Liquicity*/Hospital (Kush is over-represented; Liquicity and
Hospital are the locked holdout), mix not in fresh_mixes.json 'tried' and not in the accepted snapshot. Stops at the first mix with
>= 3 admitted transitions. Records it in fresh_mixes.json (mixes + tried + spent_on). Scored once, then spent."""
import json, os, random, sys
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); sys.path.insert(0, P)
import corpus_v2_pipeline as CP
OUT = os.path.join(H, 'fresh_mixes.json')
FW = os.path.join(H, 'fresh_work'); CP.WORK = FW; CP.LIB = os.path.join(FW, 'lib'); CP.CLIPS = os.path.join(FW, 'clips'); CP.MIXES_DIR = os.path.join(FW, 'mixes')
for d in (CP.LIB, CP.CLIPS, CP.MIXES_DIR): os.makedirs(d, exist_ok=True)
snapacc = {json.loads(l)['mix_id'] for l in open(os.path.join(H, 'nightly_1119_work', 'accepted_snapshot.jsonl'))}
q = json.load(open(CP.QUEUE))['mixes']; queued = [m for m in q if m.get('status') == 'queued']
got = json.load(open(OUT))
pool = [m for i, m in enumerate(queued) if i >= 40 and 'liquid' in (m.get('title') or '').lower()
        and not any(x in m['dj'] for x in ('KushSessions', 'Liquicity', 'Hospital')) and m['mix_id'] not in got['tried'] and m['mix_id'] not in snapacc]
random.Random(20261119).shuffle(pool); print('pool', [m['mix_id'] for m in pool], flush=True)
CP._mkdirs(); snap = CP.snapshot_protected()
for m in pool:
    got['tried'].append(m['mix_id'])
    try:
        u = CP.ingest_mix(dict(m), snap)
    except Exception as ex:
        print('FAILED', m['mix_id'], ex, flush=True); u = dict(m, status='failed')
    print('mix', m['mix_id'], m['dj'], u.get('status'), u.get('n_admit'), flush=True)
    if (u.get('n_admit') or 0) >= 3:
        got['mixes'].append(dict(mix_id=m['mix_id'], dj=m['dj'], url=m['url'], title=m.get('title'), n_admit=u.get('n_admit'), for_night='2026-11-19'))
        json.dump(got, open(OUT, 'w'), indent=1); break
    json.dump(got, open(OUT, 'w'), indent=1)
print('FRESH', json.dumps(got['mixes'][-1]))
