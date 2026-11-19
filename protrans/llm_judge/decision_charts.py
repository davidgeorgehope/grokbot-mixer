"""Ours-vs-pro DECISION charts (no audio): one composite PNG per case with three timelines drawn the same way:
REF = what the pro did, X and Y = two candidate plans. Each timeline shows both tracks' section maps (intro/build/drop/
breakdown/outro) and where the blend sits on each track (exit/cue window, overlap length, bass-swap tick).
Ground truth = the candidate with the smaller decision error vs the pro: |exit|+|cue|+|overlap| (+|swap|) in bars.
Candidates: 'ours' = the real default plan for that pair (replica/gate_ckpt/default.jsonl), 'near' = the pro plan with a small
seeded jitter, 'far' = the pro plan with a large seeded jitter. Kinds: ours_vs_near (when ours is far from the pro),
near_vs_far (always), close_call = jitter 6 vs 16 bars (kept only when the errors differ by >= 6 bars). Seed 20261118."""
import json, os, sys, random, hashlib
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H)
OUT = os.path.join(H, 'cases_dec'); os.makedirs(OUT, exist_ok=True)
COL = dict(intro='#d9d9d9', build='#a6cee3', drop='#e31a1c', breakdown='#33a02c', outro='#969696')

def lane(ax, y, sec, start, length, label, swap=None):
    for ph in sec['phases']:
        ax.barh(y, ph['end'] - ph['start'], left=ph['start'], height=0.6, color=COL.get(ph['name'], '#ffffff'), edgecolor='white')
    ax.barh(y, length, left=start, height=0.9, fill=False, edgecolor='k', lw=2.2)
    if swap is not None: ax.plot([swap, swap], [y - 0.5, y + 0.5], color='gold', lw=3)
    ax.text(-4, y, label, ha='right', va='center', fontsize=8)

def plan_ax(ax, d, plan, name):
    ov = max(2, plan['overlap'])
    sw = plan.get('swap_after_entry')
    lane(ax, 1, d['sec_a'], plan['out_bar'], ov, 'outgoing', None if sw is None else plan['out_bar'] + sw)
    lane(ax, 0, d['sec_b'], plan['in_bar'], ov, 'incoming', None if sw is None else plan['in_bar'] + sw)
    ax.set_xlim(-30, max(d['sec_a']['n_bars'], d['sec_b']['n_bars']) + 4); ax.set_ylim(-0.7, 1.7); ax.set_yticks([])
    ax.set_title(name, fontsize=11, loc='left', fontweight='bold'); ax.set_xlabel('bar within each track', fontsize=8)

def draw(d, ref, X, Y, png):
    fig, ax = plt.subplots(3, 1, figsize=(10, 6.2))
    plan_ax(ax[0], d, ref, 'REF (pro)'); plan_ax(ax[1], d, X, 'X'); plan_ax(ax[2], d, Y, 'Y')
    hs = [plt.Rectangle((0, 0), 1, 1, color=c) for c in COL.values()]
    fig.legend(hs + [plt.Rectangle((0, 0), 1, 1, fill=False, ec='k', lw=2), plt.Line2D([0], [0], color='gold', lw=3)],
               list(COL) + ['blend window on that track', 'bass swap'], loc='lower center', ncol=7, fontsize=7)
    fig.tight_layout(rect=(0, 0.05, 1, 1)); fig.savefig(png, dpi=90); plt.close(fig)

def err(p, q):
    e = abs(p['out_bar'] - q['out_bar']) + abs(p['in_bar'] - q['in_bar']) + abs(p['overlap'] - q['overlap'])
    if p.get('swap_after_entry') is not None and q.get('swap_after_entry') is not None: e += abs(p['swap_after_entry'] - q['swap_after_entry'])
    return round(e, 1)

def jitter(rng, pro, mag):
    q = dict(pro); q['out_bar'] = pro['out_bar'] + rng.choice([-1, 1]) * rng.uniform(.5, 1) * mag
    q['in_bar'] = max(0, pro['in_bar'] + rng.choice([-1, 1]) * rng.uniform(.5, 1) * mag)
    q['overlap'] = max(4, round(pro['overlap'] + rng.choice([-1, 1]) * rng.uniform(0, .5) * mag)); return q

def main():
    rng = random.Random(20261118)
    PRO = json.load(open(os.path.join(P, 'replica', 'protrans_decisions.json')))
    ours = {}
    for l in open(os.path.join(P, 'replica', 'gate_ckpt', 'default.jsonl')):
        r = json.loads(l)
        if r.get('ours'): ours[r['id']] = r['ours']
    man = open(os.path.join(H, 'cases_dec.jsonl'), 'w')
    for pid, d in sorted(PRO.items()):
        if d.get('out_bar_at_entry') is None or not d.get('sec_a') or not d.get('sec_b'): continue
        pro = dict(out_bar=d['out_bar_at_entry'], in_bar=d['in_bar_at_entry'], overlap=d.get('overlap_bars') or 16, swap_after_entry=d.get('swap_after_entry'))
        split = 'heldout' if int(hashlib.md5(pid.encode()).hexdigest(), 16) % 3 == 0 else 'dev'
        kinds = [('near_vs_far', jitter(rng, pro, 4), jitter(rng, pro, 40))]
        if pid in ours and ours[pid].get('overlap'):
            o = dict(ours[pid]); o['overlap'] = o['overlap'] or 16
            if err(o, pro) >= 24: kinds.append(('ours_vs_near', jitter(rng, pro, 4), o))
        r2 = random.Random(pid + '|close')   # separate stream: adding this kind does not move the earlier cases
        g2, b2 = jitter(r2, pro, 6), jitter(r2, pro, 16)
        if err(b2, pro) - err(g2, pro) >= 6: kinds.append(('close_call', g2, b2))
        for kind, good, bad in kinds:
            g_first = rng.random() < 0.5; X, Y = (good, bad) if g_first else (bad, good)
            case = f'{pid}__dec_{kind}'; png = os.path.join(OUT, case + '.png'); draw(d, pro, X, Y, png)
            png_sw = os.path.join(OUT, case + '_swap.png'); draw(d, pro, Y, X, png_sw)   # same case, X/Y swapped (position-bias check)
            man.write(json.dumps(dict(case=case, pair=pid, split=split, kind=kind, png=png, png_swap=png_sw, closer='X' if g_first else 'Y',
                                      err_X=err(X, pro), err_Y=err(Y, pro))) + '\n')
    man.close()

if __name__ == '__main__':
    main()
