#!/usr/bin/env python3
"""2026-11-19 EXITPOS (research, flag EXITPOS=1): a structure-based score of WHERE a blend works, replacing the rigid outro-over-intro rule
("play to the very end, incoming drop exactly at the end"). A window = outgoing A leaves at bar e after an overlap of X bars, incoming B
entered at bar ib (B is at ib+X when A is gone). Features (yes/no, from each track's sections only):
  A side, where the outgoing is left:  a_cut (more than 16 bars of A's last drop unplayed), a_tail (A leaves around its last drop's end,
          i.e. the blend sits on the last drop's tail), a_bkdn (A leaves inside a breakdown between drops), a_outro (A leaves mid-outro),
          [reference: A plays to its music end]
  B side, what the incoming is doing:  b_drop_in (B's next drop lands inside the blend), b_drop_after (B's drop comes > 2 bars after A
          is gone, intro plays alone), b_in_drop (B enters already inside a drop), b_in_bkdn (B enters in a breakdown),
          [reference: B's drop lands as A leaves]
Fitted by conditional logit on dev pro windows vs every grid alternative of the same overlap (fit_exitpos_1119.py), leave-one-DJ-out.
Score = utility relative to the rigid reference window."""
import os, json, math
H = os.path.dirname(os.path.abspath(__file__)); W_PATH = os.path.join(H, 'exitpos_w.json')
FEATS = ('a_cut', 'a_tail', 'a_bkdn', 'a_outro', 'b_drop_in', 'b_drop_after', 'b_in_drop', 'b_in_bkdn')
def feats(sa, sb, e, ib, X, me=None):
    dr = sa.get('drops') or []; me = min(me, sa.get('music_end') or sa.get('n_bars')) if me else (sa.get('music_end') or sa.get('n_bars'))  # me: latest exit the engine allows (its fade tail), else music end
    lde = dr[-1][1] if dr else me
    bk = [(dr[k][1], dr[k + 1][0]) for k in range(len(dr) - 1)]
    f = dict.fromkeys(FEATS, 0)
    if e < lde - 16: f['a_cut'] = 1
    if any(x < e <= y for x, y in bk): f['a_bkdn'] = 1; f['a_cut'] = 1 if e < lde - 16 else f['a_cut']
    elif lde - 16 <= e < lde + 8: f['a_tail'] = 1
    elif lde + 8 <= e < me - 8: f['a_outro'] = 1
    dB = sb.get('drops') or []; be = ib + X
    nd = [x for x, y in dB if x >= ib + 0.5]
    if any(x <= ib < y for x, y in dB): f['b_in_drop'] = 1
    elif any(dB[k][1] <= ib < dB[k + 1][0] for k in range(len(dB) - 1)): f['b_in_bkdn'] = 1
    if nd:
        if nd[0] < be - 2: f['b_drop_in'] = 1
        elif nd[0] > be + 2: f['b_drop_after'] = 1
    return f
def util(w, f): return sum(w['coef'].get(k, 0.0) * f[k] for k in FEATS)
_W = {}
def score(a, sa, sb, e, ib, X, path=None, me=None):
    path = path or os.environ.get('EXITPOS_FILE') or W_PATH
    if path not in _W: _W[path] = json.load(open(path))
    W = _W[path]; w = W.get('per_track', {}).get(a) or W['all']
    return util(w, feats(sa, sb, e, ib, X, me)), W['scale']
