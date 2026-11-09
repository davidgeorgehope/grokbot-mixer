#!/usr/bin/env python3
"""Beat-grid overlay for mix transitions — Tigran-inspired scrolling bar/beat grid
with phrase, drop/breakdown markers and crossfader + bass/mid/high handoff lanes.

usage:
  python3 beatgrid_viz.py AUDIO.mp3 OUT.mp4 --timing preview.timing.json [--dur 55] [--fps 30]
  [--st /workspace/mixes/src2/st] [--w 1920 --h 1080]

Driven by engine timing.json (xfader, auto.gain/low/high, deck full_map) plus
st/<id>.json beats/downs/phrases and st/<id>.sections.json drop/breakdown labels.
Optional faint audio-reactive energy strip under the grid.
"""
from __future__ import annotations
import argparse, json, math, os, subprocess, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1920, 1080, 30
# window: seconds of timeline shown (past left of playhead, future right)
WIN_PAST, WIN_FUT = 8.0, 16.0
PLAY_X = 0.30  # playhead x as fraction of width

# palette (Tigran-adjacent: dark + hot pink accents)
BG = (8, 9, 14)
GRID = (42, 44, 58)
GRID_BAR = (70, 74, 96)
GRID_PHRASE = (255, 55, 130)
PLAYHEAD = (255, 70, 150)
OUT_COL = (255, 110, 140)
IN_COL = (90, 200, 255)
DROP_COL = (255, 140, 60)
BRK_COL = (140, 120, 255)
BASS_COL = (255, 90, 120)
MID_COL = (255, 190, 80)
HIGH_COL = (120, 220, 255)
MUTED = (130, 135, 155)
WHITE = (230, 232, 240)


def font(sz, bold=False):
    for p in (
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def lerp(a, b, t):
    return a + (b - a) * t


def interp_auto(pts, bar, default=0.0):
    if not pts:
        return default
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if bar <= xs[0]:
        return float(ys[0])
    if bar >= xs[-1]:
        return float(ys[-1])
    return float(np.interp(bar, xs, ys))


def xfader_at(xf, bar):
    if not xf:
        return 0.0
    xs = [p[0] for p in xf]
    ys = [p[1] for p in xf]
    return float(np.interp(bar, xs, ys, left=ys[0], right=ys[-1]))


def load_sections(st_dir, tid):
    p = os.path.join(st_dir, f"{tid}.sections.json")
    if os.path.exists(p):
        return json.load(open(p))
    return None


def section_label(sec, track_bar):
    """Return (name, color) for a track bar, or None."""
    if not sec:
        return None
    tb = int(track_bar)
    # priority markers at boundaries
    for name, key, col in (
        ("DROP", "drop1", DROP_COL),
        ("DROP 2", "drop2", DROP_COL),
        ("BREAK", "breakdown", BRK_COL),
        ("OUTRO", "outro_start", MUTED),
    ):
        v = sec.get(key)
        if v is not None and tb == int(v):
            return name, col
    # inside a drop run
    for a, b in sec.get("drops") or []:
        if a <= tb < b:
            # only mark the start bar elsewhere; for band colouring return soft
            return None
    return None


def section_band(sec, track_bar):
    """Continuous band colour for arrangement strip."""
    if not sec:
        return (28, 30, 40)
    tb = int(track_bar)
    d1, bd, d2, outro = sec.get("drop1"), sec.get("breakdown"), sec.get("drop2"), sec.get("outro_start")
    intro = sec.get("intro_end", d1 or 0)
    if outro is not None and tb >= outro:
        return (40, 42, 55)
    if d2 is not None and tb >= d2:
        return (90, 50, 30)  # drop 2
    if bd is not None and tb >= bd:
        return (50, 45, 90)  # breakdown
    if d1 is not None and tb >= d1:
        return (90, 50, 30)  # drop 1
    if tb < (intro or 0):
        return (30, 45, 55)  # intro
    return (28, 30, 40)


def track_bar_at(deck, mix_bar):
    """Map mix bar → track bar via full_map."""
    fm = deck.get("full_map") or []
    if not fm:
        return None
    sb = deck["start_bar"]
    i = int(math.floor(mix_bar - sb))
    if i < 0 or i >= len(fm):
        return None
    return fm[i][0]


def analyze_clip_energy(path, dur, fps):
    """Lightweight per-frame bass/mid/high (0..1) for the reactive strip."""
    import librosa
    y, sr = librosa.load(path, sr=22050, mono=True, duration=dur)
    hop = 512
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    bands = {
        "bass": S[(f >= 25) & (f < 150)].sum(0),
        "mid": S[(f >= 150) & (f < 2000)].sum(0),
        "high": S[(f >= 5000) & (f < 11000)].sum(0),
    }
    t = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=hop)
    n = int(dur * fps)
    tt = np.arange(n) / fps
    out = {}
    for k, v in bands.items():
        v = v / (np.percentile(v, 98) + 1e-9)
        out[k] = np.clip(np.interp(tt, t, v), 0, 1.2)
    return out


