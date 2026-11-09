// Twin virtual turntables for DJ mix videos. Decks are rauchg/vinyl's WebGL2 deck renderer (MIT, vendored in
// ./vendor with small patches); the records are "cut" from each track's real energy (prep.py), and the
// platter angle, tonearm and mixer controls are driven per frame from the engine's timing.json.
import { Renderer } from './vendor/render.js';
import { grooveRadius, alphaForRadius, stylusXY } from './vendor/geometry.js';
import * as G from './vendor/gl-util.js';
import { KEY } from './vendor/shaders.js';
const SHADOW_SIZE = globalThis.TT_SHADOW || 2048;

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

// ---- booth layout (metres, one world): mixer centred at x = 0, decks butted against it, all square to the camera ----
const MIX_HW = 0.15, MIX_HD = 0.19, TOP_Z = -0.022, FLOOR_Z = -0.080;
const DECK_X0 = -0.185, DECK_X1 = 0.27;                       // upstream plinth extent in its own frame
const OFF = [[-MIX_HW - DECK_X1, 0, 0], [MIX_HW - DECK_X0, 0, 0]];
const CAM = { az: 0, el: 0.70, dist: 1.50, at: [0, 0.0, -0.05] };   // ~38 deg down, straight on
const DIVE_ON = () => (D.opts && D.opts.dive !== false);

