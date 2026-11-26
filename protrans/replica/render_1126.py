"""n1126: render on the official 33 protrans pairs (a) the current default (arm 'base', rules.json as is, all 33 pairs) and
(b) a frozen picker arm's windows, ONLY the pairs where the arm moved off default (abstained pairs = the base render).
Arms use the existing PICKER_STYLE_GATED flag + PICKER_INJECT_CS=1 (so off-grid / 8-bar picks are scored, not silently dropped)
with a per-arm map on a COPY of rules.json; rules.json is never written. Checkpoint variant n1126_<arm>, render tag prefix n26<x>
in /tmp/protrans_bench (own prefix; only own files are deleted afterwards). usage: render_1126.py <arm> <tag>"""
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__)); P0 = os.path.dirname(H); sys.path.insert(0, H); sys.path.insert(0, P0)
import paths, run_admitted_tune as T
arm, tag = sys.argv[1], sys.argv[2]; W = os.path.join(H, 'nightly_1126_work')
rules = json.load(open(paths.RULES)); assert not rules.get('PICKER_STYLE_GATED')
if arm == 'base':
    recs = T.load_recs()
else:
    mp = os.path.join(W, f'map_{arm}.json'); m = json.load(open(mp))
    rules = dict(rules, PICKER_STYLE_GATED=1, PICKER_INJECT_CS=1); json.dump(rules, open(os.path.join(W, f'rules_{arm}.json'), 'w'), indent=1)
    os.environ['PICKER_STYLE_GATED_MAP'] = mp; os.environ['PICKER_INJECT_CS'] = '1'
    ids = {k for k, v in m['by_id'].items() if v.get('win') and not v.get('abstain')}
    recs = [r for r in T.load_recs() if r['id'] in ids]
print(arm, 'pairs to render', len(recs), flush=True)
rows = T.run_set_checkpointed(recs, rules, f'n1126_{arm}', tag, workers=int(os.environ.get('WORKERS', 4)))
app = {r['id']: (r.get('pick') or {}).get('fam') for r in rows}
print('applied (fam=picker_style_gated):', sum(f == 'picker_style_gated' for f in app.values()), 'of', len(rows), app, flush=True)
