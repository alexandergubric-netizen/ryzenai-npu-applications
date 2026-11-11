'use strict';
const el=id=>document.getElementById(id),workspace=new URLSearchParams(location.search).get('workspace')||'default';
let requestId=null;
async function post(path,body){
 const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Tsubasa':'1'},body:JSON.stringify(body)});
 const data=await r.json();if(!r.ok)throw Error(data.error);return data;
}
function note(s){el('status').textContent=s;}
async function refresh(){
 const {result}=await post('/api/files',{workspace,action:'list'});
 el('file').replaceChildren(...result.filter(n=>/\.(wav|mp3|flac|ogg|m4a|mp4|mov|mkv|webm)$/i.test(n)).map(n=>new Option(n,n)));
 el('run').disabled=!el('file').value||!!requestId;
}
el('upload').onchange=async()=>{try{
 const f=el('upload').files[0];if(!f||!confirm('Copy '+f.name+' into this workspace?'))return;
 const r=await fetch('/api/files/import?'+new URLSearchParams({workspace,name:f.name}),{method:'POST',headers:{'X-Tsubasa':'1'},body:f});
 if(!r.ok)throw Error((await r.json()).error);await refresh();el('file').value=f.name;
}catch(e){note(e.message);}};
el('run').onclick=async()=>{
 if(requestId)return;requestId=crypto.randomUUID().replaceAll('-','');
 el('run').disabled=true;el('cancel').disabled=false;el('copy').disabled=true;el('text').value='';note('Preparing audio and waiting for local Whisper…');
 try{const r=await post('/api/audio',{workspace,request_id:requestId,arguments:{path:el('file').value,language:el('language').value}});
 el('text').value=r.text;el('copy').disabled=false;note(r.audio_seconds.toFixed(1)+' s of audio · '+r.asr_seconds.toFixed(2)+' s transcription');
 }catch(e){note(e.message);}finally{requestId=null;el('run').disabled=!el('file').value;el('cancel').disabled=true;}
};
el('cancel').onclick=async()=>{try{const r=await post('/api/cancel',{request_id:requestId});if(r.cancelled)note('Cancelled. An in-flight FLM request must finish before the next operation.');}catch(e){note(e.message);}};
el('copy').onclick=()=>navigator.clipboard.writeText(el('text').value).then(()=>note('Transcript copied.')).catch(()=>note('Select the transcript and copy it manually.'));
refresh().catch(e=>note(e.message));
setInterval(()=>post('/api/ping',{}).catch(()=>{}),10000);

