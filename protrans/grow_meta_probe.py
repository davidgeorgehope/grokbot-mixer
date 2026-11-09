import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch, paths
url = sys.argv[1] if len(sys.argv) > 1 else 'https://www.youtube.com/watch?v=PZ6aQYEIqm0'
m = fetch.meta_remote(url)
out = os.path.join(paths.RESULTS, 'grow_meta_' + (m.get('id') or 'unknown') + '.json')
json.dump(m, open(out, 'w'), indent=2)
print(json.dumps(dict(id=m.get('id'), title=m.get('title'), channel=m.get('channel'),
                      duration=m.get('duration'), chapters=len(m.get('chapters') or []),
                      desc_len=len(m.get('description') or [])), indent=2), flush=True)
