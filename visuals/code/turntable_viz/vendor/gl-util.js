// Minimal WebGL2 helpers: matrices (column-major), meshes (interleaved position + normal), programs.

export const mul = (a, b) => {
  const o = new Float32Array(16);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
    o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
  }
  return o;
};
export const chain = (...m) => m.reduce(mul);
export const ident = () => new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
export const T = (x, y, z) => { const m = ident(); m[12] = x; m[13] = y; m[14] = z; return m; };
export const Rz = (a) => { const m = ident(), c = Math.cos(a), s = Math.sin(a); m[0] = c; m[1] = s; m[4] = -s; m[5] = c; return m; };
export const Ry = (a) => { const m = ident(), c = Math.cos(a), s = Math.sin(a); m[0] = c; m[2] = -s; m[8] = s; m[10] = c; return m; };
export function perspective(fovy, aspect, near, far) {
  const f = 1 / Math.tan(fovy / 2), m = new Float32Array(16);
  m[0] = f / aspect; m[5] = f; m[10] = (far + near) / (near - far); m[11] = -1; m[14] = 2 * far * near / (near - far);
  return m;
}
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
export const norm = (a) => { const l = Math.hypot(a[0], a[1], a[2]); return [a[0] / l, a[1] / l, a[2] / l]; };
// returns { m, right, up, fwd } so the same basis can be used for picking rays
export function lookAt(eye, at, upHint = [0, 0, 1]) {
  const f = norm(sub(at, eye)), r = norm(cross(f, upHint)), u = cross(r, f);
  const m = new Float32Array([r[0], u[0], -f[0], 0, r[1], u[1], -f[1], 0, r[2], u[2], -f[2], 0,
    -(r[0] * eye[0] + r[1] * eye[1] + r[2] * eye[2]), -(u[0] * eye[0] + u[1] * eye[1] + u[2] * eye[2]), f[0] * eye[0] + f[1] * eye[1] + f[2] * eye[2], 1]);
  return { m, right: r, up: u, fwd: f };
}

// --- meshes: arrays of [px,py,pz,nx,ny,nz] per vertex, triangles ---
const tri = (v, a, b, c) => { v.push(...a, ...b, ...c); };
// frustum/cylinder about +z from z0 (radius r0) to z1 (radius r1), with caps
export function cyl(r0, r1, z0, z1, seg = 64, caps = true) {
  const v = [], sl = (r0 - r1) / (z1 - z0);
  for (let i = 0; i < seg; i++) {
    const a0 = i / seg * 2 * Math.PI, a1 = (i + 1) / seg * 2 * Math.PI;
    const c0 = Math.cos(a0), s0 = Math.sin(a0), c1 = Math.cos(a1), s1 = Math.sin(a1);
    const n0 = norm([c0, s0, sl]), n1 = norm([c1, s1, sl]);
    const A = [r0 * c0, r0 * s0, z0, ...n0], B = [r0 * c1, r0 * s1, z0, ...n1], C = [r1 * c1, r1 * s1, z1, ...n1], D = [r1 * c0, r1 * s0, z1, ...n0];
    tri(v, A, B, C); tri(v, A, C, D);
    if (caps) {
      tri(v, [0, 0, z1, 0, 0, 1], [r1 * c0, r1 * s0, z1, 0, 0, 1], [r1 * c1, r1 * s1, z1, 0, 0, 1]);
      tri(v, [0, 0, z0, 0, 0, -1], [r0 * c1, r0 * s1, z0, 0, 0, -1], [r0 * c0, r0 * s0, z0, 0, 0, -1]);
    }
  }
  return new Float32Array(v);
}
// same, but along +x (for tubes)
export function cylX(r, x0, x1, seg = 24) {
  const v = cyl(r, r, x0, x1, seg);
  for (let i = 0; i < v.length; i += 3) { const x = v[i], y = v[i + 1], z = v[i + 2]; v[i] = z; v[i + 1] = x; v[i + 2] = y; }
  return v;
}
export function box(x0, y0, z0, x1, y1, z1) {
  const v = [], q = (a, b, c, d, n) => { tri(v, [...a, ...n], [...b, ...n], [...c, ...n]); tri(v, [...a, ...n], [...c, ...n], [...d, ...n]); };
  q([x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1], [0, 0, 1]);
  q([x0, y1, z0], [x1, y1, z0], [x1, y0, z0], [x0, y0, z0], [0, 0, -1]);
  q([x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1], [0, -1, 0]);
  q([x1, y1, z0], [x0, y1, z0], [x0, y1, z1], [x1, y1, z1], [0, 1, 0]);
  q([x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1], [1, 0, 0]);
  q([x0, y1, z0], [x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [-1, 0, 0]);
  return new Float32Array(v);
}
// flat annulus in the z=0 plane as a polar grid (so it can be warped in the vertex shader)
export function annulus(r0, r1, nr = 48, na = 160) {
  const v = [], P = (i, j) => { const r = r0 + (r1 - r0) * i / nr, a = j / na * 2 * Math.PI; return [r * Math.cos(a), r * Math.sin(a), 0, 0, 0, 1]; };
  for (let i = 0; i < nr; i++) for (let j = 0; j < na; j++) { tri(v, P(i, j), P(i + 1, j), P(i + 1, j + 1)); tri(v, P(i, j), P(i + 1, j + 1), P(i, j + 1)); }
  return new Float32Array(v);
}

export function mesh(gl, data) {
  const vao = gl.createVertexArray(), buf = gl.createBuffer();
  gl.bindVertexArray(vao); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 24, 0);
  gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 24, 12);
  gl.bindVertexArray(null);
  return { vao, count: data.length / 6 };
}
export function program(gl, vs, fs) {
  const p = gl.createProgram();
  for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
    const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) + '\n' + src.split('\n').map((l, i) => `${i + 1}: ${l}`).join('\n'));
    gl.attachShader(p, s);
  }
  gl.bindAttribLocation(p, 0, 'aP'); gl.bindAttribLocation(p, 1, 'aN');
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  const u = {}, n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < n; i++) { const name = gl.getActiveUniform(p, i).name.replace(/\[0\]$/, ''); u[name] = gl.getUniformLocation(p, name); }
  return { p, u };
}

