// Terminal command cards and image results: the two modes that answer with something to act on, not just text.
const $el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;};
const button=(text,cls='ghost',title='')=>{const b=$el('button',cls,text);b.type='button';if(title)b.title=title;return b;};
export const post=(path,body)=>fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Tsubasa':'1'},body:JSON.stringify(body)});

/** Server-sent events from /api/chat, /api/terminal-ai and /api/images-create, one parsed event at a time. */
export async function readEvents(response,onEvent){
  if(!response.ok)throw new Error((await response.json().catch(()=>({}))).error||`HTTP ${response.status}`);
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
  for(;;){
    const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});
    let at;while((at=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,at);buffer=buffer.slice(at+2);for(const line of block.split('\n'))if(line.startsWith('data: '))await onEvent(JSON.parse(line.slice(6)));}
    if(done)break;
  }
}

/* ------------------------------------------------------------------ terminal ------------------------------------------------------------------ */
const RISK={safe:['Safe','Only reads information. Runs on one click.'],
  caution:['Review','Changes a setting, a file or an app. Read it before running.'],
  danger:['Careful','Deletes, stops or shuts something down. Press Run twice to confirm.'],
  unchecked:['Not checked yet','Tsubasa checks it on this PC when you press Run.']};
function sourceLabel(a){
  const t=a.seconds!=null?` · ${a.seconds} s`:'';
  if(a.how==='library')return 'Tested command · instant, no AI'+t;
  if(a.how==='router')return `Tested command · picked by ${a.model}`+t;
  if(a.how==='ai')return `Written by ${a.model} · checked on this PC`+(a.repairs?` · ${a.repairs} fix${a.repairs>1?'es':''}`:'')+t;
  if(a.how==='saved')return 'From this chat';
  return '';
}

/** A Sensei-style command: source, risk, the exact code, what it does, then Run / Edit / Copy / Open in PowerShell
    and the live output underneath. ctx: {busy(on,requestId), suggest(item), scroll(), notify(text)}. */
