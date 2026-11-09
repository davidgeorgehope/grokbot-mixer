// Twin virtual turntables for DJ mix videos. Decks are rauchg/vinyl's WebGL2 deck renderer (MIT, vendored in
// ./vendor with small patches); the records are "cut" from each track's real energy (prep.py), and the
// platter angle, tonearm and mixer controls are driven per frame from the engine's timing.json.
import { Renderer } from './vendor/render.js';
import { grooveRadius, alphaForRadius, stylusXY, ALPHA_REST } from './vendor/geometry.js';

const W = 1920, H = 1080, TAU = Math.PI * 2;
const PINK = [1.0, 0.36, 0.62], CYAN = [0.30, 0.78, 1.0];
const css = (c, a = 1) => `rgba(${c.map((v) => Math.round(v * 255)).join(',')},${a})`;
let R, D, out, ctx, glc;

function decodeVis(rec) {
  const bin = atob(rec.vis), data = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) data[i] = bin.charCodeAt(i);
  return { data, cols: rec.cols, rows: rec.rows };
}

window.setup = async (url, opts = {}) => {
  D = await (await fetch(url)).json();
  D.opts = Object.assign({ deckW: 960, mixW: 300 }, opts);
  glc = document.getElementById('gl'); out = document.getElementById('out'); ctx = out.getContext('2d');
  R = new Renderer(glc);
  // one renderer, two records: keep both cuts and swap textures per deck
  D.recs = D.decks.map((d, i) => {
    const t = i === 0 ? D.titles.out : D.titles.in;
    const rec = { rTab: Float64Array.from(d.rTab), thetaEnd: d.thetaEnd, warp: [{ k: 2, amp: 0.00035, ph: i * 1.7 }], ecc: [0, 0], scratches: [],
      condition: { dust: 0.15 }, tracks: [{ title: t.title }, { title: t.artist }],
      labelOpts: { mark: i === 0 ? 'A' : 'B', corners: ['DECK', i === 0 ? 'ONE' : 'TWO', d.bpm.toFixed(0), 'BPM'], numbered: false,
        arc: `${t.artist.toUpperCase()}  ·  ${t.title.toUpperCase()}  ·  CUT FROM THE TRACK'S OWN ENERGY  ·  ONE TURN PER BAR  ·  `,
        paper: i === 0 ? '#ffb3c8' : '#b3e4ff' } };
    R.setRecord(rec, decodeVis(d));
    return { rec, info: R.info, label: snapshotTex(R), vis: snapTexVis(R), lut: snapTexLut(R) };
  });
  return { frames: D.frameState.length, fps: D.fps };
};
// Renderer keeps one set of textures; create fresh ones per record by stealing them after setRecord
function snapshotTex(r) { const t = r.tex.label; r.tex.label = r.gl.createTexture(); return t; }
function snapTexVis(r) { const t = r.tex.vis; r.tex.vis = r.gl.createTexture(); return t; }
function snapTexLut(r) { const t = r.tex.lut; r.tex.lut = r.gl.createTexture(); return t; }

function deckState(i, fs, t) {
  const d = D.decks[i], s = fs.d[i], rec = D.recs[i];
  const theta = TAU * (d.lead + s.tb);
  const r = grooveRadius(rec.rec.rTab, theta), al = alphaForRadius(r), [sx, sy] = stylusXY(al);
  const thp = theta - Math.atan2(sy, sx);
  const beatPh = (fs.mb * 4) % 1, beat = Math.exp(-beatPh * 6) * (s.on ? 1 : 0.15) * (0.25 + 0.75 * s.g);
  const left = i === 0, dw = D.opts.deckW;
  return {
    thp, al, zt: 0, zoom: 0, motor: s.on, rpm: 60 / d.barSec,
    az: left ? 0.40 : -0.40, el: 0.80, dist: 1.18, at: [left ? 0.030 : 0.060, 0.030, -0.035], keyGain: 0.6,
    vp: left ? [0, 0, dw, H] : [W - dw, 0, dw, H], noClearColor: true,
    grooveW: d.pitch * 0.30, tint: left ? PINK.map((v) => v * 1.6) : CYAN, beat, playRev: d.lead + s.tb, glow: 3.5 * (0.3 + 0.7 * s.g),
  };
}

