"""One tuning pass over GENERAL rules only.

Accept a candidate only if the held-out mean does not drop.
Never writes per-track pins. Logs train and test scores for every try.
"""
from __future__ import annotations
import json, os, copy, time
import paths

def mean_score(rows):
    xs = [r['score']['score'] for r in rows if r.get('score')]
    return None if not xs else round(sum(xs)/len(xs), 2)

def variants(base):
    out = [dict(name='baseline', rules=base)]
    v = copy.deepcopy(base); v['BASS_SWAP_BARS'] = 2
    out.append(dict(name='swap_2bar', rules=v))
    v = copy.deepcopy(base); v['SWAP_POS'] = 0.21
    out.append(dict(name='swap_pos_021', rules=v))
    v = copy.deepcopy(base); v['hint_weight'] = 0.4
    out.append(dict(name='hint_stronger', rules=v))
    return out

def pick(results):
    """results: [{name, rules, train_mean, test_mean}]"""
    base = next(r for r in results if r['name']=='baseline')
    floor = base['test_mean']
    ok = [r for r in results if r['test_mean'] is not None and floor is not None and r['test_mean'] >= floor - 1e-9]
    if not ok:
        return base, 'no candidate kept test mean; keep baseline'
    best = max(ok, key=lambda r: (r['train_mean'] if r['train_mean'] is not None else -1, r['test_mean']))
    why = 'held-out mean did not drop'
    if best['name']=='baseline':
        why = 'no general-rule change beat baseline without dropping the held-out mean'
    return best, why

def log_row(row):
    os.makedirs(paths.LOGS, exist_ok=True)
    path = os.path.join(paths.LOGS, 'tune_log.jsonl')
    row = dict(row); row['ts'] = time.strftime('%Y-%m-%d %H:%M %Z')
    with open(path,'a') as f: f.write(json.dumps(row)+'\n')
    return path
