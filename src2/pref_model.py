"""Blend preference model (2026-11-02): audio embeddings (CLAP laion/larger_clap_music, Apache-2.0; optional MERT-v1-95M, CC BY-NC)
+ a tiny pairwise ranker trained on the listener's A/B picks (weight 3) and pro-set transitions (weight 1). Advisory only: blend_loop uses
it as a small tiebreak AFTER strict tests. Runs in /workspace/venv_clap (transformers); callers fall back to 0.0 if unavailable.
  /workspace/venv_clap/bin/python pref_model.py loo      -> leave-one-out report (eval/pref_loo.json)
  /workspace/venv_clap/bin/python pref_model.py fit      -> eval/pref_model.npz
  /workspace/venv_clap/bin/python pref_model.py score a.mp3 b.mp3 ..."""
import os, sys, json, glob, hashlib, re, numpy as np
R = '/workspace/mixes'; CACHE = f'{R}/eval/emb_cache'; MODEL = f'{R}/eval/pref_model.npz'
W_DAVID, W_PRO = 3.0, 1.0
_m = {}
def _load(path, sr, t0=None, t1=None):  # ffmpeg decode (mp3/m4a/wav), mono float32
    import subprocess
    cmd = ['ffmpeg', '-v', 'error'] + (['-ss', str(t0)] if t0 else []) + ['-i', path] + (['-t', str(t1 - (t0 or 0))] if t1 is not None else []) + ['-ac', '1', '-ar', str(sr), '-f', 'f32le', '-']
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32).copy()
def embed(path, t0=None, t1=None, kind='clap'):
    key = hashlib.md5(f'{os.path.abspath(path)}|{os.path.getmtime(path)}|{t0}|{t1}|{kind}'.encode()).hexdigest()
    f = f'{CACHE}/{key}.npy'
    if os.path.exists(f): return np.load(f)
    import torch
    torch.set_num_threads(int(os.environ.get('EMB_THREADS', 6)))
    if kind == 'clap':
        from transformers import ClapModel, ClapProcessor
        if 'clap' not in _m: _m['clap'] = (ClapModel.from_pretrained('laion/larger_clap_music').eval(), ClapProcessor.from_pretrained('laion/larger_clap_music'))
        M, P = _m['clap']; y = _load(path, 48000, t0, t1); L = 10 * 48000; H = 5 * 48000
        segs = [y[i:i + L] for i in range(0, max(1, len(y) - L + 1), H)] or [y]
        with torch.no_grad():
            x = P(audios=segs, sampling_rate=48000, return_tensors='pt'); e = M.get_audio_features(**x).numpy()
    else:
        from transformers import AutoModel, Wav2Vec2FeatureExtractor
        if 'mert' not in _m: _m['mert'] = (AutoModel.from_pretrained('m-a-p/MERT-v1-95M', trust_remote_code=True).eval(), Wav2Vec2FeatureExtractor.from_pretrained('m-a-p/MERT-v1-95M', trust_remote_code=True))
        M, P = _m['mert']; y = _load(path, 24000, t0, t1); L = 5 * 24000
        segs = [y[i:i + L] for i in range(0, max(1, len(y) - L + 1), L)] or [y]; e = []
        with torch.no_grad():
            for s in segs:
                h = M(**P(s, sampling_rate=24000, return_tensors='pt'), output_hidden_states=True).hidden_states
                e.append(torch.stack(h[4:9]).mean(0).mean(1)[0].numpy())
        e = np.array(e)
    v = e.mean(0); v = v / (np.linalg.norm(v) + 1e-9); np.save(f, v); return v

