"""Label pro-transition phases and write frequency-weighted priors (train only)."""
from __future__ import annotations
import json, os, sys, collections, math
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import structure as S
import version_match as VM
import paths

PRE = 24.0
ST = os.path.join(paths.SRC2, 'st')
BAR = S.BAR_SEC


def compute_bar_from_wav(wav, bpm=174.0):
    """Private bar energy if st/*.json is truncated. Does not write src2."""
    import subprocess
    from scipy.signal import butter, sosfilt
    sr = 44100
    raw = subprocess.run(['ffmpeg','-v','error','-i',wav,'-ac','1','-ar',str(sr),'-f','f32le','-'],
                         capture_output=True, check=True).stdout
    y = np.frombuffer(raw, np.float32).copy()
    bar = 4 * 60 / float(bpm)
    n = int(len(y) / sr / bar)
    def band(lo, hi):
        sos = butter(4, [lo, hi], 'band', fs=sr, output='sos') if lo > 0 else butter(4, hi, 'low', fs=sr, output='sos')
        return sosfilt(sos, y) ** 2
    Eall = y ** 2
    Elow = band(0, 150)
    drums = []; bass = []
    for i in range(n):
        i0 = int(i * bar * sr); i1 = int((i + 1) * bar * sr)
        if i1 > len(y):
            break
        drums.append(float(10 * np.log10(Eall[i0:i1].mean() + 1e-10)))
        bass.append(float(10 * np.log10(Elow[i0:i1].mean() + 1e-10)))
    return dict(drums=np.asarray(drums, float), bass=np.asarray(bass, float), n=len(drums))

_BAR_CACHE = {}
def load_bar_safe(yt):
    if yt in _BAR_CACHE:
        return _BAR_CACHE[yt]
    st_js = os.path.join(ST, f'{yt}.json')
    try:
        bar = S.load_bar(st_js)
    except Exception as e:
        wav = os.path.join(ST, f'{yt}.wav')
        print(f'  fallback bars for {yt}: {e}', flush=True)
        bar = compute_bar_from_wav(wav)
    _BAR_CACHE[yt] = bar
    return bar

def clip_path(rec):
    return os.path.join(paths.CLIPS, rec['split'], rec['id'], 'pro.wav')

def mixin_t(rec):
    meta = os.path.join(paths.CLIPS, rec['split'], rec['id'], 'meta.json')
    t_b = float(rec['t_b'])
    t0 = max(0.0, t_b - PRE)
    if os.path.exists(meta):
        try:
            m = json.load(open(meta))
            t0 = float(m.get('pro_clip_start', t0))
        except Exception:
            pass
    return t_b - t0  # listed incoming time inside the clip

def sl(y, t, dur, sr=VM.SR):
    i0 = int(round(t * sr)); i1 = int(round((t + dur) * sr))
    if i0 < 0 or i1 > len(y) or i1 - i0 < sr // 4:
        return None
    return y[i0:i1]

def bar_cc(mix, src, mix_t, track_t, t, sr=VM.SR, bar=BAR):
    s = sl(src, track_t + (t - mix_t), bar * 2, sr)
    m = sl(mix, t, bar * 2, sr)
    if s is None or m is None:
        return None
    n = min(len(s), len(m)); s = s[:n]; m = m[:n]
    s0 = s - s.mean(); m0 = m - m.mean()
    return float(np.dot(s0, m0) / (np.linalg.norm(s0) * np.linalg.norm(m0) + 1e-12))

def bar_proj_db(mix, src, mix_t, track_t, t, sr=VM.SR, bar=BAR):
    """Projected outgoing level in the mix (survives an incoming track being added)."""
    s = sl(src, track_t + (t - mix_t), bar * 2, sr)
    m = sl(mix, t, bar * 2, sr)
    if s is None or m is None:
        return None
    n = min(len(s), len(m)); s = s[:n]; m = m[:n]
    denom = float(np.dot(s, s) + 1e-12)
    alpha = float(np.dot(m, s) / denom)
    e = max(alpha, 0.0) ** 2 * float(np.mean(s ** 2) + 1e-12)
    return 10.0 * np.log10(e + 1e-12)

