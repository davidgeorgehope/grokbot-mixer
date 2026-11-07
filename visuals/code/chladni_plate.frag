#version 330
in vec2 uv;
out vec4 C;
uniform vec2 res;
uniform float time, flow, bass, mid, high, kick, snare, rms, beat;
uniform float mixAB, n0, m0, n1, m1;
uniform vec3 colA, colB;
uniform sampler2D card;
uniform float cardA, cardT;

float PI = 3.14159265359;

float hash(vec2 p){
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float chladni(vec2 p, float n, float m){
    return cos(n*PI*p.x)*cos(m*PI*p.y) - cos(m*PI*p.x)*cos(n*PI*p.y);
}

void main(){
    vec2 c = uv - 0.5;
    // kick tosses sand outward from centre; snare adds a brief plate wobble
    float toss = 1.0 + kick*0.10 + snare*0.03;
    vec2 p = 0.5 + c * toss;
    p += 0.008 * vec2(sin(flow*0.7 + p.y*6.0), cos(flow*0.55 + p.x*5.0)) * (0.4 + rms);

    float F0 = chladni(p, max(n0,1.0), max(m0,1.0));
    float F1 = chladni(p, max(n1,2.0), max(m1,3.0));
    float w = clamp(0.15 + 0.7*high, 0.0, 0.85);
    float F = mix(F0, mix(F0, F1, w), mixAB*0.35 + (1.0-mixAB)*0.0 + w*0.65*(1.0-0.4*mixAB));
    // clearer: blend modes by high energy and xfader
    F = mix(F0, F1, clamp(w*0.55 + mixAB*0.45, 0.0, 1.0));

    float sharp = 14.0 + 36.0*(0.35 + high);
    float node = exp(-abs(F)*sharp);
    // sand grains clustered on the nodal lines
    vec2 guv = floor(uv*res*0.45 + vec2(flow*3.0, -flow*1.4));
    float grain = smoothstep(0.42, 0.95, hash(guv + floor(beat)));
    float sand = node * (0.42 + 0.58*grain);
    sand += node*node * (0.25 + 0.8*kick);

    vec3 plate = vec3(0.035, 0.032, 0.048);
    vec3 col = mix(colA, colB, smoothstep(0.0, 1.0, mixAB));
    vec3 glow = col * sand * (0.75 + 1.6*rms + 1.8*kick + 0.5*bass);
    vec3 rgb = plate + glow;
    // plate rim
    float rim = smoothstep(0.48, 0.52, max(abs(c.x), abs(c.y)*res.y/res.x));
    rgb = mix(rgb, plate*0.4, rim*0.85);
    rgb *= 1.0 - 0.28*dot(c,c);

    vec4 cd = texture(card, uv);
    rgb = mix(rgb, cd.rgb, cd.a * cardA);
    C = vec4(rgb, 1.0);
}
