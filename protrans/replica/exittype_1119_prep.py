#!/usr/bin/env python3
"""2026-11-19 exit-type picker, feature prep (no labels touched): per track in the dev snapshot that has a local st/<id>.wav,
(1) key (essentia KeyExtractor, edma profile -> Camelot), (2) consonance peak cache (src2/consonance.track_peaks, reused by
the pair roughness feature). Writes exittype_1119_work/trackfeat.json. Safe to resume."""
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); SRC2 = os.path.join(os.path.dirname(P), 'src2')
sys.path.insert(0, SRC2); sys.path.insert(0, H)
import consonance as CO
out_p = os.path.join(H, 'exittype_1119_work', 'trackfeat.json')
out = json.load(open(out_p)) if os.path.exists(out_p) else {}
ids = []
for src in ('nightly_1119_work/accepted_snapshot.jsonl',):
    for l in open(os.path.join(H, src)):
        a = json.loads(l); f = json.load(open(os.path.join(P, 'corpus_v2', 'features', a['id'] + '.json')))
        if f.get('error'): continue
        for t in ('track_a', 'track_b'):
            if f[t]['yt'] not in ids: ids.append(f[t]['yt'])
import essentia.standard as es
CAM={('C','major'):'8B',('G','major'):'9B',('D','major'):'10B',('A','major'):'11B',('E','major'):'12B',('B','major'):'1B',('F#','major'):'2B',('Gb','major'):'2B',('C#','major'):'3B',('Db','major'):'3B',('G#','major'):'4B',('Ab','major'):'4B',('D#','major'):'5B',('Eb','major'):'5B',('A#','major'):'6B',('Bb','major'):'6B',('F','major'):'7B',
('A','minor'):'8A',('E','minor'):'9A',('B','minor'):'10A',('F#','minor'):'11A',('Gb','minor'):'11A',('C#','minor'):'12A',('Db','minor'):'12A',('G#','minor'):'1A',('Ab','minor'):'1A',('D#','minor'):'2A',('Eb','minor'):'2A',('A#','minor'):'3A',('Bb','minor'):'3A',('F','minor'):'4A',('C','minor'):'5A',('G','minor'):'6A',('D','minor'):'7A'}

for i, yt in enumerate(ids):
    wav = os.path.join(SRC2, 'st', yt + '.wav')
    if not os.path.exists(wav): continue
    r = out.get(yt) or {}
    if 'key' not in r:
        a = es.MonoLoader(filename=wav, sampleRate=44100)()
        k, s, stg = es.KeyExtractor(profileType='edma', sampleRate=44100)(a); r['key'] = CAM[(k, s)]; r['key_strength'] = round(float(stg), 3); del a
    if 'peaks' not in r:
        try: CO.track_peaks(yt); r['peaks'] = True
        except Exception as e: r['peaks'] = False; r['peaks_err'] = str(e)[:200]
        CO._MEM.pop(yt, None)
    out[yt] = r
    if i % 10 == 0:
        json.dump(out, open(out_p + '.tmp', 'w')); os.replace(out_p + '.tmp', out_p); print(i, len(ids), yt, r, flush=True)
json.dump(out, open(out_p + '.tmp', 'w')); os.replace(out_p + '.tmp', out_p)
print('DONE tracks', len(out), 'keys', sum('key' in v for v in out.values()), 'peaks', sum(bool(v.get('peaks')) for v in out.values()))