def audible_until(mix, src, mix_t, track_t, t0, sr=VM.SR, bar=BAR):
    """Last clip time where aligned source still correlates vs its own mix-in cc.

    Relative to the mix-in reference so a genuine breakdown (quiet but present)
    is not mistaken for a cut.
    """
    if mix_t is None or track_t is None:
        return None
    ref = bar_proj_db(mix, src, mix_t, track_t, t0, sr, bar)
    if ref is None or ref < -70:
        return None
    dur = len(mix) / sr
    last_ok = t0
    weak = 0
    t = t0
    while t + bar <= dur + 1e-9:
        db = bar_proj_db(mix, src, mix_t, track_t, t, sr, bar)
        if db is None:
            break
        if db >= ref - S.REL_DB:
            last_ok = t + bar
            weak = 0
        else:
            weak += 1
            if weak >= 2:
                return last_ok
        t += bar
    return last_ok

def src_bar(loc, t):
    return (float(loc['track_t']) + (float(t) - float(loc['mix_t']))) / BAR

def excerpt(y, t0, dur, sr=VM.SR):
    return sl(y, t0, dur, sr)

def locate_excerpt_in_mix(mix, src_excerpt):
    if src_excerpt is None or len(src_excerpt) < VM.SR:
        return dict(z=0, cc=0, mix_t=None, track_t=None)
    return VM.locate_in(mix, src_excerpt, chunk_s=4.0, hop_s=2.0)

def src_time_at(mix, src, t, win=8.0):
    """Source time playing at clip time t, via a local locate (handles non-linear DJ playback better)."""
    cs = max(0.0, float(t) - 1.0)
    chunk = sl(mix, cs, win)
    if chunk is None:
        return None, {}
    loc = VM.locate_in(chunk, src, chunk_s=4.0, hop_s=2.0)
    if loc.get('mix_t') is None or loc.get('z', 0) < 4.5:
        return None, loc
    st = float(loc['track_t']) + (float(t) - cs - float(loc['mix_t']))
    return st, loc

def find_src_event_in_mix(mix, src, src_bar_i, win_bars=8):
    ex = excerpt(src, float(src_bar_i) * BAR, win_bars * BAR)
    loc = locate_excerpt_in_mix(mix, ex)
    return loc

def audible_until_locate(mix, src, t0, sr=VM.SR, bar=BAR, z_min=3.0):
    dur = len(mix) / sr
    last_ok = t0
    weak = 0
    t = t0
    z0 = None
    while t + 4 <= dur + 1e-9:
        chunk = sl(mix, t, 6.0, sr)
        if chunk is None:
            break
        loc = VM.locate_in(chunk, src, chunk_s=4.0, hop_s=2.0)
        z = float(loc.get('z') or 0)
        if z0 is None:
            z0 = z
        thr = max(z_min, 0.45 * max(z0, 0))
        if z >= thr:
            last_ok = t + bar
            weak = 0
        else:
            weak += 1
            if weak >= 2:
                return last_ok, z0
        t += 2 * bar
    return last_ok, z0