export function commandCard(ans,ctx){
  const card=$el('div','cmd-card'),head=$el('div','cmd-head'),src=$el('span','cmd-src',sourceLabel(ans)),risk=$el('span','risk');
  head.append(src,risk);
  const code=$el('pre','cmd-code');code.textContent=ans.code;code.spellcheck=false;code.setAttribute('aria-label','Command');
  const note=$el('p','cmd-note',ans.text||'');note.hidden=!ans.text;
  const reasons=$el('ul','cmd-reasons');
  const actions=$el('div','cmd-actions');
  const runB=button('Run','primary run','Run this command in Tsubasa’s PowerShell session'),editB=button('Edit'),copyB=button('Copy'),winB=button('Open in PowerShell','ghost','Opens a real PowerShell window that runs this command and stays open');
  actions.append(runB,editB,copyB,winB);
  const out=$el('div','console');out.hidden=true;out.setAttribute('role','log');
  const foot=$el('p','cmd-status');foot.hidden=true;
  card.append(head,code,note,reasons,actions,out,foot);
  let ticket=ans.ticket||null,check=ans.check||null,armed=0;
  const text=()=>code.textContent.trim();
  function paint(){
    const r=check?.risk||'unchecked';card.dataset.risk=r;
    const [label,tip]=RISK[r]||RISK.unchecked;risk.textContent=label;risk.title=tip;
    const items=[...(check?.syntax||[]),...(check?.problems||[]),check?.overreach,...(check?.reasons||[])].filter(Boolean);
    const placeholder=/<[^<>\s]+>/.test(text());
    if(placeholder)items.unshift('Replace the <…> part with your own value: press Edit.');
    if(check?.interactive)items.push('This command waits for typed input: use Open in PowerShell.');
    reasons.replaceChildren(...[...new Set(items)].slice(0,5).map(t=>$el('li','',t)));
    runB.disabled=placeholder||!text()||code.isContentEditable;
  }
  async function recheck(){
    const r=await post('/api/terminal-ai',{action:'check',code:text()});const d=await r.json();
    if(!r.ok)throw new Error(d.error||'Could not check the command.');
    check=d.check;ticket=d.ticket;paint();
  }
  function arm(){
    armed=Date.now();runB.textContent='Press again to run';runB.classList.add('armed');
    setTimeout(()=>{if(Date.now()-armed>=3900){armed=0;runB.textContent='Run';runB.classList.remove('armed');}},4000);
  }
  async function runIt(){
    try{
      if(!ticket)await recheck();
      if(check?.risk==='danger'&&!armed){arm();return;}
      const confirmed=!!armed;armed=0;runB.textContent='Run';runB.classList.remove('armed');
      out.hidden=false;foot.hidden=false;foot.className='cmd-status running';foot.textContent='Running…';
      const promptLine=$el('div','prompt');const where=$el('span','where','PS> ');promptLine.append(where,document.createTextNode(text()));
      out.replaceChildren(promptLine);
      ctx.busy(true);const t0=performance.now();
      const r=await post('/api/terminal-ai',{action:'run',code:text(),ticket,confirmed});ticket=null;
      let any=false;
      await readEvents(r,ev=>{
        if(ev.type==='start')ctx.busy(true,ev.data.request_id);
        if(ev.type==='cwd')where.textContent=`PS ${ev.data}> `;
        if(ev.type==='lines'){for(const [kind,line] of ev.data){const s=$el('div','line '+kind,line||' ');out.append(s);any=true;}out.scrollTop=out.scrollHeight;ctx.scroll();}
        if(ev.type==='ran'){
          const d=ev.data,secs=((d.ms||performance.now()-t0)/1000).toFixed(1);
          if(!any)out.append($el('div','line info','(no output)'));
          foot.className='cmd-status '+(d.ok?'ok':'failed');
          foot.textContent=d.ok?`✓ Done in ${secs} s`:d.restarted?'■ Stopped':`✗ Finished with ${d.errors||0} error${d.errors===1?'':'s'}${d.exit?` · exit code ${d.exit}`:''} · ${secs} s`;
          if(d.dropped)foot.textContent+=` · ${d.dropped} more lines not shown`;
        }
        if(ev.type==='error')throw new Error(ev.data);
      });
    }catch(e){foot.hidden=false;foot.className='cmd-status failed';foot.textContent=e.message;}
    finally{ctx.busy(false);ctx.scroll();}
  }
  runB.onclick=runIt;
  editB.onclick=async()=>{
    if(!code.isContentEditable){code.contentEditable='plaintext-only';code.focus();editB.textContent='Done';runB.disabled=true;return;}
    code.contentEditable='false';editB.textContent='Edit';
    try{await recheck();}catch(e){ctx.notify(e.message);}
  };
  code.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();editB.click();}});
  copyB.onclick=async()=>{try{await navigator.clipboard.writeText(text());copyB.textContent='Copied';setTimeout(()=>copyB.textContent='Copy',1500);}catch{ctx.notify('Copy is blocked in this window. Select the command and press Ctrl+C.');}};
  winB.onclick=async()=>{
    try{
      if(!ticket)await recheck();
      if(check?.risk==='danger'&&!armed){arm();ctx.notify('This command deletes or stops things. Press Run or Open again to confirm.');return;}
      const r=await post('/api/terminal-ai',{action:'open',code:text(),ticket,confirmed:!!armed});ticket=null;armed=0;
      if(!r.ok)throw new Error((await r.json()).error);
    }catch(e){ctx.notify(e.message);}
  };
  if(!ans.code){code.hidden=true;actions.hidden=true;risk.hidden=true;}
  if(ans.suggestions?.length){
    const row=$el('div','did-you-mean');row.append($el('span','label',ans.code?'Related':'Did you mean'));
    for(const s of ans.suggestions){const b=button('❯ '+s.label,'chip-btn');b.onclick=()=>ctx.suggest(s);row.append(b);}
    card.append(row);
  }
  paint();
  return card;
}

/** One agent step (Code mode or Files on this PC). It waits for the user's decision: Run / Allow, Skip or Stop.
    ctx: {decide(payload) -> fetch Response, scroll(), notify(text)}. Returns {el, output(lines), done(info), expire()}. */
