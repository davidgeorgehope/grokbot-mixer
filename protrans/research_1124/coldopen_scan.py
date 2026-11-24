"""2026-11-24 midnight research: do pros cold-open the incoming on a groove change (start of a half-time / slowdown
section), and how often does our default outro-over-intro cue (drop1 - X) do it? Read-only on corpus_v2 features
and src2/st caches (slowdown profiles computed only where cached or the st wav exists)."""
import json, glob, os, sys, numpy as np
sys.path.insert(0, '/workspace/mixes/protrans/replica/halftime'); sys.path.insert(0, '/workspace/mixes/src2')
import slowdown as SD
ST = '/workspace/mixes/src2/st'
def events(yt):
    """groove-change starts: slowdown sections starting at bar >= 8 whose previous 4 bars had a backbeat (not just intro)."""
    P = SD.profile(yt) if (os.path.exists(f'{ST}/{yt}.slowdown.json') or os.path.exists(f'{ST}/{yt}.wav')) else None
    if not P: return None
    return [s for s, e in P['sections'] if s >= 8]
def cold(cue, evs, lo=-1, hi=4):
    return any(lo <= s - cue <= hi for s in evs)
rows = []
for fp in sorted(glob.glob('/workspace/mixes/protrans/corpus_v2/features/*.json')):
    f = json.load(open(fp)); cue = (f.get('cue') or {}).get('incoming_bar'); tb = f.get('track_b') or {}; yt = tb.get('yt')
    if cue is None or not yt or not os.path.exists(f'{ST}/{yt}.json'): continue
    try: evs = events(yt)
    except Exception as ex: continue
    if evs is None: continue
    try: d1 = json.load(open(f'{ST}/{yt}.sections.json'))['drop1']
    except Exception: continue
    ov = f.get('overlap_bars') or 16
    ib = int(round(cue))
    rows.append(dict(id=f['id'], dj=f['dj'], yt=yt, pro_cue=round(cue, 1), d1=d1, evs=evs, ov=ov,
                     pro_cold=cold(ib, evs), def16_cold=cold(d1 - 16, evs), def32_cold=cold(d1 - 32, evs),
                     pro_lead=[s - ib for s in evs if 4 < s - ib <= max(ov, 8)],
                     ))
n = len(rows); ev = [r for r in rows if r['evs']]
def rate(k, rs): return round(sum(r[k] for r in rs) / max(1, len(rs)), 3)
# base rate: random 4-bar-aligned cue in [0, d1] cold-open probability (chance level for pros)
import random; random.seed(1)
def chance(rs):
    t = 0; c = 0
    for r in rs:
        for q in range(0, max(1, r['d1']) + 1, 4): t += 1; c += cold(q, r['evs'])
    return round(c / max(1, t), 3)
out = dict(n_pairs=n, n_with_groove_change=len(ev), pro_cold=rate('pro_cold', rows), def16_cold=rate('def16_cold', rows),
           def32_cold=rate('def32_cold', rows), chance_cold_4bar_grid=chance(rows),
           among_def16_cold=dict(n=sum(r['def16_cold'] for r in rows), pro_cold=rate('pro_cold', [r for r in rows if r['def16_cold']]),
                                 pro_event_inside_overlap=round(sum(bool(r['pro_lead']) for r in rows if r['def16_cold']) / max(1, sum(r['def16_cold'] for r in rows)), 3),
                                 pro_cue_minus_d1=sorted(round(r['pro_cue'] - r['d1'], 1) for r in rows if r['def16_cold'])))
json.dump(dict(summary=out, rows=rows), open('/workspace/mixes/protrans/research_1124/coldopen_scan.json', 'w'), indent=1)
print(json.dumps(out, indent=1))
