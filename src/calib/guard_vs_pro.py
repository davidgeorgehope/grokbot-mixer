#!/usr/bin/env python3
"""Read-only calibration of bassgap, swapdip, and N1 against pro transitions.

Reuses the same measurements as:
  - src2/bassgap.py (low-end hole vs neighbour median, GAP_DB, >1 bar, source-dip exemption)
  - src/build_qa/test_release_eq_swap.py::test_no_level_dip_at_swap (DIP_DB)
  - src/guardrails.py N1 master level step (ebur128 momentary, N1_db)

Does not change any threshold, test, or render. Prints a table and writes
src/calib/guard_vs_pro_results.json.

Usage (from /workspace/mixes):
  python3 src/calib/guard_vs_pro.py
"""
from __future__ import annotations

import json, os, re, sys, subprocess, datetime
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).resolve().parents[2]
SRC2 = ROOT / 'src2'
PRO = ROOT / 'protrans'
sys.path.insert(0, str(SRC2))
sys.path.insert(0, str(PRO))
sys.path.insert(0, str(ROOT / 'src' / 'tests'))

import bassgap as BG
import score as PS
import diagnose_gap as DG
import version_match as VM

# Production constants (do not edit the tests; these are copies for measurement).
SR = 44100
BPM = 174.0
BAR = 4 * 60 / BPM
GAP_DB = float(BG.GAP_DB)          # 8.0
DIP_DB = 3.0                        # test_release_eq_swap
N1_DB = 3.0                         # guardrails TH['N1_db']
CURRENT = dict(bassgap_db=GAP_DB, swapdip_db=DIP_DB, N1_db=N1_DB)

MIX08_NAME = 'mix08_r11c'
MIX08_WAV = SRC2 / f'{MIX08_NAME}_master.wav'
MIX08_MP3 = SRC2 / f'{MIX08_NAME}.mp3'
MIX08_META = SRC2 / f'{MIX08_NAME}_meta.json'
OUT_JSON = Path(__file__).resolve().parent / 'guard_vs_pro_results.json'

# r11c failing blends, from pytest / guardrails on 2026-11-10 (America/New_York).
FAILING = [
    dict(id='rJuyd8koFAU>kKu3fIOTiHk', a='rJuyd8koFAU', b='kKu3fIOTiHk',
         check='N1', trans=15,
         artist_title='Son & Lauren Walton – Always Be -> Wilkinson – Hypnotic'),
    dict(id='EiZVTuiqo0w>n1dOiesZS1g', a='EiZVTuiqo0w', b='n1dOiesZS1g',
         check='bassgap', trans=18,
         artist_title='Hybrid Minds ft. Catching Cairo – Supernova -> Hybrid Minds ft. Alexa Harley – Solitude'),
    dict(id='NaY3x3GRDF4>sObzaBqaBRQ', a='NaY3x3GRDF4', b='sObzaBqaBRQ',
         check='swapdip', trans=9,
         artist_title='Sub Focus & Metrik – Trip -> Dimension ft. TS Graye – Remedy'),
]


def now_et():
    tz = datetime.timezone(datetime.timedelta(hours=-5), name='America/New_York')
    return datetime.datetime.now(tz).strftime('%Y-%m-%dT%H:%M:%S-05:00')


def percentile(xs, p):
    xs = sorted(float(x) for x in xs if x is not None and np.isfinite(x))
    if not xs:
        return None
    if p <= 0:
        return xs[0]
    if p >= 100:
        return xs[-1]
    i = (len(xs) - 1) * p / 100.0
    lo, hi = int(np.floor(i)), int(np.ceil(i))
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - i) + xs[hi] * (i - lo)


def dist(xs):
    xs = [float(x) for x in xs if x is not None and np.isfinite(x)]
    if not xs:
        return dict(n=0, median=None, p75=None, p90=None, p95=None, max=None)
    return dict(n=len(xs),
                median=round(percentile(xs, 50), 3),
                p75=round(percentile(xs, 75), 3),
                p90=round(percentile(xs, 90), 3),
                p95=round(percentile(xs, 95), 3),
                max=round(max(xs), 3))


def rank_pct(xs, v, higher_worse=True):
    """Percent of corpus milder than v (equal counts as not milder)."""
    xs = [float(x) for x in xs if x is not None and np.isfinite(x)]
    if not xs or v is None or not np.isfinite(v):
        return None
    if higher_worse:
        milder = sum(x < v for x in xs)
    else:
        milder = sum(x > v for x in xs)
    return round(100.0 * milder / len(xs), 1)