def analyze_rec(rec):
    a_yt, b_yt = rec['a']['yt'], rec['b']['yt']
    lab_a = S.label_phases(load_bar_safe(a_yt))
    lab_b = S.label_phases(load_bar_safe(b_yt))
    segs_a = S.detect_breakdowns(load_bar_safe(a_yt))
    segs_b = S.detect_breakdowns(load_bar_safe(b_yt))
    mixin = mixin_t(rec)
    pro = clip_path(rec)
    out = dict(id=rec['id'], dj=rec['dj'], split=rec['split'], mixin_clip_s=round(mixin, 3),
               pair=rec.get('pair'), spans_a=S.phase_spans(lab_a), spans_b=S.phase_spans(lab_b),
               brks_a=segs_a, brks_b=segs_b)
    if not os.path.exists(pro):
        out['error'] = 'missing clip'; return out
    mix = VM._load(pro)
    src_a = VM._load(os.path.join(ST, f'{a_yt}.wav'))
    src_b = VM._load(os.path.join(ST, f'{b_yt}.wav'))
    loc_a = VM.locate_in(mix, src_a)
    loc_b = VM.locate_in(mix, src_b)
    out['loc_a'] = loc_a; out['loc_b'] = loc_b
    if loc_a.get('mix_t') is None or loc_b.get('mix_t') is None:
        out['error'] = 'locate failed'; return out

    # Mix-in source times: local locate, fall back to the clip-wide hit.
    a_sec_l, loc_am = src_time_at(mix, src_a, mixin)
    b_sec_l, loc_bm = src_time_at(mix, src_b, mixin)
    a_sec_g = loc_a['track_t'] + (mixin - loc_a['mix_t'])
    b_sec_g = loc_b['track_t'] + (mixin - loc_b['mix_t'])
    # Outgoing: trust the strong early-clip locate unless a local lock is clearly stronger.
    # Incoming: do not back-extrapolate a late-clip hit (that's usually the drop);
    #           prefer a local lock at mix-in, else the global hit if it is near mix-in.
    if a_sec_l is not None and (loc_am or {}).get('z', 0) >= max(5.5, (loc_a.get('z') or 0) + 0.3):
        a_sec, a_map = a_sec_l, 'local'
    else:
        a_sec, a_map = a_sec_g, 'global'
    if b_sec_l is not None and (loc_bm or {}).get('z', 0) >= 4.0:
        b_sec, b_map = b_sec_l, 'local'
    elif loc_b.get('mix_t') is not None and abs(loc_b['mix_t'] - mixin) <= 10:
        b_sec, b_map = b_sec_g, 'global'
    elif b_sec_l is not None:
        b_sec, b_map = b_sec_l, 'local'
    else:
        b_sec, b_map = b_sec_g, 'global'
    a_cc0 = bar_cc(mix, src_a, mixin, a_sec, mixin)
    b_cc0 = bar_cc(mix, src_b, mixin, b_sec, mixin)
    a_mix = a_sec / BAR
    b_mix = b_sec / BAR
    out['loc_mixin_a'] = dict(loc_am or {}, map=a_map, cc0=a_cc0)
    out['loc_mixin_b'] = dict(loc_bm or {}, map=b_map, cc0=b_cc0)

    cut_t = audible_until(mix, src_a, mixin, a_sec, mixin)
    out['cut_clip_s'] = None if cut_t is None else round(float(cut_t), 3)
    if cut_t is None:
        cut_t = mixin  # phase-at-cut falls back to mix-in; overflow/tail omitted below
        cut_unknown = True
    else:
        cut_unknown = False

    if S.phase_at(lab_b, b_mix) == 'drop':
        # Drop is already sounding at mix-in; don't rewind to that drop's start.
        drop_b = b_mix
        already_in_drop = True
        k_drop = 0.0
    else:
        drop_b = S.first_drop_bar(lab_b, after=max(0, b_mix))
        already_in_drop = False
        k_drop = None if drop_b is None else float(drop_b - b_mix)
    # Source-bar arithmetic during the blend (linear play). Avoid locating
    # events that sit outside the 64s clip — those false-match other sections.
    drop_t = None if k_drop is None else mixin + k_drop * BAR
    out['drop_b_bar'] = drop_b
    out['drop_clip_s'] = None if drop_t is None else round(float(drop_t), 3)
    out['already_in_drop'] = already_in_drop

    nearby = []
    for seg in segs_a:
        rel = seg[0] - a_mix
        if seg[1] > a_mix - 2 and rel <= 48:
            nearby.append(seg)
    brk = S.next_breakdown(nearby, a_mix) if nearby else None
    out['out_brk'] = brk
    out['nearby_brk'] = bool(brk)
    k_brk = None if brk is None else float(brk[0] - a_mix)
    brk_t = None if k_brk is None else mixin + k_brk * BAR
    out['brk_clip_s'] = None if brk_t is None else round(float(brk_t), 3)

    a_drop = None if k_drop is None else a_mix + k_drop
    b_drop = drop_b
    a_cut = a_mix + (cut_t - mixin) / BAR
    b_cut = b_mix + (cut_t - mixin) / BAR

    out['bars'] = dict(mixin_out=round(a_mix, 2), mixin_in=round(b_mix, 2),
                       drop_out=None if a_drop is None else round(a_drop, 2),
                       drop_in=None if b_drop is None else round(float(b_drop), 2),
                       cut_out=round(a_cut, 2), cut_in=round(b_cut, 2))
    out['phases'] = dict(
        mixin=(S.phase_at(lab_a, a_mix), S.phase_at(lab_b, b_mix)),
        in_drop=(None if a_drop is None else S.phase_at(lab_a, a_drop),
                 None if b_drop is None else S.phase_at(lab_b, b_drop)),
        out_cut=(S.phase_at(lab_a, a_cut), S.phase_at(lab_b, b_cut)),
    )
    off = None
    if drop_t is not None and brk_t is not None:
        off = (drop_t - brk_t) / BAR
    out['align'] = dict(
        offset_bars=None if off is None else round(float(off), 2),
        in_drop_at_out_breakdown=bool(out['phases']['in_drop'][0] == 'breakdown') if out['phases']['in_drop'][0] else False,
        in_drop_at_out_outro=bool(out['phases']['in_drop'][0] == 'outro') if out['phases']['in_drop'][0] else False,
        mixin_vs_brk_bars=None if brk is None else round(float(a_mix - brk[0]), 2),
        has_brk=brk is not None,
        nearby_brk=bool(brk),
    )
    # linger: outgoing still audible after incoming drop
    tail = None
    if drop_t is not None:
        tail = (cut_t - drop_t) / BAR
    clip_dur = len(mix) / VM.SR
    in_window_drop = bool(drop_t is not None and -2 <= drop_t <= clip_dur + 8)
    out['in_window_drop'] = in_window_drop
    if tail is None:
        out['tail_after_in_drop_bars'] = None
        out['cut_before_in_drop'] = False
    elif tail < 0:
        out['tail_after_in_drop_bars'] = 0.0
        out['cut_before_in_drop'] = True
        out['tail_raw_bars'] = round(float(tail), 2)
    else:
        out['tail_after_in_drop_bars'] = round(float(tail), 2)
        out['cut_before_in_drop'] = False
    if cut_unknown:
        out['tail_after_in_drop_bars'] = None
        out['overflow_bars'] = None
        out['cut_unknown'] = True
    else:
        overflow, ovseg = S.bars_into_breakdown(segs_a, a_mix, a_cut)
        out['overflow_bars'] = round(float(overflow), 2)
        out['overflow_seg'] = ovseg
        out['cut_unknown'] = False
    return out

