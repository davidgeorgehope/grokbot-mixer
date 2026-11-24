#!/usr/bin/env python3
"""Compare STRUCT_MID=1 (fmid1123) to the default (fdef1123) / js13def on the
fresh-1123 pairs plus joe_syntax_hospital__13. Placement only. Does not promote."""
import json, os, sys, collections
H = os.path.dirname(os.path.abspath(__file__))
CK = os.path.join(H, 'gate_ckpt')
BR = os.path.join(H, 'fresh1123_exit_cue_breakdown.json')
OUT = os.path.join(H, 'fresh1123_struct_mid_eval.json')

def load(v):
    p = os.path.join(CK, v + '.jsonl')
    return {json.loads(l)['id']: json.loads(l) for l in open(p) if l.strip()} if os.path.exists(p) else {}

def mean(xs):
    return None if not xs else round(sum(xs) / len(xs), 2)

base_fresh = load('fdef1123')
base_js = load('js13def')
arm = load('fmid1123')
br = json.load(open(BR)) if os.path.exists(BR) else {'rows': []}
meta = {r['id']: r for r in br.get('rows', [])}

ids = sorted(set(arm) & (set(base_fresh) | set(base_js) | {'joe_syntax_hospital__13'}))
# also include arm-only with a base
rows = []
missing = []
for i in sorted(set(arm) | set(base_fresh) | {'joe_syntax_hospital__13'}):
    b = base_fresh.get(i) or base_js.get(i)
    a = arm.get(i)
    if not a or not b or a.get('error') or b.get('error'):
        if i in arm or i in base_fresh or i == 'joe_syntax_hospital__13':
            missing.append(i)
        continue
    be, ae = b['err']['exit'], a['err']['exit']
    bc, ac = b['err']['cue'], a['err']['cue']
    m = meta.get(i, {})
    rec = dict(
        id=i, mix=b.get('mix') or m.get('mix'), pair=m.get('pair'),
        pro_out=m.get('pro_out'), pro_in=m.get('pro_in'),
        default_win=b['win'], arm_win=a['win'],
        changed=list(b['win']) != list(a['win']),
        default_exit=round(be, 2), arm_exit=round(ae, 2), d_exit=round(ae - be, 2),
        default_cue=round(bc, 2), arm_cue=round(ac, 2), d_cue=round(ac - bc, 2),
        default_ours_out=b['ours']['out_bar'], arm_ours_out=a['ours']['out_bar'],
        default_ours_in=b['ours']['in_bar'], arm_ours_in=a['ours']['in_bar'],
        default_hard=bool(b['hard'].get('hard_fail')), arm_hard=bool(a['hard'].get('hard_fail')),
        default_ooi=(m.get('default') or {}).get('ooi_exit'),
        default_signed_exit=(m.get('default') or {}).get('signed_exit'),
        mid_track_pro=i in ((br.get('mid_track_pro') or {}).get('default') or {}).get('ids', []),
    )
    rows.append(rec)

fresh = [r for r in rows if r['id'] != 'joe_syntax_hospital__13']
js = [r for r in rows if r['id'] == 'joe_syntax_hospital__13']
changed = [r for r in fresh if r['changed']]
new_fails = [r['id'] for r in fresh if r['arm_hard'] and not r['default_hard']]
fixed = [r['id'] for r in fresh if r['default_hard'] and not r['arm_hard']]
mid = [r for r in fresh if r['mid_track_pro']]
ooi_late = [r for r in fresh if (r['default_signed_exit'] or 0) > 8 and r['default_ooi']]

def pack(subset, label):
    if not subset:
        return dict(n=0, label=label)
    return dict(
        n=len(subset), label=label,
        default_exit=mean([r['default_exit'] for r in subset]),
        arm_exit=mean([r['arm_exit'] for r in subset]),
        d_exit=mean([r['d_exit'] for r in subset]),
        default_cue=mean([r['default_cue'] for r in subset]),
        arm_cue=mean([r['arm_cue'] for r in subset]),
        d_cue=mean([r['d_cue'] for r in subset]),
        n_changed=sum(1 for r in subset if r['changed']),
    )

out = dict(
    error_direction='exit and cue are errors; lower is better; d_* = arm - default, so d_exit > 0 is worse',
    
    flag={'STRUCT_MID': 1, 'STRUCT_MID_B': 100, 'STRUCT_MID_W': 100},
    note=('STRUCT_MID=1 reduces the outro-over-intro bonus to 100 and adds a 100-point competing bonus at drop-1-end / breakdown-end exits, only when the outgoing track has a post-drop breakdown or half-time pocket. '
          'Diagnostic placement test on the spent 2026-11-23 fresh mixes plus the S.P.Y RCA pair. '
          'Exit and cue are errors (lower is better). A positive d_exit means the arm is worse. Not a promotion run.'),
    n_fresh=len(fresh), n_arm=len(arm), missing=missing,
    overall=pack(fresh, 'fresh-1123 19'),
    mid_track_pro=pack(mid, 'pro still >32 bars from engine outro'),
    ooi_late=pack(ooi_late, 'default was late OOI (signed_exit>8)'),
    changed_ids=[r['id'] for r in changed],
    new_hard_fails=new_fails, fixed_hard_fails=fixed,
    js13=js[0] if js else None,
    rows=rows,
)
json.dump(out, open(OUT, 'w'), indent=2)
s = out['overall']
print('STRUCT_MID=1 n', s['n'], 'changed', s['n_changed'],
      'exit', s['default_exit'], '->', s['arm_exit'], 'd', s['d_exit'],
      'cue', s['default_cue'], '->', s['arm_cue'], 'd', s['d_cue'],
      'new_fails', new_fails, 'fixed', fixed)
if mid:
    m = out['mid_track_pro']
    print('mid-track pro n', m['n'], 'exit', m['default_exit'], '->', m['arm_exit'], 'd', m['d_exit'])
if js:
    j = js[0]
    print('JS13', 'win', j['default_win'], '->', j['arm_win'],
          'exit', j['default_exit'], '->', j['arm_exit'],
          'cue', j['default_cue'], '->', j['arm_cue'], 'changed', j['changed'])
print('wrote', OUT)
