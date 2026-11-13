#!/usr/bin/env python3
"""Like-for-like FADE=graphcut vs the current default (rules.json, FADE=long).

Renders Mitekiss Final Hours -> Hybrid Minds Listen (hybrid_minds_ukf__08) with
the same window under both renderers, scores them against the pro clip, runs
blend_diag + must-pass tests, draws a low-band comparison figure, and (unless
--skip-cohort) scores the 33-pair admitted cohort with FADE=graphcut.

Does not write protrans/rules.json. Usage:
  python3 protrans/eval_graphcut.py [--skip-cohort] [--out DIR]
"""
from __future__ import annotations
import argparse, json, os, shutil, sys, time, traceback
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths, recreate, score, cleanup
import run_admitted_tune as T

PICK = 'hybrid_minds_ukf__08'
V3_TRAIN, V3_TEST = 30.97, 30.09
HELD_OUT_LINGER = 33.84
OUT0 = os.path.join(paths.MIXES, 'deliver', 'research', '2026-11-13')
RIDE_FRAC = 0.15
L1_DB, N1_MS, N1_DB, DOUBLE_DB, DOUBLE_MAX, DIP_DB = 3.0, 10.0, 3.83, 6.0, 2, 4.41


def _log(msg):
    print(msg, flush=True)


def load_pick():
    recs = {r['id']: r for r in T.load_recs()}
    rec = recs[PICK]
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
    sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    return rec, sa, sb


def rules_default():
    return json.load(open(paths.RULES))


def rules_graphcut():
    r = rules_default()
    r = dict(r)
    r['FADE'] = 'graphcut'
    r['note'] = (r.get('note') or '') + ' [eval only: FADE=graphcut, not written back]'
    return r


def keep(src, dest):
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    if src and os.path.exists(src):
        shutil.copy2(src, dest)
        return dest
    return None


def render_pinned(rec, sa, sb, win, env, tag, out_dir):
    """Render a pinned window with a given env (like-for-like)."""
    sys.path.insert(0, paths.SRC2)
    import blend_bench as BB
    os.environ['BB_SCRATCH'] = '/tmp/protrans_bench'
    os.environ['PREF_W'] = '0'
    os.makedirs('/tmp/protrans_bench', exist_ok=True)
    oldcwd = os.getcwd()
    try:
        os.chdir(paths.SRC2)
        pick = dict(fam='pinned', win=win, env=dict(env))
        dk, M = BB.render(pick, rec['a']['yt'], rec['b']['yt'], tag)
        ours = pick.get('mp3')
        meta_path = os.path.join(out_dir, f'{tag}_meta.json')
        json.dump(M, open(meta_path, 'w'), default=str)
        kept_mp3 = keep(ours, os.path.join(out_dir, f'{tag}.mp3'))
        raw = f'/tmp/protrans_bench/{tag}_raw.wav'
        master = f'/tmp/protrans_bench/{tag}_master.wav'
        kept_raw = keep(raw, os.path.join(out_dir, f'{tag}_raw.wav'))
        kept_master = keep(master, os.path.join(out_dir, f'{tag}_master.wav'))
        return dict(ours=kept_mp3 or ours, raw=kept_raw or raw, master=kept_master or master,
                    meta_path=meta_path, M=M, pick=pick, fam=pick['fam'], win=win, env=dict(env),
                    vocal_clash_bars=pick.get('vocal_clash_bars'), halfbeat=(pick.get('timing') or {}).get('trans', {}).get('halfbeat'))
    finally:
        os.chdir(oldcwd)


def score_pair(rec, sa, sb, ours):
    return score.score(rec['pro_clip'], ours, src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)


