"""RCA of mix08_long1g X1/L1/ride regression vs long1f. No rebuild."""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path('/workspace/mixes')
SRC2 = ROOT / 'src2'
sys.path[:0] = [str(SRC2), str(ROOT / 'src'), str(ROOT / 'src' / 'tests')]
os.chdir(SRC2)
import fade_long as FL
import engine as E
import test_crossfader as X1

OUT = ROOT / 'deliver' / 'mix08_long1g' / 'rca'
OUT.mkdir(parents=True, exist_ok=True)
TITLES = json.load(open(ROOT / 'mix08' / 'titles.json'))
name = lambda i: TITLES.get(i, i)
F = json.load(open(SRC2 / 'mix08_long1f_meta.json'))
G = json.load(open(SRC2 / 'mix08_long1g_meta.json'))
BAR = float(F['bar_sec'])

def ts(bar):
    s = bar * BAR
    return f"{int(s//60)}:{s%60:05.2f}"

def xf_at(t, b):
    xs = np.asarray(t['xfader'], float)
    return np.interp(b, xs[:, 0], xs[:, 1])

def lane(d, b, key='low'):
    lo = np.asarray(d['auto'][key], float)
    return np.interp(b, lo[:, 0], lo[:, 1])

def first_thin(meta, i):
    t, dB = meta['trans'][i], meta['decks'][i + 1]
    s, e = int(t['start_bar']), int(t['end_bar'])
    fm, ds = dB['full_map'], dB['start_bar']
    wb = [fm[int(b - ds)][0] if 0 <= int(b - ds) < len(fm) else -1 for b in range(s, e)]
    g = E.track(t['b'])['g']['bar']
    return FL.first_incoming_thin_bar(np.array(g['all'], float), np.array(g.get('low', g['all']), float), wb, e - s)

CASES = [(1, '5:08'), (2, '9:11'), (3, '10:51'), (12, 't12 bass gap')]

def figure():
    fig, axes = plt.subplots(4, 2, figsize=(14, 14), sharex=False, gridspec_kw={'hspace': 0.45, 'wspace': 0.25})
    fig.suptitle('RCA: mix08-long1g cover_through regression vs long1f\nleft = xfader + low lanes; right = both-decks-full-bass (L1 class)', fontsize=11, fontweight='bold')
    notes = []
    for row, (i, tag) in enumerate(CASES):
        tF, tG = F['trans'][i], G['trans'][i]
        s, e = int(tF['start_bar']), int(tF['end_bar'])
        xb = np.arange(s, e + 0.01, 0.25)
        ft = first_thin(F, i)
        a = axes[row, 0]
        a.plot(xb, xf_at(tF, xb), 'k', lw=1.2, label='xfader (same)')
        a.plot(xb, lane(F['decks'][i], xb), 'C0', lw=1.6, label='long1f low A')
        a.plot(xb, lane(F['decks'][i + 1], xb), 'C3', lw=1.6, label='long1f low B')
        a.plot(xb, lane(G['decks'][i], xb), 'C0', ls='--', lw=1.2, alpha=0.85, label='long1g low A')
        a.plot(xb, lane(G['decks'][i + 1], xb), 'C3', ls='--', lw=1.2, alpha=0.85, label='long1g low B')
        a.axvspan(tF['bass_swap'][0], tF['bass_swap'][1], color='C0', alpha=0.10, label='long1f bass_swap')
        a.axvspan(tG['bass_swap'][0], tG['bass_swap'][1], color='C3', alpha=0.10, label='long1g bass_swap')
        if ft >= 0:
            a.axvline(s + ft, color='orange', ls='--', lw=1, label=f'first thin {s+ft}')
        a.set_ylim(-0.05, 1.15)
        a.set_xlim(s, e)
        a.set_ylabel('x / low')
        a.set_title(f't{i} {tag} {name(tF["a"])} → {name(tF["b"])}  {ts(s)}–{ts(e)}', fontsize=8)
        a.legend(fontsize=5, ncol=3, loc='center left')
        a.grid(alpha=.3)
        a.set_xlabel('mix bar')

        a = axes[row, 1]
        bothF = (lane(F['decks'][i], xb) > 0.5) & (lane(F['decks'][i + 1], xb) > 0.5)
        bothG = (lane(G['decks'][i], xb) > 0.5) & (lane(G['decks'][i + 1], xb) > 0.5)
        a.fill_between(xb, 0, bothF.astype(float), color='C0', alpha=0.4, label=f'long1f both>0.5  {(bothF.sum()*0.25):.1f} bars')
        a.fill_between(xb, 0, bothG.astype(float), color='C3', alpha=0.4, label=f'long1g both>0.5  {(bothG.sum()*0.25):.1f} bars')
        a.set_ylim(0, 1.2)
        a.set_xlim(s, e)
        a.set_title(f"swap f {tF['bass_swap']}  g {tG['bass_swap']}\n"
                    f"x at g outgoing-ramp mid {xf_at(tG, np.mean(tG['bass_swap'])):.2f}", fontsize=8)
        a.legend(fontsize=6, loc='upper right')
        a.grid(alpha=.3)
        a.set_xlabel('mix bar')
        notes.append(dict(
            i=i, tag=tag, start=s, end=e, first_thin=None if ft < 0 else s + ft,
            bass_swap_f=tF['bass_swap'], bass_swap_g=tG['bass_swap'],
            swap_bar_f=tF['swap_bar'], swap_bar_g=tG['swap_bar'],
            x_centre_f=round(float(xf_at(tF, np.mean(tF['bass_swap']))), 3),
            x_centre_g=round(float(xf_at(tG, np.mean(tG['bass_swap']))), 3),
            xfader_n_f=len(tF['xfader']), xfader_n_g=len(tG['xfader']),
            both_full_bars_f=round(float(bothF.sum() * 0.25), 2),
            both_full_bars_g=round(float(bothG.sum() * 0.25), 2),
            out_at_end_f=round(float(lane(F['decks'][i], e)), 3),
            out_at_end_g=round(float(lane(G['decks'][i], e)), 3),
        ))
    fig.savefig(OUT / 'rca_long1g_lanes.png', dpi=120, bbox_inches='tight')
    plt.close(fig)
    print('wrote', OUT / 'rca_long1g_lanes.png')
    return notes

