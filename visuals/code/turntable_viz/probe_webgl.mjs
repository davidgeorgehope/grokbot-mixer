// Probe Chrome WebGL2 backends on this machine. Prints one line per attempt:
 //   TRY <name> -> ok renderer=<...> | FAIL <reason>
// Exits 0 if any real GPU backend works; 2 if only software; 1 on hard failure.
import puppeteer from 'puppeteer-core';
const CHROME = process.env.CHROME_PATH || '/usr/bin/google-chrome-stable';
const base = ['--no-sandbox', '--ignore-gpu-blocklist', '--disable-dev-shm-usage',
  '--window-size=640,360', '--enable-webgl', '--enable-webgl2', '--enable-gpu',
  '--disable-gpu-sandbox', '--disable-software-rasterizer', '--headless=new'];

const variants = {
  egl: ['--use-gl=egl', '--enable-gpu-rasterization'],
  egl_angle: ['--use-gl=angle', '--use-angle=gl-egl', '--enable-gpu-rasterization'],
  vulkan: ['--use-gl=angle', '--use-angle=vulkan', '--enable-features=Vulkan', '--disable-vulkan-surface'],
  angle_gl: ['--use-gl=angle', '--use-angle=gl'],
  desktop: ['--use-gl=desktop'],
};

function isSoft(r) {
  const s = (r || '').toLowerCase();
  return !s || s.includes('swiftshader') || s.includes('llvmpipe') || s.includes('softpipe') || s.includes('microsoft basic');
}

async function tryOne(name, extra) {
  let browser;
  try {
    browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: [...base, ...extra] });
    const page = await browser.newPage();
    const info = await page.evaluate(() => {
      const c = document.createElement('canvas');
      const gl2 = c.getContext('webgl2', { antialias: false });
      if (!gl2) return { ok: false, reason: 'no-webgl2', vendor: '', renderer: '' };
      const ext = gl2.getExtension('WEBGL_debug_renderer_info');
      return {
        ok: true,
        vendor: String(ext ? gl2.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl2.getParameter(gl2.VENDOR) || ''),
        renderer: String(ext ? gl2.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl2.getParameter(gl2.RENDERER) || ''),
      };
    });
    await browser.close();
    if (!info.ok) { console.log(`TRY ${name} -> FAIL ${info.reason}`); return null; }
    const soft = isSoft(info.renderer);
    console.log(`TRY ${name} -> ${soft ? 'SOFT' : 'ok'} vendor=${info.vendor.replace(/\s+/g, '_')} renderer=${info.renderer.replace(/\s+/g, '_')}`);
    return soft ? null : { name, ...info };
  } catch (e) {
    try { await browser?.close(); } catch {}
    console.log(`TRY ${name} -> FAIL ${String(e.message || e).slice(0, 120)}`);
    return null;
  }
}

let winner = null;
for (const [name, extra] of Object.entries(variants)) {
  const r = await tryOne(name, extra);
  if (r && !winner) winner = r;
}
if (!winner) {
  console.log('PROBE_FAIL no hardware WebGL2');
  process.exit(2);
}
console.log(`PROBE_OK backend=${winner.name} renderer=${winner.renderer.replace(/\s+/g, '_')}`);
process.exit(0);
