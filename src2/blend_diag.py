"""Per-blend diagnostic figure (the 2026-11-11 RCA figure made standard; the listener liked it).

For each blend: (1) our engine's per-deck curves: crossfader gain and the low band (<150 Hz) after the bass lane, with the
clash zone (both decks within 6 dB) shaded; (2) the rendered decks' measured low band and their sum (bass holes show here);
(3) the per-bar beat offset between the decks (A minus B, ms, signed xcorr of kick+snare onsets over +-half a beat, with the
half-beat verdict from halfbeat.py); (4) one bar of drum hits per deck averaged over the overlap (kick 30-150 Hz, snare
150-1500 Hz; x = beats in the bar of the mix grid). With a pro clip (daily protrans A/B) a pro panel is added: per-deck
full-band and low-band gains fitted from the stretched sources (NNLS on spectra, diagnose_gap.band_gains) and the pro's deck
lock vs ours (score.beat_identity). An optional last lane shows the diagnostic spectral collision / continuity penalties
(spectral_score.py, Manabe 2026); it is generate-only too and never fails a build.
Generate-only: it never fails a build (the half-beat gate lives in mix_simple.py and
src/build_qa/test_release_halfbeat.py).

usage (cwd src2):
  python3 blend_diag.py --meta mix08_r11c_meta.json --out ../deliver/mix08/diagnostics [--blends 0,5]
  python3 blend_diag.py --meta /tmp/protrans_bench/<tag>_dry_meta.json --out ../deliver/protrans/diagnostics --name daily_2026-11-11
         [--pro clips/.../pro.wav --src-a lib/A.m4a --src-b lib/B.m4a --ours ours.mp3]
Writes <out>/<name or blendNN_A_B>.png and .json (summary numbers)."""
import json, os, sys, copy, argparse
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
PRE, POST = 8, 8


def crop_decks(M, i, pre=PRE, post=POST):
    """the two decks of blend i cropped to [start-pre, end+post] (same crop as blend_bench.render), rendered alone"""
    import engine
    from engine import BS
    t = M['trans'][i]; A, B = M['decks'][i], M['decks'][i + 1]
    s0, s1 = int(t['start_bar']) - pre, int(t['end_bar']) + post; n = int(round((s1 - s0) * BS)); out = []
    for d in (A, B):
        j0 = max(0, s0 - d['start_bar']); j1 = min(len(d['full_map']), s1 - d['start_bar']); dd = copy.deepcopy(d)
        dd['full_map'] = d['full_map'][j0:j1]; dd['start_bar'] = d['start_bar'] + j0
        if dd.get('ib'):
            dd['ib'] = dict(dd['ib'], k0=dd['ib']['k0'] - j0, k1=dd['ib']['k1'] - j0)
        dd.pop('echo_out', None)
        y = engine.render_deck(dd) if dd['full_map'] else np.zeros((0, 2), np.float32)
        o = int(round((dd['start_bar'] - s0) * BS)); Y = np.zeros((n + int(8 * BS), 2), np.float32)
        m = max(0, min(len(y), len(Y) - o)); Y[o:o + m] = y[:m]; out.append(Y[:n])
    for k in list(engine._cache):
        engine._cache[k]['st'].clear()
    return s0, out[0], out[1]


def _curve(pts, x, default=1.0):
    if not pts:
        return np.full(len(x), default)
    return np.interp(x, [p[0] for p in pts], [p[1] for p in pts])


def engine_curves(M, i, x):
    """crossfader gain and gain*low-lane (linear) per deck at mix bars x"""
    A, B = M['decks'][i], M['decks'][i + 1]
    out = []
    for d in (A, B):
        g = _curve(d['auto'].get('gain'), x)
        lo = _curve(d['auto'].get('low'), x)
        on = (x >= d['start_bar']) & (x < d['start_bar'] + len(d['full_map']))
        out.append((g * on, g * lo * on))
    return out


def _db(v):
    return 20 * np.log10(np.maximum(v, 1e-3))


def band_bar_db(y, nbars, bs, kind=None, fc=None):
    from scipy.signal import butter, sosfiltfilt
    m = y.mean(1)
    if kind:
        m = sosfiltfilt(butter(4, fc, kind, fs=44100, output='sos'), m)
    L = int(bs); return np.array([10 * np.log10(np.mean(m[k * L:(k + 1) * L] ** 2) + 1e-12) for k in range(nbars)])


