#!/usr/bin/env python3
"""44 s, tick, -14 LUFS A/B clip: A = current default, B = RANKER=1, on a
pair where the ranker picks a different option. Diagnostic PNG under
deliver/protrans/diagnostics/.
"""
from __future__ import annotations
import copy, json, os, sys, shutil
import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'src2'))
import paths, recreate, cleanup, render_planner_clips as RC
import run_admitted_tune as T

OUT_DIR = paths.DELIVER
DIAG_DIR = os.path.join(paths.DELIVER, 'diagnostics')


def _concat_ab(ya, yb, sr, gap_s=0.75):
    n = int(sr * gap_s)
    if ya.ndim == 1:
        gap = np.zeros(n, dtype=ya.dtype)
        return np.concatenate([ya, gap, yb])
    gap = np.zeros((n, ya.shape[1]), dtype=ya.dtype)
    return np.concatenate([ya, gap, yb], axis=0)


def _load_snippet(info):
    ours = info['ours']
    base = os.path.splitext(ours)[0]
    wav = None
    for cand in (base + '_master.wav', base + '.wav', ours):
        if os.path.exists(cand):
            wav = cand
            break
    y, sr = sf.read(wav)
    M = json.load(open(info['meta_path']))
    bar = RC._bar_sec(M)
    tick_s = 8 * bar
    y2 = RC._tick(y, sr, tick_s)
    y2, meas, gain = RC._loudness_match(y2, sr, RC.TARGET_LUFS)
    return y2, sr, meas, gain, tick_s, M, bar


def render_pair(rec, rules_a, rules_b, stem):
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(DIAG_DIR, exist_ok=True)
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
    sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    hint = (rec.get('window') or {}).get('hint_a_played_sec')
    info_a = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                               hint_a_played_sec=hint, rules=rules_a, tag='rk_def')
    info_b = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                               hint_a_played_sec=hint, rules=rules_b, tag='rk_v0')
    ya, sr, meas_a, gain_a, tick_s, Ma, bar = _load_snippet(info_a)
    yb, sr_b, meas_b, gain_b, tick_b, Mb, bar_b = _load_snippet(info_b)
    # write halves and the concatenated A/B (A then B)
    def _write(y, name, measured, gain):
        wav = os.path.join(OUT_DIR, name + '.wav')
        mp3 = os.path.join(OUT_DIR, name + '.mp3')
        sf.write(wav, y, sr)
        RC._to_mp3(wav, mp3)
        try:
            os.remove(wav)
        except OSError:
            pass
        dur = len(y) / float(sr)
        return dict(mp3=mp3, duration_s=round(dur, 3),
                    measured_lufs_before=None if measured is None else round(float(measured), 2),
                    gain_db_applied=round(float(gain), 2), lufs=RC.TARGET_LUFS)
    a_meta = _write(ya, stem + '_A_default', meas_a, gain_a)
    b_meta = _write(yb, stem + '_B_ranker', meas_b, gain_b)
    yab = _concat_ab(ya, yb, sr)
    ab_meta = _write(yab, stem + '_AB', None, 0.0)
    # diagnostic figure for the ranker render (and a default copy)
    sys.path.insert(0, paths.SRC2)
    cwd = os.getcwd(); os.chdir(paths.SRC2)
    png = os.path.join(DIAG_DIR, stem + '.png')
    png_def = os.path.join(DIAG_DIR, stem + '_default.png')
    try:
        import blend_diag
        title_b = (f"{rec['id']} RANKER {rec.get('pair')} fam={info_b['fam']} "
                   f"win={info_b['win']} ranker={(info_b.get('ranker') or {}).get('best_type')}")
        title_a = (f"{rec['id']} default {rec.get('pair')} fam={info_a['fam']} win={info_a['win']}")
        summ_b = blend_diag.figure(Mb, 0, png, title_b, pro=rec.get('pro_clip'), src_a=sa, src_b=sb, ours=info_b['ours'])
        summ_a = blend_diag.figure(Ma, 0, png_def, title_a, pro=rec.get('pro_clip'), src_a=sa, src_b=sb, ours=info_a['ours'])
    finally:
        os.chdir(cwd)
    meta = dict(
        id=rec['id'], pair=rec.get('pair'),
        tick_s=round(tick_s, 3), bar_sec=bar,
        A=dict(a_meta, fam=info_a['fam'], win=info_a['win'], env=info_a.get('env'), planner=info_a.get('planner')),
        B=dict(b_meta, fam=info_b['fam'], win=info_b['win'], env=info_b.get('env'), ranker=info_b.get('ranker')),
        AB=ab_meta, png=png, png_default=png_def,
    )
    json.dump(meta, open(os.path.join(OUT_DIR, stem + '.json'), 'w'), indent=2, default=str)
    json.dump(summ_b, open(os.path.splitext(png)[0] + '.json', 'w'), indent=1, default=str)
    cleanup.drop_our_src2((info_a.get('created') or []) + (info_b.get('created') or []))
    return meta


