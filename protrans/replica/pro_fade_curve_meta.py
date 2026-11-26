#!/usr/bin/env python3
"""Fade curves (fader x EQ lane, per band) of rendered blend metas vs the 33-clip pro median/IQR.
  pro_fade_curve_meta.py <out.png> <label>=<meta.json> [<label>=<meta.json> ...]
Same U grid and lane maths as pro_fade_fit._curve_mae (u=0 B enters, u=1 A gone)."""
import json, os, sys
import numpy as np
H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H)
from pro_fade_curves import OUT, U, BANDS
from pro_fade_fit import _eval_lane


def curves(M):
    t = M['trans'][0]
    s, e = int(round(float(t['start_bar']))), int(round(float(t['end_bar'])))
    dA, dB = M['decks'][0]['auto'], M['decks'][1]['auto']
    bars = np.arange(s, e + 1); sub = np.linspace(0, 1, 16, endpoint=False); uu = np.linspace(0, 1, len(bars))
    out = {'U': U.tolist()}
    for band in BANDS:
        res = {}
        for k, d in (('a', dA), ('b', dB)):
            v = []
            for kb in bars:
                ts = kb + sub
                g = _eval_lane(d.get('gain'), ts) * (_eval_lane(d.get('low'), ts) if band == 'bass' else _eval_lane(d.get('high'), ts) if band == 'highs' else 1.0)
                v.append(float(np.clip(20 * np.log10(np.sqrt(np.mean(g ** 2)) + 1e-9), -30, 4)))
            res[k] = np.interp(U, uu, v).round(2).tolist()
        out[band] = res
    return out, (s, e)


def main():
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    png = sys.argv[1]; items = [a.split('=', 1) for a in sys.argv[2:]]
    rows = list(json.load(open(OUT))['rows'].values())
    ours = [(lab,) + curves(json.load(open(p))) for lab, p in items]
    colors = ['#2b6cb0', '#c53030', '#dd6b20', '#2f855a']
    fig, axs = plt.subplots(2, 4, figsize=(22, 9), sharex=True)
    for j, band in enumerate(BANDS):
        for i, deck in enumerate(('a', 'b')):
            ax = axs[i, j]
            Mx = np.array([r[band][deck] for r in rows]); q25, q50, q75 = np.percentile(Mx, [25, 50, 75], axis=0)
            ax.fill_between(U, q25, q75, color='0.75', alpha=0.6, label=f'pro IQR (n={len(rows)})')
            ax.plot(U, q50, 'k-', lw=2.5, label='pro median')
            for c, (lab, cur, se) in zip(colors, ours):
                mae = np.mean(np.abs(np.array(cur[band][deck]) - q50))
                ax.plot(U, cur[band][deck], lw=2, color=c, label=f'{lab} (bars {se[0]}-{se[1]}, |err| {mae:.1f} dB)')
            ax.set_ylim(-31, 5); ax.grid(alpha=0.3); ax.legend(fontsize=7, loc='lower left')
            ax.set_title(f"{'Outgoing A' if deck == 'a' else 'Incoming B'} - {band}" + (' (<150 Hz)' if band == 'bass' else ' (>4 kHz)' if band == 'highs' else ''))
            if j == 0: ax.set_ylabel('gain vs solo (dB)')
            if i == 1: ax.set_xlabel('blend progress u (0 = B enters, 1 = A gone)')
    fig.suptitle('pola02 fade amount over time vs pro DJs (33 pro clips, median and IQR), fader x EQ, per band', fontsize=14)
    fig.tight_layout(); fig.savefig(png, dpi=100); print('PNG', png)


if __name__ == '__main__':
    main()
