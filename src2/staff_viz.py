"""Light-up sheet-music visualizer for a blend clip.
Two staff groups (outgoing top, incoming bottom), lanes drums/bass/melody/vocals.
Drums+bass come from the engine dnb stem (st/<id>.dnb.wav); melody/vocals are the
residual (full - dnb) band-split, i.e. estimated. Deck brightness follows the xfader.
usage: python3 staff_viz.py CLIP.mp3 OUT.mp4 --meta m06v2_meta.json --trans 8 --clip-start 1555 --dur 50
"""
import argparse, json, os, subprocess, numpy as np, librosa
from PIL import Image, ImageDraw, ImageFilter
SR, HOP = 22050, 512
W, H, FPS = 1280, 720, 25
LANES = [("drums", (255, 170, 60)), ("bass", (255, 70, 120)), ("melody", (90, 200, 255)), ("vocals", (170, 255, 140))]
WIN_PAST, WIN_FUT, PLAY_X = 3.0, 5.0, 0.32

def lane_events(tid, stdir):
    full, _ = librosa.load(f"{stdir}/{tid}.wav", sr=SR, mono=True)
    dnb_p = f"{stdir}/{tid}.dnb.wav"
    dnb, _ = librosa.load(dnb_p, sr=SR, mono=True)
    n = min(len(full), len(dnb)); full, dnb = full[:n], dnb[:n]
    D = np.abs(librosa.stft(dnb, hop_length=HOP)); R = np.abs(librosa.stft(full - dnb, hop_length=HOP))
    f = librosa.fft_frequencies(sr=SR)
    Rh, _ = librosa.decompose.hpss(R)
    bands = {"drums": D[f > 150], "bass": D[f <= 150], "melody": Rh[(f > 150) & (f < 1000)], "vocals": Rh[(f >= 1000) & (f < 4000)]}
    ev = {}
    for k, S in bands.items():
        env = librosa.onset.onset_strength(S=librosa.amplitude_to_db(S, ref=np.max), sr=SR, hop_length=HOP)
        on = librosa.onset.onset_detect(onset_envelope=env, sr=SR, hop_length=HOP, units="frames", backtrack=False)
        rms = np.sqrt((S ** 2).mean(0)); lv = rms / (np.percentile(rms, 98) + 1e-9)
        sub = S[:, on]; pos = (sub * np.arange(S.shape[0])[:, None]).sum(0) / (sub.sum(0) + 1e-9) / S.shape[0]
        ev[k] = np.c_[librosa.frames_to_time(on, sr=SR, hop_length=HOP), np.clip(lv[on], 0, 1.2), np.clip(pos, 0, 1)]
    return ev

def to_mix(ev, deck, beats, bar_sec):
    out = {}
    for k, e in ev.items():
        rows = []
        for i, (tb, _) in enumerate(deck["full_map"]):
            if 4 * tb + 4 >= len(beats): continue
            t0, t1 = beats[4 * tb], beats[4 * tb + 4]
            m = (e[:, 0] >= t0) & (e[:, 0] < t1)
            for t, lv, p in e[m]:
                rows.append(((deck["start_bar"] + i + (t - t0) / (t1 - t0)) * bar_sec, lv, p))
        out[k] = np.array(rows).reshape(-1, 3)
    return out

HOPT = 256  # timing-mode hop at 44.1k (5.8 ms)
def _events_from(S, f, sr):
    env = librosa.onset.onset_strength(S=librosa.amplitude_to_db(S, ref=np.max), sr=sr, hop_length=HOPT)
    on = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=HOPT, units="frames")
    rms = np.sqrt((S ** 2).mean(0)); lv = rms / (np.percentile(rms, 98) + 1e-9)
    sub = S[:, on]; pos = (sub * np.arange(S.shape[0])[:, None]).sum(0) / (sub.sum(0) + 1e-9) / max(S.shape[0], 1)
    return np.c_[librosa.frames_to_time(on, sr=sr, hop_length=HOPT), np.clip(lv[on], 0, 1.2), np.clip(pos, 0, 1)]

