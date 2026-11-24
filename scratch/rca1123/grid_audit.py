#!/usr/bin/env python3
"""Isolated audit: is one deck's beat/downbeat grid half a beat off in the js13 overlap?

Compares stored downs to isolated kick (30-150 Hz) and snare (1.5-5 kHz) onset
folds, per structural region, and to the pro clip. Does not change defaults.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
import numpy as np

os.chdir('/workspace/mixes/src2')
sys.path.insert(0, '/workspace/mixes/src2')
sys.path.insert(0, '/workspace/mixes/protrans')
import halfbeat as HB
import sections
import soundfile as sf
import blend_diag as D
import engine as E

OUT = Path('/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-23_structbreak_ride')
A_ID, B_ID = 'u6cggHmZEAs', 'SqzxwPEa-DI'
PRO = '/workspace/mixes/protrans/clips/train/joe_syntax_hospital__13/pro.wav'
OURS = '/workspace/mixes/scratch/rca1123/ride/rca23ride_master.wav'
META = '/workspace/mixes/scratch/rca1123/ride/rca23ride_u6cggHmZEAs_SqzxwPEa-DI_meta.json'
SA = f'/workspace/mixes/lib/{A_ID}.m4a'
SB = f'/workspace/mixes/lib/{B_ID}.m4a'
BEAT_MS = HB.BEAT * 1000
BAR = HB.BAR

REGIONS = {
    A_ID: [
        ('intro', 0, 64),
        ('drop1', 64, 128),
        ('breakdown', 128, 160),
        ('overlap_out', 128, 160),
        ('drop2', 160, 224),
        ('outro', 224, 259),
        ('all_drumish', 64, 224),
    ],
    B_ID: [
        ('intro_pre_ht', 16, 32),
        ('leadin_cue', 32, 48),
        ('halftime_piano', 48, 61),
        ('riser', 61, 64),
        ('overlap_in', 32, 64),
        ('drop1', 64, 128),
        ('breakdown', 128, 160),
        ('drop2', 160, 208),
        ('all', 0, 208),
    ],
}


def load_track(tid):
    g = json.load(open(f'st/{tid}.json'))
    y, sr = sf.read(f'st/{tid}.wav', dtype='float32', always_2d=True)
    assert sr == HB.SR
    return g, y.mean(1)


def region_report(tid, name, b0, b1, g, K, S):
    downs = np.array(g['downs'], float)
    beats = np.array(g['beats'], float)
    mask = np.zeros(len(downs), bool)
    b0i, b1i = max(0, int(b0)), min(len(downs), int(b1))
    if b1i - b0i < 4:
        return dict(name=name, bars=[b0, b1], why='short')
    mask[b0i:b1i] = True
    fK, nK = HB.fold(K, downs, mask)
    fS, nS = HB.fold(S, downs, mask)
    ph = HB.phase_from_folds(fK, fS)
    # peak bins
    def peak_bin(f):
        i = int(np.argmax(f))
        return dict(bin=i, beat=round(i / HB.NB * 4, 3), ms=round(i / HB.NB * BAR * 1000, 1),
                    frac=round(float(f[i] / (f.max() + 1e-12)), 3))
    # energy at beat vs half-beat for kick and snare (bin 0 / 8 / 16 / 24 vs 8-offset: 8=half beat? 
    # NB=64, one beat = 16 bins, half beat = 8 bins)
    def at(f, bins):
        return float(np.mean([f[i % HB.NB] for i in bins]))
    kick_on = at(fK, [0, 16, 32, 48])  # beats 1,2,3,4
    kick_off = at(fK, [8, 24, 40, 56])  # the 'and' of each beat
    kick_1 = at(fK, [0])
    kick_3 = at(fK, [32])
    snare_24 = at(fS, [16, 48])
    snare_13 = at(fS, [0, 32])
    snare_and = at(fS, [8, 24, 40, 56])
    # offbeat ratio on this region only (kick env vs stored beats that fall in the bars)
    bwin = beats[(beats >= downs[b0i] - 1e-6) & (beats < downs[min(len(downs)-1, b1i)] - 1e-6)]
    obr = None
    if len(bwin) >= 8:
        obr = round(HB.offbeat_ratio(K, bwin), 3)
    # deck_phase (template, drum-bars only if we pass all region bars)
    try:
        phase, strength, used = HB.deck_phase(tid, list(range(b0i, b1i)), g)
        dp = dict(phase_beats=round(float(phase), 4), phase_ms=round(float(phase) * BEAT_MS, 1),
                  strength=round(float(strength), 3), n=int(used))
    except Exception as ex:
        dp = dict(error=str(ex)[-120:])
    # is half-beat preferred in this region?
    half_off = bool(nK >= 8 and ph['margin'] >= HB.MARGIN)
    return dict(
        name=name, bars=[b0i, b1i], n_fold=int(nK),
        kick_peak=peak_bin(fK), snare_peak=peak_bin(fS),
        phase=ph, half_off_region=half_off,
        kick_beat_vs_and=round(kick_on / (kick_off + 1e-12), 3),
        kick_1_vs_3=round(kick_1 / (kick_3 + 1e-12), 3),
        snare_24_vs_13=round(snare_24 / (snare_13 + 1e-12), 3),
        snare_24_vs_and=round(snare_24 / (snare_and + 1e-12), 3),
        offbeat_ratio_kick=obr,
        deck_phase=dp,
        kick_on=round(kick_on, 5), kick_off=round(kick_off, 5),
        kick_1=round(kick_1, 5), kick_3=round(kick_3, 5),
        snare_24=round(snare_24, 5), snare_13=round(snare_13, 5),
    )


def xcorr_detail(a, b, bars, bs, beat, hop=64, sr=44100, win_bars=1):
    """For each bar, official-style xcorr plus interior and lag-0 / lag-half strengths."""
    ma, mb = a.mean(1), b.mean(1)
    ea = D._flux(ma, 30, 150) + D._flux(ma, 150, 1500)
    eb = D._flux(mb, 30, 150) + D._flux(mb, 150, 1500)
    # also isolated
    ka, kb = D._flux(ma, 30, 150), D._flux(mb, 30, 150)
    sa, sb = D._flux(ma, 1500, 5000), D._flux(mb, 1500, 5000)
    fr = sr / hop
    L = int(beat / 2 * fr)
    half_ms = beat / 2 * 1000

    def one(ea, eb, k):
        i0, i1 = int(k * bs / hop), int((k + win_bars) * bs / hop)
        x, y = ea[i0:i1] - ea[i0:i1].mean(), eb[i0:i1] - eb[i0:i1].mean()
        n = min(len(x), len(y))
        if n < 4 * L:
            return None
        x, y = x[:n], y[:n]
        xc = np.array([np.dot(x[max(0, j):n + min(0, j)], y[max(0, -j):n - max(0, j)]) for j in range(-L, L + 1)])
        i = int(np.argmax(xc))
        lag = (i - L) * 1000 / fr
        peak = float(xc[i]) or 1e-12
        # lag 0 and lag +- half (edge)
        i0c = L
        i_lo, i_hi = 0, len(xc) - 1
        # best interior within +-40 ms
        interior = None
        for j, v in enumerate(xc):
            ms = (j - L) * 1000 / fr
            if abs(ms) <= 40 and (interior is None or v > interior[0]):
                interior = (float(v), float(ms))
        return dict(
            lag_ms=round(lag, 1), peak=round(peak, 4),
            r0=round(float(xc[i0c]) / abs(peak), 3),
            r_edge=round(max(float(xc[i_lo]), float(xc[i_hi])) / abs(peak), 3),
            interior_ms=None if interior is None else round(interior[1], 1),
            interior_rel=None if interior is None else round(interior[0] / abs(peak), 3),
            near_half=bool(abs(abs(lag) - half_ms) < 40 or abs(lag) >= 0.8 * half_ms),
        )

    out = []
    for k in bars:
        rec = dict(crop_bar=int(k))
        rec['ks'] = one(ea, eb, k)  # kick+snare (official)
        rec['kick'] = one(ka, kb, k)
        rec['snare'] = one(sa, sb, k)
        out.append(rec)
    return out


def main():
    report = dict(beat_ms=BEAT_MS, halfbeat_ms=round(BEAT_MS / 2, 3), margin=HB.MARGIN)
    tracks = {}
    envs = {}
    for tid, name in ((A_ID, 'SPY'), (B_ID, 'Meteorites')):
        g, y = load_track(tid)
        K, S = HB.drum_envs(y)
        envs[tid] = (K, S, g, y)
        downs = np.array(g['downs'], float)
        beats = np.array(g['beats'], float)
        iv = np.diff(beats)
        rec = dict(
            name=name, orig_bpm=g.get('orig_bpm'),
            stored_halfbeat=g.get('halfbeat'),
            n_downs=len(downs), n_beats=len(beats),
            beat_interval_median_ms=round(float(np.median(iv)) * 1000, 4),
            beat_interval_std_ms=round(float(np.std(iv)) * 1000, 4),
            d0=round(float(downs[0]), 6),
            d0_frac_beat=round(float((downs[0] / HB.BEAT) % 1), 4),
            regions=[],
        )
        for nm, b0, b1 in REGIONS[tid]:
            rec['regions'].append(region_report(tid, nm, b0, b1, g, K, S))
        tracks[tid] = rec
        print(f'\n======== {name} {tid} d0={rec["d0"]} frac={rec["d0_frac_beat"]} orig_bpm={rec["orig_bpm"]}')
        print('  stored halfbeat', {k: g.get('halfbeat', {}).get(k) for k in
              ('offbeat_ratio', 'half_off', 'margin', 'whole', 'half', 'applied', 'shift_sec')})
        for r in rec['regions']:
            if r.get('why'):
                print(' ', r['name'], r['why']); continue
            dp = r['deck_phase']
            print(f"  {r['name']:16s} bars {r['bars'][0]:4d}-{r['bars'][1]:3d}  n={r['n_fold']:3d}  "
                  f"whole {r['phase']['whole']:6.2f} half {r['phase']['half']:6.2f} margin {r['phase']['margin']:+6.2f}  "
                  f"half_off={r['half_off_region']}  "
                  f"kick_peak beat {r['kick_peak']['beat']:.2f} ({r['kick_peak']['ms']:.0f}ms)  "
                  f"snare_peak beat {r['snare_peak']['beat']:.2f} ({r['snare_peak']['ms']:.0f}ms)  "
                  f"kick on/and {r['kick_beat_vs_and']}  1vs3 {r['kick_1_vs_3']}  "
                  f"snare 24/13 {r['snare_24_vs_13']}  obr {r['offbeat_ratio_kick']}  "
                  f"phase {dp}")

    # --- rendered overlap + official xcorr anatomy ---
    M = json.load(open(META))
    s0, yA, yB = D.crop_decks(M, 0)
    t = M['trans'][0]
    s, e = int(t['start_bar']), int(t['end_bar'])
    bars = list(range(int(s - s0), int(e - s0)))
    xc = xcorr_detail(yA, yB, bars, E.BS, E.BAR, win_bars=1)
    # also 2-bar official default
    xc2 = xcorr_detail(yA, yB, bars, E.BS, E.BAR, win_bars=2)
    print('\n======== official-style 1-bar xcorr (kick+snare / kick / snare)')
    for rec in xc:
        ks, k, sn = rec['ks'], rec['kick'], rec['snare']
        mb = s0 + rec['crop_bar']
        def fmt(d):
            if not d: return 'None'
            return (f"lag {d['lag_ms']:+6.1f} near_half={d['near_half']} r0={d['r0']} "
                    f"r_edge={d['r_edge']} int {d['interior_ms']}/{d['interior_rel']}")
        print(f"  mix {mb:3d}  KS {fmt(ks)}")
        print(f"           K  {fmt(k)}")
        print(f"           S  {fmt(sn)}")

    def med(kind, rows, key='lag_ms'):
        vs = [r[kind][key] for r in rows if r[kind] and r[kind].get(key) is not None]
        return None if not vs else round(float(np.median(vs)), 1)

    # bars both within 20 dB (what figure uses)
    # approximate from crop faders already applied
    def db(sig, k):
        a, b = int(k * E.BS), int((k + 1) * E.BS)
        return 20 * np.log10(np.sqrt(np.mean(sig[a:b] ** 2) + 1e-18))
    loud = []
    for rec in xc:
        k = rec['crop_bar']
        dA, dB = db(yA, k), db(yB, k)
        rec['dbA'] = round(dA, 1); rec['dbB'] = round(dB, 1)
        rec['both_20'] = abs(dA - dB) <= 20 and max(dA, dB) > -40
        if rec['both_20']:
            loud.append(rec)
    print('\nloud-both-20 bars', [s0 + r['crop_bar'] for r in loud], 'n', len(loud))
    print('median KS loud', med('ks', loud), 'kick', med('kick', loud), 'snare', med('snare', loud))
    print('median KS all', med('ks', xc), 'kick', med('kick', xc), 'snare', med('snare', xc))
    print('median interior KS loud', med('ks', loud, 'interior_ms'), 'kick', med('kick', loud, 'interior_ms'))

    # --- pro vs ours deck lines and drum folds ---
    sys.path.insert(0, '/workspace/mixes/protrans')
    import score as S
    yp = S._load(PRO)
    yo = S._load(OURS)
    yp_a, yo_a, _, _ = S.align_ours_to_pro(yp, yo)
    lock = S.beat_identity(yp, yo, SA, SB)[1]
    print('\n======== beat_identity (source grid phase A vs B)')
    print(json.dumps(lock, indent=2, default=str))

    # locate each source in the pro and measure kick-fold vs THAT placement
    # map: pro_t = a + s * src_t  => src_t = (pro_t - a) / s
    # For a source downbeat src_down, pro time is a + s * src_down
    # Compare kick peaks in the pro around those times vs + half beat
    Fm, em = __import__('importlib').import_module('control_curves') if False else None
    sys.path.insert(0, '/workspace/mixes/src/eval')
    import control_curves as CC
    def deck_line(y, path):
        Fm, em = CC.bandpow(y), S._fine_env(y)
        return S._deck_line(y, Fm, em, path)

    lines = {}
    for label, yclip, src in (('pro_A', yp, SA), ('pro_B', yp, SB), ('ours_A', yo, SA), ('ours_B', yo, SB)):
        ln = deck_line(yclip, src)
        lines[label] = ln
        print(label, ln)

    def hits_vs_grid(yclip, line, g, tag, src_bar0, src_bar1):
        """For source downs in [src_bar0, src_bar1), project into the clip and measure kick/snare at 0 vs +half beat."""
        if not line:
            return dict(tag=tag, why='no line')
        y = yclip.mean(1) if yclip.ndim > 1 else yclip
        K, Sn = HB.drum_envs(y)
        downs = np.array(g['downs'], float)
        fr = HB.SR / HB.HOP
        on_k, off_k, on_s, off_s, n = [], [], [], [], 0
        lags_k = []
        for k in range(src_bar0, min(src_bar1, len(downs))):
            t = line['a'] + line['s'] * downs[k]
            if t < 0.2 or t * HB.SR >= len(y) - HB.SR:
                continue
            def pk(env, t0):
                i = int(t0 * fr); w = int(0.02 * fr)
                if i - w < 0 or i + w >= len(env):
                    return 0.0
                return float(env[i - w:i + w + 1].max())
            on_k.append(pk(K, t)); off_k.append(pk(K, t + HB.BEAT / 2))
            on_s.append(pk(Sn, t)); off_s.append(pk(Sn, t + HB.BEAT / 2))
            # nearest kick peak lag around this downbeat, +- half beat
            i0 = int((t - HB.BEAT / 2) * fr); i1 = int((t + HB.BEAT / 2) * fr)
            if 0 <= i0 < i1 <= len(K):
                w = K[i0:i1]
                if w.max() > 0:
                    j = int(np.argmax(w))
                    lags_k.append((j - (i1 - i0) / 2) * 1000 / fr)
            n += 1
        if n < 4:
            return dict(tag=tag, why='few hits', n=n)
        def ratio(a, b):
            return round(float(np.mean(a) / (np.mean(b) + 1e-12)), 3)
        return dict(
            tag=tag, n=n, line_r=line.get('r'), span=line.get('span'),
            kick_on_vs_half=ratio(on_k, off_k),
            snare_on_vs_half=ratio(on_s, off_s),
            kick_lag_median_ms=round(float(np.median(lags_k)), 1) if lags_k else None,
            kick_lag_abs_median=round(float(np.median(np.abs(lags_k))), 1) if lags_k else None,
            n_kick_lags=len(lags_k),
        )

    gA, gB = envs[A_ID][2], envs[B_ID][2]
    hit_rows = []
    # overlap source bars
    for label, yclip, g, b0, b1, src_line in (
        ('pro A breakdown 128-156', yp, gA, 128, 156, lines['pro_A']),
        ('pro B lead-in 32-64', yp, gB, 32, 64, lines['pro_B']),
        ('pro A drop1 end 112-128', yp, gA, 112, 128, lines['pro_A']),
        ('ours A breakdown 128-156', yo, gA, 128, 156, lines['ours_A']),
        ('ours B lead-in 32-64', yo, gB, 32, 64, lines['ours_B']),
        ('pro B drop 64-96 (if present)', yp, gB, 64, 96, lines['pro_B']),
        ('ours B drop 64-96 (if present)', yo, gB, 64, 96, lines['ours_B']),
    ):
        row = hits_vs_grid(yclip, src_line, g, label, b0, b1)
        hit_rows.append(row)
        print('HITS', row)

    # expected grid phase from d0 and lock
    lock_ms = float(((M['trans'][0].get('blend_lock') or {}).get('blend_lock_ms')) or 0)
    # at mix bar 144 (mid overlap): A src 144, B src 48
    d0A, d0B = float(np.array(gA['downs'])[0]), float(np.array(gB['downs'])[0])
    # source time of downbeat of those bars (without lock)
    def src_down(g, bar):
        return float(np.array(g['downs'])[bar])
    # mix time of a source bar is determined by engine, but phase between grids:
    # without lock, both bar starts are placed on the same mix downbeat, so
    # fractional source-beat phase should be 0 by construction (plus nudge).
    # beat_identity uses unstretched lib m4a via _deck_line. That's the ORIG file,
    # not st/*.wav! orig_bpm differs: SPY 174.999, MET 172.997.
    report.update(
        tracks=tracks,
        xcorr_1bar=xc,
        xcorr_2bar_medians=dict(ks=med('ks', xc2), kick=med('kick', xc2), snare=med('snare', xc2)),
        loud_both_20=[s0 + r['crop_bar'] for r in loud],
        loud_medians=dict(ks=med('ks', loud), kick=med('kick', loud), snare=med('snare', loud),
                          ks_interior=med('ks', loud, 'interior_ms'), kick_interior=med('kick', loud, 'interior_ms')),
        beat_identity=lock,
        deck_lines=lines,
        hits_vs_projected_grid=hit_rows,
        leadin_lock_ms=lock_ms,
        d0=dict(A=d0A, B=d0B),
    )
    outp = OUT / 'grid_audit.json'
    json.dump(report, open(outp, 'w'), indent=2, default=str)
    print('\nWROTE', outp)
    return report

if __name__ == '__main__':
    main()
