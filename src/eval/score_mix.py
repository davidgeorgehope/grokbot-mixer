#!/usr/bin/env python3
"""Score our mixes against eval/pro_profile.json.

Each transition metric is scored 0-1 by where it falls in the pro distribution:
  inside p25-p75 -> 1.0, inside p10-p90 -> 0.75, outside -> decays with distance (in IQR units).
One-sided metrics (bad only in one direction) are only penalised on that side.
Hard faults (beat-clarity collapse, vocal overlap far above pros) are flagged in plain language.
Usage: score_mix.py eval/sets/dj-mix-01.json [more.json ...]  -> eval/scores/<name>.json + printed summary
"""
import json, sys, os, numpy as np
PROF = '/workspace/mixes/eval/pro_profile.json'
# metric: (side, weight, label)  side: both | high_bad | low_bad
SPEC = {'overlap_bars': ('both', 2.0, 'blend length'),
        'swap_len_bars': ('high_bad', 1.0, 'bass-swap sharpness'),
        'beat_clarity_ratio': ('low_bad', 2.5, 'beat clarity in the blend'),
        'low_dip_db': ('both', 1.0, 'low-end dip at the swap'),
        'energy_delta_db': ('both', 1.5, 'energy jump/drop across the transition'),
        'camelot_dist': ('high_bad', 1.0, 'key distance'),
        'vocal_active_frac_overlap': ('high_bad', 1.5, 'vocals during the overlap')}
def metric_score(x, s, side):
    if x is None or s is None: return None
    iqr = max(s['p75'] - s['p25'], 1e-6)
    lo_ok = side == 'high_bad' or x >= s['p25']; hi_ok = side == 'low_bad' or x <= s['p75']
    if lo_ok and hi_ok: return 1.0
    lo_ok90 = side == 'high_bad' or x >= s['p10']; hi_ok90 = side == 'low_bad' or x <= s['p90']
    if lo_ok90 and hi_ok90: return 0.75
    d = (s['p10'] - x) if x < s['p10'] else (x - s['p90'])
    return round(max(0.0, 0.75 - 0.5 * d / iqr), 3)
def note(m, x, s, side):
    if m == 'beat_clarity_ratio' and x < s['p10']: return f"beats get muddy in the blend (clarity {x:.2f}x of outside vs pro p10 {s['p10']:.2f}) - likely grid slip or two kick patterns fighting"
    if m == 'overlap_bars':
        if x < s['p10']: return f"blend is short ({x} bars; pros mostly {s['p25']:.0f}-{s['p75']:.0f})"
        if x > s['p90']: return f"blend is very long ({x} bars; pros mostly {s['p25']:.0f}-{s['p75']:.0f})"
    if m == 'energy_delta_db' and abs(x) > max(abs(s['p10']), abs(s['p90'])): return f"energy {'drops' if x < 0 else 'jumps'} {abs(x):.1f} dB across the change (pros p10-p90 {s['p10']:.1f}..{s['p90']:.1f}) - the 'weirdly dropped' feeling"
    if m == 'vocal_active_frac_overlap' and x > s['p90']: return f"vocals active in {x:.0%} of the overlap (pros p90 {s['p90']:.0%}) - clash risk"
    if m == 'camelot_dist' and x > s['p90']: return f"key jump of {x} Camelot steps (pros p90 {s['p90']:.0f})"
    if m == 'low_dip_db' and x < s['p10']: return f"low end dips {x:.1f} dB at the swap (pros p10 {s['p10']:.1f}) - a hole in the bass"
    if m == 'swap_len_bars' and x > s['p90']: return f"bass handover smeared over ~{x} bars (pros p90 {s['p90']:.0f})"
    return None
