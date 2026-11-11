'use strict';
const el=id=>document.getElementById(id),workspace=new URLSearchParams(location.search).get('workspace')||'default';
let busy=false,requestId=null;
async function api(body){
 const r=await fetch('/api/images',{method:'POST',headers:{'X-Tsubasa':'1','Content-Type':'application/json'},body:JSON.stringify({workspace,...body})});
 const data=await r.json();if(!r.ok)throw Error(data.error);return data.result??data;
}
function controls(on){
 busy=on;
 for(const id of ['generate-button','start','refresh','size','prompt'])el(id).disabled=on;
 el('progress').hidden=!on;el('cancel').disabled=!requestId;
}
async function history(){
 const rows=await api({action:'list'});el('empty').hidden=rows.length>0;
 el('gallery').replaceChildren(...rows.map(row=>{
  const card=document.createElement('article'),p=document.createElement('p'),meta=document.createElement('p');
  p.textContent=row.prompt;meta.textContent=row.size+' · '+row.created+' UTC · '+row.status+(row.seconds!==null?' · '+row.seconds.toFixed(1)+' s':'');
  meta.className='image-meta';
  if(row.status==='complete'){
   const q=new URLSearchParams({workspace,id:row.id}),img=document.createElement('img'),download=document.createElement('a');
   img.src='/api/image?'+q;img.alt=row.prompt;img.loading='lazy';card.append(img);
   download.href='/api/image?'+q+'&download=1';download.textContent='Download PNG';card.append(download);
  }
  card.append(p,meta);
  if(row.error){const e=document.createElement('p');e.textContent=row.error;card.append(e);}
  return card;
 }));
}
async function status(){
 const state=await api({action:'status'});
 el('service').textContent=state.online?'Local image service ready'+(state.owned?' · started by this app':''):'Image service is offline. Start it when you are ready.';
 el('start').hidden=state.online;
 el('memory').textContent=state.warning+(state.last_observed_model?.includes('liberty')?' Last observed chat model: Qwen Liberty.':'');
}
async function approve(proposal){
 const d=el('permission');d.returnValue='deny';
 el('preview').textContent=proposal.action==='start'?'Start the installed image service. It will remain available until this app closes.':'Generate and save one '+proposal.arguments.size+' image:\n\n'+proposal.arguments.prompt;
 const decision=new Promise(resolve=>d.addEventListener('close',()=>resolve(d.returnValue==='allow'),{once:true}));
 d.showModal();return decision;
}
async function action(kind,args={}){
 if(busy)return;controls(true);el('status').textContent='';
 try{
  const proposal=await api({action:'prepare_'+kind,arguments:args});const allow=await approve(proposal);
  requestId=crypto.randomUUID().replaceAll('-','');el('cancel').disabled=kind==='start'||!allow;
  el('status').textContent=allow?(kind==='start'?'Starting the local image service…':'Generating image… This service does not report a percentage.'):'Request denied.';
  const result=await api({action:'decide',ticket:proposal.ticket,allow,request_id:requestId});
  if(allow)el('status').textContent=kind==='start'?'Image service ready.':'Image saved to this workspace.';
  await history();await status();
 }catch(e){el('status').textContent=e.message;await history().catch(()=>{});}
 finally{requestId=null;controls(false);}
}
el('generate').onsubmit=e=>{e.preventDefault();action('generate',{prompt:el('prompt').value,size:el('size').value});};
el('start').onclick=()=>action('start');
el('refresh').onclick=()=>status().catch(e=>el('status').textContent=e.message);
el('cancel').onclick=async()=>{if(!requestId)return;el('cancel').disabled=true;try{
 await fetch('/api/cancel',{method:'POST',headers:{'X-Tsubasa':'1','Content-Type':'application/json'},body:JSON.stringify({request_id:requestId})});
 el('status').textContent='Cancelled. Waiting for the image service request to finish before another operation.';
}catch(e){el('status').textContent=e.message;}};
Promise.all([status(),history()]).catch(e=>el('status').textContent=e.message);
setInterval(()=>fetch('/api/ping',{method:'POST',headers:{'X-Tsubasa':'1','Content-Type':'application/json'},body:'{}'}).catch(()=>{}),10000);

