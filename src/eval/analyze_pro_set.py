#!/usr/bin/env python3
"""Blind transition analysis of a continuous DJ set (no reference tracks).

Pipeline per set:
  1. beat grid (librosa, DnB tempo prior) -> bars (downbeat phase from kick/low band)
  2. bar-synchronous features: MFCC (timbre), chroma (harmony), bass chroma (40-250 Hz),
     band energies (low <150 Hz, mid, high >3 kHz)
  3. Foote novelty on a bar-level self-similarity matrix + long-window "identity" distance
     (32 bars before vs after) -> candidate track changes
  4. per transition: overlap length (bars where the mix resembles neither pure-pre nor pure-post),
     bass-swap bar + sharpness from bass-chroma crossover, low-band dip, key change (Camelot),
     beat clarity during the overlap vs. outside, energy delta, phrase alignment (swap bar vs grid
     and vs incoming drop), vocal activity across the overlap (demucs, windowed, cached)
  5. heuristic technique label: cut / short blend / long blend / double drop / breakdown-entry(echo/fx)
Outputs <out_dir>/<name>.json  (per-transition list + set-level summary).

Limitations (honest): without the original tracks, track boundaries are inferred; intra-track
breakdowns can produce false positives and smooth same-key blends can be missed. Technique labels
are heuristics, not ground truth.
"""
import argparse, json, os, subprocess, sys, hashlib
import numpy as np, librosa, scipy.signal as ss, soundfile as sf

SR = 22050
HOP = 512
KEYS_MAJ = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
KEYS_MIN = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])
CAM_MAJ = [8,3,10,5,12,7,2,9,4,11,6,1]   # C..B major -> Camelot number (B)
CAM_MIN = [5,12,7,2,9,4,11,6,1,8,3,10]   # C..B minor -> Camelot number (A)

def key_of(chroma_mean):
    best = (-9, None)
    for mode, prof, cam in (('B', KEYS_MAJ, CAM_MAJ), ('A', KEYS_MIN, CAM_MIN)):
        for k in range(12):
            r = np.corrcoef(np.roll(prof, k), chroma_mean)[0, 1]
            if r > best[0]: best = (r, f"{cam[k]}{mode}")
    return best[1], float(best[0])

def camelot_dist(a, b):
    if not a or not b: return None
    na, ma, nb, mb = int(a[:-1]), a[-1], int(b[:-1]), b[-1]
    d = min((na-nb) % 12, (nb-na) % 12)
    return d + (0 if ma == mb else 1) if not (d == 0 and ma != mb) else 1

def band_env(S, freqs, lo, hi):
    m = (freqs >= lo) & (freqs < hi)
    return S[m].sum(0)

def zn(x):
    x = x - x.mean(1, keepdims=True); n = np.linalg.norm(x, axis=0, keepdims=True) + 1e-9
    return x / n

