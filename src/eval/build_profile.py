#!/usr/bin/env python3
"""Aggregate per-transition JSON from pro sets into 'pro ranges' (eval/pro_profile.json)."""
import json, sys, glob, numpy as np, collections
PRO = ['wilkinson_boomtown2026', 'dimension_allstars360', 'wilkinson_oldguard', 'hospital_podcast393']
METRICS = ['overlap_bars', 'swap_len_bars', 'swap_pos_in_overlap', 'swap_to_drop_bars', 'low_dip_db', 'energy_delta_db',
           'overlap_level_db', 'beat_clarity_ratio', 'camelot_dist', 'vocal_active_frac_overlap', 'vocal_chroma_entropy']
def stats(v):
    v = np.array([x for x in v if x is not None], float)
    if not len(v): return None
    p = np.percentile(v, [10, 25, 50, 75, 90])
    return dict(n=int(len(v)), mean=round(float(v.mean()), 3), p10=round(p[0], 3), p25=round(p[1], 3), median=round(p[2], 3), p75=round(p[3], 3), p90=round(p[4], 3))
def main(d='/workspace/mixes/eval/sets', out='/workspace/mixes/eval/pro_profile.json'):
    sets = {n: json.load(open(f'{d}/{n}.json')) for n in PRO if glob.glob(f'{d}/{n}.json')}
    allt = [t | {'set': n} for n, s in sets.items() for t in s['transitions']]
    prof = dict(sources=PRO, sets_used=list(sets), n_transitions=len(allt), metrics={m: stats([t.get(m) for t in allt]) for m in METRICS})
    tc = collections.Counter(tag for t in allt for tag in t['techniques'])
    prof['technique_freq'] = {k: round(v / len(allt), 3) for k, v in tc.most_common()}
    pc = collections.Counter(t['techniques'][0] for t in allt)
    prof['primary_technique_freq'] = {k: round(v / len(allt), 3) for k, v in pc.most_common()}
    runs = []
    for s_ in sets.values():
        pr = [t['techniques'][0] for t in s_['transitions']]; run = best = 1
        for a, b in zip(pr, pr[1:]): run = run + 1 if a == b else 1; best = max(best, run)
        if pr: runs.append(best)
    prof['max_same_technique_run_median'] = float(np.median(runs)) if runs else None
    prof['overlap_bars_hist_8bar_bins'] = {f"{b*8}-{b*8+7}": int(sum(1 for t in allt if b*8 <= t['overlap_bars'] < b*8+8)) for b in range(8)}
    mod8 = [t['swap_bar_mod8'] for t in allt if t.get('swap_bar_mod8') is not None]
    prof['swap_on_8bar_grid_pm1'] = round(float(np.mean([m in (7, 0, 1) for m in mod8])), 3) if mod8 else None
    prof['per_set'] = {n: dict(detection=s['detection'], bpm=s['bpm'], duration_min=round(s['duration_sec']/60, 1), n_transitions=s['n_transitions'],
                               median_track_time_sec=s['median_track_time_sec'],
                               median_overlap_bars=(float(np.median([t['overlap_bars'] for t in s['transitions']])) if s['transitions'] else None),
                               energy_arc_range_db=round(float(np.ptp(s['energy_arc_db_per_min'])), 1)) for n, s in sets.items()}
    prof['set_level'] = dict(track_time_sec=stats([s['median_track_time_sec'] for s in sets.values()]))
    prof['caveats'] = ["Track boundaries for Wilkinson Boomtown and Hospital 393 are anchored to published YouTube chapter timestamps; Dimension and Old Guard are blind-detected (higher false-positive/miss risk).",
                       "Vocal metrics include MC/hype vocals in live sets (Wilkinson Boomtown has MC AD-APT).",
                       "Overlap length validated on dj-mix-01 (truth: 16 bars every transition) - see eval/validation.json for measured error."]
    json.dump(prof, open(out, 'w'), indent=1); return prof
if __name__ == '__main__':
    p = main(*sys.argv[1:]); print(json.dumps({k: p[k] for k in ['n_transitions', 'technique_freq', 'swap_on_8bar_grid_pm1']}, indent=1))