let x0lab = 0;
function knob(x, y, r, v, col, label, lit) {        // v 0..1, 0.5 = noon? we pass absolute angle fraction
  const a0 = Math.PI * 0.75, a1 = Math.PI * 2.25, a = a0 + (a1 - a0) * v;
  ctx.save();
  ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,0.07)'; ctx.beginPath(); ctx.arc(x, y, r + 7, a0, a1); ctx.stroke();
  ctx.strokeStyle = css(col, 0.35 + 0.65 * lit); ctx.shadowColor = css(col, 0.9); ctx.shadowBlur = 10 * lit;
  ctx.beginPath(); ctx.arc(x, y, r + 7, a0, a); ctx.stroke(); ctx.shadowBlur = 0;
  const g = ctx.createRadialGradient(x - r * 0.3, y - r * 0.4, 1, x, y, r);
  g.addColorStop(0, '#3a3c44'); g.addColorStop(1, '#0d0e12');
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.fill();
  ctx.strokeStyle = '#000'; ctx.lineWidth = 1.5; ctx.stroke();
  ctx.strokeStyle = '#e8e8ee'; ctx.lineWidth = 2.5; ctx.beginPath();
  ctx.moveTo(x + Math.cos(a) * r * 0.25, y + Math.sin(a) * r * 0.25); ctx.lineTo(x + Math.cos(a) * r * 0.9, y + Math.sin(a) * r * 0.9); ctx.stroke();
  if (label) { ctx.fillStyle = 'rgba(200,205,220,0.55)'; ctx.font = '600 11px DejaVu Sans, sans-serif'; ctx.textAlign = 'center'; ctx.fillText(label, x0lab, y + 4); }
  ctx.restore();
}

function meter(x, y, w, h, v, col) {
  const n = 18;
  for (let k = 0; k < n; k++) {
    const on = v * n > k, yy = y + h - (k + 1) * (h / n);
    const c = k > 15 ? [1, 0.25, 0.25] : k > 12 ? [1, 0.8, 0.3] : col;
    ctx.fillStyle = on ? css(c, 0.95) : 'rgba(255,255,255,0.05)';
    if (on) { ctx.shadowColor = css(c, 0.8); ctx.shadowBlur = 6; }
    ctx.fillRect(x, yy + 1, w, h / n - 3); ctx.shadowBlur = 0;
  }
}

function fader(x, y, h, v, col, vertical = true, label = '') {
  ctx.save();
  ctx.fillStyle = '#050507'; ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  if (vertical) {
    ctx.fillRect(x - 3, y, 6, h); ctx.strokeRect(x - 3, y, 6, h);
    for (let k = 0; k <= 10; k++) { ctx.fillStyle = 'rgba(255,255,255,0.12)'; ctx.fillRect(x - 16, y + k * h / 10, 7, 1); ctx.fillRect(x + 9, y + k * h / 10, 7, 1); }
    const yy = y + h * (1 - v);
    ctx.fillStyle = css(col, 0.25); ctx.fillRect(x - 2, yy, 4, y + h - yy);
    const g = ctx.createLinearGradient(0, yy - 14, 0, yy + 14); g.addColorStop(0, '#4a4c55'); g.addColorStop(0.5, '#1a1b20'); g.addColorStop(1, '#2c2e35');
    ctx.fillStyle = g; ctx.fillRect(x - 18, yy - 12, 36, 24);
    ctx.fillStyle = css(col, 0.95); ctx.shadowColor = css(col); ctx.shadowBlur = 8; ctx.fillRect(x - 16, yy - 1, 32, 2);
  } else {
    ctx.fillRect(x, y - 3, h, 6); ctx.strokeRect(x, y - 3, h, 6);
    const xx = x + h * v;
    const g = ctx.createLinearGradient(xx - 14, 0, xx + 14, 0); g.addColorStop(0, '#4a4c55'); g.addColorStop(0.5, '#1a1b20'); g.addColorStop(1, '#2c2e35');
    ctx.fillStyle = g; ctx.fillRect(xx - 14, y - 20, 28, 40);
    const c = [PINK[0] * (1 - v) + CYAN[0] * v, PINK[1] * (1 - v) + CYAN[1] * v, PINK[2] * (1 - v) + CYAN[2] * v];
    ctx.fillStyle = css(c); ctx.shadowColor = css(c); ctx.shadowBlur = 10; ctx.fillRect(xx - 1, y - 18, 2, 36);
  }
  ctx.restore();
  if (label) { ctx.fillStyle = 'rgba(200,205,220,0.55)'; ctx.font = '600 11px DejaVu Sans, sans-serif'; ctx.textAlign = 'center'; ctx.fillText(label, vertical ? x : x + h / 2, vertical ? y + h + 22 : y + 38); }
}

