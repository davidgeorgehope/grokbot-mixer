"""Per-stem blend card (2026-11-02): one PNG next to every A/B / escalation clip.
Top: log spectrogram of the clip. Then each deck's real lanes from the engine re-render of the saved timing sidecar
(drums = drums+bass stem >150 Hz, bass = stem <=150 Hz, melody/vocals = full minus stem, band-split, estimated), as energy
lanes (dB), with the deck's crossfader gain and low-EQ curves overlaid, plus ib-loop / drum-cut events.
  python3 blend_card.py clip.mp3 [clip.timing.json] [out.png]
publish(src_mp3, dst_mp3, timing) = copy + <dst>.timing.json + <dst>.card.png (never raises; the A/B flow must not die on a card)."""
import os, sys, json, copy, shutil, numpy as np
LANES = [('drums', '#ffaa3c'), ('bass', '#ff4678'), ('melody', '#5ac8ff'), ('vocals', '#aaff8c')]
HOP = 1024
def deck_lanes(tim):  # engine paths are relative to src2
    cwd = os.getcwd(); os.chdir(os.path.dirname(os.path.abspath(__file__)))
    try: return _deck_lanes(tim)
    finally: os.chdir(cwd)

def _deck_lanes(tim):
    old = {k: os.environ.get(k) for k in list(tim.get('env', {})) + ['NUDGE']}
    os.environ.update({k: str(v) for k, v in tim.get('env', {}).items()}); os.environ['NUDGE'] = tim.get('nudge', 'nudge.json')
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import importlib, engine as E
    E.NUDGE = json.load(open(os.environ['NUDGE'])) if os.path.exists(os.environ['NUDGE']) else {}
    import librosa
    try:
        sr, BS, s0 = tim['sr'], tim['bs'], tim['clip_start_bar']; nclip = int(round((tim['clip_end_bar'] - s0) * BS)); out = []
        for dd in tim['decks']:
            tr = E.track(dd['id']); m = [s for s, _ in dd['full_map']]; n = int(round(len(m) * BS))
            dn = copy.deepcopy(dd); dn['auto'] = {k: v for k, v in dd['auto'].items() if k != 'gain'}; dn.pop('echo_out', None)
            full = E.render_deck(dn).mean(1)[:n]
            yb = E._bars(tr, m, tr['st']['beat'], n)
            if dd.get('ib'): yb = yb + E._ib_layer(tr, dd, m, n, None)
            ds = dd.get('dswap')
            if ds:
                w = np.clip((np.arange(n) / BS + dd['start_bar'] - ds['bar']) / max(ds['xf'], 1e-9), 0, 1).astype(np.float32); yb = yb * (1 - w[:, None])
            yb = yb.mean(1)[:len(full)]; res = full[:len(yb)] - yb
            o = int(round((dd['start_bar'] - s0) * BS))
            def place(x):
                z = np.zeros(nclip, np.float32); k = max(0, min(len(x), nclip - o)); z[o:o + k] = x[:k]; return z
            Sb = np.abs(librosa.stft(place(yb), n_fft=4096, hop_length=HOP)); Sr = np.abs(librosa.stft(place(res), n_fft=4096, hop_length=HOP))
            f = librosa.fft_frequencies(sr=sr, n_fft=4096)
            db = lambda S: 10 * np.log10((S ** 2).mean(0) + 1e-10)
            lanes = dict(drums=db(Sb[f > 150]), bass=db(Sb[f <= 150]), melody=db(Sr[(f > 150) & (f < 1000)]), vocals=db(Sr[(f >= 1000) & (f < 4000)]))
            out.append(dict(id=dd['id'], lanes=lanes, auto=dd['auto'], start_bar=dd['start_bar'], nbars=len(m)))
        for k in list(E._cache): E._cache[k]['st'].clear()
        return out
    finally:
        for k, v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

