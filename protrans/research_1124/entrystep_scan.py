"""Entry step of the incoming at its cue: level (all band, and drums) of the 4 bars from the cue minus the 4 bars before it.
Pros vs our default drop1-16 cue vs drop1-32, on corpus_v2 pairs with a src2/st grid. Read-only."""
import json, glob, os, numpy as np
ST = '/workspace/mixes/src2/st'
def step(arr, q):
    if q < 4 or q + 4 > len(arr): return None
    return float(np.median(arr[q:q + 4]) - np.median(arr[q - 4:q]))
R = []
for fp in sorted(glob.glob('/workspace/mixes/protrans/corpus_v2/features/*.json')):
    f = json.load(open(fp)); cue = (f.get('cue') or {}).get('incoming_bar'); yt = (f.get('track_b') or {}).get('yt')
    if cue is None or not yt or not os.path.exists(f'{ST}/{yt}.json') or not os.path.exists(f'{ST}/{yt}.sections.json'): continue
    g = json.load(open(f'{ST}/{yt}.json'))['bar']; d1 = json.load(open(f'{ST}/{yt}.sections.json'))['drop1']
    A = np.array(g['all'], float); D = np.array(g['drums'], float)
    q = int(round(cue))
    R.append(dict(id=f['id'], pro_all=step(A, q), pro_dr=step(D, q), d16_all=step(A, d1 - 16), d16_dr=step(D, d1 - 16),
                  d32_all=step(A, d1 - 32), d32_dr=step(D, d1 - 32), pro_in_intro=q < d1 - 4))
def stat(k, rs):
    v = [r[k] for r in rs if r[k] is not None]; v = np.array(v)
    return dict(n=len(v), med=round(float(np.median(v)), 2), p_ge3=round(float((v >= 3).mean()), 3), p_ge6=round(float((v >= 6).mean()), 3)) if len(v) else None
intro = [r for r in R if r['pro_in_intro']]
out = {k: stat(k, intro) for k in ('pro_all', 'd16_all', 'd32_all', 'pro_dr', 'd16_dr', 'd32_dr')}
print('pairs where the pro cued inside the intro (cue < drop1-4):', len(intro)); print(json.dumps(out, indent=1))
json.dump(dict(summary=out, rows=R), open('/workspace/mixes/protrans/research_1124/entrystep_scan.json', 'w'), indent=1)
g = json.load(open(f'{ST}/SqzxwPEa-DI.json'))['bar']; print('Meteorites cue48 all', step(np.array(g['all']), 48), 'drums', step(np.array(g['drums']), 48), 'cue32', step(np.array(g['all']), 32), step(np.array(g['drums']), 32))
