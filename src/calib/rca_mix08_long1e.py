"""RCA of mix08_long1e remaining failures vs shipped Mix 08 v2 (r11c). No rebuild."""
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
import halfbeat as HB
from engine import BS, BEAT
import deckpair as P
S16 = BEAT / 4

OUT = ROOT / 'deliver' / 'mix08_long1e' / 'rca'
OUT.mkdir(parents=True, exist_ok=True)
TITLES = json.load(open(ROOT / 'mix08' / 'titles.json'))
name = lambda i: TITLES.get(i, i)

L = json.load(open(SRC2 / 'mix08_long1e_meta.json'))
R = json.load(open(SRC2 / 'mix08_r11c_meta.json'))
rowsL = json.load(open(SRC2 / 'guard_mix08_long1e' / 'transitions_rows.json'))
rowsR = json.load(open(SRC2 / 'guard_mix08_r11c' / 'transitions_rows.json'))
BAR = float(L['bar_sec'])
# decoded mp3s (same programme, already on disk)
WAVL = '/tmp/mix08_long1e.wav'
WAVR = '/tmp/mix08_r11c.wav'


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
    """pre-fader source low dB on the mix grid for this deck."""
    import engine as E
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


def load_hb(which, i):
    p = ROOT / 'deliver' / f'mix08_{which}' / 'diagnostics'
    import glob
    gs = glob.glob(str(p / f'blend{i:02d}_*.json'))
    return json.load(open(gs[0]))['halfbeat'] if gs else None


