"""Total calls and spend from runs/calls.jsonl (xAI cost_in_usd_ticks = 1e-10 USD)."""
import json, collections, os
H = os.path.dirname(os.path.abspath(__file__)); c = collections.defaultdict(float); n = collections.Counter(); err = 0
for l in open(os.path.join(H, 'runs', 'calls.jsonl')):
    r = json.loads(l)
    if 'error' in r: err += 1; continue
    u = r['usage']; c[r['model']] += u.get('cost_in_usd_ticks', 0) / 1e10; n[r['model']] += 1
print(json.dumps(dict(by_model={m: dict(calls=n[m], usd=round(c[m], 3)) for m in n}, total_calls=sum(n.values()), total_usd=round(sum(c.values()), 3), errors=err)))
