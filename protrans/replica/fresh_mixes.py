"""Fresh-mix test set (2026-11-18 night): ingest randomly chosen queued pro mixes (seed 20261118) with the normal corpus_v2
resolver/pipeline, until 2 mixes yield admitted transitions. These ids are recorded in replica/fresh_mixes.json and are never
used for training or tuning. Does not rewrite queue.json (the running corpus-v2 job owns it)."""
import json, os, random, sys
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); sys.path.insert(0, P)
import corpus_v2_pipeline as CP
OUT = os.path.join(H, 'fresh_mixes.json')
q = json.load(open(CP.QUEUE))['mixes']; todo = [m for m in q if m.get('status') == 'queued'][20:]
random.Random(20261118).shuffle(todo)
CP._mkdirs(); snap = CP.snapshot_protected(); got = json.load(open(OUT)) if os.path.exists(OUT) else dict(mixes=[], tried=[])
for m in todo:
    if len(got['mixes']) >= 2: break
    if m['mix_id'] in got['tried']: continue
    got['tried'].append(m['mix_id'])
    try:
        u = CP.ingest_mix(dict(m), snap)
    except Exception as ex:
        print('FAILED', m['mix_id'], ex, flush=True); u = dict(m, status='failed')
    print('mix', m['mix_id'], m['dj'], u.get('status'), u.get('n_admit'), flush=True)
    if u.get('n_admit'):
        got['mixes'].append(dict(mix_id=m['mix_id'], dj=m['dj'], url=m['url'], title=m.get('title'), n_admit=u.get('n_admit')))
    json.dump(got, open(OUT, 'w'), indent=1)
print('FRESH', json.dumps(got['mixes']))
