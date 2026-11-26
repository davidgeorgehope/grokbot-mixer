"""n1126: render on the official 33 protrans pairs (a) the current default (arm 'base', rules.json as is, all 33 pairs) and
(b) a frozen picker arm's windows, ONLY the pairs where the arm moved off default (abstained pairs = the base render).
Arms use the existing PICKER_STYLE_GATED flag + PICKER_INJECT_CS=1 (so off-grid / 8-bar picks are scored, not silently dropped)
with a per-arm map on a COPY of rules.json; rules.json is never written. Checkpoint variant n1126_<arm>, render tag prefix n26<x>
in /tmp/protrans_bench (own prefix; only own files are deleted afterwards). usage: render_1126.py <arm> <tag>"""
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__)); P0 = os.path.dirname(H); sys.path.insert(0, H); sys.path.insert(0, P0)
import paths, run_admitted_tune as T
arm, tag = sys.argv[1], sys.argv[2]; W = os.path.join(H, 'nightly_1126_work')
# Do not inherit leftover picker env; a COPY of rules.json is the only source. Never write rules.json.
for _k in ('PICKER_STYLE_GATED', 'PICKER_STYLE_GATED_MAP', 'PICKER_INJECT_CS', 'RIDEGATE', 'RIDEGATE_PACK', 'PICKER_WIN'):
    os.environ.pop(_k, None)
rules = json.load(open(paths.RULES)); assert not rules.get('PICKER_STYLE_GATED'); assert not rules.get('RIDEGATE')
if arm == 'base':
    recs = T.load_recs()
elif arm == 'ridegate_live':
    # Same 25 moved pairs as the n1126 map; windows are computed live (RIDEGATE=1), map flags stay off.
    m = json.load(open(os.path.join(W, 'map_ridegate.json')))
    rules = dict(rules, RIDEGATE=1)
    json.dump(rules, open(os.path.join(W, 'rules_ridegate_live.json'), 'w'), indent=1)
    ids = {k for k, v in m['by_id'].items() if v.get('win') and not v.get('abstain')}
    recs = [r for r in T.load_recs() if r['id'] in ids]
else:
    mp = os.path.join(W, f'map_{arm}.json'); m = json.load(open(mp))
    rules = dict(rules, PICKER_STYLE_GATED=1, PICKER_INJECT_CS=1); json.dump(rules, open(os.path.join(W, f'rules_{arm}.json'), 'w'), indent=1)
    os.environ['PICKER_STYLE_GATED_MAP'] = mp; os.environ['PICKER_INJECT_CS'] = '1'
    ids = {k for k, v in m['by_id'].items() if v.get('win') and not v.get('abstain')}
    recs = [r for r in T.load_recs() if r['id'] in ids]
print(arm, 'pairs to render', len(recs), flush=True)
rows = T.run_set_checkpointed(recs, rules, f'n1126_{arm}', tag, workers=int(os.environ.get('WORKERS', 4)))
app = {r['id']: (r.get('pick') or {}).get('fam') for r in rows}
want_fam = 'ridegate_live' if arm == 'ridegate_live' else 'picker_style_gated'
print(f'applied (fam={want_fam}):', sum(f == want_fam for f in app.values()), 'of', len(rows), app, flush=True)
