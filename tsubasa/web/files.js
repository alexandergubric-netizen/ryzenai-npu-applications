'use strict';
const el=id=>document.getElementById(id), val=id=>el(id).value;
const workspace=new URLSearchParams(location.search).get('workspace') || 'default';
const sheet=location.pathname==='/tables', headers={'X-Tsubasa':'1','Content-Type':'application/json'};
for(const tab of ['docs','tables']) el(tab).href='/'+tab+'?workspace='+encodeURIComponent(workspace);
el('title').textContent=sheet?'Tables':'Docs';
el(sheet?'document':'table').hidden=true;
async function request(body){
  const r=await fetch('/api/files',{method:'POST',headers,body:JSON.stringify({workspace,...body})});
  if(!r.ok)throw Error((await r.json()).error);
  return body.action==='download'?r.blob():(await r.json()).result;
}
async function refresh(name){
  const previous=name || val('file'), files=await request({action:'list'});
  el('file').replaceChildren(...files.map(f=>new Option(f,f)));
  if(files.includes(previous))el('file').value=previous;
}
async function run(name,args){
  let result=await request({action:'run',name,args});
  if(result.ticket){
    const allow=confirm('Allow '+name+' to write '+result.target+'?\n\n'+JSON.stringify(result.arguments,null,2));
    const dest=result.target;
    result=await request({action:'decide',ticket:result.ticket,allow});
    await refresh(allow?dest:null);
  }
  if(result.png){el('preview').src='data:image/png;base64,'+result.png;el('preview').hidden=false;}
  else el('result').textContent=JSON.stringify(result,null,2);
  return result;
}
function bind(id,fn,event='click'){
  el(id).addEventListener(event,async()=>{try{
    el('status').textContent='';el('result').textContent='';el('preview').hidden=true;
    await fn();
  }catch(e){el('status').textContent=e.message;}});
}
bind('upload',async()=>{
  const f=el('upload').files[0];if(!f || !confirm('Copy '+f.name+' into this workspace?'))return;
  const r=await fetch('/api/files/import?'+new URLSearchParams({workspace,name:f.name}),{method:'POST',headers:{'X-Tsubasa':'1'},body:f});
  if(!r.ok)throw Error((await r.json()).error);await refresh(f.name);
},'change');
bind('load',async()=>{
  const data=await request({action:'draft',name:val('file')});
  if(sheet && data.columns){el('cols').value=data.columns.join('\t');el('rows').value=data.rows.map(row=>row.map(v=>v?.formula??v??'').join('\t')).join('\n');el('table-name').value=val('file').replace(/\.tstable\.json$/,'');}
  else if(!sheet && data.markdown!==undefined){el('markdown').value=data.markdown;el('doc-title').value=data.title;}
  else throw Error('Select a draft matching this editor.');
});
bind('download',async()=>{const url=URL.createObjectURL(await request({action:'download',name:val('file')}));const a=document.createElement('a');a.href=url;a.download=val('file');a.click();setTimeout(()=>URL.revokeObjectURL(url),3000);});
bind('open',async()=>{if(confirm('Open '+val('file')+' in Washi?'))await request({action:'open',name:val('file'),confirmed:true});});
bind('create-doc',()=>run('doc_create',{title:val('doc-title'),markdown:val('markdown')}));
bind('edit-doc',()=>run('doc_edit',{id:val('file'),section:'*',markdown:val('markdown')}));
function typed(v){if(/^=SUM\([A-Z]+\d+:[A-Z]+\d+\)$/.test(v))return {formula:v};return /^-?(0|[1-9]\d*)(\.\d+)?$/.test(v)?Number(v):v;}
bind('create-table',()=>run('table_create',{id:val('table-name'),columns:val('cols').split('\t'),rows:val('rows')?val('rows').split('\n').map(r=>r.split('\t').map(typed)):[]}));
bind('edit-table',()=>run('table_update',{id:val('file'),ops:[{row:+val('row'),column:+val('col'),value:typed(val('cell'))}]}));
bind('export',()=>run(sheet?'table_export':'doc_export',{id:val('file'),out:val('out'),format:val('out').split('.').pop().toLowerCase()}));
bind('targets',async()=>{const fmts=await run('list_targets',{path:val('file')});el('target').replaceChildren(...fmts.map(f=>new Option(f,f)));});
bind('convert',()=>run('convert_file',{path:val('file'),out:val('out'),target:val('target')}));
bind('search',()=>run('pdf_search',{path:val('file'),query:val('query')}));
bind('read',()=>run('pdf_read',{path:val('file'),pages:val('pages')}));
bind('extract',()=>run('pdf_extract_pages',{path:val('file'),pages:val('pages'),out:val('out')}));
bind('render',()=>run('pdf_render_page',{path:val('file'),page:+val('pages')}));
bind('merge',()=>run('pdf_merge',{paths:val('merge-list').split('\n').map(x=>x.trim()).filter(Boolean),out:val('out')}));
refresh().catch(e=>el('status').textContent=e.message);
setInterval(()=>fetch('/api/ping',{method:'POST',headers,body:'{}'}).catch(()=>{}),10000);

