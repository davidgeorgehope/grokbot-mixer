"""RCA 2026-11-20: same measurement on every recent daily pick, BLEND_LOCK on (current rules) vs off.
true offset = median over overlap bars where BOTH decks have a clear backbeat (snare-band beat-phase r >= RMIN) of (A phase - B phase);
xcorr = blend_diag.bar_offsets median (the number on the daily PNG)."""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import measure, deckphase, cleanup
RMIN = 0.3
PICKS = [('11-13', 'hybrid_minds_ukf__12'), ('11-14', 'hybrid_minds_ukf__19'), ('11-15', 'hybrid_minds_ukf__25'), ('11-16', 'hybrid_minds_ukf__45'),
         ('11-17', 'joe_syntax_hospital__11'), ('11-18', 'hybrid_minds_ukf__13'), ('11-19/20 spex', 'joe_syntax_hospital__12'), ('11-20', 'hybrid_minds_ukf__09')]
def stats(o):
    ov = set(o['overlap']); rows = deckphase_rows = o['dp']['rows']
    d = []
    for r in rows:
        if r['bar'] in ov and r['snA'] is not None and r['snB'] is not None and r['rsA'] >= RMIN and r['rsB'] >= RMIN:
            d.append((r['snA'] - r['snB'] + 172.4) % 344.8 - 172.4)
    xc = [r['xcorr'] for r in o['rows'] if r['xcorr'] is not None]
    return dict(true_med=None if not d else round(float(np.median(d)), 1), true_n=len(d), true_vals=[round(x, 1) for x in d],
                xcorr_med=None if not xc else round(float(np.median(xc)), 1), xcorr_n=len(xc), lock_ms=o['lock_ms'],
                lock=(o['lock'] or {}).get('why') or ('applied' if (o['lock'] or {}).get('applied') else None), win=o['win'])
if __name__ == '__main__':
    only = sys.argv[1:]  # optional pick ids
    res = []
    for day, pid in PICKS:
        if only and pid not in only: continue
        for lbl, over in (('lock_on', {}), ('lock_off', {'BLEND_LOCK': 0})):
            try:
                o = measure.run(pid, over, tag='rcc')
                cwd = os.getcwd(); os.chdir('/workspace/mixes/src2')
                try: o['dp'] = deckphase.deck_rows(json.load(open(o['meta'])))
                finally: os.chdir(cwd)
                s = stats(o); s.update(day=day, pick=pid, arm=lbl); res.append(s)
                print(json.dumps(s), flush=True)
                cleanup.drop_our_src2(o.get('created') or [])
            except Exception as e:
                print('ERR', day, pid, lbl, type(e).__name__, str(e)[-300:], flush=True)
    json.dump(res, open(os.path.join(HERE, 'compare.json'), 'w'), indent=1)
