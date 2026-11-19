"""2026-11-19 wrap-up: score the frozen picker_1119b once on the fresh mix (fresh_mixes.json for_night 2026-11-19).
The nightly accepted snapshot (01:12 ET) predates the fresh ingest, so the fresh mix's rows are appended from
corpus_v2/accepted.jsonl into a temp copy of the snapshot. Training rows (dev) are unchanged. Defaults are proxies:
the fresh sources were cleaned after ingest, so no renders / hard checks."""
import json, os, sys, tempfile, shutil, runpy
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import picker_1119 as P
T = tempfile.mkdtemp(); shutil.copy(os.path.join(P.W, 'accepted_snapshot.jsonl'), os.path.join(T, 'accepted_snapshot.jsonl'))
with open(os.path.join(T, 'accepted_snapshot.jsonl'), 'a') as o:
    for l in open(os.path.join(os.path.dirname(H), 'corpus_v2', 'accepted.jsonl')):
        if json.loads(l)['mix_id'] in P.SPENT_FRESH: o.write(l if l.endswith('\n') else l + '\n')
P.W = T; sys.argv = ['picker_1119b.py', 'fresh']
runpy.run_path(os.path.join(H, 'picker_1119b.py'), run_name='__main__')