def render_card(mp3, tim, png):
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt, librosa, librosa.display
    dk = deck_lanes(tim); sr, BS, s0, bsec = tim['sr'], tim['bs'], tim['clip_start_bar'], tim['bar_sec']
    nb = tim['clip_end_bar'] - s0
    y, _ = librosa.load(mp3, sr=22050, mono=True)
    fig, ax = plt.subplots(3, 1, figsize=(15, 10), sharex=True, gridspec_kw=dict(height_ratios=[1.3, 2, 2]), facecolor='#0b0c14')
    S = librosa.amplitude_to_db(np.abs(librosa.stft(y, n_fft=2048, hop_length=512)), ref=np.max)
    tb = librosa.frames_to_time(np.arange(S.shape[1]), sr=22050, hop_length=512) / bsec + s0
    fq = librosa.fft_frequencies(sr=22050, n_fft=2048); k = (fq > 25) & (fq < 11000)
    ax[0].pcolormesh(tb, fq[k], S[k], shading='auto', cmap='magma', vmin=-80, vmax=0); ax[0].set_yscale('log'); ax[0].set_ylabel('clip Hz', color='w')
    for i, d in enumerate(dk):
        a = ax[1 + i]; a.set_facecolor('#0b0c14'); t = np.arange(len(d['lanes']['drums'])) * HOP / sr / bsec + s0
        ref = max(np.percentile(v, 99) for v in d['lanes'].values())
        for j, (ln, col) in enumerate(LANES):
            v = np.clip((d['lanes'][ln] - ref + 45) / 45, 0, 1)  # 45 dB range -> lane height
            a.fill_between(t, 3 - j, 3 - j + 0.9 * v, color=col, alpha=0.75, lw=0); a.text(s0 + 0.2, 3 - j + 0.65, ln, color=col, fontsize=8)
        for key, sty, lab in (('gain', '-', 'xfader gain'), ('low', '--', 'low EQ')):
            P = d['auto'].get(key) or []
            if P:
                bx = np.linspace(s0, s0 + nb, 600); g = np.interp(bx, [p[0] for p in P], [p[1] for p in P])
                live = (bx >= d['start_bar']) & (bx < d['start_bar'] + d['nbars']); g = np.where(live, g, np.nan)
                a.plot(bx, g * 4, 'w' + sty, lw=1.4, alpha=0.9, label=lab)
        a.set_ylim(0, 4.2); a.set_yticks([]); a.set_ylabel(('OUT ' if i == 0 else 'IN ') + d['id'], color='w', fontsize=9); a.legend(loc='upper right', fontsize=7, facecolor='#222', labelcolor='w')
    for e in tim.get('events', []):
        for a in ax:
            a.axvspan(e['mix_bar'], e['end_bar'], color='#ffffff' if e['kind'] == 'ib' else '#ff3030', alpha=0.08 if e['kind'] == 'ib' else 0.25)
        ax[0].text(e['mix_bar'], fq[k][-1] * 0.6, e['kind'], color='w', fontsize=8)
    tr = tim['trans']
    for a in ax:
        for b in (tr['start_bar'], tr['end_bar']): a.axvline(b, color='#7f7fff', lw=0.8, ls=':')
        a.tick_params(colors='w')
    ax[-1].set_xlabel('mix bar (blend between dotted lines; red = drum cut, white = incoming beat loop)', color='w')
    fig.suptitle(os.path.basename(mp3) + '  ' + tr.get('tech', '')[:90], color='w', fontsize=10)
    plt.tight_layout(); fig.savefig(png, dpi=72, facecolor=fig.get_facecolor()); plt.close(fig); return png

def sidecars(dst): b = os.path.splitext(dst)[0]; return b + '.timing.json', b + '.card.png'

def publish(src, dst, timing):
    """copy src->dst, write dst's timing sidecar and per-stem card. Returns card path or None (logged, never raises)."""
    shutil.copy(src, dst)
    if not timing: return None
    tj, png = sidecars(dst)
    try:
        dst = os.path.abspath(dst); json.dump(dict(timing, clip=dst), open(tj, 'w')); return render_card(dst, timing, png) if int(os.environ.get('BLEND_CARD', 1)) else None
    except Exception as ex:
        print('blend_card failed', dst, str(ex)[-200:], flush=True); return None

if __name__ == '__main__':
    mp3 = sys.argv[1]; tj = sys.argv[2] if len(sys.argv) > 2 else sidecars(mp3)[0]; out = sys.argv[3] if len(sys.argv) > 3 else sidecars(mp3)[1]
    print(render_card(mp3, json.load(open(tj)), out))
