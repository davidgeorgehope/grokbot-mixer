#!/usr/bin/env python3
"""Blind A/B of drumstretch vs Rubber Band (prep settings) on 16-bar drop clips.

Writes 192k MP3 pairs to deliver/drumstretch/ and a private answer key
(deliver/drumstretch/answer_key.json). Restores st/<id>.wav only when missing
and deletes those restored files again at the end.
"""
from __future__ import annotations
import json, os, sys, shutil, subprocess, tempfile, hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ST = HERE / 'st'
DELIVER = ROOT / 'deliver' / 'drumstretch'
sys.path.insert(0, str(HERE))
import drumstretch as D
import restore_audio

SR = 44100
FROM_BPM = 174.0
TO_TEMPOS = (179, 169)  # -3% / +3% duration (174->179 faster, 174->169 slower)
SEED = 20261111
PAIR_FADE_MS = 10.0

# 16-bar first-drop windows on Mix 08 liquid tracks that already have grids.
TRACKS = [
    dict(id='gbD9mt0T10g', title='Hybrid Minds – Better Now (ft. Lily Denning)',
         bar0=40, nbars=16, slug='better_now'),
    dict(id='NJ74qcCzTWw', title='Technimatic – Echoes of Us',
         bar0=48, nbars=16, slug='echoes_of_us'),
    dict(id='j9AuFRpLk7U', title='goddard. – Lilies (ft. Jazmine Johnson)',
         bar0=64, nbars=16, slug='lilies'),
]


def et_now():
    # box clock is America/New_York; label it ET so a snapshot stays zone-stable
    return datetime.now().astimezone().strftime('%Y-%m-%d %H:%M ET')


def load_grid(tid):
    return json.load(open(ST / f'{tid}.json'))


def section_bounds(grid, bar0, nbars, sr=SR):
    downs = grid['downs']
    if bar0 + nbars >= len(downs):
        raise SystemExit(f'not enough downs for bars {bar0}+{nbars} (have {len(downs)})')
    t0, t1 = float(downs[bar0]), float(downs[bar0 + nbars])
    return int(round(t0 * sr)), int(round(t1 * sr)), t0, t1


def ensure_wav(tid):
    path = ST / f'{tid}.wav'
    if path.exists():
        return False
    print(f'restore {tid}', flush=True)
    os.chdir(HERE)
    restore_audio.restore(tid)
    if not path.exists():
        raise SystemExit(f'restore_audio failed for {tid}')
    return True