# ---------- N1: same as guardrails.py (ffmpeg ebur128 momentary, 100 ms) ----------
def ebur128_M(path):
    o = subprocess.run(
        ['ffmpeg', '-nostats', '-i', str(path), '-af', 'ebur128=peak=true', '-f', 'null', '-'],
        capture_output=True, text=True).stderr
    L = np.array([(float(x), float(m)) for x, m in re.findall(
        r't:\s*([\d.]+)\s+TARGET.*?M:\s*(-?[\d.]+|-inf)',
        o.replace('-inf', '-120'))])
    if L.size == 0:
        return None, None
    return L[:, 0], L[:, 1]


def n1_step(tL, Mo, at):
    """Signed post-pre dB at time `at` seconds. Same windows as guardrails.py."""
    if tL is None or Mo is None or at is None:
        return None
    i = int(np.searchsorted(tL, at))
    pre_w, post_w = Mo[max(0, i - 8):i], Mo[i + 2:i + 10]
    if len(pre_w) < 4 or len(post_w) < 4:
        return None
    return float(np.median(post_w) - np.median(pre_w))


# ---------- swapdip: same formula as test_no_level_dip_at_swap ----------
def _db(x):
    return 10 * np.log10(np.mean(np.asarray(x, float) ** 2) + 1e-12)


def swapdip_at(y, sr, start_s, swap_s, bar=BAR):
    """Full-band dip (lo - ref) in dB around swap. None if the +-3 bar window does not fit.

    y is the summed programme (master / pro clip). Official test uses summed
    rendered decks; on a finished mixdown that is the same signal.
    """
    if start_s is None or swap_s is None:
        return None
    L = int(bar * sr)
    Q = L // 4
    # quarter-bar (beat) dB from blend start, as in the test
    i0 = int(round(start_s * sr))
    # need 3 bars after swap and the blend start as the beat array origin
    need_end = swap_s + 3 * bar
    if i0 < 0 or need_end * sr > len(y) + 1 or swap_s - 3 * bar < start_s - 1e-6:
        # official test skips when c-12 < 0 or c+12 > len(bt)
        # allow start slightly after start_s if we still have 3 bars pre-swap
        pass
    n = int((min(len(y) / sr, max(start_s + 32 * bar, need_end)) - start_s) * sr)
    if n < 12 * Q:
        return None
    seg = y[i0:i0 + n]
    if len(seg) < 12 * Q:
        return None
    nbeat = len(seg) // Q
    bt = np.array([_db(seg[k * Q:(k + 1) * Q]) for k in range(nbeat)])
    c = int(round((swap_s - start_s) / bar * 4))
    if c - 12 < 0 or c + 12 > len(bt):
        return None
    ref = min(np.mean(bt[c - 12:c - 4]), np.mean(bt[c + 4:c + 12]))
    lo = float(min(np.mean(bt[j:j + 2]) for j in range(c - 4, c + 4, 2)))
    return float(lo - ref)


# ---------- bassgap helpers ----------
def depth_series(db):
    """Per-bar depth (neighbour-median minus bar), same neighbour window as BG.gaps."""
    n = len(db)
    out = np.full(n, np.nan)
    for k in range(n):
        nb = [db[j] for j in range(max(0, k - 4), min(n, k + 5)) if abs(j - k) >= 1]
        if not nb or not np.isfinite(db[k]):
            continue
        out[k] = float(np.nanmedian(nb) - db[k])
    return out


def worst_run2_depth(depths, mask=None):
    """Max over adjacent overlap bars of min(depth[i], depth[i+1]). Fail iff this > GAP_DB."""
    best = 0.0
    n = len(depths)
    for k in range(n - 1):
        if mask is not None and not (mask[k] and mask[k + 1]):
            continue
        a, b = depths[k], depths[k + 1]
        if np.isfinite(a) and np.isfinite(b):
            best = max(best, float(min(a, b)))
    return best


def official_gaps_from_db(db, b0, start_bar, end_bar):
    """Same keep-rule as BG.check, without the source-dip exemption."""
    out = []
    for s, L in BG.gaps(db, b0):
        if L <= 1 or s + L <= start_bar or s >= end_bar:
            continue
        # depth of this run
        depths = depth_series(db)
        i0, i1 = s - b0, s - b0 + L
        depth = float(np.nanmax(depths[i0:i1])) if i1 > i0 else None
        out.append(dict(start_bar=int(s), bars=int(L), depth_db=None if depth is None else round(depth, 3)))
    return out


