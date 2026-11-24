#!/usr/bin/env python3
"""Compare snare-lag wander on bars 130-134 in ours vs the pro clip.

Question: is the -93..+91 ms snare xcorr spread real audible looseness,
or estimator noise from sparse half-time snares?
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
import numpy as np
import soundfile as sf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path('/workspace/mixes')
os.chdir(str(ROOT / 'src2'))
sys.path[:0] = [str(ROOT / 'src2'), str(ROOT / 'protrans'), str(ROOT / 'src' / 'eval')]
import breakdown_phase_est as B
import blend_diag as D
import engine as E
import score as S
import control_curves as CC

OUT = Path('/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-23_structbreak_est')
SCR = Path('/workspace/mixes/scratch/rca1123/est_diag')
OUT.mkdir(parents=True, exist_ok=True)
A_ID, B_ID = 'u6cggHmZEAs', 'SqzxwPEa-DI'
PRO = str(ROOT / 'protrans/clips/train/joe_syntax_hospital__13/pro.wav')
SA, SB = f'{ROOT}/lib/{A_ID}.m4a', f'{ROOT}/lib/{B_ID}.m4a'
META = Path('/workspace/mixes/scratch/rca1123/est/rca23est_u6cggHmZEAs_SqzxwPEa-DI_meta.json')
FOCUS = list(range(130, 135))  # the 5 loud bars in the ours render
PASS = 40.0


def stats(xs, label):
    a = np.asarray([v for v in xs if v is not None and np.isfinite(v)], float)
    if len(a) == 0:
        return dict(label=label, n=0)
    return dict(
        label=label, n=int(len(a)),
        median=round(float(np.median(a)), 1),
        mean=round(float(np.mean(a)), 1),
        std=round(float(np.std(a)), 1),
        iqr=round(float(np.percentile(a, 75) - np.percentile(a, 25)), 1),
        min=round(float(np.min(a)), 1),
        max=round(float(np.max(a)), 1),
        max_abs=round(float(np.max(np.abs(a))), 1),
        n_within_40=int(np.sum(np.abs(a) <= PASS)),
        frac_within_40=round(float(np.mean(np.abs(a) <= PASS)), 3),
        values=[round(float(v), 1) for v in a],
    )


def xcorr_detail(ea, eb, k, bs, beat, sr, hop=B.HOP, win_bars=1):
    """Return lag, peak/second ratio, whether prefer_interior moved the pick, raw argmax lag."""
    fr = sr / hop
    L = int(beat / 2 * fr)
    half_ms = beat / 2 * 1000
    i0, i1 = int(k * bs / hop), int((k + win_bars) * bs / hop)
    x, y = ea[i0:i1] - ea[i0:i1].mean(), eb[i0:i1] - eb[i0:i1].mean()
    n = min(len(x), len(y))
    if n < 4 * L:
        return None
    x, y = x[:n], y[:n]
    energy = float(np.sqrt((x**2).mean() * (y**2).mean()) + 1e-18)
    xc = np.array([np.dot(x[max(0, j):n + min(0, j)], y[max(0, -j):n - max(0, j)])
                   for j in range(-L, L + 1)])
    i = int(np.argmax(xc))
    raw_lag = (i - L) * 1000 / fr
    peak = float(xc[i]) or 1e-12
    # second peak at least 20 ms away
    xc2 = xc.copy()
    rad = max(1, int(20 / 1000 * fr))
    xc2[max(0, i-rad):i+rad+1] = 0
    j2 = int(np.argmax(xc2))
    lag2 = (j2 - L) * 1000 / fr
    peak2 = float(xc2[j2]) or 1e-12
    # prefer_interior
    lag = raw_lag
    moved = False
    if abs(lag) >= 0.4 * half_ms * 2:
        best, best_abs = i, abs(lag)
        for j, v in enumerate(xc):
            if v / peak < 0.75:
                continue
            ms = (j - L) * 1000 / fr
            if abs(ms) <= PASS and abs(ms) < best_abs:
                best, best_abs = j, abs(ms)
                moved = True
        i = best
        lag = (i - L) * 1000 / fr
    # snare flux energy in this bar (how sparse?)
    eA = float(np.sqrt((ea[i0:i1]**2).mean() + 1e-18))
    eB = float(np.sqrt((eb[i0:i1]**2).mean() + 1e-18))
    # peak prominence vs bar median flux
    return dict(
        lag=round(float(lag), 1),
        raw_lag=round(float(raw_lag), 1),
        moved=bool(moved),
        peak_ratio=round(float(peak / (peak2 + 1e-18)), 2),
        lag2=round(float(lag2), 1),
        ncc=round(float(peak / (energy * n + 1e-18)), 3),  # roughly normalized
        eA=round(eA, 5), eB=round(eB, 5),
        xc=xc, L=L, fr=fr,
    )


def onset_lags(ea, eb, k, bs, beat, sr, hop=B.HOP, win_ms=80.0):
    """Lag from isolated snare peaks near beats 2 and 4 (and 1 and 3 for completeness)."""
    fr = sr / hop
    rad = win_ms / 1000.0 * fr
    rows = []
    for name, frac in (('1', 0.0), ('2', 0.25), ('3', 0.5), ('4', 0.75)):
        mid = (k + frac) * bs / hop
        i0, i1 = int(round(mid - rad)), int(round(mid + rad)) + 1
        def peak(env):
            if i0 < 0 or i1 > len(env) or i1 - i0 < 4:
                return None, None
            w = env[i0:i1]
            med = float(np.median(w))
            pk = float(w.max())
            if pk < 1e-9 or (med > 0 and pk < B.PROM * med):
                return None, pk
            j = int(np.argmax(w))
            if 0 < j < len(w) - 1:
                a, b, c = float(w[j-1]), float(w[j]), float(w[j+1])
                den = a - 2*b + c
                if den != 0:
                    j = j + 0.5 * (a - c) / den
            ms = (i0 + j - mid) * 1000.0 / fr
            return float(ms), pk
        a, pa = peak(ea)
        b, pb = peak(eb)
        have = a is not None and b is not None
        rows.append(dict(
            beat=name, frac=frac,
            a_ms=None if a is None else round(a, 1),
            b_ms=None if b is None else round(b, 1),
            residual=None if not have else round(a - b, 1),
            pa=None if pa is None else round(float(pa), 5),
            pb=None if pb is None else round(float(pb), 5),
            conf=bool(have),
        ))
    # primary: beats 2 and 4 (backbeat snares)
    back = [r['residual'] for r in rows if r['beat'] in ('2', '4') and r['residual'] is not None]
    return rows, back


def place_source(yp44, src_m4a, st_id, sr=E.SR):
    y22 = S._load(src_m4a) if src_m4a and Path(src_m4a).exists() else S._load(f'st/{st_id}.wav')
    yp22 = S._load(PRO)
    ln = S._deck_line(yp22, CC.bandpow(yp22), S._fine_env(yp22),
                      src_m4a if src_m4a and Path(src_m4a).exists() else f'st/{st_id}.wav')
    if not ln:
        return None, None
    ys, ssr = sf.read(f'st/{st_id}.wav', dtype='float32', always_2d=True)
    assert ssr == sr
    ts = (np.arange(len(yp44)) / sr - ln['a']) / ln['s']
    placed = np.stack([
        np.interp(ts * sr, np.arange(len(ys)), ys[:, ch], left=0, right=0).astype(np.float32)
        for ch in range(ys.shape[1])
    ], 1)
    return placed, ln


def analyze(name, yA, yB, s0, start, end, src0=None):
    """Per-bar snare xcorr + onset lags. start/end are mix bars; s0 is crop origin."""
    sa = B._flux(yA, *B.SNARE_BAND, E.SR)
    sb = B._flux(yB, *B.SNARE_BAND, E.SR)
    rows = []
    for mb in range(int(start), int(end)):
        k = int(mb - s0)
        src = None if src0 is None else int(src0 + (mb - start))
        det = xcorr_detail(sa, sb, k, E.BS, E.BEAT, E.SR)
        on_rows, back = onset_lags(sa, sb, k, E.BS, E.BEAT, E.SR)
        rec = dict(mix_bar=mb, src_bar=src, crop=k)
        if det is None:
            rec.update(lag=None, raw_lag=None, moved=None, peak_ratio=None, ncc=None, eA=None, eB=None)
            xc = None
        else:
            xc = det.pop('xc')
            L, fr = det.pop('L'), det.pop('fr')
            rec.update(det)
        rec['onset_beats'] = on_rows
        rec['onset_backbeat'] = back
        rec['onset_med'] = None if not back else round(float(np.median(back)), 1)
        rows.append((rec, xc, L if det else None, fr if det else None))
    recs = [r for r, *_ in rows]
    xcs = [(r['mix_bar'], xc, L, fr) for r, xc, L, fr in rows]
    return recs, xcs, sa, sb


def main():
    # ---- ours (STRUCT_BREAK render) ----
    M = json.load(open(META))
    s0, yA, yB = D.crop_decks(M, 0)
    t0 = M['trans'][0]
    start, end = int(t0['start_bar']), int(t0['end_bar'])
    print('OURS crop s0', s0, 'blend', start, end, 'yA', yA.shape, flush=True)
    ours_recs, ours_xcs, *_ = analyze('ours', yA, yB, s0, start, end, src0=start)
    # official-style est on loud bars vs all bars
    os.environ['BREAKDOWN_PHASE_EST'] = '1'
    a_id, src = B.outgoing_src_bars(M, 0)
    est_loud = B.measure(yA, yB, s0, start, end, E.BS, E.SR, E.BEAT, a_id=a_id, src_bars=src, force=False)
    # force all bars (no loud filter)
    crop_all = list(range(int(start - s0), int(end - s0)))
    est_all = B.measure(yA, yB, s0, start, end, E.BS, E.SR, E.BEAT,
                        loud=crop_all, a_id=a_id, src_bars=src, force=True)
    print('OURS est loud', {k: est_loud.get(k) for k in ('family','median_ms','n','n_snare','n_kick','ok')},
          'snare', est_loud.get('snare_ms'), flush=True)
    print('OURS est all ', {k: est_all.get(k) for k in ('family','median_ms','n','n_snare','n_kick','ok')}, flush=True)

    # ---- pro ----
    yp44, sr = sf.read(PRO, dtype='float32', always_2d=True)
    assert sr == E.SR
    yAp, lnA = place_source(yp44, SA, A_ID)
    yBp, lnB = place_source(yp44, SB, B_ID)
    gA = json.load(open('st/u6cggHmZEAs.json'))
    downs = np.array(gA['downs'], float)
    t_pro = float(lnA['a'] + lnA['s'] * downs[128])
    t_end = len(yp44) / sr - 0.05
    n_bars = int(np.floor((min(float(lnA['a'] + lnA['s'] * downs[min(160, len(downs)-1)]), t_end) - t_pro) / E.BAR))
    n_bars = max(8, min(32, n_bars))
    i0 = max(0, int(round(t_pro * sr)))
    need = int(round(n_bars * E.BS))
    def crop(y):
        seg = y[i0:i0+need]
        if len(seg) < need:
            seg = np.pad(seg, ((0, need-len(seg)), (0, 0)))
        return seg[:need]
    yAc, yBc = crop(yAp), crop(yBp)
    print('PRO t0', round(t_pro, 3), 'n_bars', n_bars, 'lines', lnA, lnB, flush=True)
    pro_recs, pro_xcs, *_ = analyze('pro', yAc, yBc, 0, 0, n_bars, src0=128)
    # rewrite mix_bar as outgoing source bar for the pro (crop starts at src 128)
    for r in pro_recs:
        r['mix_bar'] = r['src_bar']  # label by outgoing source bar
    src_pro = list(range(128, 128 + n_bars))
    est_pro_all = B.measure(yAc, yBc, 0, 0, n_bars, E.BS, E.SR, E.BEAT,
                            loud=list(range(n_bars)), a_id=A_ID, src_bars=src_pro, force=True)
    # same 5 source bars as ours loud set
    focus_idx = [b - 128 for b in FOCUS if 0 <= b - 128 < n_bars]
    est_pro_focus = B.measure(yAc, yBc, 0, 0, n_bars, E.BS, E.SR, E.BEAT,
                              loud=focus_idx, a_id=A_ID, src_bars=src_pro, force=True)
    print('PRO est all  ', {k: est_pro_all.get(k) for k in ('family','median_ms','n','n_snare','n_kick','ok')}, flush=True)
    print('PRO est 130-134', {k: est_pro_focus.get(k) for k in ('family','median_ms','n','n_snare','n_kick','ok')},
          'snare', est_pro_focus.get('snare_ms'), flush=True)

    def pick(recs, bars):
        m = {r['src_bar']: r for r in recs}
        return [m[b] for b in bars if b in m]

    ours_f = pick(ours_recs, FOCUS)
    pro_f = pick(pro_recs, FOCUS)

    ours_xcorr_f = [r['lag'] for r in ours_f]
    pro_xcorr_f = [r['lag'] for r in pro_f]
    ours_on_f = [v for r in ours_f for v in r['onset_backbeat']]
    pro_on_f = [v for r in pro_f for v in r['onset_backbeat']]
    ours_xcorr_all = [r['lag'] for r in ours_recs if r['lag'] is not None]
    pro_xcorr_all = [r['lag'] for r in pro_recs if r['lag'] is not None]
    ours_on_all = [v for r in ours_recs for v in r['onset_backbeat']]
    pro_on_all = [v for r in pro_recs for v in r['onset_backbeat']]

    report = dict(
        question='Is snare xcorr wander on bars 130-134 real looseness or estimator noise?',
        ours=dict(
            blend=[start, end],
            est_loud= {k: est_loud.get(k) for k in
                       ('family','median_ms','n','n_snare','n_kick','ok','usable','snare_ms','kick_ms','bars')},
            est_all_bars={k: est_all.get(k) for k in
                          ('family','median_ms','n','n_snare','n_kick','ok','usable','snare_ms','kick_ms')},
            xcorr_130_134=stats(ours_xcorr_f, 'ours xcorr 130-134'),
            xcorr_all=stats(ours_xcorr_all, 'ours xcorr all overlap'),
            onset_backbeat_130_134=stats(ours_on_f, 'ours onset 2+4 130-134'),
            onset_backbeat_all=stats(ours_on_all, 'ours onset 2+4 all'),
            focus_rows=ours_f,
        ),
        pro=dict(
            t0=round(t_pro, 3), n_bars=n_bars,
            est_all_bars={k: est_pro_all.get(k) for k in
                          ('family','median_ms','n','n_snare','n_kick','ok','usable','snare_ms','kick_ms')},
            est_130_134={k: est_pro_focus.get(k) for k in
                         ('family','median_ms','n','n_snare','n_kick','ok','usable','snare_ms','kick_ms','bars')},
            xcorr_130_134=stats(pro_xcorr_f, 'pro xcorr 130-134'),
            xcorr_all=stats(pro_xcorr_all, 'pro xcorr all overlap'),
            onset_backbeat_130_134=stats(pro_on_f, 'pro onset 2+4 130-134'),
            onset_backbeat_all=stats(pro_on_all, 'pro onset 2+4 all'),
            focus_rows=pro_f,
        ),
        interior_ok_in_render='False because offset_interior_ms=-171.2 is 1-bar kick+snare (official family), not snare-only',
    )
    # verdict helpers
    def brief(s):
        if s.get('n', 0) == 0:
            return 'n=0'
        return (f"n={s['n']} med={s['median']} std={s['std']} iqr={s['iqr']} "
                f"range=[{s['min']},{s['max']}] max_abs={s['max_abs']} "
                f"frac<=40ms={s['frac_within_40']}")

    print('==== STATS ====', flush=True)
    for group, d in (('OURS', report['ours']), ('PRO', report['pro'])):
        print(group)
        for k in ('xcorr_130_134','xcorr_all','onset_backbeat_130_134','onset_backbeat_all'):
            print(' ', k, brief(d[k]))

    # focus row table
    print('==== FOCUS BARS 130-134 ====', flush=True)
    print(f"{'bar':>4} {'ours_xc':>8} {'pro_xc':>8} {'ours_on':>10} {'pro_on':>10} {'ours_pr':>8} {'pro_pr':>8} {'ours_mv':>7} {'pro_mv':>6}")
    for b, o, p in zip(FOCUS, ours_f, pro_f):
        print(f"{b:4d} {o['lag']:8.1f} {p['lag']:8.1f} "
              f"{str(o['onset_backbeat']):>10} {str(p['onset_backbeat']):>10} "
              f"{o['peak_ratio']:8.2f} {p['peak_ratio']:8.2f} "
              f"{str(o['moved']):>7} {str(p['moved']):>6}")

    # ---- plot ----
    fig = plt.figure(figsize=(11.2, 9.2))
    fig.suptitle('Snare alignment wander: ours vs pro (S.P.Y 130–134 and full overlap)', fontsize=12)

    ax = fig.add_subplot(3, 1, 1)
    ob = [r['src_bar'] for r in ours_recs]
    pb = [r['src_bar'] for r in pro_recs]
    ax.axhspan(-PASS, PASS, color='#c6efce', alpha=0.45, zorder=0, label='±40 ms pass line')
    ax.axhline(0, color='grey', lw=0.7)
    ax.plot(pb, [r['lag'] for r in pro_recs], 'o-', color='#2ca02c', ms=5, label='Pro snare xcorr')
    ax.plot(ob, [r['lag'] for r in ours_recs], 's-', color='#d62728', ms=5, label='Ours snare xcorr')
    ax.axvspan(129.5, 134.5, color='#fff3cd', alpha=0.55, zorder=0)
    ax.set_ylabel('snare xcorr lag (ms, + = A late)')
    ax.set_xlim(126, 161)
    ax.set_ylim(-180, 180)
    ax.legend(loc='upper right', fontsize=8)
    ax.set_title('1-bar isolated-snare xcorr (same estimator). Yellow = bars 130–134')
    ax.grid(axis='y', color='#eee')

    ax = fig.add_subplot(3, 1, 2)
    def xs_ys(recs):
        xs, ys = [], []
        for r in recs:
            for v in r['onset_backbeat']:
                xs.append(r['src_bar'])
                ys.append(v)
        return xs, ys
    px, py = xs_ys(pro_recs)
    ox, oy = xs_ys(ours_recs)
    ax.axhspan(-PASS, PASS, color='#c6efce', alpha=0.45, zorder=0)
    ax.axhline(0, color='grey', lw=0.7)
    ax.axvspan(129.5, 134.5, color='#fff3cd', alpha=0.55, zorder=0)
    ax.scatter(px, py, c='#2ca02c', marker='o', s=28, label='Pro onset lag (beats 2 & 4)', zorder=3)
    ax.scatter(ox, oy, c='#d62728', marker='s', s=28, label='Ours onset lag (beats 2 & 4)', zorder=3)
    # medians per bar
    ax.plot(pb, [r['onset_med'] for r in pro_recs], color='#2ca02c', lw=1, alpha=0.6)
    ax.plot(ob, [r['onset_med'] for r in ours_recs], color='#d62728', lw=1, alpha=0.6)
    ax.set_ylabel('backbeat onset lag (ms)')
    ax.set_xlim(126, 161)
    ax.set_ylim(-180, 180)
    ax.legend(loc='upper right', fontsize=8)
    ax.set_title('Onset-picked snares near beats 2 and 4 (independent of 1-bar xcorr)')
    ax.grid(axis='y', color='#eee')

    ax = fig.add_subplot(3, 1, 3)
    # xcorr curves for the 5 focus bars, ours vs pro
    # recompute from stored xcs — ours_xcs mix_bar is mix bar (=src for ours)
    def find_xc(xcs, mb):
        for b, xc, L, fr in xcs:
            # ours xcs keyed by mix_bar; pro xcs were keyed by crop mix_bar 0..n before we relabeled recs
            if b == mb or b == mb - 128:
                return xc, L, fr
        return None, None, None
    # For pro, analyze() used mix_bar 0..n before we overwrote recs; xcs still have crop bars 0..n
    # For ours, mix_bar is 128..159
    for i, mb in enumerate(FOCUS):
        # ours
        for b, xc, L, fr in ours_xcs:
            if b == mb and xc is not None:
                t = (np.arange(len(xc)) - L) * 1000 / fr
                ax.plot(t, xc / (np.max(np.abs(xc)) + 1e-18) + (len(FOCUS)-1-i)*2.3,
                        color='#d62728', lw=1.2, label='Ours' if i == 0 else None)
                break
        for b, xc, L, fr in pro_xcs:
            if b == (mb - 128) and xc is not None:
                t = (np.arange(len(xc)) - L) * 1000 / fr
                ax.plot(t, xc / (np.max(np.abs(xc)) + 1e-18) + (len(FOCUS)-1-i)*2.3,
                        color='#2ca02c', lw=1.2, ls='--', label='Pro' if i == 0 else None)
                break
        ax.text(-165, (len(FOCUS)-1-i)*2.3 + 0.15, f'bar {mb}', fontsize=8)
    ax.axvline(0, color='grey', lw=0.6)
    ax.axvline(-PASS, color='#7f7f7f', ls=':', lw=0.7)
    ax.axvline(PASS, color='#7f7f7f', ls=':', lw=0.7)
    ax.set_xlim(-180, 180)
    ax.set_xlabel('lag (ms)')
    ax.set_yticks([])
    ax.set_title('Normalized 1-bar snare xcorr on bars 130–134 (solid ours, dashed pro)')
    ax.legend(loc='upper right', fontsize=8)

    fig.tight_layout()
    png = OUT / 'snare_wander_pro_vs_ours.png'
    fig.savefig(png, dpi=120)
    fig.savefig(SCR / png.name, dpi=120)
    plt.close(fig)
    print('PNG', png, flush=True)

    # drop bulky lists already in stats
    out_json = dict(report)
    json.dump(out_json, open(OUT / 'snare_wander_pro_vs_ours.json', 'w'), indent=2, default=str)
    json.dump(out_json, open(SCR / 'snare_wander_pro_vs_ours.json', 'w'), indent=2, default=str)
    print('JSON written', flush=True)


if __name__ == '__main__':
    main()
