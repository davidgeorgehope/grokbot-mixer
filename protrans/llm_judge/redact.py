"""Blind a blend_diag / RCA PNG for the LLM judge: white out every axes title strip (titles carry pick ids, scores,
hard-check verdicts and dip numbers) and the figure suptitle. Axes are found from their dark top/bottom spines."""
import sys, numpy as np
from PIL import Image

def spines(im):
    a = np.asarray(im.convert('RGB')).astype(int); h, w, _ = a.shape
    g = (a.max(2) - a.min(2) < 25) & (a.max(2) < 110)          # dark neutral pixels (spines are black/dark gray)
    rows = []
    for y in range(h):
        r = g[y]; best = cur = 0; x0 = bx0 = 0
        for x in range(w):
            if r[x]:
                if cur == 0: x0 = x
                cur += 1
                if cur > best: best, bx0 = cur, x0
            else: cur = 0
        if best > 0.45 * w: rows.append((y, bx0, bx0 + best))
    # merge adjacent rows (anti-aliased 2-px spines)
    out = []
    for y, a0, a1 in rows:
        if out and y - out[-1][0] <= 2: continue
        out.append((y, a0, a1))
    return out

def redact(src, dst, strip=17):
    im = Image.open(src).convert('RGB'); a = np.asarray(im).copy(); sp = spines(im)
    tops = sp[0::2]                                              # spines come in (top, bottom) pairs per axes
    for y, x0, x1 in tops:
        a[max(0, y - strip):max(0, y - 1), :, :] = 255
    Image.fromarray(a).save(dst); return len(sp)

if __name__ == '__main__':
    print(redact(sys.argv[1], sys.argv[2]))

def panels(src, out_prefix):
    """Split a (redacted) figure into one PNG per axes panel, so each panel reaches the model at full resolution."""
    im = Image.open(src).convert('RGB'); sp = spines(im); h = im.size[1]; outs = []
    for k in range(0, len(sp) - 1, 2):
        top, bot = sp[k][0], sp[k + 1][0]
        crop = im.crop((0, max(0, top - 4), im.size[0], min(h, bot + 34)))
        p = f'{out_prefix}_p{k // 2 + 1}.png'; crop.save(p); outs.append(p)
    return outs
