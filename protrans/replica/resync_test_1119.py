#!/usr/bin/env python3
"""2026-11-19 day: engine BAR_RESYNC=1 check on named renders. Raw decks (EQ/gain off) rendered with BAR_RESYNC 0 and 1; per-bar
kick offset of each deck vs its own solo template; plus real-blend before/after mp3s and a PNG. usage: resync_test_1119.py KEY [KEY..]"""
import json, os, sys, copy, subprocess, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import deckclash_1119 as D1, deckclash2_1119 as D2, deckdrift_1119 as DD, barsync_demo_1119 as BSD
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
OUT = BSD.OUT
def run(key):
    v, pid = key.split(':', 1); row = next(json.loads(l) for l in open(os.path.join(H, 'gate_ckpt', v + '.jsonl')) if json.loads(l)['id'] == pid)
    os.chdir(D2.SRC2); import blend_diag as BD, engine
    M = json.load(open(row['meta'])); t = M['trans'][0]; s0 = int(t['start_bar']) - BD.PRE; s, e = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0)
    res = dict(key=key); P = {}
    for fl in ('0', '1'):
        os.environ['BAR_RESYNC'] = fl; engine._RESYNC_LOG.clear()
        _, n, ov, pA, pB = BSD.measure(BD, M, s, e); P[fl] = (pA, pB)
        res[f'resync{fl}'] = dict(A=BSD.ov_stats(pA, ov), B=BSD.ov_stats(pB, ov), moved_bars={k: len(x) for k, x in engine._RESYNC_LOG.items()}, log={k: x for k, x in engine._RESYNC_LOG.items()})
        _, A_, B_ = BD.crop_decks(M, 0); y = A_ + B_; pk = np.max(np.abs(y)) + 1e-9; tag = key.replace(':', '__')
        w = os.path.join(OUT, f'{tag}_engine_resync{fl}.wav'); import soundfile as sf; sf.write(w, (y / pk * 0.89).astype(np.float32), D1.SR)
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', w, '-b:a', '192k', w[:-4] + '.mp3'], check=True); os.remove(w)
    os.environ['BAR_RESYNC'] = '0'
    fig, ax = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    for j, fl in enumerate(('0', '1')):
        for P_, col, lab in ((P[fl][0], 'tab:blue', 'deck A (outgoing)'), (P[fl][1], 'tab:orange', 'deck B (incoming)')):
            ax[j].plot([p[0] for p in P_], [p[1] if p[2] >= 0.2 else np.nan for p in P_], 'o-', color=col, label=lab, ms=3)
        ax[j].axvspan(s, e, color='grey', alpha=0.15, label='overlap'); ax[j].axhline(0, color='k', lw=0.5); ax[j].axhspan(-20, 20, color='green', alpha=0.06)
        ax[j].set_ylabel('kick offset vs own template (ms)'); ax[j].set_title(f"{key}: BAR_RESYNC={fl}"); ax[j].legend(fontsize=7)
    ax[1].set_xlabel('bar (crop; green band = +-20 ms)'); fig.tight_layout(); fig.savefig(os.path.join(OUT, f"{key.replace(':', '__')}_engine_resync.png"), dpi=90); plt.close(fig)
    return res
if __name__ == '__main__':
    out = [run(k) for k in sys.argv[1:]]
    for r in out: print(r['key'], 'moved', r['resync1']['moved_bars'], '\n  before A', r['resync0']['A'], 'B', r['resync0']['B'], '\n  after  A', r['resync1']['A'], 'B', r['resync1']['B'])
    json.dump(out, open(os.path.join(H, 'resync_test_1119.json'), 'w'), indent=1, default=float)
