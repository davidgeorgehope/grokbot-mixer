"""Diagnostic only: full-reference closeness of our clip to the pro clip (protrans pairs), after the scorer's alignment.
ViSQOL is not installed on the box, so: mean |log-mel| distance (dB, 64 mel bands, per-clip loudness-normalised) and chroma
cosine distance. Lower = closer to the pro. Never used to keep/reject anything."""
import json, os, sys, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); sys.path.insert(0, P)
import score, librosa
def close(pro, ours):
    yp, yo, _, _ = score.align_ours_to_pro(score._load(pro), score._load(ours)); n = min(len(yp), len(yo)); yp, yo = yp[:n], yo[:n]
    sr = score.SR
    mp = librosa.power_to_db(librosa.feature.melspectrogram(y=yp, sr=sr, n_mels=64) + 1e-10); mo = librosa.power_to_db(librosa.feature.melspectrogram(y=yo, sr=sr, n_mels=64) + 1e-10)
    mp -= np.median(mp); mo -= np.median(mo)
    cp = librosa.feature.chroma_stft(y=yp, sr=sr); co = librosa.feature.chroma_stft(y=yo, sr=sr)
    cos = np.sum(cp*co, 0) / (np.linalg.norm(cp, axis=0)*np.linalg.norm(co, axis=0) + 1e-9)
    return dict(mel_db=round(float(np.mean(np.clip(np.abs(mp - mo), 0, 40))), 2), chroma_dist=round(float(1 - np.mean(cos)), 3))
if __name__ == '__main__':
    import analyze as A, eval_gate as EG
    PR = {r['id']: r for r in EG.pairs() if r['src'] == 'protrans'}; out = {}
    for v in sys.argv[1:]:
        for i, r in A.load(v).items():
            if i in PR and r.get('mp3') and os.path.exists(r['mp3']) and not r.get('error'):
                try: out.setdefault(v, {})[i] = close(PR[i]['pro_clip'], r['mp3'])
                except Exception as ex: out.setdefault(v, {})[i] = dict(error=str(ex)[-100:])
    json.dump(out, open(os.path.join(H, 'melclose.json'), 'w'), indent=1)
    for v, d in out.items():
        ok = [x for x in d.values() if 'mel_db' in x]
        print(v, len(ok), 'mel_db', round(float(np.mean([x['mel_db'] for x in ok])), 2), 'chroma', round(float(np.mean([x['chroma_dist'] for x in ok])), 3))
