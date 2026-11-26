"""n1126: official hard checks (replica/hardcheck.check: beat clash, bass hole, pumping; pro-p95 thresholds, unchanged) on the renders of a
cohort variant. Reads metas in /tmp/protrans_bench, writes nothing there. usage: hc_1126.py <variant>"""
import glob, json, os, sys
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); sys.path.insert(0, os.path.dirname(H))
import run_admitted_tune as T, hardcheck as HC
import paths; os.chdir(paths.SRC2); sys.path.insert(0, paths.SRC2)
v = sys.argv[1]; rows = T.load_ckpt(v); out = {}
for k, r in sorted(rows.items()):
    if not r.get('ours'): out[k] = dict(error='no render'); continue
    m = [x for x in sorted(glob.glob(os.path.splitext(r['ours'])[0] + '_*_meta.json')) if not x.endswith('_dry_meta.json')]
    if not m: out[k] = dict(error='no meta'); continue
    try: out[k] = dict(HC.check(m[0]), win=(r.get('pick') or {}).get('win'), fam=(r.get('pick') or {}).get('fam'))
    except Exception as e: out[k] = dict(error=f'{type(e).__name__}: {e}')
dest = os.path.join(H, 'nightly_1126_work', f'hc_{v}.json'); json.dump(out, open(dest, 'w'), indent=1, default=str)
print(v, 'n', len(out), 'hard_fail', sum(bool(x.get('hard_fail')) for x in out.values()), 'clash', sum(bool(x.get('beat_clash')) for x in out.values()),
      'hole', sum(bool(x.get('bass_hole')) for x in out.values()), 'pump', sum(bool(x.get('pumping')) for x in out.values()), 'errors', sum('error' in x for x in out.values()))
