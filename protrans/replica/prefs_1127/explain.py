"""Which learned signals chose the 11-27 blend (exit + cue LightGBM contributions)."""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ridegate_live as R, picker_1119b as B
EN = ['x','x/na','left','sec@x','sec@x+15','d_dropend','d_drop1end','d_outro','d_bd','d_dropstart'] + ['t_'+t for t in B.ETAGS] + ['na','nb','ndropA','ndropB','introA','introB','outroA','drop1B','bassA_outro','bassB_intro','bassA_bd']
CN = ['x','x/nb','x-drop1B','sec@x','d_bd/drop2','d_introend'] + ['t_'+t for t in B.CTAGS] + EN[-11:]
R._index_built(); r = R._BUILT_BY_ID[sys.argv[1] if len(sys.argv) > 1 else 'joe_syntax_hospital__00']
pack = R.load_pack(); d = R.predict_rows(pack, [r])[0]; print(d)
for part, names, j in (('E', EN, d['je']), ('C', CN, d['jc'])):
    X = r[f'X{part}0']; m = pack['_m' + part]
    s = m.predict(X); c = m.predict(X, pred_contrib=True)
    dix = r[part + 'dix']
    print(part, 'chosen', r[part][j]['v'], round(s[j], 2), 'default', r[part][dix]['v'], round(s[dix], 2))
    diff = c[j, :-1] - c[dix, :-1]
    for i in np.argsort(-np.abs(diff))[:6]: print('   ', names[i], round(float(diff[i]), 2), 'val', X[j, i], 'vs', X[dix, i])
