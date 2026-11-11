// 3D Print mode: an interactive WebGL viewer for the designed part, and the card around it (parameters you can
// edit, printability numbers, downloads). Z is up and the print bed is the grid at z = 0, as in OpenSCAD.
const $el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;};

/* ------------------------------------------------------------------ small matrix helpers ------------------------------------------------------------------ */
const M={
  mul(a,b){const o=new Float32Array(16);for(let i=0;i<4;i++)for(let j=0;j<4;j++){let s=0;for(let k=0;k<4;k++)s+=a[k*4+j]*b[i*4+k];o[i*4+j]=s;}return o;},
  persp(fov,asp,n,f){const t=1/Math.tan(fov/2),o=new Float32Array(16);o[0]=t/asp;o[5]=t;o[10]=(f+n)/(n-f);o[11]=-1;o[14]=2*f*n/(n-f);return o;},
  look(e,c,u){const z=norm(sub(e,c)),x=norm(cross(u,z)),y=cross(z,x);return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,e),-dot(y,e),-dot(z,e),1]);},
};
const sub=(a,b)=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]],dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]],norm=a=>{const l=Math.hypot(...a)||1;return a.map(v=>v/l);};

function cssColor(name,fallback){
  const v=getComputedStyle(document.body).getPropertyValue(name).trim()||fallback,c=document.createElement('canvas').getContext('2d');
  c.fillStyle=v;const h=c.fillStyle;if(h.startsWith('#'))return [1,3,5].map(i=>parseInt(h.slice(i,i+2),16)/255);
  const m=h.match(/[\d.]+/g);return m?m.slice(0,3).map(x=>x/255):[0.6,0.6,0.6];
}

const VS=`attribute vec3 p;attribute vec3 n;uniform mat4 mvp;varying vec3 vn;varying float vz;void main(){vn=n;vz=p.z;gl_Position=mvp*vec4(p,1.0);}`;
const FS=`precision mediump float;varying vec3 vn;varying float vz;uniform vec3 col;uniform vec3 l1;uniform vec3 l2;uniform float flat1;
void main(){vec3 n=normalize(vn);float d=max(dot(n,l1),0.0)*0.72+max(dot(n,l2),0.0)*0.28;
float k=flat1>0.5?(d>0.55?1.0:d>0.2?0.62:0.25):0.32+0.68*d;gl_FragColor=vec4(col*k,1.0);}`;
const LVS=`attribute vec3 p;uniform mat4 mvp;void main(){gl_Position=mvp*vec4(p,1.0);}`;
const LFS=`precision mediump float;uniform vec4 col;void main(){gl_FragColor=col;}`;

function program(gl,vs,fs){
  const p=gl.createProgram();
  for(const [t,src] of [[gl.VERTEX_SHADER,vs],[gl.FRAGMENT_SHADER,fs]]){const s=gl.createShader(t);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));gl.attachShader(p,s);}
  gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(p));return p;
}

