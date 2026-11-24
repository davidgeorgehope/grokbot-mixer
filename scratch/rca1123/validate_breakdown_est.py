#!/usr/bin/env python3
"""Validate BREAKDOWN_PHASE_EST on (a) the pro js13 clip, (b) known trainwrecks."""
import json, os, sys, shutil
from pathlib import Path
import numpy as np
import soundfile as sf

os.chdir('/workspace/mixes/src2')
sys.path[:0] = ['/workspace/mixes/src2', '/workspace/mixes/protrans', '/workspace/mixes/src/eval']
import breakdown_phase_est as B
import blend_diag as D
import engine as E
import halfbeat as H
import score as S
import control_curves as CC

OUT = Path('/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-23_structbreak_ride')
OUT.mkdir(parents=True, exist_ok=True)
A_ID, B_ID = 'u6cggHmZEAs', 'SqzxwPEa-DI'
PRO = '/workspace/mixes/protrans/clips/train/joe_syntax_hospital__13/pro.wav'
SA, SB = f'/workspace/mixes/lib/{A_ID}.m4a', f'/workspace/mixes/lib/{B_ID}.m4a'
R12_MP3 = '/workspace/mixes/deliver/ab/mix07r12_grid_Parallel_25m23.mp3'
R12_TIMING = '/workspace/mixes/deliver/ab/mix07r12_grid_Parallel_25m23.timing.json'
R17_MP3 = '/workspace/mixes/deliver/ab/mix07r17_grid_Parallel_24m49.mp3'
R17_TIMING = '/workspace/mixes/deliver/ab/mix07r17_grid_Parallel_24m49.timing.json'


def place_source(yp44, src_m4a, st_id, sr=E.SR):
    """Locate with score._load (seconds, any sr) and place st/<id>.wav at 44.1 kHz."""
    y22 = S._load(src_m4a) if src_m4a and Path(src_m4a).exists() else S._load(f'st/{st_id}.wav')
    yp22 = S._load(PRO)
    ln = S._deck_line(yp22, CC.bandpow(yp22), S._fine_env(yp22), src_m4a if src_m4a and Path(src_m4a).exists() else f'st/{st_id}.wav')
    if not ln:
        return None, None
    ys, ssr = sf.read(f'st/{st_id}.wav', dtype='float32', always_2d=True)
    assert ssr == sr
    ts = (np.arange(len(yp44)) / sr - ln['a']) / ln['s']
    placed = np.stack([
        np.interp(ts * sr, np.arange(len(ys)), ys[:, ch], left=0, right=0).astype(np.float32)
        for ch in range(ys.shape[1])
    ], 1)
    return placed, ln



def official_and_est(yA, yB, s0, start, end, a_id, src_bars, force=True):
    off = B.measure(yA, yB, s0, start, end, E.BS, E.SR, E.BEAT,
                    a_id=a_id, src_bars=src_bars, force=False)
    # official with flag off
    est = B.measure(yA, yB, s0, start, end, E.BS, E.SR, E.BEAT,
                    a_id=a_id, src_bars=src_bars, force=force)
    return off, est


def validate_pro():
    yp44, sr = sf.read(PRO, dtype='float32', always_2d=True)
    assert sr == E.SR
    print('PRO dur', len(yp44)/sr)
    yA, lnA = place_source(yp44, SA, A_ID)
    yB, lnB = place_source(yp44, SB, B_ID)
    print('PRO lines', lnA, lnB)
    gA = json.load(open('st/u6cggHmZEAs.json'))
    downs = np.array(gA['downs'], float)
    t0 = float(lnA['a'] + lnA['s'] * downs[128])
    t_end = len(yp44) / sr - 0.05
    n_bars = int(np.floor((min(float(lnA['a'] + lnA['s'] * downs[min(160, len(downs)-1)]), t_end) - t0) / E.BAR))
    n_bars = max(8, min(32, n_bars))
    print('PRO overlap t0', round(t0, 3), 'n_bars', n_bars, 't1', round(t0 + n_bars*E.BAR, 3))
    i0 = max(0, int(round(t0 * sr)))
    need = int(round(n_bars * E.BS))
    def crop(y):
        seg = y[i0:i0+need]
        if len(seg) < need:
            seg = np.pad(seg, ((0, need-len(seg)), (0, 0)))
        return seg[:need]
    yAc, yBc = crop(yA), crop(yB)
    src = list(range(128, 128 + n_bars))
    off, est = official_and_est(yAc, yBc, 0, 0, n_bars, A_ID, src, force=True)
    def brief(r):
        return {k: r.get(k) for k in ('family','median_ms','ok','n','n_snare','n_kick','usable','active')}
    print('PRO official', brief(off))
    print('PRO est     ', brief(est), 'reason', (est.get('reason') or {}).get('why'))
    os.environ['BREAKDOWN_PHASE_EST'] = '1'
    auto = B.measure(yAc, yBc, 0, 0, n_bars, E.BS, E.SR, E.BEAT, a_id=A_ID, src_bars=src, force=False)
    os.environ.pop('BREAKDOWN_PHASE_EST', None)
    print('PRO flag-on auto', brief(auto), (auto.get('reason') or {}).get('why'))
    return dict(official=off, forced=est, auto=auto, lines=dict(A=lnA, B=lnB),
                t0=t0, n_bars=n_bars, dur=len(yp44)/sr)