def source_low_dip(src_path, loc, mix_s, n_bars, bar=BAR, gap_db=GAP_DB):
    """True if the aligned source itself dips >= GAP_DB/2 at the mix time (exemption)."""
    if not loc or loc.get('mix_t') is None or loc.get('track_t') is None:
        return False
    if not src_path or not os.path.exists(src_path):
        return False
    try:
        y, sr = _load_audio(src_path)
    except Exception:
        return False
    # source time of mix time t: track_t + (t - mix_t)
    t0 = float(loc['track_t']) + (float(mix_s) - float(loc['mix_t']))
    pad = 4
    t_load = t0 - pad * bar
    if t_load + (n_bars + 2 * pad) * bar <= 0:
        return True  # source not playing — not its gap
    x = y
    if x.ndim > 1:
        x = x.mean(1)
    bs = bar * sr
    # bar_db wants a global bar index; use ofs so bar 0 is t_load
    ofs = t_load * sr
    db = BG.bar_db(x, sr, bs, 0, n_bars + 2 * pad, ofs=ofs)
    i = pad
    L = n_bars
    if i + L > len(db):
        return False
    ref = np.nanmedian(np.r_[db[:i], db[i + L:]])
    if not np.isfinite(ref):
        return False
    return bool(np.nanmin(db[i:i + L]) < ref - gap_db / 2)


def _load_audio(path):
    path = str(path)
    if path.endswith('.wav') or path.endswith('.flac'):
        x, sr = sf.read(path, dtype='float32', always_2d=True)
        return x, sr
    raw = subprocess.run(
        ['ffmpeg', '-v', 'error', '-i', path, '-ac', '2', '-ar', str(SR), '-f', 'f32le', '-'],
        capture_output=True, check=True).stdout
    y = np.frombuffer(raw, np.float32)
    if len(y) % 2:
        y = y[:len(y) - 1]
    return y.reshape(-1, 2), SR


def mono(y):
    return y.mean(1) if getattr(y, 'ndim', 1) > 1 else y


# ---------- pro event times (score.source_gain_events, clip-absolute bars) ----------
def events_extended(out_db, in_db):
    ev = PS.events_from_pair(out_db, in_db)
    o, i = PS._to_bars(out_db), PS._to_bars(in_db)
    n = min(len(o), len(i))
    start = ev.get('bass_swap')
    # incoming first sustained presence, same rule as events_from_pair
    if n:
        def relative(x):
            ref = np.percentile(x, 90)
            return x - ref if ref > -90 else np.full_like(x, -120)
        o, i = relative(o[:n]), relative(i[:n])
        on_o, on_i = o > -12, i > -12
        incoming_start = next((k for k in range(n - 1) if on_i[k:k + 2].all()), None)
        both = np.flatnonzero(on_o & on_i)
        overlap_start = int(both[0]) if len(both) else incoming_start
        overlap_end = int(both[-1]) + 1 if len(both) else ev.get('outgoing_cut')
    else:
        incoming_start = overlap_start = overlap_end = None
    ev = dict(ev)
    ev['incoming_start'] = incoming_start
    ev['overlap_start'] = overlap_start
    ev['overlap_end'] = overlap_end
    return ev


def detect_events(pro_path, src_a, src_b, loc_a=None, loc_b=None):
    """Deck-gain events on the full pro clip. Bars are from clip t=0 at 174 BPM."""
    mix = PS._load(str(pro_path))
    aligned, locs = [], []
    for path, cached in ((src_a, loc_a), (src_b, loc_b)):
        if not path or not os.path.exists(path):
            return None, [None, None]
        loc = None
        if cached and cached.get('mix_t') is not None and cached.get('track_t') is not None:
            loc = dict(mix_t=float(cached['mix_t']), track_t=float(cached['track_t']),
                       z=cached.get('z'), cc=cached.get('cc'), source='cache')
        else:
            src = PS._load(path)
            hit = VM.locate_in(mix, src)
            if hit.get('track_t') is None:
                locs.append(hit)
                return None, locs + [None] * (1 - len(locs))
            loc = dict(hit)
            loc['source'] = 'locate'
        y = DG.place_source(path, loc['track_t'], loc['mix_t'], len(mix))
        y, _ = DG.refine_lag(mix, y)
        aligned.append(y)
        locs.append(loc)
    gains, _, times, _ = DG.band_gains(mix, *aligned)

    def curves(band):
        t = np.arange(len(PS._rms(mix))) * PS.HOP / PS.SR
        return tuple(PS._db(np.interp(t, times, gains[band][deck])) for deck in ('a', 'b'))

    ev = events_extended(*curves('bass'))
    full = events_extended(*curves('all'))
    # bass swap from the bass band; overlap bounds from the full-band gains
    out = dict(bass_swap=ev.get('bass_swap'),
               outgoing_cut=full.get('outgoing_cut'),
               blend_length=full.get('blend_length'),
               incoming_start=full.get('incoming_start'),
               overlap_start=full.get('overlap_start'),
               overlap_end=full.get('overlap_end'))
    return out, locs


def bar_to_s(idx, bar=BAR):
    return None if idx is None else float(idx) * bar


def src_path(yt):
    p = PRO / 'lib' / f'{yt}.m4a'
    return str(p) if p.exists() else None