function drawMixer(fs) {
  const mw = D.opts.mixW, x0 = (W - mw) / 2, y0 = 250, y1 = 960;
  ctx.save();
  // panel
  ctx.shadowColor = 'rgba(0,0,0,0.9)'; ctx.shadowBlur = 40; ctx.shadowOffsetY = 18;
  const g = ctx.createLinearGradient(x0, y0, x0 + mw, y1); g.addColorStop(0, '#1b1c21'); g.addColorStop(1, '#0c0d10');
  ctx.fillStyle = g; ctx.beginPath(); ctx.roundRect(x0, y0, mw, y1 - y0, 14); ctx.fill();
  ctx.shadowColor = 'transparent'; ctx.shadowOffsetY = 0; ctx.shadowBlur = 0;
  ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 1; ctx.stroke();
  for (let k = 0; k < 60; k++) { ctx.fillStyle = `rgba(255,255,255,${0.008 + 0.006 * Math.sin(k * 7.1)})`; ctx.fillRect(x0 + 4, y0 + 6 + k * (y1 - y0 - 12) / 60, mw - 8, 1); }
  ctx.fillStyle = 'rgba(210,214,228,0.7)'; ctx.font = '700 13px DejaVu Sans, sans-serif'; ctx.textAlign = 'center';
  ctx.fillText('GROKBOT · MIXER', x0 + mw / 2, y0 + 26);
  const cx = [x0 + mw * 0.27, x0 + mw * 0.73], cols = [PINK, CYAN];
  for (let i = 0; i < 2; i++) {
    const s = fs.d[i], lit = s.on ? 0.3 + 0.7 * s.g : 0.1;
    ctx.fillStyle = css(cols[i], 0.85); ctx.font = '700 12px DejaVu Sans, sans-serif'; ctx.fillText(i ? 'CH 2' : 'CH 1', cx[i], y0 + 54);
    // EQ: engine lanes are 1 = flat (noon), 0 = kill (fully counter-clockwise). MID has no lane -> stays at noon.
    x0lab = x0 + mw / 2; const lb = (s2) => (i ? '' : s2);
    knob(cx[i], y0 + 100, 24, 0.5 * s.hi, cols[i], lb('HIGH'), lit);
    knob(cx[i], y0 + 175, 24, 0.5, cols[i], lb('MID'), lit * 0.5);
    knob(cx[i], y0 + 250, 24, 0.5 * s.lo, cols[i], lb('LOW'), lit);
    fader(cx[i], y0 + 320, 230, s.g, cols[i], true, 'GAIN');
  }
  meter(x0 + mw / 2 - 14, y0 + 320, 10, 230, fs.d[0].lvl, PINK);
  meter(x0 + mw / 2 + 4, y0 + 320, 10, 230, fs.d[1].lvl, CYAN);
  ctx.fillStyle = 'rgba(200,205,220,0.45)'; ctx.font = '600 10px DejaVu Sans, sans-serif'; ctx.fillText('LVL', x0 + mw / 2, y0 + 572);
  fader(x0 + 40, y0 + 640, mw - 80, fs.xf, PINK, false, 'CROSSFADER');
  ctx.restore();
}

