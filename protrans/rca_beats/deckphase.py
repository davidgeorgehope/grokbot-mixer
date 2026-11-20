"""Rendered-deck phase vs the mix grid (each deck rendered alone, as the engine plays it). Uses gridcheck's onset env."""
import json, sys, os
import numpy as np, librosa
sys.path.insert(0, '/workspace/mixes/src2'); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gridcheck as G

def deck_rows(M, i=0):
    import blend_diag as D, engine as E
    s0, A, B = D.crop_decks(M, i); t = M['trans'][i]
    nb = int(round(len(A) / E.BS)); out = []
    allA, allB = D.band_bar_db(A, nb, E.BS), D.band_bar_db(B, nb, E.BS)
    envs = []
    for y in (A, B):
        m = librosa.resample(y.mean(1), orig_sr=44100, target_sr=22050)
        envs.append((G.onset_env(m, 22050, 20, 150), G.onset_env(m, 22050, 150, 2000)))
    srcA = M['decks'][i]; srcB = M['decks'][i + 1]
    def src_bar(d, mb):
        j = int(mb - d['start_bar']); fm = d['full_map']
        return fm[j][0] if 0 <= j < len(fm) else None
    for k in range(nb):
        r = dict(bar=s0 + k, srcA=src_bar(srcA, s0 + k), srcB=src_bar(srcB, s0 + k), dbA=round(float(allA[k]), 1), dbB=round(float(allB[k]), 1))
        for nm, ((ok, dt), (osn, _)) in zip('AB', envs):
            pk, rk = G.bar_phase(ok, dt, k * E.BAR, E.BEAT); ps, rs = G.bar_phase(osn, dt, k * E.BAR, E.BEAT)
            r[f'sn{nm}'] = None if np.isnan(ps) else round(ps, 1); r[f'rs{nm}'] = round(rs, 2)
        out.append(r)
    return dict(s0=s0, start=t['start_bar'], end=t['end_bar'], lock=t.get('blend_lock'), lock_ms=srcB.get('blend_lock_ms'), rows=out)

if __name__ == '__main__':
    M = json.load(open(sys.argv[1])); os.chdir('/workspace/mixes/src2')
    o = deck_rows(M)
    print('blend', o['start'], o['end'], 'lock_ms', o['lock_ms'])
    for r in o['rows']:
        d = None
        if r['snA'] is not None and r['snB'] is not None and r['rsA'] >= .2 and r['rsB'] >= .2:
            d = round((r['snA'] - r['snB'] + 172.4) % 344.8 - 172.4, 1)
        print(r, 'A-B', d)