def _flux(m, lo, hi, hop=64, sr=44100):
    from scipy.signal import butter, sosfiltfilt
    sos = butter(4, [lo, hi], 'band', fs=sr, output='sos') if lo > 0 else butter(4, hi, 'low', fs=sr, output='sos')
    z = sosfiltfilt(sos, m); n = len(z) // hop
    e = np.sqrt((z[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    return np.maximum(np.diff(e, prepend=e[:1]), 0.0)


def bar_offsets(a, b, bars, bs, beat, hop=64, sr=44100):
    """signed per-bar lag (ms, + = A late) of max xcorr of kick+snare onsets over +-half a beat, 2-bar windows"""
    ma, mb = a.mean(1), b.mean(1)
    ea = _flux(ma, 30, 150) + _flux(ma, 150, 1500); eb = _flux(mb, 30, 150) + _flux(mb, 150, 1500)
    fr = sr / hop; L = int(beat / 2 * fr); out = []
    for k in bars:
        i0, i1 = int(k * bs / hop), int((k + 2) * bs / hop)
        x, y = ea[i0:i1] - ea[i0:i1].mean(), eb[i0:i1] - eb[i0:i1].mean()
        n = min(len(x), len(y))
        if n < 4 * L:
            out.append(np.nan); continue
        x, y = x[:n], y[:n]
        xc = [np.dot(x[max(0, j):n + min(0, j)], y[max(0, -j):n - max(0, j)]) for j in range(-L, L + 1)]
        out.append((int(np.argmax(xc)) - L) * 1000 / fr)
    return np.array(out)


def drum_fold(y, bars, bs, nb=64, sr=44100, hop=64):
    m = y.mean(1); K, S = _flux(m, 30, 150), _flux(m, 150, 1500); fr = sr / hop
    acc = [np.zeros(nb), np.zeros(nb)]
    for k in bars:
        idx = ((k * bs / sr + np.arange(nb) * bs / sr / nb) * fr).astype(int)
        if idx[-1] + 2 >= len(K):
            continue
        for j, e in enumerate((K, S)):
            acc[j] += np.array([e[max(0, i - 1):i + 2].max() for i in idx])
    return [a / (a.max() + 1e-12) for a in acc]


def pro_panel(pro, src_a, src_b):
    """fitted per-deck gains of the pro clip (full band and lows) from the located, stretched sources"""
    sys.path.insert(0, os.path.join(HERE, '..', 'protrans')); sys.path.insert(0, os.path.join(HERE, '..', 'src', 'eval'))
    import score as S, diagnose_gap as DG, control_curves as CC
    y = S._load(pro); Fm, em = CC.bandpow(y), S._fine_env(y); placed = []
    for p in (src_a, src_b):
        ln = S._deck_line(y, Fm, em, p)
        if not ln:
            return None
        ys = S._load(S._stretched_source(p)); ts = (np.arange(len(y)) / S.SR - ln['a']) / ln['s']
        placed.append(np.interp(ts * S.SR, np.arange(len(ys)), ys, left=0, right=0).astype(np.float32))
    gains, _, tt, _ = DG.band_gains(y, placed[0], placed[1])
    return dict(t=tt, all=(gains['all']['a'], gains['all']['b']), low=(gains['bass']['a'], gains['bass']['b']))


def figure(M, i, out_png, title=None, pro=None, src_a=None, src_b=None, ours=None):
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    from engine import BS, BAR, BEAT
    import halfbeat
    t = M['trans'][i]; s, e = float(t['start_bar']), float(t['end_bar'])
    s0, A, B = crop_decks(M, i); nbars = int(round(len(A) / BS))
    xb = s0 + np.arange(nbars * 16) / 16.0
    (gA, lA), (gB, lB) = engine_curves(M, i, xb)
    dbA, dbB = _db(gA), _db(gB); clash = (np.abs(dbA - dbB) < 6) & (dbA > -40) & (dbB > -40)
    loA, loB = band_bar_db(A, nbars, BS, 'low', 150), band_bar_db(B, nbars, BS, 'low', 150)
    sumlo = 10 * np.log10(10 ** (loA / 10) + 10 ** (loB / 10)); allA, allB = band_bar_db(A, nbars, BS), band_bar_db(B, nbars, BS)
    ref = max(np.median(allA[:PRE]), np.median(allB[-POST:]))
    bl = [k for k in range(int(s - s0), int(e - s0)) if allA[k] > ref - 20 and allB[k] > ref - 20]
    offs = bar_offsets(A, B, bl, BS, BEAT); fA, fB = drum_fold(A, bl, BS), drum_fold(B, bl, BS)
    a_id, b_id = t['a'], t['b']
    try:
        hb = t.get('halfbeat') or halfbeat.blend_check(a_id, b_id, *[w for w in halfbeat.meta_blends(M)[i][2:]])
    except Exception as ex:
        hb = dict(error=str(ex)[-120:])
    pp = None
    if pro and src_a and src_b:
        try:
            pp = pro_panel(pro, src_a, src_b)
        except Exception as ex:
            print('pro panel skipped', ex, file=sys.stderr)
    lock = None
    if pro and ours and src_a and src_b:
        try:
            sys.path.insert(0, os.path.join(HERE, '..', 'protrans')); import score as S
            yp, yo, _, _ = S.align_ours_to_pro(S._load(pro), S._load(ours)); lock = S.beat_identity(yp, yo, src_a, src_b)[1]
        except Exception as ex:
            lock = dict(error=str(ex)[-120:])
    sp = None
    try:
        import spectral_score as SS
        sp = SS.score_decks(A, B, sr=44100, bar_s=BAR, start_s=(s - s0) * BAR, end_s=(e - s0) * BAR,
                            pre_s=PRE * BAR, post_s=POST * BAR, already_gained=True)
    except Exception as ex:
        sp = dict(error=str(ex)[-160:])
    rows = (5 if pp else 4) + (1 if sp and 'collision_bar' in sp else 0)
    fig, ax = plt.subplots(rows, 1, figsize=(11, 3.1 * rows))
    k = 0
    a = ax[k]; k += 1
    a.plot(xb, dbA, color='tab:blue', label=f'A {a_id} (out) fader'); a.plot(xb, _db(lA), '--', color='tab:blue', label='A lows (<150 Hz)')
    a.plot(xb, dbB, color='tab:red', label=f'B {b_id} (in) fader'); a.plot(xb, _db(lB), '--', color='tab:red', label='B lows')
    a.fill_between(xb, -60, 3, where=clash, color='orange', alpha=0.25, label='both within 6 dB')
    a.set_ylim(-60, 3); a.set_ylabel('dB'); a.set_title(title or f"blend {i}: {t.get('tech', '')[:110]}", fontsize=9); a.legend(fontsize=7, loc='lower left'); a.grid(alpha=.3)
    if pp:
        a = ax[k]; k += 1; tb = pp['t'] / BAR + s0
        for (g, c, lab) in ((pp['all'][0], 'tab:blue', 'A fitted'), (pp['all'][1], 'tab:red', 'B fitted')):
            a.plot(tb, _db(g / max(np.percentile(g, 95), 1e-6)), color=c, label=lab)
        for (g, c, lab) in ((pp['low'][0], 'tab:blue', 'A lows'), (pp['low'][1], 'tab:red', 'B lows')):
            a.plot(tb, _db(g / max(np.percentile(g, 95), 1e-6)), '--', color=c, label=lab)
        a.set_ylim(-60, 6); a.set_ylabel('dB'); a.set_title('PRO: per-deck gains fitted from the sources (NNLS on spectra), x = pro clip in our bars', fontsize=9)
        a.legend(fontsize=7, loc='lower left'); a.grid(alpha=.3)
    a = ax[k]; k += 1; xr = s0 + np.arange(nbars)
    a.step(xr, loA, where='post', color='tab:blue', label='A lows measured'); a.step(xr, loB, where='post', color='tab:red', label='B lows measured')
    a.step(xr, sumlo, where='post', color='k', lw=2, label='summed lows')
    dip = float(np.max(sumlo[max(0, int(s - s0) - 2):int(s - s0)]) - np.min(sumlo[int(s - s0):int(e - s0)])) if e > s else 0.0
    a.set_title(f'rendered low band per bar (summed-lows dip in the blend vs just before: {dip:.1f} dB)', fontsize=9); a.set_ylabel('dB'); a.legend(fontsize=7); a.grid(alpha=.3)
    a = ax[k]; k += 1
    a.plot(np.array(bl) + s0, offs, 'o-', color='k', ms=3, label='per-bar offset A minus B (ms)')
    hb_ms = BEAT / 2 * 1000; a.axhspan(-hb_ms - 30, -hb_ms + 30, color='orange', alpha=.2); a.axhspan(hb_ms - 30, hb_ms + 30, color='orange', alpha=.2, label='half a beat')
    a.axhspan(-20, 20, color='green', alpha=.15, label='+-20 ms')
    a.set_ylim(-hb_ms - 40, hb_ms + 40); a.set_ylabel('ms'); a.legend(fontsize=7)
    vt = 'FAIL' if hb.get('fail') else 'ok'
    lk = f" | pro lock diff {lock.get('diff_ms')} ms" if lock and 'diff_ms' in lock else ''
    a.set_title(f"beat offset between decks (bars both within 20 dB) | half-beat check {vt}: drum phase A-B {hb.get('dphase_beats')} beat, "
                f"xcorr r0 {hb.get('r0')} rh {hb.get('rh')}{lk}", fontsize=9); a.grid(alpha=.3)
    a = ax[k]; k += 1; xx = np.arange(64) / 16
    a.plot(xx, fA[0], color='tab:blue', label='A kick'); a.plot(xx, fA[1], '--', color='tab:blue', label='A snare band')
    a.plot(xx, fB[0], color='tab:red', label='B kick'); a.plot(xx, fB[1], '--', color='tab:red', label='B snare band')
    a.set_xticks([0, 1, 2, 3, 4]); a.set_xlabel('beats in bar (mix grid)'); a.set_title(f'one bar of drum hits per deck, averaged over {len(bl)} overlap bars', fontsize=9); a.legend(fontsize=7); a.grid(alpha=.3)
    if sp and 'collision_bar' in sp:
        a = ax[k]; k += 1
        import spectral_score as SS
        SS.add_diag_lane(a, sp, x0_bar=s0)
    for a in ax[:-1]:
        a.set_xlabel('mix bar')
    fig.tight_layout(); os.makedirs(os.path.dirname(out_png) or '.', exist_ok=True); fig.savefig(out_png, dpi=90); plt.close(fig)
    summ = dict(blend=i, a=a_id, b=b_id, start_bar=s, end_bar=e, png=out_png, halfbeat=hb, pro_lock=lock,
                offset_ms_median=None if not len(offs) or np.all(np.isnan(offs)) else round(float(np.nanmedian(offs)), 1),
                offset_bars=len(bl), clash_bars=round(float(clash.sum() / 16), 2), sum_lows_dip_db=round(dip, 1),
                bass_swap=t.get('bass_swap'), phrase_cut=t.get('phrase_cut'))
    if sp and 'collision_bar' in sp:
        import spectral_score as SS
        summ['spectral'] = {k: SS.compact(sp)[k] for k in
                            ('diagnostic_only', 'pcol', 'pcty', 'Scol', 'Scty', 'banger_clash_rate',
                             'start_s', 'end_s', 'continuity_fallback')}
    elif sp and sp.get('error'):
        summ['spectral'] = dict(diagnostic_only=True, error=sp['error'])
    json.dump(summ, open(out_png[:-4] + '.json', 'w'), indent=1, default=float)
    return summ


def mix_diagnostics(meta_path, out_dir, blends=None):
    M = json.load(open(meta_path)); res = []
    for i in (blends if blends is not None else range(len(M['trans']))):
        t = M['trans'][i]
        try:
            res.append(figure(M, i, os.path.join(out_dir, f"blend{i:02d}_{t['a']}_{t['b']}.png")))
        except Exception as ex:
            res.append(dict(blend=i, a=t['a'], b=t['b'], error=f'{type(ex).__name__}: {ex}'[-200:]))
        print(json.dumps(res[-1], default=float)[:300], flush=True)
    json.dump(res, open(os.path.join(out_dir, 'summary.json'), 'w'), indent=1, default=float)
    return res


if __name__ == '__main__':
    os.chdir(HERE)
    ap = argparse.ArgumentParser(); ap.add_argument('--meta', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--blends'); ap.add_argument('--name'); ap.add_argument('--pro'); ap.add_argument('--src-a'); ap.add_argument('--src-b'); ap.add_argument('--ours')
    ap.add_argument('--title')
    a = ap.parse_args()
    if a.name:
        M = json.load(open(a.meta)); print(json.dumps(figure(M, 0, os.path.join(a.out, a.name + '.png'), a.title, a.pro, a.src_a, a.src_b, a.ours), default=float))
    else:
        mix_diagnostics(a.meta, a.out, [int(x) for x in a.blends.split(',')] if a.blends else None)
