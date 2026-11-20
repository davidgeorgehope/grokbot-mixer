import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.dirname(HERE), '/workspace/mixes/src2']
os.environ['BB_SCRATCH'] = '/tmp/protrans_bench'; os.makedirs('/tmp/protrans_bench', exist_ok=True)
import paths, recreate, cleanup, run_admitted_tune as T
pid = sys.argv[1]; rec = {r['id']: r for r in T.load_recs()}[pid]
rules = json.load(open(paths.RULES)); rules['DRUMCLASH'] = 1
info = recreate.recreate(rec['a']['yt'], rec['b']['yt'], os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'), os.path.join(paths.LIB, rec['b']['yt'] + '.m4a'),
                         hint_a_played_sec=rec['window'].get('hint_a_played_sec'), rules=rules, tag=f'smk{os.getpid()}')
print('PICK', info['fam'], info['win'], info['ours']); print('DC', json.dumps(info['drumclash'], default=str))
json.dump(dict(info, created=None), open(os.path.join(HERE, f'smoke_{pid}.json'), 'w'), default=str, indent=1)
cleanup.drop_our_src2(info.get('created') or [])