/** viewer(canvas) → {set(floats, bed), reset(), wire(on), destroy()} */
export function viewer(canvas,onNote=()=>{}){
  const gl=canvas.getContext('webgl',{antialias:true,preserveDrawingBuffer:true});
  if(!gl){onNote('This window cannot show 3D (WebGL is off). The STL download still works.');return {set(){},reset(){},wire(){},destroy(){}};}
  gl.getExtension('OES_element_index_uint');
  const shade=program(gl,VS,FS),line=program(gl,LVS,LFS);
  const buf={tri:gl.createBuffer(),nrm:gl.createBuffer(),edge:gl.createBuffer(),grid:gl.createBuffer(),axes:gl.createBuffer()};
  let count=0,edges=0,gridN=0,wire=false,box=null,cam={yaw:-0.75,pitch:0.55,dist:100,target:[0,0,0]},home=null,raf=0;
  function set(f,bed=[220,220,250]){
    count=f.length/3;
    const n=new Float32Array(f.length),e=[];let mn=[1e9,1e9,1e9],mx=[-1e9,-1e9,-1e9];
    for(let i=0;i<f.length;i+=9){
      const a=[f[i],f[i+1],f[i+2]],b=[f[i+3],f[i+4],f[i+5]],c=[f[i+6],f[i+7],f[i+8]],nn=norm(cross(sub(b,a),sub(c,a)));
      for(let k=0;k<3;k++){n.set(nn,i+k*3);const v=[a,b,c][k];for(let j=0;j<3;j++){mn[j]=Math.min(mn[j],v[j]);mx[j]=Math.max(mx[j],v[j]);}}
      e.push(...a,...b,...b,...c,...c,...a);
    }
    box={mn,mx};edges=e.length/3;
    gl.bindBuffer(gl.ARRAY_BUFFER,buf.tri);gl.bufferData(gl.ARRAY_BUFFER,f,gl.STATIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER,buf.nrm);gl.bufferData(gl.ARRAY_BUFFER,n,gl.STATIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER,buf.edge);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(e),gl.STATIC_DRAW);
    // bed grid: 10 mm lines around the part (at least 60 mm), the bed outline as a frame
    const span=Math.max(60,Math.ceil(Math.max(mx[0]-mn[0],mx[1]-mn[1])*1.6/10)*10),cx=Math.round((mn[0]+mx[0])/20)*10,cy=Math.round((mn[1]+mx[1])/20)*10,g=[];
    for(let v=-span/2;v<=span/2+1e-6;v+=10){g.push(cx+v,cy-span/2,0,cx+v,cy+span/2,0,cx-span/2,cy+v,0,cx+span/2,cy+v,0);}
    gridN=g.length/3;gl.bindBuffer(gl.ARRAY_BUFFER,buf.grid);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(g),gl.STATIC_DRAW);
    const L=Math.max(10,span/6);gl.bindBuffer(gl.ARRAY_BUFFER,buf.axes);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([cx-span/2,cy-span/2,0,cx-span/2+L,cy-span/2,0,cx-span/2,cy-span/2,0,cx-span/2,cy-span/2+L,0,cx-span/2,cy-span/2,0,cx-span/2,cy-span/2,L]),gl.STATIC_DRAW);
    const size=Math.hypot(mx[0]-mn[0],mx[1]-mn[1],mx[2]-mn[2])||10;
    home={yaw:-0.75,pitch:0.55,dist:size*1.9,target:[(mn[0]+mx[0])/2,(mn[1]+mx[1])/2,(mn[2]+mx[2])/2]};
    cam={...home,target:[...home.target]};draw();
  }
  function draw(){
    cancelAnimationFrame(raf);raf=requestAnimationFrame(()=>{
      const dpr=Math.min(window.devicePixelRatio||1,2),w=canvas.clientWidth,h=canvas.clientHeight;
      if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
      gl.viewport(0,0,canvas.width,canvas.height);
      const bg=cssColor('--bg-2','#171614');gl.clearColor(bg[0],bg[1],bg[2],1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);
      if(!count)return;
      const t=cam.target,cp=Math.cos(cam.pitch),eye=[t[0]+cam.dist*cp*Math.cos(cam.yaw),t[1]+cam.dist*cp*Math.sin(cam.yaw),t[2]+cam.dist*Math.sin(cam.pitch)];
      const mvp=M.mul(M.persp(0.62,(w||1)/(h||1),cam.dist/100,cam.dist*20),M.look(eye,t,[0,0,1]));
      const bitmap=document.body.dataset.theme==='bitmap';
      // lines: grid, axes, then the part
      gl.useProgram(line);const lp=gl.getAttribLocation(line,'p');gl.enableVertexAttribArray(lp);
      gl.uniformMatrix4fv(gl.getUniformLocation(line,'mvp'),false,mvp);
      const lc=cssColor('--line-strong','#47443b');gl.uniform4f(gl.getUniformLocation(line,'col'),lc[0],lc[1],lc[2],1);
      gl.bindBuffer(gl.ARRAY_BUFFER,buf.grid);gl.vertexAttribPointer(lp,3,gl.FLOAT,false,0,0);gl.drawArrays(gl.LINES,0,gridN);
      gl.bindBuffer(gl.ARRAY_BUFFER,buf.axes);gl.vertexAttribPointer(lp,3,gl.FLOAT,false,0,0);
      for(const [i,c] of [[0,bitmap?[0,0,0]:[0.94,0.45,0.4]],[2,bitmap?[0,0,0]:[0.5,0.82,0.5]],[4,bitmap?[0,0,0]:[0.45,0.62,0.95]]]){gl.uniform4f(gl.getUniformLocation(line,'col'),c[0],c[1],c[2],1);gl.drawArrays(gl.LINES,i,2);}
      if(!wire){
        gl.useProgram(shade);const p=gl.getAttribLocation(shade,'p'),n=gl.getAttribLocation(shade,'n');
        gl.uniformMatrix4fv(gl.getUniformLocation(shade,'mvp'),false,mvp);
        const col=bitmap?[1,1,1]:cssColor('--print','#8ab4f8');gl.uniform3f(gl.getUniformLocation(shade,'col'),col[0],col[1],col[2]);
        const l1=norm([Math.cos(cam.yaw+0.6),Math.sin(cam.yaw+0.6),1.1]),l2=norm([-0.4,0.3,-0.6]);
        gl.uniform3f(gl.getUniformLocation(shade,'l1'),...l1);gl.uniform3f(gl.getUniformLocation(shade,'l2'),...l2);
        gl.uniform1f(gl.getUniformLocation(shade,'flat1'),bitmap?1:0);
        gl.enableVertexAttribArray(p);gl.enableVertexAttribArray(n);
        gl.bindBuffer(gl.ARRAY_BUFFER,buf.tri);gl.vertexAttribPointer(p,3,gl.FLOAT,false,0,0);
        gl.bindBuffer(gl.ARRAY_BUFFER,buf.nrm);gl.vertexAttribPointer(n,3,gl.FLOAT,false,0,0);
        gl.enable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(1,1);gl.drawArrays(gl.TRIANGLES,0,count);gl.disable(gl.POLYGON_OFFSET_FILL);
        gl.disableVertexAttribArray(n);
      }
      if(wire||bitmap){
        gl.useProgram(line);gl.uniformMatrix4fv(gl.getUniformLocation(line,'mvp'),false,mvp);
        const ec=bitmap?[0,0,0]:cssColor('--print','#8ab4f8');gl.uniform4f(gl.getUniformLocation(line,'col'),ec[0],ec[1],ec[2],wire?0.9:0.35);
        gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
        gl.bindBuffer(gl.ARRAY_BUFFER,buf.edge);gl.vertexAttribPointer(lp,3,gl.FLOAT,false,0,0);gl.drawArrays(gl.LINES,0,edges);gl.disable(gl.BLEND);
      }
    });
  }
  // orbit (left drag), pan (right drag or Shift), zoom (wheel or pinch), reset (double-click)
  const pts=new Map();let pinch=0;
  canvas.addEventListener('contextmenu',e=>e.preventDefault());
  canvas.addEventListener('pointerdown',e=>{canvas.setPointerCapture(e.pointerId);pts.set(e.pointerId,{x:e.clientX,y:e.clientY,b:e.button,s:e.shiftKey});if(pts.size===2){const [a,b]=[...pts.values()];pinch=Math.hypot(a.x-b.x,a.y-b.y);}});
  canvas.addEventListener('pointermove',e=>{
    const p=pts.get(e.pointerId);if(!p)return;const dx=e.clientX-p.x,dy=e.clientY-p.y;p.x=e.clientX;p.y=e.clientY;
    if(pts.size===2){const [a,b]=[...pts.values()],d=Math.hypot(a.x-b.x,a.y-b.y);if(pinch){cam.dist=Math.min(Math.max(cam.dist*pinch/d,1),5000);}pinch=d;draw();return;}
    if(p.b===2||p.s||e.shiftKey){const k=cam.dist/canvas.clientHeight*1.1,right=[-Math.sin(cam.yaw),Math.cos(cam.yaw),0],up=[-Math.cos(cam.yaw)*Math.sin(cam.pitch),-Math.sin(cam.yaw)*Math.sin(cam.pitch),Math.cos(cam.pitch)];
      for(let i=0;i<3;i++)cam.target[i]+=(-dx*right[i]+dy*up[i])*k;}
    else{cam.yaw-=dx*0.008;cam.pitch=Math.min(Math.max(cam.pitch+dy*0.008,-1.45),1.45);}
    draw();
  });
  const end=e=>{pts.delete(e.pointerId);if(pts.size<2)pinch=0;};
  canvas.addEventListener('pointerup',end);canvas.addEventListener('pointercancel',end);
  canvas.addEventListener('wheel',e=>{e.preventDefault();cam.dist=Math.min(Math.max(cam.dist*Math.exp(e.deltaY*0.0012),1),5000);draw();},{passive:false});
  canvas.addEventListener('dblclick',()=>{if(home){cam={...home,target:[...home.target]};draw();}});
  const ro=new ResizeObserver(()=>draw());ro.observe(canvas);
  // Colours come from the theme: redraw at once when it changes (Settings → Appearance).
  const mo=new MutationObserver(()=>draw());mo.observe(document.body,{attributes:true,attributeFilter:['data-theme']});
  return {set,draw,reset(){if(home){cam={...home,target:[...home.target]};draw();}},wire(on){wire=on;draw();},
    view(name){if(!home)return;const v={front:[-Math.PI/2,0.05],side:[0,0.05],top:[-Math.PI/2,1.45],iso:[-0.75,0.55]}[name];cam.yaw=v[0];cam.pitch=v[1];draw();},
    destroy(){ro.disconnect();mo.disconnect();cancelAnimationFrame(raf);}};
}