# ---------- Mix 08 official measurements ----------

def official_deck_swapdips():
    """Same path as test_no_level_dip_at_swap: summed rendered decks, pre-master."""
    import importlib
    src_qa = str(ROOT / 'src' / 'build_qa')
    src_tests = str(ROOT / 'src' / 'tests')
    for p in (src_qa, src_tests):
        if p not in sys.path:
            sys.path.insert(0, p)
    os.environ['MIX_SRC'] = str(SRC2)
    os.environ['MIX_NAME'] = MIX08_NAME
    os.environ['MIX_WAV'] = str(MIX08_WAV)
    import test_release_eq_swap as T
    importlib.reload(T)
    out = {}
    for r in T.blends():
        bt = np.array(r['beats'])
        rec = {}
        for which, sb in (('bass', r['t']['swap_bar']), ('high', r['t'].get('high_bar'))):
            if sb is None:
                rec[which] = None
                continue
            c = int(round((sb - r['s']) * 4))
            if c - 12 < 0 or c + 12 > len(bt):
                rec[which] = None
                continue
            ref = min(np.mean(bt[c - 12:c - 4]), np.mean(bt[c + 4:c + 12]))
            lo = float(min(np.mean(bt[j:j + 2]) for j in range(c - 4, c + 4, 2)))
            rec[which] = float(lo - ref)
        out[(r['t']['a'], r['t']['b'])] = rec
    return out


def measure_mix08():
    meta = json.load(open(MIX08_META))
    bar = float(meta.get('bar_sec') or BAR)
    y, sr = sf.read(str(MIX08_WAV), dtype='float32', always_2d=True)
    ym = mono(y)
    tL, Mo = ebur128_M(MIX08_MP3)
    cwd = os.getcwd()
    try:
        os.chdir(SRC2)
        official = BG.check(meta, str(MIX08_WAV))
    finally:
        os.chdir(cwd)
    print('  official deck-sum swapdip (test_release_eq_swap)...', flush=True)
    deck_dips = official_deck_swapdips()
    rows = []
    for spec in FAILING:
        t = meta['trans'][spec['trans']]
        assert t['a'] == spec['a'] and t['b'] == spec['b'], (t['a'], t['b'], spec)
        s, e, sw = int(t['start_bar']), int(t['end_bar']), float(t['swap_bar'])
        high = t.get('high_bar')
        start_s, end_s, swap_s = s * bar, e * bar, sw * bar
        # bassgap on this blend
        b0, b1 = s - 4, e + 4
        db = BG.bar_db(y, sr, bar * sr, b0, b1)
        depths = depth_series(db)
        mask = np.array([b0 + k >= s and b0 + k < e for k in range(len(db))])
        run2 = worst_run2_depth(depths, mask)
        gaps = official_gaps_from_db(db, b0, s, e)
        # official list for this trans
        off = [g for g in official if g[0] == spec['trans']]
        # swapdip at bass (and high if present) on the master
        dip_bass = swapdip_at(ym, sr, start_s, swap_s, bar)
        dip_high = swapdip_at(ym, sr, start_s, None if high is None else float(high) * bar, bar)
        dips = [d for d in (dip_bass, dip_high) if d is not None]
        worst_dip = min(dips) if dips else None
        # N1 at entry (incoming deck start = blend start) and bass swap
        step_entry = n1_step(tL, Mo, start_s)
        step_swap = n1_step(tL, Mo, swap_s)
        steps = [x for x in (step_entry, step_swap) if x is not None]
        worst_n1 = max(steps, key=lambda x: abs(x)) if steps else None
        row = dict(
            id=spec['id'], check=spec['check'], artist_title=spec['artist_title'],
            trans=spec['trans'], start_bar=s, end_bar=e, swap_bar=sw,
            start_s=round(start_s, 3), swap_s=round(swap_s, 3), end_s=round(end_s, 3),
            bassgap=dict(worst_run2_depth_db=round(run2, 3),
                         official_gaps=[{'trans': g[0], 'mix_bar': g[1], 'bars': g[2]} for g in off],
                         measured_gaps=gaps,
                         fail=bool(off)),
            swapdip=dict(master_dip_db=None if worst_dip is None else round(worst_dip, 3),
                         master_at_bass=None if dip_bass is None else round(dip_bass, 3),
                         master_at_high=None if dip_high is None else round(dip_high, 3),
                         official_deck_at_bass=None if deck_dips.get((spec['a'], spec['b']), {}).get('bass') is None else round(deck_dips[(spec['a'], spec['b'])]['bass'], 3),
                         official_deck_at_high=None if deck_dips.get((spec['a'], spec['b']), {}).get('high') is None else round(deck_dips[(spec['a'], spec['b'])]['high'], 3),
                         dip_db=None,  # filled below: official deck-sum (what the test uses)
                         fail=False),
            N1=dict(step_db=None if worst_n1 is None else round(worst_n1, 3),
                    at_entry=None if step_entry is None else round(step_entry, 3),
                    at_swap=None if step_swap is None else round(step_swap, 3),
                    fail=bool(any(abs(x) > N1_DB for x in steps))),
        )
        od = deck_dips.get((spec['a'], spec['b']), {})
        official_vals = [v for v in (od.get('bass'), od.get('high')) if v is not None]
        official_dip = min(official_vals) if official_vals else None
        # Placement and fail use the official pre-master deck sum (the test).
        # master_* fields are the same formula on the mastered wav (closer to what you hear).
        row['swapdip']['dip_db'] = None if official_dip is None else round(official_dip, 3)
        row['swapdip']['fail'] = bool(official_dip is not None and official_dip < -DIP_DB)
        rows.append(row)
    return rows


