#!/usr/bin/env python3
"""2026-11-19: one PNG per pair: outgoing and incoming timelines (per-bar level, strong snare hits per bar), drops shaded, slowdown /
breakdown sections (slowdown.py) hatched, and the pro window vs our windows on both tracks. usage: pro_vs_ours_png.py out.png ya yb pro_json ours_json
pro_json: {"A": [a0, a1], "B": [b0, b1], "swapA": x}   ours_json: {"label": {"A": [a0, a1], "B": [b0, b1]}, ...}"""
import sys, json, numpy as np, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.path.insert(0, '/workspace/mixes/protrans/replica/halftime'); import slowdown as SD
SRC2 = '/workspace/mixes/src2'
def main(out, ya, yb, pro, ours, titles=('outgoing', 'incoming')):
    fig, ax = plt.subplots(2, 1, figsize=(13, 6.5)); cols = ['tab:red', 'tab:purple', 'tab:brown']
    for i, (yt, key, ttl) in enumerate(((ya, 'A', titles[0]), (yb, 'B', titles[1]))):
        P = SD.profile(yt); lv = json.load(open(f'{SRC2}/st/{yt}.json'))['bar']['all']; sec = json.load(open(f'{SRC2}/st/{yt}.sections.json'))
        a = ax[i]; a.plot(lv, color='k', lw=1, label='level (dB)'); a.set_ylabel('dB'); a.set_xlim(0, len(lv))
        for k, (x, y) in enumerate(sec.get('drops') or []): a.axvspan(x, y, color='orange', alpha=0.18, label='drop' if k == 0 else None)
        for k, (x, y) in enumerate(P['sections']): a.axvspan(x, y, facecolor='none', edgecolor='gray', hatch='//', label='slowdown / no-snare section' if k == 0 else None)
        b = a.twinx(); b.step(range(len(P['snare_strong'])), np.convolve(P['snare_strong'], np.ones(2) / 2, 'same'), where='mid', color='tab:green', alpha=0.6, lw=1); b.set_ylabel('strong snare hits / bar', color='tab:green'); b.set_ylim(0, 6)
        lo, hi = a.get_ylim(); yy = lo + (hi - lo) * 0.92
        a.plot(pro[key], [yy, yy], color='tab:blue', lw=7, solid_capstyle='butt', label=f"pro window {pro[key][0]}-{pro[key][1]}")
        for j, (lab, w) in enumerate(ours.items()):
            y2 = lo + (hi - lo) * (0.84 - 0.08 * j); a.plot(w[key], [y2, y2], color=cols[j % 3], lw=7, solid_capstyle='butt', label=f"{lab} {w[key][0]}-{w[key][1]}")
        if key == 'A' and pro.get('swapA') is not None: a.axvline(pro['swapA'], color='tab:blue', ls=':', label=f"pro bass swap ({pro['swapA']})")
        a.set_title(f'{ttl}: {yt} (bars at mix tempo)'); a.legend(fontsize=7, loc='lower left', ncol=2); a.set_xlabel('bar')
    fig.tight_layout(); fig.savefig(out, dpi=105); plt.close(fig)
if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4]), json.loads(sys.argv[5]), tuple(sys.argv[6:8]) if len(sys.argv) > 7 else ('outgoing', 'incoming'))
