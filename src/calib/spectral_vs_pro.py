#!/usr/bin/env python3
"""Calibrate the diagnostic spectral collision / continuity scorer on pro transitions.

Scores admitted protrans clips (same corpus index as guard_vs_pro.py), writes
pro median / p95, fits score scales so a penalty equal to the pro median maps
to 0.70, then scores Mix 08 v2 (r11c), Mix 08 long1h, the known-bad Shine In
-> Dusk To Dawn equal-level clash (2026-11-11), and the daily A/B clips that
the listener rated (protrans/log.jsonl). Diagnostic only: does not change any test
threshold, does not write protrans/rules.json, and does not add a failing gate.

Usage (from /workspace/mixes):
  python3 src/calib/spectral_vs_pro.py
  # or via jobs/runjob.sh spectral-vs-pro python3 src/calib/spectral_vs_pro.py
"""
from __future__ import annotations
import json, os, sys, traceback, datetime, subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC2 = ROOT / 'src2'
PRO = ROOT / 'protrans'
sys.path.insert(0, str(SRC2))
sys.path.insert(0, str(PRO))
sys.path.insert(0, str(ROOT / 'src' / 'calib'))

import guard_vs_pro as G
import diagnose_gap as DG
import score as PS
import spectral_score as SS

OUT_JSON = Path(__file__).resolve().parent / 'spectral_vs_pro_results.json'
SCALES_JSON = Path(__file__).resolve().parent / 'spectral_scales.json'
REPORT = ROOT / 'docs' / 'SPECTRAL_SCORE_2026-11-12.md'
FIG_DIR = ROOT / 'deliver' / 'spectral' / '2026-11-12'
TITLES = json.load(open(ROOT / 'mix08' / 'titles.json')) if (ROOT / 'mix08' / 'titles.json').exists() else {}

# Daily 2026-11-12 log entry omitted A_is; the listener was told A was the pro (he guessed B).
CLIP_ROLE_OVERRIDE = {
    '2026-11-12': dict(A='pro', B='ours', note='from the 2026-11-12 session: A was the pro, B was ours'),
}

# Deeper -> Just Hold On (mix 03-60 v1, listener: "horrible"). Audio was later cleaned out.
CRASH_03_CANDIDATES = [
    ROOT / 'dj-mix-03-60.mp3',
    ROOT / 'pro_sets' / 'wav' / 'dj-mix-03-60.wav',
]
CRASH_03_WINDOW = dict(start_s=13 * 60, end_s=14 * 60 + 40,
                       a='F1NCnCxyhqc', b='_K2sC9nrf_A',
                       pair='Kanine & Raphaella – Deeper -> Sub Focus & Wilkinson – Just Hold On (original)')


def now_et():
    tz = datetime.timezone(datetime.timedelta(hours=-5), name='America/New_York')
    return datetime.datetime.now(tz).strftime('%Y-%m-%dT%H:%M:%S-05:00')


def pct(xs, p):
    v = np.asarray([x for x in xs if x is not None and np.isfinite(x)], float)
    if not len(v):
        return None
    return float(np.percentile(v, p))


def dist(xs):
    v = [x for x in xs if x is not None and np.isfinite(x)]
    if not v:
        return dict(n=0, mean=None, median=None, p5=None, p95=None, min=None, max=None)
    a = np.asarray(v, float)
    return dict(n=int(len(a)), mean=round(float(a.mean()), 6), median=round(float(np.median(a)), 6),
                p5=round(float(np.percentile(a, 5)), 6), p95=round(float(np.percentile(a, 95)), 6),
                min=round(float(a.min()), 6), max=round(float(a.max()), 6))


def resample_to_44(y, sr):
    return SS._mono44(y, sr)


def apply_scales(row, scales):
    if row.get('pcol') is None:
        return row
    row = dict(row)
    row['Scol'] = None if scales.get('s_col') is None else round(SS._to_score(row['pcol'], scales['s_col']), 4)
    row['Scty'] = None if scales.get('s_cty') is None else round(SS._to_score(row['pcty'], scales['s_cty']), 4)
    row['scales'] = dict(s_col=scales.get('s_col'), s_cty=scales.get('s_cty'),
                         source=scales.get('source'), note=scales.get('note'))
    return row


def summary_of(rows, keys=('pcol', 'pcty', 'Scol', 'Scty', 'banger_clash_rate')):
    return {k: dist([r.get(k) for r in rows if 'error' not in r]) for k in keys}