def first_span_start(labels, phase, at):
    at = int(round(float(at)))
    at = max(0, min(len(labels) - 1, at))
    i = at
    while i > 0 and labels[i - 1] == phase:
        i -= 1
    return i

def smooth_counts(pairs, alpha=1.0):
    keys = [f'{a}+{b}' for a in S.PHASES for b in S.PHASES]
    c = collections.Counter(pairs)
    n = len(pairs)
    den = n + alpha * len(keys)
    dist = {k: (c.get(k, 0) + alpha) / den for k in keys}
    dist['_floor'] = alpha / den
    dist['_pmax'] = max(dist[k] for k in keys)
    dist['_n'] = n
    dist['_raw'] = dict(c)
    return dist

def summarize(rows):
    offs = [r['align']['offset_bars'] for r in rows if r.get('align') and r['align'].get('offset_bars') is not None]
    tails = [r['tail_after_in_drop_bars'] for r in rows if r.get('tail_after_in_drop_bars') is not None]
    ov = [r['overflow_bars'] for r in rows if r.get('overflow_bars') is not None]
    lined = [r for r in rows if r.get('align', {}).get('in_drop_at_out_breakdown')]
    lined8 = [r for r in rows if r.get('align', {}).get('offset_bars') is not None and abs(r['align']['offset_bars']) <= 8]
    lined4 = [r for r in rows if r.get('align', {}).get('offset_bars') is not None and abs(r['align']['offset_bars']) <= 4]
    def pct(xs):
        if not xs: return {}
        a = np.array(xs, float)
        return dict(n=len(xs), mean=round(float(a.mean()), 2), median=round(float(np.median(a)), 2),
                    p25=round(float(np.percentile(a, 25)), 2), p75=round(float(np.percentile(a, 75)), 2))
    def pair_tab(key):
        c = collections.Counter()
        for r in rows:
            ph = (r.get('phases') or {}).get(key)
            if ph and ph[0] and ph[1]:
                c[f'{ph[0]}+{ph[1]}'] += 1
        n = sum(c.values()) or 1
        return {k: {'n': v, 'p': round(v / n, 3)} for k, v in c.most_common()}
    return dict(
        n=len(rows),
        mixin_pairs=pair_tab('mixin'),
        in_drop_pairs=pair_tab('in_drop'),
        out_cut_pairs=pair_tab('out_cut'),
        in_drop_at_out_breakdown=dict(n=len(lined), p=round(len(lined) / max(len(rows), 1), 3)),
        offset_within_4_bars=dict(n=len(lined4), p=round(len(lined4) / max(len(offs), 1), 3)),
        offset_within_8_bars=dict(n=len(lined8), p=round(len(lined8) / max(len(offs), 1), 3)),
        offset_bars=pct(offs),
        tail_after_in_drop_bars=pct(tails),
        overflow_bars=pct(ov),
    )

