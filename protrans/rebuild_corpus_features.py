#!/usr/bin/env python3
"""Re-extract corpus_v2 features from feat_lib (Drive restore), not work/.

Fixes the sections_from_bar ndarray truth-value bug, then writes features
atomically. Safe to run while the corpus-v2 ingest job is running: it only
reads accepted.jsonl and feat_lib, and only replaces feature files that
currently have a features_bar error (or --all).
"""
from __future__ import annotations
import json, os, sys, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import corpus_v2_pipeline as P
import fetch

FEAT_LIB = os.path.join(P.ROOT, 'feat_lib')
WORKERS = int(os.environ.get('FEAT_WORKERS', '2'))


def media_path(side):
    key = fetch.media_key(side) if hasattr(fetch, 'media_key') else (side or {}).get('yt')
    if not key:
        key = (side or {}).get('yt') or (side or {}).get('id')
    if not key:
        return None, None
    p = os.path.join(FEAT_LIB, f'{key}.m4a')
    return key, p if os.path.exists(p) and os.path.getsize(p) > 100_000 else None


def needs_rebuild(feat_path, force=False):
    if force or not os.path.exists(feat_path):
        return True
    try:
        feat = json.load(open(feat_path))
    except Exception:
        return True
    if feat.get('error') or feat.get('cand_error'):
        return True
    sa = (feat.get('track_a') or {}).get('sections') or {}
    sb = (feat.get('track_b') or {}).get('sections') or {}
    if not sa or not sb or not (feat.get('candidates') or []):
        return True
    return False


def _one(payload):
    os.environ.setdefault('OMP_NUM_THREADS', '1')
    row, force = payload
    dest = os.path.join(P.FEATURES, row['id'] + '.json')
    if not needs_rebuild(dest, force):
        return dict(id=row['id'], status='skip')
    ka, sa = media_path(row.get('a') or {})
    kb, sb = media_path(row.get('b') or {})
    if not sa or not sb:
        return dict(id=row['id'], status='missing_audio', a=ka, b=kb, sa=bool(sa), sb=bool(sb))
    rec = {}
    try:
        feat = P.extract_features(row, rec, sa, sb)
        ok = not feat.get('error') and bool((feat.get('track_a') or {}).get('sections'))
        n_c = len(feat.get('candidates') or [])
        return dict(id=row['id'], status='ok' if ok else 'error',
                    error=feat.get('error'), n_cands=n_c,
                    in_sec=(feat.get('cue') or {}).get('incoming_section'),
                    out_sec=(feat.get('cue') or {}).get('outgoing_section'))
    except Exception as e:
        return dict(id=row['id'], status='exception', error=f'{type(e).__name__}: {e}'[:240],
                    tb=traceback.format_exc()[-400:])


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--workers', type=int, default=WORKERS)
    args = ap.parse_args()
    os.makedirs(P.FEATURES, exist_ok=True)
    rows = list(P.load_jsonl(P.ACCEPTED))
    print(f'rebuild features: {len(rows)} accepted, lib={FEAT_LIB}, workers={args.workers}', flush=True)
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_one, (r, args.all)) for r in rows]
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            results.append(r)
            print(f"  {i}/{len(rows)} {r['id']} {r['status']}"
                  + (f" cands={r.get('n_cands')} {r.get('out_sec')}>{r.get('in_sec')}" if r.get('n_cands') is not None else '')
                  + (f" err={r.get('error')}" if r.get('error') else ''), flush=True)
    from collections import Counter
    c = Counter(r['status'] for r in results)
    print('RESULT', json.dumps(dict(n=len(results), status=dict(c))), flush=True)
    outp = os.path.join(P.ROOT, '..', 'ranker', 'rebuild_features.json')
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    json.dump(dict(status=dict(c), rows=results), open(outp, 'w'), indent=2)
    return 0 if c.get('exception', 0) == 0 and c.get('missing_audio', 0) < len(rows) else 2


if __name__ == '__main__':
    raise SystemExit(main())
