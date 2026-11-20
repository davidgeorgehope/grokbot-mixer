"""Grid-free phase of the drum hits in a delivered clip: circular mean of percussive onset flux at the 174 BPM beat period, per bar
of clip time (arbitrary origin). A-only bars vs B-only bars vs overlap bars: if the decks are offset, the A-only and B-only phases
differ by that offset; in an overlap with both kits, a flam shows as low coherence r or a double peak in the 16th fold."""
import sys, numpy as np, librosa
def env(y, sr, lo, hi, hop=64):
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=hop)); f = librosa.fft_frequencies(sr=sr, n_fft=1024)
    _, P = librosa.decompose.hpss(S, margin=2.0); b = np.log1p(100 * P[(f >= lo) & (f < hi)]).sum(0)
    o = np.maximum(0, np.diff(b, prepend=b[:1])); o = np.maximum(o - np.convolve(o, np.ones(64) / 64, 'same'), 0); return o, hop / sr
def run(p, bpm=174.0, rate=1.0):
    y, sr = librosa.load(p, sr=22050); beat = 60 / bpm / rate; bar = 4 * beat; out = []
    for lo, hi, nm in ((20, 150, 'kick'), (150, 5000, 'snare')):
        o, dt = env(y, sr, lo, hi); t = np.arange(len(o)) * dt
        for k in range(int(t[-1] / bar)):
            m = (t >= k * bar) & (t < (k + 1) * bar); w = o[m]
            z = np.sum(w * np.exp(-2j * np.pi * t[m] / beat)); r = abs(z) / (w.sum() + 1e-9)
            out.append((nm, k, round(float(-np.angle(z) / (2 * np.pi) * beat * 1000), 1), round(float(r), 2), round(float(w.sum()), 1)))
    return out
if __name__ == '__main__':
    for p in sys.argv[1:]:
        res = run(p); print(p)
        for k in range(max(x[1] for x in res) + 1):
            a = [x for x in res if x[1] == k]; print(k, a[0][2:], a[1][2:])
