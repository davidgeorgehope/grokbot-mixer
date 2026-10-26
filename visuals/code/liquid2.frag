#version 330
in vec2 uv; out vec4 o;
uniform vec2 res; uniform float time,flow,kacc,mixAB,bass,mid,high,kick,snare,rms,beat,seedA,seedB,cardA,cardT;
uniform sampler2D texA,texB,card;
uniform vec3 paA,pbA,pcA,pdA,accA,paB,pbB,pcB,pdB,accB;
float h21(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
 return mix(mix(h21(i),h21(i+vec2(1,0)),f.x),mix(h21(i+vec2(0,1)),h21(i+vec2(1,1)),f.x),f.y);}
const mat2 R=mat2(.8,.6,-.6,.8);
float fbm(vec2 p){float s=0.,a=.5;for(int i=0;i<5;i++){s+=a*noise(p);p=R*p*2.02;a*=.5;}return s;}
vec3 pal(float t,vec3 a,vec3 b,vec3 c,vec3 d){return a+b*cos(6.28318*(c*t+d));}
vec3 scene(vec2 p,vec2 q,float sd,vec3 pa,vec3 pb,vec3 pc,vec3 pd,vec3 acc,sampler2D tex){
 float F=flow*.18;
 // domain-warped liquid
 vec2 w1=vec2(fbm(p*1.3+vec2(0,F)+sd*7.),fbm(p*1.3+vec2(5.2,1.3)-F*.7));
 vec2 w2=vec2(fbm(p*1.3+(2.+bass*1.2)*w1+vec2(1.7,9.2)+F*.5),fbm(p*1.3+(2.+bass*1.2)*w1+vec2(8.3,2.8)));
 float f=fbm(p*1.3+2.5*w2);
 vec3 col=pal(f*1.2+length(w2)*.4+sd*.13+time*.01,pa,pb,pc,pd);
 col*=.25+.9*f*f;
 // backdrop texture, refracted through the liquid
 vec2 tuv=q+ (w2-.5)*.06*(1.+bass)+vec2(sin(time*.05),cos(time*.04))*.02;
 tuv=(tuv-.5)*(.92-.03*kick)+.5;
 vec3 tx=texture(tex,tuv).rgb;
 col=mix(col*.7,tx*(.75+.5*f),.62)+tx*tx*.3*f;
 // liquid orb (2D metaball-ish), refractive rim, pulses on bass
 float r=.21+.05*bass+.03*kick; float d=1e9;
 for(int i=0;i<4;i++){float fi=float(i); vec2 c=.16*vec2(sin(F*1.3+fi*1.7+sd),cos(F*1.1+fi*2.3));
   d=min(d,length(p-c)-r*(1.-.18*fi));}
 float k2=0.; for(int i=0;i<4;i++){float fi=float(i); vec2 c=.16*vec2(sin(F*1.3+fi*1.7+sd),cos(F*1.1+fi*2.3)); k2+=exp(-8.*max(length(p-c)-r*(1.-.18*fi),0.)/r);}
 float m=smoothstep(.9,1.25,k2);
 float depth=smoothstep(1.,3.5,k2);           // 0 at rim -> 1 deep inside
 float fres=pow(1.-depth,3.)*m;
 vec2 rq=(q-.5)*(.55+.35*depth)+.5+(w1-.5)*.12*(1.-depth)+p*.04*(1.-depth);
 vec3 inner=texture(tex,rq).rgb;
 inner=mix(inner,inner.gbr,.15)*1.15+acc*.08*(1.+bass);
 col=mix(col,inner,m*.6);
 col+=mix(acc,vec3(1),.35)*fres*(.55+1.1*kick+.5*snare);
 // specular glint top-left of each blob
 col+=vec3(1)*pow(clamp(1.-length(p-vec2(-.12,.16)-.05*w1)*3.2,0.,1.),6.)*m*.45;
 col+=acc*exp(-max(1.-k2,0.)*14.)*(1.-m)*.25*(1.+kick);   // outer glow
 // volumetric light rays from behind the orb
 float an=atan(p.y,p.x); float rl=length(p);
 float rays=fbm(vec2(an*3.,F*.6+sd))*fbm(vec2(an*7.-F*.3,sd*3.));
 col+=acc*pow(rays,2.)*1.6*(.4+bass*.8+kick*.8)*exp(-rl*1.6)*smoothstep(.05,.35,rl)*(1.-m*.7);
 // bokeh particles drifting upward, sparkle on highs
 for(int l=0;l<3;l++){float fl=float(l); vec2 g=p*(5.+fl*4.)+vec2(fl*13.+sd*3.,-F*(1.+fl*.6));
   vec2 id=floor(g),fr=fract(g)-.5; float hh=h21(id+fl*7.);
   vec2 off=vec2(h21(id+3.)-.5,h21(id+9.)-.5)*.6; float dd=length(fr-off);
   float sz=.03+.09*hh*hh*hh; float tw=.5+.5*sin(time*(1.+hh*3.)+hh*40.);
   col+=mix(acc,vec3(1),.4)*smoothstep(sz,sz*.3,dd)*step(.86,hh)*(.15+tw*.35+high*1.0)*(1./(1.+fl));}
 return col;}
void main(){
 vec2 q=uv; vec2 p=(uv-.5)*vec2(res.x/res.y,1.);
 float bph=fract(beat); float bar=fract(beat/4.);
 // kick punch zoom
 p*=1.-.035*kick;
 p+= .004*kick*vec2(sin(time*40.),cos(time*37.));
 vec3 A=scene(p,q,seedA,paA,pbA,pcA,pdA,accA,texA);
 vec3 col=A;
 if(mixAB>0.001){
   vec3 B=scene(p,q,seedB,paB,pbB,pcB,pdB,accB,texB);
   // liquid wipe: noisy threshold sweeping through
   float n=fbm(p*2.+time*.1); float m=smoothstep(mixAB*1.4-.4-.08,mixAB*1.4-.4+.08,n*.9+.05*length(p));
   m=1.-m; col=mix(A,B,clamp(m,0.,1.));
   col+=mix(accA,accB,.5)*smoothstep(.06,0.,abs(m-.5))*.25*(1.-abs(mixAB-.5)*2.);
 }
 // snare flash + subtle chromatic split via luminance offset
 col*=1.+.25*snare+.15*kick;
 col+=vec3(.9,.95,1)*snare*.04;
 // bar-level breathing
 col*=.92+.08*cos(bar*6.28318);
 // tonemap + grade
 col=col/(1.+col*.55); col=pow(col,vec3(.92));
 float vig=smoothstep(1.15,.25,length((uv-.5)*vec2(1.25,1.)));
 col*=.35+.65*vig;
 col+=(h21(uv*res+fract(time)*100.)-.5)*.02;
 // title card
 vec2 cu=uv; cu.x+= (1.-smoothstep(0.,1.5,cardT))*.02;
 vec4 c=texture(card,cu); col=mix(col,c.rgb,c.a*cardA);
 o=vec4(clamp(col,0.,1.),1);}
