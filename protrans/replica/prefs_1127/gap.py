import sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ridegate_live as R, census as C
rows = [r for r in R.load_all_built() if r['set'] in ('dev', 'fresh')]
decs = R.predict_rows(R.load_pack(), rows)
cnt = collections.Counter()
for r, d in zip(rows, decs):
    if not r.get('pro_ov'): continue
    ps = C.style(r['sa'], r['sb'], r['pro_out'] - 1, r['pro_in'] - 1, int(round(r['pro_ov'])))
    os_, X = C.win_style(r, d)
    if ps != 'drop>drop': continue
    ex = d['exit'] if not d.get('is_default') else r['dex']; cu = d['cue'] if not d.get('is_default') else r['dcue']
    eok = abs(ex - r['pro_out']) <= 8; cok = abs(cu - r['pro_in']) <= 8
    near_e = min(abs(c['v'] - r['pro_out']) for c in r['E']); near_c = min(abs(c['v'] - r['pro_in']) for c in r['C'])
    db = [tuple(d_) for d_ in r['sb'].get('drops') or []]
    rel = [r['pro_in'] - 1 - d0 for d0, d1 in db if d0 - 4 <= r['pro_in'] - 1 < d1]
    cnt[(r['set'], os_, 'exit_ok' if eok else 'exit_off', 'cue_ok' if cok else 'cue_off', 'candC<=4' if near_c <= 4 else 'candC>4')] += 1
    cnt[(r['set'], 'pro_cue_rel_drop_start', (int(rel[0]) // 8 * 8) if rel else None)] += 1
for k, v in sorted(cnt.items(), key=str): print(k, v)