def _align_pro_sources(pro_path, src_a, src_b, loc_a=None, loc_b=None):
    """Place both sources onto the mix, refine lag, return mono 44.1 kHz signals."""
    mix = PS._load(str(pro_path))  # 22050, mono
    placed, locs = [], []
    for path, cached in ((src_a, loc_a), (src_b, loc_b)):
        if not path or not os.path.exists(path):
            return None, [None, None]
        loc = None
        if cached and cached.get('mix_t') is not None and cached.get('track_t') is not None:
            loc = dict(mix_t=float(cached['mix_t']), track_t=float(cached['track_t']),
                       z=cached.get('z'), cc=cached.get('cc'), source='cache')
        else:
            import version_match as VM
            hit = VM.locate_in(mix, PS._load(path))
            if hit.get('track_t') is None:
                locs.append(hit)
                return None, locs + [None] * (1 - len(locs))
            loc = dict(hit)
            loc['source'] = 'locate'
        y = DG.place_source(path, loc['track_t'], loc['mix_t'], len(mix))
        y, _ = DG.refine_lag(mix, y)
        placed.append(y)
        locs.append(loc)
    yc = resample_to_44(mix, PS.SR)
    ya = resample_to_44(placed[0], PS.SR)
    yb = resample_to_44(placed[1], PS.SR)
    n = min(len(yc), len(ya), len(yb))
    return (ya[:n], yb[:n], yc[:n]), locs


def score_aligned(ya, yb, yc, start_s, end_s, scales=None, already_gained=False,
                  pre_s=None, post_s=None, plot=None, title=None):
    bar_s = 4 * 60 / 174
    res = SS.score_decks(ya, yb, sr=SS.SR, bar_s=bar_s, start_s=start_s, end_s=end_s,
                         pre_s=pre_s if pre_s is not None else 8 * bar_s,
                         post_s=post_s if post_s is not None else 8 * bar_s,
                         yc=yc, already_gained=already_gained, scales=scales)
    if plot:
        SS.plot_lanes(res, str(plot), title=title)
    return SS.compact(res)


def score_pro_clip(clip, scales=None, plot=None):
    sa, sb = G.src_path(clip['yt_a']), G.src_path(clip['yt_b'])
    aligned, locs = _align_pro_sources(clip['pro_clip'], sa, sb, clip.get('loc_a'), clip.get('loc_b'))
    if aligned is None:
        return dict(diagnostic_only=True, id=clip['id'], pair=clip['pair'], admitted=clip['admitted'],
                    error='align_failed', split=clip.get('split'), dj=clip.get('dj'))
    # Window from contribution activity μ (Manabe §4.3), not the noisy event detector.
    res = score_aligned(*aligned, None, None, scales=scales, already_gained=False,
                        plot=plot, title=f"PRO {clip['id']}: {clip['pair']}")
    res.update(id=clip['id'], pair=clip['pair'], admitted=clip['admitted'],
               split=clip.get('split'), dj=clip.get('dj'), window='activity',
               method='fitted_contributions')
    return res


def score_mix_subprocess(name, nudge, out_json, plot_dir=None, blends=None):
    env = os.environ.copy()
    env['NUDGE'] = nudge
    cmd = [sys.executable, str(SRC2 / 'spectral_score.py'),
           '--meta', f'{name}_meta.json', '--out', str(out_json)]
    if plot_dir:
        Path(plot_dir).mkdir(parents=True, exist_ok=True)
        cmd += ['--plot', str(plot_dir)]
    if blends is not None:
        cmd += ['--blends', ','.join(str(i) for i in blends)]
    print(f'  mix {name} NUDGE={nudge}', flush=True)
    r = subprocess.run(cmd, cwd=str(SRC2), env=env)
    if r.returncode != 0 or not Path(out_json).exists():
        return [dict(diagnostic_only=True, error=f'subprocess rc={r.returncode}', mix=name)]
    rows = json.load(open(out_json))
    for row in rows:
        row['mix'] = name
        a, b = row.get('a'), row.get('b')
        if a in TITLES or b in TITLES:
            row['pair'] = f"{TITLES.get(a, a)} -> {TITLES.get(b, b)}"
    return rows


