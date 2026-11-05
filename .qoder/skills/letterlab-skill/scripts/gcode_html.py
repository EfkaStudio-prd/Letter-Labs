"""Self-contained interactive WebGL 3D preview for LetterLab G-code.

`write_viewer` packs an already-parsed gcode3d.Toolpath into a single HTML
file: base64 Float32 vertices, WebGL1 renderer, orbit (mouse drag), zoom
(wheel), layer slider + build-up play, per-tool colour legend with toggles,
bed outline and a stats HUD.  No external assets, no build step - just open
the file in any WebGL-capable browser.

Vertex stream (the only data format the template understands):
    per VERTEX: x, y, z, tool, layer   (5 x Float32 = 20 bytes)
segments contribute two consecutive vertices (line endpoints), so the whole
toolpath draws with one gl.LINES call and beads read as gl.POINTS peeks.

When the file has more segments than `cap`, decimation strides evenly
through the toolpath so every layer stays visible instead of chopping the
top of the print away.
"""
from __future__ import annotations

import array
import base64
import json


def pack_viewer(tp, cap):
    """Return (bytes, n_lines_drawable, nlayers, zs_list)."""
    zs = sorted(tp.zs)
    idx = {z: i for i, z in enumerate(zs)}

    def layer_of(s):
        return idx.get(round(s[2], 4),
                       idx.get(round(s[5], 4), 0))

    n = len(tp.seg)
    stride = 1
    if cap and n > cap:
        stride = (n + cap - 1) // cap
    flat = array.array("f")
    kept = 0
    for i in range(0, n, stride):
        s = tp.seg[i]
        tool = float(s[6] % 250)
        lay = float(layer_of(s))
        flat.extend((s[0], s[1], s[2], tool, lay,
                     s[3], s[4], s[5], tool, lay))
        kept += 1
    return flat.tobytes(), kept * 2, len(zs), zs


def write_viewer(tp, stats, out_path, bed=None, cap=140000, width=1.2,
                 name=""):
    data, nvert, nlayers, zs = pack_viewer(tp, cap)
    b64 = base64.b64encode(data).decode("ascii")
    b = tp.bounds or (0, 0, 0, 0, 0, 0)
    size = (round(b[3] - b[0], 1), round(b[4] - b[1], 1), round(b[5] - b[2], 1))
    page = _HTML_TEMPLATE
    for key, val in (
        ("@@B64@@", b64),
        ("@@NVERT@@", str(nvert)),
        ("@@NLAYERS@@", str(max(0, nlayers - 1))),
        ("@@ZLIST@@", json.dumps([round(z, 3) for z in zs])),
        ("@@COLORS@@", json.dumps([list(c) for c in _TOOL_COLORS])),
        ("@@BED@@", json.dumps([bed[0], bed[1]]) if bed else "null"),
        ("@@SIZE@@", json.dumps(list(size))),
        ("@@STATS@@", json.dumps(stats, sort_keys=True)),
        ("@@NAME@@", str(name).replace("<", "&#60;").replace("&", "&#38;")),
        ("@@WIDTH@@", str(width)),
    ):
        page = page.replace(key, val)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return out_path