function smoothstep(a, b, x) {
  const t = Math.max(0, Math.min(1, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
}
function diveAmt(fs) {
  // 0 = booth overview, 1 = needle close-up. Ease in/out over the dive window.
  if (!DIVE_ON() || !D.dives || !D.dives.length) return { k: 0, deck: 0 };
  const mb = fs.mb;
  let best = null;
  for (const dv of D.dives) {
    if (mb < dv.startBar || mb > dv.endBar) continue;
    const span = dv.endBar - dv.startBar, u = (mb - dv.startBar) / span;
    // hold near peak in the middle third
    const k = u < 0.25 ? smoothstep(0, 0.25, u) : u > 0.75 ? 1 - smoothstep(0.75, 1, u) : 1;
    if (!best || k > best.k) best = { k, deck: dv.deck | 0, kind: dv.kind };
  }
  return best || { k: 0, deck: 0 };
}
function camFor(fs) {
  const dv = diveAmt(fs);
  if (dv.k < 1e-4) return { ...CAM, zoom: 0, dive: dv };
  // Fly toward the focused deck's stylus: raise elevation a touch, nudge az, pull zoom in.
  const az = CAM.az + (dv.deck === 0 ? -0.18 : 0.18) * dv.k;
  const el = CAM.el + 0.25 * dv.k;
  const dist = CAM.dist * (1 - 0.55 * dv.k);
  const at = [CAM.at[0] + (dv.deck === 0 ? -0.12 : 0.12) * dv.k, CAM.at[1] + 0.02 * dv.k, CAM.at[2]];
  return { az, el, dist, at, zoom: 0.82 * dv.k, dive: dv };
}

function deckState(i, fs, cam) {
  const d = D.decks[i], s = fs.d[i], rec = D.recs[i];
  const theta = TAU * (d.lead + s.tb);
  const r = grooveRadius(rec.rec.rTab, theta), al = alphaForRadius(r), [sx, sy] = stylusXY(al);
  const thp = theta - Math.atan2(sy, sx);
  const beatPh = (fs.mb * 4) % 1, beat = Math.exp(-beatPh * 6) * (s.on ? 1 : 0.15) * (0.25 + 0.75 * s.g);
  const c = cam || CAM;
  // Only the focused deck gets the stylus zoom; the other stays in booth frame so the dive reads clearly.
  const zoom = (c.dive && c.dive.k > 0 && c.dive.deck === i) ? c.zoom : 0;
  return {
    thp, al, zt: 0, zoom, motor: s.on, rpm: 60 / d.barSec, az: c.az, el: c.el, dist: c.dist, at: c.at,
    off: OFF[i], bare: true, noClear: true, keyGain: 0.6,
    grooveW: d.pitch * 0.30, tint: i === 0 ? PINK.map((v) => v * 1.6) : CYAN, beat, playRev: d.lead + s.tb, glow: 3.5 * (0.3 + 0.7 * s.g),
  };
}

// ---- 3D mixer + booth table, drawn with the vendored PBR shader in the same camera ----
let MX = null;
const KX = [-0.072, 0.072], KY = { hi: 0.125, mid: 0.080, lo: 0.035 }, FAD = [-0.105, -0.010], XF = [-0.065, 0.065, -0.150];
function buildMixer() {
  const gl = R.gl, m = (d) => G.mesh(gl, d), L = G.lathe;
  const knob = L([[0.0115, TOP_Z], [0.0115, TOP_Z + 0.004], [0.0102, TOP_Z + 0.013], [0.0088, TOP_Z + 0.0155], [0, TOP_Z + 0.0158]], 40);
  const ledM = G.box(-0.0011, -0.0011, TOP_Z, 0.0011, 0.0011, TOP_Z + 0.0007);
  MX = {
    table: m(G.box(-3, -1.2, FLOOR_Z - 0.04, 3, 1.2, FLOOR_Z)),
    body: m(G.rbox(-MIX_HW, -MIX_HD, MIX_HW, MIX_HD, FLOOR_Z + 0.004, -0.030, 0.010, 0.002)),
    plate: m(G.rbox(-MIX_HW + 0.002, -MIX_HD + 0.002, MIX_HW - 0.002, MIX_HD - 0.002, -0.030, TOP_Z, 0.009, 0.0015)),
    knob: m(knob),
    ptr: m(G.box(-0.0007, 0.0035, TOP_Z + 0.0156, 0.0007, 0.0098, TOP_Z + 0.0162)),
    led: m(ledM),
    slot: m(G.rbox(-0.0022, FAD[0], 0.0022, FAD[1], TOP_Z - 0.0004, TOP_Z + 0.0002, 0.001, 0.0002)),
    xslot: m(G.rbox(XF[0], XF[2] - 0.0022, XF[1], XF[2] + 0.0022, TOP_Z - 0.0004, TOP_Z + 0.0002, 0.001, 0.0002)),
    cap: m(G.merge(G.rbox(-0.011, -0.0065, 0.011, 0.0065, TOP_Z, TOP_Z + 0.011, 0.002, 0.0012))),
    capLine: m(G.box(-0.010, -0.0007, TOP_Z + 0.0112, 0.010, 0.0007, TOP_Z + 0.0116)),
    xcap: m(G.rbox(-0.0065, -0.011, 0.0065, 0.011, TOP_Z, TOP_Z + 0.012, 0.002, 0.0012)),
    xcapLine: m(G.box(-0.0007, -0.010, TOP_Z + 0.0122, 0.0007, 0.010, TOP_Z + 0.0126)),
    tick: m(G.box(-0.004, -0.0003, TOP_Z, 0.004, 0.0003, TOP_Z + 0.0002)),
  };
  const c = [0, 0, -0.03], eye = c.map((v, k) => v + KEY[k] * 1.3);
  MX.lvp = G.mul(G.ortho(-0.85, 0.85, -0.85, 0.85, 0.2, 2.6), G.lookAt(eye, c).m);
}
const T = (x, y, z = 0) => G.T(x, y, z);
const OFFCOL = [0.015, 0.015, 0.017];
const glowC = (c, k) => c.map((v) => v * 1.4 * k);

function mixerItems(fs) {
  const it = [], cols = [PINK, CYAN];
  const P = (mesh, M, col, rough, metal, emis = [0, 0, 0]) => it.push([mesh, M, col, rough, metal, emis]);
  P(MX.body, G.ident(), [0.012, 0.012, 0.013], 0.6, 0);
  P(MX.plate, G.ident(), [0.045, 0.047, 0.052], 0.42, 0.75);
  for (let i = 0; i < 2; i++) {
    const s = fs.d[i], col = cols[i], lit = s.on ? 0.35 + 0.65 * s.g : 0.08, x = KX[i];
    // EQ lanes: 1 = flat (noon), 0 = kill (fully CCW). No mid lane in the engine -> MID stays at noon.
    for (const [key, v] of [['hi', s.hi], ['mid', 1], ['lo', s.lo]]) {
      const y = KY[key], kv = 0.5 * v, ang = (0.5 - kv) * 1.5 * Math.PI;
      P(MX.knob, T(x, y), [0.03, 0.03, 0.034], 0.32, 0.6);
      P(MX.ptr, G.chain(T(x, y), G.Rz(ang)), [0.8, 0.8, 0.82], 0.3, 0, [0.5, 0.5, 0.52]);
      for (let k = 0; k < 11; k++) {                                    // LED ring, lit from min up to the knob value
        const a = (0.75 + 1.5 * (k / 10)) * Math.PI, on = k / 10 <= kv + 1e-3 && key !== 'mid' ? 1 : (key === 'mid' && k === 5 ? 0.6 : 0);
        const lx = x + 0.0165 * Math.cos(-a + Math.PI), ly = y + 0.0165 * Math.sin(-a + Math.PI);
        P(MX.led, T(lx, ly), OFFCOL, 0.4, 0, glowC(col, on * lit));
      }
    }
    // channel fader (engine gain lane)
    P(MX.slot, T(x, 0), [0.003, 0.003, 0.003], 0.3, 0);
    for (let k = 0; k <= 10; k++) P(MX.tick, T(x + (k % 5 === 0 ? 0.0145 : 0.0135), FAD[0] + (FAD[1] - FAD[0]) * k / 10), [0.25, 0.25, 0.27], 0.5, 0);
    const fy = FAD[0] + (FAD[1] - FAD[0]) * s.g;
    P(MX.cap, T(x, fy), [0.05, 0.05, 0.055], 0.35, 0.4);
    P(MX.capLine, T(x, fy), col, 0.4, 0, glowC(col, 0.25 + 0.75 * lit));
    // level meter (approx: track energy x gain), 16 LEDs beside the fader
    const mx = i === 0 ? -0.020 : 0.020;
    for (let k = 0; k < 16; k++) {
      const on = s.lvl * 16 > k ? 1 : 0, c = k > 13 ? [1, 0.25, 0.25] : k > 10 ? [1, 0.8, 0.3] : col;
      P(MX.led, T(mx, FAD[0] + 0.003 + k * 0.0058), OFFCOL, 0.4, 0, glowC(c, on));
    }
  }
  P(MX.xslot, G.ident(), [0.003, 0.003, 0.003], 0.3, 0);
  const xx = XF[0] + (XF[1] - XF[0]) * fs.xf, xc = PINK.map((v, k) => v * (1 - fs.xf) + CYAN[k] * fs.xf);
  P(MX.xcap, T(xx, XF[2]), [0.05, 0.05, 0.055], 0.35, 0.4);
  P(MX.xcapLine, T(xx, XF[2]), xc, 0.4, 0, glowC(xc, 0.8));
  for (let k = 0; k < 16; k++) {                                        // master meter (real, from the mix mp3)
    const on = fs.m * 16 > k ? 1 : 0, c = k > 13 ? [1, 0.25, 0.25] : k > 10 ? [1, 0.8, 0.3] : [0.85, 0.9, 1.0];
    P(MX.led, T(0, FAD[0] + 0.003 + k * 0.0058), OFFCOL, 0.4, 0, glowC(c, on * 0.8));
  }
  return it;
}

function drawMixerPass(fs, camIn) {
  const gl = R.gl, cam = R.camera({ ...(camIn || CAM), zoom: 0, al: 0 });
  const items = mixerItems(fs);
  const casters = [[MX.body, G.ident()], [MX.plate, G.ident()]];
  for (const o of OFF) for (const mm of [R.m.body, R.m.plate, R.m.feet, R.m.platter, R.m.tower]) casters.push([mm, T(o[0], o[1], o[2])]);
  for (const x of items) casters.push([x[0], x[1]]);
  gl.bindFramebuffer(gl.FRAMEBUFFER, R.fbo); gl.viewport(0, 0, SHADOW_SIZE, SHADOW_SIZE); gl.clear(gl.DEPTH_BUFFER_BIT);
  gl.useProgram(R.dep.p); gl.uniformMatrix4fv(R.dep.u.uVP, false, MX.lvp);
  gl.enable(gl.POLYGON_OFFSET_FILL); gl.polygonOffset(2, 4);
  for (const [mesh, M] of casters) { gl.uniformMatrix4fv(R.dep.u.uM, false, M); gl.bindVertexArray(mesh.vao); gl.drawArrays(gl.TRIANGLES, 0, mesh.count); }
  gl.disable(gl.POLYGON_OFFSET_FILL);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, W, H);
  gl.activeTexture(gl.TEXTURE3); gl.bindTexture(gl.TEXTURE_2D, R.tex.shadow);
  const u = R.std.u; gl.useProgram(R.std.p);
  gl.uniformMatrix4fv(u.uVP, false, cam.vp); gl.uniformMatrix4fv(u.uLVP, false, MX.lvp); gl.uniform3fv(u.uEye, cam.eye);
  gl.uniform1i(u.uShadow, 3); gl.uniform4f(u.uLamp, 0, 0, 0, 0); gl.uniform1f(u.uKeyGain, 0.6); gl.uniform2f(u.uPivot, 9, 9);
  const all = [[MX.table, G.ident(), [0.018, 0.018, 0.02], 0.6, 0, [0, 0, 0]], ...items];
  for (const [mesh, M, col, rough, metal, emis] of all) {
    gl.uniformMatrix4fv(u.uM, false, M); gl.uniform3fv(u.uCol, col); gl.uniform3fv(u.uEmis, emis);
    gl.uniform1f(u.uRough, rough); gl.uniform1f(u.uMetal, metal); gl.uniform1i(u.uMode, 0);
    gl.bindVertexArray(mesh.vao); gl.drawArrays(gl.TRIANGLES, 0, mesh.count);
  }
  return cam;
}

// faceplate text, projected into the same perspective (affine per label)
function proj(vp, p) {
  const x = vp[0] * p[0] + vp[4] * p[1] + vp[8] * p[2] + vp[12], y = vp[1] * p[0] + vp[5] * p[1] + vp[9] * p[2] + vp[13];
  const w = vp[3] * p[0] + vp[7] * p[1] + vp[11] * p[2] + vp[15];
  return [(x / w * 0.5 + 0.5) * W, (0.5 - y / w * 0.5) * H];
}
function plateText(cam, x, y, txt, sizeMM, col, weight = 600) {
  const z = TOP_Z + 0.0003, u = 0.001, o = proj(cam.vp, [x, y, z]), ex = proj(cam.vp, [x + u, y, z]), ey = proj(cam.vp, [x, y - u, z]);
  ctx.save(); ctx.setTransform(ex[0] - o[0], ex[1] - o[1], ey[0] - o[0], ey[1] - o[1], o[0], o[1]);
  ctx.font = `${weight} ${sizeMM}px DejaVu Sans, sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = col;
  ctx.fillText(txt, 0, 0); ctx.restore();
}
function mixerLabels(cam) {
  const g = 'rgba(200,205,222,0.62)';
  plateText(cam, 0, 0.178, 'GROKBOT · MIXER', 7, 'rgba(220,224,236,0.8)', 700);
  plateText(cam, KX[0], 0.163, 'CH 1', 6, css(PINK, 0.9), 700); plateText(cam, KX[1], 0.163, 'CH 2', 6, css(CYAN, 0.9), 700);
  for (const [k, n] of [['hi', 'HIGH'], ['mid', 'MID'], ['lo', 'LOW']]) plateText(cam, 0, KY[k], n, 5, g);
  plateText(cam, 0, FAD[0] - 0.010, 'LVL', 4.5, g);
  for (const x of KX) plateText(cam, x, FAD[0] - 0.015, 'GAIN', 5, g);
  plateText(cam, 0, XF[2] - 0.022, 'CROSSFADER', 5, g);
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
  if (!MX) buildMixer();
  const gl = R.gl; gl.viewport(0, 0, W, H); gl.clearColor(0.004, 0.004, 0.005, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  const camP = camFor(fs);
  const cam = drawMixerPass(fs, camP);                  // table + mixer first (fills depth), then the two decks
  for (let i = 0; i < 2; i++) {
    const rr = D.recs[i];
    R.info = rr.info; R.tex.label = rr.label; R.tex.vis = rr.vis; R.tex.lut = rr.lut;
    R.draw(deckState(i, fs, camP));
  }
  gl.finish();
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
  ctx.drawImage(glc, 0, 0);
  mixerLabels(cam);
  let g = ctx.createLinearGradient(0, 0, 0, 230); g.addColorStop(0, 'rgba(0,0,0,0.85)'); g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, 230);
  g = ctx.createRadialGradient(W / 2, H / 2, H * 0.5, W / 2, H / 2, H * 1.1); g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,0.55)');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  hud(fs, t);
  if (noEncode) return '';
  return out.toDataURL(fmt, q);
};