def timing_lanes(tim):
    """Exact lanes from the A/B timing sidecar: re-render each deck with the engine (same map, ib loop, dswap),
    times in clip seconds (clip sample 0 = mix bar clip_start_bar). Returns per deck: lane events, gain fn, ib window."""
    os.environ["NUDGE"] = tim["nudge"]; import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import copy, engine as E
    sr, BS, s0 = tim["sr"], tim["bs"], tim["clip_start_bar"]; out = []
    for dd in tim["decks"]:
        tr = E.track(dd["id"]); m = [s for s, _ in dd["full_map"]]; n = int(round(len(m) * BS))
        dn = copy.deepcopy(dd); dn["auto"] = {k: v for k, v in dd["auto"].items() if k != "gain"}
        full = E.render_deck(dn).mean(1)
        yb = E._bars(tr, m, tr["st"]["beat"], n)
        if dd.get("ib"): yb = yb + E._ib_layer(tr, dd, m, n, None)
        ds = dd.get("dswap")
        if ds:
            w = np.clip((np.arange(n) / BS + dd["start_bar"] - ds["bar"]) / max(ds["xf"], 1e-9), 0, 1).astype(np.float32); yb = yb * (1 - w[:, None])
        yb = yb.mean(1)[: len(full)]; res = full[: len(yb)] - yb
        D = np.abs(librosa.stft(yb, n_fft=2048, hop_length=HOPT)); Rh, _ = librosa.decompose.hpss(np.abs(librosa.stft(res, n_fft=2048, hop_length=HOPT)))
        f = librosa.fft_frequencies(sr=sr, n_fft=2048); off = (dd["start_bar"] - s0) * BS / sr
        ev = {k: _events_from(S, f, sr) for k, S in {"drums": D[f > 150], "bass": D[f <= 150], "melody": Rh[(f > 150) & (f < 1000)], "vocals": Rh[(f >= 1000) & (f < 4000)]}.items()}
        for e in ev.values(): e[:, 0] += off
        pts = dd["auto"].get("gain") or [[0, 1], [1e9, 1]]; low = dd["auto"].get("low") or [[0, 1], [1e9, 1]]
        bar = lambda t: s0 + t * sr / BS
        g = (lambda P: lambda t: float(np.interp(bar(t), [p[0] for p in P], [p[1] for p in P], left=0 if P[0][1] > 0.5 and False else P[0][1], right=P[-1][1])))
        ib = dd.get("ib"); ibw = ((dd["start_bar"] + ib["k0"] - s0) * BS / sr, (dd["start_bar"] + ib["k1"] - s0) * BS / sr) if ib else None
        live = ((dd["start_bar"] - s0) * BS / sr, (dd["start_bar"] - s0 + len(m)) * BS / sr)
        gg, gl = g(pts), g(low)
        out.append(dict(ev=ev, gain=lambda t, gg=gg, live=live: gg(t) if live[0] <= t < live[1] else 0.0, low=gl, ib=ibw, id=dd["id"]))
    return out

def measure_sync(clip, drum_times, dur):
    """Offset (ms) between drum dots and an onset detection of the clip audio: lag maximizing the onset envelope summed at the dots."""
    y, sr = librosa.load(clip, sr=44100, mono=True, duration=dur)
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOPT); fr = librosa.frames_to_time(np.arange(len(env)), sr=sr, hop_length=HOPT)
    lags = np.arange(-0.2, 0.2001, 0.001); sc = [np.interp(drum_times + l, fr, env).sum() for l in lags]
    return 1000 * lags[int(np.argmax(sc))]

def gains(tr, bar_sec, t):
    xb = np.array(tr["xfader"]); b = t / bar_sec
    x = np.interp(b, xb[:, 0], xb[:, 1], left=0, right=1)
    return np.cos(x * np.pi / 2), np.sin(x * np.pi / 2)

def persp(x, y):  # slight perspective: far (top) narrower
    s = 0.82 + 0.18 * (y / H); return W / 2 + (x - W / 2) * s, 60 + y * 0.9

def lane_geom():
    g = []
    for d in range(2):
        top = 30 + d * 345
        for j in range(4): g.append((d, j, top + j * 80, top + j * 80 + 56))
    return g

def background():
    im = Image.new("RGB", (W, H), (8, 9, 16)); dr = ImageDraw.Draw(im)
    for d, j, y0, y1 in lane_geom():
        for k in range(5):
            y = y0 + k * (y1 - y0) / 4
            dr.line([persp(0, y), persp(W, y)], fill=(48, 52, 70), width=1)
        dr.text(persp(8, y0 - 12), f"{'OUT' if d == 0 else 'IN '} {LANES[j][0]}", fill=(110, 115, 140))
    return np.asarray(im).astype(np.float32)

