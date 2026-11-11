// Offline frame capture for turntable_viz: headless Chrome WebGL2 -> JPEG frames -> ffmpeg.
// usage: node render.mjs --data data.json --out out.mp4 [--from 0 --to N] [--still F --png out.png] [--check N]
//        [--backend auto|gpu|cpu]  auto prefers GPU (egl/vulkan) and falls back to SwiftShader;
//        gpu fails closed if the WebGL renderer is SwiftShader/llvmpipe/softpipe.
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path'; import { spawn } from 'node:child_process';
import puppeteer from 'puppeteer-core';
const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, arr) => (v.startsWith('--') && a.push([v.slice(2), arr[i + 1]]), a), []));
const ROOT = path.dirname(new URL(import.meta.url).pathname), DATA = path.resolve(args.data);
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json' };
const BACKEND = (args.backend || process.env.TT_BACKEND || 'auto').toLowerCase();
const CHROME = process.env.CHROME_PATH || '/usr/bin/google-chrome';

function chromeArgs(backend) {
  const base = ['--no-sandbox', '--ignore-gpu-blocklist', '--disable-dev-shm-usage', '--window-size=1920,1080',
    '--enable-webgl', '--enable-webgl2', '--disable-gpu-sandbox', '--headless=new'];
  if (backend === 'cpu') {
    return [...base, '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--use-gl=angle'];
  }
  // GPU path — never enable SwiftShader. TT_GL selects the backend (egl|vulkan|egl_angle|angle_gl|desktop).
  const gl = process.env.TT_GL || 'egl';
  const gpu = ['--enable-gpu', '--disable-software-rasterizer', '--enable-gpu-rasterization'];
  if (gl === 'vulkan') return [...base, ...gpu, '--use-gl=angle', '--use-angle=vulkan', '--enable-features=Vulkan', '--disable-vulkan-surface'];
  if (gl === 'egl_angle') return [...base, ...gpu, '--use-gl=angle', '--use-angle=gl-egl'];
  if (gl === 'angle' || gl === 'angle_gl') return [...base, ...gpu, '--use-gl=angle', '--use-angle=gl'];
  if (gl === 'desktop') return [...base, ...gpu, '--use-gl=desktop'];
  return [...base, ...gpu, '--use-gl=egl'];
}

function isSoftwareRenderer(name) {
  const s = (name || '').toLowerCase();
  return !s || s === 'no-webgl' || s.includes('swiftshader') || s.includes('llvmpipe') || s.includes('softpipe') || s.includes('microsoft basic render');
}

const srv = http.createServer((q, r) => {
  const u = decodeURIComponent(q.url.split('?')[0]), f = u === '/data.json' ? DATA : path.join(ROOT, u);
  fs.readFile(f, (e, b) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { 'content-type': MIME[path.extname(f)] || 'application/octet-stream' }); r.end(b); });
}).listen(0, '127.0.0.1');
await new Promise((ok) => srv.once('listening', ok));
const port = srv.address().port;

async function launch(backend) {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: chromeArgs(backend) });
  const page = await browser.newPage();
  page.on('console', (m) => console.log('[page]', m.text())); page.on('pageerror', (e) => console.log('[pageerror]', e.message));
  const gopt = JSON.parse(args.gl || '{}');
  await page.evaluateOnNewDocument((g) => { if (g.shadow) globalThis.TT_SHADOW = g.shadow; if (g.aa !== undefined) globalThis.TT_AA = g.aa; }, gopt);
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: 'load' });
  await page.waitForFunction('window.setup && window.renderFrame');
  // Probe WebGL before scene setup so we can fail closed without depending on the Renderer ctor.
  const glInfo = await page.evaluate(() => {
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl2') || c.getContext('webgl');
    if (!gl) return { ok: false, vendor: '', renderer: 'no-webgl' };
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    const vendor = ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR);
    const renderer = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    return { ok: true, vendor: String(vendor || ''), renderer: String(renderer || '') };
  });
  // Soft/missing GL: skip setup (Renderer ctor needs WebGL2). Caller decides fail-closed vs CPU fallback.
  if (isSoftwareRenderer(glInfo.renderer) && backend !== 'cpu') {
    return { browser, page, info: null, glInfo };
  }
  const info = await page.evaluate((o) => window.setup('/data.json', o), JSON.parse(args.opts || '{}'));
  return { browser, page, info, glInfo };
}