def _differs(info_a, info_b):
    wa, wb = list(info_a.get('win') or []), list(info_b.get('win') or [])
    ea, eb = info_a.get('env') or {}, info_b.get('env') or {}
    def g(e, k, d='0'):
        return str(e.get(k, d) or d)
    return (wa != wb
            or g(ea, 'SNAP_IN') != g(eb, 'SNAP_IN')
            or g(ea, 'SNAP_IN_HOLD') != g(eb, 'SNAP_IN_HOLD')
            or g(ea, 'TAIL_EXIT', '6') != g(eb, 'TAIL_EXIT', '6'))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--id', default='hybrid_minds_ukf__25')
    args = ap.parse_args()
    recs = {r['id']: r for r in T.load_recs()}
    rules = json.load(open(paths.RULES))
    trial = copy.deepcopy(rules)
    trial['RANKER'] = 1
    if args.id:
        rec = recs[args.id]
        meta = render_pair(rec, rules, trial, f'ranker_v0_{args.id}')
        print('CLIP', json.dumps({k: meta[k] for k in ('id', 'pair', 'png', 'AB', 'A', 'B', 'tick_s') if k in meta}, default=str), flush=True)
        return 0
    # Prefer a pair listed in the train report's example_diffs that is in the 33.
    report_p = os.path.join(paths.ROOT if hasattr(paths, 'ROOT') else HERE, 'ranker', 'report.json')
    if not os.path.exists(report_p):
        report_p = os.path.join(HERE, 'ranker', 'report.json')
    prefer = []
    if os.path.exists(report_p):
        rep = json.load(open(report_p))
        prefer = [d['id'] for d in (rep.get('example_diffs') or []) if d['id'] in recs]
    eval_p = os.path.join(paths.RESULTS, 'eval_ranker_v0.json')
    if os.path.exists(eval_p):
        ev = json.load(open(eval_p))
        for p in ev.get('pairs') or []:
            if p['id'] in recs:
                prefer.append(p['id'])
    order = []
    for i in prefer + list(recs):
        if i not in order and i in recs:
            order.append(i)
    chosen = None
    meta = None
    # Probe cheaply: recreate dry-ish by actually rendering candidates until one differs.
    # Start with known train-split pairs so we're not leaking a held-out example as the demo
    # unless that's the only difference.
    train_first = [i for i in order if recs[i].get('split') == 'train'] + [i for i in order if recs[i].get('split') != 'train']
    for pid in train_first:
        rec = recs[pid]
        sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
        sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
        if not (os.path.exists(sa) and os.path.exists(sb)):
            continue
        hint = (rec.get('window') or {}).get('hint_a_played_sec')
        try:
            ia = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                                   hint_a_played_sec=hint, rules=rules, tag='rkprobe_a')
            ib = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                                   hint_a_played_sec=hint, rules=trial, tag='rkprobe_b')
        except Exception as e:
            print('probe fail', pid, type(e).__name__, str(e)[-200:], flush=True)
            continue
        if _differs(ia, ib):
            chosen = pid
            print('DIFF', pid, 'default', ia.get('fam'), ia.get('win'),
                  'ranker', ib.get('fam'), ib.get('win'), ib.get('ranker'), flush=True)
            # re-render properly into deliver (the probe files can be reused but
            # render_pair writes the loudness-matched A/B + png)
            meta = render_pair(rec, rules, trial, f'ranker_v0_{pid}')
            break
        else:
            print('SAME', pid, ia.get('fam'), ia.get('win'), flush=True)
            cleanup.drop_our_src2((ia.get('created') or []) + (ib.get('created') or []))
    if meta is None:
        print('RESULT', json.dumps(dict(found=False, reason='no_pair_where_ranker_differs')), flush=True)
        return 1
    print('CLIP', json.dumps({k: meta[k] for k in ('id', 'pair', 'png', 'AB', 'A', 'B', 'tick_s') if k in meta}, default=str), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
