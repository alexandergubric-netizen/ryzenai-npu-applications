'use strict';
const el=id=>document.getElementById(id),workspace=new URLSearchParams(location.search).get('workspace')||'default';
el('docs').href='/docs?workspace='+encodeURIComponent(workspace);
const headers={'X-Tsubasa':'1','Content-Type':'application/json'};
async function api(body,path='/api/knowledge'){
  const r=await fetch(path,{method:'POST',headers,body:JSON.stringify({workspace,...body})});
  const data=await r.json();if(!r.ok)throw Error(data.error);return data.result;
}
function report(e){el('status').textContent=e.message;}
async function refresh(){
  const info=await api({action:'list'}),files=await api({action:'list'},'/api/files');
  el('file').replaceChildren(...files.filter(f=>/\.(pdf|txt|md)$/i.test(f)).map(f=>new Option(f,f)));
  el('areas').replaceChildren(...[...new Set([...info.areas,...info.sources.map(s=>s.area)])].map(a=>new Option(a,a)));
  el('sources').replaceChildren(...info.sources.map(s=>{
    const p=document.createElement('p'),b=document.createElement('button');
    p.append(s.area+' · '+s.name+' ');b.textContent='Remove from index';
    b.onclick=()=>change('remove',s.area,s.name).catch(report);p.append(b);return p;}));
}
async function change(action,area,name){
  const proposal=await api({action,area,paths:[name]});
  const allow=confirm((action==='remove'?'Remove from index':'Index source')+'?\n'+area+' / '+name);
  const result=await api({action:'decide',ticket:proposal.ticket,allow});
  el('status').textContent=!allow?'Cancelled.':result.unchanged?'Already up to date.':'Index updated.';await refresh();
}
el('add').onclick=()=>change('kb_add',el('area').value,el('file').value).catch(report);
el('upload').onchange=async()=>{try{
  const file=el('upload').files[0];if(!file||!confirm('Copy '+file.name+' into this workspace?'))return;
  const r=await fetch('/api/files/import?'+new URLSearchParams({workspace,name:file.name}),{method:'POST',headers:{'X-Tsubasa':'1'},body:file});
  if(!r.ok)throw Error((await r.json()).error);await refresh();el('file').value=file.name;
}catch(e){report(e);}};
el('search').onsubmit=async e=>{e.preventDefault();el('hits').replaceChildren();try{
  const hits=await api({action:'kb_search',area:el('area').value,query:el('query').value,k:5});
  for(const h of hits){const block=document.createElement('blockquote'),cite=document.createElement('cite');
    block.textContent=h.excerpt;cite.textContent='['+h.citation+'] '+h.source+(h.page?' · page '+h.page:'');el('hits').append(block,cite);}
  el('status').textContent=hits.length?hits.length+' matching passages.':'No supporting passage found.';
}catch(e){report(e);}};
refresh().catch(report);
setInterval(()=>fetch('/api/ping',{method:'POST',headers,body:'{}'}).catch(()=>{}),10000);

