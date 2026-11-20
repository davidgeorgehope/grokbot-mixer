import sys, json, numpy as np
sys.path.insert(0, '/workspace/mixes/protrans/rca_beats'); import gridcheck as G
for yid in sys.argv[1:]:
    rows = G.track(yid); json.dump(rows, open(f'/workspace/mixes/protrans/rca_beats/grid_{yid}.json', 'w'))
    sec = json.load(open(f'st/{yid}.sections.json'))
    good = [(r['bar'], r['snare_ms']) for r in rows if r['rs'] >= 0.3 and r['snare_ms'] is not None]
    v = np.array([p for _, p in good]); b = np.array([k for k, _ in good])
    line = f"{yid} n_bars {len(rows)} confident {len(good)} median {np.median(v):.1f} ms  IQR {np.percentile(v,25):.1f}..{np.percentile(v,75):.1f}"
    segs = []
    for lo in range(0, len(rows), 16):
        m = v[(b >= lo) & (b < lo + 16)]
        segs.append(f"{lo}:{np.median(m):.0f}" if len(m) >= 3 else f"{lo}:--")
    print(line, '| drops', sec.get('drops')); print('   per16', ' '.join(segs))