# ---------- data ----------
def david_pairs():
    """[(group, winner_path, loser_path, weight)] from ratings.jsonl 'ab' rows and daily 1-5 A/B pairs whose clips exist on the box."""
    ab = {e['pair']: e for e in json.load(open(f'{R}/deliver/ab/ab.json'))}; out = []
    daily = {}  # date -> {version: rating, files via log}
    for ln in open(f'{R}/ratings.jsonl'):
        r = json.loads(ln)
        if r.get('source') == 'daily':
            daily.setdefault(r['date'], {})[r['version']] = r['rating']
            continue
        if r.get('type') != 'ab': continue
        f, w, pair = r.get('file', ''), str(r.get('winner', '')), r.get('pair', '')
        wt = W_DAVID * (0.5 if r.get('strength') == 'weak' else 1.0)
        if re.fullmatch(r'deliver/ab/ab\d', f) and pair in ab and w in 'AB':
            e = ab[pair]; out.append((pair, e[w]['file'], e['B' if w == 'A' else 'A']['file'], wt)); continue
        pth = f if f.startswith('/') else f'{R}/{f}'
        if not os.path.exists(pth): continue
        m = re.match(r'(.*_)([A-Z])\.mp3$', pth)
        if m and m.group(2) == w:  # esc_N_B.mp3 style: siblings are the losers
            for q in glob.glob(m.group(1) + '[A-Z].mp3'):
                if q != pth: out.append((pair + '|' + os.path.basename(m.group(1)), pth, q, wt))
        elif os.path.basename(pth).startswith(w):  # bm folder: winner variant vs the other variants
            for q in glob.glob(os.path.join(os.path.dirname(pth), '*.mp3')):
                if q != pth: out.append((pair + '|bm', pth, q, wt))
    # daily 1-5: within each day, higher rating beats lower (ties skipped)
    logs = {}
    if os.path.exists(f'{R}/daily/log.jsonl'):
        for ln in open(f'{R}/daily/log.jsonl'):
            e = json.loads(ln); logs[e.get('date')] = e
    for date, scores in daily.items():
        e = logs.get(date) or {}
        vers = {v['label'].lower().replace(' ', ''): v for v in e.get('versions', [])}
        # also key by version1/version2 from file basename
        by_file = {}
        for v in e.get('versions', []):
            bn = os.path.basename(v.get('file', ''))
            if bn.startswith('version'): by_file[bn.split('.')[0]] = v
        keys = [k for k in scores if k in by_file and os.path.exists(by_file[k]['file'])]
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                ra, rb = scores[a], scores[b]
                if ra == rb: continue
                win, lose = (a, b) if ra > rb else (b, a)
                # weight scales with rating gap (1..4) so a 5-vs-1 counts more than a 3-vs-2
                wt = W_DAVID * (0.5 + 0.5 * min(abs(ra - rb), 4) / 4)
                out.append((f'daily|{date}|{e.get("pair", "")}', by_file[win]['file'], by_file[lose]['file'], wt))
    return out
def pro_clips():
    out = []
    for f in sorted(glob.glob(f'{R}/eval/sets/*.json')):
        d = json.load(open(f)); nm = d['name']; src = f'{R}/pro_sets/{nm}.m4a'
        if not os.path.exists(src): continue  # our own mixes live in eval/sets too; pro = the downloaded sets only
        for t in d['transitions']:
            c = t.get('swap_sec', t['time_sec']); out.append((src, max(0, c - 10), c + 10))
    return out

# ---------- ranker ----------
def fit_w(D, P=None, ours=None, l2=1.0):
    """Linear scorer w: pairwise logistic on the listener's (winner - loser) diffs (weight W_DAVID); pro transitions enter as
    pairs (pro - our clip mean) with weight W_PRO split over all pro clips. Ridge l2. Returns unit-ish w."""
    import torch
    X, wt = [], []
    for a, b, w in D: X.append(a - b); wt.append(w)
    if P is not None and ours is not None and len(P):
        mo = ours.mean(0)
        for p in P: X.append(p - mo); wt.append(W_PRO * 10 / len(P))  # pro clips total weight ~ 10*W_PRO
    X = torch.tensor(np.array(X), dtype=torch.float32); wt = torch.tensor(wt, dtype=torch.float32)
    w = torch.zeros(X.shape[1], requires_grad=True); opt = torch.optim.LBFGS([w], max_iter=200)
    def cl():
        opt.zero_grad(); l = (wt * torch.nn.functional.softplus(-(X @ w))).sum() / wt.sum() + l2 * 1e-2 * (w ** 2).sum(); l.backward(); return l
    opt.step(cl); return w.detach().numpy()

