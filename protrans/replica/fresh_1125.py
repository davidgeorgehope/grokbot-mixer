"""2026-11-25: ingest an unspent unseen-DJ pro liquid DnB mix, fully ISOLATED.

Mix: zaklynskyi_SKL2rC3tcug (Euphoria System, "Zaklynskyi Liquid Drum and Bass Mix Vol 5  - Seasons")
https://www.youtube.com/watch?v=SKL2rC3tcug
Verified live via yt-dlp 2026-11-25.

New DJ (not in corpus-v2 accepted/queued DJs, not in Liquicity/Hospital holdout, not in
fresh_mixes.json tried/spent), official Artist - Title chapters (16 tracks: S.P.Y, High
Contrast, Dawn Wall, Sub:liminal, Citra, goddard.), liquid DnB. Isolated in
replica/fresh_work_1125/; does not touch corpus_v2 or rules.json.
"""
import json, os, shutil, sys, time

H = os.path.dirname(os.path.abspath(__file__))
P = os.path.dirname(H)
sys.path.insert(0, P)
import corpus_v2_pipeline as CP
import admit

MIX = dict(
    mix_id='zaklynskyi_SKL2rC3tcug',
    video_id='SKL2rC3tcug',
    dj='Euphoria System',
    url='https://www.youtube.com/watch?v=SKL2rC3tcug',
    title='Zaklynskyi Liquid Drum and Bass Mix Vol 5  - Seasons',
    status='queued',
)
OUT = os.path.join(H, 'fresh_mixes.json')
FW = os.path.join(H, 'fresh_work_1125')

CP.ROOT = FW
CP.WORK = FW
CP.LIB = os.path.join(FW, 'lib')
CP.CLIPS = os.path.join(FW, 'clips')
CP.MIXES_DIR = os.path.join(FW, 'mixes')
CP.META_CACHE = os.path.join(FW, 'meta_cache')
CP.QUEUE = os.path.join(FW, 'queue.json')
CP.ACCEPTED = os.path.join(FW, 'accepted.jsonl')
CP.REJECTED = os.path.join(FW, 'rejected.jsonl')
CP.FEATURES = os.path.join(FW, 'features')
CP.PROGRESS = os.path.join(FW, 'progress.json')
CP.SPLIT = os.path.join(FW, 'split.json')
CP.MANIFEST = os.path.join(FW, 'manifest.json')
CP.RESOLVE_RETRY = os.path.join(FW, 'resolve_retry.json')
CP.SUMMARY = os.path.join(FW, 'summary.json')
CP.MODEL_DIR = os.path.join(FW, 'models')
CP.archive_mix = lambda mix, rows: {}

for d in (CP.LIB, CP.CLIPS, CP.MIXES_DIR, CP.FEATURES, CP.META_CACHE, CP.MODEL_DIR):
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
    rec['for_night'] = '2026-11-25-fresh'
    rec['queued'] = True
    rec.setdefault('queued_on', time.strftime('%Y-%m-%d %H:%M ET'))
    rec.setdefault('spent', False)
    rec['note'] = (
        'Unseen DJ (Euphoria System / Zaklynskyi), not in corpus-v2 accepted/queued DJs, '
        'not in locked Liquicity/Hospital holdout, not previously spent. Isolated ingest in '
        'replica/fresh_work_1125. Do not touch corpus_v2.'
    )
    if extra:
        rec.update(extra)
    if mix['mix_id'] not in got['tried']:
        got['tried'].append(mix['mix_id'])
    json.dump(got, open(OUT, 'w'), indent=1)
    return got


if __name__ == '__main__':
    _register(MIX)
    print('=== start', MIX['mix_id'], MIX['url'], flush=True)
    snap = CP.snapshot_protected()
    u = CP.ingest_mix(dict(MIX), snap)
    print('mix', MIX['mix_id'], u.get('status'), 'admit', u.get('n_admit'), 'reject', u.get('n_reject'), flush=True)
    _register(MIX, dict(
        n_admit=u.get('n_admit'),
        n_reject=u.get('n_reject'),
        ingested='2026-11-25 isolated in replica/fresh_work_1125',
        status=u.get('status'),
    ))
    if not u.get('n_admit'):
        sys.exit(2)