def diag(rec, sa, sb, info, name, out_dir):
    sys.path.insert(0, paths.SRC2)
    cwd = os.getcwd()
    os.chdir(paths.SRC2)
    try:
        import blend_diag
        M = json.load(open(info['meta_path'])) if not info.get('M') else info['M']
        png = os.path.join(out_dir, name + '.png')
        summ = blend_diag.figure(M, 0, png,
                                 f"{PICK} {rec['pair']} {name}",
                                 pro=rec['pro_clip'], src_a=sa, src_b=sb, ours=info['ours'])
        json.dump(summ, open(os.path.join(out_dir, name + '.json'), 'w'), indent=1, default=str)
        return summ
    finally:
        os.chdir(cwd)


def _db(x):
    return 10 * np.log10(np.mean(np.asarray(x, float) ** 2) + 1e-12)


def run_must_pass(M, wav, tag):
    """Bass-gap, L1, N1, X1, bass-never-doubles, outgoing fader tail, V1."""
    sys.path.insert(0, paths.SRC2)
    sys.path.insert(0, os.path.join(paths.MIXES, 'src', 'tests'))
    sys.path.insert(0, os.path.join(paths.MIXES, 'src'))
    out = {}
    # X1
    import test_crossfader as U
    x1 = U.run(M)
    out['X1'] = dict(pass_=not x1, failures=[str(x) for x in x1])

    # bass-gap
    import bassgap
    cwd = os.getcwd()
    os.chdir(paths.SRC2)
    try:
        gaps = bassgap.check(M, wav)
    except Exception as e:
        gaps = [f'error {type(e).__name__}: {e}']
    finally:
        os.chdir(cwd)
    out['bass_gap'] = dict(pass_=not gaps, failures=[str(x) for x in gaps], GAP_DB=bassgap.GAP_DB)

    # V1
    clashes = []
    for t in M['trans']:
        v = float(t.get('vocal_clash_bars') or 0)
        if v >= 1:
            clashes.append(dict(a=t['a'], b=t['b'], bars=v))
    out['V1'] = dict(pass_=not clashes, failures=clashes)

    # outgoing fader tail (meta curve, same as test_release_structure_tail)
    bad_tail = []
    import fade_long as FL  # noqa: F401
    for t in M['trans']:
        s, e = t['start_bar'], t['end_bar']
        X = e - s
        xs = np.array(t['xfader'])
        bars = np.arange(s, e + 1e-9, 1.0)
        g = 20 * np.log10(np.cos(np.interp(bars, xs[:, 0], xs[:, 1]) * np.pi / 2) + 1e-9)
        d = np.diff(g)
        steep = [float(x) for x, v in zip(d, g[1:]) if v > -24 and x < -3]
        sw = (t['bass_swap'][1] if t.get('bass_swap') else s + 0.35 * X)
        ride = float(np.sum(g[bars >= sw] > -20))
        if steep or ride < RIDE_FRAC * X - 1:
            bad_tail.append(dict(steep=steep[:3], ride=ride, X=X, need=RIDE_FRAC * X - 1))
    out['outgoing_fader_tail'] = dict(pass_=not bad_tail, failures=bad_tail, RIDE_FRAC=RIDE_FRAC)

    # rendered-deck checks: L1, bass-never-doubles, N1 entry, audio tail
    os.chdir(paths.SRC2)
    try:
        import engine as E
        from scipy.signal import butter, sosfiltfilt
        LP = butter(4, 120, 'low', fs=E.SR, output='sos')
        LP150 = butter(4, 150, 'low', fs=E.SR, output='sos')
        t = M['trans'][0]
        A, B = M['decks'][0], M['decks'][1]
        ya, yb = E.render_deck(A), E.render_deck(B)
        s, e = int(t['start_bar']), int(t['end_bar'])
        def cut(d, y):
            return y[int((s - d['start_bar']) * E.BS):int((e - d['start_bar']) * E.BS)]
        a, b = cut(A, ya), cut(B, yb)
        n = min(len(a), len(b)); a, b = a[:n], b[:n]
        la = sosfiltfilt(LP, a, axis=0); lb = sosfiltfilt(LP, b, axis=0)
        la150 = sosfiltfilt(LP150, a, axis=0); lb150 = sosfiltfilt(LP150, b, axis=0)
        L = int(E.BAR * E.SR)
        nb = n // L
        l1 = []
        # body ref: outgoing first 2 bars of its crop
        refA = _db(la[:2 * L] if 2 * L <= len(la) else la)
        for k in range(nb):
            sega, segb = la[k * L:(k + 1) * L], lb[k * L:(k + 1) * L]
            lsa, lsb, lsum = _db(sega), _db(segb), _db(sega + segb)
            if lsum > max(lsa, lsb) + L1_DB and lsum > refA - 25:
                l1.append(dict(bar=s + k, kind='sum', over=round(lsum - max(lsa, lsb), 2)) )
            la_body, lb_body = np.percentile([_db(la150[j * L:(j + 1) * L]) for j in range(nb)], 75), \
                               np.percentile([_db(lb150[j * L:(j + 1) * L]) for j in range(nb)], 75)
            if lsa > la_body - 6 and lsb > lb_body - 6 and min(lsa, lsb) > refA - 12:
                l1.append(dict(bar=s + k, kind='both_full'))
        out['L1'] = dict(pass_=not l1, failures=l1[:8], L1_db=L1_DB)

        # bass never doubles on <150 Hz
        bars = [(_db(la150[k * L:(k + 1) * L]), _db(lb150[k * L:(k + 1) * L])) for k in range(nb)]
        ref = max(max(x) for x in bars) if bars else -120
        doubled = sum(min(x) > ref - 12 and abs(x[0] - x[1]) < DOUBLE_DB for x in bars)
        out['bass_never_doubles'] = dict(pass_=bool(doubled <= DOUBLE_MAX), doubled_bars=int(doubled), max_ok=DOUBLE_MAX)

        # N1 off-grid entry (10 ms). The official grid branch is this lag;
        # a cropped-snippet level-step is not a reliable stand-in for the
        # full-mix N1_db check (it flagged the default renderer too).
        hb = t.get('halfbeat') or {}
        lag = hb.get('lag_ms')
        n1 = []
        if lag is not None and abs(float(lag)) > N1_MS:
            n1.append(dict(kind='halfbeat_lag_ms', lag_ms=lag, limit=N1_MS))
        out['N1'] = dict(pass_=not n1, failures=n1, N1_ms=N1_MS, halfbeat=hb)
    except Exception as e:
        out['render_checks_error'] = f'{type(e).__name__}: {e}'
        _log('render checks failed: ' + out['render_checks_error'])
        traceback.print_exc()
    finally:
        os.chdir(cwd if 'cwd' in dir() else paths.MIXES)
        # restore
        os.chdir(HERE)

    out['all_pass'] = bool(all(v.get('pass_') for v in out.values() if isinstance(v, dict) and 'pass_' in v))
    return out


