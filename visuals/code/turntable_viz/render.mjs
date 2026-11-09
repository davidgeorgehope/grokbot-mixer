// Offline frame capture for turntable_viz: headless Chrome (SwiftShader WebGL2) -> JPEG frames -> ffmpeg (+ mix audio).
// usage: node render.mjs --data data.json --out out.mp4 --mix mix.mp3 [--from 0 --to N] [--still F --png out.png]
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path'; import { spawn } from 'node:child_process';
import puppeteer from 'puppeteer-core';
const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, arr) => (v.startsWith('--') && a.push([v.slice(2), arr[i + 1]]), a), []));
const ROOT = path.dirname(new URL(import.meta.url).pathname), DATA = path.resolve(args.data);
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json' };
const srv = http.createServer((q, r) => {
  const u = decodeURIComponent(q.url.split('?')[0]), f = u === '/data.json' ? DATA : path.join(ROOT, u);
  fs.readFile(f, (e, b) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { 'content-type': MIME[path.extname(f)] || 'application/octet-stream' }); r.end(b); });
}).listen(0, '127.0.0.1');
await new Promise((ok) => srv.once('listening', ok));
const port = srv.address().port;
const browser = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', headless: true,
  args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--disable-dev-shm-usage', '--window-size=1920,1080'] });
const page = await browser.newPage();
page.on('console', (m) => console.log('[page]', m.text())); page.on('pageerror', (e) => console.log('[pageerror]', e.message));
const gopt = JSON.parse(args.gl || '{}');
await page.evaluateOnNewDocument((g) => { if (g.shadow) globalThis.TT_SHADOW = g.shadow; if (g.aa !== undefined) globalThis.TT_AA = g.aa; }, gopt);
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: 'load' });
await page.waitForFunction('window.setup && window.renderFrame');
const info = await page.evaluate((o) => window.setup('/data.json', o), JSON.parse(args.opts || '{}'));
const dec = (u) => Buffer.from(u.slice(u.indexOf(',') + 1), 'base64');
try {
  if (args.prof) {
    for (const mode of ['full', 'glonly']) { const t0 = Date.now();
      for (let f = 400; f < 420; f++) await page.evaluate((f, m) => { if (m === 'glonly') { window.renderFrame(f, 'image/jpeg', 0.9, true); return 1; } return window.renderFrame(f).length; }, f, mode);
      console.log(mode, ((Date.now() - t0) / 20).toFixed(0), 'ms/frame'); }
  } else if (args.still) {
    for (const f of args.still.split(',')) {
      const u = await page.evaluate((f) => window.renderFrame(f, 'image/png'), +f);
      const o = args.png.replace('%d', f); fs.writeFileSync(o, dec(u)); console.log('still', f, '->', o);
    }
  } else {
    const from = +(args.from || 0), to = Math.min(+(args.to || info.frames), info.frames), fps = info.fps;
    const mixOff = await page.evaluate(() => window.D_mixOffset || 0);
    const ffa = ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-c:v', 'mjpeg', '-framerate', String(fps), '-i', '-'];
    if (args.mix) ffa.push('-ss', String(+args.ss + from / fps), '-t', String((to - from) / fps), '-i', args.mix, '-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '192k', '-shortest');
    ffa.push('-c:v', 'libx264', '-preset', 'medium', '-crf', String(args.crf || 18), '-pix_fmt', 'yuv420p', '-movflags', '+faststart', args.out);
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
    console.log(`RENDER_DONE frames=${to - from} wall=${el.toFixed(1)}s speed=${((to - from) / fps / el).toFixed(3)}x realtime`);
  }
} finally { await browser.close(); srv.close(); }