const STEP_TITLE={run:'Run a command',write:'Write a file',read:'Read a file',list:'Look in a folder'};
export function stepCard(step,ctx){
  const card=$el('div','cmd-card step-card'),head=$el('div','cmd-head');
  head.append($el('span','step-n',`Step ${step.n}`),$el('span','cmd-src',STEP_TITLE[step.kind]+(step.source?` · ${step.source}`:'')));
  const risk=$el('span','risk');head.append(risk);
  card.append(head);
  if(step.purpose)card.append($el('p','cmd-note',step.purpose));
  let code=null;
  if(step.kind==='run'){code=$el('pre','cmd-code');code.textContent=step.code;code.spellcheck=false;card.append(code);}
  else{const p=$el('p','step-path');p.append($el('span','',step.path));card.append(p);}
  if(step.kind==='write'){
    const diff=$el('pre','diff');
    for(const line of String(step.diff).split('\n')){const s=$el('span',line.startsWith('+')&&!line.startsWith('+++')?'add':line.startsWith('-')&&!line.startsWith('---')?'del':line.startsWith('@@')?'hunk':'',line+'\n');diff.append(s);}
    card.append(diff);
  }
  const reasons=$el('ul','cmd-reasons');card.append(reasons);
  // Administrator steps always ask here first; Windows then shows its own prompt. Read-only steps may run by themselves.
  if(step.admin){const b=$el('p','admin-note');b.append($el('b','','🛡 Needs administrator rights.'),document.createTextNode(' Tsubasa asks you every time; after you allow it, Windows asks too. The output comes back here.'));card.append(b);card.classList.add('admin');}
  const goLabel=step.kind!=='run'?'Allow':step.admin?'Run as administrator':'Run';
  const actions=$el('div','cmd-actions'),go=button(goLabel,'primary run'),edit=button('Edit'),skip=button('Skip','ghost','Skip this step; Tsubasa can try another way'),stop=button('Stop','ghost danger-text','Stop the whole task');
  const elev=step.kind==='run'&&!step.admin?button('Run as admin','ghost','Run it in an administrator PowerShell: Windows asks for permission, and the output comes back here'):null;
  actions.append(go);if(elev)actions.append(elev);if(code&&!step.retry)actions.append(edit);actions.append(skip,stop);card.append(actions);
  const out=$el('div','console');out.hidden=true;card.append(out);
  const foot=$el('p','cmd-status');foot.hidden=true;card.append(foot);
  const check=step.check||null;
  const r=step.kind==='run'?(check?.risk||'caution'):step.kind==='write'?'caution':'safe';card.dataset.risk=r;
  const labels={safe:step.kind==='run'?'Safe':'Read only',caution:step.kind==='write'?(step.exists?'Changes a file':'New file'):'Review',danger:'Careful'};
  risk.textContent=labels[r];
  const items=[...(check?.syntax||[]),...(check?.problems||[]),...(check?.reasons||[])].filter(Boolean);
  if(code&&/<[^<>\s]+>/.test(step.code))items.unshift('Replace the <…> part with your own value: press Edit.');
  reasons.replaceChildren(...[...new Set(items)].slice(0,5).map(t=>$el('li','',t)));
  let armed=0,decided=false;
  const all=[go,edit,skip,stop,elev].filter(Boolean);
  const lock=label=>{decided=true;for(const b of all)b.disabled=true;card.classList.add('decided');foot.hidden=false;foot.className='cmd-status running';foot.textContent=label;};
  const showPrompt=admin=>{out.hidden=false;const p=$el('div','prompt');p.append($el('span','where',admin?'PS (admin)> ':'PS> '),document.createTextNode(code.textContent.trim()));out.replaceChildren(p);};
  async function send(action,elevate=false){
    if(decided)return;
    const b=elevate&&elev?elev:go;
    if(action==='allow'&&r==='danger'&&armed!==b){armed=b;const was=b.textContent;b.textContent='Press again to run';b.classList.add('armed');setTimeout(()=>{if(!decided&&armed===b){armed=0;b.textContent=was;b.classList.remove('armed');}},4000);return;}
    lock(action==='allow'?(step.kind==='run'?(elevate?'Waiting for the Windows prompt…':'Running…'):'Working…'):action==='skip'?'Skipping…':'Stopping…');
    if(action==='allow'&&step.kind==='run')showPrompt(elevate);
    try{
      const res=await ctx.decide({action,elevate,confirmed:!!armed,code:code?code.textContent.trim():undefined});
      if(!res.ok)throw new Error((await res.json().catch(()=>({}))).error||'This step expired.');
    }catch(e){foot.className='cmd-status failed';foot.textContent=e.message;}
    ctx.scroll();
  }
  go.onclick=()=>send('allow',!!step.admin);skip.onclick=()=>send('skip');stop.onclick=()=>send('stop');
  if(elev)elev.onclick=()=>send('allow',true);
  if(step.auto){actions.hidden=true;card.classList.add('auto');risk.textContent='Read only · ran by itself';risk.title='Read-only commands run automatically (Settings → Privacy & data)';lock('Running…');showPrompt(false);}
  edit.onclick=()=>{if(!code.isContentEditable){code.contentEditable='plaintext-only';code.focus();edit.textContent='Done';go.disabled=true;return;}code.contentEditable='false';edit.textContent='Edit';go.disabled=false;ctx.notify('Edited: Tsubasa checks the new command again when you press Run.');};
  return {el:card,
    output(lines){out.hidden=false;for(const [kind,line] of lines)out.append($el('div','line '+kind,line||' '));out.scrollTop=out.scrollHeight;ctx.scroll();},
    done(d){
      foot.hidden=false;decided=true;for(const b of all)b.disabled=true;card.classList.add('decided');
      if(d.kind==='ran'){const secs=((d.ms||0)/1000).toFixed(1),as=d.admin?' as administrator':'';if(!out.querySelector('.line:not(.info)'))out.append($el('div','line info','(no output)'));foot.className='cmd-status '+(d.ok?'ok':'failed');foot.textContent=d.ok?`✓ Done${as} in ${secs} s`:`✗ Finished${as} with ${d.errors||0} error${d.errors===1?'':'s'}${d.exit?` · exit code ${d.exit}`:''}`;}
      else{foot.className='cmd-status '+(d.ok?'ok':d.kind==='skipped'||d.kind==='stopped'?'':'failed');foot.textContent=(d.ok?'✓ ':d.kind==='skipped'?'↷ ':d.kind==='stopped'?'■ ':'✗ ')+(d.text||'');}
      ctx.scroll();
    },
    expire(){if(!decided){decided=true;for(const b of all)b.disabled=true;foot.hidden=false;foot.textContent='Not run';}}};
}

