#!/usr/bin/env python3
"""Pro fade curves (33 pinned pro clips, median/IQR) vs our fader x lane automation.

  pro_fade_curves.py pro                -> nightly_1125_work/profade_fit/pro_curves_33.json (per-clip u-grid dB, 4 bands, A/B)
  pro_fade_curves.py plot <ours.json> <out.png>
ours.json = {label: {band: {'a': [...], 'b': [...]}}} median curves on the same U grid (from pro_fade_fit rows).
Pro gains are NNLS band gains of each aligned source in the pro clip (diagnose_gap.band_gains), relative to solo.
"""
import json, os, sys
import numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P0 = os.path.dirname(H)
sys.path.insert(0, H); sys.path.insert(0, P0)
OUT = os.path.join(H, 'nightly_1125_work', 'profade_fit', 'pro_curves_33.json')
U = np.linspace(0.0, 1.0, 21)
BANDS = ('all', 'bass', 'mids', 'highs')


def _db(g):
    return np.clip(20.0 * np.log10(np.maximum(np.asarray(g, float), 1e-6)), -30.0, 4.0)


def pro():
    import st_pin
    os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
    import paths, run_admitted_tune as T, score, diagnose_gap as D
    PRO = json.load(open(os.path.join(H, 'protrans_decisions.json')))
    rows = {}
    for rec in T.load_recs():
        d = PRO.get(rec['id']) or {}
        s, e = d.get('in_entry_clip_bar'), d.get('out_gone_clip_bar')
        if s is None or e is None or e - s < 4:
            continue
        try:
            y = score._load(rec['pro_clip']); y = y.mean(1) if y.ndim > 1 else y
            sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
            za = D.place_source(sa, d['loc']['a']['track_t'], d['loc']['a']['mix_t'], len(y)); za, _ = D.refine_lag(y, za)
            zb = D.place_source(sb, d['loc']['b']['track_t'], d['loc']['b']['mix_t'], len(y)); zb, _ = D.refine_lag(y, zb)
            hop = 0.25
            g, _, _, _ = D.band_gains(y, za, zb, hop_s=hop)
            bar = score.BAR_SEC
            out = {}
            for band in BANDS:
                ga, gb = np.asarray(g[band]['a']), np.asarray(g[band]['b'])
                fr = lambda b: int(round(b * bar / hop))
                n_b = int(len(ga) * hop / bar)
                ba = np.array([np.mean(ga[fr(k):fr(k + 1)]) if fr(k + 1) > fr(k) else 0 for k in range(n_b)])
                bb = np.array([np.mean(gb[fr(k):fr(k + 1)]) if fr(k + 1) > fr(k) else 0 for k in range(n_b)])
                ee = min(int(e), n_b - 1)
                bars = np.arange(int(s), ee + 1); uu = np.linspace(0, 1, len(bars))
                out[band] = dict(a=np.interp(U, uu, _db(ba[bars])).round(2).tolist(), b=np.interp(U, uu, _db(bb[bars])).round(2).tolist())
            rows[rec['id']] = out
            print('pro', rec['id'], len(rows), flush=True)
        except Exception as ex:
            print('skip', rec['id'], type(ex).__name__, str(ex)[:120], flush=True)
    json.dump(dict(U=U.tolist(), rows=rows), open(OUT, 'w'))
    print('PRO_CURVES', len(rows), OUT, flush=True)


def plot(ours_p, png):
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    P = json.load(open(OUT)); ours = json.load(open(ours_p)); rows = list(P['rows'].values())
    fig, axs = plt.subplots(2, 4, figsize=(22, 9), sharex=True)
    cols = {'base (safe outro fade)': '#2b6cb0', 'fit-2 fade (fixed -24 dB bass cut)': '#dd6b20', 'new pro fade': '#c53030'}
    for j, band in enumerate(BANDS):
        for i, deck in enumerate(('a', 'b')):
            ax = axs[i, j]
            M = np.array([r[band][deck] for r in rows])
            q25, q50, q75 = np.percentile(M, [25, 50, 75], axis=0)
            ax.fill_between(U, q25, q75, color='0.75', alpha=0.6, label=f'pro IQR (n={len(rows)})')
            ax.plot(U, q50, 'k-', lw=2.5, label='pro median')
            for lab, cur in ours.items():
                ax.plot(ours[lab]['U'], cur[band][deck], lw=2, color=cols.get(lab), label=lab)
            ax.set_ylim(-31, 3); ax.grid(alpha=0.3)
            ax.set_title(f"{'Outgoing A' if deck == 'a' else 'Incoming B'} - {band}" + (' (<150 Hz)' if band == 'bass' else ' (>4 kHz)' if band == 'highs' else ''))
            if j == 0: ax.set_ylabel('gain vs solo (dB)')
            if i == 1: ax.set_xlabel('blend progress u (0 = B enters, 1 = A gone)')
    axs[0, 0].legend(fontsize=8, loc='lower left')
    fig.suptitle('Learned pro fade vs pro DJs (33 pinned pro clips, median and IQR) - fader x EQ lane, per band', fontsize=14)
    fig.tight_layout(); fig.savefig(png, dpi=110); print('PNG', png)


if __name__ == '__main__':
    if sys.argv[1] == 'pro':
        pro()
    else:
        plot(sys.argv[2], sys.argv[3])