#: same palette as gcode3d.TOOK_COLORS-style swatches, index 6 = bed gray
_TOOL_COLORS = [
    (232, 74, 60),    # T0  red
    (48, 118, 214),   # T1  blue
    (46, 174, 96),    # T2  green
    (238, 178, 36),   # T3  amber
    (156, 92, 200),   # T4  violet
    (230, 230, 230),  # T5  white
    (120, 126, 138),  # bed / frame gray
]


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>LetterLab 3D preview - @@NAME@@</title>
<style>
  html,body{margin:0;height:100%;background:#14161a;color:#ccd3dd;
            font:13px/1.4 Consolas,Menlo,monospace;overflow:hidden}
  #gl{position:absolute;inset:0;width:100%;height:100%;display:block;cursor:grab}
  #hud{position:absolute;top:10px;left:12px;background:rgba(18,20,24,.82);
       border:1px solid #2c313a;padding:8px 12px;border-radius:6px;white-space:pre}
  #legend{position:absolute;top:10px;right:12px;background:rgba(18,20,24,.82);
          border:1px solid #2c313a;padding:8px 10px;border-radius:6px}
  .ch{display:inline-flex;align-items:center;margin:2px 4px;cursor:pointer}
  .off{opacity:.25;pointer-events:auto}
  .sw{width:12px;height:12px;border-radius:2px;margin-right:5px;display:inline-block}
  #bar{position:absolute;left:50%;transform:translateX(-50%);bottom:14px;
       background:rgba(18,20,24,.85);border:1px solid #2c313a;border-radius:8px;
       padding:8px 14px;display:flex;gap:10px;align-items:center;
       width:min(760px,94vw);box-sizing:border-box}
  #lay{flex:1}
  input[type=range]{accent-color:#e84a3c}
  button{background:#23272f;border:1px solid #39414d;color:#ccd3dd;border-radius:5px;
         padding:3px 12px;cursor:pointer;font:inherit}
  button:hover{background:#2f3540}
  button.sel{background:#e84a3c;border-color:#e84a3c;color:#fff}
  #zl{min-width:70px;text-align:right;display:inline-block}
</style>
</head><body>
<canvas id="gl"></canvas>
<div id="hud"></div>
<div id="legend"></div>
<div id="bar">
  <button id="play">&#9654;</button>
  <button class="spd" data-sp="1">&frac12;x</button>
  <button class="spd" data-sp="2">1x</button>
  <button class="spd" data-sp="3">2x</button>
  <button class="spd" data-sp="4">4x</button>
  <input id="lay" type="range" min="0" max="@@NLAYERS@@" step="1" value="@@NLAYERS@@">
  <span id="zl"></span>
</div>
<script>
"use strict";
// ===================================================================== data
// base64 Float32: per VERTEX x,y,z,tool,layer ; two vertices per segment
const B64="@@B64@@";
const NVERT=@@NVERT@@, MAXLAY=@@NLAYERS@@;
const ZS=@@ZLIST@@, COLS=@@COLORS@@;
const BED=@@BED@@, SIZE=@@SIZE@@, STATS=@@STATS@@;
const TITLE="@@NAME@@";
const BEAD=@@WIDTH@@;        // mm, the bead width the file was drawn with

function b64bytes(s){const bin=atob(s),u=new Uint8Array(bin.length);
  for(let i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);return u;}
const vdata=new Float32Array(b64bytes(B64).buffer);  // 5 floats per vertex

// ===================================================================== gl
const cv=document.getElementById("gl");
const gl=cv.getContext("webgl",{antialias:true});
const VS=`
attribute vec3 aPos;attribute vec2 aMeta;
uniform mat4 uM;uniform float uLayMax,uPSS;
uniform float uHide[7];
varying vec3 vC;uniform vec3 uCol[7];
void off2(){gl_Position=vec4(2.,2.,2.,1.);gl_PointSize=0.;vC=vec3(0.);}
void main(){
  if(aMeta.y>uLayMax){off2();return;}
  int t=int(aMeta.x+0.5);bool hid=false;
  for(int i=0;i<7;i++){if(t==i&&uHide[i]>0.5){hid=true;break;}}
  if(hid){off2();return;}
  vC=uCol[t];
  gl_Position=uM*vec4(aPos,1.);
  gl_PointSize=uPSS;
}`;
const FS=`precision mediump float;varying vec3 vC;
void main(){gl_FragColor=vec4(vC,1.);}`;
function sh(t,s){const o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);
  if(!gl.getShaderParameter(o,gl.COMPILE_STATUS))throw gl.getShaderInfoLog(o);
  return o;}
const pr=gl.createProgram();
gl.attachShader(pr,sh(gl.VERTEX_SHADER,VS));
gl.attachShader(pr,sh(gl.FRAGMENT_SHADER,FS));
gl.linkProgram(pr);gl.useProgram(pr);
const U={M:gl.getUniformLocation(pr,"uM"),
  L:gl.getUniformLocation(pr,"uLayMax"),
  P:gl.getUniformLocation(pr,"uPSS"),
  H:gl.getUniformLocation(pr,"uHide[0]"),
  C:gl.getUniformLocation(pr,"uCol[0]")};
const colarr=new Float32Array(21);
COLS.forEach((c,i)=>{colarr[i*3]=c[0]/255;colarr[i*3+1]=c[1]/255;
  colarr[i*3+2]=c[2]/255;});
gl.uniform3fv(U.C,colarr);
const HIDE=new Float32Array(7);

const A0=gl.getAttribLocation(pr,"aPos");
const A1=gl.getAttribLocation(pr,"aMeta");
const VBO=gl.createBuffer();
gl.bindBuffer(gl.ARRAY_BUFFER,VBO);
gl.bufferData(gl.ARRAY_BUFFER,vdata,gl.STATIC_DRAW);
gl.enableVertexAttribArray(A0);
gl.vertexAttribPointer(A0,3,gl.FLOAT,false,20,0);
gl.enableVertexAttribArray(A1);
gl.vertexAttribPointer(A1,2,gl.FLOAT,false,20,12);

// bed rectangle: same 5-float vertex layout, tool = 6 (gray), layer far above
let BEDN=0;
if(BED){
  const w=BED[0],h=BED[1];
  const quad=[[0,0],[w,0],[w,h],[0,h]];
  const bed=new Float32Array(4*2*5);
  for(let i=0;i<4;i++){
    bed.set([quad[i][0],quad[i][1],0,6,1e5],i*10);
    bed.set([quad[(i+1)%4][0],quad[(i+1)%4][1],0,6,1e5],i*10+5);}
  const bb=gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER,bb);
  gl.bufferData(gl.ARRAY_BUFFER,bed,gl.STATIC_DRAW);
  BEDN=8;
  function bindBed(){
    gl.bindBuffer(gl.ARRAY_BUFFER,bb);
    gl.vertexAttribPointer(A0,3,gl.FLOAT,false,20,0);
    gl.vertexAttribPointer(A1,2,gl.FLOAT,false,20,12);}
  window._bindBed=bindBed;
}

// ===================================================================== camera
let YAW=-45*Math.PI/180,ELEV=24*Math.PI/180,ZOOM=1.0;
let span=100,cy0=0,cy1=0,cy2=0;
(function(){
  let xa=1e9,ya=1e9,za=1e9,xb=-1e9,yb=-1e9,zb=-1e9;
  for(let i=0;i<vdata.length;i+=5){
    const x=vdata[i],y=vdata[i+1],z=vdata[i+2];
    if(x<xa)xa=x;if(x>xb)xb=x;
    if(y<ya)ya=y;if(y>yb)yb=y;
    if(z<za)za=z;if(z>zb)zb=z;}
  span=Math.max(xb-xa,yb-ya,zb-za)||100;
  cy0=(xa+xb)/2;cy1=(ya+yb)/2;cy2=(za+zb)/2;})();

function mul(a,b){const o=new Float32Array(16);
  for(let c=0;c<4;c++)for(let r=0;r<4;r++)
    o[c*4+r]=a[r]*b[c*4]+a[4+r]*b[c*4+1]+a[8+r]*b[c*4+2]+a[12+r]*b[c*4+3];
  return o;}
function Tm(x,y,z){const m=new Float32Array(16);
  m[0]=m[5]=m[10]=m[15]=1;m[12]=x;m[13]=y;m[14]=z;return m;}
function Rz(a){const c=Math.cos(a),s=Math.sin(a);const m=new Float32Array(16);
  m[0]=c;m[1]=s;m[4]=-s;m[5]=c;m[10]=m[15]=1;return m;}
function Rx(e){const c=Math.cos(e),s=Math.sin(e);const m=new Float32Array(16);
  m[0]=m[15]=1;m[5]=c;m[6]=s;m[9]=-s;m[10]=c;return m;}
function mat4(){
  const s=Math.min(cv.width,cv.height)/2*0.92/span*ZOOM;
  const P=new Float32Array(16);
  P[0]=2*s/cv.width;P[5]=2*s/cv.height;P[10]=0.9/span;P[15]=1;
  return mul(P,mul(Rx(ELEV),mul(Rz(-YAW),Tm(-cy0,-cy1,-cy2))));}

let down=false,lx=0,ly=0;
cv.addEventListener("mousedown",e=>{down=true;lx=e.clientX;ly=e.clientY;
  cv.style.cursor="grabbing";});
addEventListener("mouseup",()=>{down=false;cv.style.cursor="grab";});
addEventListener("mousemove",e=>{if(!down)return;
  YAW+=(e.clientX-lx)*0.0075;
  ELEV=Math.max(-0.02,Math.min(1.52,ELEV+(e.clientY-ly)*0.0075));
  lx=e.clientX;ly=e.clientY;draw();});
cv.addEventListener("wheel",e=>{e.preventDefault();
  ZOOM*=Math.pow(1.0015,-e.deltaY);
  ZOOM=Math.max(0.2,Math.min(60,ZOOM));draw();},{passive:false});

// ===================================================================== ui
const lay=document.getElementById("lay"),zl=document.getElementById("zl");
const play=document.getElementById("play");
const hud=document.getElementById("hud");
let laying=MAXLAY;
let SPD=3;
const RATES=[0,1.5,3,6,12];
let raf=null,acc=0,last=0;
const f2=n=>n.toFixed(2);
function hudtxt(){
  const dz=STATS.layers?STATS.layers:MAXLAY+1;
  hud.textContent=TITLE+"\n"+
   `${dz} layers   ${STATS.segments} segments parsed\n`+
   `size ${SIZE.join(" x ")} mm\n`+
   `path ${(STATS.toolpath_total_m||0).toFixed(1)} m  filament ${(STATS.filament_total_m||0).toFixed(1)} m\n`+
   `est ${String(STATS.est_print_time_min||0)} min\n`+
   `layer ${laying}/${MAXLAY}`;
  zl.textContent="z "+f2(ZS[Math.min(laying,ZS.length-1)]||0)+" mm";
}
function playbtn(){
  play.innerHTML=raf?"&#9646;&#9646;":"&#9654;";}
function stop(){if(raf){cancelAnimationFrame(raf);raf=null;}playbtn();}
play.addEventListener("click",()=>{
  if(raf){stop();return;}
  if(laying>=MAXLAY)laying=0;
  last=performance.now();acc=0;
  playbtn();raf=requestAnimationFrame(tick);});
function tick(t){
  const dt=Math.min(0.1,(t-last)/1000);last=t;
  acc+=dt*RATES[SPD];
  let moved=false;
  while(acc>=1&&laying<MAXLAY){acc-=1;laying++;moved=true;}
  if(moved){lay.value=laying;hudtxt();draw();}
  if(laying>=MAXLAY){stop();return;}
  raf=requestAnimationFrame(tick);}
lay.addEventListener("input",()=>{laying=+lay.value;stop();hudtxt();draw();});
document.querySelectorAll(".spd").forEach(b=>b.addEventListener("click",()=>{
  SPD=+b.dataset.sp;
  document.querySelectorAll(".spd").forEach(x=>x.classList.remove("sel"));
  b.classList.add("sel");}));
document.querySelector('.spd[data-sp="2"]').classList.add("sel");

const legend=document.getElementById("legend");
(function(){const shown=new Set();
  for(let i=0;i<vdata.length;i+=5)shown.add(vdata[i+3]|0);
  const bed=!!BED;
  for(let i=0;i<7;i++){
    if(i<6&&!shown.has(i))continue;
    if(i===6&&!bed)continue;
    const d=document.createElement("span");d.className="ch";
    d.innerHTML=`<span class="sw" style="background:rgb(${COLS[i]})
      "></span>${i===6?"bed":"T"+i}`;
    d.onclick=()=>{HIDE[i]=HIDE[i]?0:1;d.classList.toggle("off",!!HIDE[i]);draw();};
    legend.appendChild(d);}})();

// ===================================================================== draw
function resize(){cv.width=innerWidth;cv.height=innerHeight;
  gl.viewport(0,0,cv.width,cv.height);}
addEventListener("resize",()=>{resize();draw();});
function draw(){
  gl.enable(gl.DEPTH_TEST);
  gl.clearColor(0.078,0.086,0.102,1);
  gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
  const pxmm=Math.min(cv.width,cv.height)/2*0.92/span*ZOOM;
  gl.uniformMatrix4fv(U.M,false,mat4());
  gl.uniform1f(U.L,laying+0.5);
  gl.uniform1f(U.P,Math.max(2,BEAD*pxmm));
  gl.uniform1fv(U.H,HIDE);
  gl.bindBuffer(gl.ARRAY_BUFFER,VBO);
  gl.vertexAttribPointer(A0,3,gl.FLOAT,false,20,0);
  gl.vertexAttribPointer(A1,2,gl.FLOAT,false,20,12);
  gl.drawArrays(gl.LINES,0,NVERT);
  gl.drawArrays(gl.POINTS,0,NVERT);
  if(BEDN){window._bindBed();gl.drawArrays(gl.LINES,0,BEDN);}}

resize();hudtxt();draw();
</script>
</body></html>
"""