# ---------- pro corpus ----------
def load_corpus_index():
    admitted = {r['id']: r for r in json.load(open(PRO / 'results' / 'admitted.json'))}
    phase_rows = {}
    ps = PRO / 'results' / 'phase_stats.json'
    if ps.exists():
        for r in json.load(open(ps)).get('rows') or []:
            phase_rows[r['id']] = r
    clips = []
    for meta_p in sorted((PRO / 'clips').glob('*/*/meta.json')):
        m = json.load(open(meta_p))
        cid = m['id']
        adm = admitted.get(cid)
        phase = phase_rows.get(cid)
        loc_a = loc_b = None
        bpm_a = bpm_b = None
        if adm:
            ga, gb = (adm.get('gate') or {}).get('a') or {}, (adm.get('gate') or {}).get('b') or {}
            loc_a = (ga.get('locate') or None)
            loc_b = (gb.get('locate') or None)
            bpm_a = (ga.get('bpm') or {}).get('bpm')
            bpm_b = (gb.get('bpm') or {}).get('bpm')
        if phase:
            # prefer phase_stats loc when present (same clip)
            if phase.get('loc_a'):
                loc_a = phase['loc_a']
            if phase.get('loc_b'):
                loc_b = phase['loc_b']
        clips.append(dict(
            id=cid, dj=m.get('dj'), split=m.get('split'),
            pair=f"{m['a'].get('title')} -> {m['b'].get('title')}",
            admitted=cid in admitted,
            pro_clip=m['pro_clip'] if os.path.exists(m.get('pro_clip') or '') else str(meta_p.parent / 'pro.wav'),
            yt_a=m['a'].get('yt'), yt_b=m['b'].get('yt'),
            loc_a=loc_a, loc_b=loc_b, bpm_a=bpm_a, bpm_b=bpm_b,
            tracklist_b_s=24.0,
        ))
    return clips