def load_david_log():
    rows = []
    p = PRO / 'log.jsonl'
    if not p.exists():
        return rows
    for line in open(p):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        david = r.get('david_answer') or r.get('david') or {}
        rating = david.get('rating') if 'rating' in david else david.get('rating_ours')
        clips = r.get('clips') or {}
        roles = {}
        if clips.get('A_is') and clips.get('B_is'):
            roles = dict(A=clips['A_is'], B=clips['B_is'])
        elif r.get('date') in CLIP_ROLE_OVERRIDE:
            o = CLIP_ROLE_OVERRIDE[r['date']]
            roles = dict(A=o['A'], B=o['B'], note=o.get('note'))
        rows.append(dict(
            date=r.get('date'), pair=r.get('pair'), pick_id=r.get('pick_id'),
            sources=r.get('sources'), clips=clips, roles=roles, david=david, rating=rating,
            long_verdict=r.get('david_long_verdict'), long_fix=r.get('david_long_fix_verdict'),
            rebuild=r.get('david_rebuild_verdict'),
        ))
    return rows


def score_mix_file(path, src_a, src_b, start_s=None, end_s=None, loc_a=None, loc_b=None,
                   scales=None, plot=None, title=None, extra=None):
    """Fit contributions of two sources into a mixed clip (daily A/B, RCA, etc.)."""
    if not path or not os.path.exists(path):
        return dict(diagnostic_only=True, error=f'missing {path}')
    if not src_a or not src_b or not os.path.exists(src_a) or not os.path.exists(src_b):
        return dict(diagnostic_only=True, error='missing sources', path=str(path))
    aligned, locs = _align_pro_sources(path, src_a, src_b, loc_a, loc_b)
    if aligned is None:
        return dict(diagnostic_only=True, error='align_failed', path=str(path),
                    loc_a=(locs or [None])[0], loc_b=(locs or [None, None])[1])
    dur = len(aligned[2]) / SS.SR
    # Prefer activity detection inside the clip; fall back to a centred window
    if start_s is None or end_s is None:
        window = 'activity'
    else:
        window = 'given'
    res = score_aligned(*aligned, start_s, end_s, scales=scales, already_gained=False,
                        plot=plot, title=title)
    res.update(path=str(path), method='fitted_contributions', window=window, duration_s=round(dur, 3))
    if extra:
        res.update(extra)
    return res


def yt_from_url(url):
    if not url:
        return None
    if 'v=' in url:
        return url.split('v=', 1)[1].split('&')[0]
    return url.rstrip('/').split('/')[-1]


def src_from_yt(yt):
    if not yt:
        return None
    for p in (PRO / 'lib' / f'{yt}.m4a', SRC2 / f'{yt}.m4a', SRC2 / f'{yt}.flac'):
        if p.exists():
            return str(p)
    return G.src_path(yt)


def write_report(doc, path=REPORT):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc)
    return path