if __name__ == '__main__':
    notes = figure()
    hits_g = X1.run(G)
    summary = dict(
        long1g_pytest='4 failed, 213 passed, 1 skipped in 2069.95s',
        official=['X1 (14, including t1 5:08 x=1.00 and 13 “does not go 1->0”)',
                  'test_bass_never_doubles (3 blends, 3–6 bars both loud)',
                  'guardrails n_fail=49 (X1 14, L1 35 including 10:51 both decks full bass)',
                  'test_outgoing_fader_tail_is_gradual ride=0.0 (steep=[], xfader was not empty: bass_swap[1] was at/past the window end)'],
        ranked_causes=[
            dict(rank=1, cause='cover_through delayed the outgoing low down-ramp to last_thin+1 on every blend that had any second-half thin bars, even when the exit-start handoff already finished BEFORE first_thin (t1, t2, t3, …). That is a later move, to x=1 / past the window end.',
                 evidence=notes),
            dict(rank=2, cause='Incoming lag stayed 0, so incoming lows still rose at the original exit-start swap while outgoing stayed at 1 until the end. Both decks carried full bass for most of the second half (L1, bass_never_doubles).',
                 evidence='t1 5:08 both>0.5 for ~20 bars; t3 10:51 is one of 35 L1 hits.'),
            dict(rank=3, cause='X1 reads the low-lane movement itself: outgoing often did not reach 0 inside the blend (ramp ended after e), or its mid-point sat at x=1.00 (t1). The xfader curves were present and monotonic; the ride test used bass_swap[1] as the start of the “after swap” region, which was now at/past e, so ride=0.0 with empty steep list.',
                 evidence='guardrails + test_outgoing_fader_tail_is_gradual'),
            dict(rank=4, cause='Not a unit mismatch (mix bars were used consistently) and not “no thin stretch” — cover_through only fired when last_thin>=0. The wrong predicate was last_thin (hold outgoing to the end) rather than “does this handoff overlap the thin region?” Unit tests only checked the lead arithmetic, not X1 or doubled bass on real transitions.',
                 evidence='first_thin vs bass_swap on long1f: t1 ends 232, first thin 241; t12 ends 1333, first thin 1328 (the one case that needed an earlier swap).'),
        ],
        fix='Revert cover_through. swap_before_thin moves the 4-bar outgoing-leads handoff earlier only when it would still be running after first_thin, and only if the new centre stays in X1 0.2-0.65. t12 ends at 1328, x≈0.46. t1/t2/t3/t0/t6 unchanged. Never move later.',
        long1g_x1_n=len(hits_g),
        cases=notes,
    )
    json.dump(summary, open(OUT / 'rca_numbers.json', 'w'), indent=2, default=float)
    print('x1 hits on recorded long1g', len(hits_g))
    print('done', OUT)