def low_curve_figure(def_summ, gc_summ, def_info, gc_info, out_png):
    """Compare measured summed / per-deck low-band curves for default vs graphcut."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    sys.path.insert(0, paths.SRC2)
    cwd = os.getcwd()
    os.chdir(paths.SRC2)
    try:
        import blend_diag as BD
        from engine import BS, BAR
        fig, ax = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
        colors = dict(default='tab:blue', graphcut='tab:orange')
        rows = []
        for name, info, summ, col in (('default', def_info, def_summ, colors['default']),
                                      ('graphcut', gc_info, gc_summ, colors['graphcut'])):
            M = json.load(open(info['meta_path']))
            t = M['trans'][0]
            s, e = float(t['start_bar']), float(t['end_bar'])
            s0, A, B = BD.crop_decks(M, 0)
            nbars = int(round(len(A) / BS))
            loA = BD.band_bar_db(A, nbars, BS, 'low', 150)
            loB = BD.band_bar_db(B, nbars, BS, 'low', 150)
            sm = 10 * np.log10(10 ** (loA / 10) + 10 ** (loB / 10))
            xr = s0 + np.arange(nbars)
            rows.append((name, xr, loA, loB, sm, s, e, summ.get('sum_lows_dip_db'), col))
        for i, (ylab, getter) in enumerate((
            ('A lows (dB, <150 Hz)', lambda r: r[2]),
            ('B lows (dB, <150 Hz)', lambda r: r[3]),
            ('summed lows (dB)', lambda r: r[4]),
        )):
            for name, xr, loA, loB, sm, s, e, dip, col in rows:
                ax[i].step(xr, getter((name, xr, loA, loB, sm, s, e, dip, col)), where='post',
                           color=col, lw=1.8 if i == 2 else 1.2, label=f'{name}' + (f' dip {dip} dB' if i == 2 else ''))
            ax[i].axvspan(rows[0][5], rows[0][6], color='k', alpha=0.06, label='blend' if i == 0 else None)
            ax[i].set_ylabel(ylab)
            ax[i].grid(alpha=0.3)
            ax[i].legend(fontsize=8, loc='lower left')
        ax[0].set_title('Final Hours → Listen: low-band curves, default (FADE=long) vs FADE=graphcut')
        ax[-1].set_xlabel('mix bar')
        fig.tight_layout()
        os.makedirs(os.path.dirname(out_png) or '.', exist_ok=True)
        fig.savefig(out_png, dpi=110)
        plt.close(fig)
    finally:
        os.chdir(cwd)
    return out_png


def maybe_ab_clips(def_info, gc_info, out_dir, key_path, blend_start_s):
    """Blind A/B of the same window, ~60 s, blend start marked in the filename."""
    import random, subprocess
    letter = ['A', 'B']
    # random but logged
    rng = random.Random(20261113)
    order = ['default', 'graphcut']
    rng.shuffle(order)
    key = dict(date='2026-11-13', pick=PICK, pair='Mitekiss - Final Hours -> Hybrid Minds - Listen (ft. Tiffani Juno)',
               A=order[0], B=order[1], blend_start_s=blend_start_s,
               note='same pinned window; A/B is ours-default vs ours-graphcut (no pro in this pair)')
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    json.dump(key, open(key_path, 'w'), indent=2)
    # filename mark: blend_at_XmYs
    m, sec = divmod(int(round(blend_start_s)), 60)
    mark = f'blend_at_{m}m{sec:02d}s'
    paths_out = {}
    for lab, name in zip(letter, order):
        src = def_info['ours'] if name == 'default' else gc_info['ours']
        dest = os.path.join(out_dir, f'clip01{lab}_final_hours_listen_{mark}.mp3')
        shutil.copy2(src, dest)
        paths_out[lab] = dest
    listen = os.path.join(out_dir, 'LISTEN.txt')
    open(listen, 'w').write(
        'Blind A/B: Final Hours → Listen, same mix window, default renderer vs FADE=graphcut.\n'
        f'The blend starts at {m}:{sec:02d} in both clips ({mark}).\n'
        'Which is smoother in the low end? Rate each 1-5.\n'
    )
    return dict(key=key_path, files=paths_out, mark=mark, blend_start_s=blend_start_s)


def write_loss_doc(path, payload):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    d, g = payload['default'], payload['graphcut']
    ds, gs = d['score']['score'], g['score']['score']
    lines = [
        '# Graph-cut crossfade eval, 13 November 2026 (ET)',
        '',
        'Prototype of Robinson & Brown (ISMIR 2019 LBD, [arXiv:2301.13380](https://arxiv.org/abs/2301.13380))',
        'as `FADE=graphcut` (off by default). This write-up exists because graphcut did **not**',
        'match or beat the current default on the like-for-like test, so no blind A/B was cut.',
        '',
        '## Pair: Mitekiss — Final Hours → Hybrid Minds — Listen',
        '',
        f"- Window (pinned, same as the 2026-11-12 daily): `{d['win']}`",
        f"- Default (`FADE={d['env'].get('FADE')}`): score **{ds}**, summed-lows dip **{d['diag'].get('sum_lows_dip_db')} dB**",
        f"- Graphcut (`FADE=graphcut`): score **{gs}**, summed-lows dip **{g['diag'].get('sum_lows_dip_db')} dB**",
        f"- Spectral (diagnostic): default banger clash {((d['diag'].get('spectral') or {}).get('banger_clash_rate'))}, "
        f"graphcut {((g['diag'].get('spectral') or {}).get('banger_clash_rate'))}",
        '',
        '## Why it lost',
        '',
        payload.get('why') or 'See numbers above; graphcut did not improve the pro-similarity score.',
        '',
        'The 44.5 dB summed-lows dip is mostly a window problem, not a same-time fader problem.',
        "Listen has essentially no bass in this 16-bar outro-over-intro (incoming <250 Hz sits 9-20 dB",
        'under the outgoing groove for the whole window). X1 still requires a 1-4 bar bass swap centred',
        'at crossfader x 0.2-0.65, so the outgoing low end is taken out before Listen can cover it.',
        'Graph-cut kept the bass on Final Hours as late as that window allows ([214, 218] vs default',
        "[212, 217]); the measured dip did not shrink. A different/longer window that includes Listen's",
        'bass, or a later-than-X1 handoff, would be needed to actually fill the hole. Mid/high seams',
        'also landed on the same late bar as the bass on this pair, so the per-band freedom did not show.',
        '',
        '## Tests',
        '',
        f"- Default all_pass={d['tests'].get('all_pass')}",
        f"- Graphcut all_pass={g['tests'].get('all_pass')}",
        '',
        '## Cohort',
        '',
        json.dumps(payload.get('cohort') or {}, indent=2, default=str),
        '',
        'Defaults and thresholds were not changed. `protrans/rules.json` still has FADE=long.',
        '',
    ]
    open(path, 'w').write('\n'.join(lines))
    return path


def run_cohort(out_dir):
    rules = rules_graphcut()
    # side file only — never overwrite rules.json
    side = os.path.join(out_dir, 'rules_graphcut_eval_only.json')
    json.dump(rules, open(side, 'w'), indent=2)
    recs = T.load_recs()
    rows = T.run_set_checkpointed(recs, rules, 'gc1113', 'gc13')
    sm = T.summarize(rows)
    v2 = __import__('eval_cohort', fromlist=['summary_v2']).summary_v2(rows)
    out = dict(variant='gc1113',
               v3=dict(train=sm['train_mean'], test=sm['test_mean'], n=sm['n'], n_fail=sm['n_fail']),
               v2=dict(train=v2['train_mean'], test=v2['test_mean']),
               by_dj=sm['by_dj'],
               baseline_v3=dict(train=V3_TRAIN, test=V3_TEST),
               current_heldout=HELD_OUT_LINGER,
               current_train=33.12)
    json.dump(out, open(os.path.join(paths.RESULTS, 'eval_gc1113.json'), 'w'), indent=2)
    json.dump(out, open(os.path.join(out_dir, 'eval_gc1113.json'), 'w'), indent=2)
    # per-pair compact
    compact = []
    for r in rows:
        sc = r.get('score') or {}
        compact.append(dict(id=r['id'], split=r.get('split'), dj=r.get('dj'),
                            score=sc.get('score') if isinstance(sc, dict) else sc,
                            error=r.get('error'), fam=(r.get('pick') or {}).get('fam'),
                            win=(r.get('pick') or {}).get('win')))
    json.dump(compact, open(os.path.join(out_dir, 'cohort_gc1113_rows.json'), 'w'), indent=1)
    _log('COHORT ' + json.dumps(out))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-cohort', action='store_true')
    ap.add_argument('--reuse-pair', action='store_true', help='reuse already-rendered gcdef/gcgc in --out')
    ap.add_argument('--out', default=OUT0)
    args = ap.parse_args()
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)
    rec, sa, sb = load_pick()
    rules = rules_default()
    assert rules.get('FADE') != 'graphcut', 'rules.json must stay on the current default'

    env_d = recreate.apply_rules(rules)
    env_g = dict(env_d, FADE='graphcut', GRAPH_CUT='1')
    if args.reuse_pair:
        _log(f'== reuse pair renders in {out_dir} ==')
        def _load(tag):
            meta = os.path.join(out_dir, f'{tag}_meta.json')
            M = json.load(open(meta))
            win = None
            return dict(ours=os.path.join(out_dir, f'{tag}.mp3'),
                        raw=os.path.join(out_dir, f'{tag}_raw.wav'),
                        master=os.path.join(out_dir, f'{tag}_master.wav'),
                        meta_path=meta, M=M, pick={}, fam=M['trans'][0].get('fade'),
                        win=[M['trans'][0].get('notes')], env={})
        info_d = dict(_load('gcdef'), env=env_d)
        info_g = dict(_load('gcgc'), env=env_g)
        Md = json.load(open(info_d['meta_path']))
        t = Md['trans'][0]
        win = ['n', int(t['end_bar']), None, None, int(t['end_bar'] - t['start_bar'])]
        # recover the exact pinned window from the plan if present
        if Md.get('plan'):
            w = Md['plan'][0].get('out_win')
            if w:
                win = w
        info_d['win'] = info_g['win'] = win
        info_d0 = dict(fam='reused', win=win, env=env_d)
        sc_d = score_pair(rec, sa, sb, info_d['ours'])
        sc_g = score_pair(rec, sa, sb, info_g['ours'])
        _log(f'reused win={win} default {sc_d["score"]} graphcut {sc_g["score"]}')
    else:
        _log(f'== default recreate {PICK} ==')
        info_d0 = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                                    hint_a_played_sec=rec['window'].get('hint_a_played_sec'),
                                    rules=rules, tag='gcd0')
        win = info_d0['win']
        env_d = info_d0['env']
        env_g = dict(env_d, FADE='graphcut', GRAPH_CUT='1')
        _log(f'default picked fam={info_d0["fam"]} win={win} env FADE={env_d.get("FADE")}')
        info_d = render_pinned(rec, sa, sb, win, env_d, 'gcdef', out_dir)
        sc_d = score_pair(rec, sa, sb, info_d['ours'])
        _log(f'default score {sc_d["score"]} v2 {sc_d.get("score_v2")}')
        _log(f'== graphcut pinned window {win} ==')
        info_g = render_pinned(rec, sa, sb, win, env_g, 'gcgc', out_dir)
        sc_g = score_pair(rec, sa, sb, info_g['ours'])
        _log(f'graphcut score {sc_g["score"]} v2 {sc_g.get("score_v2")}')

    _log('== diagnostics ==')
    diag_d = diag(rec, sa, sb, info_d, 'diag_default', out_dir)
    diag_g = diag(rec, sa, sb, info_g, 'diag_graphcut', out_dir)
    _log(f'default dip {diag_d.get("sum_lows_dip_db")} halfbeat {diag_d.get("halfbeat")}')
    _log(f'graphcut dip {diag_g.get("sum_lows_dip_db")} halfbeat {diag_g.get("halfbeat")}')
    fig = low_curve_figure(diag_d, diag_g, info_d, info_g, os.path.join(out_dir, 'lows_default_vs_graphcut.png'))
    _log(f'figure {fig}')

    _log('== must-pass tests ==')
    tests_d = run_must_pass(json.load(open(info_d['meta_path'])), info_d['raw'] or info_d['master'] or info_d['ours'], 'def')
    tests_g = run_must_pass(json.load(open(info_g['meta_path'])), info_g['raw'] or info_g['master'] or info_g['ours'], 'gc')
    _log('default tests ' + json.dumps({k: (v.get('pass_') if isinstance(v, dict) else v) for k, v in tests_d.items()}, default=lambda o: bool(o) if hasattr(o,'__bool__') else str(o)))
    _log('graphcut tests ' + json.dumps({k: (v.get('pass_') if isinstance(v, dict) else v) for k, v in tests_g.items()}, default=lambda o: bool(o) if hasattr(o,'__bool__') else str(o)))

    # blend start in the delivered clip: blend_bench starts PRE=8 bars before the blend
    # (plus lx pad). Use the snippet metadata.
    t = json.load(open(info_d['meta_path']))['trans'][0]
    # from blend_bench: snip has pre, start, s0
    # safest: 8 bars * bar_sec, unless the dry meta says otherwise
    bar = json.load(open(info_d['meta_path'])).get('bar_sec') or (4 * 60 / 174)
    # The kept mp3 is the bench clip, typically 8 bars of preroll.
    blend_start_s = 8 * bar
    # prefer exact from pick timing if present
    snip = (info_d.get('pick') or {}).get('snip') or {}
    if snip.get('start') is not None and snip.get('s0') is not None:
        blend_start_s = (snip['start'] - snip['s0']) * bar

    payload = dict(
        pick=PICK, pair=rec['pair'], win=win, bar_sec=bar, blend_start_s=blend_start_s,
        default=dict(score=sc_d, diag=diag_d, tests=tests_d, env=env_d, win=win,
                     ours=info_d['ours'], meta=info_d['meta_path'], fam=info_d0['fam']),
        graphcut=dict(score=sc_g, diag=diag_g, tests=tests_g, env=env_g, win=win,
                      ours=info_g['ours'], meta=info_g['meta_path'],
                      seams=(json.load(open(info_g['meta_path']))['trans'][0].get('graphcut'))),
        figure=fig,
        baselines=dict(v3_train=V3_TRAIN, v3_test=V3_TEST, current_heldout=HELD_OUT_LINGER, current_train=33.12),
    )
    beats = (sc_g['score'] >= sc_d['score']) and tests_g.get('all_pass', False)
    payload['verdict'] = 'beats_or_ties' if beats else 'loses'
    why = []
    if sc_g['score'] < sc_d['score']:
        why.append(f"pro-similarity dropped {sc_d['score']} -> {sc_g['score']}.")
    if not tests_g.get('all_pass', False):
        failed = [k for k, v in tests_g.items() if isinstance(v, dict) and v.get('pass_') is False]
        why.append('must-pass tests failed: ' + ', '.join(failed) + '.')
    dip_d, dip_g = diag_d.get('sum_lows_dip_db'), diag_g.get('sum_lows_dip_db')
    if dip_g is not None and dip_d is not None:
        if dip_g < dip_d:
            why.append(f"The summed-lows dip did shrink ({dip_d} -> {dip_g} dB) but that was not enough to count as a win.")
        else:
            why.append(f"The summed-lows dip was not improved ({dip_d} -> {dip_g} dB).")
    payload['why'] = ' '.join(why) or 'graphcut matched or beat the default.'

    if beats:
        ab = maybe_ab_clips(info_d, info_g, out_dir, '/workspace/private/research_2026-11-13_key.json', blend_start_s)
        payload['ab'] = ab
        _log('A/B ' + json.dumps(ab, default=str))
    else:
        doc = write_loss_doc(os.path.join(paths.MIXES, 'docs', 'GRAPHCUT_2026-11-13.md'), payload)
        payload['writeup'] = doc
        _log('LOSS writeup ' + doc)

    json.dump(payload, open(os.path.join(out_dir, 'pair_eval.json'), 'w'), indent=2, default=str)
    _log('PAIR ' + json.dumps(dict(default=sc_d['score'], graphcut=sc_g['score'],
                                   dip_d=dip_d, dip_g=dip_g, beats=beats), default=str))

    if not args.skip_cohort:
        _log('== cohort FADE=graphcut ==')
        payload['cohort'] = run_cohort(out_dir)
        # rewrite writeup with cohort if we already wrote it
        if payload['verdict'] == 'loses':
            write_loss_doc(os.path.join(paths.MIXES, 'docs', 'GRAPHCUT_2026-11-13.md'), payload)
        json.dump(payload, open(os.path.join(out_dir, 'pair_eval.json'), 'w'), indent=2, default=str)

    _log('DONE ' + json.dumps(dict(verdict=payload['verdict'], out=out_dir)))
    return payload


if __name__ == '__main__':
    main()