def draw_round_rect(dr, xy, fill, r=8):
    x0, y0, x1, y1 = xy
    dr.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("out")
    ap.add_argument("--timing", required=True)
    ap.add_argument("--st", default="/workspace/mixes/src2/st")
    ap.add_argument("--dur", type=float, default=None)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--still-at", type=float, default=None)
    a = ap.parse_args()

    # local dims (avoid mutating module globals)
    width, height, fps = a.w, a.h, a.fps

    tim = json.load(open(a.timing))
    bs = float(tim["bar_sec"])
    s0 = float(tim["clip_start_bar"])
    s1 = float(tim.get("clip_end_bar") or (s0 + 40))
    tr = tim["trans"]
    decks = tim["decks"]
    assert len(decks) >= 2, "need 2 decks"
    xf = tr.get("xfader") or []
    titles = tim.get("titles") or {}
    out_t = titles.get("out") or {"artist": "OUT", "title": decks[0]["id"][:11]}
    in_t = titles.get("in") or {"artist": "IN", "title": decks[1]["id"][:11]}

    # probe audio duration
    probe = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", a.audio],
        text=True,
    ).strip()
    audio_dur = float(probe)
    dur = a.dur or min(audio_dur, (s1 - s0) * bs)
    dur = min(dur, audio_dur)

    secs = [load_sections(a.st, d["id"]) for d in decks]

    print(f"beatgrid: {dur:.1f}s @ {fps}fps {width}x{height}  bar_sec={bs:.4f}  clip_bars={s0:.0f}..{s0+dur/bs:.0f}", flush=True)
    print(f"  OUT {out_t.get('artist')} – {out_t.get('title')}", flush=True)
    print(f"  IN  {in_t.get('artist')} – {in_t.get('title')}", flush=True)
    print(f"  blend bars {tr['start_bar']}→{tr['end_bar']}  bass_swap={tr.get('bass_swap')}  high_bar={tr.get('high_bar')}", flush=True)

    print("analyzing clip energy…", flush=True)
    energy = analyze_clip_energy(a.audio, dur, fps)

    F_TITLE = font(36, True)
    F_SUB = font(22)
    F_SMALL = font(16)
    F_TINY = font(13)
    F_LABEL = font(15, True)

    # layout regions (y)
    y_header = 28
    y_grid0, y_grid1 = 110, 520          # main scrolling grid
    y_arr0, y_arr1 = 530, 590            # arrangement strips OUT/IN
    y_energy0, y_energy1 = 600, 640      # reactive energy
    y_hand0, y_hand1 = 660, 1040         # handoff lanes
    lane_h = (y_hand1 - y_hand0) // 4

    px_per_sec = width / (WIN_PAST + WIN_FUT)

    def x_at(t_clip, t_now):
        return width * PLAY_X + (t_clip - t_now) * px_per_sec

    def mix_bar(t_clip):
        return s0 + t_clip / bs

    # precompute marker list (mix_bar, label, color, deck)
    markers = []
    for di, (deck, sec) in enumerate(zip(decks, secs)):
        if not sec:
            continue
        fm = deck.get("full_map") or []
        sb = deck["start_bar"]
        for i, (tb, _) in enumerate(fm):
            mb = sb + i
            lab = section_label(sec, tb)
            if lab:
                markers.append((mb, lab[0], lab[1], di))
    # also explicit bass_swap / high_bar / blend edges
    for b in tr.get("bass_swap") or []:
        markers.append((float(b), "BASS", BASS_COL, -1))
    if tr.get("high_bar") is not None:
        markers.append((float(tr["high_bar"]), "HIGH", HIGH_COL, -1))
    markers.append((float(tr["start_bar"]), "BLEND", GRID_PHRASE, -1))
    markers.append((float(tr["end_bar"]), "END", MUTED, -1))
    markers.sort(key=lambda m: m[0])

    nframes = int(dur * fps)
    still_f = int((a.still_at if a.still_at is not None else dur * 0.45) * fps)

    ff = subprocess.Popen(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
            "-t", str(dur), "-i", a.audio,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(a.crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
            a.out,
        ],
        stdin=subprocess.PIPE,
    )

    T0 = time.time()
    for fi in range(nframes):
        t = fi / fps
        mb = mix_bar(t)
        xfade = xfader_at(xf, mb)
        go = math.cos(xfade * math.pi / 2)
        gi = math.sin(xfade * math.pi / 2)

        im = Image.new("RGB", (width, height), BG)
        dr = ImageDraw.Draw(im)

        # subtle vertical vignette texture lines
        for x in range(0, width, 48):
            dr.line([(x, 0), (x, height)], fill=(12, 13, 20), width=1)

        # --- header ---
        out_name = f"{out_t.get('artist', '')} – {out_t.get('title', '')}"
        in_name = f"{in_t.get('artist', '')} – {in_t.get('title', '')}"
        if in_t.get("feat"):
            in_name += f" ({in_t['feat']})"
        dr.text((48, y_header), out_name, font=F_TITLE, fill=OUT_COL)
        dr.text((48, y_header + 44), "→  " + in_name, font=F_SUB, fill=IN_COL)
        right = f"bar {mb:.1f}   OUT {go:.2f}  IN {gi:.2f}"
        dr.text((width - 420, y_header + 8), right, font=F_SUB, fill=MUTED)
        tech = tr.get("tech") or ""
        if tech:
            dr.text((width - 420, y_header + 40), tech[:54], font=F_TINY, fill=(90, 95, 115))

        # --- main scrolling beat / bar / phrase grid ---
        # background panel
        draw_round_rect(dr, (24, y_grid0 - 8, width - 24, y_grid1 + 8), (14, 15, 22), r=12)

        t_lo = t - WIN_PAST
        t_hi = t + WIN_FUT
        # beat / bar / phrase lines from mix grid (constant bar_sec)
        # first beat at mix bar floor
        b0 = math.floor(mix_bar(t_lo))
        b1 = math.ceil(mix_bar(t_hi)) + 1
        grid_top, grid_bot = y_grid0 + 10, y_grid1 - 10
        mid_y = (grid_top + grid_bot) // 2

        for b in range(b0, b1 + 1):
            tc = (b - s0) * bs
            x = x_at(tc, t)
            if x < 20 or x > width - 20:
                continue
            # phrase every 16 bars, bar every 1, beat = bar/4 visually via subdiv
            is_phrase = (b % 16) == 0
            is_8 = (b % 8) == 0
            if is_phrase:
                dr.line([(x, grid_top), (x, grid_bot)], fill=GRID_PHRASE + (0,), width=2)
                # bright phrase pillar
                dr.line([(x, grid_top), (x, grid_bot)], fill=GRID_PHRASE, width=2)
                dr.text((x + 6, grid_top + 4), f"{b}", font=F_TINY, fill=GRID_PHRASE)
                dr.text((x + 6, grid_bot - 22), "16", font=F_TINY, fill=GRID_PHRASE)
            elif is_8:
                dr.line([(x, grid_top), (x, grid_bot)], fill=GRID_BAR, width=2)
                dr.text((x + 4, grid_top + 4), f"{b}", font=F_TINY, fill=MUTED)
            else:
                dr.line([(x, grid_top + 30), (x, grid_bot - 30)], fill=GRID, width=1)

            # beat subdivisions (4 beats/bar) — faint
            for k in range(1, 4):
                tb = (b + k / 4.0 - s0) * bs
                xb = x_at(tb, t)
                if 20 < xb < width - 20:
                    dr.line([(xb, mid_y - 40), (xb, mid_y + 40)], fill=(30, 32, 42), width=1)

        # current-bar highlight band
        bar_floor = math.floor(mb)
        x_a = x_at((bar_floor - s0) * bs, t)
        x_b = x_at((bar_floor + 1 - s0) * bs, t)
        if x_b > x_a:
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            od = ImageDraw.Draw(overlay)
            od.rectangle([x_a, grid_top, x_b, grid_bot], fill=(255, 70, 150, 28))
            im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
            dr = ImageDraw.Draw(im)

        # drop / breakdown / handoff markers
        for mbar, label, col, di in markers:
            tc = (mbar - s0) * bs
            x = x_at(tc, t)
            if x < 30 or x > width - 30:
                continue
            y_base = grid_top + 20 if di <= 0 else grid_bot - 50
            if di < 0:
                y_base = mid_y - 10
            # flag
            dr.polygon([(x, y_base), (x + 14, y_base + 8), (x, y_base + 16)], fill=col)
            dr.line([(x, y_base), (x, y_base + 36)], fill=col, width=2)
            dr.text((x + 16, y_base), label, font=F_LABEL, fill=col)

        # playhead
        px = width * PLAY_X
        dr.line([(px, grid_top - 6), (px, grid_bot + 6)], fill=PLAYHEAD, width=3)
        dr.polygon([(px - 10, grid_top - 6), (px + 10, grid_top - 6), (px, grid_top + 10)], fill=PLAYHEAD)

        # legend on grid
        dr.text((36, grid_top + 8), "BEAT GRID", font=F_LABEL, fill=MUTED)
        dr.text((36, grid_bot - 28), "phrase = 16 bars   |   bar   |   beat", font=F_TINY, fill=(70, 74, 96))

        # --- arrangement strips (OUT / IN) ---
        strip_h = (y_arr1 - y_arr0) // 2 - 2
        for di, (deck, sec, label, col) in enumerate(
            zip(decks, secs, ("OUT", "IN"), (OUT_COL, IN_COL))
        ):
            yy0 = y_arr0 + di * (strip_h + 4)
            yy1 = yy0 + strip_h
            dr.rectangle([24, yy0, width - 24, yy1], fill=(16, 17, 24))
            dr.text((32, yy0 + 4), label, font=F_TINY, fill=col)
            fm = deck.get("full_map") or []
            sb = deck["start_bar"]
            # paint each visible mix bar
            for b in range(b0, b1 + 1):
                i = b - sb
                if i < 0 or i >= len(fm):
                    continue
                tb = fm[i][0]
                xa = x_at((b - s0) * bs, t)
                xb = x_at((b + 1 - s0) * bs, t)
                if xb < 40 or xa > width - 40:
                    continue
                band = section_band(sec, tb)
                dr.rectangle([max(40, xa), yy0 + 2, min(width - 28, xb), yy1 - 2], fill=band)
            # live gain tint
            g = go if di == 0 else gi
            # left label brightness
            dr.text((70, yy0 + 4), f"gain {g:.2f}", font=F_TINY, fill=tuple(int(c * (0.4 + 0.6 * g)) for c in col))

        # --- energy strip ---
        dr.rectangle([24, y_energy0, width - 24, y_energy1], fill=(16, 17, 24))
        ei = min(fi, len(energy["bass"]) - 1)
        bw = width - 80
        for name, col, yoff in (("bass", BASS_COL, 0), ("mid", MID_COL, 12), ("high", HIGH_COL, 24)):
            v = float(energy[name][ei])
            dr.rectangle([48, y_energy0 + 4 + yoff, 48 + int(bw * min(v, 1)), y_energy0 + 12 + yoff], fill=col)
        dr.text((width - 200, y_energy0 + 8), "energy", font=F_TINY, fill=MUTED)

        # --- handoff lanes ---
        lanes = [
            ("CROSSFADER", "xfader", None),
            ("BASS", "low", BASS_COL),
            ("MID / HIGH", "high", HIGH_COL),
            ("DECK GAIN", "gain", None),
        ]
        # rebuild draw after possible alpha composite
        for li, (label, key, accent) in enumerate(lanes):
            yy0 = y_hand0 + li * lane_h
            yy1 = yy0 + lane_h - 8
            draw_round_rect(dr, (24, yy0, width - 24, yy1), (14, 15, 22), r=10)
            dr.text((36, yy0 + 8), label, font=F_LABEL, fill=accent or MUTED)

            # plot curves across the visible window
            lane_top = yy0 + 28
            lane_bot = yy1 - 10
            lane_mid = (lane_top + lane_bot) / 2
            h = lane_bot - lane_top

            # baseline
            dr.line([(40, lane_bot), (width - 40, lane_bot)], fill=(30, 32, 42), width=1)
            dr.line([(40, lane_top), (width - 40, lane_top)], fill=(30, 32, 42), width=1)

            xs_out, ys_out, xs_in, ys_in = [], [], [], []
            steps = 120
            for si in range(steps + 1):
                tc = t_lo + (t_hi - t_lo) * si / steps
                mbb = mix_bar(tc)
                x = x_at(tc, t)
                if key == "xfader":
                    xfv = xfader_at(xf, mbb)
                    # show OUT gain (cos) and IN gain (sin) as two curves
                    yo = lane_bot - go_curve(xfv) * h
                    yi = lane_bot - gi_curve(xfv) * h
                else:
                    yo = lane_bot - interp_auto(decks[0]["auto"].get(key), mbb, 0.0) * h
                    yi = lane_bot - interp_auto(decks[1]["auto"].get(key), mbb, 0.0) * h
                xs_out.append(x); ys_out.append(yo)
                xs_in.append(x); ys_in.append(yi)

            def poly(xs, ys, col, width=2):
                pts = [(xs[i], ys[i]) for i in range(len(xs)) if 20 < xs[i] < width - 20]
                if len(pts) > 1:
                    dr.line(pts, fill=col, width=width)

            poly(xs_out, ys_out, OUT_COL, 3)
            poly(xs_in, ys_in, IN_COL, 3)

            # fill under curves lightly near playhead
            # current values
            if key == "xfader":
                v_out, v_in = go_curve(xfade), gi_curve(xfade)
            else:
                v_out = interp_auto(decks[0]["auto"].get(key), mb, 0.0)
                v_in = interp_auto(decks[1]["auto"].get(key), mb, 0.0)
            dr.text((width - 280, yy0 + 8), f"OUT {v_out:.2f}", font=F_TINY, fill=OUT_COL)
            dr.text((width - 160, yy0 + 8), f"IN {v_in:.2f}", font=F_TINY, fill=IN_COL)

            # playhead in lane
            dr.line([(px, lane_top), (px, lane_bot)], fill=PLAYHEAD, width=2)
            # dots at current
            dr.ellipse([px - 5, lane_bot - v_out * h - 5, px + 5, lane_bot - v_out * h + 5], fill=OUT_COL)
            dr.ellipse([px - 5, lane_bot - v_in * h - 5, px + 5, lane_bot - v_in * h + 5], fill=IN_COL)

        # footer
        dr.text((48, height - 32), "beat-grid prototype  ·  engine timing + sections  ·  Mix 07", font=F_TINY, fill=(60, 64, 80))

        if fi == still_f:
            still_path = os.path.splitext(a.out)[0] + ".png"
            im.save(still_path)
            print(f"still → {still_path}", flush=True)

        ff.stdin.write(im.tobytes())
        if fi % 60 == 0 and fi > 0:
            el = time.time() - T0
            fps = fi / el
            print(f"{fi}/{nframes}  {fps:.1f} fps  ETA {(nframes-fi)/max(fps,0.1):.0f}s", flush=True)

    ff.stdin.close()
    rc = ff.wait()
    el = time.time() - T0
    print(f"done rc={rc}  {nframes} frames in {el:.1f}s  ({nframes/max(el,0.01):.1f} fps)  "
          f"render_min_per_audio_min={ (el/60) / (dur/60) :.2f}", flush=True)
    if rc != 0:
        raise SystemExit(rc)


def go_curve(xf):
    return math.cos(xf * math.pi / 2)


def gi_curve(xf):
    return math.sin(xf * math.pi / 2)


if __name__ == "__main__":
    main()
