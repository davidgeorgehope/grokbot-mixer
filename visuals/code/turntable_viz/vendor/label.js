// MODIFIED for grokbot-mixer turntable_viz (twin decks, data-driven groove glow). Upstream: github.com/rauchg/vinyl (MIT).
// The paper label at the centre of the record, drawn into a canvas and used as a texture.
// Dark grey stock with visible grain and fibres, a little shelf wear, and cream ink that did not
// quite cover: the Vercel triangle above the spindle, the track list below it.
import { TAU, rng } from './dsp.js';

const S = 1024, C = S / 2;                      // texture size; the label is 100 mm across, so about 10 px per mm
const DARKEN = 0.4, INK = '#716d64';            // texture values that land as dark grey paper and cream ink once lit (see paper())
const SANS = '"Helvetica Neue", Helvetica, Arial, sans-serif', MONO = 'ui-monospace, SFMono-Regular, Menlo, monospace';
let stock = null;                               // the blank paper, made once

const sheet = () => { const c = document.createElement('canvas'); c.width = c.height = S; return c; };
// n x n random texels, to be stretched over the label: grey values, or white with random opacity
function noise(n, R, asAlpha) {
  const c = document.createElement('canvas'); c.width = c.height = n;
  const x = c.getContext('2d'), d = x.createImageData(n, n);
  for (let i = 0; i < n * n; i++) {
    const v = R();
    d.data[i * 4] = d.data[i * 4 + 1] = d.data[i * 4 + 2] = asAlpha ? 255 : 28 + v * 200; d.data[i * 4 + 3] = asAlpha ? v * 255 : 255;
  }
  x.putImageData(d, 0, 0);
  return c;
}
const stretch = (x, tex) => { const m = S / tex.width; x.drawImage(tex, -m, -m, S + 2 * m, S + 2 * m); };

function paper() {
  const c = sheet(), x = c.getContext('2d'), R = rng(41);
  x.fillStyle = '#4c4c4e'; x.fillRect(0, 0, S, S);
  x.imageSmoothingEnabled = true; x.imageSmoothingQuality = 'high';
  x.globalCompositeOperation = 'overlay';       // mottling: soft blotches at three scales
  for (const [n, a] of [[5, 0.34], [19, 0.24], [77, 0.18]]) { x.globalAlpha = a; stretch(x, noise(n, R)); }
  x.globalCompositeOperation = 'source-over';
  for (let i = 0; i < 1500; i++) {              // fibres: short curved hairs, mostly paler than the stock
    const px = R() * S, py = R() * S, len = 5 + R() * 30, a = R() * TAU, b = a + (R() - 0.5) * 1.2;
    x.globalAlpha = 1; x.lineWidth = 0.5 + R() * 0.9;
    x.strokeStyle = R() < 0.65 ? `rgba(255,250,240,${0.035 + R() * 0.075})` : `rgba(0,0,0,${0.06 + R() * 0.12})`;
    x.beginPath(); x.moveTo(px, py);
    x.quadraticCurveTo(px + Math.cos(b) * len * 0.5, py + Math.sin(b) * len * 0.5, px + Math.cos(a) * len, py + Math.sin(a) * len); x.stroke();
  }
  const img = x.getImageData(0, 0, S, S), p = img.data;
  for (let i = 0; i < p.length; i += 4) { const g = (R() + R() - 1) * 15; p[i] += g; p[i + 1] += g; p[i + 2] += g * 0.92; }   // grain
  x.putImageData(img, 0, 0);

  // age: darker toward the rim, a paler scuffed patch where the spindle has been missed a few times
  let g = x.createRadialGradient(C, C, C * 0.4, C, C, C);
  g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(0.8, 'rgba(0,0,0,.10)'); g.addColorStop(1, 'rgba(0,0,0,.34)');
  x.fillStyle = g; x.fillRect(0, 0, S, S);
  g = x.createRadialGradient(C, C, 30, C, C, 110);
  g.addColorStop(0, 'rgba(255,250,240,.10)'); g.addColorStop(1, 'rgba(255,250,240,0)');
  x.fillStyle = g; x.fillRect(0, 0, S, S);
  x.lineCap = 'round';
  for (let i = 0; i < 46; i++) {                // spindle trails: short pale scratches around the hole
    const a = R() * TAU, r0 = 38 + R() * 26, r1 = r0 + 10 + R() * 55, bend = (R() - 0.5) * 0.9;
    x.lineWidth = 0.7 + R() * 1.3; x.strokeStyle = `rgba(255,250,240,${0.05 + R() * 0.13})`;
    x.beginPath(); x.moveTo(C + r0 * Math.cos(a), C + r0 * Math.sin(a)); x.lineTo(C + r1 * Math.cos(a + bend), C + r1 * Math.sin(a + bend)); x.stroke();
  }
  for (let i = 0; i < 30; i++) {                // ring wear from years in a sleeve
    const a = R() * TAU, r = 175 + R() * 330;
    x.lineWidth = 0.6 + R() * 2.2; x.strokeStyle = `rgba(255,250,240,${0.02 + R() * 0.05})`;
    x.beginPath(); x.arc(C, C, r, a, a + 0.15 + R() * 1.1); x.stroke();
  }
  for (let i = 0; i < 70; i++) {                // foxing: a few faint warm specks
    const px = R() * S, py = R() * S, r = 1 + R() * 5;
    g = x.createRadialGradient(px, py, 0, px, py, r);
    g.addColorStop(0, `rgba(150,110,70,${0.08 + R() * 0.14})`); g.addColorStop(1, 'rgba(150,110,70,0)');
    x.fillStyle = g; x.fillRect(px - r, py - r, 2 * r, 2 * r);
  }
  // Everything above is drawn at the brightness it should look. The scene's key light is several times
  // unity and the disc shader squares the texel, so the texture itself has to be much darker than that.
  x.globalCompositeOperation = 'multiply'; x.fillStyle = `rgb(${DARKEN * 255},${DARKEN * 255},${DARKEN * 255})`; x.fillRect(0, 0, S, S);
  return c;
}

