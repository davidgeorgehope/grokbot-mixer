"""Like-for-like ESTAB vs tonight's fresh base: means, mix-grouped bootstrap CI of the per-pair delta, changed pairs with
windows, predicted dips and the pro's placement (protrans/replica/protrans_decisions.json). Read-only."""
import json, sys, random, statistics as st, os
sys.path.insert(0, '/workspace/mixes/src2'); import energy_stab as E
CK = '/workspace/mixes/protrans/results/score_ckpt'
def L(v):
    d = {}
    for l in open(f'{CK}/{v}.jsonl'):
        r = json.loads(l)
        if isinstance(r.get('score'), dict): d[r['id']] = r
    return d
PD = json.load(open('/workspace/mixes/protrans/replica/protrans_decisions.json'))
def dip(r):
    w = r['pick']['win']; a, b = r['pair'], None
    return None
base = L(sys.argv[1]); out = {}
for v in sys.argv[2:]:
    arm = L(v); ids = sorted(set(base) & set(arm)); rows = []
    for k in ids:
        b0, a0 = base[k], arm[k]
        rows.append(dict(id=k, split=b0['split'], mix=k.rsplit('__', 1)[0], d=a0['score']['score'] - b0['score']['score'],
                         base_win=b0['pick']['win'], arm_win=a0['pick']['win'], base=b0['score']['score'], arm=a0['score']['score'],
                         base_fam=b0['pick']['fam'], arm_fam=a0['pick']['fam']))
    res = {}
    for sp in ('train', 'test'):
        R = [r for r in rows if r['split'] == sp]
        mixes = sorted({r['mix'] for r in R}); by = {m: [r for r in R if r['mix'] == m] for m in mixes}
        rng = random.Random(20261124); bs = []
        for _ in range(4000):
            s = [r for m in rng.choices(mixes, k=len(mixes)) for r in by[m]]
            bs.append(st.mean(r['d'] for r in s))
        bs.sort()
        res[sp] = dict(n=len(R), base=round(st.mean(r['base'] for r in R), 2), arm=round(st.mean(r['arm'] for r in R), 2),
                       delta=round(st.mean(r['d'] for r in R), 2), ci95=[round(bs[100], 2), round(bs[3899], 2)],
                       changed=sum(r['base_win'] != r['arm_win'] for r in R))
    ch = []
    for r in rows:
        if r['base_win'] != r['arm_win']:
            p = PD.get(r['id']) or {}
            ch.append(dict(id=r['id'], split=r['split'], base_win=r['base_win'], base_fam=r['base_fam'], arm_win=r['arm_win'], arm_fam=r['arm_fam'],
                           base=round(r['base'], 2), arm=round(r['arm'], 2),
                           pro=dict(out_at_entry=p.get('out_bar_at_entry'), in_at_entry=p.get('in_bar_at_entry'), out_gone=p.get('out_bar_at_gone'), overlap=p.get('overlap_bars'))))
    same = [r['d'] for r in rows if r['base_win'] == r['arm_win']]
    res['same_window_rerender_delta'] = dict(n=len(same), mean=round(st.mean(same), 2) if same else None, max_abs=round(max(map(abs, same)), 2) if same else None)
    res['changed_pairs'] = ch; out[v] = res
print(json.dumps(out, indent=1, default=str))
json.dump(out, open('/workspace/mixes/protrans/research_1124/compare_estab.json', 'w'), indent=1, default=str)
