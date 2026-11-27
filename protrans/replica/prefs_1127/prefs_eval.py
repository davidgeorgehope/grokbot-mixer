import sys, os, collections, json
H = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, H); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ridegate_live as R, listener_prefs as LP, census as C, picker_1119b as B
rows = R.load_all_built()
by = {r['id']: r for r in rows}
dev = [r for r in rows if r['set'] == 'dev']
pr = LP.pref_rows(by) if not os.environ.get("NOPREF") else []
if os.environ.get("DUP"):
    import copy; pr = [dict(copy.deepcopy({k: v for k, v in by[os.environ["DUP"]].items() if not k.startswith("X")}), id="dup")]
print('pref rows', [p['id'] for p in pr])
alt = R.train_pack(dev=dev + pr, dest='/tmp/pack_prefs_1127')
base = R.load_pack()
ev = [r for r in rows if r['set'] in ('dev', 'fresh', 'protrans')]
for r in ev:
    for k in [k for k in r if k.startswith('X')]: del r[k]
d0 = R.predict_rows(base, ev); d1 = R.predict_rows(alt, ev)
sh = collections.defaultdict(collections.Counter); flips = collections.Counter(); err = collections.defaultdict(lambda: [0, 0, 0])
for r, a, b in zip(ev, d0, d1):
    s0, _ = C.win_style(r, a); s1, _ = C.win_style(r, b)
    sh[r['set'] + ' before'][s0] += 1; sh[r['set'] + ' after'][s1] += 1
    if (a.get('win') != b.get('win')): flips[(r['set'], s0, s1)] += 1
    if r.get('pro_ov'):
        e = err[r['set']]; e[0] += abs(a['exit'] - r['pro_out']) + abs(a['cue'] - r['pro_in']); e[1] += abs(b['exit'] - r['pro_out']) + abs(b['cue'] - r['pro_in']); e[2] += 1
for k in sorted(sh):
    n = sum(sh[k].values()); print(k, n, {s: f'{c/n:.0%}' for s, c in sorted(sh[k].items())})
print('flips', dict(flips))
print('mean |exit|+|cue| bars vs pro', {k: (round(v[0]/v[2], 2), round(v[1]/v[2], 2)) for k, v in err.items()})
j = [x for x in zip(ev, d0, d1) if x[0]['id'] == 'joe_syntax_hospital__00'][0]; print('joe', j[1]['win'], j[2]['win'])