def align_lag(clip, mixev, t0, dur):
    y, _ = librosa.load(clip, sr=SR, mono=True, duration=dur)
    env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP); fr = librosa.frames_to_time(np.arange(len(env)), sr=SR, hop_length=HOP)
    best = (0, -1)
    for lag in np.arange(-4, 4, 0.01):
        s = 0
        for dk in mixev:
            e = dk["drums"]; tt = e[:, 0] - t0 + lag; m = (tt > 0) & (tt < dur)
            s += np.interp(tt[m], fr, env).sum()
        best = max(best, (s, lag), key=lambda z: z[0]) if best[1] != -1 else (s, lag)
    return best[1]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("clip"); ap.add_argument("out")
    ap.add_argument("--meta"); ap.add_argument("--trans", type=int)
    ap.add_argument("--clip-start", type=float, default=0); ap.add_argument("--dur", type=float, default=50)
    ap.add_argument("--st", default=os.path.join(os.path.dirname(__file__), "st")); ap.add_argument("--still-at", type=float, default=None)
    ap.add_argument("--flyover", action="store_true"); ap.add_argument("--v1plus", action="store_true"); ap.add_argument("--hd", action="store_true")
    a = ap.parse_args()
    tj = os.path.splitext(a.clip)[0] + ".timing.json"
    if os.path.exists(tj) and a.v1plus:
        return main_v1plus(a, json.load(open(tj)))
    if os.path.exists(tj) and a.flyover:
        return main_flyover(a, json.load(open(tj)))
    if os.path.exists(tj):
        return main_timing(a, json.load(open(tj)))
    m = json.load(open(a.meta)); tr = m["trans"][a.trans]; bs = m["bar_sec"]
    decks = [next(d for d in m["decks"] if d["id"] == tr[k]) for k in ("a", "b")]
    mixev = []
    for d in decks:
        beats = np.array(json.load(open(f"{a.st}/{d['id']}.json"))["beats"])
        mixev.append(to_mix(lane_events(d["id"], a.st), d, beats, bs))
    lag = align_lag(a.clip, mixev, a.clip_start, a.dur); print("align lag s", round(lag, 2))
    bg = background(); geo = lane_geom(); px = (WIN_PAST + WIN_FUT) / W
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-t", str(a.dur), "-i", a.clip, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", a.out], stdin=subprocess.PIPE)
    still_f = int((a.still_at if a.still_at is not None else a.dur / 2) * FPS)
    for fi in range(int(a.dur * FPS)):
        tc = fi / FPS; tm = a.clip_start + tc - lag
        go, gi = gains(tr, bs, tm); g = (go, gi)
        glow = Image.new("RGB", (W, H)); core = Image.new("RGB", (W, H)); dg, dc = ImageDraw.Draw(glow), ImageDraw.Draw(core)
        for d, j, y0, y1 in geo:
            e = mixev[d][LANES[j][0]]; m_ = (e[:, 0] > tm - WIN_PAST) & (e[:, 0] < tm + WIN_FUT)
            col = np.array(LANES[j][1])
            for t, lv, p in e[m_]:
                x = W * PLAY_X + (t - tm) / px; y = y1 - p * (y1 - y0)
                X, Y = persp(x, y)
                age = tm - t
                b = (0.18 if age < 0 else 0.25 + 1.6 * np.exp(-age / 0.35)) * (0.35 + 0.65 * min(lv, 1)) * (0.12 + 0.88 * g[d])
                r = 2 + 3 * min(lv, 1) + (4 * np.exp(-age / 0.25) if age >= 0 else 0)
                c = tuple(int(v) for v in np.clip(col * b, 0, 255))
                dg.ellipse([X - r * 2.2, Y - r * 2.2, X + r * 2.2, Y + r * 2.2], fill=c); dc.ellipse([X - r, Y - r, X + r, Y + r], fill=c)
        dim = np.ones((H, 1, 1), np.float32); dim[:360] = 0.45 + 0.55 * go; dim[360:] = 0.45 + 0.55 * gi
        fr = bg * dim + np.asarray(glow.filter(ImageFilter.GaussianBlur(9)), np.float32) * 1.4 + np.asarray(core, np.float32)
        X0, _ = persp(W * PLAY_X, 0); X1, _ = persp(W * PLAY_X, H)
        img = Image.fromarray(np.clip(fr, 0, 255).astype(np.uint8)); dr = ImageDraw.Draw(img)
        dr.line([(X0, 50), (X1, H - 10)], fill=(200, 200, 220), width=1)
        dr.text((W - 260, 8), f"OUT {go:.2f}  IN {gi:.2f}   bar {tm / bs:.1f}", fill=(160, 165, 190))
        if fi == still_f: img.save(os.path.splitext(a.out)[0] + ".png")
        ff.stdin.write(img.tobytes())
    ff.stdin.close(); ff.wait()

