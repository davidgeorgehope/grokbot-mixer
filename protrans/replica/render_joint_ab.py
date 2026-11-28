#!/usr/bin/env python3
"""Blind A/B of the current default vs JOINT_PICKER=1, plus a daily-harness smoke test.

40 s (or the engine snippet, trimmed around the blend), loudness-matched to -14 LUFS,
tick at the blend start. A/B order is random; the key goes to /workspace/private only.
Measures hop-wise RMS difference across the blend and refuses to write near-identical clips.

usage:
  python3 render_joint_ab.py --test-daily <pick_id>   # one-pair harness check, writes nothing public unless --write
  python3 render_joint_ab.py --ab <pick_id>           # write A/B + PNG if they differ
"""
from __future__ import annotations
import argparse, copy, json, os, random, sys
import numpy as np
import soundfile as sf

H = os.path.dirname(os.path.abspath(__file__))
P = os.path.dirname(H)
sys.path.insert(0, P); sys.path.insert(0, H)
import paths, recreate, cleanup, render_planner_clips as RP

OUT = os.path.join(paths.DELIVER, 'diagnostics')  # png lives here; mp3s in deliver/protrans
MP3_DIR = paths.DELIVER
KEY_DIR = '/workspace/private'


def hop_diff(ya, yb, sr, hop_s=0.1, start_s=0.0, end_s=None):
    n = min(len(ya), len(yb))
    a = np.asarray(ya[:n], float); b = np.asarray(yb[:n], float)
    if a.ndim == 2: a = a.mean(1); b = b.mean(1)
    i0 = int(start_s * sr); i1 = n if end_s is None else min(n, int(end_s * sr))
    hop = max(1, int(sr * hop_s)); dbs = []
    for i in range(i0, max(i0 + 1, i1 - hop), hop):
        ra = float(np.sqrt(np.mean(a[i:i+hop] ** 2) + 1e-12))
        rb = float(np.sqrt(np.mean(b[i:i+hop] ** 2) + 1e-12))
        dbs.append(abs(20 * np.log10(ra) - 20 * np.log10(rb)))
    dbs = np.array(dbs)
    return dict(n=int(len(dbs)), mean=round(float(dbs.mean()), 2), mx=round(float(dbs.max()), 2),
                over_3db=int((dbs > 3).sum()), hop_s=hop_s)


def trim40(y, sr, tick_s, dur=40.0):
    """Keep the tick, take up to `dur` seconds, pad the tail with silence so 8-bar and 16-bar snippets match."""
    n = int(round(dur * sr)); mid = int(tick_s * sr)
    a = max(0, mid - n // 4)
    if a + n > len(y):
        a = max(0, min(mid, max(0, len(y) - n))) if len(y) >= n else 0
    sl = y[a:a + min(n, len(y) - a)]
    if len(sl) < n:
        if sl.ndim == 1:
            sl = np.concatenate([sl, np.zeros(n - len(sl), dtype=sl.dtype)])
        else:
            z = np.zeros((n, sl.shape[1]), dtype=sl.dtype); z[:len(sl)] = sl; sl = z
    return sl, tick_s - a / sr


def render_arm(rec, rules, tag):
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
    sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    info = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                             hint_a_played_sec=(rec.get('window') or {}).get('hint_a_played_sec'),
                             rules=rules, tag=tag)
    M = json.load(open(info['meta_path']))
    base = os.path.splitext(info['ours'])[0]
    wav = next(c for c in (base + '_master.wav', base + '.wav', info['ours']) if os.path.exists(c))
    y, sr = sf.read(wav)
    bar = RP._bar_sec(M)
    tick_s = 8 * bar
    y2 = RP._tick(y, sr, tick_s)
    y2, meas, gain = RP._loudness_match(y2, sr, RP.TARGET_LUFS)
    y40, tick40 = trim40(y2, sr, tick_s)
    return dict(info=info, y=y40, sr=sr, tick_s=tick40, meas=meas, gain=gain, M=M, sa=sa, sb=sb, dur=len(y40) / sr)


