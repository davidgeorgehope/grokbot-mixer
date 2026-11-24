"""Dry candidate dump for one pair under rules (+ env overrides). No render."""
import sys, os, json
sys.path.insert(0, '/workspace/mixes/protrans'); import paths, recreate as R
a, b = sys.argv[1], sys.argv[2]; extra = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
rules = {**R.load_rules(), **extra}
os.environ['BB_SCRATCH'] = '/tmp/protrans_bench_dry1124'; os.makedirs('/tmp/protrans_bench_dry1124', exist_ok=True); os.environ['PREF_W'] = '0'
sys.path.insert(0, paths.SRC2); created = []
A = R._prep_track(a, os.path.join(paths.LIB, a + '.m4a'), created); B = R._prep_track(b, os.path.join(paths.LIB, b + '.m4a'), created)
import blend_bench as BB
os.environ.update(R.apply_rules(rules)); os.chdir(paths.SRC2)
cs = BB.cands_for(A, B, 'dry1124')
cs = [c for c in cs if not c.get('land_extra')]
fams = BB.families(cs, None)
print('top cands:', [(c['win'], round(c['cost'], 1)) for c in sorted(cs, key=lambda c: c['cost'])[:6]])
print('families:', [(f['fam'], f['win'], f.get('cost', f.get('rank'))) for f in fams][:8])
