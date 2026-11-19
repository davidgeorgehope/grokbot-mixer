"""Retry one corpus_v2 reject that was caused by another job deleting its sources (2026-11-18 21:57 ET incident).
Runs the normal pipeline steps (same gate, same thresholds) in an ISOLATED work dir (replica/retry_work), never touching
corpus_v2/work. Appends the new verdict to accepted/rejected.jsonl (marked retried_after_incident), archives the used
sources to Drive like archive_mix, then clears only its own dir. usage: retry_one_reject.py <pair_id>"""
import json, os, sys, shutil
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); sys.path.insert(0, P)
import corpus_v2_pipeline as CP, admit
W = os.path.join(H, 'retry_work'); CP.WORK = W; CP.LIB = os.path.join(W, 'lib'); CP.CLIPS = os.path.join(W, 'clips'); CP.MIXES_DIR = os.path.join(W, 'mixes')
for d in (CP.LIB, CP.CLIPS, CP.MIXES_DIR): os.makedirs(d, exist_ok=True)
pid = sys.argv[1]
r = [x for x in CP.load_jsonl(CP.REJECTED) if x.get('id') == pid][-1]
assert pid not in {x['id'] for x in CP.load_jsonl(CP.ACCEPTED)}, 'already accepted'
q = json.load(open(CP.QUEUE))['mixes']; mix = next(m for m in q if m['mix_id'] == r['mix_id'])
snap = CP.snapshot_protected()
dest = CP._mix_audio_for(mix)
c = dict(id=r['id'], mix_id=r['mix_id'], dj=r['dj'], mix_url=r.get('mix_url'), video_id=r.get('video_id'), t_a=r['t_a'], t_b=r['t_b'],
         t_next=r['t_b'] + 90, a=dict(r['a']), b=dict(r['b']))
row, rec, sa, sb = CP.process_pair_v2(c, dest)
row['retried_after_incident'] = '2026-11-18 sources deleted by replica-fresh-1118 archive_mix'
print('verdict', row['verdict'], row.get('reason'), flush=True)
if row['verdict'] == 'admit':
    try:
        feat = CP.extract_features(row, rec, sa, sb); row['feature_path'] = os.path.join('features', row['id'] + '.json'); row['cue'] = feat.get('cue')
    except Exception as e:
        row['feature_error'] = str(e)[:200]; print('feature fail', e, flush=True)
    CP.append_jsonl(CP.ACCEPTED, {k: v for k, v in row.items() if k not in ('pro_clip', '_deck_levels')})
    for s in (sa, sb): CP.archive_and_verify(s, f'sources/{os.path.basename(s)}')
    clip = os.path.dirname(row['pro_clip']); CP.archive_and_verify(clip, f"clips/{row['mix_id']}/{row['id']}")
else:
    CP.append_jsonl(CP.REJECTED, {k: v for k, v in row.items() if k not in ('pro_clip', '_deck_levels')})
CP.assert_protected(snap, where='retry ' + pid)
shutil.rmtree(W, ignore_errors=True)
print('RESULT', pid, row['verdict'], row.get('reason'))