def main_timing(a, tim):
    decks = timing_lanes(tim); bs = tim["bar_sec"]; s0 = tim["clip_start_bar"]
    drums = np.concatenate([d["ev"]["drums"][:, 0][[d["gain"](t) > 0.3 for t in d["ev"]["drums"][:, 0]]] for d in decks])
    drums = drums[(drums > 0.2) & (drums < a.dur - 0.2)]
    off = measure_sync(a.clip, drums, a.dur); print(f"sync offset (dots vs clip onsets): {off:+.0f} ms over {len(drums)} drum dots", flush=True)
    evtxt = [(e["kind"], (e["mix_bar"] - s0) * bs, (e["end_bar"] - s0) * bs) for e in tim["events"]]
    bg = background(); geo = lane_geom(); px = (WIN_PAST + WIN_FUT) / W
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-t", str(a.dur), "-i", a.clip, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", a.out], stdin=subprocess.PIPE)
    still_f = int((a.still_at if a.still_at is not None else a.dur / 2) * FPS)
    for fi in range(int(a.dur * FPS)):
        tm = fi / FPS; g = [d["gain"](tm) for d in decks]
        glow = Image.new("RGB", (W, H)); core = Image.new("RGB", (W, H)); dg, dc = ImageDraw.Draw(glow), ImageDraw.Draw(core)
        for d, j, y0, y1 in geo:
            dk = decks[d]; lane = LANES[j][0]; e = dk["ev"][lane]; m_ = (e[:, 0] > tm - WIN_PAST) & (e[:, 0] < tm + WIN_FUT); col = np.array(LANES[j][1])
            for t, lv, p in e[m_]:
                gt = dk["gain"](t) * (dk["low"](t) if lane == "bass" else 1)
                if gt < 0.02: continue
                x = W * PLAY_X + (t - tm) / px; y = y1 - p * (y1 - y0); X, Y = persp(x, y); age = tm - t
                b = (0.18 if age < 0 else 0.25 + 1.6 * np.exp(-age / 0.35)) * (0.35 + 0.65 * min(lv, 1)) * (0.12 + 0.88 * gt)
                r = 2 + 3 * min(lv, 1) + (4 * np.exp(-age / 0.25) if age >= 0 else 0)
                c = tuple(int(v) for v in np.clip(col * b, 0, 255))
                dg.ellipse([X - r * 2.2, Y - r * 2.2, X + r * 2.2, Y + r * 2.2], fill=c); dc.ellipse([X - r, Y - r, X + r, Y + r], fill=c)
                if dk["ib"] and lane in ("drums", "bass") and dk["ib"][0] <= t < dk["ib"][1]:  # ib loop hits: white ring
                    q = int(200 * min(1, b)); dc.ellipse([X - r - 3, Y - r - 3, X + r + 3, Y + r + 3], outline=(q, q, q))
        dim = np.ones((H, 1, 1), np.float32); dim[:360] = 0.45 + 0.55 * g[0]; dim[360:] = 0.45 + 0.55 * g[1]
        fr = bg * dim + np.asarray(glow.filter(ImageFilter.GaussianBlur(9)), np.float32) * 1.4 + np.asarray(core, np.float32)
        img = Image.fromarray(np.clip(fr, 0, 255).astype(np.uint8)); dr = ImageDraw.Draw(img)
        X0, _ = persp(W * PLAY_X, 0); X1, _ = persp(W * PLAY_X, H); dr.line([(X0, 50), (X1, H - 10)], fill=(200, 200, 220), width=1)
        lab = [k.upper() + (" loop (IN beat)" if k == "ib" else " cut (OUT beat)") for k, t0, t1 in evtxt if t0 <= tm < t1 + 1]
        dr.text((W - 330, 8), f"OUT {g[0]:.2f}  IN {g[1]:.2f}   bar {s0 + tm / bs:.1f}  " + "  ".join(lab), fill=(170, 175, 200))
        if fi == still_f: img.save(os.path.splitext(a.out)[0] + ".png")
        ff.stdin.write(img.tobytes())
    ff.stdin.close(); ff.wait()


# ---------------- 3D flyover (numpy perspective camera) ----------------
def _ss(x):  # smoothstep, eased 0..1
    x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)