export function decode(b64){const bin=atob(b64),u=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);return new Float32Array(u.buffer);}

/** The 3D model card: viewer, view buttons, parameters, printability, downloads, code.
    ctx: {workspace, render(script, values) → Promise<data>, notify(text)} */
export function cadCard(data,script,ctx){
  const card=$el('div','cad-card'),stage=$el('div','cad-stage'),canvas=$el('canvas','cad-canvas'),dims=$el('div','cad-dims'),hint=$el('div','cad-hint','Drag to turn · right-drag to move · scroll to zoom · double-click to reset');
  canvas.setAttribute('aria-label','3D view of the designed part');stage.append(canvas,dims,hint);
  const views=$el('div','cad-views');
  const mk=(label,fn,title='')=>{const b=$el('button','ghost',label);b.type='button';if(title)b.title=title;b.onclick=fn;views.append(b);return b;};
  const v=viewer(canvas,t=>ctx.notify(t));
  mk('Iso',()=>v.view('iso'));mk('Front',()=>v.view('front'));mk('Side',()=>v.view('side'));mk('Top',()=>v.view('top'));
  let wire=false;const wb=mk('Outline',()=>{wire=!wire;wb.setAttribute('aria-pressed',String(wire));v.wire(wire);},'Show the triangle edges');
  const facts=$el('div','cad-facts'),warn=$el('ul','cad-warnings');
  const params=$el('form','cad-params'),files=$el('div','cad-files');
  const code=$el('details','cad-code'),sum=$el('summary','','OpenSCAD code'),pre=$el('pre');code.append(sum,pre);
  card.append(stage,views,facts,warn,params,files,code);
  let values={};
  // Rebuilt files keep the design's name (the part before the content hash).
  const stem=(data?.files?.stl||'design').replace(/-[0-9a-f]{8}\.stl$/,'');
  function show(d){
    v.set(decode(d.mesh));
    const s=d.stats,e=d.estimate,f=n=>n.toLocaleString(undefined,{maximumFractionDigits:1});
    dims.textContent=`X ${f(s.size[0])} × Y ${f(s.size[1])} × Z ${f(s.size[2])} mm`;
    facts.replaceChildren(...[['Size',`${f(s.size[0])} × ${f(s.size[1])} × ${f(s.size[2])} mm`],['Plastic',`${f(e.printed_cm3)} cm³ · ≈ ${f(e.grams)} g ${e.material} at ${Math.round(e.infill*100)} % infill`],
      ['Cost and time',`≈ €${e.cost_eur.toFixed(2)} · ≈ ${e.hours<1?Math.max(1,Math.round(e.hours*60))+' min':f(e.hours)+' h'} (rough)`],['Overhangs',s.overhang_pct>0?`${f(s.overhang_pct)} % of the surface beyond 45°`:'none beyond 45°'],
      ['On the bed',s.orientation||'As designed.'],['Mesh',`${s.triangles.toLocaleString()} triangles${s.pieces>1?` · ${s.pieces} pieces`:''}`]].map(([k,val])=>{const d2=$el('div');d2.append($el('span','label',k),$el('b','',val));return d2;}));
    warn.replaceChildren(...(d.warnings||[]).map(w=>$el('li','',w)));
    const q=n=>'/api/cad-file?'+new URLSearchParams({workspace:ctx.workspace,name:n});
    const stl=$el('a','button primary','⬇ Download STL');stl.href=q(d.files.stl);stl.setAttribute('download',d.files.stl);
    const scadA=$el('a','button ghost','OpenSCAD file');scadA.href=q(d.files.scad);scadA.setAttribute('download',d.files.scad);
    const copy=$el('button','ghost','Copy code');copy.type='button';copy.onclick=async()=>{try{await navigator.clipboard.writeText(pre.textContent);copy.textContent='Copied';setTimeout(()=>copy.textContent='Copy code',1500);}catch{ctx.notify('Copy is blocked here; select the code and press Ctrl+C.');}};
    const saved=$el('span','hint',`Saved in this workspace as ${d.files.stl}`);
    files.replaceChildren(stl,scadA,copy,saved);
  }
  function form(list,current){
    params.replaceChildren();
    if(!list.length)return;
    params.append($el('p','label','Dimensions'));
    const grid=$el('div','cad-param-grid');
    for(const p of list){
      const row=$el('label','cad-param'),name=$el('span','',p.label||p.name),inp=$el('input');
      if(typeof p.value==='boolean'){inp.type='checkbox';inp.checked=current[p.name]??p.value;}
      else{inp.type='number';inp.step=p.step??'any';if(p.min!=null)inp.min=p.min;if(p.max!=null)inp.max=p.max;inp.value=current[p.name]??p.value;}
      inp.name=p.name;row.title=p.name;row.append(name,inp);
      if(typeof p.value!=='boolean'){const unit=$el('small','',/angle|deg/i.test(p.name+p.label)?'°':/count|num|n_|number/i.test(p.name+p.label)?'':'mm');row.append(unit);}
      grid.append(row);
    }
    const go=$el('button','primary','Update model');go.type='submit';
    const reset=$el('button','ghost','Reset');reset.type='button';
    params.append(grid,go,reset);
    reset.onclick=()=>{form(list,{});values={};rebuild();};
  }
  async function rebuild(){
    const btn=params.querySelector('button[type=submit]');if(btn){btn.disabled=true;btn.textContent='Building…';}
    try{const d=await ctx.render(script,values,stem);show(d);}catch(e){ctx.notify(e.message);}
    finally{if(btn){btn.disabled=false;btn.textContent='Update model';}}
  }
  params.onsubmit=e=>{e.preventDefault();values={};for(const inp of params.querySelectorAll('input')){values[inp.name]=inp.type==='checkbox'?inp.checked:Number(inp.value);}rebuild();};
  pre.textContent=script;
  if(data){show(data);form(data.params||[],data.values||{});}
  return {el:card,show,form,destroy:v.destroy};
}