def measure_pro(clip):
    path = clip['pro_clip']
    sa, sb = src_path(clip['yt_a']), src_path(clip['yt_b'])
    y, sr = sf.read(path, dtype='float32', always_2d=True)
    ym = mono(y)
    dur = len(ym) / sr
    tL, Mo = ebur128_M(path)
    ev, locs = detect_events(path, sa, sb, clip.get('loc_a'), clip.get('loc_b'))
    loc_a, loc_b = (locs + [None, None])[:2]
    # If detect_events failed mid-way it may return None locs; keep cache
    if not loc_a:
        loc_a = clip.get('loc_a')
    if not loc_b:
        loc_b = clip.get('loc_b')

    window = 'events'
    if ev and ev.get('overlap_start') is not None and ev.get('overlap_end') is not None and ev['overlap_end'] > ev['overlap_start']:
        start_s = bar_to_s(ev['overlap_start'])
        end_s = bar_to_s(ev['overlap_end'])
        entry_s = bar_to_s(ev.get('incoming_start') if ev.get('incoming_start') is not None else ev['overlap_start'])
        swap_s = bar_to_s(ev.get('bass_swap'))
    else:
        window = 'fallback_tracklist'
        start_s, entry_s, end_s = max(0.0, 24.0 - 16 * BAR), 24.0, min(dur, 24.0 + 24 * BAR)
        swap_s = None
        ev = ev or {}

    # bassgap over the overlap, with +-4 bar padding like BG.check
    b0 = int(np.floor(start_s / BAR)) - 4
    b1 = int(np.ceil(end_s / BAR)) + 4
    b0 = max(0, b0)
    db = BG.bar_db(y, sr, BAR * sr, b0, b1)
    depths = depth_series(db)
    s_bar, e_bar = start_s / BAR, end_s / BAR
    mask = np.array([b0 + k >= s_bar and b0 + k < e_bar for k in range(len(db))])
    run2 = worst_run2_depth(depths, mask)
    gaps = official_gaps_from_db(db, b0, s_bar, e_bar)
    exempt = []
    kept = []
    for g in gaps:
        mix_s = g['start_bar'] * BAR
        dip_a = source_low_dip(sa, loc_a, mix_s, g['bars'])
        dip_b = source_low_dip(sb, loc_b, mix_s, g['bars'])
        rec = dict(g, source_dip_a=dip_a, source_dip_b=dip_b)
        if dip_a and dip_b:
            exempt.append(rec)
        else:
            kept.append(rec)
    bass_fail = bool(kept)

    # The dip formula only needs +-3 bars around the swap. Using a late
    # detected overlap start was skipping clips that have enough audio.
    meas_start = start_s
    if swap_s is not None and swap_s - 3 * BAR >= 0:
        meas_start = min(start_s, swap_s - 3 * BAR) if start_s is not None else swap_s - 3 * BAR
    dip = swapdip_at(ym, sr, meas_start, swap_s)
    swap_fail = bool(dip is not None and dip < -DIP_DB)

    step_entry = n1_step(tL, Mo, entry_s)
    step_swap = n1_step(tL, Mo, swap_s)
    step_listed = n1_step(tL, Mo, clip['tracklist_b_s'])
    steps = [x for x in (step_entry, step_swap) if x is not None]
    worst_n1 = max(steps, key=lambda x: abs(x)) if steps else None
    n1_fail = bool(any(abs(x) > N1_DB for x in steps))

    return dict(
        id=clip['id'], dj=clip['dj'], split=clip['split'], pair=clip['pair'],
        admitted=clip['admitted'], window=window, duration_s=round(dur, 3),
        events={k: ev.get(k) for k in ('bass_swap', 'outgoing_cut', 'blend_length',
                                       'incoming_start', 'overlap_start', 'overlap_end')} if ev else None,
        start_s=None if start_s is None else round(start_s, 3),
        end_s=None if end_s is None else round(end_s, 3),
        entry_s=None if entry_s is None else round(entry_s, 3),
        swap_s=None if swap_s is None else round(swap_s, 3),
        bassgap=dict(worst_run2_depth_db=round(run2, 3),
                     gaps=kept, exempt_gaps=exempt, fail=bass_fail),
        swapdip=dict(dip_db=None if dip is None else round(dip, 3),
                     measured=dip is not None, fail=swap_fail),
        N1=dict(step_db=None if worst_n1 is None else round(worst_n1, 3),
                at_entry=None if step_entry is None else round(step_entry, 3),
                at_swap=None if step_swap is None else round(step_swap, 3),
                at_tracklist_b=None if step_listed is None else round(step_listed, 3),
                measured=bool(steps), fail=n1_fail),
    )


def propose(current, p90, higher_worse=True, unit='dB'):
    """Evidence-based proposal. Not applied. p90 of the worse-direction metric."""
    if p90 is None:
        return dict(current=current, proposed_p90=None, vs_current='n/a',
                    note='no pro measurements')
    # bassgap / N1 abs / swapdip depth: higher is worse, fail if metric > current
    looser = p90 > current + 1e-9 if higher_worse else p90 < current - 1e-9
    tighter = p90 < current - 1e-9 if higher_worse else p90 > current + 1e-9
    vs = 'looser than current' if looser else ('tighter than current' if tighter else 'same as current')
    note = (f'Pro p90 is {p90:.2f} {unit}. Current gate is {current:g} {unit} ({vs}). '
            'Proposal only — not written into any test.')
    return dict(current=current, proposed_p90=round(p90, 3), vs_current=vs, note=note)