// text along the bottom edge, centred, reading left to right
function arcText(k, text, r, gap) {
  const chars = [...text], adv = chars.map((ch) => k.measureText(ch).width + gap);
  let th = Math.PI / 2 + adv.reduce((a, b) => a + b, 0) / r / 2;
  chars.forEach((ch, i) => {
    th -= adv[i] / r / 2;
    k.save(); k.translate(C + r * Math.cos(th), C + r * Math.sin(th)); k.rotate(th - Math.PI / 2); k.fillText(ch, 0, 0); k.restore();
    th -= adv[i] / r / 2;
  });
}

export function drawLabel(titles = [], opts = {}) {
  stock ||= paper();
  const c = sheet(), x = c.getContext('2d');
  x.drawImage(stock, 0, 0);
  if (opts.paper) { x.globalCompositeOperation = 'multiply'; x.fillStyle = opts.paper; x.fillRect(0, 0, S, S); x.globalCompositeOperation = 'source-over'; }

  // the ink is its own layer, so it can wear without the paper under it changing
  const layer = sheet(), k = layer.getContext('2d'), R = rng(7);
  k.fillStyle = k.strokeStyle = INK; k.textAlign = 'center'; k.textBaseline = 'middle';
  k.lineWidth = 3; k.beginPath(); k.arc(C, C, 489, 0, TAU); k.stroke();
  k.lineWidth = 1.2; k.beginPath(); k.arc(C, C, 440, 0, TAU); k.stroke();

  const w = 330, h = w * Math.sqrt(3) / 2, top = C - 2 * h / 3;    // the triangle: equilateral, its centroid on the spindle so it turns in place
  if (opts.mark) { k.font = `800 250px ${SANS}`; k.fillText(opts.mark, C, C - 175); }
  else { k.beginPath(); k.moveTo(C, top); k.lineTo(C + w / 2, top + h); k.lineTo(C - w / 2, top + h); k.closePath(); k.fill(); }

  k.font = `600 23px ${SANS}`; k.letterSpacing = '5px';            // either side of the spindle
  const [l1, l2, r1, r2] = opts.corners || ['STEREO', 'SIDE A', '33⅓', 'RPM'];
  k.fillText(l1, C - 300, C - 17); k.fillText(l2, C - 300, C + 17);
  k.fillText(r1, C + 300, C - 17); k.fillText(r2, C + 300, C + 17);
  k.letterSpacing = '0px';
  k.font = `500 27px ${MONO}`;                                     // tracks, each kept inside the circle
  titles.filter(Boolean).slice(0, 5).forEach((t, i) => {
    const dy = (opts.titleY || 204) + i * 40;
    k.fillText((opts.numbered === false ? t : `${i + 1}. ${t}`).slice(0, 40), C, C + dy, 2 * Math.sqrt(425 * 425 - dy * dy) - 44);
  });
  k.font = `600 15px ${SANS}`;
  arcText(k, opts.arc || 'NOT A SOUND EFFECT  ·  CUT INTO A GROOVE  ·  READ BACK BY A SIMULATED STYLUS', 464, 5);

  k.globalCompositeOperation = 'destination-out';
  k.imageSmoothingEnabled = true; k.imageSmoothingQuality = 'high';
  k.globalAlpha = 0.30; stretch(k, noise(46, R, true));            // uneven ink density
  for (let i = 0; i < 7000; i++) {                                 // pinholes where the ink missed the grain
    const s = 0.6 + R() * 1.5; k.globalAlpha = 0.1 + 0.45 * R(); k.fillRect(R() * S, R() * S, s, s);
  }
  for (let i = 0; i < 44; i++) {                                   // hairline scuffs, following the rotation
    const a = R() * TAU; k.globalAlpha = 0.2 + 0.45 * R(); k.lineWidth = 0.6 + R() * 1.2;
    k.beginPath(); k.arc(C, C, 60 + R() * 425, a, a + 0.05 + R() * 0.4); k.stroke();
  }
  k.lineCap = 'round';
  for (let i = 0; i < 16; i++) {                                   // spindle trails: a little ink scratched off around the hole
    const a = R() * TAU, r0 = 38 + R() * 20, r1 = r0 + 8 + R() * 34, bend = (R() - 0.5) * 0.9;
    k.globalAlpha = 0.12 + 0.3 * R(); k.lineWidth = 0.6 + R() * 0.9;
    k.beginPath(); k.moveTo(C + r0 * Math.cos(a), C + r0 * Math.sin(a)); k.lineTo(C + r1 * Math.cos(a + bend), C + r1 * Math.sin(a + bend)); k.stroke();
  }
  x.globalAlpha = 0.95; x.drawImage(layer, 0, 0);
  // pressing ring: the dent the press leaves around the spindle, through paper and ink alike
  x.globalAlpha = 1;
  x.lineWidth = 3.5; x.strokeStyle = 'rgba(0,0,0,.30)'; x.beginPath(); x.arc(C, C, 158, 0, TAU); x.stroke();
  x.lineWidth = 2; x.strokeStyle = 'rgba(255,255,255,.03)'; x.beginPath(); x.arc(C, C, 162, 0, TAU); x.stroke();
  return c;
}
