"""RCA of mix08_long1f remaining failure vs shipped Mix 08 v2 (r11c). No rebuild.
Failure: test_no_bass_gap_in_overlaps, trans 12, mix bar 1331, 2 bars.
"""
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

import blend_diag as BD
import bassgap as BG
import fade_long as FL
import engine as E
from engine import BS, BEAT
import deckpair as P
S16 = BEAT / 4

OUT = ROOT / 'deliver' / 'mix08_long1f' / 'rca'
OUT.mkdir(parents=True, exist_ok=True)
TITLES = json.load(open(ROOT / 'mix08' / 'titles.json'))
name = lambda i: TITLES.get(i, i)

L = json.load(open(SRC2 / 'mix08_long1f_meta.json'))
Emeta = json.load(open(SRC2 / 'mix08_long1e_meta.json'))
R = json.load(open(SRC2 / 'mix08_r11c_meta.json'))
rowsL = json.load(open(SRC2 / 'guard_mix08_long1f' / 'transitions_rows.json'))
rowsR = json.load(open(SRC2 / 'guard_mix08_r11c' / 'transitions_rows.json'))
BAR = float(L['bar_sec'])
WAVL = str(SRC2 / 'mix08_long1f_master.wav')  # what the failing test read
WAVE = str(SRC2 / 'mix08_long1e_master.wav')
WAVR = '/tmp/mix08_r11c.wav'
X = 32
LG0 = dict(rise=2.0, xp=0.35, xp2=0.5, exit_=8.0, solo=16.0)


def ts(bar):
    s = bar * BAR
    return f"{int(s//60)}:{s%60:05.2f}"


def xf_at(t, bars):
    xs = np.asarray(t['xfader'], float)
    return np.interp(bars, xs[:, 0], xs[:, 1])


def mix_lows(wav, b0, b1):
    import soundfile as sf
    x, sr = sf.read(wav, dtype='float32', always_2d=True)
    return BG.bar_db(x, sr, BAR * sr, int(b0), int(b1))


def src_lows(deck, b0, b1):
    tr = E.track(deck['id'])
    x = tr['st']['mix']
    sr = E.SR
    bs = E.BAR * sr
    fm = deck['full_map']
    ds = deck['start_bar']
    out = []
    for b in range(int(b0), int(b1)):
        k = int(b - ds)
        if not 0 <= k < len(fm):
            out.append(np.nan)
            continue
        sb = fm[k][0]
        out.append(float(BG.bar_db(x, sr, bs, sb, sb + 1, ofs=tr['d0'] * sr)[0]))
    return np.array(out)


def srcbar(deck, mb):
    k = int(mb - deck['start_bar'])
    fm = deck['full_map']
    if 0 <= k < len(fm):
        v = fm[k]
        return v[0] if isinstance(v, (list, tuple)) else v
    return None


def load_hb(which, i):
    p = ROOT / 'deliver' / f'mix08_{which}' / 'diagnostics'
    import glob
    gs = glob.glob(str(p / f'blend{i:02d}_*.json'))
    return json.load(open(gs[0]))['halfbeat'] if gs else None


def window_maps(meta, i):
    t = meta['trans'][i]
    dA, dB = meta['decks'][i], meta['decks'][i + 1]
    s, e = int(t['start_bar']), int(t['end_bar'])
    wa = [srcbar(dA, b) for b in range(s, e)]
    wb = [srcbar(dB, b) for b in range(s, e)]
    return t, dA, dB, s, e, wa, wb


