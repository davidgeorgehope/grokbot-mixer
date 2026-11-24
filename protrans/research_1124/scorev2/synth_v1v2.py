import os, sys, json, tempfile, numpy as np
PT = '/workspace/mixes/protrans'; sys.path.insert(0, PT); sys.path.insert(0, PT + '/tests')
import st_pin; os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
import paths, score, score_v2 as S2, test_score_v2 as TT
d = tempfile.mkdtemp(prefix='sv2_syn_'); ga, gb = TT._blend(8, 16)
P = {k: os.path.join(d, k + '.wav') for k in ('ref', 'near', 'far', 'full')}
TT._synth(P['ref'], 122, 14, ga, gb); TT._synth(P['near'], 124, 16, ga, gb); TT._synth(P['far'], 234, 14, ga, gb); TT._synth(P['full'], 122, 14, np.ones(33), np.ones(33))
sa, sb = (os.path.join(paths.LIB, y + '.m4a') for y in TT.UKF)
out = {}
for k in ('ref', 'near', 'far', 'full'):
    r = S2.score_v2(P['ref'], P[k], sa, sb)
    out[k] = dict(v1=r['score'], v2=r['official_v2'], place=r['placement']['parts'])
    print(k, out[k], flush=True)
json.dump(out, open(PT + '/research_1124/scorev2/synth_v1v2.json', 'w'), indent=1)
