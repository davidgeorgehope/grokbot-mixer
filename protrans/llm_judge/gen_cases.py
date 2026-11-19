"""Build labelled judge cases from existing renders (2026-11-18 LLM-judge pilot). Generate-only: reads rules.json never.
For each rendered default blend in replica/gate_ckpt (meta still in /tmp/protrans_bench) it writes
  cases/<id>__clean.png            the standard blend_diag figure of the real render, with exact hardcheck.check results
  cases/<id>__inj_<defect>.png     the same render with ONE known defect injected into the deck audio (ground truth by construction)
Injections: beat_clash = incoming deck delayed 110 ms; bass_hole = both decks' <150 Hz cut ~50 dB for 6 bars mid-blend;
level_pump = both decks -10 dB full band for 1 bar mid-blend. Hard checks are re-run on the injected decks (same code).
usage: python3 gen_cases.py [max_pairs]"""
import json, os, sys, hashlib, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); SRC2 = os.path.join(os.path.dirname(P), 'src2')
for p in (P, SRC2, os.path.join(P, 'replica')):
    if p not in sys.path: sys.path.insert(0, p)
os.chdir(SRC2)
import blend_diag as BD, hardcheck as HC
from engine import BS
OUT = os.path.join(H, 'cases'); os.makedirs(OUT, exist_ok=True)
DEFECTS = ['beat_clash', 'bass_hole', 'level_pump']
SR = 44100

def lows_cut(y, db=50.0, fc=150.0):
    Y = np.fft.rfft(y, axis=0); f = np.fft.rfftfreq(len(y), 1 / SR); g = np.ones_like(f); g[f < fc] = 10 ** (-db / 20)
    return np.fft.irfft(Y * g[:, None], n=len(y), axis=0).astype(np.float32)

def inject(kind, s0, A, B, s, e):
    A, B = A.copy(), B.copy(); mid = int((s + e) / 2 - s0)
    if kind == 'beat_clash':
        k = int(0.110 * SR); B = np.concatenate([np.zeros((k, 2), np.float32), B[:-k]])
    elif kind == 'bass_hole':
        i0, i1 = int((mid - 3) * BS), int((mid + 3) * BS)
        A[i0:i1] = lows_cut(A[i0:i1]); B[i0:i1] = lows_cut(B[i0:i1])
    elif kind == 'level_pump':
        i0, i1 = int(mid * BS), int((mid + 1) * BS); A[i0:i1] *= 10 ** (-10 / 20); B[i0:i1] *= 10 ** (-10 / 20)
    return A, B

def split_of(pid):  # whole pairs stay in one split; ~1/3 held out
    return 'heldout' if int(hashlib.md5(pid.encode()).hexdigest(), 16) % 3 == 0 else 'dev'

def main(maxn=99):
    rows = [json.loads(l) for l in open(os.path.join(P, 'replica', 'gate_ckpt', 'default.jsonl'))]
    rows = [r for r in rows if r.get('meta') and os.path.exists(r['meta'])][:maxn]
    man = os.path.join(H, 'cases.jsonl'); done = set()
    if os.path.exists(man): done = {json.loads(l)['case'] for l in open(man)}
    orig = BD.crop_decks
    for n, r in enumerate(rows):
        pid = r['id']; M = json.load(open(r['meta'])); t = M['trans'][0]; s, e = float(t['start_bar']), float(t['end_bar'])
        kind = DEFECTS[n % 3]; want = [('clean', None), ('inj_' + kind, kind)]
        if all(f'{pid}__{c}' in done for c, _ in want): continue
        s0, A, B = orig(M, 0)
        for cname, k in want:
            case = f'{pid}__{cname}'
            if case in done: continue
            AA, BB = (A, B) if k is None else inject(k, s0, A, B, s, e)
            BD.crop_decks = lambda M_, i_, pre=BD.PRE, post=BD.POST, _r=(s0, AA, BB): _r
            try:
                png = os.path.join(OUT, case + '.png'); hc = HC.check(r['meta'], png=png, title='blend')
            finally:
                BD.crop_decks = orig
            truth = {d: False for d in DEFECTS}
            if k: truth[k] = True
            rec = dict(case=case, pair=pid, split=split_of(pid), source='injected' if k else 'real_render', png=png,
                       truth=truth, truth_basis='injection' if k else 'hardcheck (real render, no human label)',
                       hard={kk: hc[kk] for kk in ('beat_clash', 'bass_hole', 'pumping', 'lows_dip_db', 'pump_db', 'residual_lag_ms')})
            if not k:  # real render: hard checks are the only label
                rec['truth'] = dict(beat_clash=hc['beat_clash'], bass_hole=hc['bass_hole'], level_pump=hc['pumping'])
            open(man, 'a').write(json.dumps(rec, default=float) + '\n'); print(case, rec['hard'], flush=True)

if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 99)