def figure_cmp(i, mark_bars, title, note, fname, extra_ann=()):
    tL, tR = L['trans'][i], R['trans'][i]
    s, e = int(tL['start_bar']), int(tL['end_bar'])
    b0, b1 = s - 4, e + 4
    bars = np.arange(b0, b1)
    # engine curves from each meta
    xb = np.arange(b0, b1, 0.25)
    (gLa, lLa), (gLb, lLb) = BD.engine_curves(L, i, xb)
    (gRa, lRa), (gRb, lRb) = BD.engine_curves(R, i, xb)
    # rendered decks (cropped) for lows + offsets; one crop per meta
    s0L, AL, BL_ = BD.crop_decks(L, i, pre=4, post=4)
    s0R, AR, BR_ = BD.crop_decks(R, i, pre=4, post=4)
    nbL, nbR = int(round(len(AL) / BS)), int(round(len(AR) / BS))
    loAL, loBL = BD.band_bar_db(AL, nbL, BS, 'low', 150), BD.band_bar_db(BL_, nbL, BS, 'low', 150)
    loAR, loBR = BD.band_bar_db(AR, nbR, BS, 'low', 150), BD.band_bar_db(BR_, nbR, BS, 'low', 150)
    sumL = 10 * np.log10(10 ** (loAL / 10) + 10 ** (loBL / 10))
    sumR = 10 * np.log10(10 ** (loAR / 10) + 10 ** (loBR / 10))
    xrL = s0L + np.arange(nbL)
    xrR = s0R + np.arange(nbR)
    # mixdown lows
    mdL = mix_lows(WAVL, b0, b1)
    mdR = mix_lows(WAVR, b0, b1)
    # source lows
    dA = L['decks'][i]
    dB = L['decks'][i + 1]
    srcA = src_lows(dA, b0, b1)
    srcB = src_lows(dB, b0, b1)
    # offsets
    bl = list(range(4, 4 + (e - s)))  # bars into the crop
    offL = BD.bar_offsets(AL, BL_, bl, BS, BEAT)
    offR = BD.bar_offsets(AR, BR_, bl, BS, BEAT)
    hbL = load_hb('long1e', i) or {}
    # rows L1
    rl = {r['bar']: r for r in rowsL[i]['rows']}
    rr = {r['bar']: r for r in rowsR[i]['rows']}

    fig, ax = plt.subplots(5, 1, figsize=(12, 14), sharex=True,
                           gridspec_kw={'hspace': 0.32})
    fig.suptitle(title, fontsize=11, fontweight='bold')

    # 1. xfader + low-lane gains
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
    a.set_title('Engine: crossfader and low-lane gains (solid/dashed = long1e, faint = v2 r11c)', fontsize=9)
    a.legend(fontsize=6, ncol=4, loc='lower left')
    a.grid(alpha=.3)

    # 2. mixdown lows + source lows
    a = ax[1]
    a.plot(bars + 0.5, mdL, 'k', lw=2, label='long mixdown <150 Hz')
    a.plot(bars + 0.5, mdR, 'k', lw=1.2, alpha=0.45, label='v2 mixdown <150 Hz')
    a.plot(bars + 0.5, srcA, 'C0', lw=1, label='source A (pre-fader)')
    a.plot(bars + 0.5, srcB, 'C3', lw=1, label='source B (pre-fader)')
    # neighbour-median ref for bassgap around mark
    for m in mark_bars:
        a.axvline(m, color='orange', ls='--', lw=1)
    a.axvline(s, color='k', lw=0.8)
    a.axvline(e, color='k', lw=0.8)
    a.set_ylim(-50, 0)
    a.set_ylabel('dB')
    a.set_title('Mixdown lows vs each source’s own lows (a source breakdown is exempt only if BOTH decks dip)', fontsize=9)
    a.legend(fontsize=6, loc='lower left')
    a.grid(alpha=.3)

    # 3. rendered deck lows + sum (what L1 / holes see)
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
            a.annotate(f"L1 long subA {r.get('subA')} subB {r.get('subB')} sum {r.get('subSum')}",
                       xy=(m, r['subSum']), xytext=(m + 1, r['subSum'] + 6),
                       fontsize=7, color='C1',
                       arrowprops=dict(arrowstyle='->', color='C1', lw=0.6))
    a.axvline(s, color='k', lw=0.8)
    a.axvline(e, color='k', lw=0.8)
    a.set_ylim(-70, 0)
    a.set_ylabel('dB')
    a.set_title('Rendered-deck low band and power sum (L1 uses these, not the mixdown)', fontsize=9)
    a.legend(fontsize=6, ncol=3, loc='lower left')
    a.grid(alpha=.3)

    # 4. beat offsets + half-beat
    a = ax[3]
    a.plot(np.array(bl) + s0L, offL, 'C0o-', ms=3, label='long A-B offset (ms)')
    a.plot(np.array(bl) + s0R, offR, 'o-', color='0.4', ms=3, alpha=0.7, label='v2 A-B offset (ms)')
    a.axhline(10, color='r', ls=':', lw=0.8, label='N1 10 ms line')
    a.axhline(-10, color='r', ls=':', lw=0.8)
    a.axhline(0, color='k', lw=0.4)
    for m in mark_bars:
        a.axvline(m, color='orange', ls='--', lw=1)
    a.axvline(s, color='k', lw=0.8)
    a.axvline(e, color='k', lw=0.8)
    vt = 'FAIL' if hbL.get('fail') else 'ok'
    a.set_title(
        f"Per-bar beat offset (A minus B, ms) | long half-beat {vt}: "
        f"dphase={hbL.get('dphase_ms')} ms, lag={hbL.get('lag_ms')} ms, r0={hbL.get('r0')}",
        fontsize=9)
    a.set_ylabel('ms')
    a.legend(fontsize=6, loc='upper right')
    a.grid(alpha=.3)
    a.set_ylim(-80, 80)

    # 5. all-band rendered levels (N1 entry uses B vs refA-24)
    a = ax[4]
    # from rows
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
    # refA-24 from early A
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
    a.set_title('Rendered all-band deck levels (N1 entry = first bar incoming exceeds the dotted line)', fontsize=9)
    a.legend(fontsize=6, ncol=3, loc='lower left')
    a.grid(alpha=.3)
    a.set_xlim(b0, b1)

    # annotation box
    txt = note + '\n' + '\n'.join(extra_ann)
    fig.text(0.01, 0.01, txt, fontsize=7, va='bottom', family='monospace',
             wrap=True)

    fig.savefig(OUT / fname, dpi=120, bbox_inches='tight')
    plt.close(fig)
    print('wrote', OUT / fname)
    return dict(
        i=i, s=s, e=e, mark_bars=list(mark_bars),
        md_long={int(b0 + k): round(float(v), 2) for k, v in enumerate(mdL) if np.isfinite(v)},
        md_v2={int(b0 + k): round(float(v), 2) for k, v in enumerate(mdR) if np.isfinite(v)},
        srcA={int(b0 + k): round(float(v), 2) for k, v in enumerate(srcA) if np.isfinite(v)},
        srcB={int(b0 + k): round(float(v), 2) for k, v in enumerate(srcB) if np.isfinite(v)},
        off_long={int(s0L + b): (None if not np.isfinite(v) else round(float(v), 1)) for b, v in zip(bl, offL)},
        off_v2={int(s0R + b): (None if not np.isfinite(v) else round(float(v), 1)) for b, v in zip(bl, offR)},
        hb=hbL,
        bass_swap_long=tL.get('bass_swap'), bass_swap_v2=tR.get('bass_swap'),
        gone_long=float(tL['end_bar'] if xf_at(tL, [tL['end_bar']])[0] < 1 - 1e-4 else
                        next((b for b in np.arange(s, e + 0.1, 0.25) if xf_at(tL, [b])[0] >= 1 - 1e-4), e)),
    )


