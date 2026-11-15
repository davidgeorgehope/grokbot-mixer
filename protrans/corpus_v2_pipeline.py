"""Scale the pro-transition corpus into an isolated corpus_v2 dataset.

Does not write protrans/rules.json, results/admitted.json, the official
clips/lib trees, or the 33-pair score checkpoints. Quality gates are the
same as the existing admit path (locate z>=6, cc>=0.28, BPM 169-179,
talkover, real-blend v3). Source audio is archived to Google Drive and
removed from the box after a verified copy.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import time
import traceback

import numpy as np

import admit
import extract
import fetch
import paths
import real_blend
import structure as S
import talkover
import version_match

ROOT = os.path.join(paths.ROOT, 'corpus_v2')
WORK = os.path.join(ROOT, 'work')
LIB = os.path.join(WORK, 'lib')
CLIPS = os.path.join(WORK, 'clips')
MIXES_DIR = os.path.join(WORK, 'mixes')
META_CACHE = os.path.join(ROOT, 'meta_cache')
QUEUE = os.path.join(ROOT, 'queue.json')
ACCEPTED = os.path.join(ROOT, 'accepted.jsonl')
REJECTED = os.path.join(ROOT, 'rejected.jsonl')
FEATURES = os.path.join(ROOT, 'features')
PROGRESS = os.path.join(ROOT, 'progress.json')
SPLIT = os.path.join(ROOT, 'split.json')
MANIFEST = os.path.join(ROOT, 'manifest.json')
LEGACY = os.path.join(ROOT, 'legacy_33.jsonl')
SUMMARY = os.path.join(ROOT, 'summary.json')
MODEL_DIR = os.path.join(ROOT, 'models')

RCLONE = os.path.expanduser('~/bin/rclone')
DRIVE = 'gdrive:DJ Mixes Archive/protrans/corpus_v2'
SPLIT_SEED = 20261115
HELD_OUT_MIX_FRAC = 0.20
TARGET_ACCEPT = 300
TRAIN_MIN = 150
SLOT_LO, SLOT_HI = 90, 280

# Official 33-pair mixes: never re-ingest, never train the ranker on them.
LEGACY_VIDEO_IDS = {
    'Ea4ngKLPNMQ',  # Hybrid Minds UKF
    'zgKc7vQNrrE',  # Joe Syntax Hospital
    '0yIOFIW4Eow',  # Netsky Hospital Classics
    'PZ6aQYEIqm0',  # Maduk Liquicity Lunar 2025
    'nNpy62IMI-A',  # Pola & Bryson Puzzlewood
    'ifOtJV-xZ-U',  # Wilkinson Boomtown 2026
}
PROTECTED = [
    os.path.join(paths.RESULTS, 'admitted.json'),
    paths.RULES,
    os.path.join(paths.RESULTS, 'real_blend.json'),
    os.path.join(paths.RESULTS, 'talkover.json'),
    paths.CORPUS,
]

# Yearmix / megamix titles are not live DJ blends (see CORPUS_PLAN.md).
_SKIP_TITLE = re.compile(
    r'year\s*mix|megamix|best of 20|top\s*\d+|nightcore|sped up|slowed'
    r'|8d audio|mashup compilation|album mix(?!er)',
    re.I,
)

SEED_VIDEOS = [
    # Known Hospital / Liquicity / UKF-style sets not in the 33-pair cohort.
    'https://www.youtube.com/watch?v=2wXDFi2eL1U',  # HP393 London Elektricity
    'https://www.youtube.com/watch?v=az6BZJAQCGo',  # HP400 London Elektricity
    'https://www.youtube.com/watch?v=XR2FdYeJ_4U',  # HP425 Grafix
    'https://www.youtube.com/watch?v=GwCR07oXGZs',  # HP452 Whiney
    'https://www.youtube.com/watch?v=QkzMkgg2flQ',  # HP478 Degs
    'https://www.youtube.com/watch?v=wRxePyKWgdU',  # GLXY Fabric rooftop
]

SEED_QUERIES = [
    'Hospital Podcast Hospital Records',
    'Hospital Records DJ mix tracklist',
    'UKF liquid drum and bass mix',
    'UKF Drum & Bass Mix official',
    'Liquicity festival DJ set',
    'Liquicity Records DJ set tracklist',
    'Hybrid Minds DJ set liquid',
    'Logistics DJ mix Hospital Records',
    'Netsky DJ set Hospital',
    'Maduk DJ set Liquicity',
    'Pola & Bryson DJ set',
    'KushSessions liquid drum and bass',
    'Alpha Rhythm liquid drum and bass podcast',
    'Shogun Audio liquid DJ set',
    'Med School Hospital podcast mix',
    'Fred V Grafix DJ set Hospital',
    'High Contrast DJ set Hospital',
    'LSB DJ set liquid drum and bass',
    'Etherwood DJ set Hospital',
    'Technimatic DJ set liquid',
    'Nu:Tone DJ set Hospital',
    'Whiney DJ set Hospital Podcast',
    'Degs Hospital Podcast mix',
]

SEED_LISTS = [
    'https://www.youtube.com/@hospitalrecords/videos',
    'https://www.youtube.com/@hospitalrecords/playlists',
    'https://www.youtube.com/@UKF/search?query=liquid%20drum%20bass%20mix',
    'https://www.youtube.com/@Liquicity/videos',
    'https://www.youtube.com/@HybridMinds/videos',
    'https://www.youtube.com/@KushSessions/videos',
    'https://www.youtube.com/@ShogunAudio/videos',
    'https://www.youtube.com/@MedSchoolMusic/videos',
]


def _mkdirs():
    for d in (ROOT, WORK, LIB, CLIPS, MIXES_DIR, META_CACHE, FEATURES, MODEL_DIR):
        os.makedirs(d, exist_ok=True)


def _atomic_json(path, obj):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    json.dump(obj, open(tmp, 'w'), indent=2)
    os.replace(tmp, path)


def sha256_file(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def snapshot_protected():
    return {p: sha256_file(p) for p in PROTECTED}


def assert_protected(snap, where=''):
    bad = []
    now = snapshot_protected()
    for p, old in snap.items():
        if now.get(p) != old:
            bad.append(p)
    if bad:
        raise RuntimeError(f'protected files changed {where}: {bad}')


def append_jsonl(path, row):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'a') as f:
        f.write(json.dumps(row) + '\n')


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    for line in open(path):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def save_progress(p):
    p = dict(p)
    p['ts'] = time.strftime('%Y-%m-%d %H:%M:%S %Z')
    _atomic_json(PROGRESS, p)


def load_progress():
    return json.load(open(PROGRESS)) if os.path.exists(PROGRESS) else dict(
        phase='init', accepted=0, rejected=0, mixes_done=0)


def slug(s, n=48):
    s = re.sub(r'[^a-zA-Z0-9]+', '_', (s or '').strip()).strip('_').lower()
    return (s or 'mix')[:n]


def video_id_from_url(url):
    if not url:
        return None
    if 'watch?v=' in url:
        return url.split('watch?v=', 1)[1].split('&')[0]
    if 'youtu.be/' in url:
        return url.split('youtu.be/', 1)[1].split('?')[0].split('/')[0]
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', url):
        return url
    return None


def watch_url(vid_or_url):
    vid = video_id_from_url(vid_or_url) or vid_or_url
    if vid.startswith('http'):
        return vid
    return 'https://www.youtube.com/watch?v=' + vid


# ---------- remote listing (existing yt-dlp HOST flow) ----------

def ytdlp_flat(url, limit=None):
    """Flat-list a playlist, channel, or search URL on HOST. No download."""
    host = fetch._host()
    extra = f' --playlist-end {int(limit)}' if limit else ''
    script = (
        'set -euo pipefail\n'
        'export PATH=/opt/homebrew/bin:$HOME/.ytdlp-nightly/bin:$PATH\n'
        + fetch._ytdlp_snippet() +
        f'\nURL={__import__("shlex").quote(url)}\n'
        'for jar in safari chrome; do\n'
        f'  if $YTDLP --no-update --cookies-from-browser "$jar" --flat-playlist '
        f'--skip-download --no-warnings --no-progress{extra} '
        f'--print "%(id)s\\t%(title)s\\t%(duration)s\\t%(channel)s\\t%(webpage_url)s" "$URL"; then\n'
        '    exit 0\n'
        '  fi\n'
        'done\n'
        'exit 1\n'
    )
    r = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=25',
                        host, 'bash', '-s'],
                       input=script, text=True, capture_output=True)
    if r.returncode:
        raise RuntimeError(f'flat list failed for {url}: {(r.stderr or "")[-300:]}')
    out = []
    for line in (r.stdout or '').splitlines():
        line = line.replace('\\t', '\t')
        if '\t' not in line:
            continue
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        dur = parts[2].strip() if len(parts) > 2 else ''
        try:
            duration = float(dur) if dur not in ('', 'NA', 'None') else None
        except ValueError:
            duration = None
        out.append(dict(id=parts[0].strip(), title=parts[1].strip(),
                        duration=duration,
                        channel=parts[3].strip() if len(parts) > 3 else '',
                        url=(parts[4].strip() if len(parts) > 4 else '') or watch_url(parts[0].strip())))
    return out


def retry(fn, times=3, wait=8, what='op'):
    last = None
    for i in range(times):
        try:
            return fn()
        except Exception as e:
            last = e
            print(f'retry {what} {i+1}/{times}: {type(e).__name__}: {e}'[:300], flush=True)
            time.sleep(wait * (i + 1))
    raise last


def cached_meta(url):
    vid = video_id_from_url(url) or hashlib.sha1(url.encode()).hexdigest()[:16]
    path = os.path.join(META_CACHE, vid + '.json')
    if os.path.exists(path):
        return json.load(open(path))
    meta = retry(lambda: fetch.meta_remote(url), what=f'meta {vid}')
    _atomic_json(path, meta)
    return meta


def title_ok(title):
    if not title:
        return False
    return _SKIP_TITLE.search(title) is None


def duration_ok(dur):
    if dur is None:
        return True
    return 20 * 60 <= float(dur) <= 3.5 * 3600


def looks_like_mix(title, duration=None):
    """Prefer long DJ sets / podcasts; drop obvious single-track videos."""
    if not title_ok(title):
        return False
    if duration is not None and not duration_ok(duration):
        return False
    tl = (title or '').lower()
    keys = ('podcast', 'dj set', 'dj-set', 'live from', 'live set', 'takeover',
            'session', 'mix', 'radioshow', 'radio show')
    if any(k in tl for k in keys) and 'remix' not in tl:
        return True
    if duration is not None and float(duration) >= 30 * 60:
        return True
    return False


def goldilocks_pairs(tracks, mix_id, dj, mix_url, video_id):
    """Same slot / ID / bootleg rules as run_corpus_phase.pairs_from_tracks."""
    items = []
    for t in tracks:
        if isinstance(t, dict):
            items.append((float(t['t'] if 't' in t else t.get('start')), t.get('title') or ''))
        else:
            items.append((float(t[0]), t[1]))
    items.sort(key=lambda x: x[0])
    out = []
    for i in range(len(items) - 1):
        ta, tb = items[i][0], items[i + 1][0]
        a, b = items[i][1], items[i + 1][1]
        slot = tb - ta
        if not (SLOT_LO <= slot <= SLOT_HI):
            continue
        def is_id(s):
            s = (s or '').strip()
            return s == 'ID' or s.endswith(' ID') or s.startswith('ID ') or ' ID ' in f' {s} '
        if is_id(a) or is_id(b):
            continue
        if 'bootleg' in a.lower() or 'bootleg' in b.lower():
            continue
        nxt = items[i + 2][0] if i + 2 < len(items) else tb + 90
        out.append(dict(
            id=f'{mix_id}__{i:02d}', mix_id=mix_id, dj=dj, mix_url=mix_url,
            video_id=video_id, t_a=float(ta), t_b=float(tb), t_next=float(nxt),
            a=dict(title=a, yt=None), b=dict(title=b, yt=None),
        ))
    return out


# ---------- discovery ----------

def discover(max_list=120, max_meta=400, search_n=25, seeds_only=False):
    """Build a queue of tracklisted mixes. Resumable via meta_cache + queue.json."""
    _mkdirs()
    seen = {}
    queue = json.load(open(QUEUE)) if os.path.exists(QUEUE) else dict(mixes=[])
    for m in queue.get('mixes') or []:
        if m.get('video_id'):
            seen[m['video_id']] = m
    candidates = []

    def add_row(row, seed=False):
        vid = row.get('id') or video_id_from_url(row.get('url') or '')
        if not vid or vid in seen or vid in {c.get('id') for c in candidates}:
            return
        if not title_ok(row.get('title') or ''):
            return
        if not duration_ok(row.get('duration')):
            return
        if not seed and row.get('title') not in (None, '', 'seed'):
            if not looks_like_mix(row.get('title'), row.get('duration')):
                return
        candidates.append(dict(id=vid, title=row.get('title'),
                               duration=row.get('duration'),
                               channel=row.get('channel'),
                               url=row.get('url') or watch_url(vid)))

    for url in SEED_VIDEOS:
        vid = video_id_from_url(url)
        add_row(dict(id=vid, title='seed', duration=3600, channel='', url=url), seed=True)

    if not seeds_only:
        for q in SEED_QUERIES:
            try:
                print('search', q, flush=True)
                rows = retry(lambda qq=q: fetch.search_remote(qq, n=search_n), what=f'search {q}')
                for r in rows:
                    dur = r.get('duration')
                    try:
                        duration = float(dur) if dur not in (None, '', 'NA', 'None') else None
                    except (TypeError, ValueError):
                        duration = None
                    add_row(dict(id=r.get('id'), title=r.get('title'), duration=duration,
                                 channel=r.get('channel'), url=watch_url(r.get('id'))))
            except Exception as e:
                print('search failed', q, type(e).__name__, str(e)[:200], flush=True)
            time.sleep(1.0)

        for url in SEED_LISTS:
            try:
                print('list', url, flush=True)
                rows = retry(lambda u=url: ytdlp_flat(u, limit=max_list), what=f'list {url}')
                print(f'  {len(rows)} entries', flush=True)
                # If this is a playlists tab, flatten a few inner playlists.
                for r in rows:
                    title = (r.get('title') or '').lower()
                    href = r.get('url') or ''
                    if 'playlist?list=' in href or href.startswith('PL') or (
                            r.get('id', '').startswith('PL')):
                        if not title_ok(r.get('title') or 'x'):
                            continue
                        try:
                            inner = retry(lambda u=href if href.startswith('http') else
                                          'https://www.youtube.com/playlist?list=' + r['id']:
                                          ytdlp_flat(u, limit=max_list),
                                          what=f'plist {r.get("id")}')
                            for ir in inner:
                                add_row(ir)
                        except Exception as e:
                            print('  inner list fail', r.get('id'), e, flush=True)
                        time.sleep(0.8)
                    else:
                        add_row(r)
            except Exception as e:
                print('list failed', url, type(e).__name__, str(e)[:200], flush=True)
            time.sleep(1.0)


    # Prioritize seeds and "podcast" / "dj set" / "mix" titles.
    def prio(c):
        vid = c['id']
        if any(video_id_from_url(u) == vid for u in SEED_VIDEOS):
            return 0
        t = (c.get('title') or '').lower()
        if 'podcast' in t or 'dj set' in t or 'live from' in t:
            return 1
        if 'mix' in t and 'remix' not in t:
            return 2
        return 3

    candidates = sorted(candidates, key=prio)
    print(f'discover candidates after filters: {len(candidates)}', flush=True)

    mixes = list(queue.get('mixes') or [])
    n_meta = 0
    for c in candidates:
        if n_meta >= max_meta:
            break
        vid = c['id']
        if vid in seen:
            continue
        url = c.get('url') or watch_url(vid)
        try:
            meta = cached_meta(url)
        except Exception as e:
            print('meta fail', vid, type(e).__name__, str(e)[:200], flush=True)
            continue
        n_meta += 1
        title = meta.get('title') or c.get('title') or vid
        if not title_ok(title):
            continue
        if not duration_ok(meta.get('duration')):
            continue
        tracks = fetch.parse_tracklist(meta.get('description') or '', meta.get('chapters'))
        if len(tracks) < 8:
            continue
        if vid in LEGACY_VIDEO_IDS:
            status = 'legacy_skip'
        else:
            status = 'queued'
        mix_id = f"{slug(meta.get('channel') or 'mix', 24)}_{vid}"
        dj = (meta.get('channel') or 'Unknown').strip()
        rec = dict(
            mix_id=mix_id, video_id=vid, url=meta.get('webpage_url') or url,
            title=title, dj=dj, channel=meta.get('channel'),
            duration=meta.get('duration'), n_tracks=len(tracks),
            n_chapters=len(meta.get('chapters') or []),
            tracklist_source='chapters' if (meta.get('chapters') and len(meta['chapters']) >= 8) else 'description',
            status=status, n_goldilocks=None, n_admit=0, n_reject=0,
        )
        # Count goldilocks without resolving sources.
        rec['n_goldilocks'] = len(goldilocks_pairs(tracks, mix_id, dj, rec['url'], vid))
        if rec['n_goldilocks'] <= 0 and status == 'queued':
            rec['status'] = 'no_goldilocks'
        mixes.append(rec)
        seen[vid] = rec
        _atomic_json(QUEUE, dict(mixes=mixes, ts=time.strftime('%Y-%m-%d %H:%M:%S %Z'),
                                 n=len(mixes)))
        print(f"queued {rec['status']:14} {mix_id} tracks={len(tracks)} gold={rec['n_goldilocks']} {title[:70]}",
              flush=True)
        time.sleep(0.4)

    queued = [m for m in mixes if m.get('status') == 'queued']
    gold = sum(m.get('n_goldilocks') or 0 for m in queued)
    out = dict(mixes=mixes, ts=time.strftime('%Y-%m-%d %H:%M:%S %Z'),
               n=len(mixes), n_queued=len(queued), goldilocks_queued=gold)
    _atomic_json(QUEUE, out)
    print(json.dumps(dict(n=out['n'], n_queued=out['n_queued'],
                          goldilocks_queued=gold), indent=2), flush=True)
    return out


# ---------- ingest / gates (isolated) ----------

def load_tracks_for(mix):
    meta = cached_meta(mix['url'])
    return fetch.parse_tracklist(meta.get('description') or '', meta.get('chapters')), meta


def ensure_source_v2(yt):
    dest = os.path.join(LIB, f'{yt}.m4a')
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return dest
    os.makedirs(LIB, exist_ok=True)
    retry(lambda: fetch.ytdlp_remote(f'https://youtu.be/{yt}', dest),
          times=3, wait=12, what=f'source {yt}')
    return dest


def cut_clip_v2(rec, mix_audio):
    dest_dir = os.path.join(CLIPS, rec['mix_id'], rec['id'])
    return extract.extract_one(rec, mix_audio, dest_dir=dest_dir)


def process_pair_v2(c, mix_audio):
    rec = dict(
        id=c['id'], mix_id=c['mix_id'], dj=c['dj'],
        a=dict(title=c['a']['title'], yt=c['a']['yt'], t=c['t_a']),
        b=dict(title=c['b']['title'], yt=c['b']['yt'], t=c['t_b']),
        window=dict(mix_t_a=c['t_a'], mix_t_b=c['t_b'],
                    mix_t_next=c.get('t_next', c['t_b'] + 90),
                    hint_a_played_sec=c['t_b'] - c['t_a']),
    )
    rec = cut_clip_v2(rec, mix_audio)
    sa = ensure_source_v2(rec['a']['yt'])
    sb = ensure_source_v2(rec['b']['yt'])
    gate = version_match.match_pair(rec['pro_clip'], sa, sb, incoming_off=extract.PRE)
    row = dict(
        id=rec['id'], dj=c['dj'], mix_id=c['mix_id'], video_id=c.get('video_id'),
        mix_url=c.get('mix_url'), pair=f"{c['a']['title']} -> {c['b']['title']}",
        t_a=c['t_a'], t_b=c['t_b'],
        a=dict(title=c['a']['title'], yt=c['a']['yt']),
        b=dict(title=c['b']['title'], yt=c['b']['yt']),
        gate=gate, pro_clip=rec['pro_clip'],
        verdict='admit' if gate.get('passed') else 'reject',
        reason='; '.join(gate.get('reasons') or []) or None,
    )
    if gate.get('passed'):
        tk = talkover.check_clip(rec['pro_clip'], sa, sb)
        row['talkover'] = {k: tk.get(k) for k in ('talk_s', 'talk_frac', 'flagged')}
        if tk.get('flagged'):
            row['verdict'] = 'reject'
            row['reason'] = f"dj_talkover {tk.get('talk_s')}s"
            gate['passed'] = False
    if gate.get('passed'):
        blend = _real_blend_paths(rec['pro_clip'], sa, sb)
        row['real_blend'] = blend
        if blend.get('flagged'):
            row['verdict'] = 'reject'
            row['reason'] = 'not_real_blend: ' + (blend.get('reason') or 'flagged')
            gate['passed'] = False
    return row, rec, sa, sb


def _real_blend_paths(pro, sa, sb):
    """real_blend.assess on explicit paths; does not write official caches."""
    import score
    import diagnose_gap as D
    try:
        mix = score._load(pro)
        aligned = []
        for path in (sa, sb):
            loc = D.version_match.locate_in(mix, score._load(path))
            if loc.get('track_t') is None:
                return dict(version=real_blend.VERSION, flagged=True, reason='source_locator_failed')
            y = D.place_source(path, loc['track_t'], loc['mix_t'], len(mix))
            y, _ = D.refine_lag(mix, y)
            aligned.append(y)
        gains, _, times, hop = D.band_gains(mix, *aligned)
        r = real_blend.assess(gains['all']['a'], gains['all']['b'], hop / D.SR, D.BAR_SEC)
        r['gains'] = _curve_summary(gains, times, hop, D)
        return r
    except Exception as e:
        return dict(version=real_blend.VERSION, flagged=True, reason='measurement_failed',
                    error=str(e)[-200:])


def _curve_summary(gains, times, hop, D):
    """Compact rise / tail / per-band numbers for the ranker (no raw audio)."""
    out = {}
    for band in ('all', 'bass', 'drums', 'highs', 'mids'):
        if band not in gains:
            continue
        a = np.asarray(gains[band]['a'], float)
        b = np.asarray(gains[band]['b'], float)
        def db(x):
            return 20.0 * np.log10(np.maximum(x, 1e-8))
        ad, bd = db(a), db(b)
        # Incoming rise: dB / beat over first ~8 bars after b becomes audible.
        loud_b = np.percentile(bd, 90)
        start = int(np.argmax(bd > loud_b - 18))
        end = min(len(bd) - 1, start + max(1, int(round(8 * D.BAR_SEC * D.SR / hop))))
        rise = None
        if end > start + 2:
            rise = float((bd[end] - bd[start]) / max(1e-6, (end - start) * hop / D.SR * 174.0 / 60.0))
        # Outgoing hold: median level for 16 bars after mix-in-ish (start of incoming).
        hold = float(np.median(ad[start:min(len(ad), start + max(1, int(round(16 * D.BAR_SEC * D.SR / hop))))]))
        tail = ad[start:]
        still = np.flatnonzero(tail > hold - 12)
        tail_bars = float(still[-1] * hop / D.SR / D.BAR_SEC) if len(still) else 0.0
        out[band] = dict(rise_db_per_beat=None if rise is None else round(rise, 3),
                         hold_db=round(hold, 2), tail_bars=round(tail_bars, 2),
                         out_p90=round(float(np.percentile(ad, 90)), 2),
                         in_p90=round(float(np.percentile(bd, 90)), 2))
    return out


def bar_from_audio(path, bpm=174.0):
    wav = path + '.__bar.wav'
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in __import__('sys').path:
        __import__('sys').path.insert(0, here)
    from analyze_pro_phases import compute_bar_from_wav
    try:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-ac', '1', '-ar', '44100', wav],
                       check=True, capture_output=True)
        return compute_bar_from_wav(wav, bpm=bpm)
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass


def sections_from_bar(bar):
    labels = S.label_phases(bar)
    spans = S.phase_spans(labels)
    drops = [(int(s), int(e)) for name, s, e in spans if name == 'drop']
    first_drop = drops[0][0] if drops else 0
    brks = [(int(s), int(e)) for name, s, e in spans if name == 'breakdown']
    outro = next((s for name, s, e in spans if name == 'outro'), None)
    intro_end = first_drop
    n = int(bar.get('n') or len(bar.get('drums') or []))
    bass = np.asarray(bar.get('bass') or [], float)
    drums = np.asarray(bar.get('drums') or [], float)

    def mean_band(seg):
        s, e = seg
        e = min(len(bass), e)
        s = max(0, min(s, e))
        if e <= s or len(bass) == 0:
            return None
        return dict(bass=round(float(np.mean(bass[s:e])), 2),
                    drums=round(float(np.mean(drums[s:e])), 2),
                    energy=round(float(np.mean(np.maximum(bass[s:e], drums[s:e]))), 2))

    bass_by = {name: mean_band((s, e)) for name, s, e in spans}
    return dict(
        n_bars=n, intro_end=int(intro_end), drop1=int(first_drop) if drops else None,
        breakdown=int(brks[0][0]) if brks else None,
        drop2=int(drops[1][0]) if len(drops) > 1 else None,
        outro_start=None if outro is None else int(outro),
        music_end=n, drops=drops,
        phases=[{'name': n, 'start': int(s), 'end': int(e)} for n, s, e in spans],
        bass_by_section=bass_by,
        intro_len=int(intro_end),
        n_drops=len(drops),
    )


def extract_features(row, rec, sa, sb):
    """Cue / section / blend / rise-tail / per-track features. JSON only."""
    BAR = S.BAR_SEC
    loc_a = (row.get('gate') or {}).get('a', {}).get('locate') or {}
    loc_b = (row.get('gate') or {}).get('b', {}).get('locate') or {}
    mixin = extract.PRE  # incoming listed start in the clip
    a_sec = None
    b_sec = None
    if loc_a.get('track_t') is not None and loc_a.get('mix_t') is not None:
        a_sec = loc_a['track_t'] + (mixin - loc_a['mix_t'])
    if loc_b.get('track_t') is not None and loc_b.get('mix_t') is not None:
        b_sec = loc_b['track_t'] + (mixin - loc_b['mix_t'])
        # Prefer a locate near mix-in when the global hit is a later drop.
        if loc_b.get('mix_t') is not None and abs(loc_b['mix_t'] - mixin) > 10:
            # keep global only as fallback; still record it
            pass
    bpm_a = ((row.get('gate') or {}).get('a', {}).get('bpm') or {}).get('bpm')
    bpm_b = ((row.get('gate') or {}).get('b', {}).get('bpm') or {}).get('bpm')
    try:
        bar_a = bar_from_audio(sa, bpm=bpm_a or 174.0)
        bar_b = bar_from_audio(sb, bpm=bpm_b or 174.0)
        sec_a = sections_from_bar(bar_a)
        sec_b = sections_from_bar(bar_b)
    except Exception as e:
        sec_a, sec_b = {}, {}
        row_err = f'features_bar: {e}'[:200]
    else:
        row_err = None
    a_bar = None if a_sec is None else a_sec / BAR
    b_bar = None if b_sec is None else b_sec / BAR

    def phase_at(sec, bar):
        if bar is None or not sec.get('phases'):
            return None
        for p in sec['phases']:
            if p['start'] <= bar < p['end']:
                return p['name']
        return sec['phases'][-1]['name'] if sec.get('phases') else None

    feat = dict(
        id=row['id'], mix_id=row['mix_id'], dj=row['dj'], pair=row.get('pair'),
        video_id=row.get('video_id'),
        cue=dict(
            incoming_bar=None if b_bar is None else round(float(b_bar), 2),
            incoming_section=phase_at(sec_b, b_bar),
            outgoing_bar=None if a_bar is None else round(float(a_bar), 2),
            outgoing_section=phase_at(sec_a, a_bar),
            blend_list_s=round(float(row['t_b'] - row['t_a']), 2),
            locate_a=loc_a, locate_b=loc_b,
        ),
        rise_tail=(row.get('real_blend') or {}).get('gains'),
        overlap_bars=(row.get('real_blend') or {}).get('overlap_bars'),
        track_a=dict(sections=sec_a, bpm=bpm_a, yt=row['a']['yt'], title=row['a']['title']),
        track_b=dict(sections=sec_b, bpm=bpm_b, yt=row['b']['yt'], title=row['b']['title']),
        error=row_err,
    )
    # Candidate windows + labels (no engine render required).
    try:
        cands = []
        if sec_a and sec_b:
            import sys
            sys.path.insert(0, paths.SRC2)
            import window_planner as WP
            for c in WP.nominate(sec_a, sec_b, X=16):
                feat_c = dict(type=c['type'], win=list(c['win']),
                              in_drop=c.get('in_drop'), ib_is_start=c.get('ib_is_start'))
                # SNAP_IN / HOLD variants for breakdown_drop
                variants = [dict(feat_c, snap_in=False, snap_in_hold=False)]
                if c['type'] == 'breakdown_drop':
                    variants.append(dict(feat_c, snap_in=True, snap_in_hold=False))
                    variants.append(dict(feat_c, snap_in=True, snap_in_hold=True))
                for v in variants:
                    ib = int(v['win'][3])
                    dbar = None if b_bar is None else abs(ib - b_bar)
                    same = (v['type'] == 'breakdown_drop' and feat['cue']['incoming_section'] == 'drop'
                            and feat['cue']['outgoing_section'] in ('breakdown', 'outro')) or (
                        v['type'] == 'outro_intro' and feat['cue']['incoming_section'] in ('intro', 'build')
                    ) or (
                        v['type'] == 'drop1_end' and feat['cue']['outgoing_section'] in ('drop', 'breakdown')
                        and feat['cue']['incoming_section'] in ('drop', 'intro', 'build')
                    )
                    v['delta_bars'] = None if dbar is None else round(float(dbar), 2)
                    v['section_match'] = bool(
                        feat['cue']['incoming_section'] and
                        _cand_in_section(v, sec_b) == feat['cue']['incoming_section']
                    )
                    # graded relevance for ranking
                    rel = 0
                    if v['section_match']:
                        rel = 1
                    if dbar is not None and dbar <= 8 and v['section_match']:
                        rel = 2
                    if dbar is not None and dbar <= 4 and v['section_match']:
                        rel = 3
                    v['relevance'] = rel
                    cands.append(v)
        feat['candidates'] = cands
    except Exception as e:
        feat['candidates'] = []
        feat['cand_error'] = str(e)[-200:]
    dest = os.path.join(FEATURES, row['id'] + '.json')
    _atomic_json(dest, feat)
    return feat


def _cand_in_section(v, sec_b):
    ib = int(v['win'][3])
    X = int(v['win'][4])
    mid = ib + X / 2.0
    for p in sec_b.get('phases') or []:
        if p['start'] <= mid < p['end']:
            return p['name']
    return None


# ---------- Drive archive ----------

def rclone(*args, check=True):
    cmd = [RCLONE, '--retries', '3', '--low-level-retries', '5'] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f'rclone {" ".join(args[:4])} failed: {(r.stderr or r.stdout)[-400:]}')
    return r


def archive_and_verify(local_path, remote_rel):
    """Copy one file or directory to Drive and verify size."""
    if not os.path.exists(local_path):
        return None
    remote = f'{DRIVE}/{remote_rel}'
    if os.path.isdir(local_path):
        rclone('copy', local_path, remote)
        chk = rclone('check', local_path, remote, '--size-only', check=False)
    else:
        dest_dir = remote.rsplit('/', 1)[0]
        rclone('copy', local_path, dest_dir)
        chk = rclone('check', local_path, dest_dir, '--size-only', check=False)
    if chk.returncode:
        raise RuntimeError(f'Drive verify failed for {remote_rel}: {(chk.stderr or chk.stdout)[-300:]}')
    return remote


def archive_mix(mix, admitted_rows):
    """Archive mix audio, used sources, and accepted clips; then delete local copies."""
    vid = mix['video_id']
    mix_path = os.path.join(MIXES_DIR, vid + '.m4a')
    remotes = {}
    if os.path.exists(mix_path):
        remotes['mix'] = archive_and_verify(mix_path, f"mixes/{mix['mix_id']}/{vid}.m4a")
        os.remove(mix_path)
        print('archived+deleted mix', mix['mix_id'], flush=True)
    used = set()
    for r in admitted_rows:
        if r.get('a', {}).get('yt'):
            used.add(r['a']['yt'])
        if r.get('b', {}).get('yt'):
            used.add(r['b']['yt'])
    for yt in sorted(used):
        src = os.path.join(LIB, yt + '.m4a')
        if os.path.exists(src):
            remotes.setdefault('sources', []).append(archive_and_verify(src, f'sources/{yt}.m4a'))
            os.remove(src)
    clip_root = os.path.join(CLIPS, mix['mix_id'])
    if os.path.isdir(clip_root):
        remotes['clips'] = archive_and_verify(clip_root, f"clips/{mix['mix_id']}")
        shutil.rmtree(clip_root, ignore_errors=True)
    # drop leftover unused sources for this mix
    if os.path.isdir(LIB):
        for n in os.listdir(LIB):
            if n.endswith('.m4a'):
                try:
                    os.remove(os.path.join(LIB, n))
                except OSError:
                    pass
    return remotes


# ---------- mix ingest ----------

def already_ids():
    return {r['id'] for r in load_jsonl(ACCEPTED)} | {r['id'] for r in load_jsonl(REJECTED)}


def ingest_mix(mix, snap):
    if mix.get('video_id') in LEGACY_VIDEO_IDS or mix.get('status') == 'legacy_skip':
        mix['status'] = 'legacy_skip'
        print('skip legacy mix', mix['mix_id'], flush=True)
        return mix
    if mix.get('status') in ('done', 'no_goldilocks'):
        return mix
    tracks, meta = load_tracks_for(mix)
    cands = goldilocks_pairs(tracks, mix['mix_id'], mix['dj'], mix['url'], mix['video_id'])
    mix['n_goldilocks'] = len(cands)
    print(f"=== ingest {mix['mix_id']}: {len(cands)} goldilocks ===", flush=True)
    if not cands:
        mix['status'] = 'no_goldilocks'
        return mix
    dest = os.path.join(MIXES_DIR, mix['video_id'] + '.m4a')
    if not (os.path.exists(dest) and os.path.getsize(dest) > 1_000_000):
        print('download mix', mix['url'], flush=True)
        retry(lambda: fetch.ytdlp_remote(meta.get('webpage_url') or mix['url'], dest),
              times=3, wait=15, what=f"mix {mix['video_id']}")
    have = already_ids()
    admitted_rows = []
    n_admit = n_rej = 0
    for c in cands:
        if c['id'] in have:
            print('skip already logged', c['id'], flush=True)
            continue
        try:
            c['a']['yt'] = admit.resolve_yt(c['a']['title'], c['a'].get('yt'))
            c['b']['yt'] = admit.resolve_yt(c['b']['title'], c['b'].get('yt'))
        except Exception as e:
            row = dict(id=c['id'], dj=c.get('dj'), mix_id=c['mix_id'], video_id=c.get('video_id'),
                       pair=f"{c['a']['title']} -> {c['b']['title']}", t_a=c['t_a'], t_b=c['t_b'],
                       verdict='reject', reason=f'resolve: {e}'[:300])
            append_jsonl(REJECTED, row)
            n_rej += 1
            print('reject', row['id'], row['reason'], flush=True)
            continue
        try:
            row, rec, sa, sb = process_pair_v2(c, dest)
        except Exception as e:
            row = dict(id=c['id'], dj=c.get('dj'), mix_id=c['mix_id'], video_id=c.get('video_id'),
                       pair=f"{c['a']['title']} -> {c['b']['title']}", t_a=c['t_a'], t_b=c['t_b'],
                       verdict='reject', reason=f'error: {e}'[:300],
                       traceback=traceback.format_exc()[-500:])
            append_jsonl(REJECTED, row)
            n_rej += 1
            print('reject', row['id'], row['reason'], flush=True)
            # drop a failed clip dir if present
            shutil.rmtree(os.path.join(CLIPS, c['mix_id'], c['id']), ignore_errors=True)
            continue
        if row['verdict'] == 'admit':
            try:
                feat = extract_features(row, rec, sa, sb)
                row['feature_path'] = os.path.join('features', row['id'] + '.json')
                row['cue'] = feat.get('cue')
            except Exception as e:
                row['feature_error'] = str(e)[:200]
                print('feature fail', row['id'], e, flush=True)
            # strip huge gate arrays; keep locates + bpm
            append_jsonl(ACCEPTED, {k: v for k, v in row.items() if k != 'pro_clip'})
            admitted_rows.append(row)
            n_admit += 1
            print('admit', row['id'], row.get('pair'), flush=True)
        else:
            append_jsonl(REJECTED, {k: v for k, v in row.items() if k != 'pro_clip'})
            n_rej += 1
            print('reject', row['id'], row.get('reason'), flush=True)
            shutil.rmtree(os.path.dirname(row.get('pro_clip') or '/tmp/none'), ignore_errors=True)
        assert_protected(snap, where=row['id'])
    mix['n_admit'] = n_admit
    mix['n_reject'] = n_rej
    mix['status'] = 'done'
    try:
        mix['drive'] = archive_mix(mix, admitted_rows)
        mix['archived'] = True
    except Exception as e:
        mix['archived'] = False
        mix['archive_error'] = str(e)[:300]
        print('ARCHIVE FAIL', mix['mix_id'], e, flush=True)
        # still try to drop the mix file to keep the box lean
        if os.path.exists(dest):
            try:
                os.remove(dest)
            except OSError:
                pass
    assert_protected(snap, where='after '+mix['mix_id'])
    return mix


def ingest_all(limit=None):
    _mkdirs()
    snap = snapshot_protected()
    queue = json.load(open(QUEUE)) if os.path.exists(QUEUE) else dict(mixes=[])
    mixes = queue.get('mixes') or []
    todo = [m for m in mixes if m.get('status') == 'queued']
    if limit:
        todo = todo[:int(limit)]
    print(f'ingest starting {len(todo)} mixes; already accepted={len(load_jsonl(ACCEPTED))}', flush=True)
    done = 0
    for mix in todo:
        try:
            updated = ingest_mix(mix, snap)
        except Exception as e:
            mix['status'] = 'failed'
            mix['error'] = f'{type(e).__name__}: {e}'[:400]
            mix['traceback'] = traceback.format_exc()[-800:]
            updated = mix
            print('FAILED mix', mix.get('mix_id'), mix['error'], flush=True)
        # write back
        for i, m in enumerate(mixes):
            if m.get('video_id') == updated.get('video_id'):
                mixes[i] = updated
                break
        _atomic_json(QUEUE, dict(mixes=mixes, ts=time.strftime('%Y-%m-%d %H:%M:%S %Z'), n=len(mixes)))
        done += 1
        acc, rej = len(load_jsonl(ACCEPTED)), len(load_jsonl(REJECTED))
        save_progress(dict(phase='ingest', accepted=acc, rejected=rej,
                           mixes_done=sum(1 for m in mixes if m.get('status') in ('done', 'failed', 'no_goldilocks')),
                           last=updated.get('mix_id'), last_status=updated.get('status')))
        print(f"progress accepted={acc} rejected={rej} mixes={done}/{len(todo)}", flush=True)
    return dict(accepted=len(load_jsonl(ACCEPTED)), rejected=len(load_jsonl(REJECTED)))


# ---------- split / manifest ----------

def assign_split():
    """Reserve >=20% of mixes (not transitions) as held-out. Fixed seed."""
    acc = load_jsonl(ACCEPTED)
    by_mix = {}
    for r in acc:
        by_mix.setdefault(r['mix_id'], []).append(r['id'])
    mix_ids = sorted(by_mix)
    rng = random.Random(SPLIT_SEED)
    order = list(mix_ids)
    rng.shuffle(order)
    n = len(order)
    n_hold = 0 if n == 0 else max(1, int(np.ceil(HELD_OUT_MIX_FRAC * n)))
    # if only one mix, it stays train until a second mix arrives (can't hold out everything)
    if n < 5:
        n_hold = max(0, n - max(1, n // 2)) if n >= 2 else 0
    hold = set(order[:n_hold])
    train = [m for m in order if m not in hold]
    held = [m for m in order if m in hold]
    # rebalance so held-out is at least 20% when we have enough mixes
    if n >= 5 and len(held) / n < HELD_OUT_MIX_FRAC:
        while len(held) / n < HELD_OUT_MIX_FRAC and train:
            held.append(train.pop())
    split = dict(seed=SPLIT_SEED, by='mix', held_out_frac=HELD_OUT_MIX_FRAC,
                 n_mixes=n, n_train_mixes=len(train), n_heldout_mixes=len(held),
                 train_mixes=train, heldout_mixes=held,
                 n_train_transitions=sum(len(by_mix[m]) for m in train),
                 n_heldout_transitions=sum(len(by_mix[m]) for m in held),
                 legacy_video_ids=sorted(LEGACY_VIDEO_IDS),
                 note='Legacy 33-pair mixes are never in this split; they stay eval-only.')
    _atomic_json(SPLIT, split)
    return split


def counts_by_source():
    acc = load_jsonl(ACCEPTED)
    rej = load_jsonl(REJECTED)
    def bag(rows, key='dj'):
        out = {}
        for r in rows:
            k = r.get(key) or r.get('mix_id') or 'unknown'
            out[k] = out.get(k, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))
    return dict(
        accepted=len(acc), rejected=len(rej),
        accepted_by_dj=bag(acc, 'dj'), rejected_by_dj=bag(rej, 'dj'),
        accepted_by_mix=bag(acc, 'mix_id'), rejected_by_mix=bag(rej, 'mix_id'),
    )


def write_manifest(split=None, model=None):
    queue = json.load(open(QUEUE)) if os.path.exists(QUEUE) else dict(mixes=[])
    split = split or (json.load(open(SPLIT)) if os.path.exists(SPLIT) else None)
    counts = counts_by_source()
    man = dict(
        dataset='corpus_v2',
        created=time.strftime('%Y-%m-%d %H:%M:%S %Z'),
        drive=DRIVE,
        target_accept=TARGET_ACCEPT,
        gates=dict(z_min=version_match.Z_MIN, cc_min=version_match.CC_MIN,
                   bpm=(version_match.BPM_LO, version_match.BPM_HI),
                   talkover_s=talkover.TALK_MIN_S, real_blend_bars=real_blend.MIN_BARS,
                   real_blend_db=real_blend.LEVEL_DB),
        counts=counts,
        split=split,
        mixes=[{k: m.get(k) for k in
                ('mix_id', 'video_id', 'url', 'title', 'dj', 'channel', 'duration',
                 'n_tracks', 'n_goldilocks', 'n_admit', 'n_reject', 'status',
                 'tracklist_source', 'archived', 'drive')}
               for m in (queue.get('mixes') or [])],
        model=model,
        official_33_untouched=True,
    )
    _atomic_json(MANIFEST, man)
    return man


# ---------- ranker (step 2, only at 150+) ----------

def _iter_labeled(split, which):
    mix_set = set(split['train_mixes'] if which == 'train' else split['heldout_mixes'])
    for rec in load_jsonl(ACCEPTED):
        if rec.get('video_id') in LEGACY_VIDEO_IDS:
            continue
        if rec['mix_id'] not in mix_set:
            continue
        fp = os.path.join(FEATURES, rec['id'] + '.json')
        if not os.path.exists(fp):
            continue
        feat = json.load(open(fp))
        cue_sec = (feat.get('cue') or {}).get('incoming_section')
        for i, c in enumerate(feat.get('candidates') or []):
            yield rec, feat, c, cue_sec, i


def _cand_vec(feat, c):
    typ = c.get('type') or ''
    types = ('outro_intro', 'drop1_end', 'breakdown_drop')
    x = [1.0 if typ == t else 0.0 for t in types]
    win = c.get('win') or [None, 0, None, 0, 16]
    x += [float(win[1] or 0), float(win[3] or 0), float(win[4] or 16)]
    x += [1.0 if c.get('snap_in') else 0.0, 1.0 if c.get('snap_in_hold') else 0.0]
    x += [float(c['delta_bars']) if c.get('delta_bars') is not None else 99.0]
    sb = (feat.get('track_b') or {}).get('sections') or {}
    sa = (feat.get('track_a') or {}).get('sections') or {}
    x += [float(sb.get('intro_len') or 0), float(sb.get('n_drops') or 0),
          float(sa.get('n_bars') or 0), float(sb.get('n_bars') or 0)]
    cue = feat.get('cue') or {}
    secs = ('intro', 'build', 'drop', 'breakdown', 'outro')
    x += [1.0 if cue.get('incoming_section') == s else 0.0 for s in secs]
    x += [1.0 if cue.get('outgoing_section') == s else 0.0 for s in secs]
    x += [float(feat.get('overlap_bars') or 0)]
    return x


def train_ranker(split):
    os.makedirs(MODEL_DIR, exist_ok=True)
    rows = list(_iter_labeled(split, 'train'))
    if not rows:
        return dict(trained=False, reason='no_training_rows')
    X = np.asarray([_cand_vec(f, c) for _, f, c, _, _ in rows], float)
    y = np.asarray([int(c.get('relevance') or 0) for _, f, c, _, _ in rows], int)
    groups = []
    # group by transition id for grouped ranking
    qid = [r[0]['id'] for r in rows]
    try:
        import lightgbm as lgb
        # query groups
        order = []
        counts = []
        last = None
        n = 0
        for q in qid:
            if last is None:
                last = q
                n = 1
            elif q == last:
                n += 1
            else:
                counts.append(n)
                last = q
                n = 1
        if last is not None:
            counts.append(n)
        dtrain = lgb.Dataset(X, label=y, group=counts)
        params = dict(objective='lambdarank', metric='ndcg',
                      ndcg_eval_at=[1, 3], learning_rate=0.05,
                      num_leaves=31, min_data_in_leaf=8,
                      verbose=-1, force_col_wise=True)
        booster = lgb.train(params, dtrain, num_boost_round=200)
        model_path = os.path.join(MODEL_DIR, 'ranker_lgbm.txt')
        booster.save_model(model_path)
        kind = 'lightgbm'
        def predict(xs):
            return booster.predict(np.asarray(xs, float))
    except Exception as e:
        print('lightgbm unavailable or failed, sklearn fallback:', e, flush=True)
        from sklearn.ensemble import HistGradientBoostingRegressor
        model = HistGradientBoostingRegressor(max_depth=6, learning_rate=0.08,
                                              max_iter=250, random_state=SPLIT_SEED)
        model.fit(X, y)
        import joblib
        model_path = os.path.join(MODEL_DIR, 'ranker_hgb.joblib')
        joblib.dump(model, model_path)
        kind = 'sklearn_hgb'
        def predict(xs):
            return model.predict(np.asarray(xs, float))
    # held-out cue-section top-1
    hold_ids = []
    top_section = []
    top_rel = []
    for rec, feat, group in _group_hold(split):
        if not group:
            continue
        scores = predict([_cand_vec(feat, c) for c in group])
        best = group[int(np.argmax(scores))]
        hold_ids.append(rec['id'])
        top_section.append(1.0 if best.get('section_match') else 0.0)
        top_rel.append(int(best.get('relevance') or 0) >= 2)
    report = dict(
        trained=True, kind=kind, model_path=model_path,
        n_train_candidates=int(len(y)), n_train_transitions=len(set(qid)),
        n_heldout_transitions=len(hold_ids),
        heldout_top1_section_match=None if not top_section else round(float(np.mean(top_section)), 4),
        heldout_top1_within_8bars=None if not top_rel else round(float(np.mean(top_rel)), 4),
    )
    _atomic_json(os.path.join(MODEL_DIR, 'report.json'), report)
    print('RANKER', json.dumps(report), flush=True)
    return report


def _group_hold(split):
    cur = None
    group = []
    feat = rec = None
    for rec_i, feat_i, c, cue, i in _iter_labeled(split, 'heldout'):
        if cur is None:
            cur, feat, rec, group = rec_i['id'], feat_i, rec_i, [c]
        elif rec_i['id'] == cur:
            group.append(c)
        else:
            yield rec, feat, group
            cur, feat, rec, group = rec_i['id'], feat_i, rec_i, [c]
    if group:
        yield rec, feat, group


def import_legacy_33():
    """Read-only feature snapshot of the official 33, stored separately."""
    rows = json.load(open(os.path.join(paths.RESULTS, 'admitted.json')))
    n = 0
    # rewrite file
    if os.path.exists(LEGACY):
        os.remove(LEGACY)
    for r in rows:
        out = dict(id=r['id'], dj=r.get('dj'), mix_id=r.get('mix_id'), split=r.get('split'),
                   pair=r.get('pair'), a=r.get('a'), b=r.get('b'),
                   t_a=r.get('t_a'), t_b=r.get('t_b'), legacy=True)
        append_jsonl(LEGACY, out)
        n += 1
    return n


def eval_ranker_on_33(report):
    """Placeholder hook: 33-pair scorer eval only after a model exists.

    The flag stays off and rules.json is not changed. A full 33-pair score
    run is started by eval_window-style tooling when LEARNED_RANKER=1 is
    wired; until then we report that this step is pending if the model
    exists but the scorer flag is still default-off.
    """
    return dict(ran=False, reason='flag_default_off', floor=34.05,
                note='Scorer eval is a separate flagged run; defaults unchanged.')


def run_all(discover_first=True, ingest_limit=None, max_meta=400):
    _mkdirs()
    snap = snapshot_protected()
    save_progress(dict(phase='discover', accepted=0, rejected=0))
    if discover_first:
        print('discover seeds first', flush=True)
        discover(max_meta=max_meta, seeds_only=True)
        assert_protected(snap, 'after seed discover')
        save_progress(dict(phase='ingest_seeds', accepted=len(load_jsonl(ACCEPTED)),
                           rejected=len(load_jsonl(REJECTED))))
        ingest_all(limit=ingest_limit)
        print('discover remaining lists and searches', flush=True)
        discover(max_meta=max_meta, seeds_only=False)
    assert_protected(snap, 'after discover')
    save_progress(dict(phase='ingest', accepted=len(load_jsonl(ACCEPTED)),
                       rejected=len(load_jsonl(REJECTED))))
    ingest_all(limit=ingest_limit)
    assert_protected(snap, 'after ingest')
    split = assign_split()
    counts = counts_by_source()
    model = None
    if counts['accepted'] >= TRAIN_MIN:
        print(f"accepted {counts['accepted']} >= {TRAIN_MIN}; training ranker", flush=True)
        save_progress(dict(phase='train', **counts))
        model = train_ranker(split)
        model['scorer_33'] = eval_ranker_on_33(model)
    else:
        print(f"accepted {counts['accepted']} < {TRAIN_MIN}; skipping ranker", flush=True)
    import_legacy_33()
    man = write_manifest(split, model)
    # copy compact json to Drive (no audio here; audio already archived per mix)
    try:
        for name in ('manifest.json', 'queue.json', 'split.json', 'accepted.jsonl',
                     'rejected.jsonl', 'progress.json', 'summary.json', 'legacy_33.jsonl'):
            p = os.path.join(ROOT, name)
            if os.path.exists(p):
                archive_and_verify(p, f'meta/{name}')
        if os.path.isdir(FEATURES):
            archive_and_verify(FEATURES, 'meta/features')
        if os.path.isdir(MODEL_DIR) and os.listdir(MODEL_DIR):
            archive_and_verify(MODEL_DIR, 'meta/models')
    except Exception as e:
        print('meta archive warning', e, flush=True)
    summary = dict(counts=counts, split=split, model=model, drive=DRIVE,
                   ts=time.strftime('%Y-%m-%d %H:%M:%S %Z'),
                   official_protected=snapshot_protected() == snap)
    _atomic_json(SUMMARY, summary)
    save_progress(dict(phase='done', **counts))
    assert_protected(snap, 'final')
    print(json.dumps(summary, indent=2, default=str), flush=True)
    return summary


if __name__ == '__main__':
    import sys
    cmd = sys.argv[1:] or ['all']
    if cmd[0] == 'discover':
        discover()
    elif cmd[0] == 'ingest':
        lim = int(cmd[1]) if len(cmd) > 1 else None
        ingest_all(limit=lim)
    elif cmd[0] == 'split':
        print(json.dumps(assign_split(), indent=2))
    elif cmd[0] == 'manifest':
        print(json.dumps(write_manifest(), indent=2, default=str)[:2000])
    elif cmd[0] == 'train':
        split = json.load(open(SPLIT)) if os.path.exists(SPLIT) else assign_split()
        print(json.dumps(train_ranker(split), indent=2))
    else:
        run_all()