def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    started = now_et()
    print(f'spectral_vs_pro start {started}', flush=True)

    # --- pro corpus ---
    clips = G.load_corpus_index()
    admitted = [c for c in clips if c.get('admitted')]
    print(f'  corpus {len(clips)} clips, {len(admitted)} admitted', flush=True)
    pro_rows = []
    for i, c in enumerate(clips):
        plot = FIG_DIR / f"pro_{c['id']}.png" if c['id'] in (
            'joe_syntax_hospital__08', 'hybrid_minds_ukf__08', 'joe_syntax_hospital__01',
            'hybrid_minds_ukf__11') or (c.get('admitted') and i < 2) else None
        print(f'  pro {i+1}/{len(clips)} {c["id"]} admitted={c.get("admitted")}', flush=True)
        try:
            pro_rows.append(score_pro_clip(c, plot=plot))
        except Exception as ex:
            pro_rows.append(dict(diagnostic_only=True, id=c['id'], pair=c['pair'],
                                 admitted=c.get('admitted'), error=f'{type(ex).__name__}: {ex}'[-240:]))
            traceback.print_exc()
        row = pro_rows[-1]
        print(f"    pcol={row.get('pcol')} pcty={row.get('pcty')} err={row.get('error')}", flush=True)

    ok_adm = [r for r in pro_rows if r.get('admitted') and 'error' not in r]
    scales = SS.scales_from_penalties([r['pcol'] for r in ok_adm], [r['pcty'] for r in ok_adm], target=SS.S_TARGET)
    scales.update(source=str(SCALES_JSON), n_pro=len(ok_adm),
                  note='s such that a penalty equal to the admitted-pro median maps to score 0.70. Diagnostic only.')
    # persist even if one scale is None, so later runs can load what we have
    json.dump(dict(s_col=scales.get('s_col'), s_cty=scales.get('s_cty'), target=SS.S_TARGET,
                   n_pro=len(ok_adm), note=scales['note'], at=now_et(),
                   pro_median_pcol=pct([r['pcol'] for r in ok_adm], 50),
                   pro_median_pcty=pct([r['pcty'] for r in ok_adm], 50),
                   pro_p95_pcol=pct([r['pcol'] for r in ok_adm], 95),
                   pro_p95_pcty=pct([r['pcty'] for r in ok_adm], 95),
                   diagnostic_only=True),
              open(SCALES_JSON, 'w'), indent=1)
    print(f'  scales {scales}', flush=True)
    pro_rows = [apply_scales(r, scales) if 'error' not in r else r for r in pro_rows]
    ok_adm = [r for r in pro_rows if r.get('admitted') and 'error' not in r]
    pro_dist = dict(admitted=summary_of(ok_adm),
                    all_ok=summary_of([r for r in pro_rows if 'error' not in r]),
                    n_clips=len(clips), n_admitted=len(admitted), n_scored=len(ok_adm),
                    n_failed=sum(1 for r in pro_rows if 'error' in r))

    # --- Mix 08 v2 (r11c) and long1h ---
    mix_dir = FIG_DIR / 'mixes'
    mix_dir.mkdir(exist_ok=True)
    r11c = score_mix_subprocess('mix08_r11c', 'nudge08_r9c.json',
                                FIG_DIR / 'mix08_r11c_spectral.json', plot_dir=mix_dir / 'r11c')
    long1h = score_mix_subprocess('mix08_long1h', 'nudge08_long.json',
                                  FIG_DIR / 'mix08_long1h_spectral.json', plot_dir=mix_dir / 'long1h')
    r11c = [apply_scales(r, scales) if 'error' not in r else r for r in r11c]
    long1h = [apply_scales(r, scales) if 'error' not in r else r for r in long1h]

    # --- known-bad cases ---
    shine = next((c for c in clips if c['id'] == 'joe_syntax_hospital__08'), None)
    known = {}
    if shine:
        sa, sb = G.src_path(shine['yt_a']), G.src_path(shine['yt_b'])
        cases = [
            ('pro_official', shine['pro_clip'], 'Joe Syntax official clip (pro)'),
            ('daily_ours_2of5', ROOT / 'deliver' / 'protrans' / 'daily_2026-11-11_A.mp3',
             'daily 2026-11-11 A = ours, the listener 2/5'),
            ('daily_pro', ROOT / 'deliver' / 'protrans' / 'daily_2026-11-11_B.mp3',
             'daily 2026-11-11 B = pro'),
            ('long_3p5', ROOT / 'deliver' / 'protrans' / 'rca_2026-11-11_long.mp3',
             'FADE=long LONG_SOLO=16, the listener 3.5/5'),
            ('long_fix_4plus', ROOT / 'deliver' / 'protrans' / 'rca_2026-11-11_long_fix.mp3',
             'LONG_SWAP=exit LONG_SOLO_STRUCT=1, the listener better than 4/5'),
            ('engine_rebuild', ROOT / 'deliver' / 'protrans' / 'rca_2026-11-11_engine.mp3',
             'engine rebuild, listener: pretty good, that will do it'),
        ]
        for key, path, title in cases:
            print(f'  known {key} {path}', flush=True)
            try:
                known[key] = score_mix_file(str(path), sa, sb, scales=scales,
                                            plot=FIG_DIR / f'shine_{key}.png', title=title,
                                            extra=dict(label=key, title=title, pair=shine['pair']))
            except Exception as ex:
                known[key] = dict(diagnostic_only=True, label=key, error=f'{type(ex).__name__}: {ex}'[-240:])
                traceback.print_exc()
            print(f"    pcol={known[key].get('pcol')} pcty={known[key].get('pcty')} err={known[key].get('error')}", flush=True)

    crash_path = next((p for p in CRASH_03_CANDIDATES if p.exists()), None)
    if crash_path:
        sa, sb = src_from_yt(CRASH_03_WINDOW['a']), src_from_yt(CRASH_03_WINDOW['b'])
        print(f'  crash 03-60 {crash_path}', flush=True)
        try:
            known['deeper_just_hold_on'] = score_mix_file(
                str(crash_path), sa, sb, start_s=CRASH_03_WINDOW['start_s'], end_s=CRASH_03_WINDOW['end_s'],
                scales=scales, plot=FIG_DIR / 'deeper_just_hold_on.png',
                title=CRASH_03_WINDOW['pair'], extra=dict(label='deeper_just_hold_on', **CRASH_03_WINDOW))
        except Exception as ex:
            known['deeper_just_hold_on'] = dict(diagnostic_only=True, error=f'{type(ex).__name__}: {ex}'[-240:],
                                                **CRASH_03_WINDOW)
    else:
        known['deeper_just_hold_on'] = dict(
            diagnostic_only=True, skipped=True,
            reason='mix 03-60 v1 audio is gone (dj-mix-03-60.mp3 and pro_sets/wav/dj-mix-03-60.wav are not on disk); '
                   'the stem wav for the 124 BPM original Just Hold On is also gone. Cannot rescore the actual car-crash blend. '
                   'Historical record: the listener rated Deeper -> Just Hold On (~13:00-14:30) horrible; the failure was a fake 174 grid on a 124 BPM UK-breaks track (R1 rhythm clash), which this spectral scorer is not designed to catch.',
            **CRASH_03_WINDOW)

    # --- the listener daily A/B agreement ---
    log_rows = load_david_log()
    agreement = []
    for rec in log_rows:
        roles, clips = rec.get('roles') or {}, rec.get('clips') or {}
        pid = rec.get('pick_id')
        srcs = rec.get('sources') or {}
        yt_a, yt_b = yt_from_url((srcs or {}).get('a')), yt_from_url((srcs or {}).get('b'))
        if (not yt_a or not yt_b) and pid:
            meta_p = next((PRO / 'clips').glob(f'*/{pid}/meta.json'), None)
            if meta_p and meta_p.exists():
                m = json.load(open(meta_p))
                yt_a = yt_a or m['a'].get('yt')
                yt_b = yt_b or m['b'].get('yt')
        sa, sb = src_from_yt(yt_a), src_from_yt(yt_b)
        entry = dict(date=rec['date'], pair=rec['pair'], pick_id=pid, rating=rec.get('rating'),
                     david=rec.get('david'), roles=roles, ours=None, pro=None)
        for letter in ('A', 'B'):
            path = clips.get(letter)
            role = roles.get(letter)
            if not path:
                continue
            print(f"  daily {rec['date']} {letter}={role} {path}", flush=True)
            try:
                sc = score_mix_file(path, sa, sb, scales=scales,
                                    plot=FIG_DIR / f"daily_{rec['date']}_{letter}_{role or 'unk'}.png",
                                    title=f"{rec['date']} {letter}={role}: {rec['pair']}",
                                    extra=dict(letter=letter, role=role, date=rec['date']))
            except Exception as ex:
                sc = dict(diagnostic_only=True, error=f'{type(ex).__name__}: {ex}'[-240:])
                traceback.print_exc()
            if role == 'ours':
                entry['ours'] = sc
            elif role == 'pro':
                entry['pro'] = sc
            else:
                entry[f'clip_{letter}'] = sc
        # extra Shine In long variants already in `known`; attach ratings
        entry['long_verdict'] = rec.get('long_verdict')
        entry['long_fix'] = rec.get('long_fix')
        agreement.append(entry)
        o, p = (entry.get('ours') or {}).get('pcol'), (entry.get('pro') or {}).get('pcol')
        print(f"    ours pcol={o} pro pcol={p} rating={entry['rating']}", flush=True)

    # --- separation / verdict ---
    shine_ours = known.get('daily_ours_2of5') or {}
    shine_pro = known.get('daily_pro') or known.get('pro_official') or {}
    shine_fix = known.get('long_fix_4plus') or {}
    shine_long = known.get('long_3p5') or {}
    bad_pcol = [r['pcol'] for r in (shine_ours, shine_long) if r.get('pcol') is not None]
    good_pcol = [r['pcol'] for r in ok_adm]
    # rated dailies
    rated = [e for e in agreement if e.get('rating') is not None and e.get('ours') and e['ours'].get('pcol') is not None]
    # does ours-vs-pro delta go the right way on the 2/5 vs 4/5 days?
    def flag_vs_pro(row, metric='pcol', p95=None):
        if row.get(metric) is None or not p95:
            return None
        return bool(row[metric] > p95) if metric in ('pcol', 'pcty', 'banger_clash_rate') else bool(row[metric] < p95)

    p95_pcol = pro_dist['admitted']['pcol']['p95']
    p5_scol = pro_dist['admitted']['Scol']['p5']
    sep = dict(
        pro_admitted=pro_dist['admitted'],
        r11c=summary_of(r11c),
        long1h=summary_of(long1h),
        shine_in=dict(
            ours_2of5={k: shine_ours.get(k) for k in ('pcol', 'pcty', 'Scol', 'Scty', 'banger_clash_rate', 'error')},
            daily_pro={k: shine_pro.get(k) for k in ('pcol', 'pcty', 'Scol', 'Scty', 'banger_clash_rate', 'error')},
            long_3p5={k: shine_long.get(k) for k in ('pcol', 'pcty', 'Scol', 'Scty', 'banger_clash_rate', 'error')},
            long_fix_4plus={k: shine_fix.get(k) for k in ('pcol', 'pcty', 'Scol', 'Scty', 'banger_clash_rate', 'error')},
            ours_worse_collision_than_pro=(None if shine_ours.get('pcol') is None or shine_pro.get('pcol') is None
                                           else bool(shine_ours['pcol'] > shine_pro['pcol'])),
            ours_above_pro_p95=(None if shine_ours.get('pcol') is None or p95_pcol is None
                                else bool(shine_ours['pcol'] > p95_pcol)),
            fix_improved_on_ours=(None if shine_ours.get('pcol') is None or shine_fix.get('pcol') is None
                                  else bool(shine_fix['pcol'] < shine_ours['pcol'])),
        ),
        r11c_n_above_pro_p95=sum(1 for r in r11c if r.get('pcol') is not None and p95_pcol is not None and r['pcol'] > p95_pcol),
        long1h_n_above_pro_p95=sum(1 for r in long1h if r.get('pcol') is not None and p95_pcol is not None and r['pcol'] > p95_pcol),
        r11c_n=sum(1 for r in r11c if 'error' not in r),
        long1h_n=sum(1 for r in long1h if 'error' not in r),
    )
    # Spearmans on the tiny the listener sample (ours pcol vs rating; lower rating should mean higher pcol)
    if len(rated) >= 3:
        try:
            from scipy.stats import spearmanr
            xs = [e['ours']['pcol'] for e in rated]
            ys = [float(e['rating']) for e in rated]
            rho, pv = spearmanr(xs, ys)
            sep['david_spearman_ours_pcol_vs_rating'] = dict(rho=round(float(rho), 3), p=round(float(pv), 3), n=len(rated),
                                                              note='negative rho is agreement (worse collision, lower rating)')
            xs2 = [e['ours']['Scty'] for e in rated if e['ours'].get('Scty') is not None]
            ys2 = [float(e['rating']) for e in rated if e['ours'].get('Scty') is not None]
            if len(xs2) >= 3:
                rho2, pv2 = spearmanr(xs2, ys2)
                sep['david_spearman_ours_Scty_vs_rating'] = dict(rho=round(float(rho2), 3), p=round(float(pv2), 3), n=len(xs2),
                                                                  note='positive rho is agreement (higher continuity, higher rating)')
        except Exception as ex:
            sep['david_spearman_error'] = str(ex)[-160:]

    # Verdict: worth a later gate?
    reasons = []
    shine_sep = sep['shine_in'].get('ours_worse_collision_than_pro')
    shine_tail = sep['shine_in'].get('ours_above_pro_p95')
    fix_ok = sep['shine_in'].get('fix_improved_on_ours')
    if shine_sep and shine_tail:
        reasons.append('the 2/5 Shine In ours sits above the pro p95 collision penalty and worse than the matching pro clip')
    elif shine_sep:
        reasons.append('the 2/5 Shine In ours is more collided than the matching pro, but not above the pro p95')
    elif shine_ours.get('pcol') is not None:
        reasons.append('the 2/5 Shine In ours is not clearly more collided than the matching pro')
    if fix_ok:
        reasons.append('the approved long-blend fix lowered the collision penalty vs the 2/5 ours')
    elif shine_fix.get('pcol') is not None:
        reasons.append('the approved long-blend fix did not lower the collision penalty vs the 2/5 ours')
    false_alarm_r11c = sep['r11c_n_above_pro_p95']
    false_alarm_long = sep['long1h_n_above_pro_p95']
    reasons.append(f"{false_alarm_r11c}/{sep['r11c_n']} r11c blends and {false_alarm_long}/{sep['long1h_n']} long1h blends sit above the pro p95 collision penalty")
    promote = bool(shine_sep and (shine_tail or fix_ok) and (sep['r11c_n'] and false_alarm_r11c / max(sep['r11c_n'], 1) <= 0.35))
    verdict = dict(
        promote_to_gate_later=promote,
        stance='promising diagnostic; not a gate yet' if promote else 'keep as a diagnostic only; too early to gate',
        reasons=reasons,
        note='A later gate would be calibrated to the pro p95 (or a looser percentile) of pcol, never hand-set, and only after more the listener-rated blends confirm the separation. Continuity is reported but should not gate on this sample alone.',
    )

    out = dict(
        diagnostic_only=True,
        at=now_et(), started=started,
        scales=dict(s_col=scales.get('s_col'), s_cty=scales.get('s_cty'), target=SS.S_TARGET,
                    n_pro=len(ok_adm), note=scales.get('note')),
        pro=dict(distribution=pro_dist, rows=[{k: r[k] for k in r if k not in ('collision_bar', 'continuity_bar')} for r in pro_rows]),
        mix08_r11c=dict(distribution=summary_of(r11c),
                        rows=[{k: r[k] for k in r if k not in ('collision_bar', 'continuity_bar')} for r in r11c]),
        mix08_long1h=dict(distribution=summary_of(long1h),
                          rows=[{k: r[k] for k in r if k not in ('collision_bar', 'continuity_bar')} for r in long1h]),
        known=known,
        david_agreement=agreement,
        separation=sep,
        verdict=verdict,
        files=dict(results=str(OUT_JSON), scales=str(SCALES_JSON), report=str(REPORT), figures=str(FIG_DIR)),
    )
    json.dump(out, open(OUT_JSON, 'w'), indent=1, default=float)
    write_report(render_report(out))
    print(json.dumps(dict(verdict=verdict, scales=out['scales'],
                          pro_pcol=pro_dist['admitted']['pcol'],
                          shine=sep['shine_in']), indent=2, default=float), flush=True)
    print(f'wrote {OUT_JSON} and {REPORT}', flush=True)
    return 0