// ---------- extra builders for the detailed deck ----------
export function ortho(l, r, b, t, n, f) {
  const m = new Float32Array(16);
  m[0] = 2 / (r - l); m[5] = 2 / (t - b); m[10] = -2 / (f - n);
  m[12] = -(r + l) / (r - l); m[13] = -(t + b) / (t - b); m[14] = -(f + n) / (f - n); m[15] = 1;
  return m;
}
// surface of revolution about +z. pts = [[r, z], ...] ordered bottom-centre -> out -> up -> in, flat per segment
export function lathe(pts, seg = 72) {
  const v = [];
  for (let k = 0; k + 1 < pts.length; k++) {
    const [r0, z0] = pts[k], [r1, z1] = pts[k + 1], l = Math.hypot(r1 - r0, z1 - z0) || 1, nr = (z1 - z0) / l, nz = -(r1 - r0) / l;
    for (let i = 0; i < seg; i++) {
      const a0 = i / seg * 2 * Math.PI, a1 = (i + 1) / seg * 2 * Math.PI, c0 = Math.cos(a0), s0 = Math.sin(a0), c1 = Math.cos(a1), s1 = Math.sin(a1);
      const A = [r0 * c0, r0 * s0, z0, nr * c0, nr * s0, nz], B = [r0 * c1, r0 * s1, z0, nr * c1, nr * s1, nz];
      const C = [r1 * c1, r1 * s1, z1, nr * c1, nr * s1, nz], D = [r1 * c0, r1 * s0, z1, nr * c0, nr * s0, nz];
      tri(v, A, B, C); tri(v, A, C, D);
    }
  }
  return new Float32Array(v);
}
// re-axis a z-axis mesh so its axis is +x
export function alongX(v) {
  for (let i = 0; i < v.length; i += 3) { const x = v[i], y = v[i + 1], z = v[i + 2]; v[i] = z; v[i + 1] = x; v[i + 2] = y; }
  return v;
}
// round tube swept along a polyline of [x, y, z] points
export function tube(path, r, seg = 16) {
  const v = [], rings = [];
  for (let i = 0; i < path.length; i++) {
    const p = path[i], a = path[Math.max(0, i - 1)], b = path[Math.min(path.length - 1, i + 1)];
    const t = norm(sub(b, a)), n = norm(cross([0, 0, 1], t)), bn = cross(t, n), ring = [];
    for (let j = 0; j <= seg; j++) {
      const an = j / seg * 2 * Math.PI, c = Math.cos(an), s = Math.sin(an), d = [n[0] * c + bn[0] * s, n[1] * c + bn[1] * s, n[2] * c + bn[2] * s];
      ring.push([p[0] + r * d[0], p[1] + r * d[1], p[2] + r * d[2], d[0], d[1], d[2]]);
    }
    rings.push(ring);
  }
  for (let i = 0; i + 1 < rings.length; i++) for (let j = 0; j < seg; j++) {
    tri(v, rings[i][j], rings[i + 1][j], rings[i + 1][j + 1]); tri(v, rings[i][j], rings[i + 1][j + 1], rings[i][j + 1]);
  }
  return new Float32Array(v);
}
export function bezier(p0, p1, p2, p3, n = 28) {
  const out = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n, u = 1 - t, a = u * u * u, b = 3 * u * u * t, c = 3 * u * t * t, d = t * t * t;
    out.push([0, 1, 2].map((k) => a * p0[k] + b * p1[k] + c * p2[k] + d * p3[k]));
  }
  return out;
}
// rounded-rectangle slab with a chamfered top edge
export function rbox(x0, y0, x1, y1, z0, z1, rad = 0.004, ch = 0.001, n = 6) {
  const o = [], v = [];
  for (const [cx, cy, a0] of [[x1 - rad, y1 - rad, 0], [x0 + rad, y1 - rad, 0.5], [x0 + rad, y0 + rad, 1], [x1 - rad, y0 + rad, 1.5]]) {
    for (let i = 0; i <= n; i++) { const a = (a0 + 0.5 * i / n) * Math.PI, c = Math.cos(a), s = Math.sin(a); o.push([cx + rad * c, cy + rad * s, c, s]); }
  }
  const zc = z1 - ch, k = Math.SQRT1_2, mx = (x0 + x1) / 2, my = (y0 + y1) / 2;
  for (let i = 0; i < o.length; i++) {
    const a = o[i], b = o[(i + 1) % o.length];
    const ai = [a[0] - a[2] * ch, a[1] - a[3] * ch], bi = [b[0] - b[2] * ch, b[1] - b[3] * ch];
    tri(v, [a[0], a[1], z0, a[2], a[3], 0], [b[0], b[1], z0, b[2], b[3], 0], [b[0], b[1], zc, b[2], b[3], 0]);
    tri(v, [a[0], a[1], z0, a[2], a[3], 0], [b[0], b[1], zc, b[2], b[3], 0], [a[0], a[1], zc, a[2], a[3], 0]);
    tri(v, [a[0], a[1], zc, a[2] * k, a[3] * k, k], [b[0], b[1], zc, b[2] * k, b[3] * k, k], [bi[0], bi[1], z1, b[2] * k, b[3] * k, k]);
    tri(v, [a[0], a[1], zc, a[2] * k, a[3] * k, k], [bi[0], bi[1], z1, b[2] * k, b[3] * k, k], [ai[0], ai[1], z1, a[2] * k, a[3] * k, k]);
    tri(v, [mx, my, z1, 0, 0, 1], [ai[0], ai[1], z1, 0, 0, 1], [bi[0], bi[1], z1, 0, 0, 1]);
  }
  return new Float32Array(v);
}
// concatenate meshes, optionally offsetting each: merge([data, [dx, dy, dz]], ...)
export function merge(...parts) {
  const items = parts.map((p) => (Array.isArray(p) ? p : [p, [0, 0, 0]]));
  const out = new Float32Array(items.reduce((a, [d]) => a + d.length, 0));
  let o = 0;
  for (const [d, off] of items) {
    for (let i = 0; i < d.length; i += 6) { out[o++] = d[i] + off[0]; out[o++] = d[i + 1] + off[1]; out[o++] = d[i + 2] + off[2]; out[o++] = d[i + 3]; out[o++] = d[i + 4]; out[o++] = d[i + 5]; }
  }
  return out;
}