def main():
    recs = json.load(open(os.path.join(paths.RESULTS, 'admitted.json')))
    rows = []
    for i, rec in enumerate(recs, 1):
        print(f'[{i}/{len(recs)}] {rec["id"]}', flush=True)
        try:
            rows.append(analyze_rec(rec))
        except Exception as e:
            rows.append(dict(id=rec['id'], dj=rec.get('dj'), split=rec.get('split'), error=str(e)[:300]))
            print('  ERROR', e, flush=True)
        if rows[-1].get('phases'):
            print(' ', rows[-1]['phases'], 'off', rows[-1].get('align'), 'tail', rows[-1].get('tail_after_in_drop_bars'),
                  'ov', rows[-1].get('overflow_bars'), flush=True)
    ok = [r for r in rows if r.get('phases') and not r.get('error')]
    train = [r for r in ok if r.get('split') == 'train']
    test = [r for r in ok if r.get('split') == 'test']
    stats = dict(all=summarize(ok), train=summarize(train), test=summarize(test),
                 n_error=sum(1 for r in rows if r.get('error')))
    def pairs_at(rs, key):
        out = []
        for r in rs:
            ph = (r.get('phases') or {}).get(key)
            if not (ph and ph[0] and ph[1]):
                continue
            if key == 'in_drop' and r.get('in_window_drop') is False:
                continue
            if key == 'out_cut' and r.get('cut_clip_s') is None:
                continue
            out.append(f'{ph[0]}+{ph[1]}')
        return out
    tails = [r['tail_after_in_drop_bars'] for r in train if r.get('tail_after_in_drop_bars') is not None]
    ovs = [r['overflow_bars'] for r in train if r.get('overflow_bars') is not None]
    priors = dict(
        note='Laplace-smoothed phase-pairing frequencies from TRAIN pro transitions only. Soft preferences, not bans.',
        n_train=len(train),
        mixin=smooth_counts(pairs_at(train, 'mixin')),
        in_drop=smooth_counts(pairs_at(train, 'in_drop')),
        out_cut=smooth_counts(pairs_at(train, 'out_cut')),
        linger_grace_bars=(round(float(np.median(tails)), 2) if tails and float(np.median(tails)) > 0 else 8.0),
        overflow_grace_bars=(round(float(np.median(ovs)), 2) if ovs else 4.0),
        linger_p75_bars=round(float(np.percentile(tails, 75)), 2) if tails else 16.0,
        overflow_p75_bars=round(float(np.percentile(ovs, 75)), 2) if ovs else 8.0,
    )
    os.makedirs(paths.RESULTS, exist_ok=True)
    json.dump(dict(stats=stats, rows=rows), open(os.path.join(paths.RESULTS, 'phase_stats.json'), 'w'), indent=2)
    json.dump(priors, open(os.path.join(paths.RESULTS, 'phase_priors.json'), 'w'), indent=2)
    print(json.dumps(stats, indent=2))
    print('wrote phase_stats.json and phase_priors.json; linger_grace', priors['linger_grace_bars'],
          'overflow_grace', priors['overflow_grace_bars'])

if __name__ == '__main__':
    main()