def analyze(path, name, out_dir, bpm_prior=174.0, demucs=True, min_gap_bars=24, cache_dir=None, anchors=None, anchor_win=45.0):
    y, sr = librosa.load(path, sr=SR, mono=True)
    dur = len(y) / SR
    # ---- beat grid
    oenv = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP, aggregate=np.median)
    tempo, beats = librosa.beat.beat_track(onset_envelope=oenv, sr=SR, hop_length=HOP,
                                           start_bpm=bpm_prior, tightness=400, trim=False)
    bt = librosa.frames_to_time(beats, sr=SR, hop_length=HOP)
    ibi = np.diff(bt); med = np.median(ibi)
    if med > 0.5:  # tracked half-time (87 BPM) -> interpolate
        bt = np.sort(np.concatenate([bt, bt[:-1] + ibi / 2])); ibi = np.diff(bt); med = np.median(ibi)
    o2 = librosa.onset.onset_strength(y=y, sr=SR, hop_length=128, aggregate=np.median)
    _, b2 = librosa.beat.beat_track(onset_envelope=o2, sr=SR, hop_length=128, bpm=60/med, tightness=400, trim=False)
    bt2 = librosa.frames_to_time(b2, sr=SR, hop_length=128); i2 = np.diff(bt2); i2 = i2[(i2 > 0.25) & (i2 < 0.45)]
    if len(i2) > 100: bt, ibi = bt2, np.diff(bt2)
    q = ibi[(ibi > np.percentile(ibi, 10)) & (ibi < np.percentile(ibi, 90))]
    med = float(q.mean()) if len(q) else med
    bpm = 60 / med  # mean, not median: hop quantization biases the median
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=SR, n_fft=2048)
    low = band_env(S, freqs, 20, 150); mid = band_env(S, freqs, 150, 3000); high = band_env(S, freqs, 3000, 11000)
    bf = librosa.time_to_frames(bt, sr=SR, hop_length=HOP)
    bf = bf[bf < S.shape[1]]
    # downbeat phase: DnB kick on beat 1 -> low-band onset strongest at phase 0
    lo_on = np.maximum(0, np.diff(np.log(low + 1e-6), prepend=0))
    ph_score = [lo_on[bf[p::4]].mean() for p in range(4)]
    phase = int(np.argmax(ph_score))
    bar_f = bf[phase::4]
    nb = len(bar_f) - 1
    bar_t = librosa.frames_to_time(bar_f, sr=SR, hop_length=HOP)
    # ---- bar features
    mfcc = librosa.feature.mfcc(S=librosa.power_to_db(librosa.feature.melspectrogram(S=S**2, sr=SR, n_mels=64)), n_mfcc=20)
    chroma = librosa.feature.chroma_stft(S=S**2, sr=SR)
    Sb = S.copy(); Sb[(freqs < 40) | (freqs > 250)] = 0
    bchroma = librosa.feature.chroma_stft(S=Sb**2, sr=SR)
    def sync(F, agg=np.mean): return librosa.util.sync(F, bar_f, aggregate=agg)[:, 1:nb+1] if False else np.stack([agg(F[:, bar_f[i]:bar_f[i+1]], axis=1) for i in range(nb)], 1)
    M, C, B = sync(mfcc), sync(chroma), sync(bchroma)
    E = np.stack([sync(x[None])[0] for x in (low, mid, high)])
    Edb = 10 * np.log10(E + 1e-9); Edb -= Edb.max(1, keepdims=True)
    rms_db = 10 * np.log10(E.sum(0) + 1e-9); rms_db -= np.percentile(rms_db, 95)
    # beat clarity per bar: autocorr of onset env at beat lag within bar-pair windows
    lag = int(round(med * SR / HOP))
    clar = np.zeros(nb)
    for i in range(nb):
        a, b = bar_f[max(0, i-1)], bar_f[min(nb, i+2)]
        seg = oenv[a:b] - oenv[a:b].mean()
        den = (seg**2).sum() + 1e-9
        clar[i] = max((seg[:-lag] * seg[lag:]).sum() / den, 0) if len(seg) > 2*lag else 0
    F = np.vstack([zn(M), zn(C) * 0.8])
    F = zn(F)
    SSM = F.T @ F
    # Foote novelty, kernel 16 bars
    K = 16; g = ss.windows.gaussian(2*K, K/2); ker = np.outer(g, g) * np.block([[np.ones((K,K)), -np.ones((K,K))], [-np.ones((K,K)), np.ones((K,K))]])
    nov = np.zeros(nb)
    for i in range(K, nb-K): nov[i] = (SSM[i-K:i+K, i-K:i+K] * ker).sum()
    # long-window identity distance (32 bars each side, skipping 8 around the point)
    ident = np.zeros(nb); W, G = 32, 8
    Fc = np.vstack([zn(M), zn(C)])
    for i in range(W+G, nb-W-G):
        pre = Fc[:, i-G-W:i-G].mean(1); post = Fc[:, i+G:i+G+W].mean(1)
        ident[i] = 1 - pre @ post / (np.linalg.norm(pre)*np.linalg.norm(post) + 1e-9)
    score = (nov / (nov.max()+1e-9)) * 0.5 + (ident / (ident.max()+1e-9)) * 0.5
    score = ss.savgol_filter(score, 9, 2)
    peaks, _ = ss.find_peaks(score, distance=min_gap_bars, prominence=0.04)
    thr = np.percentile(score[score > 0], 55)
    if anchors:  # tracklist timestamps: best novelty within +-anchor_win s of each
        peaks = []
        for a in anchors:
            m = np.where(np.abs(bar_t[:nb] - a) <= anchor_win)[0]
            m = m[(m > 40) & (m < nb - 40)]
            if len(m): peaks.append(int(m[np.argmax(score[m])]))
        peaks = sorted(set(peaks)); mode = 'anchored'
    else:   # blind: stricter, identity change must be in top 30% of the set
        peaks = [p for p in peaks if score[p] > thr and ident[p] > np.percentile(ident[ident > 0], 70)]; mode = 'blind'
    trans = []
    for p in peaks:
        a0, a1 = max(0, p-56), max(1, p-24); b0, b1 = min(nb-1, p+24), min(nb, p+56)
        if a1 - a0 < 8 or b1 - b0 < 8: continue
        tp, tq = Fc[:, a0:a1].mean(1), Fc[:, b0:b1].mean(1)
        w0, w1 = max(0, p-40), min(nb, p+40)
        sp = np.array([Fc[:, i] @ tp / (np.linalg.norm(tp)+1e-9) for i in range(w0, w1)])
        sq = np.array([Fc[:, i] @ tq / (np.linalg.norm(tq)+1e-9) for i in range(w0, w1)])
        mix = ss.savgol_filter(sq - sp, 5, 1)
        lo_m, hi_m = np.percentile(mix, 10), np.percentile(mix, 90)
        rng = hi_m - lo_m + 1e-9; frac = (mix - lo_m) / rng
        # overlap = bars between last 'pure pre' (<0.2) and first 'pure post' (>0.8) around p
        c = p - w0
        pre_idx = np.where(frac[:c+1] < 0.2)[0]; post_idx = np.where(frac[c:] > 0.8)[0]
        s_bar = w0 + (pre_idx[-1] + 1 if len(pre_idx) else 0)
        e_bar = w0 + c + (post_idx[0] if len(post_idx) else len(frac) - c - 1)
        overlap = int(max(0, e_bar - s_bar))
        # bass swap: bass-chroma crossover
        bp, bq = B[:, a0:a1].mean(1), B[:, b0:b1].mean(1)
        bsp = np.array([np.corrcoef(B[:, i], bp)[0, 1] for i in range(w0, w1)])
        bsq = np.array([np.corrcoef(B[:, i], bq)[0, 1] for i in range(w0, w1)])
        bd = np.convolve(np.nan_to_num(bsq - bsp), np.ones(3)/3, mode="same")
        cross = np.where((bd[:-1] < 0) & (bd[1:] >= 0))[0]
        if len(cross):
            ci = cross[np.argmin(np.abs(cross - c))]; swap_bar = int(w0 + ci + 1)
            # sharpness: bars from 25% to 75% of bass-identity change
            bf_ = (bd - np.percentile(bd, 10)) / (np.percentile(bd, 90) - np.percentile(bd, 10) + 1e-9)
            l = ci
            while l > 0 and bf_[l] > 0.25: l -= 1
            r = ci + 1
            while r < len(bf_)-1 and bf_[r] < 0.75: r += 1
            swap_len = int(r - l)
        else:
            swap_bar, swap_len = None, None
        win = slice(max(0, s_bar-2), min(nb, e_bar+3))
        low_dip = float(Edb[0, win].min() - np.median(Edb[0, a0:a1]))
        energy_delta = float(np.median(rms_db[b0:b1]) - np.median(rms_db[a0:a1]))
        ov = slice(s_bar, max(s_bar+1, e_bar))
        clar_ov = float(np.mean(clar[ov])); clar_out = float(np.median(np.r_[clar[a0:a1], clar[b0:b1]]))
        kp, kpc = key_of(C[:, a0:a1].mean(1)); kq, kqc = key_of(C[:, b0:b1].mean(1))
        # energy level at overlap relative to set: both sides at drop level?
        hi_lvl = float(np.median(rms_db[ov]))
        # incoming drop: first bar after s_bar where low band jumps > 6 dB over 2 bars
        drop_bar = None
        for i in range(s_bar, min(nb-2, e_bar+48)):
            if Edb[0, i] - Edb[0, max(0, i-2)] > 6 and Edb[0, i] > -10: drop_bar = i; break
        rec = dict(bar=int(p), time_sec=round(float(bar_t[p]), 2), score=round(float(score[p]), 3),
                   start_sec=round(float(bar_t[s_bar]), 2), end_sec=round(float(bar_t[min(e_bar, nb)]), 2),
                   overlap_bars=overlap, swap_bar=swap_bar,
                   swap_sec=round(float(bar_t[swap_bar]), 2) if swap_bar is not None else None,
                   swap_len_bars=swap_len, swap_pos_in_overlap=(round((swap_bar - s_bar) / overlap, 2) if swap_bar is not None and overlap > 0 else None),
                   swap_bar_mod8=(int(swap_bar % 8) if swap_bar is not None else None),
                   drop_bar=drop_bar, swap_to_drop_bars=(int(drop_bar - swap_bar) if drop_bar is not None and swap_bar is not None else None),
                   low_dip_db=round(low_dip, 1), energy_delta_db=round(energy_delta, 1), overlap_level_db=round(hi_lvl, 1),
                   beat_clarity_overlap=round(clar_ov, 3), beat_clarity_outside=round(clar_out, 3),
                   beat_clarity_ratio=round(clar_ov / (clar_out + 1e-9), 3),
                   key_out=kp, key_in=kq, camelot_dist=camelot_dist(kp, kq))
        trans.append(rec)
    # ---- vocals (demucs on overlap windows, max 32 bars)
    if demucs and trans:
        cache_dir = cache_dir or os.path.join(out_dir, 'demucs_cache', name)
        os.makedirs(cache_dir, exist_ok=True)
        for t in trans:
            s = max(0, t['start_sec'] - 2); e = min(dur, max(t['end_sec'], t['start_sec'] + 8 * 4 * 60 / bpm) + 2)
            e = min(e, s + 32 * 4 * 60 / bpm)
            tag = f"{int(s*100)}_{int(e*100)}"; voc = os.path.join(cache_dir, f"{tag}_vocals.npy")
            if not os.path.exists(voc):
                tmp = os.path.join(cache_dir, f"{tag}.wav")
                seg = librosa.resample(y[int(s*SR):int(e*SR)], orig_sr=SR, target_sr=44100)
                sf.write(tmp, seg, 44100)
                subprocess.run([sys.executable, '-m', 'demucs', '--two-stems=vocals', '-n', 'htdemucs', '-j', '2',
                                '-o', cache_dir, tmp], check=True, capture_output=True)
                vy, _ = librosa.load(os.path.join(cache_dir, 'htdemucs', tag, 'vocals.wav'), sr=SR)
                ay, _ = librosa.load(os.path.join(cache_dir, 'htdemucs', tag, 'no_vocals.wav'), sr=SR)
                np.save(voc, np.stack([vy[:len(ay)], ay[:len(vy)]]))
                os.remove(tmp)
            vy, ay = np.load(voc)
            bar_s = 4 * 60 / bpm; n = int(len(vy) / SR / bar_s)
            vr = np.array([np.sqrt(np.mean(vy[int(i*bar_s*SR):int((i+1)*bar_s*SR)]**2)) for i in range(n)])
            ar = np.array([np.sqrt(np.mean(ay[int(i*bar_s*SR):int((i+1)*bar_s*SR)]**2)) for i in range(n)])
            vrel = 20 * np.log10((vr + 1e-9) / (ar + 1e-9))
            active = vrel > -12
            t['vocal_active_frac_overlap'] = round(float(active.mean()), 2) if n else None
            # chroma-based clash proxy: vocal stem pitch-class spread (two singers -> flatter chroma)
            if active.any():
                vc = librosa.feature.chroma_stft(y=vy, sr=SR)
                ent = []
                for i in np.where(active)[0]:
                    seg = vc[:, int(i*bar_s*SR/HOP):int((i+1)*bar_s*SR/HOP)].mean(1); pdist = seg / (seg.sum() + 1e-9)
                    ent.append(float(-(pdist * np.log2(pdist + 1e-9)).sum()))
                t['vocal_chroma_entropy'] = round(float(np.mean(ent)), 3)
            else:
                t['vocal_chroma_entropy'] = None
    # ---- classify
    for t in trans:
        ov = t['overlap_bars']; tags = []
        if ov <= 2: tags.append('cut')
        elif ov < 16: tags.append('short_blend')
        elif ov < 32: tags.append('16_bar_blend')
        else: tags.append('32plus_bar_blend')
        if t['overlap_level_db'] > -4 and t['low_dip_db'] > -6 and ov >= 4: tags.append('double_drop_or_drop_blend')
        if t['low_dip_db'] < -12: tags.append('breakdown_or_echo_entry')
        if t['swap_len_bars'] is not None and t['swap_len_bars'] <= 2: tags.append('hard_bass_swap')
        if t.get('vocal_active_frac_overlap') and t['vocal_active_frac_overlap'] > 0.5: tags.append('vocal_over_transition')
        if t['beat_clarity_ratio'] < 0.6: tags.append('beat_clarity_drop')
        t['techniques'] = tags
    # ---- set summary
    arc = [round(float(np.median(rms_db[i:i+43])), 1) for i in range(0, nb, 43)]  # ~1 min bins
    gaps = np.diff([t['time_sec'] for t in trans]) if len(trans) > 1 else np.array([])
    out = dict(name=name, path=path, detection=mode, anchors=anchors, duration_sec=round(dur, 1), bpm=round(bpm, 2), n_bars=nb,
               n_transitions=len(trans), median_track_time_sec=round(float(np.median(gaps)), 1) if len(gaps) else None,
               energy_arc_db_per_min=arc, transitions=trans,
               curves=dict(bar_t=[round(float(x),2) for x in bar_t[:nb]], score=[round(float(x),4) for x in score], ident=[round(float(x),4) for x in ident], nov=[round(float(x),3) for x in nov]))
    os.makedirs(out_dir, exist_ok=True)
    json.dump(out, open(os.path.join(out_dir, f"{name}.json"), 'w'), indent=1)
    return out

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('audio'); ap.add_argument('--name'); ap.add_argument('--out', default='/workspace/mixes/eval/sets')
    ap.add_argument('--no-demucs', action='store_true'); ap.add_argument('--anchors', help='comma-separated seconds from a tracklist'); ap.add_argument('--bpm', type=float, default=174)
    a = ap.parse_args()
    o = analyze(a.audio, a.name or os.path.splitext(os.path.basename(a.audio))[0], a.out, a.bpm, not a.no_demucs, anchors=[float(x) for x in a.anchors.split(',')] if a.anchors else None)
    print(o['name'], o['bpm'], o['n_transitions'], o['median_track_time_sec'])
