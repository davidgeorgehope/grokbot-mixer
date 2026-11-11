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


DIVE_PRE, DIVE_POST = 2.0, 6.0   # bars: swoop in over the 2 bars before the drop, ride the needle, pull back by +6


def dive_candidates(secs, decks, s0, s1):
    """Drop/breakdown moments of the two decks inside [s0, s1], in mix bars.

    secs[di] is deck di's sections dict. Each candidate is {startBar, endBar, deck, kind, peakBar};
    the camera lands on the needle right at peakBar (the drop) and pulls back DIVE_POST bars later.
    """
    import numpy as np
    cands = []
    for di, d in enumerate(decks):
        sec = secs[di] or {}
        fm = d['full_map']; sb = d['start_bar']
        tbs = [float(r[0]) for r in fm]
        def mix_of(tb):
            # full_map[k][0] is track bar at mix bar sb+k
            for k, row in enumerate(fm):
                if abs(float(row[0]) - tb) < 0.51:
                    return sb + k
            if not tbs or tb < tbs[0] - 1 or tb > tbs[-1] + 1:
                return None
            return float(np.interp(tb, tbs, [sb + i for i in range(len(tbs))]))
        evs = [(kind, sec.get(key)) for kind, key in (('drop', 'drop2'), ('drop', 'drop1'), ('breakdown', 'breakdown'))]
        evs += [('drop', pair[0]) for pair in (sec.get('drops') or []) if pair]
        for kind, tb in evs:
            if tb is None:
                continue
            mb = mix_of(float(tb))
            if mb is None or mb < s0 or mb > s1:
                continue
            cands.append(dict(peakBar=mb, startBar=mb - DIVE_PRE, endBar=mb + DIVE_POST, deck=di, kind=kind))
    return cands


def plan_dives(out, decks, envs, s0, s1, bs, plan=None):
    """Rare camera swoops tied to real musical moments (drop landings, breakdowns).

    Returns a list of {startBar, endBar, deck, kind, peakBar}, 8 bars each. With a whole-mix
    plan (dive_plan.json from --plan-dives) only the planned peaks are kept, so dives stay rare
    across segments (Mix 08 got one per segment, 24 in an hour). Without a plan (single clip),
    at most one per ~15 min. FORCE_DIVE=1 plants one mid-clip when nothing natural falls inside.
    """
    import os
    want = os.environ.get('GROOVE_DIVE', '1') != '0'
    if not want:
        return []
    secs = [out['decks'][di].get('sections') for di in range(len(decks))]
    cands = dive_candidates(secs, decks, s0, s1)
    cands.sort(key=lambda c: (0 if c['kind'] == 'drop' else 1, c['peakBar']))
    picked, last = [], None
    if plan is not None:
        for p in plan:
            hit = [c for c in cands if abs(c['peakBar'] - p['peakBar']) < 0.5 and c['startBar'] >= s0 and c['endBar'] <= s1]
            if hit and not any(abs(q['peakBar'] - p['peakBar']) < 0.5 for q in picked):
                picked.append(hit[0])
    else:
        for c in cands:
            if c['startBar'] < s0 or c['endBar'] > s1: continue
            if last is not None and abs(c['peakBar'] - last) < 64: continue
            picked.append(c); last = c['peakBar']
            if len(picked) >= max(1, int((s1 - s0) * bs / 900) + 1):  # ~1 per 15 min, at least 1 if any
                break
    if not picked and plan is None and os.environ.get('FORCE_DIVE', '0') == '1':
        mid = (s0 + s1) / 2
        picked = [dict(peakBar=mid, startBar=mid - DIVE_PRE, endBar=mid + DIVE_POST, deck=0, kind='forced')]
    for c in picked:
        print(f"  dive: deck {c['deck']} {c['kind']} bars {c['startBar']:.1f}-{c['endBar']:.1f}")
    return picked


def plan_mix_dives(segs_json, st_dir, gap_sec):
    """Whole-mix dive plan: drops only, fully inside one segment, at least gap_sec apart."""
    S = json.load(open(segs_json))
    allc = []
    for sg in S['segs']:
        t = json.load(open(sg['timing']))
        s0, s1 = float(t['clip_start_bar']), float(t['clip_end_bar'])
        decks = t['decks'][:2]
        secs = [load_sections(st_dir, d['id']) for d in decks]
        for c in dive_candidates(secs, decks, s0, s1):
            if c['kind'] == 'drop' and c['startBar'] >= s0 and c['endBar'] <= s1:
                c['seg'] = sg['tag']; allc.append(c)
    bs = float(S['bar_sec'])
    allc.sort(key=lambda c: c['peakBar'])
    picked = []
    for c in allc:
        if picked and (c['peakBar'] - picked[-1]['peakBar']) * bs < gap_sec:
            continue
        picked.append(c)
    for c in picked:
        t = c['peakBar'] * bs
        print(f"  plan: {c['seg']} deck {c['deck']} drop at {int(t // 60)}:{t % 60:04.1f} (bar {c['peakBar']:.1f})")
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--timing')
    ap.add_argument('--dive-plan', default='', help='whole-mix dive_plan.json (only these dives)')
    ap.add_argument('--plan-dives', default='', help='segs.json: write a whole-mix dive plan to --out and exit')
    ap.add_argument('--dive-gap-sec', type=float, default=float(os.environ.get('DIVE_GAP_SEC', 600)))
    ap.add_argument('--mix')
    ap.add_argument('--out', required=True)
    ap.add_argument('--st', default='/workspace/mixes/src2/st')
    ap.add_argument('--src', default='/workspace/mixes/src2')
    ap.add_argument('--fps', type=int, default=30)
    ap.add_argument('--dur', type=float, default=None)
    a = ap.parse_args()
    if a.plan_dives:
        plan = plan_mix_dives(a.plan_dives, a.st, a.dive_gap_sec) if os.environ.get('GROOVE_DIVE', '1') != '0' else []
        json.dump(plan, open(a.out, 'w'), indent=1)
        print(f'prep: dive plan {len(plan)} dives (gap >= {a.dive_gap_sec:.0f}s) -> {a.out}')
        return
    if not a.timing:
        ap.error('--timing is required')
    if not a.mix:
        ap.error('--mix is required')
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
    out['dives'] = plan_dives(out, decks, envs, s0, s1, bs, plan=json.load(open(a.dive_plan)) if a.dive_plan else None)
    json.dump(out, open(a.out, 'w'))
    print(f'prep: {n} frames, decks {[d["id"] for d in decks]}, bars {[r["nBars"] for r in out["decks"]]}, dives={len(out["dives"])} -> {a.out}')


if __name__ == '__main__':
    main()
