"""2026-11-23: ingest a NEW unused fresh mix, fully ISOLATED.

Mix: yolowich_FIdBhH3SuXk (YoloWich, "Hybrid Minds - Drum n Bass Listening Liquid Set")
https://www.youtube.com/watch?v=FIdBhH3SuXk
Verified live via YouTube oembed 2026-11-23 19:20 ET.

Why this mix: new DJ (not in corpus-v2 accepted DJs, not KushSessions / John B / Alpha
Rhythm / the 11-19 dev set, not Liquicity/Hospital locked holdout), not in
fresh_mixes.json tried/spent, official Artist-Title chapters, 8 goldilocks pairs,
explicitly liquid. Queue.json is read, never rewritten. Sources kept until
renders and hard checks finish. corpus_v2 ledgers and work dirs are not used.
"""
import json, os, shutil, sys, time

H = os.path.dirname(os.path.abspath(__file__))
P = os.path.dirname(H)
sys.path.insert(0, P)
import corpus_v2_pipeline as CP
import admit
import fetch as _F  # used so a later host override can be process-local if box YouTube fails

MIX_ID = 'yolowich_FIdBhH3SuXk'
OUT = os.path.join(H, 'fresh_mixes.json')
FW = os.path.join(H, 'fresh_work_1123')
CP.WORK = FW
CP.LIB = os.path.join(FW, 'lib')
CP.CLIPS = os.path.join(FW, 'clips')
CP.MIXES_DIR = os.path.join(FW, 'mixes')
CP.ACCEPTED = os.path.join(FW, 'accepted.jsonl')
CP.REJECTED = os.path.join(FW, 'rejected.jsonl')
CP.FEATURES = os.path.join(FW, 'features')
CP.PROGRESS = os.path.join(FW, 'progress.json')
CP.MANIFEST = os.path.join(FW, 'manifest.json')
CP.SUMMARY = os.path.join(FW, 'summary.json')
# Do not delete sources or rewrite Drive from this isolated pass.
CP.archive_mix = lambda mix, rows: {}

for d in (CP.LIB, CP.CLIPS, CP.MIXES_DIR, CP.FEATURES):
    os.makedirs(d, exist_ok=True)

# Resolve caches: copy-on-write so we do not race the running corpus-v2 job.
_cache_dir = os.path.join(FW, 'search_cache')
os.makedirs(_cache_dir, exist_ok=True)
for src, name in (
    (admit._source_cache_path(), 'source_search_cache.json'),
    (admit._legacy_cache_path(), 'yt_search_cache.json'),
):
    dest = os.path.join(_cache_dir, name)
    if os.path.exists(src) and not os.path.exists(dest):
        shutil.copy2(src, dest)
admit._source_cache_path = lambda: os.path.join(_cache_dir, 'source_search_cache.json')
admit._legacy_cache_path = lambda: os.path.join(_cache_dir, 'yt_search_cache.json')


def _register_queued(mix):
    got = json.load(open(OUT)) if os.path.exists(OUT) else dict(mixes=[], tried=[])
    rec = None
    for x in got['mixes']:
        if x['mix_id'] == MIX_ID:
            rec = x
            break
    if rec is None:
        rec = dict(mix_id=MIX_ID, dj=mix['dj'], url=mix['url'], title=mix.get('title'),
                   n_admit=0)
        got['mixes'].append(rec)
    rec['for_night'] = '2026-11-23'
    rec['queued'] = True
    rec.setdefault('queued_on', time.strftime('%Y-%m-%d %H:%M ET'))
    rec['note'] = (
        'New DJ, not in corpus-v2 accepted DJs, not in the locked Liquicity/Hospital '
        'holdout, not previously spent. Isolated ingest in replica/fresh_work_1123. '
        'Do not rewrite corpus_v2/queue.json.'
    )
    if MIX_ID not in got['tried']:
        got['tried'].append(MIX_ID)
    json.dump(got, open(OUT, 'w'), indent=1)
    return got


if __name__ == '__main__':
    q = json.load(open(CP.QUEUE))['mixes']
    hits = [x for x in q if x['mix_id'] == MIX_ID]
    if not hits:
        raise SystemExit(f'{MIX_ID} not found in queue.json (read-only lookup)')
    m = dict(hits[0])
    # ingest_mix returns early if status is already done/no_goldilocks in the
    # queue record; force a fresh isolated pass without writing the queue.
    m['status'] = 'queued'
    _register_queued(m)
    snap = CP.snapshot_protected()
    u = CP.ingest_mix(dict(m), snap)
    print('mix', m['mix_id'], u.get('status'), u.get('n_admit'), flush=True)
    got = json.load(open(OUT))
    for x in got['mixes']:
        if x['mix_id'] == MIX_ID:
            x['n_admit'] = u.get('n_admit')
            x['n_reject'] = u.get('n_reject')
            x['ingested'] = '2026-11-23 isolated in replica/fresh_work_1123'
            x['status'] = u.get('status')
    json.dump(got, open(OUT, 'w'), indent=1)
    print('FRESH', u.get('n_admit'), flush=True)
    if not u.get('n_admit'):
        sys.exit(2)