class Flyover:
    """Staves as a lit plane z=0 in world space: x = time (KX units/s), y = lane. Camera does a low flyover following the
    playhead; music-driven moves, all smooth: cumulative 90-degree yaw eased across each transition, crane/pull-up bump on
    drops (cut, incoming real drums), slow orbit drift in breakdowns (low drum density), zoom pulse + small shake on kicks,
    roll banks with yaw rate. Depth fog, bloom on dots, light trail behind the playhead."""
    KX, LW, NL = 2.2, 0.9, 5
    def __init__(s, decks, tim, dur, W=1280, H=720):
        s.d, s.W, s.H, s.dur = decks, W, H, dur
        bs, s0 = tim["bar_sec"], tim["clip_start_bar"]; tr = tim["trans"]
        s.trans = [((tr["start_bar"] - s0) * bs, (tr["end_bar"] - s0) * bs)]
        s.drops = [(e["mix_bar"] - s0) * bs for e in tim["events"] if e["kind"] == "dswap"] + [(e["end_bar"] - s0) * bs for e in tim["events"] if e["kind"] == "ib"]
        tg = np.arange(0, dur + 1, 0.01); s.tg = tg
        K = np.zeros_like(tg); dens = np.zeros_like(tg)
        for dk in decks:
            for t, lv, _ in dk["ev"]["drums"]:
                g = dk["gain"](t)
                if g < 0.3: continue
                i = int(t / 0.01)
                if 0 <= i < len(tg): K[i] += lv * g; dens[i] += 1
        a = np.exp(-0.01 / 0.13); kk = np.zeros_like(K); acc = 0.0
        for i, v in enumerate(K): acc = acc * a + v; kk[i] = acc
        att = np.convolve(kk, np.ones(3) / 3, "same")  # ~30 ms attack smoothing: no jerk
        s.kick = att / (np.percentile(att, 99) + 1e-9)
        w = np.exp(-np.linspace(-3, 3, 401) ** 2); w /= w.sum()  # ~2 s window
        dn = np.convolve(dens, w, "same"); s.brk = _ss(1 - dn / (np.percentile(dn, 90) + 1e-9) * 1.4)
        s.brk = np.convolve(s.brk, w, "same")
        # lanes y positions (OUT group then IN group)
        s.lane_y = []
        for d in range(2):
            for j in range(4): s.lane_y.append((d, j, (d * 4.6 + j * 1.05) - 4.0))
    def _at(s, arr, t): return float(np.interp(t, s.tg, arr))
    def cam(s, t):
        yaw = sum(np.pi / 2 * _ss((t - a) / (b - a)) for a, b in s.trans)
        dyaw = sum(np.pi / 2 * (_ss((t + 0.05 - a) / (b - a)) - _ss((t - 0.05 - a) / (b - a))) / 0.1 for a, b in s.trans)
        crane = sum(np.exp(-0.5 * ((t - dt - 0.6) / 1.1) ** 2) for dt in s.drops)  # smooth pull-up around each drop
        brk = s._at(s.brk, t); k = s._at(s.kick, t)
        px = t * s.KX
        dist = 6.5 + 2.0 * crane + 1.5 * brk
        h = 1.7 + 2.6 * crane + 0.8 * brk + 0.3 * np.sin(t * 0.21)
        orbit = yaw + 0.35 * brk * np.sin(t * 0.17) + 0.08 * np.sin(t * 0.07)
        tgt = np.array([px + 1.8 * np.cos(orbit), 0.6 * np.sin(t * 0.11), 0.0])
        eye = tgt - dist * np.array([np.cos(orbit), np.sin(orbit), 0]) + np.array([0, 0, h])
        sh = 0.035 * k * np.array([np.sin(t * 37.0), np.sin(t * 29.0 + 1), np.sin(t * 23.0 + 2)])  # smooth, small
        eye = eye + sh; roll = float(np.clip(-0.35 * dyaw, -0.25, 0.25)) + 0.01 * k * np.sin(t * 31)
        fov = 1.05 / (1 + 0.035 * k)
        f = tgt - eye; f /= np.linalg.norm(f); r = np.cross(f, [0, 0, 1.0]); r /= np.linalg.norm(r); u = np.cross(r, f)
        cr, sr_ = np.cos(roll), np.sin(roll); r, u = cr * r + sr_ * u, -sr_ * r + cr * u
        return eye, f, r, u, s.W / 2 / np.tan(fov / 2)
    def proj(s, P, C):
        eye, f, r, u, foc = C; v = P - eye; z = v @ f
        x = s.W / 2 + foc * (v @ r) / np.maximum(z, 1e-3); y = s.H / 2 - foc * (v @ u) / np.maximum(z, 1e-3)
        return x, y, z
    def frame(s, t):
        C = s.cam(t); W, H = s.W, s.H; fogd = 16.0
        base = Image.new("RGB", (W, H), (6, 7, 14)); dr = ImageDraw.Draw(base)
        gl = Image.new("RGB", (W // 2, H // 2)); dg = ImageDraw.Draw(gl)
        t0, t1 = t - 9, t + 14; xs = np.linspace(t0 * s.KX, t1 * s.KX, 48)
        g = [dk["gain"](t) for dk in s.d]
        for d, j, yc in s.lane_y:  # staff lines, fogged segments, lit by deck gain
            lit = 0.35 + 0.65 * g[d]
            for k in range(s.NL):
                yy = yc + (k - 2) * s.LW / 4
                P = np.c_[xs, np.full_like(xs, yy), np.zeros_like(xs)]; x, y, z = s.proj(P, C)
                for i in range(len(xs) - 1):
                    if z[i] < 0.3 or z[i + 1] < 0.3: continue
                    fo = np.exp(-z[i] / fogd) * lit; c = (int(70 * fo), int(78 * fo), int(110 * fo))
                    dr.line([(x[i], y[i]), (x[i + 1], y[i + 1])], fill=c, width=1)
        # playhead + light trail
        for k, a in enumerate(np.linspace(0, 1.2, 9)):
            xx = (t - a) * s.KX; ys = np.linspace(-4.6, 5.0, 20)
            x, y, z = s.proj(np.c_[np.full_like(ys, xx), ys, np.full_like(ys, 0.02)], C)
            q = np.exp(-a / 0.4)
            for i in range(len(ys) - 1):
                if z[i] < 0.3 or z[i + 1] < 0.3: continue
                fo = np.exp(-z[i] / fogd) * q; c = (int(220 * fo), int(225 * fo), int(255 * fo))
                (dr if k == 0 else dg).line([(x[i] / (1 if k == 0 else 2), y[i] / (1 if k == 0 else 2)), (x[i + 1] / (1 if k == 0 else 2), y[i + 1] / (1 if k == 0 else 2))], fill=c, width=1 if k == 0 else 3)
        # dots
        for d, j, yc in s.lane_y:
            dk = s.d[d]; lane = LANES[j][0]; e = dk["ev"][lane]; m = (e[:, 0] > t0) & (e[:, 0] < t1)
            if not m.any(): continue
            E_ = e[m]; P = np.c_[E_[:, 0] * s.KX, yc + (E_[:, 2] - 0.5) * s.LW, np.full(len(E_), 0.03)]; x, y, z = s.proj(P, C)
            col = np.array(LANES[j][1])
            for (te, lv, _), X, Y, Z in sorted(zip(E_, x, y, z), key=lambda q: (q[0][0] <= t, -q[3])):  # future/far first, lit hits on top
                if Z < 0.4 or not (-50 < X < W + 50 and -50 < Y < H + 50): continue
                gt = dk["gain"](te) * (dk["low"](te) if lane == "bass" else 1)
                if gt < 0.02: continue
                age = t - te
                b = (0.2 if age < 0 else 0.3 + 1.7 * np.exp(-age / 0.35)) * (0.35 + 0.65 * min(lv, 1)) * (0.12 + 0.88 * gt) * np.exp(-Z / fogd)
                rr = (0.05 + 0.05 * min(lv, 1) + (0.08 * np.exp(-age / 0.25) if age >= 0 else 0)) * C[4] / Z
                rr = float(np.clip(rr, 1, 22)); c = tuple(int(v) for v in np.clip(col * b, 0, 255))
                dr.ellipse([X - rr, Y - rr, X + rr, Y + rr], fill=c)
                dg.ellipse([(X - rr * 2.4) / 2, (Y - rr * 2.4) / 2, (X + rr * 2.4) / 2, (Y + rr * 2.4) / 2], fill=c)
                if dk["ib"] and lane in ("drums", "bass") and dk["ib"][0] <= te < dk["ib"][1]:
                    q = int(210 * min(1, b)); dr.ellipse([X - rr - 2, Y - rr - 2, X + rr + 2, Y + rr + 2], outline=(q, q, q))
        bloom = gl.filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BILINEAR)
        fr = np.asarray(base, np.float32) + 1.5 * np.asarray(bloom, np.float32)
        vy = np.linspace(-1, 1, H)[:, None]; vx = np.linspace(-1, 1, W)[None, :]
        return np.clip(fr * (1 - 0.35 * (vx ** 2 + vy ** 2) / 2)[:, :, None], 0, 255).astype(np.uint8)

def main_flyover(a, tim):
    import time
    decks = timing_lanes(tim)
    drums = np.concatenate([d["ev"]["drums"][:, 0][[d["gain"](t) > 0.3 for t in d["ev"]["drums"][:, 0]]] for d in decks])
    drums = drums[(drums > 0.2) & (drums < a.dur - 0.2)]
    off = measure_sync(a.clip, drums, a.dur); print(f"sync offset (dots vs clip onsets): {off:+.0f} ms over {len(drums)} drum dots", flush=True)
    W_, H_ = (1920, 1080) if a.hd else (1280, 720); fv = Flyover(decks, tim, a.dur, W_, H_)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W_}x{H_}", "-r", str(FPS), "-i", "-",
                           "-t", str(a.dur), "-i", a.clip, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", a.out], stdin=subprocess.PIPE)
    T = time.time(); n = int(a.dur * FPS)
    for fi in range(n): ff.stdin.write(fv.frame(fi / FPS).tobytes())
    ff.stdin.close(); ff.wait(); el = time.time() - T
    print(f"render {n} frames in {el:.1f}s = {n / el:.1f} fps ({el / a.dur:.2f}x realtime)", flush=True)


