#!/usr/bin/env python3
"""Camelot Chladni Plate renderer (moderngl/EGL -> ffmpeg).
usage: render_chladni.py analysis.json mix.mp3 out.mp4 [--start S --dur D --w 1920 --h 1080]
Distinct from Mix 01–05 liquid orbs and Mix 06 staff_viz: top-down nodal sand,
Camelot-tinted grains, kick toss, title cards on track enter."""
import json, argparse, subprocess, colorsys, numpy as np, moderngl, os, time
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ap = argparse.ArgumentParser()
ap.add_argument('analysis'); ap.add_argument('mix'); ap.add_argument('out')
ap.add_argument('--start', type=float, default=0)
ap.add_argument('--dur', type=float, default=None)
ap.add_argument('--w', type=int, default=1920)
ap.add_argument('--h', type=int, default=1080)
ap.add_argument('--crf', type=int, default=20)
ap.add_argument('--abr', default='192k')
a = ap.parse_args()
A = json.load(open(a.analysis)); fps = A['fps']
N = len(A['bass']); dur = a.dur or (A['duration'] - a.start)
f0 = int(a.start * fps); nf = min(int(dur * fps), N - f0)
W, H = a.w // 2 * 2, a.h // 2 * 2
tracks = A['tracks']; starts = [t['start'] for t in tracks]; OV = A['overlap']; spb = 60 / A['bpm']

def key_hue(cam):
    if not cam: return 0.58, 0.7, 0.95
    try:
        n, ab = int(cam[:-1]), cam[-1]
        return ((n - 1) / 12.0) % 1.0, (0.65 if ab == 'B' else 0.85), (1.0 if ab == 'B' else 0.85)
    except Exception:
        return 0.58, 0.7, 0.95

def key_rgb(cam):
    h, s, v = key_hue(cam)
    return tuple(colorsys.hsv_to_rgb(h, s, v))

cols = [key_rgb(t.get('key') or t.get('camelot') or '') for t in tracks]

ctx = moderngl.create_context(standalone=True, backend='egl')
VS = """#version 330
in vec2 p; out vec2 uv; void main(){ uv = p*0.5+0.5; gl_Position = vec4(p,0,1); }"""
FS = open(os.path.join(os.path.dirname(__file__), 'chladni_plate.frag')).read()
prog = ctx.program(vertex_shader=VS, fragment_shader=FS)
vbo = ctx.buffer(np.array([-1,-1, 1,-1, -1,1, 1,1], 'f4'))
vao = ctx.simple_vertex_array(prog, vbo, 'p')
fbo = ctx.simple_framebuffer((W, H)); fbo.use()

def load_tex(img):
    t = ctx.texture(img.size, 4, img.convert('RGBA').transpose(Image.FLIP_TOP_BOTTOM).tobytes())
    t.repeat_x = t.repeat_y = False
    t.filter = (moderngl.LINEAR, moderngl.LINEAR)
    return t

def font(sz, bold=False):
    for p in ['/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf' % ('-Bold' if bold else ''),
              '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf']:
        if os.path.exists(p): return ImageFont.truetype(p, sz)
    return ImageFont.load_default()

def card(i, t):
    w, h = 1920, 1080
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    x, y = 120, h - 300
    acc = tuple(int(255 * c) for c in cols[i])
    d.text((x, y), f"{i+1:02d}  ·  {t['artist'].upper()}", font=font(34), fill=(255, 255, 255, 200))
    d.text((x - 4, y + 48), t['title'], font=font(104, True), fill=(255, 255, 255, 255))
    if t.get('feat'): d.text((x, y + 176), t['feat'], font=font(34), fill=acc + (230,))
    key = t.get('key') or ''
    if key: d.text((x + 110, y - 8), key, font=font(28), fill=acc + (220,))
    d.rectangle((x, y - 26, x + 90, y - 21), fill=acc + (255,))
    sh = im.filter(ImageFilter.GaussianBlur(14))
    sh2 = Image.new('RGBA', im.size, (0, 0, 0, 0)); sh2.paste((0, 0, 0, 150), mask=sh.split()[3])
    return load_tex(Image.alpha_composite(sh2, im))

cards = [card(i, t) for i, t in enumerate(tracks)]
if 'card' in prog: prog['card'] = 0
prog['res'] = (W, H)

def U(k, v):
    if k in prog: prog[k].value = v

ff = subprocess.Popen([
    'ffmpeg', '-v', 'error', '-y',
    '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(fps), '-i', '-',
    '-ss', str(a.start), '-t', str(nf / fps), '-i', a.mix,
    '-map', '0:v', '-map', '1:a', '-vf', 'vflip',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', str(a.crf), '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', a.abr, '-shortest', '-movflags', '+faststart', a.out
], stdin=subprocess.PIPE)

def trk(t):
    return max(j for j, s in enumerate(starts) if s <= t + 1e-6)

def sm(x):
    x = min(max(x, 0), 1); return x * x * (3 - 2 * x)

g = lambda k, i: A[k][min(i, N - 1)]
flow = 0.0
for i in range(f0):
    flow += (0.35 + 0.9 * g('bass', i) + 0.4 * g('high', i)) / fps
T0 = time.time()
for n in range(nf):
    i = f0 + n; t = i / fps
    flow += (0.35 + 0.9 * g('bass', i) + 0.4 * g('high', i)) / fps
    ti = trk(t)
    if ti > 0 and t - starts[ti] < OV:
        ia, ib, m = ti - 1, ti, sm((t - starts[ti]) / OV)
    else:
        ia, ib, m = ti, ti, 0.0
    bass, mid, high = g('bass', i), g('mid', i), g('high', i)
    n0 = 1 + int(np.clip(bass * 5, 0, 5))
    m0 = 2 + int(np.clip(mid * 4, 0, 4))
    if n0 == m0: m0 += 1
    n1 = 4 + int(np.clip(high * 4, 0, 4))
    m1 = n1 + 1 + int(np.clip(mid * 2, 0, 2))
    ct = t - (starts[ti] + (OV / 2 if ti > 0 else 0) - 1.0)
    if ti > 0 and t - starts[ti] < OV / 2 - 1.0:
        ci, ct = ti - 1, t - (starts[ti - 1] + (OV / 2 if ti > 1 else 0) - 1.0)
    else:
        ci = ti
    ca = sm(ct / 1.2) * (1 - sm((ct - 7) / 1.5)) if ct >= 0 else 0
    cards[ci].use(0); U('cardA', ca); U('cardT', max(ct, 0))
    bp = (t - A.get('beat_offset', 0)) / spb
    for k, v in [('time', t), ('flow', flow), ('mixAB', m),
                 ('bass', bass), ('mid', mid), ('high', high),
                 ('kick', g('kick', i)), ('snare', g('snare', i)), ('rms', g('rms', i)),
                 ('beat', bp), ('n0', float(n0)), ('m0', float(m0)),
                 ('n1', float(n1)), ('m1', float(m1)),
                 ('colA', cols[ia]), ('colB', cols[ib])]:
        U(k, v)
    vao.render(moderngl.TRIANGLE_STRIP)
    ff.stdin.write(fbo.read(components=3))
    if n % 300 == 0:
        print(f'{n}/{nf} {n/max(time.time()-T0,1e-3):.2f} fps', flush=True)
ff.stdin.close(); rc = ff.wait(); el = time.time() - T0
print(f'done {nf} frames in {el:.0f}s = {nf/max(el,1e-3):.2f} fps rc={rc}')
if rc != 0:
    raise SystemExit(rc)