/** A terminal answer saved in a chat: the first powershell block becomes a card again (checked when run). */
export function savedCommand(markdown){
  const m=/```(?:powershell|pwsh|ps1?|zsh|bash|sh)?[ \t]*\r?\n([\s\S]*?)```/i.exec(markdown||'');
  if(!m)return null;
  return {code:m[1].trim(),text:markdown.replace(m[0],'').trim(),how:'saved',check:null,ticket:null,suggestions:[]};
}

/* ------------------------------------------------------------------ images ------------------------------------------------------------------ */
export const IMAGE_TAG=/\[\[image:([a-f0-9]{32}):([\w-]+)\]\]/;
export function imagePending(expected,size='1024x1024'){
  const box=$el('div','image-card pending'),canvas=$el('div','image-canvas'),cap=$el('p','image-cap','Starting…');
  const [w,h]=size.split('x').map(Number);canvas.style.aspectRatio=`${w} / ${h}`;
  canvas.append($el('span','brush'));box.append(canvas,cap);
  return {box,tick(s){cap.textContent=`Painting… ${s} s${expected?` (usually about ${expected} s)`:''}`;},status(t){cap.textContent=t;}};
}
export function imageCard(id,workspace,caption){
  const q=new URLSearchParams({workspace,id}),box=$el('figure','image-card'),img=$el('img');
  img.alt=caption||'Generated image';img.src='/api/image?'+q;img.decoding='async';
  img.onload=()=>box.classList.add('loaded');
  const cap=$el('figcaption','image-cap',caption||''),acts=$el('div','image-actions');
  const dl=$el('a','ghost-link','Download');dl.href='/api/image?'+q+'&download=1';
  const gal=$el('a','ghost-link','Open gallery');gal.href='/images?workspace='+encodeURIComponent(workspace);
  acts.append(dl,gal);box.append(img,cap,acts);
  return box;
}