def reconstruct_long_params(meta, i):
    """Replay fade_long decisions for this blend (same env as long_test.sh). Does not import mix_simple."""
    t, dA, dB, s, e, wa, wb = window_maps(meta, i)
    a, b = t['a'], t['b']
    gA = E.track(a)['g']['bar']
    gB = E.track(b)['g']['bar']
    alA = np.array(gA['all'], float)
    alB = np.array(gB['all'], float)
    loB = np.array(gB.get('low', gB['all']), float)
    loA = np.array(gA.get('low', gA['all']), float)
    vA = np.array(gA.get('voc', [-100] * len(alA)), float)
    vB = np.array(gB.get('voc', [-100] * len(alB)), float)
    rvA = float(np.percentile(vA, 95)) if float(np.ptp(vA)) else float('inf')
    rvB = float(np.percentile(vB, 95)) if float(np.ptp(vB)) else float('inf')
    struct = FL.struct_solo(alA, list(wa), X, **LG0)
    cap = FL.cap_solo_incoming(alB, loB, list(wb), X, **{**LG0, 'solo': struct})
    hold = float(FL.vocal_hold(vA, rvA, list(wa), vB, rvB, list(wb), X))
    solo, ex = FL.vocal_exit_params(vB, rvB, list(wb), X, **{**LG0, 'solo': struct, 'hold': hold, 'cap_solo': cap})
    lg = dict(LG0, solo=solo, hold=hold, exit_=ex)
    pos = FL.swap_pos(X, **lg)
    ex0 = FL.exit_start(X, **lg)
    ex1 = FL.exit_bar(X, rise=lg['rise'], exit_=lg['exit_'], solo=lg['solo'])
    lead = FL.bass_lead(1.0, phrase=bool(t.get('swap_phrase')), fade=t.get('fade', 'long'))
    c_mix = s + pos * X
    # second-half thin bars of incoming (same rule as cap_solo_incoming)
    def series(arr):
        out = []
        for j in range(int(X)):
            k = wb[j] if j < len(wb) and 0 <= wb[j] < len(arr) else None
            out.append(arr[k] if k is not None else np.nan)
        return np.array(out, float)
    def thin_bars(arr, db=4):
        s_ = series(arr)
        half = max(4, int(X) // 2)
        ref = float(np.nanmedian(s_[:half])) if np.isfinite(s_[:half]).sum() >= 2 else np.nan
        idx = np.where((np.arange(int(X)) >= half) & (s_ < ref - db))[0]
        return ref, [int(s + j) for j in idx], {int(s + j): round(float(s_[j]), 2) for j in range(int(X)) if np.isfinite(s_[j])}
    ref_all, thin_all, ser_all = thin_bars(alB)
    ref_lo, thin_lo, ser_lo = thin_bars(loB)
    return dict(
        struct_solo=struct, cap_solo_incoming=cap, hold=hold,
        vocal_exit_solo=solo, vocal_exit_exit_=ex,
        exit_start_bars_into=ex0, exit_end_bars_into=ex1,
        swap_pos=pos, swap_centre_mix=c_mix,
        bass_lead=lead,
        predicted_bass_swap=[round(c_mix - lead[0] - 4 / 2, 3), round(c_mix + lead[1] + 4 / 2, 3)],
        predicted_swap_bar=s + int(round(pos * X)),
        xf_gone_pred=s + ex1,
        incoming_first_half_median_all=ref_all, incoming_thin_all_mixbars=thin_all,
        incoming_first_half_median_low=ref_lo, incoming_thin_low_mixbars=thin_lo,
        incoming_low_in_window=ser_lo, incoming_all_in_window=ser_all,
        srcA_at_gap=[srcbar(dA, b) for b in (1331, 1332)],
        srcB_at_gap=[srcbar(dB, b) for b in (1331, 1332)],
        recorded=dict(bass_swap=t.get('bass_swap'), swap_bar=t.get('swap_bar'),
                      high_bar=t.get('high_bar'), end_bar=t.get('end_bar'),
                      swap_phrase=t.get('swap_phrase'), swap_w=t.get('swap_w')),
    )


def figure_cmp(i, mark_bars, title, note, fname, extra_ann=()):
    tL, tR = L['trans'][i], R['trans'][i]
    s, e = int(tL['start_bar']), int(tL['end_bar'])
    b0, b1 = s - 4, e + 4
    bars = np.arange(b0, b1)
    xb = np.arange(b0, b1, 0.25)
    (gLa, lLa), (gLb, lLb) = BD.engine_curves(L, i, xb)
    (gRa, lRa), (gRb, lRb) = BD.engine_curves(R, i, xb)
    s0L, AL, BL_ = BD.crop_decks(L, i, pre=4, post=4)
    s0R, AR, BR_ = BD.crop_decks(R, i, pre=4, post=4)
    nbL, nbR = int(round(len(AL) / BS)), int(round(len(AR) / BS))
    loAL, loBL = BD.band_bar_db(AL, nbL, BS, 'low', 150), BD.band_bar_db(BL_, nbL, BS, 'low', 150)
    loAR, loBR = BD.band_bar_db(AR, nbR, BS, 'low', 150), BD.band_bar_db(BR_, nbR, BS, 'low', 150)
    sumL = 10 * np.log10(10 ** (loAL / 10) + 10 ** (loBL / 10))
    sumR = 10 * np.log10(10 ** (loAR / 10) + 10 ** (loBR / 10))
    xrL = s0L + np.arange(nbL)
    xrR = s0R + np.arange(nbR)
    mdL = mix_lows(WAVL, b0, b1)
    mdR = mix_lows(WAVR, b0, b1)
    mdE = mix_lows(WAVE, b0, b1)
    dA = L['decks'][i]
    dB = L['decks'][i + 1]
    srcA = src_lows(dA, b0, b1)
    srcB = src_lows(dB, b0, b1)
    bl = list(range(4, 4 + (e - s)))
    offL = BD.bar_offsets(AL, BL_, bl, BS, BEAT)
    offR = BD.bar_offsets(AR, BR_, bl, BS, BEAT)
    hbL = load_hb('long1f', i) or {}
    rl = {r['bar']: r for r in rowsL[i]['rows']}
    rr = {r['bar']: r for r in rowsR[i]['rows']}

    fig, ax = plt.subplots(5, 1, figsize=(12, 14), sharex=True,
                           gridspec_kw={'hspace': 0.32})
    fig.suptitle(title, fontsize=11, fontweight='bold')

    a = ax[0]
    a.plot(xb, 20 * np.log10(np.clip(gLa, 1e-9, 1)), 'C0', label='long xfader A')
    a.plot(xb, 20 * np.log10(np.clip(gLb, 1e-9, 1)), 'C3', label='long xfader B')
    a.plot(xb, 20 * np.log10(np.clip(lLa, 1e-9, 1)), 'C0--', lw=1, label='long low A')
    a.plot(xb, 20 * np.log10(np.clip(lLb, 1e-9, 1)), 'C3--', lw=1, label='long low B')
    a.plot(xb, 20 * np.log10(np.clip(gRa, 1e-9, 1)), 'C0', alpha=0.3, label='v2 xfader A')
    a.plot(xb, 20 * np.log10(np.clip(gRb, 1e-9, 1)), 'C3', alpha=0.3, label='v2 xfader B')
    a.plot(xb, 20 * np.log10(np.clip(lRa, 1e-9, 1)), 'C0:', alpha=0.5, lw=1, label='v2 low A')
    a.plot(xb, 20 * np.log10(np.clip(lRb, 1e-9, 1)), 'C3:', alpha=0.5, lw=1, label='v2 low B')
    a.axvline(s, color='k', lw=0.8)
    a.axvline(e, color='k', lw=0.8)
    for m in mark_bars:
        a.axvline(m, color='orange', ls='--', lw=1)
    if tL.get('bass_swap'):
        a.axvspan(tL['bass_swap'][0], tL['bass_swap'][1], color='C1', alpha=0.12, label='long bass swap')
    if tR.get('bass_swap'):
        a.axvspan(tR['bass_swap'][0], tR['bass_swap'][1], color='0.5', alpha=0.08, label='v2 bass swap')
    a.set_ylim(-36, 3)
    a.set_ylabel('dB')
    a.set_title('Engine: crossfader and low-lane gains (solid/dashed = long1f, faint = v2 r11c)', fontsize=9)
    a.legend(fontsize=6, ncol=4, loc='lower left')
    a.grid(alpha=.3)

    a = ax[1]
    a.plot(bars + 0.5, mdL, 'k', lw=2, label='long1f mixdown <150 Hz')
    a.plot(bars + 0.5, mdE, color='C2', lw=1.2, ls='--', label='long1e mixdown <150 Hz (passed this check)')
    a.plot(bars + 0.5, mdR, 'k', lw=1.2, alpha=0.45, label='v2 mixdown <150 Hz')
    a.plot(bars + 0.5, srcA, 'C0', lw=1, label='source A Ember (pre-fader)')
    a.plot(bars + 0.5, srcB, 'C3', lw=1, label='source B Bad To Me (pre-fader)')
    for m in mark_bars:
        a.axvline(m, color='orange', ls='--', lw=1)
    a.axvline(s, color='k', lw=0.8)
    a.axvline(e, color='k', lw=0.8)
    a.set_ylim(-50, 0)
    a.set_ylabel('dB')
    a.set_title('Mixdown lows vs each source’s own lows (exempt only if BOTH decks dip). Green dashed = long1e.', fontsize=9)
    a.legend(fontsize=6, loc='lower left')
    a.grid(alpha=.3)

    a = ax[2]
    a.plot(xrL, loAL, 'C0', label='long rendered A low')
    a.plot(xrL, loBL, 'C3', label='long rendered B low')
    a.plot(xrL, sumL, 'k', lw=1.4, label='long sum')
    a.plot(xrR, loAR, 'C0', alpha=0.3, label='v2 rendered A low')
    a.plot(xrR, loBR, 'C3', alpha=0.3, label='v2 rendered B low')
    a.plot(xrR, sumR, 'k', alpha=0.35, lw=1, label='v2 sum')
    for m in mark_bars:
        a.axvline(m, color='orange', ls='--', lw=1)
        r = rl.get(int(m)) or rl.get(m)
        if r and 'subSum' in r:
            a.annotate(f"long subA {r.get('subA')} subB {r.get('subB')} sum {r.get('subSum')}",
                       xy=(m, r['subSum']), xytext=(m + 1, r['subSum'] + 6),
                       fontsize=7, color='C1',
                       arrowprops=dict(arrowstyle='->', color='C1', lw=0.6))
    a.axvline(s, color='k', lw=0.8)
    a.axvline(e, color='k', lw=0.8)
    a.set_ylim(-70, 0)
    a.set_ylabel('dB')
    a.set_title('Rendered-deck low band and power sum', fontsize=9)
    a.legend(fontsize=6, ncol=3, loc='lower left')
    a.grid(alpha=.3)

    a = ax[3]
    a.plot(np.array(bl) + s0L, offL, 'C0o-', ms=3, label='long A-B offset (ms)')
    a.plot(np.array(bl) + s0R, offR, 'o-', color='0.4', ms=3, alpha=0.7, label='v2 A-B offset (ms)')
    a.axhline(10, color='r', ls=':', lw=0.8, label='N1 10 ms line')
    a.axhline(-10, color='r', ls=':', lw=0.8)
    a.axhline(0, color='k', lw=0.4)
    # half-beat = 0.5 * BEAT in ms
    half = 0.5 * (BEAT / E.SR) * 1000
    a.axhline(half, color='purple', ls=':', lw=0.7, alpha=0.7, label=f'half-beat {half:.0f} ms')
    a.axhline(-half, color='purple', ls=':', lw=0.7, alpha=0.7)
    for m in mark_bars:
        a.axvline(m, color='orange', ls='--', lw=1)
    a.axvline(s, color='k', lw=0.8)
    a.axvline(e, color='k', lw=0.8)
    vt = 'FAIL' if hbL.get('fail') else 'ok'
    a.set_title(
        f"Per-bar beat offset (A minus B, ms) | long half-beat {vt}: "
        f"r0={hbL.get('r0')} rh={hbL.get('rh')} lag={hbL.get('lag_ms')} ms bars={hbL.get('bars')}",
        fontsize=9)
    a.set_ylabel('ms')
    a.legend(fontsize=6, loc='upper right')
    a.grid(alpha=.3)
    a.set_ylim(-80, 80)

    a = ax[4]
    def series(rows, key):
        bs = [r['bar'] for r in rows if b0 <= r['bar'] < b1]
        vs = [r[key] for r in rows if b0 <= r['bar'] < b1]
        return bs, vs
    bsl, al = series(rowsL[i]['rows'], 'A')
    _, blv = series(rowsL[i]['rows'], 'B')
    bsr, ar = series(rowsR[i]['rows'], 'A')
    _, brv = series(rowsR[i]['rows'], 'B')
    a.plot(bsl, al, 'C0', label='long A')
    a.plot(bsl, blv, 'C3', label='long B')
    a.plot(bsr, ar, 'C0', alpha=0.3, label='v2 A')
    a.plot(bsr, brv, 'C3', alpha=0.3, label='v2 B')
    early = [r['A'] for r in rowsL[i]['rows'] if s - 8 <= r['bar'] < s and r['A'] > -80]
    refA = float(np.median(early)) if early else -20
    a.axhline(refA - 24, color='C3', ls=':', lw=0.9, label=f'N1 first-audible line (refA-24={refA-24:.1f})')
    for m in mark_bars:
        a.axvline(m, color='orange', ls='--', lw=1)
    a.axvline(s, color='k', lw=0.8)
    a.axvline(e, color='k', lw=0.8)
    a.set_ylim(-60, 0)
    a.set_ylabel('dB')
    a.set_xlabel('mix bar')
    a.set_title('Rendered all-band deck levels', fontsize=9)
    a.legend(fontsize=6, ncol=3, loc='lower left')
    a.grid(alpha=.3)
    a.set_xlim(b0, b1)

    txt = note + '\n' + '\n'.join(extra_ann)
    fig.text(0.01, 0.01, txt, fontsize=7, va='bottom', family='monospace', wrap=True)
    fig.savefig(OUT / fname, dpi=120, bbox_inches='tight')
    plt.close(fig)
    print('wrote', OUT / fname, flush=True)
    return dict(
        i=i, s=s, e=e, mark_bars=list(mark_bars),
        md_long={int(b0 + k): round(float(v), 2) for k, v in enumerate(mdL) if np.isfinite(v)},
        md_long1e={int(b0 + k): round(float(v), 2) for k, v in enumerate(mdE) if np.isfinite(v)},
        md_v2={int(b0 + k): round(float(v), 2) for k, v in enumerate(mdR) if np.isfinite(v)},
        srcA={int(b0 + k): round(float(v), 2) for k, v in enumerate(srcA) if np.isfinite(v)},
        srcB={int(b0 + k): round(float(v), 2) for k, v in enumerate(srcB) if np.isfinite(v)},
        off_long={int(s0L + b): (None if not np.isfinite(v) else round(float(v), 1)) for b, v in zip(bl, offL)},
        off_v2={int(s0R + b): (None if not np.isfinite(v) else round(float(v), 1)) for b, v in zip(bl, offR)},
        hb=hbL,
        bass_swap_long=tL.get('bass_swap'), bass_swap_v2=tR.get('bass_swap'),
        bass_swap_long1e=Emeta['trans'][i].get('bass_swap'),
    )


def bassgap_depths(wav, t, b0=None, b1=None):
    s, e = int(t['start_bar']), int(t['end_bar'])
    b0 = s - 4 if b0 is None else b0
    b1 = e + 4 if b1 is None else b1
    db = mix_lows(wav, b0, b1)
    out = []
    for k, v in enumerate(db):
        nb = [db[j] for j in range(max(0, k - 4), min(len(db), k + 5)) if abs(j - k) >= 1]
        med = float(np.nanmedian(nb))
        depth = med - float(v) if np.isfinite(v) else None
        out.append(dict(bar=b0 + k, db=None if not np.isfinite(v) else round(float(v), 2),
                        neigh=round(med, 2), depth=None if depth is None else round(depth, 2),
                        flag=bool(depth is not None and depth > BG.GAP_DB)))
    return out


if __name__ == '__main__':
    summary = {}
    i = 12
    tL, tR, tE = L['trans'][i], R['trans'][i], Emeta['trans'][i]
    print('reconstructing fade params…', flush=True)
    pathL = reconstruct_long_params(L, i)
    summary['code_path'] = pathL
    print(json.dumps({k: pathL[k] for k in pathL if k not in ('incoming_low_in_window', 'incoming_all_in_window')}, indent=2, default=float), flush=True)

    print('measuring depths…', flush=True)
    depthsL = bassgap_depths(WAVL, tL)
    depthsE = bassgap_depths(WAVE, tE)
    depthsR = bassgap_depths(WAVR, tR)
    note = (
        f"trans 12 {name(tL['a'])} -> {name(tL['b'])}\n"
        f"window {tL['start_bar']}-{tL['end_bar']} ({ts(tL['start_bar'])}-{ts(tL['end_bar'])})  "
        f"GAP_DB={BG.GAP_DB}\n"
        f"long1f bass_swap {tL.get('bass_swap')} swap_bar {tL.get('swap_bar')}; "
        f"long1e {tE.get('bass_swap')} @{tE.get('swap_bar')}; "
        f"v2 {tR.get('bass_swap')} @{tR.get('swap_bar')}"
    )
    extra = [f"code-path: struct={pathL['struct_solo']} cap={pathL['cap_solo_incoming']} hold={pathL['hold']} "
             f"solo={pathL['vocal_exit_solo']} exit_={pathL['vocal_exit_exit_']} "
             f"exit_start={pathL['exit_start_bars_into']} swap_centre={pathL['swap_centre_mix']} "
             f"lead={pathL['bass_lead']} pred_swap={pathL['predicted_bass_swap']}",
             f"incoming thin (all) bars {pathL['incoming_thin_all_mixbars']}  (low) {pathL['incoming_thin_low_mixbars']}",
             f"src bars at gap: Ember {pathL['srcA_at_gap']}  Bad To Me {pathL['srcB_at_gap']}"]
    for label, depths in (('long1f', depthsL), ('long1e', depthsE), ('v2', depthsR)):
        extra.append(label + ':')
        for d in depths:
            if 1326 <= d['bar'] <= 1336:
                extra.append(f"  {label} bar {d['bar']} mix {d['db']} neigh {d['neigh']} depth {d['depth']} flag={d['flag']}")

    print('drawing figure…', flush=True)
    summary['bassgap_t12'] = figure_cmp(
        12, [1331, 1332],
        'RCA: bass gap trans 12 @ bar 1331 (2 bars) — long1f vs Mix 08 v2 (long1e dashed)',
        note, 'rca_t12_bassgap.png', extra)
    summary['bassgap_depths_long1f'] = [d for d in depthsL if 1324 <= d['bar'] <= 1338]
    summary['bassgap_depths_long1e'] = [d for d in depthsE if 1324 <= d['bar'] <= 1338]
    summary['bassgap_depths_v2'] = [d for d in depthsR if 1324 <= d['bar'] <= 1338]
    summary['meta_cmp'] = dict(
        long1f=dict(swap_bar=tL['swap_bar'], bass_swap=tL.get('bass_swap'), high_bar=tL.get('high_bar'), fade=tL.get('fade'), swap_w=tL.get('swap_w'), swap_phrase=tL.get('swap_phrase')),
        long1e=dict(swap_bar=tE['swap_bar'], bass_swap=tE.get('bass_swap'), high_bar=tE.get('high_bar'), fade=tE.get('fade'), swap_w=tE.get('swap_w'), swap_phrase=tE.get('swap_phrase')),
        v2=dict(swap_bar=tR['swap_bar'], bass_swap=tR.get('bass_swap'), high_bar=tR.get('high_bar'), fade=tR.get('fade'), swap_w=tR.get('swap_w'), swap_phrase=tR.get('swap_phrase')),
    )
    print('scanning all long1f transitions for official gaps and near-misses (within 2 dB of GAP_DB)…', flush=True)
    import soundfile as sf
    xL, srL = sf.read(WAVL, dtype='float32', always_2d=True)
    xE, srE = sf.read(WAVE, dtype='float32', always_2d=True)
    xR, srR = sf.read(WAVR, dtype='float32', always_2d=True)

    def scan(meta, x, sr, also_src=True):
        bs = meta['bar_sec'] * sr
        out = []
        for i, t in enumerate(meta['trans']):
            b0, b1 = int(t['start_bar']) - 4, int(t['end_bar']) + 4
            db = BG.bar_db(x, sr, bs, b0, b1)
            rows = []
            official = []
            near = []
            for k, v in enumerate(db):
                nb = [db[j] for j in range(max(0, k - 4), min(len(db), k + 5)) if abs(j - k) >= 1]
                med = float(np.nanmedian(nb))
                depth = (med - float(v)) if np.isfinite(v) else None
                bar = b0 + k
                rec = dict(bar=bar, db=None if not np.isfinite(v) else round(float(v), 2),
                           neigh=round(med, 2), depth=None if depth is None else round(depth, 2))
                if depth is not None and depth > BG.GAP_DB - 2:
                    rows.append(rec)
            # official gap runs (same rules as BG.check, plus near-miss isolated bars)
            low = []
            for k, v in enumerate(db):
                nb = [db[j] for j in range(max(0, k - 4), min(len(db), k + 5)) if abs(j - k) >= 1]
                low.append(np.isfinite(v) and v < np.nanmedian(nb) - (BG.GAP_DB - 2))
            k = 0
            n = len(db)
            while k < n:
                if low[k]:
                    j = k
                    while j < n and low[j]:
                        j += 1
                    s, Lrun = b0 + k, j - k
                    depths = []
                    for kk in range(k, j):
                        nb = [db[q] for q in range(max(0, kk - 4), min(n, kk + 5)) if abs(q - kk) >= 1]
                        depths.append(float(np.nanmedian(nb) - db[kk]))
                    rec = dict(start_bar=s, bars=Lrun, max_depth=round(max(depths), 2),
                               official_depth_over=bool(max(depths) > BG.GAP_DB),
                               in_overlap=not (s + Lrun <= t['start_bar'] or s >= t['end_bar']),
                               over_1_bar=Lrun > 1)
                    # source exemption only for official-depth runs
                    both_src = None
                    if also_src and rec['in_overlap'] and rec['official_depth_over'] and rec['over_1_bar']:
                        both_src = all(BG.src_dip(meta['decks'][j_], s, Lrun) for j_ in (i, i + 1))
                    rec['both_sources_dip'] = both_src
                    rec['would_fail'] = bool(rec['in_overlap'] and rec['official_depth_over'] and rec['over_1_bar'] and not both_src)
                    rec['near_miss'] = bool(rec['in_overlap'] and rec['over_1_bar'] and not rec['would_fail'] and max(depths) > BG.GAP_DB - 2)
                    rec['one_bar_near'] = bool(rec['in_overlap'] and Lrun == 1 and max(depths) > BG.GAP_DB - 2)
                    (official if rec['would_fail'] else near).append(rec)
                    k = j
                else:
                    k += 1
            if official or near or any(r.get('depth') and r['depth'] > BG.GAP_DB - 2 for r in rows):
                out.append(dict(i=i, a=t['a'], b=t['b'], start_bar=t['start_bar'], end_bar=t['end_bar'],
                                bass_swap=t.get('bass_swap'), swap_bar=t.get('swap_bar'), fade=t.get('fade'),
                                official=official, near=near,
                                deep_bars=[r for r in rows if r['depth'] and r['depth'] > BG.GAP_DB - 2]))
        return out

    scanL = scan(L, xL, srL)
    scanE = scan(Emeta, xE, srE, also_src=False)
    scanR = scan(R, xR, srR, also_src=False)
    summary['scan_long1f'] = scanL
    summary['scan_long1e_same_windows'] = scanE
    summary['scan_v2_same_windows'] = scanR
    print('LONG1F official / near-miss:', flush=True)
    for row in scanL:
        print(f"  t{row['i']} {row['a']}->{row['b']} swap={row['bass_swap']} official={row['official']} near={row['near']}", flush=True)

    json.dump(summary, open(OUT / 'rca_numbers.json', 'w'), indent=2, default=float)
    print('done', OUT, flush=True)