def both(rec):
    rules = json.load(open(paths.RULES))
    assert not rules.get('JOINT_PICKER'), 'JOINT_PICKER must stay off in rules.json'
    rd, rj = copy.deepcopy(rules), copy.deepcopy(rules)
    rj['JOINT_PICKER'] = 1
    d = render_arm(rec, rd, 'jdaily_d')
    j = render_arm(rec, rj, 'jdaily_j')
    return d, j


def maybe_write_ab(rec, d, j, stem, force=False):
    diff = hop_diff(d['y'], j['y'], d['sr'], start_s=max(0, d['tick_s'] - 1), end_s=d['tick_s'] + 25)
    same_win = list(d['info']['win']) == list(j['info']['win'])
    if same_win and diff['mean'] < 1.0 and not force:
        return dict(wrote=False, reason='windows and audio match', diff=diff, win=d['info']['win'])
    if diff['over_3db'] < 5 and diff['mean'] < 1.5 and not force:
        return dict(wrote=False, reason='clips too similar across the blend', diff=diff,
                    win_d=d['info']['win'], win_j=j['info']['win'])
    os.makedirs(MP3_DIR, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    sides = [('default', d), ('joint', j)]
    order = sides[:]
    rng = random.SystemRandom()
    if rng.random() < 0.5:
        order.reverse()
    key = dict(pick=rec['id'], pair=rec.get('pair'), A=order[0][0], B=order[1][0], diff=diff,
               default=dict(fam=d['info']['fam'], win=d['info']['win']),
               joint=dict(fam=j['info']['fam'], win=j['info']['win'],
                          margin=(j['info'].get('ridegate_info') or j['info'].get('ridegate') or {}).get('joint')))
    for ab, (name, arm) in zip('AB', order):
        wav = os.path.join(MP3_DIR, f'{stem}_{ab}.wav')
        mp3 = os.path.join(MP3_DIR, f'{stem}_{ab}.mp3')
        sf.write(wav, arm['y'], arm['sr']); RP._to_mp3(wav, mp3); os.remove(wav)
    sys.path.insert(0, paths.SRC2)
    cwd = os.getcwd(); os.chdir(paths.SRC2)
    try:
        import blend_diag
        png = os.path.join(OUT, stem + '.png')
        title = f"{rec['id']} default {d['info']['win']} vs joint {j['info']['win']}"
        blend_diag.figure(j['M'], 0, png, title, pro=rec.get('pro_clip'), src_a=j['sa'], src_b=j['sb'], ours=j['info']['ours'])
        key['png'] = png
    finally:
        os.chdir(cwd)
    key_path = os.path.join(KEY_DIR, stem + '_key.json')
    json.dump(key, open(key_path, 'w'), indent=1, default=str)
    return dict(wrote=True, key=key_path, diff=diff, A=order[0][0], B=order[1][0],
                mp3=[os.path.join(MP3_DIR, f'{stem}_A.mp3'), os.path.join(MP3_DIR, f'{stem}_B.mp3')])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--test-daily', metavar='PICK')
    ap.add_argument('--ab', metavar='PICK')
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()
    import run_admitted_tune as T
    recs = {r['id']: r for r in T.load_recs()}
    pid = args.test_daily or args.ab
    rec = recs[pid]
    d, j = both(rec)
    margin = (j['info'].get('ridegate_info') or j['info'].get('ridegate') or {}).get('joint')
    report = dict(
        id=pid,
        default=dict(fam=d['info']['fam'], win=d['info']['win']),
        joint=dict(fam=j['info']['fam'], win=j['info']['win'], margin=margin),
        same_win=list(d['info']['win']) == list(j['info']['win']),
        flag_on_default=bool((d['info'].get('env') or {}).get('JOINT_PICKER')),
        flag_on_joint=bool((j['info'].get('env') or {}).get('JOINT_PICKER')),
    )
    report['diff'] = hop_diff(d['y'], j['y'], d['sr'], start_s=max(0, d['tick_s'] - 1), end_s=d['tick_s'] + 25)
    print('DAILY_HARNESS', json.dumps(report, default=str), flush=True)
    if args.ab or args.write:
        stem = f"AB_joint_{pid}"
        w = maybe_write_ab(rec, d, j, stem)
        print('AB', json.dumps(w, default=str), flush=True)
    cleanup.drop_our_src2((d['info'].get('created') or []) + (j['info'].get('created') or []))

if __name__ == '__main__':
    main()
