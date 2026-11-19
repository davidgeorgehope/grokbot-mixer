import sys, json, numpy as np, soundfile as sf, scipy.signal as ss
SRC2 = '/workspace/mixes/src2'
def bands(y, sr):
    out = {}
    for name, lo, hi in (('kick', 30, 150), ('snare', 180, 2500), ('hat', 6000, 14000)):
        sos = ss.butter(4, [lo / (sr / 2), min(hi / (sr / 2), 0.99)], 'band', output='sos'); x = ss.sosfiltfilt(sos, y)
        hop = 256; n = len(x) // hop; e = np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, 1) + 1e-12); le = np.log(e)
        out[name] = np.maximum(np.diff(le, prepend=le[0]), 0)  # onset flux
    return out, sr / 256
def per_bar(yt, b0, b1):
    g = json.load(open(f'{SRC2}/st/{yt}.json')); per = g['per']; bar = 4 * per
    info = sf.info(f'{SRC2}/st/{yt}.wav'); sr = info.samplerate
    y, _ = sf.read(f'{SRC2}/st/{yt}.wav', start=int(b0 * bar * sr), stop=int(b1 * bar * sr)); y = y.mean(1) if y.ndim > 1 else y
    F, fr = bands(y, sr); rows = []
    for k in range(b1 - b0):
        r = {'bar': b0 + k}
        for nm, f in F.items():
            seg = f[int(k * bar * fr):int((k + 1) * bar * fr)]
            if len(seg) < 16: continue
            st16 = np.array_split(seg, 16); s = np.array([x.max() for x in st16])
            thr = max(0.25, np.percentile(f, 90)); r[nm + '_hits'] = int((s > thr).sum())
            r[nm + '_beats'] = [round(float(s[i * 4]), 2) for i in range(4)]  # onset strength on the 4 beats
        rows.append(r)
    return rows
if __name__ == '__main__':
    yt, b0, b1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    for r in per_bar(yt, b0, b1): print(r['bar'], 'kick', r.get('kick_hits'), r.get('kick_beats'), '| snare', r.get('snare_hits'), r.get('snare_beats'), '| hat', r.get('hat_hits'))