def render_timing_decks(timing_path):
    T = json.load(open(timing_path))
    s0, s1 = int(T['clip_start_bar']), int(T['clip_end_bar'])
    n = int(round((s1 - s0) * E.BS))
    ys = []
    for d in T['decks']:
        fm = d['full_map']
        # timing full_map is already the deck from d['start_bar']
        j0 = max(0, s0 - int(d['start_bar']))
        j1 = min(len(fm), s1 - int(d['start_bar']))
        m = [s for s, _ in fm[j0:j1]]
        tr = E.track(d['id'])
        y = E._bars(tr, m, tr['st']['mix'], int(round(len(m) * E.BS)))
        # place into clip
        o = int(round((d['start_bar'] + j0 - s0) * E.BS))
        Y = np.zeros((n + int(8 * E.BS), 2), np.float32)
        mlen = min(len(y), len(Y) - max(o, 0))
        if o < 0:
            Y[0:mlen] = y[-o:-o+mlen]
        else:
            Y[o:o+mlen] = y[:mlen]
        # apply fader if present
        pts = (d.get('auto') or {}).get('gain') or []
        if pts:
            t = np.arange(n) / E.BS + s0
            g = np.interp(t, [p[0] for p in pts], [p[1] for p in pts]).astype(np.float32)
            Y[:n] *= g[:, None]
        ys.append(Y[:n])
    t = T['trans']
    if isinstance(t, list):
        t = t[0]
    return T, s0, t, ys[0], ys[1]


def validate_clip(tag, timing_path, expect_fail, force=True):
    T, s0, t, yA, yB = render_timing_decks(timing_path)
    a_id, src = T['decks'][0]['id'], []
    # outgoing src bars over the blend
    A = T['decks'][0]
    fm = A['full_map']
    for k in range(int(t['start_bar']), int(t['end_bar'])):
        j = k - int(A['start_bar'])
        if 0 <= j < len(fm) and fm[j][1] == 'mix':
            src.append(int(fm[j][0]))
    print(f'\n==== {tag} {a_id} blend {t["start_bar"]}-{t["end_bar"]} src {src[:3]}..{src[-3:] if src else []} n={len(src)}')
    # detector
    active, rec = B.outgoing_is_breakdown_ht(a_id, src)
    print('  detector', active, rec.get('why'), 'margin', rec.get('local_margin'), 'ht', rec.get('ht_hit'))
    off = B.measure(yA, yB, s0, t['start_bar'], t['end_bar'], E.BS, E.SR, E.BEAT,
                    a_id=a_id, src_bars=src, force=False)
    est = B.measure(yA, yB, s0, t['start_bar'], t['end_bar'], E.BS, E.SR, E.BEAT,
                    a_id=a_id, src_bars=src, force=True)
    os.environ['BREAKDOWN_PHASE_EST'] = '1'
    auto = B.measure(yA, yB, s0, t['start_bar'], t['end_bar'], E.BS, E.SR, E.BEAT,
                     a_id=a_id, src_bars=src, force=False)
    os.environ.pop('BREAKDOWN_PHASE_EST', None)
    def brief(r):
        return {k: r.get(k) for k in ('active','family','median_ms','ok','usable','n','n_snare','n_kick')}
    print('  official', brief(off))
    print('  forced  ', brief(est), 'used', (est.get('used_ms') or [])[:8])
    print('  flag-on ', brief(auto), auto.get('reason',{}).get('why'))
    # For a known wreck, the estimator (forced) must fail the 40 ms line
    forced_ok = bool(est.get('usable') and not est.get('ok')) if expect_fail else bool(est.get('ok'))
    auto_ok = True
    if expect_fail:
        # flag-on path must not pass a wreck: either official (if not activated) fails, or est fails
        auto_ok = not auto.get('ok')
    result = dict(tag=tag, expect_fail=expect_fail, detector=rec, official=off, forced=est, auto=auto,
                  forced_verdict_ok=forced_ok, auto_verdict_ok=auto_ok)
    return result


def main():
    report = {}
    print('======== (a) pro S.P.Y → Meteorites')
    report['pro'] = validate_pro()
    pro_pass = bool(report['pro']['auto'].get('ok') and report['pro']['auto'].get('active'))
    # auto should activate and pass; forced should also pass
    pro_pass = pro_pass and bool(report['pro']['forced'].get('ok'))
    print('PRO_PASS', pro_pass)

    print('\n======== (b) known trainwrecks')
    wrecks = []
    if Path(R12_TIMING).exists():
        r = validate_clip('mix07r12 Daydreaming→Parallel (heard trainwreck)', R12_TIMING, expect_fail=True)
        wrecks.append(r)
        print('R12_FORCED_FAILS', r['forced_verdict_ok'], 'R12_AUTO_DOES_NOT_PASS', r['auto_verdict_ok'])
    else:
        print('R12 timing missing')
    # r17 is the heard-OK rewrite of the same pair — should not be required to fail
    if Path(R17_TIMING).exists():
        r = validate_clip('mix07r17 Daydreaming→Parallel (heard OK, not a trainwreck)', R17_TIMING, expect_fail=False)
        wrecks.append(r)
        print('R17_INFO forced_ok_as_pass_target', r['forced_verdict_ok'], 'auto', r['auto'].get('ok'), r['auto'].get('active'))
    report['wrecks'] = wrecks
    report['pro_pass'] = pro_pass
    report['r12_fail_ok'] = bool(wrecks and wrecks[0]['tag'].startswith('mix07r12') and wrecks[0]['forced_verdict_ok'] and wrecks[0]['auto_verdict_ok'])
    json.dump(report, open(OUT / 'estimator_validation.json', 'w'), indent=2, default=str)
    print('\nWROTE', OUT / 'estimator_validation.json')
    print('SUMMARY pro_pass', report['pro_pass'], 'r12_still_fails', report['r12_fail_ok'])
    return report

if __name__ == '__main__':
    main()
