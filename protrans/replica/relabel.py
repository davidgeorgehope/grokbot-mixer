"""DAgger-style relabel (dev only): for each rollout (default / gated) where our exit or cue lands in a different section than the
pro's, record the section the pro used and the nearest phrase-grid boundary to the pro's bar (the corrected target for that state).
Writes replica/relabel_dev.jsonl and prints the section confusion."""
import json, os, sys, collections
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import policy as PO
def sec_of(s, bar):
    d = s.get('drops') or []; na = s.get('music_end') or 0
    if bar >= na: return 'after_end'
    if bar >= (s.get('outro_start') or na): return 'outro'
    for k, (a, b) in enumerate(d):
        if a <= bar < b: return f'drop{k+1}'
        if k + 1 < len(d) and b <= bar < d[k+1][0]: return f'breakdown{k+1}'
    return 'intro' if bar < (d[0][0] if d else 0) else 'other'
if __name__ == '__main__':
    os.chdir(PO.SRC2); import sections as S
    rs = PO.load_all(False); out = []; conf = collections.Counter()
    for r in rs:
        a, b = r['D']['id'], None
        pr = {p['id']: p for p in PO.EG.pairs()}[r['id']]; sa, sb = S.get(pr['a']), S.get(pr['b'])
        for v in ('D', 'G'):
            x = r[v]
            for side, s, ours, pro, bnd in (('exit', sa, x['ours']['out_bar'], r['pro']['out_bar'], r['bnd']), ('cue', sb, x['ours']['in_bar'], r['pro']['in_bar'], r['bndb'])):
                so, sp = sec_of(s, ours), sec_of(s, pro)
                conf[(v, side, so, sp)] += 1
                if so != sp:
                    tgt = min(bnd + [int(round(pro / 8) * 8)], key=lambda q: abs(q - pro))
                    out.append(dict(id=r['id'], dj=r['dj'], rollout=v, side=side, ours_bar=ours, ours_sec=so, pro_bar=pro, pro_sec=sp, relabel_bar=tgt))
    with open(os.path.join(H, 'relabel_dev.jsonl'), 'w') as f:
        for o in out: f.write(json.dumps(o) + '\n')
    for v in ('D', 'G'):
        for side in ('exit', 'cue'):
            tot = sum(c for k, c in conf.items() if k[:2] == (v, side)); same = sum(c for k, c in conf.items() if k[:2] == (v, side) and k[2] == k[3])
            top = collections.Counter({(k[2], k[3]): c for k, c in conf.items() if k[:2] == (v, side) and k[2] != k[3]}).most_common(4)
            print(v, side, f'same section {same}/{tot}', 'top misses (ours->pro):', top)
