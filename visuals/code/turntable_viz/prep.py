#!/usr/bin/env python3
"""Prepare data for turntable_viz: per-deck record "cuts" (groove energy map) and per-frame deck/mixer state.

usage: python3 prep.py --timing T.json --mix MIX.mp3 --out data.json [--st DIR] [--src DIR] [--fps 30] [--dur 55]

Data loading mirrors visuals/code/beatgrid_viz.py (engine timing.json + st/<id>.json + st/<id>.sections.json).
Record model: 1 revolution = 1 bar of the track (so the platter turns at the real tempo, 174 BPM -> 43.5 rpm),
LEAD revolutions of lead-in, then bar k of the track is cut into revolution LEAD+k. Groove energy comes from the
track's own audio file (src2/<id>.flac), sampled along the spiral.
"""
from __future__ import annotations
import argparse, base64, json, math, os, sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from beatgrid_viz import interp_auto, xfader_at, load_sections  # reuse engine-data helpers

LEAD, TAIL, COLS, SPIN_DOWN = 3, 3, 512, 0.6
R_LEADIN, R_PROGRAM, R_PROGRAM_MIN, R_LOCK, TAB_PER_REV = 0.1490, 0.1463, 0.0603, 0.0532, 64


def envelope(path, sr=22050, hop=110):
    import librosa
    y, sr = librosa.load(path, sr=sr, mono=True)
    fr = librosa.util.frame(np.pad(y, (256, 256)), frame_length=512, hop_length=hop)
    rms = np.sqrt((fr ** 2).mean(0) + 1e-12)
    from scipy.signal import butter, sosfilt
    lo = sosfilt(butter(4, 150, 'low', fs=sr, output='sos'), y)
    frl = librosa.util.frame(np.pad(lo, (256, 256)), frame_length=512, hop_length=hop)
    rl = np.sqrt((frl ** 2).mean(0) + 1e-12)
    def norm(x):
        db = 20 * np.log10(x)
        top = np.percentile(db, 99.5)
        return np.clip((db - (top - 30)) / 30, 0, 1)
    return np.arange(len(rms)) * hop / sr, norm(rms), norm(rl), 20 * np.log10(rms)


def sec_code(sec, tb):
    if not sec:
        return 0.0
    bd, d2, outro = sec.get('breakdown'), sec.get('drop2'), sec.get('outro_start')
    if outro is not None and tb >= outro:
        return 0.9
    if bd is not None and tb >= bd and (d2 is None or tb < d2):
        return 0.45
    return 0.1


def cut_record(st, sec, env):
    """Spiral radius table + RGBA groove map for one track."""
    nb = len(st['downs'])
    revs = LEAD + nb + TAIL
    downs = np.array(st['downs'], float)
    bar_s = float(np.median(np.diff(downs)))
    # radius per revolution boundary
    rb = np.empty(revs + 1)
    rb[:LEAD + 1] = np.linspace(R_LEADIN, R_PROGRAM, LEAD + 1)
    rb[LEAD:LEAD + nb + 1] = np.linspace(R_PROGRAM, R_PROGRAM_MIN, nb + 1)
    rb[LEAD + nb:] = np.linspace(R_PROGRAM_MIN, R_LOCK, TAIL + 1)
    k = np.arange(revs * TAB_PER_REV + 1) / TAB_PER_REV
    rtab = np.interp(k, np.arange(revs + 1), rb)
    pitch = (R_PROGRAM - R_PROGRAM_MIN) / nb
    # groove map
    t_env, e_all, e_lo, _ = env
    col = np.arange(COLS) / COLS
    tbf = (np.arange(revs)[:, None] - LEAD) + col[None, :]          # track bar (float) per texel
    bi = np.clip(np.floor(tbf).astype(int), 0, nb - 1)
    t = downs[bi] + (tbf - bi) * bar_s
    inside = (tbf >= 0) & (tbf < nb)
    R = np.where(inside, np.interp(t, t_env, e_all), 0)
    G = np.where(inside, np.interp(t, t_env, e_lo), 0)
    B = np.zeros_like(R)
    for r in range(revs):
        tb = r - LEAD
        if 0 <= tb < nb:
            B[r, :] = sec_code(sec, tb)
    A = np.zeros_like(R)
    beat = (np.abs(((col * 4 + 0.5) % 1) - 0.5) < 0.012)              # quarter-note ticks (1 rev = 1 bar)
    A[:, beat] = 0.4
    phr_bars = set(int(round(np.interp(p, downs, np.arange(nb)))) for p in st.get('phrases', []))
    for pb in phr_bars:
        if 0 <= pb < nb:
            A[LEAD + pb, :] = 1.0
    A[~inside] = 0
    rgba = np.stack([R, G, B, A], -1)
    rgba = (np.clip(rgba, 0, 1) * 255).astype(np.uint8)
    return dict(rTab=rtab.tolist(), thetaEnd=(len(rtab) - 1) * 2 * math.pi / TAB_PER_REV, rows=revs, cols=COLS,
                vis=base64.b64encode(rgba.tobytes()).decode(), pitch=pitch, nBars=nb, lead=LEAD, barSec=bar_s)