def summarize(pro_rows, mix_rows):
    admitted = [r for r in pro_rows if r['admitted']]
    others = [r for r in pro_rows if not r['admitted']]

    def pack(rows, label):
        bg = [r['bassgap']['worst_run2_depth_db'] for r in rows]
        # swapdip: store depth = -dip so higher is worse, and raw dip
        sd_raw = [r['swapdip']['dip_db'] for r in rows if r['swapdip']['measured']]
        sd_depth = [(-x) for x in sd_raw]
        n1_abs = [abs(r['N1']['step_db']) for r in rows if r['N1']['measured'] and r['N1']['step_db'] is not None]
        n_bg, n_sd, n_n1 = len(rows), len(sd_raw), len(n1_abs)
        fail_bg = sum(1 for r in rows if r['bassgap']['fail'])
        fail_sd = sum(1 for r in rows if r['swapdip']['fail'])
        fail_n1 = sum(1 for r in rows if r['N1']['fail'])
        return dict(
            label=label, n=len(rows),
            bassgap=dict(distribution=dist(bg),
                         n_measured=n_bg,
                         n_fail=fail_bg,
                         pct_fail=None if not n_bg else round(100.0 * fail_bg / n_bg, 1),
                         metric='worst_run2_depth_db (max over adjacent overlap bars of min(depth_i, depth_i+1); fail if > GAP_DB and not source-exempt)'),
            swapdip=dict(distribution_dip_db=dist(sd_raw),
                         distribution_depth_db=dist(sd_depth),
                         n_measured=n_sd,
                         n_unmeasured=len(rows) - n_sd,
                         n_fail=fail_sd,
                         pct_fail=None if not n_sd else round(100.0 * fail_sd / n_sd, 1),
                         metric='lo-ref dB at detected bass swap (fail if < -DIP_DB). Unmeasured swaps are not counted as fails.'),
            N1=dict(distribution_abs_step_db=dist(n1_abs),
                    n_measured=n_n1,
                    n_unmeasured=len(rows) - n_n1,
                    n_fail=fail_n1,
                    pct_fail=None if not n_n1 else round(100.0 * fail_n1 / n_n1, 1),
                    metric='max |post-pre| ebur128 M step (dB) at incoming start and bass swap (fail if > N1_db)'),
        )

    adm_s, all_s, oth_s = pack(admitted, 'admitted'), pack(pro_rows, 'all_available'), pack(others, 'other_clips')

    # place mix08 fails in the admitted distribution
    bg_xs = [r['bassgap']['worst_run2_depth_db'] for r in admitted]
    sd_xs = [(-r['swapdip']['dip_db']) for r in admitted if r['swapdip']['measured']]
    n1_xs = [abs(r['N1']['step_db']) for r in admitted if r['N1']['measured'] and r['N1']['step_db'] is not None]

    mix_place = []
    for r in mix_rows:
        item = dict(id=r['id'], check=r['check'], artist_title=r['artist_title'])
        if r['check'] == 'bassgap':
            v = r['bassgap']['worst_run2_depth_db']
            item['value_db'] = v
            item['admitted_percentile'] = rank_pct(bg_xs, v, True)
            item['would_fail_current'] = bool(r['bassgap']['fail'])
        elif r['check'] == 'swapdip':
            v = None if r['swapdip']['dip_db'] is None else -r['swapdip']['dip_db']
            item['value_db'] = r['swapdip']['dip_db']
            item['depth_db'] = None if v is None else round(v, 3)
            item['admitted_percentile'] = rank_pct(sd_xs, v, True)
            item['would_fail_current'] = bool(r['swapdip']['fail'])
        elif r['check'] == 'N1':
            v = None if r['N1']['step_db'] is None else abs(r['N1']['step_db'])
            item['value_db'] = r['N1']['step_db']
            item['abs_step_db'] = None if v is None else round(v, 3)
            item['admitted_percentile'] = rank_pct(n1_xs, v, True)
            item['would_fail_current'] = bool(r['N1']['fail'])
        mix_place.append(item)

    proposals = dict(
        bassgap_db=propose(GAP_DB, (adm_s['bassgap']['distribution'] or {}).get('p90'), True, 'dB'),
        swapdip_db=propose(DIP_DB, (adm_s['swapdip']['distribution_depth_db'] or {}).get('p90'), True, 'dB'),
        N1_db=propose(N1_DB, (adm_s['N1']['distribution_abs_step_db'] or {}).get('p90'), True, 'dB'),
        note=('Proposals are the admitted-set p90 of each worse-direction metric. '
              'They are not applied. Standing rule: do not loosen thresholds by hand, '
              'and do not lower DROP_FRAC or change the structure test. '
              'Previous energy-drop calibration (docs/PRO_CALIBRATION_2026-11-07.md) used p95; p95 is reported alongside p90 for comparison.'),
    )
    return dict(admitted=adm_s, all_available=all_s, other_clips=oth_s,
                mix08_r11c_in_admitted_distribution=mix_place,
                proposed_thresholds=proposals)


