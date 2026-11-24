#!/usr/bin/env python3
"""Pro vs ours: where do kick/snare hits sit relative to each source grid in the overlap."""
import json, os, sys
from pathlib import Path
import numpy as np
import soundfile as sf

os.chdir('/workspace/mixes/src2')
sys.path[:0] = ['/workspace/mixes/src2', '/workspace/mixes/protrans', '/workspace/mixes/src/eval']
import halfbeat as HB
import score as S
import control_curves as CC
import blend_diag as D
import engine as E

A_ID, B_ID = 'u6cggHmZEAs', 'SqzxwPEa-DI'
PRO = '/workspace/mixes/protrans/clips/train/joe_syntax_hospital__13/pro.wav'
OURS = '/workspace/mixes/scratch/rca1123/ride/rca23ride_master.wav'
META = '/workspace/mixes/scratch/rca1123/ride/rca23ride_u6cggHmZEAs_SqzxwPEa-DI_meta.json'
SA, SB = f'/workspace/mixes/lib/{A_ID}.m4a', f'/workspace/mixes/lib/{B_ID}.m4a'
OUT = Path('/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-23_structbreak_ride')
BEAT_MS = HB.BEAT * 1000


def line_of(y, path):
    Fm, em = CC.bandpow(y), S._fine_env(y)
    return S._deck_line(y, Fm, em, path)


def band_env(y, lo, hi, hop=HB.HOP):
    return HB._flux(y if y.ndim == 1 else y.mean(1), lo, hi, HB.SR, hop)


def nearest_peak_ms(env, t, sr=HB.SR, hop=HB.HOP, win=HB.BEAT / 2):
    fr = sr / hop
    i0, i1 = int((t - win) * fr), int((t + win) * fr)
    if i0 < 0 or i1 > len(env) or i1 - i0 < 8:
        return None, None
    w = env[i0:i1]
    if w.max() <= 1e-12:
        return None, 0.0
    j = int(np.argmax(w))
    if 0 < j < len(w) - 1:
        a, b, c = float(w[j - 1]), float(w[j]), float(w[j + 1])
        den = a - 2 * b + c
        if den != 0:
            j = j + 0.5 * (a - c) / den
    ms = (i0 + j - t * fr) * 1000 / fr
    # prominence
    med = float(np.median(w))
    prom = float(w.max() / (med + 1e-12))
    return float(ms), prom


def per_bar(yclip, line, downs, env, b0, b1, label):
    rows = []
    if not line:
        return rows
    for k in range(b0, b1):
        t = line['a'] + line['s'] * float(downs[k])
        if t < 0.15 or t > len(yclip) / HB.SR - 0.15:
            continue
        ms, prom = nearest_peak_ms(env, t)
        rows.append(dict(src_bar=k, t=round(t, 3), lag_ms=None if ms is None else round(ms, 1),
                         prom=None if prom is None else round(prom, 2), label=label))
    return rows


def summarize(rows, prom_min=1.8, ok=80):
    conf = [r for r in rows if r['lag_ms'] is not None and (r['prom'] or 0) >= prom_min and abs(r['lag_ms']) <= ok]
    near_half = [r for r in rows if r['lag_ms'] is not None and (r['prom'] or 0) >= prom_min
                 and abs(abs(r['lag_ms']) - BEAT_MS / 2) <= 40]
    allp = [r for r in rows if r['lag_ms'] is not None and (r['prom'] or 0) >= prom_min]
    def med(xs):
        return None if not xs else round(float(np.median(xs)), 1)
    return dict(
        n=len(rows), n_conf_onbeat=len(conf), n_conf_near_half=len(near_half), n_strong=len(allp),
        onbeat_med=med([r['lag_ms'] for r in conf]),
        strong_med=med([r['lag_ms'] for r in allp]),
        strong_abs_med=med([abs(r['lag_ms']) for r in allp]),
        near_half_bars=[r['src_bar'] for r in near_half],
        onbeat_bars=[r['src_bar'] for r in conf],
    )


