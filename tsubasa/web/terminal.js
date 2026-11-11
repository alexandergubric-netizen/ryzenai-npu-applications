'use strict';
const el=id=>document.getElementById(id);
const workspace=new URLSearchParams(location.search).get('workspace')||'default';
let requestId=null;
async function api(body,path='/api/terminal'){
 const r=await fetch(path,{method:'POST',headers:{'X-Tsubasa':'1','Content-Type':'application/json'},body:JSON.stringify({workspace,...body})});
 const data=await r.json();if(!r.ok)throw Error(data.error);return data.result??data;
}
function display(){
 const op=el('op').value;
 el('templates').hidden=op!=='ps_run';el('file-field').hidden=!op.startsWith('fs_');el('code-field').hidden=op==='fs_read';
 el('code').maxLength=op==='fs_write'?16000:4000;
 el('code-label').textContent={ps_run:'Command',py_run:'Expression',fs_write:'New contents'}[op]||'';
 el('submit').textContent={fs_read:'Read file',fs_write:'Review changes'}[op]||'Review and run';
 el('help').textContent={ps_run:'Use one of the reviewed commands. Replace notes.txt with a file in this project.',
 py_run:'Use numbers, lists, arithmetic, abs, round, len, min, max, sum or sorted.',
 fs_read:'Choose a UTF-8 file in this project, up to 16,000 bytes.',fs_write:'Review the proposed changes before saving.'}[op];
 el('code').value={ps_run:el('template').value,py_run:'sum([2, 3, 5])',fs_write:''}[op]||'';
}
el('op').onchange=display;el('template').onchange=()=>{el('code').value=el('template').value;};
function lock(on){for(const id of ['op','template','path','code','submit'])el(id).disabled=on;}
el('form').onsubmit=async e=>{
 e.preventDefault();lock(true);el('output').textContent='';el('status').textContent='';
 try{
  const name=el('op').value,args=name==='fs_read'?{path:el('path').value}:name==='fs_write'?{path:el('path').value,content:el('code').value}:{code:el('code').value};
  let result=await api({action:'prepare',name,arguments:args});
  if(result.ticket){
   const dialog=el('approval');dialog.returnValue='deny';
   el('preview').textContent=name+' · '+workspace+'\n'+(name==='fs_write'?result.target+'\n'+result.diff+'\nProposed contents:\n'+args.content:args.code);
   const answer=new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='allow'),{once:true}));
   dialog.showModal();const allow=await answer;requestId=crypto.randomUUID().replaceAll('-','');
   el('cancel').disabled=!allow||name==='fs_write';el('status').textContent=allow?'Running…':'Denied.';
   result=await api({action:'decide',ticket:result.ticket,allow,request_id:requestId});
   if(!allow)return;
  }
  el('output').textContent=result.output||'(no output)';
  el('status').textContent=result.limited||('exit_code' in result?'Exit '+result.exit_code+' · '+result.seconds+' s':'Done.');
 }catch(error){el('status').textContent=error.message;}
 finally{requestId=null;el('cancel').disabled=true;lock(false);}
};
el('cancel').onclick=()=>api({request_id:requestId},'/api/cancel').catch(e=>el('status').textContent=e.message);
api({action:'catalog'}).then(items=>{el('template').replaceChildren(...items.map(i=>new Option(i.label,i.code)));display();}).catch(e=>el('status').textContent=e.message);
setInterval(()=>api({},'/api/ping').catch(()=>{}),10000);