# ---------------- v1+ : flat v1 layout, key palette, energy glow, drop shockwaves, bass dust, title cards ----------------
import colorsys, glob, re
def track_info(tid):
    """(title, camelot) from any delivered tracklist line '... Artist – Title  [6B]  (youtu.be/<id>)'."""
    for f in sorted(glob.glob("/workspace/mixes/deliver/*/*tracklist.md")):
        for ln in open(f):
            if tid in ln:
                m = re.search(r"\d+:\d+\s+(.*?)\s+\[(\d+[AB])\]", ln)
                if m: return m.group(1).replace("\u2013", "-").replace("\u2014", "-"), m.group(2)
    return tid, None

def key_hue(cam):  # Camelot wheel -> hue (adjacent keys = adjacent hues); B (major) brighter, A (minor) deeper
    if not cam: return 0.6, 0.75, 1.0
    n, ab = int(cam[:-1]), cam[-1]; return ((n - 1) / 12.0) % 1.0, (0.65 if ab == "B" else 0.85), (1.0 if ab == "B" else 0.85)

def _rgb(h, s_, v): return np.array(colorsys.hsv_to_rgb(h % 1.0, s_, v)) * 255
LANE_DH = [0.0, -0.09, 0.1, 0.2]  # lane hue offsets around the deck's key hue (drums, bass, melody, vocals)

