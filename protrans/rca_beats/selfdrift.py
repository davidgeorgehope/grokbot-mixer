"""Track self-consistency: per 8-bar block, lag (ms) of the block's 1-bar onset template (full-band 40-4k onset env, folded per bar on OUR grid)
against the track's reference block (the first drop). A correct, steady grid reads ~0 everywhere; drift or a section with a moved grid shows up."""
import json, sys, numpy as np, librosa
sys.path.insert(0, '/workspace/mixes/protrans'); import score as S
ST = '/workspace/mixes/src2/st'
def run(yid, blk=8, lim_ms=180):
    g = json.load(open(f'{ST}/{yid}.json')); sec = json.load(open(f'{ST}/{yid}.sections.json'))
    y = S._load(f'{ST}/{yid}.wav'); e = S._fine_env(y); fr = S.SR / 32.0; per = g['per']; n = int(round(4 * per * fr))
    downs = g['downs']
    def tmpl(b0, b1):
        P = [e[int(downs[k] * fr): int(downs[k] * fr) + n] for k in range(b0, min(b1, len(downs))) if int(downs[k] * fr) + n <= len(e)]
        return np.mean(P, 0) if P else None
    d1 = sec['drop1']; ref = tmpl(d1, d1 + 16); L = int(lim_ms / 1000 * fr); out = []
    for b0 in range(0, len(downs), blk):
        t = tmpl(b0, b0 + blk)
        if t is None or t.std() == 0: continue
        cc = np.array([np.dot(np.roll(t, -l), ref) for l in range(-L, L + 1)]) / (np.linalg.norm(t) * np.linalg.norm(ref) + 1e-12)
        i = int(np.argmax(cc)); out.append((b0, round((i - L) / fr * 1000, 1), round(float(cc[i]), 2)))
    return out, sec
if __name__ == '__main__':
    for yid in sys.argv[1:]:
        out, sec = run(yid); print(yid, 'drops', sec['drops'])
        print('  ', ' '.join(f"{b}:{l:+.0f}({c})" for b, l, c in out))