def render_report(out):
    sc, sep, v = out['scales'], out['separation'], out['verdict']
    pro = sep['pro_admitted']
    def fmt(d, k):
        x = (d or {}).get(k) or {}
        if not x or not x.get('n'):
            return 'n=0'
        return (f"n={x['n']}  median={x['median']}  p95={x['p95']}  p5={x['p5']}  "
                f"min={x['min']}  max={x['max']}")

    lines = []
    lines.append('# Spectral collision / continuity scorer (2026-11-12)')
    lines.append('')
    lines.append('Diagnostic only. Not a failing test, not a build gate, and `protrans/rules.json` was not changed.')
    lines.append('')
    lines.append('Implements Daito Manabe, *On the Measurability of DJ Mix Quality* (March 2026), §§5.2–5.3: contribution-weighted spectral collision (penalise both decks occupying the same low / low-mid band) and spectral continuity (reward a tone that glides from old to new rather than lurching). Companion rate: Banger Lab `clash()` over 6 bands (20–80, 80–250, 250–800, 800–2500, 2500–7000, 7000–20000 Hz). Our mixes are scored from the actual rendered deck signals (gain and bass/high lanes already applied). Pro clips and daily A/B files are scored by fitting non-negative per-band contributions of the two aligned sources into the master (Manabe eq. 5).')
    lines.append('')
    lines.append(f"Calibrated at {out['at']} America/New_York on {sc['n_pro']} admitted pro transitions. Score scales map a penalty equal to the pro median to 0.70: `s_col={sc.get('s_col')}`  `s_cty={sc.get('s_cty')}`. Higher Scol / Scty is better; higher pcol / pcty is worse.")
    lines.append('')
    lines.append('## Pro distributions (admitted)')
    lines.append('')
    lines.append(f"- collision penalty pcol: {fmt(pro, 'pcol')}")
    lines.append(f"- continuity penalty pcty: {fmt(pro, 'pcty')}")
    lines.append(f"- Scol: {fmt(pro, 'Scol')}")
    lines.append(f"- Scty: {fmt(pro, 'Scty')}")
    lines.append(f"- Banger clash rate: {fmt(pro, 'banger_clash_rate')}")
    lines.append('')
    lines.append('## Mix 08 v2 (r11c) and long1h')
    lines.append('')
    lines.append(f"- r11c pcol: {fmt(sep, 'r11c') and fmt(out['mix08_r11c']['distribution'], 'pcol')}")
    lines.append(f"- r11c Scol: {fmt(out['mix08_r11c']['distribution'], 'Scol')}")
    lines.append(f"- long1h pcol: {fmt(out['mix08_long1h']['distribution'], 'pcol')}")
    lines.append(f"- long1h Scol: {fmt(out['mix08_long1h']['distribution'], 'Scol')}")
    lines.append(f"- blends above the pro p95 collision penalty: r11c {sep['r11c_n_above_pro_p95']}/{sep['r11c_n']}, long1h {sep['long1h_n_above_pro_p95']}/{sep['long1h_n']}")
    lines.append('')
    lines.append('## Known-bad cases')
    lines.append('')
    si = sep['shine_in']
    lines.append('### Shine In -> Dusk To Dawn (2026-11-11, equal-level clash, the listener 2/5 on the daily ours)')
    lines.append('')
    for label, rec in si.items():
        if isinstance(rec, dict) and ('pcol' in rec or 'error' in rec):
            lines.append(f"- {label}: pcol={rec.get('pcol')}  pcty={rec.get('pcty')}  Scol={rec.get('Scol')}  Scty={rec.get('Scty')}  banger={rec.get('banger_clash_rate')}  {rec.get('error') or ''}")
    lines.append(f"- ours worse collision than the matching pro: {si.get('ours_worse_collision_than_pro')}")
    lines.append(f"- ours above the pro p95: {si.get('ours_above_pro_p95')}")
    lines.append(f"- long-blend fix improved on the 2/5 ours: {si.get('fix_improved_on_ours')}")
    lines.append('')
    crash = out['known'].get('deeper_just_hold_on') or {}
    lines.append('### Deeper -> Just Hold On (mix 03-60 v1, listener: horrible)')
    lines.append('')
    if crash.get('skipped'):
        lines.append(crash.get('reason'))
    else:
        lines.append(f"- pcol={crash.get('pcol')}  pcty={crash.get('pcty')}  Scol={crash.get('Scol')}  Scty={crash.get('Scty')}  {crash.get('error') or ''}")
    lines.append('')
    lines.append('## Agreement with the listener (protrans/log.jsonl)')
    lines.append('')
    for e in out['david_agreement']:
        o, p = e.get('ours') or {}, e.get('pro') or {}
        lines.append(f"- {e.get('date')}  {e.get('pair')}: the listener rating={e.get('rating')}  ours pcol={o.get('pcol')} Scol={o.get('Scol')} Scty={o.get('Scty')}  pro pcol={p.get('pcol')} Scol={p.get('Scol')} Scty={p.get('Scty')}")
    if sep.get('david_spearman_ours_pcol_vs_rating'):
        lines.append(f"- Spearman (ours pcol vs rating): {sep['david_spearman_ours_pcol_vs_rating']}")
    if sep.get('david_spearman_ours_Scty_vs_rating'):
        lines.append(f"- Spearman (ours Scty vs rating): {sep['david_spearman_ours_Scty_vs_rating']}")
    lines.append('')
    lines.append('## Verdict')
    lines.append('')
    lines.append(f"**{v['stance']}**  (promote later: {v['promote_to_gate_later']})")
    for r in v['reasons']:
        lines.append(f"- {r}")
    lines.append('')
    lines.append(v['note'])
    lines.append('')
    lines.append('## Files')
    lines.append('')
    lines.append('- `src2/spectral_score.py` — scorer')
    lines.append('- `src/tests/test_spectral_score.py` — unit tests (synthetic signals only)')
    lines.append('- `src/calib/spectral_vs_pro.py` — this calibration')
    lines.append('- `src/calib/spectral_scales.json` — calibrated scales')
    lines.append('- `src/calib/spectral_vs_pro_results.json` — full numbers')
    lines.append('- `src2/blend_diag.py` — extra diagnostic lane (generate-only)')
    lines.append(f"- figures under `{out['files']['figures']}`")
    lines.append('')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    try:
        sys.exit(main() or 0)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