def print_table(summary, mix_rows, pro_rows):
    def fmt(v, nd=2):
        return 'n/a' if v is None else f'{v:.{nd}f}'

    print('\n=== Current thresholds (unchanged) ===')
    print(f"  bassgap  GAP_DB={GAP_DB:g} dB  (fail if a 2+ bar run is deeper, unless both sources dip)")
    print(f"  swapdip  DIP_DB={DIP_DB:g} dB  (fail if lo-ref < -DIP_DB)")
    print(f"  N1       N1_db={N1_DB:g} dB   (fail if |post-pre| at entry or bass swap > N1_db)")

    for key, title in (('admitted', 'Admitted pro transitions'),
                       ('all_available', 'All available pro clips (admitted + others)'),
                       ('other_clips', 'Other available clips (not in the 33 admitted)')):
        s = summary[key]
        print(f"\n=== {title}  n={s['n']} ===")
        for m in ('bassgap', 'swapdip', 'N1'):
            block = s[m]
            d = block.get('distribution') or block.get('distribution_depth_db') or block.get('distribution_abs_step_db')
            print(f"  {m:8}  measured={block.get('n_measured')}  fail={block.get('n_fail')} ({fmt(block.get('pct_fail'),1)}%)"
                  + (f"  unmeasured={block['n_unmeasured']}" if 'n_unmeasured' in block else ''))
            if d:
                print(f"           median={fmt(d['median'])}  p75={fmt(d['p75'])}  p90={fmt(d['p90'])}  p95={fmt(d['p95'])}  max={fmt(d['max'])}")

    print('\n=== Mix 08 r11c failing blends vs admitted p90 ===')
    for r, p in zip(mix_rows, summary['mix08_r11c_in_admitted_distribution']):
        print(f"  {r['check']:8}  {r['artist_title']}")
        print(f"           value={p.get('value_db')}  admitted_percentile_worse_than={p.get('admitted_percentile')}%  fail_current={p.get('would_fail_current')}")

    print('\n=== Proposed thresholds (NOT applied) ===')
    pr = summary['proposed_thresholds']
    for k in ('bassgap_db', 'swapdip_db', 'N1_db'):
        b = pr[k]
        print(f"  {k:12}  current={b['current']}  proposed_p90={b['proposed_p90']}  ({b['vs_current']})")
    print('  ' + pr['note'])


def main():
    print('Measuring Mix 08 r11c failing blends...', flush=True)
    mix_rows = measure_mix08()
    for r in mix_rows:
        print(f"  {r['check']} {r['id']} bassgap={r['bassgap']} swapdip={r['swapdip']} N1={r['N1']}", flush=True)

    clips = load_corpus_index()
    print(f"Measuring {len(clips)} pro clips "
          f"({sum(c['admitted'] for c in clips)} admitted)...", flush=True)
    pro_rows = []
    for i, c in enumerate(clips, 1):
        print(f"  [{i}/{len(clips)}] {c['id']} admitted={c['admitted']}", flush=True)
        try:
            pro_rows.append(measure_pro(c))
        except Exception as e:
            print(f"    ERROR {type(e).__name__}: {e}", flush=True)
            pro_rows.append(dict(
                id=c['id'], dj=c['dj'], split=c['split'], pair=c['pair'],
                admitted=c['admitted'], error=f'{type(e).__name__}: {e}',
                bassgap=dict(worst_run2_depth_db=None, gaps=[], exempt_gaps=[], fail=False),
                swapdip=dict(dip_db=None, measured=False, fail=False),
                N1=dict(step_db=None, at_entry=None, at_swap=None, at_tracklist_b=None,
                        measured=False, fail=False),
            ))

    ok = [r for r in pro_rows if 'error' not in r]
    summary = summarize(ok, mix_rows)
    # keep errors in the row dump
    out = dict(
        generated=now_et(),
        timezone='America/New_York',
        read_only=True,
        applied=False,
        mix=MIX08_NAME,
        current_thresholds=CURRENT,
        method=dict(
            bassgap='src2/bassgap.py bar_db + gaps (neighbour median of +-4 bars, GAP_DB, L>1 inside overlap). Source-dip exemption uses aligned studio tracks when locate is available (same GAP_DB/2 rule as bassgap.src_dip). Continuous metric: worst adjacent-pair depth.',
            swapdip='test_release_eq_swap.test_no_level_dip_at_swap: lo-ref of half-bar full-band dB, +-1 bar around swap vs quieter of the 2 bars before/after. Mix 08 fail/placement uses official pre-master summed rendered decks (the test); master_* is the same formula on the mastered wav. Pro clips are released mixdowns (no separate decks) with swap time from score.source_gain_events; the measurement window origin is swapped back 3 bars when the clip has audio (the formula only needs +-3 bars). High-swap is measured on Mix 08 only.',
            N1='guardrails.py master level-step branch only (not the 10 ms grid branch): ffmpeg ebur128 momentary, median of 8 frames before vs 8 frames after (skip 2) at incoming start and bass swap. Mix 08 incoming start is B start_bar (blend start). Pro incoming start is first sustained incoming presence from full-band deck gains.',
            corpus='33 admitted in protrans/results/admitted.json, plus any other extracted clips under protrans/clips (64 s, listed incoming at 24 s).',
        ),
        summary=summary,
        mix08_r11c=mix_rows,
        pro_rows=pro_rows,
    )
    json.dump(out, open(OUT_JSON, 'w'), indent=2)
    print_table(summary, mix_rows, pro_rows)
    print(f'\nWrote {OUT_JSON}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