def score(path, prof):
    d = json.load(open(path)); P = prof['metrics']; rows = []
    for i, t in enumerate(d['transitions']):
        parts, notes = {}, []
        for m, (side, w, _) in SPEC.items():
            sc = metric_score(t.get(m), P.get(m), side)
            if sc is not None:
                parts[m] = sc
                n = note(m, t[m], P[m], side)
                if n: notes.append(n)
        ws = sum(SPEC[m][1] for m in parts); tot = sum(parts[m] * SPEC[m][1] for m in parts) / ws if ws else None
        mm = int(t['time_sec'] // 60), int(t['time_sec'] % 60)
        rows.append(dict(idx=i + 1, at=f"{mm[0]}:{mm[1]:02d}", time_sec=t['time_sec'], score=round(100 * tot, 1), parts=parts,
                         techniques=t['techniques'], notes=notes or ['inside pro ranges']))
    tr = [r['score'] for r in rows]
    # set-level: track time + technique variety vs pros
    pro_tt = prof['set_level']['track_time_sec']; tt = d['median_track_time_sec']
    set_notes = []
    if pro_tt and tt:
        set_notes.append(f"median time between transitions {tt:.0f}s vs pro sets {pro_tt['min'] if 'min' in pro_tt else pro_tt['p10']:.0f}-{pro_tt['p90']:.0f}s")
    labels = {tag.split('_')[0] if tag[0].isdigit() else tag for r in rows for tag in r['techniques']}
    set_notes.append(f"technique labels used: {sorted(labels)}")
    # ---- transition variety (listener: don't repeat one technique; loops only when a track lacks runway)
    prim = [r['techniques'][0] for r in rows]
    def primary_dist(ts): 
        import collections; c = collections.Counter(ts); return {k: v / len(ts) for k, v in c.items()}
    md = primary_dist(prim) if prim else {}
    pro_prim = prof.get('primary_technique_freq', {})
    pro_max = max(pro_prim.values()) if pro_prim else 0.6
    top = max(md.items(), key=lambda kv: kv[1]) if md else (None, 0)
    run = best = 1
    for a, b in zip(prim, prim[1:]): run = run + 1 if a == b else 1; best = max(best, run)
    pro_run = prof.get('max_same_technique_run_median', 3)
    # L1 distance between our technique mix and the pros'
    keys = set(md) | set(pro_prim); l1 = sum(abs(md.get(k, 0) - pro_prim.get(k, 0)) for k in keys)
    variety = 100 * max(0.0, 1 - 0.5 * l1 - max(0, top[1] - pro_max) - 0.1 * max(0, best - pro_run))
    loops = None; meta = d.get('declared_transitions')
    if meta:
        loops = sum(1 for t in meta if any('loop' in n for n in t.get('notes', [])) or 'loop' in t.get('tech', ''))
        if loops / len(meta) > 0.25:
            variety -= 10 * (loops / len(meta) - 0.25) * 4
            set_notes.append(f"loop extensions used in {loops}/{len(meta)} transitions - keep them for tracks that lack runway")
    variety = round(max(0.0, variety), 1)
    set_notes.append(f"variety {variety}: top technique '{top[0]}' = {top[1]:.0%} of transitions (pro max share {pro_max:.0%}); longest same-technique run {best} (pro median {pro_run})")
    worst = sorted(rows, key=lambda r: r['score'])[:3]
    overall = round(float(np.mean(tr)) * 0.6 + float(np.min(tr)) * 0.25 + variety * 0.15, 1) if tr else None  # weakest link + variety matter
    out = dict(mix=d['name'], overall=overall, variety=variety, loop_extensions=loops, primary_techniques=prim, mean_transition=round(float(np.mean(tr)), 1) if tr else None,
               min_transition=min(tr) if tr else None, n_transitions=len(rows), set_notes=set_notes,
               weakest=[f"{r['at']}: {'; '.join(r['notes'])}" for r in worst], transitions=rows)
    os.makedirs('/workspace/mixes/eval/scores', exist_ok=True)
    json.dump(out, open(f"/workspace/mixes/eval/scores/{d['name']}.json", 'w'), indent=1)
    return out
if __name__ == '__main__':
    prof = json.load(open(PROF))
    for p in sys.argv[1:]:
        o = score(p, prof)
        print(f"\n== {o['mix']}: overall {o['overall']} (mean {o['mean_transition']}, weakest {o['min_transition']})")
        for r in o['transitions']: print(f"  {r['at']:>6} {r['score']:5.1f}  {','.join(r['techniques'])}  | {' / '.join(r['notes'])}")
        print('  variety:', o['variety'])
        for n in o['set_notes']: print('  *', n)