def fade_edges(y, sr, ms=PAIR_FADE_MS):
    y = np.asarray(y, dtype=np.float64)
    if y.ndim == 1:
        y = y.reshape(-1, 1)
        squeeze = True
    else:
        squeeze = False
    nfade = min(int(round(ms * 1e-3 * sr)), max(0, y.shape[0] // 4))
    if nfade:
        w = np.linspace(0, 1, nfade, dtype=np.float64)
        y = y.copy()
        y[:nfade] *= w[:, None]
        y[-nfade:] *= w[::-1][:, None]
    return y[:, 0] if squeeze else y


def match_peak(y, peak):
    y = np.asarray(y, dtype=np.float64)
    cur = np.max(np.abs(y))
    if cur <= 0 or peak <= 0:
        return y
    return y * (peak / cur)


def write_mp3(y, sr, path, peak=None):
    y = np.asarray(y, dtype=np.float64)
    if peak is not None:
        y = match_peak(y, peak)
    y = np.clip(y, -1.0, 1.0)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        tmp = f.name
    try:
        sf.write(tmp, y, sr, subtype='FLOAT')
        subprocess.run(
            ['ffmpeg', '-loglevel', 'error', '-y', '-i', tmp,
             '-codec:a', 'libmp3lame', '-b:a', '192k', str(path)],
            check=True)
    finally:
        os.remove(tmp)


def rubberband_stretch(y, sr, from_bpm, to_bpm, work):
    work = Path(work)
    inn, out = work / 'rb_in.wav', work / 'rb_out.wav'
    sf.write(inn, y, sr, subtype='FLOAT')
    ratio = float(to_bpm) / float(from_bpm)
    subprocess.run(
        ['rubberband', '-3', '-F', '-T', str(ratio), '-q', str(inn), str(out)],
        check=True)
    z, zsr = sf.read(out, always_2d=True)
    if zsr != sr:
        raise SystemExit(f'rubberband sr {zsr} != {sr}')
    os.remove(inn)
    os.remove(out)
    if np.asarray(y).ndim == 1:
        z = z.mean(1) if z.shape[1] > 1 else z[:, 0]
    return z


def envelope(x, sr, win_ms=2.0):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 2:
        x = np.mean(x, axis=1)
    nwin = max(1, int(round(win_ms * 1e-3 * sr)))
    absx = np.abs(x)
    # trailing/leading pad so every window is centred
    ker = np.ones(nwin, dtype=np.float64) / nwin
    return np.convolve(absx, ker, mode='same')


def highpass(x, sr, fc=5000):
    from scipy.signal import butter, filtfilt
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 2:
        x = np.mean(x, axis=1)
    b, a = butter(2, min(fc / (sr / 2), 0.99), btype='high')
    try:
        return filtfilt(b, a, x)
    except ValueError:
        return np.diff(x, prepend=x[:1])


def attack_ms(env, peak_i, sr, pre_ms=15, post_ms=15, lo=0.2, hi=0.9):
    pre = int(round(pre_ms * 1e-3 * sr))
    post = int(round(post_ms * 1e-3 * sr))
    a, b = max(0, peak_i - pre), min(len(env), peak_i + post)
    seg = env[a:b]
    if seg.size == 0:
        return None
    pk = float(np.max(seg))
    if pk <= 1e-12:
        return None
    rel = seg / pk
    # first time we reach lo, then hi, before the peak
    peak_rel = int(np.argmax(seg))
    below = np.where(rel[:peak_rel + 1] <= lo)[0]
    above = np.where(rel[:peak_rel + 1] >= hi)[0]
    if below.size == 0 or above.size == 0:
        return None
    i0 = below[-1]
    i1 = above[0]
    if i1 <= i0:
        return None
    return (i1 - i0) / sr * 1000.0


def fwhm_ms(env, peak_i, sr, radius_ms=30):
    rad = int(round(radius_ms * 1e-3 * sr))
    a, b = max(0, peak_i - rad), min(len(env), peak_i + rad)
    seg = env[a:b]
    if seg.size == 0:
        return None
    pk = float(np.max(seg))
    if pk <= 1e-12:
        return None
    half = pk * 0.5
    rel_peak = int(np.argmax(seg))
    left = rel_peak
    while left > 0 and seg[left] >= half:
        left -= 1
    right = rel_peak
    while right < len(seg) - 1 and seg[right] >= half:
        right += 1
    return (right - left) / sr * 1000.0


def energy(x):
    x = np.asarray(x, dtype=np.float64)
    return float(np.sum(x * x))


def local_peak(x, center, sr, radius_ms=5):
    rad = int(round(radius_ms * 1e-3 * sr))
    a, b = max(0, center - rad), min(len(x) if x.ndim == 1 else x.shape[0], center + rad + 1)
    if b <= a:
        return 0.0, center
    if x.ndim == 2:
        mag = np.max(np.abs(x[a:b]), axis=1)
    else:
        mag = np.abs(x[a:b])
    i = int(np.argmax(mag))
    return float(mag[i]), a + i


def aligned_xcorr(ref, out_mono, expected_start, sr, max_ms=8):
    """Normalized correlation of `ref` against `out_mono`, searching ±max_ms around expected_start.

    `expected_start` is the sample in `out_mono` where `ref[0]` should sit (lag 0).
    Returns (lag_samples, peak_score).
    """
    ref = np.asarray(ref, dtype=np.float64)
    out_mono = np.asarray(out_mono, dtype=np.float64)
    L = len(ref)
    if L < 8:
        return 0, 0.0
    ref0 = ref - ref.mean()
    rn = np.linalg.norm(ref0)
    if rn < 1e-12:
        return 0, 0.0
    maxlag = int(round(max_ms * 1e-3 * sr))
    best_score, best_lag = -1.0, 0
    nout = len(out_mono)
    for lag in range(-maxlag, maxlag + 1):
        a = int(expected_start) + lag
        b = a + L
        if a < 0 or b > nout:
            continue
        c = out_mono[a:b]
        c0 = c - c.mean()
        cn = np.linalg.norm(c0)
        if cn < 1e-12:
            continue
        score = float(np.dot(ref0, c0) / (rn * cn))
        if score > best_score:
            best_score, best_lag = score, lag
    if best_score < 0:
        return 0, 0.0
    return best_lag, best_score


def measure(orig, stretched, sr, onsets, alpha, name):
    """Objective numbers for one stretched clip vs the original section."""
    o, _ = D.as_nc(orig)
    s, _ = D.as_nc(stretched)
    o_mono = o.mean(1)
    s_mono = s.mean(1)
    env_o = envelope(o_mono, sr)
    env_s = envelope(s_mono, sr)
    hp_o = highpass(o_mono, sr, 5000)
    hp_s = highpass(s_mono, sr, 5000)
    nout = s.shape[0]
    rows = []
    for onset in onsets:
        onset = int(onset)
        if onset < int(0.02 * sr) or onset >= o.shape[0] - int(0.02 * sr):
            continue
        exp = D.out_onset(onset, alpha)
        if exp < int(0.02 * sr) or exp >= nout - int(0.02 * sr):
            continue
        pk_o, i_o = local_peak(o_mono, onset, sr, 5)
        pk_s, i_s = local_peak(s_mono, exp, sr, 8)
        # finer timing: xcorr of the 20 ms hit (4 ms pre + 16 ms post) around the onset
        pre, post = int(round(0.004 * sr)), int(round(0.016 * sr))
        if onset < pre or onset + post > o_mono.shape[0]:
            continue
        ref = o_mono[onset - pre:onset + post]
        lag, corr = aligned_xcorr(ref, s_mono, exp - pre, sr, max_ms=8)
        found = exp + lag
        timing_ms = (found - exp) / sr * 1000.0
        att_o = attack_ms(env_o, i_o, sr)
        att_s = attack_ms(env_s, i_s, sr)
        w_o = fwhm_ms(env_o, i_o, sr)
        w_s = fwhm_ms(env_s, i_s, sr)
        # pre-echo: energy in 15 ms before the onset vs first 5 ms of the hit
        pre15, hit5 = int(round(0.015 * sr)), int(round(0.005 * sr))
        e_pre_o = energy(o_mono[onset - pre15:onset])
        e_hit_o = energy(o_mono[onset:onset + hit5]) + 1e-20
        e_pre_s = energy(s_mono[found - pre15:found])
        e_hit_s = energy(s_mono[found:found + hit5]) + 1e-20
        pre_echo_db = 10 * np.log10((e_pre_s / e_hit_s + 1e-20) / (e_pre_o / e_hit_o + 1e-20))
        hf_o = energy(hp_o[onset:onset + int(round(0.008 * sr))]) + 1e-20
        hf_s = energy(hp_s[found:found + int(round(0.008 * sr))]) + 1e-20
        rows.append(dict(
            onset=onset, expected=exp, found=int(found),
            timing_ms=float(timing_ms),
            peak_ratio=float(pk_s / (pk_o + 1e-20)),
            xcorr=float(corr),
            attack_ms_orig=None if att_o is None else float(att_o),
            attack_ms_out=None if att_s is None else float(att_s),
            fwhm_ms_orig=None if w_o is None else float(w_o),
            fwhm_ms_out=None if w_s is None else float(w_s),
            pre_echo_db=float(pre_echo_db),
            hf_ratio=float(hf_s / hf_o),
        ))
    if not rows:
        return dict(method=name, n_hits=0)
    def col(key):
        return np.array([r[key] for r in rows], dtype=np.float64)
    def col_ok(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return np.array(vals, dtype=np.float64)
    timing = np.abs(col('timing_ms'))
    att_o, att_s = col_ok('attack_ms_orig'), col_ok('attack_ms_out')
    f_o, f_s = col_ok('fwhm_ms_orig'), col_ok('fwhm_ms_out')
    # paired attack/fwhm deltas where both exist
    att_delta = []
    fwhm_delta = []
    for r in rows:
        if r['attack_ms_orig'] is not None and r['attack_ms_out'] is not None:
            att_delta.append(r['attack_ms_out'] - r['attack_ms_orig'])
        if r['fwhm_ms_orig'] is not None and r['fwhm_ms_out'] is not None:
            fwhm_delta.append(r['fwhm_ms_out'] - r['fwhm_ms_orig'])
    out = dict(
        method=name,
        n_hits=len(rows),
        timing_abs_median_ms=float(np.median(timing)),
        timing_abs_p95_ms=float(np.percentile(timing, 95)),
        peak_ratio_median=float(np.median(col('peak_ratio'))),
        xcorr_median=float(np.median(col('xcorr'))),
        attack_delta_median_ms=None if not att_delta else float(np.median(att_delta)),
        fwhm_delta_median_ms=None if not fwhm_delta else float(np.median(fwhm_delta)),
        pre_echo_db_median=float(np.median(col('pre_echo_db'))),
        hf_ratio_median=float(np.median(col('hf_ratio'))),
        length_in=int(o.shape[0]),
        length_out=int(s.shape[0]),
        length_expected=D.expected_length(o.shape[0], alpha),
    )
    return out


def grid_timing(stretched, sr, beats, t0, alpha, name):
    """How far detected output hits sit from the tempo-scaled beat grid, in ms."""
    s, _ = D.as_nc(stretched)
    onsets = D.detect_hits(s, sr)
    if onsets.size == 0 or len(beats) == 0:
        return dict(method=name, grid_n=0)
    # expected beat times in the output, relative to the start of the clip
    exp = np.array([(b - t0) * alpha * sr for b in beats], dtype=np.float64)
    err = []
    for e in exp:
        if e < 0 or e >= s.shape[0]:
            continue
        j = int(np.argmin(np.abs(onsets - e)))
        err.append(abs(onsets[j] - e) / sr * 1000.0)
    if not err:
        return dict(method=name, grid_n=0)
    err = np.array(err)
    return dict(
        method=name,
        grid_n=int(len(err)),
        grid_abs_median_ms=float(np.median(err)),
        grid_abs_p95_ms=float(np.percentile(err, 95)),
    )


def summarize(m, g):
    """Plain-words metric dict for the answer key."""
    d = dict(m)
    d.update({k: v for k, v in g.items() if k != 'method'})
    return d


def main():
    os.chdir(HERE)
    DELIVER.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    restored = []
    pairs = []
    work = Path(tempfile.mkdtemp(prefix='drumstretch_ab_'))
    try:
        pair_i = 0
        for tr in TRACKS:
            tid = tr['id']
            if ensure_wav(tid):
                restored.append(tid)
            wav = ST / f'{tid}.wav'
            info = sf.info(str(wav))
            if info.samplerate != SR:
                raise SystemExit(f'{tid} sr={info.samplerate}, expected {SR}')
            grid = load_grid(tid)
            i0, i1, t0, t1 = section_bounds(grid, tr['bar0'], tr['nbars'], SR)
            y, sr = sf.read(str(wav), always_2d=True, start=i0, stop=i1)
            if sr != SR:
                raise SystemExit(f'{tid} read sr {sr}')
            y = np.asarray(y, dtype=np.float64)
            # onsets relative to the clip
            onsets = D.detect_hits(y, SR)
            beats = [b for b in grid['beats'] if t0 - 1e-6 <= b < t1 - 1e-6]
            dur_s = y.shape[0] / SR
            print(f"{tr['title']}: bars {tr['bar0']}-{tr['bar0']+tr['nbars']} "
                  f"{dur_s:.2f}s  hits={len(onsets)}  beats={len(beats)}", flush=True)
            for to_bpm in TO_TEMPOS:
                alpha = FROM_BPM / float(to_bpm)
                pair_i += 1
                print(f'  stretch {FROM_BPM:g} -> {to_bpm} (alpha={alpha:.6f})', flush=True)
                ds, ds_info = D.stretch(y, SR, alpha, onsets=onsets)
                rb = rubberband_stretch(y, SR, FROM_BPM, to_bpm, work)
                # length of rubberband may differ by a hop; leave as produced
                m_ds = measure(y, ds, SR, onsets, alpha, 'drumstretch')
                m_rb = measure(y, rb, SR, onsets, alpha, 'rubberband')
                g_ds = grid_timing(ds, SR, beats, t0, alpha, 'drumstretch')
                g_rb = grid_timing(rb, SR, beats, t0, alpha, 'rubberband')
                # listening copies: same peak, short edge fades
                peak = 0.89  # ~ -1 dBFS
                ds_l = fade_edges(ds, SR)
                rb_l = fade_edges(rb, SR)
                # coin flip for A/B
                ds_is_a = bool(rng.integers(0, 2))
                a_y, b_y = (ds_l, rb_l) if ds_is_a else (rb_l, ds_l)
                a_method = 'drumstretch' if ds_is_a else 'rubberband'
                b_method = 'rubberband' if ds_is_a else 'drumstretch'
                tag = f"{pair_i:02d}_{tr['slug']}_{int(to_bpm)}bpm"
                fa = DELIVER / f'{tag}_A.mp3'
                fb = DELIVER / f'{tag}_B.mp3'
                write_mp3(a_y, SR, fa, peak=peak)
                write_mp3(b_y, SR, fb, peak=peak)
                pairs.append(dict(
                    id=pair_i,
                    tag=tag,
                    title=tr['title'],
                    youtube_id=tid,
                    youtube=f'https://youtu.be/{tid}',
                    section=f"bars {tr['bar0']}-{tr['bar0']+tr['nbars']} (first drop), 16 bars",
                    bar0=tr['bar0'],
                    nbars=tr['nbars'],
                    t0=t0, t1=t1,
                    input_seconds=round(dur_s, 3),
                    from_bpm=FROM_BPM,
                    to_bpm=to_bpm,
                    stretch_factor=alpha,
                    n_hits=int(len(onsets)),
                    files={'A': str(fa.relative_to(ROOT)), 'B': str(fb.relative_to(ROOT))},
                    A=a_method,
                    B=b_method,
                    metrics={'drumstretch': summarize(m_ds, g_ds),
                             'rubberband': summarize(m_rb, g_rb)},
                    drumstretch_length=int(np.asarray(ds).shape[0]),
                    rubberband_length=int(np.asarray(rb).shape[0]),
                    expected_length=D.expected_length(y.shape[0], alpha),
                ))
                print(f"    wrote {fa.name} / {fb.name}  A={a_method} B={b_method}", flush=True)
                for label, m, g in (('drumstretch', m_ds, g_ds), ('rubberband', m_rb, g_rb)):
                    print(
                        f"    {label}: timing med {m.get('timing_abs_median_ms')} ms  "
                        f"p95 {m.get('timing_abs_p95_ms')} ms  "
                        f"peak {m.get('peak_ratio_median')}  xcorr {m.get('xcorr_median')}  "
                        f"pre-echo {m.get('pre_echo_db_median')} dB  "
                        f"grid med {g.get('grid_abs_median_ms')} ms",
                        flush=True)
        key = dict(
            seed=SEED,
            created=et_now(),
            method_notes=(
                'A/B is Rubber Band R3 (rubberband -3 -F -T to/from, the same flags prep.py uses) '
                'vs drumstretch.py (Tero: sample-exact hits, HPSS on decays, OLA on noise, '
                'phase vocoder on tonal ring; Fitzgerald 2010 / Driedger, Müller and Ewert 2014 / libtsm). '
                'A/B order is randomized with the seed above. Keep this file from the listening notes.'
            ),
            from_bpm=FROM_BPM,
            to_tempos=list(TO_TEMPOS),
            tracks=TRACKS,
            restored_and_deleted=restored,
            pairs=pairs,
        )
        key_path = DELIVER / 'answer_key.json'
        key_path.write_text(json.dumps(key, indent=2, sort_keys=False))
        # a listener sheet that does not reveal the key
        lines = [
            '# Drum stretch A/B clips',
            '',
            'Each pair is the same 16-bar drop, stretched to a nearby DJ tempo.',
            'A and B are the two stretchers. Peak-matched 192k MP3, order randomized.',
            '',
        ]
        for p in pairs:
            lines.append(f"{p['id']:02d}. {p['title']}  → {int(p['to_bpm'])} BPM")
            lines.append(f"    {p['section']}")
            lines.append(f"    A: {p['files']['A']}")
            lines.append(f"    B: {p['files']['B']}")
            lines.append('')
        (DELIVER / 'listen.md').write_text('\n'.join(lines))
        print(f'KEY {key_path}', flush=True)
        print(f'PAIRS {len(pairs)}', flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        for tid in restored:
            p = ST / f'{tid}.wav'
            if p.exists():
                p.unlink()
                print(f'deleted restored {p}', flush=True)
            # also drop a decoded wav/ we created if we were the ones who made it
            # restore_audio writes wav/<id>.wav only when missing; if we created it, leave
            # it only when it already existed. We cannot know cheaply if we created wav/,
            # so leave wav/ caches alone unless this process created them and they are
            # unused. restore() skips wav creation when the file already exists; we only
            # delete st wavs we restored, as requested.


if __name__ == '__main__':
    main()