def n1_phase(meta, i, ent, nbar=2):
    """beat_phase of incoming deck at entry bar, same method as guardrails N1."""
    s0, A, B = BD.crop_decks(meta, i, pre=8, post=8)
    i0 = int(round((ent - s0) * BS))
    seg = B[max(0, i0):i0 + int(nbar * BS)]
    env = P.snare_env(seg) if len(seg) > 2048 else None
    if env is None:
        return None
    pb = P.beat_phase(env, per=S16, nb=2)
    return None if pb is None else float(pb)


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
    # ----- trans 18 bass gap -----
    i = 18
    tL, tR = L['trans'][i], R['trans'][i]
    depthsL = bassgap_depths(WAVL, tL)
    depthsR = bassgap_depths(WAVR, tR)
    note = (f"trans 18 {name(tL['a'])} -> {name(tL['b'])}\n"
            f"window {tL['start_bar']}-{tL['end_bar']} ({ts(tL['start_bar'])}-{ts(tL['end_bar'])})  "
            f"GAP_DB={BG.GAP_DB}\n"
            f"long gone ~{ts(1900)} (bar 1900, solo 4); v2 gone at window end 1904")
    extra = []
    for d in depthsL:
        if 1896 <= d['bar'] <= 1904:
            extra.append(f"long bar {d['bar']} mix {d['db']} neigh {d['neigh']} depth {d['depth']} flag={d['flag']}")
    extra.append('v2 same bars:')
    for d in depthsR:
        if 1896 <= d['bar'] <= 1904:
            extra.append(f" v2  bar {d['bar']} mix {d['db']} neigh {d['neigh']} depth {d['depth']} flag={d['flag']}")
    summary['bassgap_t18'] = figure_cmp(
        18, [1901, 1902],
        'RCA: bass gap trans 18 @ bar 1901 (2 bars) — long1e vs Mix 08 v2',
        note, 'rca_t18_bassgap.png', extra)
    summary['bassgap_depths_long'] = [d for d in depthsL if 1888 <= d['bar'] <= 1904]
    summary['bassgap_depths_v2'] = [d for d in depthsR if 1888 <= d['bar'] <= 1904]

    # ----- L1 trans 0 and 6 -----
    for i, bar, tag in ((0, 120, '2m45'), (6, 696, '16m00')):
        tL = L['trans'][i]
        rl = {r['bar']: r for r in rowsL[i]['rows']}
        rr = {r['bar']: r for r in rowsR[i]['rows']}
        r, v = rl.get(bar, {}), rr.get(bar, {})
        note = (f"trans {i} {name(tL['a'])} -> {name(tL['b'])}\n"
                f"L1 at {ts(bar)} bar {bar}: long subA={r.get('subA')} subB={r.get('subB')} sum={r.get('subSum')}  "
                f"v2 subA={v.get('subA')} subB={v.get('subB')} sum={v.get('subSum')}\n"
                f"long swap {tL.get('bass_swap')}  v2 swap {R['trans'][i].get('bass_swap')}")
        extra = []
        for b in range(bar - 3, bar + 4):
            a, c = rl.get(b, {}), rr.get(b, {})
            extra.append(
                f"bar {b} long A/B/subA/subB/sum={a.get('A')}/{a.get('B')}/{a.get('subA')}/{a.get('subB')}/{a.get('subSum')}  "
                f"v2 {c.get('A')}/{c.get('B')}/{c.get('subA')}/{c.get('subB')}/{c.get('subSum')}")
        summary[f'L1_t{i}'] = figure_cmp(
            i, [bar],
            f'RCA: L1 trans {i} @ {tag} bar {bar} — long1e vs Mix 08 v2',
            note, f'rca_t{i}_L1_{tag}.png', extra)

    # ----- N1 trans 5 -----
    i, bar = 5, 596
    tL = L['trans'][i]
    rl = {r['bar']: r for r in rowsL[i]['rows']}
    rr = {r['bar']: r for r in rowsR[i]['rows']}
    earlyL = [r['A'] for r in rowsL[i]['rows'] if tL['start_bar'] - 8 <= r['bar'] < tL['start_bar'] and r['A'] > -80]
    earlyR = [r['A'] for r in rowsR[i]['rows'] if tL['start_bar'] - 8 <= r['bar'] < tL['start_bar'] and r['A'] > -80]
    refL, refR = float(np.median(earlyL)), float(np.median(earlyR))
    entL = next((r['bar'] for r in rowsL[i]['rows'] if r['B'] > refL - 24), None)
    entR = next((r['bar'] for r in rowsR[i]['rows'] if r['B'] > refR - 24), None)
    print('N1 entry bars', entL, entR, 'refL', refL, 'refR', refR)
    phL = n1_phase(L, i, entL) if entL is not None else None
    phR = n1_phase(R, i, entR) if entR is not None else None
    print('N1 phase long', phL, 'v2', phR)
    # also measure v2 at long's entry bar and long at v2's entry bar
    phL_atR = n1_phase(L, i, entR) if entR is not None else None
    phR_atL = n1_phase(R, i, entL) if entL is not None else None
    print('cross phase long-at-v2-bar', phL_atR, 'v2-at-long-bar', phR_atL)
    note = (f"trans 5 {name(tL['a'])} -> {name(tL['b'])}\n"
            f"N1 long first-audible bar {entL} ({ts(entL) if entL else '?'}) phase {phL} ms; "
            f"v2 first-audible bar {entR} ({ts(entR) if entR else '?'}) phase {phR} ms")
    extra = [f"long at v2 entry bar: {phL_atR} ms; v2 at long entry bar: {phR_atL} ms",
             f"refA long {refL:.1f} v2 {refR:.1f}; threshold long {refL-24:.1f} v2 {refR-24:.1f}",
             f"incoming VdyXzg3nxfU has no per-bar nudge in nudge08_r9c.json"]
    for b in range(592, 602):
        a, c = rl.get(b, {}), rr.get(b, {})
        extra.append(f"bar {b} long A/B={a.get('A')}/{a.get('B')}  v2 A/B={c.get('A')}/{c.get('B')}")
    summary['N1_t5'] = figure_cmp(
        5, [entL or bar, entR or bar],
        'RCA: N1 trans 5 @ 13:42 VdyXzg3nxfU — long1e vs Mix 08 v2',
        note, 'rca_t5_N1_13m42.png', extra)
    summary['N1'] = dict(ent_long=entL, ent_v2=entR, phase_long=phL, phase_v2=phR,
                         phase_long_at_v2bar=phL_atR, phase_v2_at_longbar=phR_atL,
                         refA_long=refL, refA_v2=refR)

    json.dump(summary, open(OUT / 'rca_numbers.json', 'w'), indent=2, default=float)
    print('done', OUT)