def loo(kind='clap'):
    D = david_pairs(); groups = sorted(set(g for g, *_ in D))
    E = {p: embed(p, kind=kind) for _, a, b, _ in D for p in (a, b)}
    P = np.array([embed(s, t0, t1, kind=kind) for s, t0, t1 in pro_clips()])
    ours = np.array(list(E.values()))
    res = {}
    for name, use_pro, use_david in [('pro_only', True, False), ('david_only', False, True), ('david+pro', True, True)]:
        hits = []
        for g in groups:
            tr = [(E[a], E[b], w) for gg, a, b, w in D if gg != g] if use_david else []
            w = fit_w(tr, P if use_pro else None, ours)
            te = [(E[a] @ w - E[b] @ w) for gg, a, b, _ in D if gg == g]
            hits.append(dict(group=g, pairs=len(te), correct=int(sum(x > 0 for x in te)), margin=float(np.mean(te))))
        c = sum(h['correct'] for h in hits); n = sum(h['pairs'] for h in hits)
        gc = sum(h['correct'] * 2 > h['pairs'] for h in hits)
        res[name] = dict(pair_acc=f'{c}/{n}', group_acc=f'{gc}/{len(hits)}', groups=hits)
    if kind == 'clap':  # zero-shot text baseline
        from transformers import ClapModel, ClapProcessor
        import torch
        if 'clap' not in _m: _m['clap'] = (ClapModel.from_pretrained('laion/larger_clap_music').eval(), ClapProcessor.from_pretrained('laion/larger_clap_music'))
        M, Pp = _m['clap']
        with torch.no_grad():
            t = M.get_text_features(**Pp(text=['a smooth seamless drum and bass DJ transition', 'a messy clashing DJ transition with tracks fighting'], return_tensors='pt', padding=True)).numpy()
        t = t / np.linalg.norm(t, axis=1, keepdims=True); d = t[0] - t[1]
        te = [(E[a] - E[b]) @ d for _, a, b, _ in D]; res['zero_shot_text'] = dict(pair_acc=f'{sum(x > 0 for x in te)}/{len(te)}')
    return dict(kind=kind, n_pairs=len(D), n_groups=len(groups), n_pro=len(P), results=res)

def fit_save(kind='clap'):
    D = david_pairs(); E = {p: embed(p, kind=kind) for _, a, b, _ in D for p in (a, b)}
    P = np.array([embed(s, t0, t1, kind=kind) for s, t0, t1 in pro_clips()])
    w = fit_w([(E[a], E[b], wt) for _, a, b, wt in D], P, np.array(list(E.values())))
    np.savez(MODEL, w=w, kind=kind, n_pairs=len(D), n_pro=len(P)); return w

def score(paths):
    if not os.path.exists(MODEL): return {p: 0.0 for p in paths}
    z = np.load(MODEL); w = z['w']; return {p: float(embed(p, kind=str(z['kind'])) @ w) for p in paths}

if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'loo':
        out = [loo('clap')] + ([loo('mert')] if os.environ.get('MERT', '1') == '1' else [])
        json.dump(out, open(f'{R}/eval/pref_loo.json', 'w'), indent=1)
        for o in out: print(o['kind'], o['n_pairs'], 'pairs', o['n_groups'], 'groups', o['n_pro'], 'pro', {k: (v['pair_acc'], v.get('group_acc')) for k, v in o['results'].items()})
    elif c == 'fit': print(fit_save(sys.argv[2] if len(sys.argv) > 2 else 'clap').shape)
    elif c == 'score': print(json.dumps(score(sys.argv[2:]), indent=1))