def xcorr_bars(yA, yB, s0, s, e, both20=None):
    bars = list(range(int(s - s0), int(e - s0)))
    # official uses BEAT (one beat), not BAR
    offs1 = D.bar_offsets(yA, yB, bars, E.BS, E.BEAT, win_bars=1, prefer_interior=False)
    offs1i = D.bar_offsets(yA, yB, bars, E.BS, E.BEAT, win_bars=1, prefer_interior=True)
    kick_off = D.bar_offsets  # will custom below
    # kick-only / snare-only by temporarily... just compute with flux replacement via a small local
    def offsets(band):
        # monkey by copying logic
        from scipy.signal import butter, sosfiltfilt
        hop = 64; sr = 44100; beat = E.BEAT; bs = E.BS; win_bars = 1
        ma, mb = yA.mean(1), yB.mean(1)
        def fl(m, lo, hi):
            sos = butter(4, [lo, hi], 'band', fs=sr, output='sos')
            z = sosfiltfilt(sos, m)
            n = len(z) // hop
            e = np.sqrt((z[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
            return np.maximum(np.diff(e, prepend=e[:1]), 0.0)
        if band == 'kick':
            ea, eb = fl(ma, 30, 150), fl(mb, 30, 150)
        else:
            ea, eb = fl(ma, 1500, 5000), fl(mb, 1500, 5000)
        fr = sr / hop; L = int(beat / 2 * fr); out = []
        for k in bars:
            i0, i1 = int(k * bs / hop), int((k + win_bars) * bs / hop)
            x, y = ea[i0:i1] - ea[i0:i1].mean(), eb[i0:i1] - eb[i0:i1].mean()
            n = min(len(x), len(y))
            if n < 4 * L:
                out.append(np.nan); continue
            x, y = x[:n], y[:n]
            xc = np.array([np.dot(x[max(0, j):n + min(0, j)], y[max(0, -j):n - max(0, j)]) for j in range(-L, L + 1)])
            i = int(np.argmax(xc)); lag = (i - L) * 1000 / fr
            peak = float(xc[i]) or 1e-12
            # interior
            inter = None
            for j, v in enumerate(xc):
                ms = (j - L) * 1000 / fr
                if abs(ms) <= 40 and (inter is None or v > inter[0]):
                    inter = (v, ms)
            out.append(dict(mix=s0 + k, lag=round(lag, 1), near_half=bool(abs(abs(lag) - BEAT_MS / 2) < 40),
                            interior=None if inter is None else round(inter[1], 1),
                            interior_rel=None if inter is None else round(inter[0] / abs(peak), 3)))
        return out

    ks, k, sn = offsets('kick'), None, offsets('snare')
    # reuse offsets for kick already; do ks via official arrays
    rows = []
    for i, kbar in enumerate(bars):
        rows.append(dict(
            mix=s0 + kbar,
            ks_lag=None if not np.isfinite(offs1[i]) else round(float(offs1[i]), 1),
            ks_interior=None if not np.isfinite(offs1i[i]) else round(float(offs1i[i]), 1),
            kick=ks[i],
            snare=sn[i],
        ))
    return rows, offs1, offs1i


def main():
    yp, yo = S._load(PRO), S._load(OURS)
    yp_a, yo_a, lag, sc = S.align_ours_to_pro(yp, yo)
    print('align ours->pro lag_ms', lag, 'scorepeak', sc)
    # beat identity on aligned clips (same as score)
    lock_raw = S.beat_identity(yp, yo, SA, SB)[1]
    lock_al = S.beat_identity(yp_a, yo_a, SA, SB)[1]
    print('lock unaligned', json.dumps(lock_raw, default=str))
    print('lock aligned  ', json.dumps(lock_al, default=str))

    lines = {
        'pro_A': line_of(yp, SA), 'pro_B': line_of(yp, SB),
        'ours_A': line_of(yo, SA), 'ours_B': line_of(yo, SB),
        'proA_al': line_of(yp_a, SA), 'oursA_al': line_of(yo_a, SA),
        'proB_al': line_of(yp_a, SB), 'oursB_al': line_of(yo_a, SB),
    }
    for k, v in lines.items():
        print('LINE', k, v)

    gA = json.load(open('st/u6cggHmZEAs.json'))
    gB = json.load(open('st/SqzxwPEa-DI.json'))
    dA, dB = np.array(gA['downs'], float), np.array(gB['downs'], float)

    report = dict(align=dict(lag=lag, peak=sc), lock_raw=lock_raw, lock_aligned=lock_al, lines=lines)

    # Kick and snare envs of pro and ours clips
    packs = {}
    for tag, y in ('pro', yp), ('ours', yo), ('pro_al', yp_a), ('ours_al', yo_a):
        ym = y.mean(1) if y.ndim > 1 else y
        packs[tag] = dict(y=y, k=band_env(ym, 30, 150), s=band_env(ym, 1500, 5000))

    blocks = [
        ('pro', 'A', 'pro_A', dA, 112, 128, 'SPY drop1 tail'),
        ('pro', 'A', 'pro_A', dA, 128, 156, 'SPY breakdown in pro'),
        ('pro', 'B', 'pro_B', dB, 28, 48, 'MET lead-in in pro'),
        ('pro', 'B', 'pro_B', dB, 48, 64, 'MET piano in pro'),
        ('ours', 'A', 'ours_A', dA, 128, 156, 'SPY breakdown in ours'),
        ('ours', 'B', 'ours_B', dB, 28, 48, 'MET lead-in in ours'),
        ('ours', 'B', 'ours_B', dB, 48, 64, 'MET piano in ours'),
    ]
    rows_out = []
    for clip, deck, lnk, downs, b0, b1, label in blocks:
        for band, env in ('kick', packs[clip]['k']), ('snare', packs[clip]['s']):
            rows = per_bar(packs[clip]['y'], lines[lnk], downs, env, b0, b1, f'{label} {band}')
            sm = summarize(rows)
            rec = dict(label=label, clip=clip, deck=deck, band=band, bars=[b0, b1], summary=sm, rows=rows)
            rows_out.append(rec)
            print(f'{label:28s} {band:5s}  {sm}')

    # xcorr anatomy on our rendered decks
    M = json.load(open(META))
    s0, yA, yB = D.crop_decks(M, 0)
    t = M['trans'][0]
    xc_rows, offs1, offs1i = xcorr_bars(yA, yB, s0, t['start_bar'], t['end_bar'])
    print('\n======== 1-bar xcorr (fixed BEAT window)')
    for r in xc_rows:
        k = r['kick']; s = r['snare']
        print(f"  mix {r['mix']:3d}  KS {r['ks_lag']} int {r['ks_interior']}  "
              f"K {k.get('lag') if isinstance(k,dict) else k} int {k.get('interior') if isinstance(k,dict) else None}  "
              f"S {s.get('lag') if isinstance(s,dict) else s} int {s.get('interior') if isinstance(s,dict) else None}")

    # official loud-bar set
    from engine import BS, BAR, BEAT, PRE
    nbars = int(round(len(yA) / BS))
    allA, allB = D.band_bar_db(yA, nbars, BS), D.band_bar_db(yB, nbars, BS)
    ref = max(np.median(allA[:8]), np.median(allB[-8:]))
    s, e = int(t['start_bar']), int(t['end_bar'])
    bl = [k for k in range(int(s - s0), int(e - s0)) if allA[k] > ref - 20 and allB[k] > ref - 20]
    print('loud bars mix', [s0 + k for k in bl])
    print('official median', None if not bl else round(float(np.nanmedian(D.bar_offsets(yA, yB, bl, BS, BEAT, win_bars=2))), 1))
    print('1bar median loud', None if not bl else round(float(np.nanmedian(D.bar_offsets(yA, yB, bl, BS, BEAT, win_bars=1))), 1))
    print('1bar interior loud', None if not bl else round(float(np.nanmedian(D.bar_offsets(yA, yB, bl, BS, BEAT, win_bars=1, prefer_interior=True))), 1))

    report['hits'] = rows_out
    report['xcorr'] = xc_rows
    report['loud_mix_bars'] = [s0 + k for k in bl]
    json.dump(report, open(OUT / 'grid_audit_pro.json', 'w'), indent=2, default=str)
    print('WROTE', OUT / 'grid_audit_pro.json')

if __name__ == '__main__':
    main()