def deck_bar(deck, mb):
    """mix bar -> (track bar float, playing). Cued at first bar before start; extrapolated after the map ends."""
    fm, sb = deck['full_map'], deck['start_bar']
    i = mb - sb
    if i < 0:
        return float(fm[0][0]), False
    if i >= len(fm):   # engine drops the deck here (gain 0): show it stopping, with a faked 0.6-bar spin-down
        x = min(1.0, (i - len(fm)) / SPIN_DOWN)
        return float(fm[-1][0]) + 1 + SPIN_DOWN / 2 * (1 - (1 - x) ** 2), False
    k = int(math.floor(i))
    return float(fm[k][0]) + (i - k), True


def plan_dives(out, decks, envs, s0, s1, bs):
    """Rare camera swoops tied to real musical moments (drop landings, breakdowns).

    Returns a list of {startBar, endBar, deck, kind, peakBar}. About 4-8 bars each,
    a few per hour, spaced at least ~64 bars apart. FORCE_DIVE=1 plants one mid-clip
    when nothing natural falls inside the window (preview testing).
    """
    import os
    want = os.environ.get('GROOVE_DIVE', '1') != '0'
    if not want:
        return []
    cands = []
    for di, (d, (st, env)) in enumerate(zip(decks, envs)):
        sec = out['decks'][di].get('sections') or {}
        # map track-bar event -> mix bar via full_map
        fm = d['full_map']; sb = d['start_bar']
        def mix_of(tb):
            # full_map[k][0] is track bar at mix bar sb+k
            for k, row in enumerate(fm):
                if abs(float(row[0]) - tb) < 0.51:
                    return sb + k
            # interpolate
            tbs = [float(r[0]) for r in fm]
            if not tbs or tb < tbs[0] - 1 or tb > tbs[-1] + 1:
                return None
            import numpy as np
            return float(np.interp(tb, tbs, [sb + i for i in range(len(tbs))]))
        for kind, key in (('drop', 'drop2'), ('drop', 'drop1'), ('breakdown', 'breakdown')):
            tb = sec.get(key)
            if tb is None:
                continue
            mb = mix_of(float(tb))
            if mb is None or mb < s0 or mb > s1:
                continue
            # 6-bar swoop centered just after the event (settle into the groove)
            dur = 6.0
            cands.append(dict(peakBar=mb, startBar=mb - 1.0, endBar=mb - 1.0 + dur, deck=di, kind=kind))
        # also mark each drops[] interval start
        for pair in sec.get('drops') or []:
            if not pair: continue
            tb = float(pair[0]); mb = mix_of(tb)
            if mb is None or mb < s0 or mb > s1: continue
            cands.append(dict(peakBar=mb, startBar=mb - 1.0, endBar=mb + 5.0, deck=di, kind='drop'))
    # prefer drops, then chronological; enforce spacing
    cands.sort(key=lambda c: (0 if c['kind'] == 'drop' else 1, c['peakBar']))
    picked, last = [], None
    for c in cands:
        c['startBar'] = max(s0, c['startBar']); c['endBar'] = min(s1, c['endBar'])
        if c['endBar'] - c['startBar'] < 3: continue
        if last is not None and c['peakBar'] - last < 64: continue
        picked.append(c); last = c['peakBar']
        if len(picked) >= max(1, int((s1 - s0) * bs / 900) + 1):  # ~1 per 15 min, at least 1 if any
            break
    if not picked and os.environ.get('FORCE_DIVE', '0') == '1':
        mid = (s0 + s1) / 2
        picked = [dict(peakBar=mid, startBar=mid - 1, endBar=mid + 5, deck=0, kind='forced')]
    for c in picked:
        print(f"  dive: deck {c['deck']} {c['kind']} bars {c['startBar']:.1f}-{c['endBar']:.1f}")
    return picked



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--timing', required=True)
    ap.add_argument('--mix', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--st', default='/workspace/mixes/src2/st')
    ap.add_argument('--src', default='/workspace/mixes/src2')
    ap.add_argument('--fps', type=int, default=30)
    ap.add_argument('--dur', type=float, default=None)
    a = ap.parse_args()
    tim = json.load(open(a.timing))
    bs = float(tim['bar_sec']); s0 = float(tim['clip_start_bar']); s1 = float(tim['clip_end_bar'])
    tr, decks = tim['trans'], tim['decks'][:2]
    dur = a.dur or (s1 - s0) * bs
    n = int(round(dur * a.fps))
    out = dict(fps=a.fps, frames=n, dur=dur, barSec=bs, clipStartBar=s0, mixOffset=s0 * bs,
               titles=tim.get('titles', {}), tech=tr.get('tech', ''), keys=tr.get('keys', ''),
               trans={k: tr.get(k) for k in ('start_bar', 'end_bar', 'bass_swap', 'high_bar', 'swap_bar')}, decks=[])
    envs = []
    for d in decks:
        st_path = os.path.join(a.st, d['id'] + '.json')
        if not os.path.exists(st_path):
            raise SystemExit(f"prep: missing analysis file {st_path}")
        st = json.load(open(st_path))
        sec = load_sections(a.st, d['id'])
        src_cands = [os.path.join(a.src, d['id'] + ext) for ext in ('.flac', '.wav', '.m4a', '.mp3', '.opus', '.ogg')]
        src = next((p for p in src_cands if os.path.exists(p)), None)
        if src is None:
            raise SystemExit(f"prep: missing source audio for {d['id']} under {a.src}")
        env = envelope(src); envs.append((st, env))
        rec = cut_record(st, sec, env)
        rec.update(id=d['id'], sections=sec, bpm=60 / st['per'])
        out['decks'].append(rec)
    # mix master level (real, from the delivered mp3)
    import librosa
    y, sr = librosa.load(a.mix, sr=22050, mono=True, offset=s0 * bs, duration=dur + 0.5)
    hop = sr // a.fps
    mrms = np.array([np.sqrt((y[i * hop:i * hop + 1024] ** 2).mean() + 1e-12) for i in range(n)])
    mdb = 20 * np.log10(mrms)
    frames = []
    xf = tr.get('xfader') or []
    for f in range(n):
        mb = s0 + f / a.fps / bs
        fr = dict(mb=mb, xf=xfader_at(xf, mb) if mb >= (xf[0][0] if xf else 0) else 0.0, m=float(np.clip((mdb[f] + 40) / 40, 0, 1)), d=[])
        for di, d in enumerate(decks):
            au = d.get('auto', {})
            tb, playing = deck_bar(d, mb)
            g = interp_auto(au.get('gain'), mb, 1.0); lo = interp_auto(au.get('low'), mb, 1.0); hi = interp_auto(au.get('high'), mb, 1.0)
            st, (te, ea, el, edb) = envs[di]
            downs = np.array(st['downs']); bi = int(np.clip(math.floor(tb), 0, len(downs) - 1))
            tt = downs[bi] + (tb - bi) * np.median(np.diff(downs))
            lvl = float(np.interp(tt, te, edb)) + 20 * math.log10(max(g, 1e-4)) if playing else -90
            fr['d'].append(dict(tb=tb, on=playing, cued=mb < d['start_bar'], g=g, lo=lo, hi=hi, lvl=float(np.clip((lvl + 40) / 40, 0, 1))))
        frames.append(fr)
    out['frameState'] = frames
    out['dives'] = plan_dives(out, decks, envs, s0, s1, bs)
    json.dump(out, open(a.out, 'w'))
    print(f'prep: {n} frames, decks {[d["id"] for d in decks]}, bars {[r["nBars"] for r in out["decks"]]}, dives={len(out["dives"])} -> {a.out}')


if __name__ == '__main__':
    main()
