"""2026-11-23: ingest TWO more unused pro liquid mixes into the existing
isolated fresh_work_1123 (YoloWich already admitted there). Queue.json is
read-only and is not required: these mixes were not in the queue.

  nicky_havey_1xpuWyKZ4R0
    https://www.youtube.com/watch?v=1xpuWyKZ4R0
    Nicky Havey, "Liquid Drum & Bass Mix - January 2026"
    Verified live via YouTube oembed 2026-11-23 ~7:58 PM ET.
    New DJ, official Artist-Title chapters, 17 tracks, 16 goldilocks.

  outer_bass_3Tt7qDw8uaQ
    https://www.youtube.com/watch?v=3Tt7qDw8uaQ
    Outer Bass, "2026 Liquid Drum and Bass Mix"
    Verified live via YouTube oembed 2026-11-23 ~7:58 PM ET.
    New DJ, official Artist-Title chapters, 33 tracks, 28 goldilocks.

Neither DJ is in corpus-v2 accepted rows, the locked Liquicity/Hospital
holdout, or fresh_mixes.json tried/spent. Sources are kept. rules.json is
not written.
"""
import json, os, shutil, sys, time

H = os.path.dirname(os.path.abspath(__file__))
P = os.path.dirname(H)
sys.path.insert(0, P)
import corpus_v2_pipeline as CP
import admit

MIXES = [
    dict(mix_id='nicky_havey_1xpuWyKZ4R0', video_id='1xpuWyKZ4R0', dj='Nicky Havey',
         url='https://www.youtube.com/watch?v=1xpuWyKZ4R0',
         title='Liquid Drum & Bass Mix - January 2026', status='queued'),
    dict(mix_id='outer_bass_3Tt7qDw8uaQ', video_id='3Tt7qDw8uaQ', dj='Outer Bass',
         url='https://www.youtube.com/watch?v=3Tt7qDw8uaQ',
         title='2026 Liquid Drum and Bass Mix', status='queued'),
]
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
CP.META_CACHE = os.path.join(FW, 'meta_cache')
CP.archive_mix = lambda mix, rows: {}

for d in (CP.LIB, CP.CLIPS, CP.MIXES_DIR, CP.FEATURES, CP.META_CACHE):
    os.makedirs(d, exist_ok=True)

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


def _register(mix, extra=None):
    got = json.load(open(OUT)) if os.path.exists(OUT) else dict(mixes=[], tried=[])
    rec = None
    for x in got['mixes']:
        if x['mix_id'] == mix['mix_id']:
            rec = x
            break
    if rec is None:
        rec = dict(mix_id=mix['mix_id'], dj=mix['dj'], url=mix['url'], title=mix.get('title'), n_admit=0)
        got['mixes'].append(rec)
    rec['for_night'] = '2026-11-23'
    rec['queued'] = True
    rec.setdefault('queued_on', time.strftime('%Y-%m-%d %H:%M ET'))
    rec['note'] = (
        'New DJ, not in corpus-v2 accepted DJs, not in the locked Liquicity/Hospital '
        'holdout, not previously spent. Isolated ingest in replica/fresh_work_1123. '
        'Do not rewrite corpus_v2/queue.json.'
    )
    if extra:
        rec.update(extra)
    if mix['mix_id'] not in got['tried']:
        got['tried'].append(mix['mix_id'])
    json.dump(got, open(OUT, 'w'), indent=1)
    return got


if __name__ == '__main__':
    only = os.environ.get('FRESH_MIX')
    todo = [m for m in MIXES if (not only or m['mix_id'] == only or m['video_id'] == only)]
    if not todo:
        raise SystemExit(f'no mix matched FRESH_MIX={only!r}')
    snap = CP.snapshot_protected()
    failed = 0
    for m in todo:
        _register(m)
        print('=== start', m['mix_id'], m['url'], flush=True)
        if not os.path.exists(os.path.join(CP.META_CACHE, m['video_id'] + '.json')):
            raise SystemExit(f"missing isolated meta for {m['video_id']}")
        u = CP.ingest_mix(dict(m), snap)
        print('mix', m['mix_id'], u.get('status'), 'admit', u.get('n_admit'), 'reject', u.get('n_reject'), flush=True)
        got = json.load(open(OUT))
        for x in got['mixes']:
            if x['mix_id'] == m['mix_id']:
                x['n_admit'] = u.get('n_admit')
                x['n_reject'] = u.get('n_reject')
                x['ingested'] = '2026-11-23 isolated in replica/fresh_work_1123'
                x['status'] = u.get('status')
        json.dump(got, open(OUT, 'w'), indent=1)
        print('FRESH', m['mix_id'], u.get('n_admit'), flush=True)
        if not u.get('n_admit'):
            failed += 1
    if failed == len(todo):
        sys.exit(2)
