"""Fail-closed real-blend gate: source-fitted deck gains, not pro loudness.

Each deck must be within 12 dB of its own 95th-percentile fitted gain
for eight bars in total. Only simultaneous frames count; silent gaps do not.
The 0.25 s fit resolution slightly quantizes boundaries. Cached measurements
include thresholds/version so stale results cannot admit a daily pick.
"""
import json
import os
import numpy as np
import paths

VERSION = 'real-blend-v2'
LEVEL_DB = -12.0
MIN_BARS = 8.0
CACHE_JSON = os.path.join(paths.RESULTS, 'real_blend.json')


def assess(a, b, dt, bar_sec, level_db=LEVEL_DB, min_bars=MIN_BARS):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape or a.ndim != 1 or not len(a):
        raise ValueError('equal nonempty gain curves required')
    if dt <= 0 or bar_sec <= 0 or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('invalid gain curves or timing')
    refs = [float(np.percentile(np.maximum(x, 0), 95)) for x in (a, b)]
    masks = [(x >= ref * 10 ** (level_db / 20)) & (x > 1e-6) if ref > 1e-6
             else np.zeros(len(x), bool) for x, ref in zip((a, b), refs)]
    both = masks[0] & masks[1]
    edges = np.diff(np.r_[False, both, False].astype(int))
    lengths = np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)
    longest = float(max(lengths, default=0) * dt / bar_sec)
    passed = float(both.sum() * dt / bar_sec) + 1e-9 >= min_bars
    return dict(version=VERSION, level_db=level_db, min_bars=min_bars,
                overlap_bars=round(float(both.sum() * dt / bar_sec), 3),
                longest_overlap_bars=round(longest, 3), references=refs,
                flagged=not passed, reason=None if passed else 'insufficient_overlap')


def load_cache():
    return json.load(open(CACHE_JSON)) if os.path.exists(CACHE_JSON) else {}


def fingerprint(row):
    import hashlib
    pro = row.get('pro_clip') or os.path.join(paths.CLIPS, row['split'], row['id'], 'pro.wav')
    files = [pro] + [os.path.join(paths.LIB, row[d]['yt'] + '.m4a') for d in ('a', 'b')]
    stamps = []
    for p in files:
        st = os.stat(p)
        stamps.append((os.path.abspath(p), st.st_size, st.st_mtime_ns))
    return hashlib.sha256(repr(stamps).encode()).hexdigest()


def check_row(row, force=False):
    import score
    import diagnose_gap as D
    c = load_cache()
    old = c.get(row['id'], {})
    try:
        signature = fingerprint(row)
    except OSError as e:
        return dict(version=VERSION, flagged=True, error=str(e), reason='missing_input')
    if (not force and old.get('version') == VERSION and old.get('fingerprint') == signature
            and old.get('level_db') == LEVEL_DB and old.get('min_bars') == MIN_BARS
            and not old.get('error')):
        return old
    try:
        pro = row.get('pro_clip') or os.path.join(paths.CLIPS, row['split'], row['id'], 'pro.wav')
        mix = score._load(pro)
        aligned = []
        for deck in ('a', 'b'):
            path = os.path.join(paths.LIB, row[deck]['yt'] + '.m4a')
            loc = D.version_match.locate_in(mix, score._load(path))
            if loc.get('track_t') is None:
                raise ValueError('source_locator_failed_' + deck)
            y = D.place_source(path, loc['track_t'], loc['mix_t'], len(mix))
            y, _ = D.refine_lag(mix, y)
            aligned.append(y)
        gains, _, times, hop = D.band_gains(mix, *aligned)
        r = assess(gains['all']['a'], gains['all']['b'], hop / D.SR, D.BAR_SEC)
    except Exception as e:
        r = dict(version=VERSION, flagged=True, error=str(e), reason='measurement_failed')
    r.update(dj=row['dj'], split=row['split'], fingerprint=signature)
    import fcntl, tempfile
    with open(CACHE_JSON + '.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        c = load_cache()
        c[row['id']] = r
        fd, tmp = tempfile.mkstemp(dir=paths.RESULTS, prefix='.real_blend_', suffix='.json')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(c, f, indent=2)
            os.replace(tmp, CACHE_JSON)
        finally:
            if os.path.exists(tmp): os.remove(tmp)
    return r


def eligible(row):
    return not check_row(row).get('flagged', True)


if __name__ == '__main__':
    rows = json.load(open(os.path.join(paths.RESULTS, 'admitted.json')))
    # Include the known negative control, already excluded for talkover.
    for row in json.load(open(os.path.join(paths.RESULTS, 'talkover_rejected.json'))):
        if row['id'] == 'hospital_podcast393__04':
            rows.append(row)
    for row in rows:
        print(row['id'], json.dumps(check_row(row, force='--force' in __import__('sys').argv)), flush=True)
