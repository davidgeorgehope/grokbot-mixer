#!/usr/bin/env python3
"""2026-11-19: before/after listening clips + PNGs for typical PLACE=safe c mid-track exits (default vs c). The clips are the rendered
transition excerpts (blend +- 8 bars) copied as-is; the PNG shows the outgoing track's per-bar loudness with its drops shaded and where
each version blends out, plus where the incoming track gets cued relative to its first drop."""
import os, sys, json, shutil, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); import safeplace_1119 as S
OUT = os.path.join(H, 'placequal_clips'); Q = {x['id']: x for x in json.load(open(os.path.join(H, 'placequal_1119.json')))['rows']}
R = {r['id']: r for r in S.dev_rows()}
def row(v, i):
    for l in open(os.path.join(H, 'gate_ckpt', v + '.jsonl')):
        r = json.loads(l)
        if r['id'] == i: return r
IDS = sys.argv[1:]; summ = []
for i in IDS:
    r = R[i]; d = row('default', i) or row('ndef1119', i); c = row('sp1119c1', i); c2 = row('sp1119c2', i)
    c = c2 if (c2 and c['hard'].get('hard_fail')) else c
    for tag, g in (('default', d), ('safe_c', c)): shutil.copy(g['mp3'], os.path.join(OUT, f'{i}_{tag}.mp3'))
    A = np.asarray(S.st(r['ya'])['all'], float); B = np.asarray(S.st(r['yb'])['all'], float)
    fig, ax = plt.subplots(2, 1, figsize=(12, 5.5), gridspec_kw=dict(height_ratios=[3, 2]))
    ax[0].plot(A, color='k', lw=1); [ax[0].axvspan(a, b, color='orange', alpha=0.25, label='drop' if k == 0 else None) for k, (a, b) in enumerate(r['sa'].get('drops') or [])]
    for tag, g, col in (('default', d, 'tab:blue'), ('safe c', c, 'tab:red')):
        e, X = g['win'][1], g['win'][4]; ax[0].axvspan(e - X, e, color=col, alpha=0.3, label=f'{tag} blend-out (bars {e - X}-{e})')
    ax[0].set_title(f"{i}: outgoing track (A) loudness per bar; A plays {Q[i]['default']['played']:.0%} (default) vs {Q[i]['c_final']['played']:.0%} (safe c)")
    ax[0].set_xlabel('A bar'); ax[0].set_ylabel('dB'); ax[0].legend(fontsize=8, loc='lower left')
    ax[1].plot(B, color='k', lw=1); [ax[1].axvspan(a, b, color='orange', alpha=0.25) for a, b in (r['sb'].get('drops') or [])]
    for tag, g, col in (('default', d, 'tab:blue'), ('safe c', c, 'tab:red')): ib, X = g['win'][3], g['win'][4]; ax[1].axvspan(ib, ib + X, color=col, alpha=0.3)
    ax[1].set_xlabel('incoming track (B) bar; shaded = where each version cues it in'); ax[1].set_ylabel('dB')
    fig.tight_layout(); fig.savefig(os.path.join(OUT, f'{i}_placement.png'), dpi=110); plt.close(fig)
    summ.append(dict(id=i, drops_A=r['sa'].get('drops'), music_end_A=S.NA(r['sa']), default_win=d['win'], c_win=c['win'], default_fail=d['hard'].get('hard_fail'), c_fail=c['hard'].get('hard_fail'),
                     played_default=Q[i]['default']['played'], played_c=Q[i]['c_final']['played']))
json.dump(summ, open(os.path.join(OUT, 'clips.json'), 'w'), indent=1, default=float); print(json.dumps(summ, indent=1, default=float))
