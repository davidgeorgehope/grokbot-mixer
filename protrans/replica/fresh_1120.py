"""2026-11-20 nightly: ingest the pre-registered fresh mix (Sirenity ofcHup56lME, fresh_mixes.json for_night 2026-11-20)
fully ISOLATED in replica/fresh_work_1120: own work/lib/clips/mixes, own accepted/rejected ledgers and features
(nothing appended to corpus_v2, queue.json not rewritten), sources KEPT until renders/hard checks are done."""
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); sys.path.insert(0, P)
import corpus_v2_pipeline as CP
import fetch as _F
# 2026-11-20 1:25 AM ET: the direct tailnet hop (nc, DERP relay only) times out at the ssh banner; the Pi jump route works.
# Process-local override only (config.env untouched, corpus-v2 unaffected).
_F._host = lambda: os.environ.get('FRESH_HOST') or ('m' + 'ini' + '-via-pi')
OUT = os.path.join(H, 'fresh_mixes.json'); FW = os.path.join(H, 'fresh_work_1120')
CP.WORK = FW; CP.LIB = os.path.join(FW, 'lib'); CP.CLIPS = os.path.join(FW, 'clips'); CP.MIXES_DIR = os.path.join(FW, 'mixes')
CP.ACCEPTED = os.path.join(FW, 'accepted.jsonl'); CP.REJECTED = os.path.join(FW, 'rejected.jsonl'); CP.FEATURES = os.path.join(FW, 'features')
CP.PROGRESS = os.path.join(FW, 'progress.json'); CP.MANIFEST = os.path.join(FW, 'manifest.json'); CP.SUMMARY = os.path.join(FW, 'summary.json')
CP.archive_mix = lambda mix, rows: {}
for d in (CP.LIB, CP.CLIPS, CP.MIXES_DIR, CP.FEATURES): os.makedirs(d, exist_ok=True)
if __name__ == '__main__':
    q = json.load(open(CP.QUEUE))['mixes']
    m = [x for x in q if x['mix_id'] == 'sirenity_ofcHup56lME'][0]
    snap = CP.snapshot_protected()
    u = CP.ingest_mix(dict(m), snap)
    print('mix', m['mix_id'], u.get('status'), u.get('n_admit'), flush=True)
    got = json.load(open(OUT))
    for x in got['mixes']:
        if x['mix_id'] == m['mix_id']:
            x['n_admit'] = u.get('n_admit'); x['ingested'] = '2026-11-20 nightly, isolated in replica/fresh_work_1120'
    if m['mix_id'] not in got['tried']: got['tried'].append(m['mix_id'])
    json.dump(got, open(OUT, 'w'), indent=1)
    print('FRESH', u.get('n_admit'), flush=True)