def main_v1plus(a, tim):
    import time
    decks = timing_lanes(tim); bs, s0 = tim["bar_sec"], tim["clip_start_bar"]
    drums = np.concatenate([d["ev"]["drums"][:, 0][[d["gain"](t) > 0.3 for t in d["ev"]["drums"][:, 0]]] for d in decks])
    drums = drums[(drums > 0.2) & (drums < a.dur - 0.2)]
    off = measure_sync(a.clip, drums, a.dur); print(f"sync offset (dots vs clip onsets): {off:+.0f} ms over {len(drums)} drum dots", flush=True)
    info = [track_info(d["id"]) for d in decks]; hues = [key_hue(c) for _, c in info]
    dt = 0.01; tg = np.arange(0, a.dur + 1, dt)
    def env(dk, lanes, tau):
        x = np.zeros_like(tg)
        for ln in lanes:
            for t, lv, _ in dk["ev"][ln]:
                i = int(t / dt)
                if 0 <= i < len(tg): x[i] += lv * dk["gain"](t)
        k = np.exp(-np.arange(0, 6 * tau, dt) / tau); y = np.convolve(x, k)[: len(x)]; return y / (np.percentile(y, 99) + 1e-9)
    energy = [env(dk, ["drums", "bass", "melody", "vocals"], 1.5) for dk in decks]  # slow build-up envelope
    bass = env(decks[0], ["bass"], 0.12) * 0 + sum(env(dk, ["bass"], 0.12) for dk in decks); bass /= bass.max() + 1e-9
    drops = [(e["mix_bar"] - s0) * bs for e in tim["events"] if e["kind"] == "dswap"] + [(e["end_bar"] - s0) * bs for e in tim["events"] if e["kind"] == "ib" and (e["end_bar"] - s0) * bs < a.dur]
    enter = []
    for i, dk in enumerate(decks):
        ts = next((t for t in np.arange(0, a.dur, 0.05) if dk["gain"](t) > 0.05), None)
        if ts is not None: enter.append((max(ts, 0.0), i))
    rng = np.random.default_rng(7); NP = 220
    dust = np.c_[rng.uniform(0, W, NP), rng.uniform(0, H, NP), rng.uniform(0.3, 1.0, NP), rng.uniform(0, 6.28, NP)]
    geo = lane_geom(); px = (WIN_PAST + WIN_FUT) / W
    staff = {}  # pre-rendered staff line masks per deck (white), tinted per frame
    for d in range(2):
        im = Image.new("L", (W, H)); dr = ImageDraw.Draw(im)
        for dd, j, y0, y1 in geo:
            if dd != d: continue
            for k in range(5):
                y = y0 + k * (y1 - y0) / 4; dr.line([persp(0, y), persp(W, y)], fill=255, width=1)
        staff[d] = np.asarray(im, np.float32)[:, :, None] / 255
        staff[d] = (staff[d], np.asarray(im.filter(ImageFilter.GaussianBlur(4)), np.float32)[:, :, None] / 255)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-t", str(a.dur), "-i", a.clip, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", a.out], stdin=subprocess.PIPE)
    vy = np.linspace(-1, 1, H)[:, None, None]; vx = np.linspace(-1, 1, W)[None, :, None]; vign = 1 - 0.3 * (vx ** 2 + vy ** 2) / 2
    T0 = time.time(); n = int(a.dur * FPS)
    for fi in range(n):
        tm = fi / FPS; ix = min(int(tm / dt), len(tg) - 1); g = [dk["gain"](tm) for dk in decks]
        wsum = g[0] + g[1] + 1e-9; deck_col = [_rgb(*hues[d]) for d in range(2)]
        mixcol = (deck_col[0] * g[0] + deck_col[1] * g[1]) / wsum
        dx, dy = 3 * np.sin(tm * 0.13), 2 * np.sin(tm * 0.09 + 1)  # slow drift
        # background: key-tinted gradient blending with the crossfade
        fr = np.zeros((H, W, 3), np.float32) + np.array([6, 7, 14], np.float32)
        fr += (mixcol * 0.07)[None, None, :] * (1 - (vy + 1) / 2 * 0.6)
        # dust (parallax: drifts slower than staves, pulses with bass)
        b = bass[ix]; dl = Image.new("RGB", (W, H)); dd_ = ImageDraw.Draw(dl)
        for x0, y0, z, ph in dust:
            x = (x0 - tm * 6 * z + dx * z * 2) % W; y = (y0 + 4 * np.sin(tm * 0.3 + ph) + dy * z * 2) % H
            r = 0.6 + z * (0.8 + 2.2 * b); c = tuple(int(v) for v in np.clip(mixcol * (0.12 + 0.55 * b) * z, 0, 255))
            dd_.ellipse([x - r, y - r, x + r, y + r], fill=c)
        fr += np.asarray(dl, np.float32)
        # staff lines: deck key colour, glow with energy build-up
        for d in range(2):
            e = energy[d][ix]; e_up = max(0.0, energy[d][ix] - energy[d][max(0, ix - 100)])
            lines, glow = staff[d]; lit = 0.35 + 0.65 * g[d]
            col = 0.55 * np.array([48, 52, 70]) + 0.45 * deck_col[d] * 0.35
            fr += lines * col * lit + glow * deck_col[d] * (0.25 * e + 0.9 * e_up) * lit
        # shockwaves on drops: bright band expanding from the playhead across all staves
        sx = W * PLAY_X + dx
        for td in drops:
            age = tm - td
            if 0 <= age < 1.6:
                rad = 60 + 900 * (1 - np.exp(-age / 0.45)); amp = np.exp(-age / 0.5)
                ring = np.exp(-((np.abs(vx[0, :, 0] * W / 2 + W / 2 - sx) - rad) / 18) ** 2)[None, :, None]
                flash = np.exp(-((vx[0, :, 0] * W / 2 + W / 2 - sx) / 140) ** 2)[None, :, None] * np.exp(-age / 0.18)
                fr += (ring * 160 * amp + flash * 120) * (0.6 + 0.4 * deck_col[1] / 255)[None, None, :] * (0.4 + 0.6 * (lines_any := 1))
        # dots (v1 layout), lane colours from the deck's key hue
        glow = Image.new("RGB", (W, H)); core = Image.new("RGB", (W, H)); dg, dc = ImageDraw.Draw(glow), ImageDraw.Draw(core)
        for d, j, y0, y1 in geo:
            dk = decks[d]; lane = LANES[j][0]; e = dk["ev"][lane]; m_ = (e[:, 0] > tm - WIN_PAST) & (e[:, 0] < tm + WIN_FUT)
            h_, s_, v_ = hues[d]; col = _rgb(h_ + LANE_DH[j], s_, v_)
            for t, lv, p in sorted(e[m_], key=lambda q: q[0] <= tm):
                gt = dk["gain"](t) * (dk["low"](t) if lane == "bass" else 1)
                if gt < 0.02: continue
                x = W * PLAY_X + (t - tm) / px + dx; y = y1 - p * (y1 - y0) + dy; X, Y = persp(x, y); age = tm - t
                bb = (0.18 if age < 0 else 0.25 + 1.6 * np.exp(-age / 0.35)) * (0.35 + 0.65 * min(lv, 1)) * (0.12 + 0.88 * gt)
                r = 2 + 3 * min(lv, 1) + (4 * np.exp(-age / 0.25) if age >= 0 else 0)
                c = tuple(int(v) for v in np.clip(col * bb, 0, 255))
                dg.ellipse([X - r * 2.2, Y - r * 2.2, X + r * 2.2, Y + r * 2.2], fill=c); dc.ellipse([X - r, Y - r, X + r, Y + r], fill=c)
                if dk["ib"] and lane in ("drums", "bass") and dk["ib"][0] <= t < dk["ib"][1]:
                    q = int(200 * min(1, bb)); dc.ellipse([X - r - 3, Y - r - 3, X + r + 3, Y + r + 3], outline=(q, q, q))
        gsm = glow.resize((W // 2, H // 2), Image.BILINEAR).filter(ImageFilter.GaussianBlur(4.5)).resize((W, H), Image.BILINEAR)
        fr += np.asarray(gsm, np.float32) * 1.4 + np.asarray(core, np.float32)
        fr *= vign
        img = Image.fromarray(np.clip(fr, 0, 255).astype(np.uint8)); dr = ImageDraw.Draw(img)
        X0, _ = persp(W * PLAY_X + dx, 0); X1, _ = persp(W * PLAY_X + dx, H); dr.line([(X0, 50), (X1, H - 10)], fill=(210, 210, 230), width=1)
        for d, j, y0, y1 in geo:
            if j == 0 or True:
                dr.text(persp(8 + dx, y0 - 12 + dy), f"{'OUT' if d == 0 else 'IN '} {LANES[j][0]}", fill=tuple(int(v) for v in 0.45 * deck_col[d] + 60))
        for ts, i in enter:  # title cards: fade in 0.8 s, hold, fade out by 5 s
            age = tm - ts
            if 0 <= age < 5.5:
                al = _ss(age / 0.8) * (1 - _ss((age - 4.2) / 1.3)); title, cam = info[i]
                cy = 200 if i == 0 else 545; c = tuple(int(v) for v in np.clip((deck_col[i] * 0.6 + 100) * al, 0, 255))
                dr.text((W - 470, cy), title, fill=c, font_size=22); dr.text((W - 470, cy + 30), f"key {cam or '?'}  ·  {'outgoing' if i == 0 else 'incoming'}", fill=tuple(int(v * 0.7) for v in c), font_size=15)
        if a.still_at is not None and fi == int(a.still_at * FPS): img.save(os.path.splitext(a.out)[0] + ".png")
        ff.stdin.write(img.tobytes())
    ff.stdin.close(); ff.wait(); el = time.time() - T0
    print(f"render {n} frames in {el:.1f}s = {n / el:.1f} fps ({el / a.dur:.2f}x realtime)", flush=True)

if __name__ == "__main__": main()