let backend = BACKEND === 'gpu' ? 'gpu' : BACKEND === 'cpu' ? 'cpu' : 'gpu';
let browser, page, info, glInfo;
try {
  ({ browser, page, info, glInfo } = await launch(backend === 'cpu' ? 'cpu' : 'gpu'));
  console.log(`WEBGL vendor=${glInfo.vendor} renderer=${glInfo.renderer} backend_requested=${BACKEND}`);
  if (BACKEND === 'gpu' && isSoftwareRenderer(glInfo.renderer)) {
    await browser.close();
    throw new Error(`GPU backend required but WebGL renderer is software: ${glInfo.renderer}`);
  }
  if (BACKEND === 'auto' && isSoftwareRenderer(glInfo.renderer)) {
    console.log('auto: GPU unavailable, falling back to SwiftShader');
    await browser.close();
    ({ browser, page, info, glInfo } = await launch('cpu'));
    console.log(`WEBGL vendor=${glInfo.vendor} renderer=${glInfo.renderer} backend_requested=auto(fallback-cpu)`);
  }
  if (!info) {
    // cpu launch path always sets up; this guards a bad state
    info = await page.evaluate((o) => window.setup('/data.json', o), JSON.parse(args.opts || '{}'));
  }
  if (BACKEND === 'cpu' && !isSoftwareRenderer(glInfo.renderer)) {
    console.log('cpu backend requested; using launched GL as-is');
  }
  const dec = (u) => Buffer.from(u.slice(u.indexOf(',') + 1), 'base64');
  try {
    if (args.prof) {
      for (const mode of ['full', 'glonly']) { const t0 = Date.now();
        for (let f = 400; f < 420; f++) await page.evaluate((f, m) => { if (m === 'glonly') { window.renderFrame(f, 'image/jpeg', 0.9, true); return 1; } return window.renderFrame(f).length; }, f, mode);
        console.log(mode, ((Date.now() - t0) / 20).toFixed(0), 'ms/frame'); }
    } else if (args.check) {
      // --check [N]: sample N frames across every dive window (plus booth frames) and fail if an in-frame deck is not drawn.
      const D = await page.evaluate(() => ({ dives: window.__dives(), n: window.__nframes(), fps: window.__fps() }));
      const per = +args.check || 24, frames = new Set();
      for (const dv of D.dives) for (let k = 0; k <= per; k++) frames.add(Math.round(dv.f0 + (dv.f1 - dv.f0) * k / per));
      for (let k = 0; k < 4; k++) frames.add(Math.round((D.n - 1) * k / 3));
      let bad = 0;
      for (const f of [...frames].filter((f) => f >= 0 && f < D.n).sort((a, b) => a - b)) {
        const r = await page.evaluate((f) => window.deckCheck(f), f);
        const errs = [];
        for (const d of r.decks) if (d.inFrame >= 0.05 && d.drawn < 0.6) errs.push(`deck ${d.deck + 1} in frame (${(d.inFrame * 100).toFixed(0)}% of plate) but only ${(d.drawn * 100).toFixed(0)}% drawn`);
        if (r.k < 1e-4 && r.decks.some((d) => d.inFrame < 0.9)) errs.push('booth shot does not show both full decks');
        if (r.stylus && (r.stylus.x < 0.2 || r.stylus.x > 0.8 || r.stylus.y < 0.2 || r.stylus.y > 0.8)) errs.push(`dive peak: stylus off-centre at (${r.stylus.x.toFixed(2)}, ${r.stylus.y.toFixed(2)})`);
        const line = `f=${f} bar=${r.mb.toFixed(2)} dive=${r.k.toFixed(2)} near=${r.near.toFixed(4)} ` + r.decks.map((d) => `d${d.deck + 1}:inFrame=${d.inFrame.toFixed(2)},drawn=${d.drawn.toFixed(2)}`).join(' ');
        console.log((errs.length ? 'FAIL ' : 'ok   ') + line + (errs.length ? '  <- ' + errs.join('; ') : ''));
        bad += errs.length ? 1 : 0;
      }
      console.log(bad ? `DECK_CHECK_FAIL ${bad} frame(s)` : `DECK_CHECK_OK ${frames.size} frames, ${D.dives.length} dive(s)`);
      if (bad) process.exitCode = 1;
    } else if (args.still) {
      for (const f of args.still.split(',')) {
        const u = await page.evaluate((f) => window.renderFrame(f, 'image/png'), +f);
        const o = args.png.replace('%d', f); fs.writeFileSync(o, dec(u)); console.log('still', f, '->', o);
      }
    } else {
      const from = +(args.from || 0), to = Math.min(+(args.to || info.frames), info.frames), fps = info.fps;
      const ffa = ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-c:v', 'mjpeg', '-framerate', String(fps), '-i', '-'];
      if (args.mix) ffa.push('-ss', String(+args.ss + from / fps), '-t', String((to - from) / fps), '-i', args.mix, '-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '192k', '-shortest');
      ffa.push('-c:v', 'libx264', '-preset', 'medium', '-crf', String(args.crf || 18), '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-f', 'mp4', args.out);
      const ff = spawn('ffmpeg', ffa, { stdio: ['pipe', 'inherit', 'inherit'] });
      const t0 = Date.now();
      for (let f = from; f < to; f++) {
        const u = await page.evaluate((f) => window.renderFrame(f), f);
        if (!ff.stdin.write(dec(u))) await new Promise((ok) => ff.stdin.once('drain', ok));
        if ((f - from + 1) % 30 === 0 || f === to - 1) {
          const el = (Date.now() - t0) / 1000, done = f - from + 1, rf = done / el;
          console.log(`${done}/${to - from} frames  ${rf.toFixed(2)} fps  ${(rf / fps).toFixed(3)}x realtime  ETA ${((to - from - done) / rf).toFixed(0)}s`);
        }
      }
      ff.stdin.end(); await new Promise((ok, no) => ff.on('close', (c) => (c ? no(new Error('ffmpeg ' + c)) : ok())));
      const el = (Date.now() - t0) / 1000;
      console.log(`RENDER_DONE frames=${to - from} wall=${el.toFixed(1)}s speed=${((to - from) / fps / el).toFixed(3)}x realtime renderer=${glInfo.renderer.replace(/\s+/g, '_')}`);
    }
  } finally { await browser.close(); }
} finally { srv.close(); }
