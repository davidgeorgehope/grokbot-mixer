#!/usr/bin/env python3
"""2026-11-19: standard "pro pick vs ours and why" table + PNG for every daily delivery and RCA (listener rule). For one protrans pick and one or
more of our windows: outgoing bar, incoming bar and time for the blend start / bass swap / end, the section each sits in (intro, drop N,
breakdown, outro; + slowdown / half-time from replica/halftime/slowdown.py), whether the window touches the outgoing's slowdown, where the
incoming's first drop lands, and how much of the outgoing's last drop plays. Writes <stem>_provsours.md/.json/.png in out_dir.
usage: provsours.py pick_id stem 'json {label: [kind, out_bar, loop, in_bar, X], ...}' [out_dir]"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'replica', 'halftime'))
import paths
SRC2 = paths.SRC2; DEC = os.path.join(HERE, 'replica', 'protrans_decisions.json')

def _sec(yt): return json.load(open(os.path.join(SRC2, 'st', yt + '.sections.json')))
def _bar_s(yt): return 4 * json.load(open(os.path.join(SRC2, 'st', yt + '.json')))['per']
def _slow(yt):
    try:
        import slowdown as SD; P = SD.profile(yt); return [tuple(x) for x in (P or {}).get('sections', [])]
    except Exception: return []
def label(yt, bar):
    s = _sec(yt); dr = s.get('drops') or []; sl = _slow(yt); t = None
    if not dr or bar < dr[0][0]: t = 'intro'
    for i, (x, y) in enumerate(dr):
        if x <= bar < y: t = f'drop {i + 1}'
    if t is None: t = 'outro' if bar >= dr[-1][1] else 'breakdown'
    if any(x <= bar < y for x, y in sl): t += ' + slowdown/half-time'
    return t
def _mmss(t): return f'{int(t // 60)}:{int(t % 60):02d}'

def row(name, ya, yb, a0, a1, b0, swap_a=None, mix_t0=None, why=''):
    sa, sb = _sec(ya), _sec(yb); dr = sa.get('drops') or [[0, 0]]; sl = _slow(ya); d1 = sb.get('drop1')
    touch = any(x < a1 and a0 < y for x, y in sl); lde = dr[-1][1]
    nd = [x for x, y in (sb.get('drops') or []) if x >= b0]; d1 = nd[0] if nd else None  # B's next drop at/after its entry
    r = dict(who=name, out_start=a0, out_end=a1, in_start=b0, in_end=b0 + (a1 - a0), out_swap=swap_a,
             out_start_section=label(ya, a0), in_start_section=label(yb, b0), touches_out_slowdown=touch,
             in_next_drop_vs_blend_end=(None if d1 is None else round(d1 - (b0 + (a1 - a0)), 1)),
             out_last_drop_played=('all' if a0 >= lde - 0.5 else f'cut {round(lde - a0)} bars early' if a1 <= lde else f'blend starts {round(lde - a0)} bars before its end'),
             out_time=_mmss(a0 * _bar_s(ya)), mix_time=(None if mix_t0 is None else _mmss(mix_t0)), why=why)
    return r

def make(pick_id, stem, ours, out_dir=None):
    out_dir = out_dir or os.path.join(paths.DELIVER, 'diagnostics'); D = json.load(open(DEC)).get(pick_id)
    import run_admitted_tune as T
    rec = {r['id']: r for r in T.load_recs()}[pick_id]; ya, yb = rec['a']['yt'], rec['b']['yt']
    meta = json.load(open(os.path.join(os.path.dirname(rec['pro_clip']), 'meta.json'))); bs = _bar_s(ya)
    rows = []
    if D:
        t0 = meta.get('pro_clip_start')
        rows.append(row('pro', ya, yb, D['out_bar_at_entry'], D['out_bar_at_gone'], D['in_bar_at_entry'], D.get('out_bar_at_swap'),
                        None if t0 is None else t0 + D['in_entry_clip_bar'] * bs, why='what the DJ did'))
    sa, sb = _sec(ya), _sec(yb); es = (sa['music_end'] // 8) * 8
    for lab, w in ours.items():
        kind, ea, loop, ib, X = w; a0 = ea - X
        why = []
        if kind in ('n', 'lb') and ea >= sa.get('outro_start', 1e9) and ib == (sb.get('drop1') or -99) - X: why.append("outro-over-intro bonus window (A plays its outro, B's first drop lands as A ends)")
        if sb.get('drop1') is not None and ib <= sb['drop1'] < ib + X: why.append("B's first drop lands inside the blend")
        if any(x <= a0 < y for x, y in _slow(ya)): why.append('blend starts inside the outgoing slowdown')
        rows.append(row(lab, ya, yb, a0, ea, ib, None, None, '; '.join(why) or 'lowest engine cost'))
    res = dict(pick=pick_id, pair=rec['pair'], rows=rows)
    os.makedirs(out_dir, exist_ok=True); json.dump(res, open(os.path.join(out_dir, stem + '_provsours.json'), 'w'), indent=1)
    cols = ['who', 'out_start', 'out_end', 'in_start', 'out_start_section', 'in_start_section', 'touches_out_slowdown', 'in_next_drop_vs_blend_end', 'out_last_drop_played', 'out_time', 'mix_time', 'why']
    md = [f"# Pro pick vs ours: {pick_id}", '', f"{rec['pair']}. Bars are each track's own bars at mix tempo; in_next_drop_vs_blend_end < 0 means the incoming's drop lands inside the blend, 0 = right as it ends; out_time is the time in the outgoing track; mix_time is the pro's set.", '',
          '| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)] + ['| ' + ' | '.join(str(r.get(c)) for c in cols) + ' |' for r in rows]
    open(os.path.join(out_dir, stem + '_provsours.md'), 'w').write('\n'.join(md) + '\n')
    try:
        import pro_vs_ours_png as PP
        pro = dict(A=[rows[0]['out_start'], rows[0]['out_end']], B=[rows[0]['in_start'], rows[0]['in_end']], swapA=rows[0]['out_swap']) if D else dict(A=[0, 0], B=[0, 0])
        PP.main(os.path.join(out_dir, stem + '_provsours.png'), ya, yb, pro, {r['who']: dict(A=[r['out_start'], r['out_end']], B=[r['in_start'], r['in_end']]) for r in rows if r['who'] != 'pro'},
                ('outgoing: ' + rec['pair'].split(' -> ')[0], 'incoming: ' + rec['pair'].split(' -> ')[-1]))
    except Exception as ex: print('provsours png failed', ex, file=sys.stderr)
    return res

if __name__ == '__main__':
    r = make(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else None)
    print(json.dumps(r, indent=1, default=str))