function hud(fs, t) {
  const tr = D.trans, mb = fs.mb, bar = Math.floor(mb), beat = Math.floor((mb % 1) * 4) + 1;
  ctx.save();
  const tl = (x, align, col, t2, s) => {
    ctx.textAlign = align;
    ctx.fillStyle = css(col); ctx.font = '700 15px DejaVu Sans, sans-serif'; ctx.fillText(s, x, 52);
    ctx.fillStyle = '#eef0f6'; ctx.font = '700 34px DejaVu Sans, sans-serif'; ctx.fillText(t2.title, x, 92);
    ctx.fillStyle = 'rgba(220,224,236,0.7)'; ctx.font = '400 20px DejaVu Sans, sans-serif'; ctx.fillText(t2.artist + (t2.feat ? ' ' + t2.feat : ''), x, 122);
  };
  const st = (i) => { const s = fs.d[i]; return s.cued ? 'CUED · bar ' + Math.floor(s.tb) : !s.on ? 'STOPPED' : `PLAYING · bar ${Math.floor(s.tb)}`; };
  tl(56, 'left', PINK, D.titles.out, 'DECK 1  ·  ' + st(0));
  tl(W - 56, 'right', CYAN, D.titles.in, st(1) + '  ·  DECK 2');
  ctx.textAlign = 'center';
  ctx.fillStyle = 'rgba(238,240,246,0.95)'; ctx.font = '700 40px DejaVu Sans Mono, monospace'; ctx.fillText(`${bar}.${beat}`, W / 2, 92);
  ctx.fillStyle = 'rgba(200,205,220,0.5)'; ctx.font = '600 12px DejaVu Sans, sans-serif'; ctx.fillText('MIX BAR · BEAT', W / 2, 52);
  for (let k = 0; k < 4; k++) { ctx.fillStyle = k + 1 === beat ? 'rgba(255,90,160,0.95)' : 'rgba(255,255,255,0.12)'; ctx.fillRect(W / 2 - 42 + k * 22, 108, 16, 5); }
  let phase = 'DECK 1 SOLO';
  if (mb >= tr.start_bar && mb < tr.end_bar) phase = 'BLEND';
  if (tr.bass_swap && mb >= tr.bass_swap[0] && mb < tr.bass_swap[1]) phase = 'BASS SWAP';
  if (tr.high_bar != null && mb >= tr.high_bar && mb < tr.high_bar + 2) phase = 'HIGHS HANDOFF';
  if (mb >= tr.end_bar) phase = 'DECK 2 SOLO';
  ctx.fillStyle = phase === 'BLEND' || phase.includes('SWAP') || phase.includes('HAND') ? 'rgba(255,110,170,0.95)' : 'rgba(200,205,220,0.6)';
  ctx.font = '700 16px DejaVu Sans, sans-serif'; ctx.fillText(phase, W / 2, 150);
  // blend progress
  const p = Math.max(0, Math.min(1, (mb - tr.start_bar) / (tr.end_bar - tr.start_bar)));
  ctx.fillStyle = 'rgba(255,255,255,0.08)'; ctx.fillRect(W / 2 - 120, 164, 240, 3);
  ctx.fillStyle = 'rgba(255,110,170,0.9)'; ctx.fillRect(W / 2 - 120, 164, 240 * p, 3);
  ctx.fillStyle = 'rgba(160,165,185,0.55)'; ctx.font = '400 14px DejaVu Sans, sans-serif';
  ctx.fillText(D.tech + (D.keys ? '  ·  ' + D.keys : ''), W / 2, H - 40);
  ctx.fillStyle = 'rgba(120,124,140,0.45)'; ctx.font = '400 12px DejaVu Sans, sans-serif';
  ctx.fillText('twin-deck prototype · decks after rauchg/vinyl (MIT) · grooves cut from each track’s energy · arm, platters & mixer from engine timing', W / 2, H - 18);
  ctx.restore();
}

window.renderFrame = (f, fmt = 'image/jpeg', q = 0.92, noEncode = false) => {
  const fs = D.frameState[Math.min(f, D.frameState.length - 1)], t = f / D.fps;
  const gl = R.gl; gl.clearColor(0.004, 0.004, 0.005, 1); gl.clear(gl.COLOR_BUFFER_BIT);
  for (let i = 0; i < 2; i++) {
    const rr = D.recs[i];
    R.info = rr.info; R.tex.label = rr.label; R.tex.vis = rr.vis; R.tex.lut = rr.lut;
    R.draw(deckState(i, fs, t));
  }
  R.gl.finish();
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
  ctx.drawImage(glc, 0, 0);
  // vignette + top fade for the HUD
  let g = ctx.createLinearGradient(0, 0, 0, 260); g.addColorStop(0, 'rgba(0,0,0,0.85)'); g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, 260);
  g = ctx.createRadialGradient(W / 2, H / 2, H * 0.45, W / 2, H / 2, H * 1.05); g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,0.6)');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  drawMixer(fs);
  hud(fs, t);
  if (noEncode) { out.getContext('2d').getImageData(0, 0, 1, 1); return ''; }
  return out.toDataURL(fmt, q);
};
