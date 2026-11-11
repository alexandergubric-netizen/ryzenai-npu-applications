import {MarkdownStream} from '/markdown.js';
import {readEvents,post,commandCard,stepCard,savedCommand,imagePending,imageCard,IMAGE_TAG} from '/modes.js';
import {cadCard} from '/cad.js';
let TERMINAL_MODEL='qwen3-it:4b', PLATFORM='windows', ENGINE='flm', ENGINE_LABEL='FastFlowLM';
const IMAGE_MODEL='RealVisXL V5 Lightning', IMAGE_OPTION='@image';
const $ = id => document.getElementById(id);
let state=null, currentChat=null, currentWorkspace='default';
let busy = false, online = false, requestId = null, stopped = false;
// The model the engine last served for Tsubasa. Confirmation is needed only when a request could switch models.
let lastModel = null;
let models = {};            // id -> {context_length, supports_vision, supports_reasoning}
let lastUsage = null;       // usage of the latest finished answer in this chat
let attached = [];          // files imported into the workspace for the next message

/* ------------------------------------------------------------------ modes ------------------------------------------------------------------
   Chat is the everyday window (documents, PDFs, tables, your files, the Library). Code (the switch at the top right)
   adds an approved, step-by-step terminal and file agent. Images paints with RealVisXL. */
const MODES = {
  chat:   {label:'Chat', badge:'', placeholder:'How can I help you today?', sub:'Your thoughts stay on this machine.',
           hint:'Chat · documents, PDFs, tables, files on this PC and your Library',
           suggestions:[['✎ Explain something','Explain this concept simply: '],['▤ Summarize a PDF','Summarize the attached PDF in five bullet points'],['📁 Tidy my Downloads','List what is in my Downloads folder and suggest how to organise it'],['⇄ Convert a file','Convert the attached CSV to XLSX'],['☰ Make a plan','Make a step-by-step plan for ']]},
  code:   {label:'Code', badge:'', greeting:'What are we building?', placeholder:'Describe what to build, fix or run…',
           sub:'Your chosen model plans and writes the code. Terminal steps are written by qwen3-it:4b from Sensei’s tested commands and checked on this PC. Every step waits for your approval.',
           hint:'Code · you approve every step · Stop at any time',
           suggestions:[['❯ Python script','In my Documents\\tsubasa-code folder, write a Python script that lists the 10 largest files in a folder I give it, then run it on my Downloads folder'],['❯ My dev setup','Which versions of Python, Node and Git are installed?'],['❯ Explain a project','Look at my project folder and explain what the code does'],['❯ Free disk space','How much free space is on my disks'],['❯ Brightness 70%','Set the brightness to 70 percent']]},
  print3d:{label:'3D Print', badge:'3D Print · Experimental', greeting:'What should we print?', placeholder:'Describe the part and its sizes, or attach photos or a sketch…',
           sub:'Attach photos or a sketch and give the sizes you need. Tsubasa thinks the design through, builds a 3D model you can turn and resize, recommends a material and saves an STL for your slicer.',
           hint:'3D Print · thinks deeply · OpenSCAD model → STL · edit the dimensions below the model',
           suggestions:[['⬡ Wall hook','A wall hook for a towel, 2 screw holes for 4 mm screws, holds 2 kg, 60 mm deep'],['⬡ Phone stand','A phone stand for a 75 mm wide phone, 65° viewing angle, cable slot at the back'],['⬡ Cable clips','A set of 4 cable clips for 6 mm cables that screw onto a desk edge'],['⬡ From a photo','Model the object in the attached photo. It is about 80 mm wide.'],['⬡ Replacement knob','A replacement knob for a 6 mm D-shaft (flat at 4.5 mm), 30 mm diameter, knurled grip']]},
  images: {label:'Images', badge:'Images', greeting:'What should we imagine?', placeholder:'Describe the picture: subject, style, light…',
           sub:'RealVisXL V5 Lightning paints it on the Radeon graphics chip, about 50 seconds per picture. Pick the shape below; your message is the prompt.', hint:'Images · RealVisXL V5 Lightning · local, no chat model needed', workbench:'/images',
           suggestions:[['✦ Watercolor','A watercolor bird flying above a mountain lake at sunrise'],['✦ Product photo','A ceramic mug on a wooden table, soft daylight, product photo, shallow depth of field'],['✦ Retro poster','A retro travel poster of Bratislava castle, bold flat colours'],['✦ Portrait','Portrait of an old fisherman, golden hour, 85mm photo']]},
};
// Chats saved in the earlier area modes open in their new home.
const ALIAS={terminal:'code',docs:'chat',tables:'chat',audio:'chat',knowledge:'chat'};
const TOOL_IDS = ['file-tools','practice-tools','knowledge-tools','terminal-tools','pc-tools','library-tools'];
let mode = 'chat';
function modeMap(){try{return JSON.parse(localStorage.getItem('tsubasa.chatModes')||'{}');}catch{return {};}}
function rememberMode(id,m){try{const map=modeMap();map[id]=m;localStorage.setItem('tsubasa.chatModes',JSON.stringify(map));}catch{}}
function applyModeTools(){for(const id of ['practice-tools','knowledge-tools','terminal-tools'])$(id).checked=false;}
function setMode(m){
  m=ALIAS[m]||m;if(!MODES[m])m='chat';
  if(m==='print3d'&&!prefs().print3d)m='chat';   // the experimental tab is off in Settings
  mode=m;const cfg=MODES[m];
  document.body.dataset.mode=m;document.body.dataset.area=m==='code'?'terminal':m;
  document.querySelectorAll('.tools-nav .nav-item[data-mode]').forEach(b=>{if(b.dataset.mode===(m==='code'?'chat':m))b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  document.querySelectorAll('#mode-switch button').forEach(b=>b.setAttribute('aria-checked',String(b.dataset.mode===m)));
  // The Chat/Code switch belongs to the chat tab only; Images and 3D Print are tabs of their own.
  $('mode-switch').dataset.on=m;$('mode-switch').hidden=m!=='chat'&&m!=='code';
  $('mode-badge').hidden=!cfg.badge;$('mode-badge').textContent=cfg.badge;$('mode-badge').dataset.tab=m;
  $('workbench').hidden=!cfg.workbench;if(cfg.workbench)$('workbench').href=cfg.workbench+'?workspace='+encodeURIComponent(currentWorkspace);
  $('message').placeholder=cfg.placeholder;$('mode-hint').textContent=cfg.hint;
  $('suggestions').replaceChildren(...cfg.suggestions.map(([label,prompt])=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=()=>{const t=$('message');t.value=prompt;grow();controls();t.focus();t.setSelectionRange(t.value.length,t.value.length);};return b;}));
  $('shape-menu').hidden=m!=='images';$('code-warning').hidden=m!=='code';$('code-folder').hidden=m!=='code';
  for(const id of ['think-chip','thorough-chip'])$(id).hidden=m==='images';
  document.querySelector('.message-tools').hidden=m!=='chat';$('attach').hidden=m!=='chat'&&m!=='print3d';$('context-menu').hidden=m==='images';
  $('print-options').hidden=m!=='print3d';$('print-warning').hidden=m!=='print3d';if(m==='print3d')enterPrint();
  if(m==='code'){post('/api/terminal-ai',{action:'warm'}).catch(()=>{});showFolder();}
  fillModels();applyModeTools();greet();updateContext();
  if(m==='images'&&$('status').textContent.startsWith('Loading '))$('status').textContent='';
  if(m!=='images')preload($('model').value);
}
/* Preload: the engine holds one model at a time and a swap takes about 9 s (qwen3-it:4b) to 30 s (liberty).
   Switching modes or models starts the swap at once, so it happens while you type instead of after you send. */
let warming=null,warmTimer=null;
async function preload(model){
  if(!prefs().preload||!online||busy||!models[model]||model===lastModel||model===warming)return;
  warming=model;clearTimeout(warmTimer);
  try{
    const r=await api('/api/warm',{model});
    if(!r.started){warming=null;return;}
    if(!$('status').textContent)$('status').textContent=`Loading ${model} in the background…`;
    const t0=Date.now();
    const poll=async()=>{
      const st=await api('/api/status').catch(()=>null);
      if(st?.last_observed_model===model&&!st.warming){lastModel=model;warming=null;if($('status').textContent.startsWith('Loading '+model+' in the background'))$('status').textContent='';return;}
      if(Date.now()-t0<150000&&warming===model)warmTimer=setTimeout(poll,1500);else warming=null;
    };
    warmTimer=setTimeout(poll,1500);
  }catch{warming=null;}
}
/* The model menu follows the mode: chat models (plus RealVisXL, which opens Images), the code model, or RealVisXL.
   Only the model name is shown, so it is never cut off; Settings → Models describes each one. */
let inventory={models:[],default:'',suggested:[]};
const chosen={chat:'',code:'',print3d:''};
function pick(list,...wants){for(const w of wants)if(w&&list[w])return w;return '';}
function chatModel(){return pick(models,chosen.chat,prefs().defaultModel,inventory.default);}
function codeModel(){return pick(models,chosen.code,prefs().codeModel,TERMINAL_MODEL,inventory.default);}
function fillModels(){
  const sel=$('model');
  const opt=m=>{const o=new Option(m.id+(m.id===inventory.default?' (default)':m.id===TERMINAL_MODEL&&mode==='code'?' (fastest)':''),m.id);o.title=MODEL_NOTES[m.id]||'';return o;};
  if(mode==='images'){sel.replaceChildren(new Option(IMAGE_MODEL,IMAGE_OPTION));sel.title='Images always use RealVisXL V5 Lightning';return;}
  const list=inventory.models.map(opt);
  if(mode==='chat'){const group=document.createElement('optgroup');group.label='Pictures';group.append(new Option(`${IMAGE_MODEL} → Images`,IMAGE_OPTION));list.push(group);}
  sel.replaceChildren(...list);
  const want=mode==='code'?codeModel():mode==='print3d'?pick(models,chosen.print3d,prefs().printModel,'qwen-liberty3.5:9b',inventory.default):chatModel();if(want)sel.value=want;
  sel.title=mode==='code'?'Code model: plans and writes the code. Terminal commands are always written by qwen3-it:4b.':'Model for this chat';
}
async function showFolder(){try{const r=await api('/api/terminal-ai',{action:'cwd'});$('code-folder-name').textContent=shortPath(r.cwd);$('code-folder').title='Project folder: '+r.cwd+' (click to change)';}catch{}}
function shortPath(p){const sep=String(p).includes('\\')?'\\':'/',parts=String(p).split(sep).filter(Boolean);return parts.length>2?'…'+sep+parts.slice(-2).join(sep):p;}

/* ------------------------------------------------------------------ prefs (local) ------------------------------------------------------------------ */
const PREF_DEFAULTS={textSize:'m',motion:'system',sendKey:'enter',defaultModel:'',codeModel:'',defaultThink:false,defaultLong:false,askSwitch:true,preload:true,shape:'1:1',quality:0,printMaterial:'PLA',printInfill:20,printBed:[220,220,250],printModel:'',print3d:true,autoRun:true};
function setPref(k,v){const p=prefs();p[k]=v;try{localStorage.setItem('tsubasa.prefs',JSON.stringify(p));}catch{}}
function prefs(){try{return {...PREF_DEFAULTS,...JSON.parse(localStorage.getItem('tsubasa.prefs')||'{}')};}catch{return {...PREF_DEFAULTS};}}
function applyPrefs(){const p=prefs();$('print-tab').hidden=!p.print3d;document.body.dataset.textsize=p.textSize;document.body.dataset.motion=p.motion;$('message').title=p.sendKey==='ctrl'?'Ctrl+Enter sends':'';document.querySelector('.dock footer .keys').innerHTML=p.sendKey==='ctrl'?'<kbd>Ctrl</kbd> <kbd>Enter</kbd> send · <kbd>Enter</kbd> new line':'<kbd>Enter</kbd> send · <kbd>Shift</kbd> <kbd>Enter</kbd> new line';}

/* ------------------------------------------------------------------ server helpers ------------------------------------------------------------------ */
async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Tsubasa':'1'},body:JSON.stringify(body)});
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}
function controls() {
  document.body.dataset.busy = String(busy);
  // Images need no chat engine; in Code, tested library commands work offline too (the server says when AI is needed).
  const needsEngine=mode==='chat'||mode==='print3d';
  for (const id of ['model','refresh','load','send']) $(id).disabled = busy || (id !== 'refresh' && ((needsEngine&&!online&&!(id==='send'&&engineStarting)) || !$('model').options.length));
  // While the engine is still starting you can already send: the message waits and goes out when it is ready.
  if(queued)$('send').disabled=true;
  if(mode==='images')$('model').disabled=true;
  $('load').disabled=$('load').disabled||$('model').value===IMAGE_OPTION;
  if (!busy && !$('message').value.trim()) $('send').disabled = true;
  $('stop').disabled = !busy || !requestId || stopped;
  $('close').disabled = busy;
  if (!busy && state && $('message').value.trimStart().startsWith('/')) $('send').disabled=false;
  $('progress').hidden = !busy;
  for(const id of ['workspace','new-chat','add-workspace','manage-workspaces','practice-tools','file-tools','terminal-tools','knowledge-tools','pc-tools','library-tools','persona-open','think','thorough','delete-chat','attach','code-folder']) $(id).disabled=busy;
  document.querySelectorAll('#mode-switch button').forEach(b=>b.disabled=busy);
  $('delete-chat').disabled=busy || !currentChat;
  const thinks=canThink($('model').value);
  $('think').disabled=busy || !thinks;
  $('think-chip').title=thinks?'Think first: the model reasons step by step before it answers. Slower, but better for tricky questions.':'Think first is available with reasoning models such as qwen3.5 (pick one in the model menu).';
  document.querySelectorAll('#chats button, .tools-nav .nav-item[data-mode]').forEach(b=>b.disabled=busy);
}
const canThink=id=>ENGINE==='mlx'?!!models[id]?.supports_reasoning:/^(qwen3\.5|qwen-liberty3\.5)/.test(id||'');
const LOAD_SECONDS={'qwen-liberty3.5:9b':25,'qwen3.5:9b':25,'qwen3.5:4b':10,'qwen3.5:2b':7,'qwen3-it:4b':9};  // measured swaps (2026-11-04)
const MODEL_NOTES={'qwen3-it:4b':'Fastest','qwen3.5:2b':'Quick · sees images','qwen3.5:4b':'Balanced · sees images','qwen3.5:9b':'Best · sees images','qwen-liberty3.5:9b':'Default · uncensored · sees images'};
// Right after launch the engine is often still starting, so keep checking for about two minutes.
let engineWait=0, engineTimer=null, engineStarting=false, queued=false;
async function refresh() {
  clearTimeout(engineTimer);
  try {
    const [list,status,images] = await Promise.all([api('/api/models').catch(() => null),api('/api/status'),engineWait===0?api('/api/images',{action:'status',workspace:currentWorkspace}).catch(()=>null):null]);
    const inv = list || {models: [], default: '', suggested: []};
    if(list){TERMINAL_MODEL=list.terminal||TERMINAL_MODEL;PLATFORM=list.platform||PLATFORM;ENGINE=list.engine||ENGINE;ENGINE_LABEL=list.engine_label||ENGINE_LABEL;applyPlatform(list);}
    if(inv.models.length||!inventory.models.length||ENGINE==='mlx'){inventory=inv;models=Object.fromEntries(inv.models.map(m=>[m.id,m]));}
    fillModels();
    $('pref-model').replaceChildren(new Option(`App default (${inventory.default||'none'})`,''),...inventory.models.map(m=>new Option(m.id,m.id)));
    $('pref-code-model').replaceChildren(new Option(`App default (${TERMINAL_MODEL||'none'})`,''),...inventory.models.map(m=>new Option(m.id,m.id)));
    online = status.online;
    if(images)$('settings-images').textContent=images.result&&images.result.installed===false&&!images.result.online?'Image engine: not set up on this computer (optional; see the README).':images.result?.online?`Image engine: running · ${IMAGE_MODEL}`:`Image engine: stopped · starts by itself with the first picture (${IMAGE_MODEL})`;
    if (online) engineWait=0;
    $('engine-start').hidden=online;$('engine-stop').hidden=!online;
    const waiting=!online && engineWait<60;engineStarting=waiting;
    if (status.last_observed_model) lastModel = status.last_observed_model;
    $('connection').dataset.online=String(online);
    $('connection').textContent = online ? 'Engine connected' : waiting ? 'Engine starting…' : 'Engine offline';
    $('settings-engine').textContent = online ? `Chat engine: connected${lastModel?` · loaded ${lastModel}`:''} · ${inventory.models.length} chat models installed` : 'Chat engine: offline. Press Start engine below.';
    $('status').textContent = online ? (inventory.models.length ? '' : 'Engine connected, but installed models could not be listed. Open the engine menu and choose Refresh.') : waiting ? 'Waiting for the AI engine to start… This connects by itself. Saved chats and local tools already work.' : (ENGINE==='mlx'&&!inventory.models.length?'No model is installed yet. Open Settings → Engine to download one. ':'The AI engine is stopped. Open Settings → Engine and press Start. ')+'Saved chats and local tools still work.';
    if(mode==='images')$('status').textContent='';
    if(queued&&!online)$('status').textContent='Your message goes out as soon as the engine is ready…';
    if(mode==='code'&&!online)$('status').textContent=waiting?'Engine starting… Tested library commands already work.':'Engine offline · tested library commands still work; everything else needs the engine.';
  } catch(e) { online = false; $('connection').dataset.online='false'; $('connection').textContent='Engine unavailable'; $('status').textContent = e.message; }
  controls();updateContext();
  // Check every 2 s for two minutes after opening, then every 10 s, so a later engine start is noticed too.
  if (!online) { engineWait++; engineTimer=setTimeout(refresh,engineWait<60?2000:10000); }
  if (online && queued) { queued=false; run(); }
}
function confirmUse(switching) {
  // Same model as last time: nothing is swapped, so don't interrupt every message with a dialog.
  if (!switching && lastModel && lastModel === $('model').value) return Promise.resolve(true);
  if (!prefs().askSwitch || warming===$('model').value) return Promise.resolve(true);
  $('confirm-skip').checked=false;
  $('confirm').addEventListener('close',()=>{if($('confirm').returnValue==='allow'&&$('confirm-skip').checked)setPref('askSwitch',false);},{once:true});
  $('confirm').querySelector('h2').textContent = lastModel ? 'Switch the shared AI engine?' : 'Use the shared AI engine?';
  $('confirm-text').textContent = `This request uses ${$('model').value}${lastModel ? ` instead of ${lastModel}` : ''}. The engine loads it if another model is active, which takes 15–40 s.`;
  return new Promise(resolve => {
    $('confirm').addEventListener('close',()=>resolve($('confirm').returnValue === 'allow'),{once:true});
    $('confirm').returnValue='cancel';
    $('confirm').showModal();
  });
}
// Hint lines Tsubasa adds for the model ("[Attached PDF: x]", "(table request)") are hidden from titles and bubbles.
function splitHints(text){
  const files=[],kept=[];
  for(const line of String(text).split('\n')){const a=/^\[Attached (?:audio|PDF|file|image): (.+)\]$/.exec(line.trim());if(a)files.push(a[1]);else if(!/^\([\w ]+ request\)$/.test(line.trim()))kept.push(line);}
  return {text:kept.join('\n').trim(),files};
}
function article(label,text='',fresh=false,user=label==='YOU') {
  const el=document.createElement('article'), title=document.createElement('h3'), body=document.createElement('div');
  el.className=(user?'from-user':'from-assistant')+(fresh?' enter':'');
  title.textContent=label; body.className='body';
  if(user){const s=splitHints(text);body.textContent=s.text;el.append(title,body);if(s.files.length){const row=document.createElement('div');row.className='sent-files';for(const f of s.files){const c=document.createElement('span');c.className='attachment';c.textContent=f;row.append(c);}el.append(row);}}
  else{body.textContent=text;el.append(title,body);}
  $('conversation').append(el);
  return {el,body};
}
/* Attached files are imported into the workspace and named in the message, so the file tools know which file to use. */
const AUDIO=/\.(wav|mp3|flac|ogg|m4a|mp4|mov|mkv|webm)$/i;
// The server offers file tools by keywords in the message; in an area mode, add the area's keyword when it is missing.
const MODE_KEYWORDS={docs:[/pdf|document|docx|markdown|section/i,'Document: '],tables:[/table|csv|spreadsheet|xlsx|cells?/i,'Table: '],images:[/image|picture|illustrat|draw|paint/i,'Create an image: '],audio:[/transcrib|transcript|audio|speech|spoken|vocals/i,'Transcribe: ']};
function modePrefix(text){const k=MODE_KEYWORDS[mode];return k&&!k[0].test(text)?k[1]:'';}
const PICTURE=/\.(png|jpe?g|webp|gif|bmp)$/i;
function attachmentPrefix(){return attached.map(n=>`[Attached ${AUDIO.test(n)?'audio':PICTURE.test(n)?'image':n.toLowerCase().endsWith('.pdf')?'PDF':'file'}: ${n}]`).join('\n');}
function renderAttachments(){
  $('attachments').replaceChildren(...attached.map(n=>{const s=document.createElement('span'),x=document.createElement('button');s.className='attachment';s.textContent=n;x.type='button';x.textContent='✕';x.title='Remove from this message (the file stays in the workspace)';x.onclick=()=>{attached=attached.filter(a=>a!==n);renderAttachments();};s.append(x);return s;}));
  updateContext();
}
// Workspace file names allow letters, digits, spaces and . ( ) - _ ; anything else becomes _.
function safeName(name){
  const dot=name.lastIndexOf('.'),ext=dot>0?name.slice(dot).toLowerCase().replace(/[^\w.]/g,''):'';
  let base=(dot>0?name.slice(0,dot):name).normalize('NFC').replace(/[^\w .()-]/gu,'_').replace(/\.{2,}/g,'.').replace(/^[^\w]+/u,'').trim().slice(0,80);
  return (base||'file')+ext;
}
// Big pictures are shrunk to 1600 px (JPEG) before upload: the model sees them just as well, and they load faster.
async function shrinkPicture(f){
  if(!/^image\/(png|jpeg|webp|bmp)$/.test(f.type)||f.size<1.5*1024*1024)return f;
  try{
    const bmp=await createImageBitmap(f),k=Math.min(1,1600/Math.max(bmp.width,bmp.height));
    const c=new OffscreenCanvas(Math.round(bmp.width*k),Math.round(bmp.height*k));c.getContext('2d').drawImage(bmp,0,0,c.width,c.height);
    const blob=await c.convertToBlob({type:'image/jpeg',quality:0.86});
    return new File([blob],f.name.replace(/\.\w+$/,'')+'.jpg',{type:'image/jpeg'});
  }catch{return f;}
}
const sees=()=>!!models[$('model').value]?.supports_vision;
async function attachFile(original){
  if(!original)return;
  const f=PICTURE.test(original.name)?await shrinkPicture(original):original;
  if(f.size>8*1024*1024){fail(Error(`${original.name} is larger than 8 MB.`));return;}
  const wanted=safeName(f.name);
  $('status').textContent='Adding '+original.name+'…';
  try{
    const r=await fetch('/api/files/import?'+new URLSearchParams({workspace:currentWorkspace,name:wanted}),{method:'POST',headers:{'X-Tsubasa':'1'},body:f});
    const data=await r.json().catch(()=>({}));
    let name=data.result?.saved,note='';
    if(!r.ok){
      // Imports never overwrite: if a file with this name is already in the workspace, use that copy.
      const list=await api('/api/files',{workspace:currentWorkspace,action:'list'}).catch(()=>({result:[]}));
      if(!(list.result||[]).includes(wanted))throw new Error(data.error||'The file could not be added.');
      name=wanted;note='Using the copy of '+wanted+' already in this workspace.';
    }
    if(!attached.includes(name))attached.push(name);renderAttachments();
    if(PICTURE.test(name)&&!sees())note='This model cannot see pictures. Pick qwen-liberty3.5:9b or a qwen3.5 model in the model menu.';
    $('status').textContent=note;
  }catch(e){fail(e);}
}
async function attachMany(files){for(const f of [...files].slice(0,8))await attachFile(f);}
$('attach').onclick=()=>$('attach-input').click();
$('attach-input').onchange=()=>{attachMany($('attach-input').files);$('attach-input').value='';};
$('chat').addEventListener('dragover',e=>{e.preventDefault();$('chat').classList.add('drop');});
$('chat').addEventListener('dragleave',()=>$('chat').classList.remove('drop'));
$('chat').addEventListener('drop',e=>{e.preventDefault();$('chat').classList.remove('drop');if(mode==='chat'||mode==='print3d')attachMany(e.dataTransfer.files);});
// Pasting a screenshot (Ctrl+V) attaches it.
$('message').addEventListener('paste',e=>{const files=[...(e.clipboardData?.files||[])];if(files.length&&(mode==='chat'||mode==='print3d')){e.preventDefault();attachMany(files.map((f,i)=>f.name&&f.name!=='image.png'?f:new File([f],`pasted-${new Date().toISOString().slice(0,19).replace(/[:T]/g,'-')}${i?'-'+i:''}.png`,{type:f.type})));}});

/* ------------------------------------------------------------------ terminal & images ------------------------------------------------------------------
   Terminal: Sensei's pipeline answers with a command card (Run, Edit, Copy, Open in PowerShell, live output).
   Images: the message is the prompt for RealVisXL; no chat model is involved. */
const scrollDown=()=>{const c=$('conversation');if(c.scrollHeight-c.scrollTop-c.clientHeight<200)c.scrollTop=c.scrollHeight;};
const cardCtx={busy(on,id){busy=on;requestId=on?(id||requestId):null;if(on)stopped=false;controls();},scroll:scrollDown,notify:t=>{$('status').textContent=t;}};
async function ensureChat(model){if(!currentChat){const c=await api('/api/store',{action:'chat',workspace:currentWorkspace,model});currentChat=c.id;rememberMode(currentChat,mode);}}
function startTurn(userText){
  busy=true;stopped=false;requestId=null;controls();
  $('empty')?.remove();article('YOU',userText,true);
  const answer=article(state.settings.assistant_name.toUpperCase(),'',true,false);answer.el.classList.add('live');scrollDown();
  return answer;
}
async function endTurn(answer){answer.el.classList.remove('live');busy=false;requestId=null;controls();await loadState().catch(fail);}
/* Code mode and "Files on this PC": the agent works one approved step at a time. Text between steps streams as
   Markdown; each step is a card (Run / Allow, Skip, Stop) with its live output. */
const PC_HINT=/([a-z]:\\|%\w+%|\$home|~[\\/]|\b(desktop|downloads|documents|pictures|music|videos|folders?|directory|directories|my files|this file|that file)\b|\.(txt|md|py|js|json|csv|html|css|ps1|log)\b)/i;
const DOC_HINT=/\b(pdf|docx|xlsx|table|spreadsheet|convert|merge|export|transcri\w*|attached)\b/i;
async function runAgent(code){
  const typed=$('message').value.trim();
  if(busy||!typed)return;
  busy=true;controls();
  if(!(await confirmUse(false))){busy=false;controls();return;}
  $('message').value='';grow();
  const model=$('model').value,answer=startTurn(typed),cards={},started=performance.now();
  let seg=null,first=null;
  const text=()=>{if(!seg){const d=document.createElement('div');d.className='seg-text';answer.body.append(d);seg=new MarkdownStream(d);}return seg;};
  const swapping=lastModel&&lastModel!==model;
  const waitTimer=setInterval(()=>{if(first!==null||stopped)return;const s=Math.round((performance.now()-started)/1000);if(s>=2)$('status').textContent=(swapping?`Loading ${model} (usually about ${LOAD_SECONDS[model]||20} s)…`:'Reading your message…')+` ${s} s`;},1000);
  try{
    await ensureChat(model);await saveOptions();
    const r=await post('/api/agent',{chat_id:currentChat,message:typed,model,code,library:$('library-tools').checked,think:$('think').checked,autorun:!!prefs().autoRun});
    await readEvents(r,ev=>{
      if(ev.type==='start'){requestId=ev.data.request_id;controls();}
      if(ev.type==='status')$('status').textContent=ev.data;
      if(ev.type==='text'&&!stopped){if(first===null&&ev.data.trim()){first=1;$('status').textContent='';}text().append(ev.data);scrollDown();}
      if(ev.type==='library')libraryNote(answer,ev.data);
      if(ev.type==='step'){
        first=1;$('status').textContent='';seg?.flush(true);seg=null;
        const card=stepCard(ev.data,{decide:p=>post('/api/agent-decision',{...p,ticket:ev.data.ticket,request_id:requestId}),scroll:scrollDown,notify:t=>{$('status').textContent=t;}});
        cards[ev.data.n]=card;answer.body.append(card.el);flap();scrollDown();
      }
      if(ev.type==='step_output')cards[ev.data.n]?.output(ev.data.lines);
      if(ev.type==='step_done'){cards[ev.data.n]?.done(ev.data);if(!cards[ev.data.n]&&ev.data.text)text().append(`\n\n> ${ev.data.text}\n\n`);}
      if(ev.type==='usage')lastUsage=ev.data;
      if(ev.type==='done')lastModel=model;
      if(ev.type==='error')throw new Error(ev.data);
    });
  }catch(e){$('status').textContent=e.message;if(first===null&&!$('message').value){$('message').value=typed;grow();}}
  finally{clearInterval(waitTimer);seg?.flush(true);for(const c of Object.values(cards))c.expire();await endTurn(answer);updateContext();}
}
function libraryNote(answer,names){const p=document.createElement('p');p.className='library-note';p.textContent='Library · '+names.join(', ');answer.el.querySelector('h3').after(p);}
// The bird in the sidebar beats its wings once when Tsubasa starts working on something.
function flap(){const b=$('brand-bird');b.classList.remove('flap');void b.offsetWidth;b.classList.add('flap');}

/* Images: shape and quality pick the exact SDXL size; the server accepts only these. */
const SHAPES={'1:1':['1024x1024','768x768'],'4:3':['1152x896','768x576'],'3:4':['896x1152','576x768'],'3:2':['1216x832','768x512'],'2:3':['832x1216','512x768'],'16:9':['1344x768','896x512'],'9:16':['768x1344','512x896'],'21:9':['1536x640','1024x448']};
const SHAPE_NAMES={'1:1':'Square','4:3':'Photo','3:4':'Photo, tall','3:2':'Classic','2:3':'Portrait','16:9':'Wide','9:16':'Phone','21:9':'Cinema'};
function currentSize(){const p=prefs();return (SHAPES[p.shape]||SHAPES['1:1'])[p.quality?1:0];}
function secondsFor(size){const [w,h]=size.split('x').map(Number);return Math.max(12,Math.round(50*w*h/1048576));}
function paintShape(el,shape){const [w,h]=shape.split(':').map(Number),k=16/Math.max(w,h);el.style.width=Math.round(w*k)+'px';el.style.height=Math.round(h*k)+'px';}
function renderShapes(){
  const p=prefs(),size=currentSize();
  $('shape-grid').replaceChildren(...Object.keys(SHAPES).map(s=>{const b=document.createElement('button'),i=document.createElement('i'),t=document.createElement('span');b.type='button';b.setAttribute('aria-pressed',String(s===p.shape));i.className='shape-icon';paintShape(i,s);t.innerHTML='';t.append(Object.assign(document.createElement('b'),{textContent:s}),Object.assign(document.createElement('small'),{textContent:SHAPE_NAMES[s]}));b.append(i,t);b.onclick=()=>{setPref('shape',s);renderShapes();};return b;}));
  document.querySelectorAll('#quality button').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.q)===(p.quality?1:0))));
  paintShape($('shape-icon'),p.shape in SHAPES?p.shape:'1:1');
  $('shape-label').textContent=`${p.shape} · ${size.replace('x','×')}`;
  $('shape-hint').textContent=`${size.replace('x',' × ')} pixels · about ${secondsFor(size)} s`;
}
document.querySelectorAll('#quality button').forEach(b=>b.onclick=()=>{setPref('quality',Number(b.dataset.q));renderShapes();});
async function runImage(){
  const prompt=$('message').value.trim();
  if(busy||!prompt)return;
  $('message').value='';grow();
  const size=currentSize(),answer=startTurn(prompt),pending=imagePending(secondsFor(size),size);
  answer.body.append(pending.box);flap();scrollDown();
  try{
    await ensureChat(chatModel()||TERMINAL_MODEL);
    const r=await post('/api/images-create',{chat_id:currentChat,workspace:currentWorkspace,prompt,size});
    await readEvents(r,ev=>{
      if(ev.type==='start'){requestId=ev.data.request_id;controls();}
      if(ev.type==='status')pending.status(ev.data);
      if(ev.type==='progress')pending.tick(ev.data.seconds);
      if(ev.type==='image'){$('settings-images').textContent=`Image engine: running · ${IMAGE_MODEL} · stops after 3 idle minutes`;pending.box.replaceWith(imageCard(ev.data.id,ev.data.workspace,`${IMAGE_MODEL} · ${size.replace('x','×')} · ${Math.round(ev.data.seconds)} s`));scrollDown();}
      if(ev.type==='error')throw new Error(ev.data);
    });
  }catch(e){pending.box.classList.add('failed');pending.status(e.message);if(!$('message').value){$('message').value=prompt;grow();}}
  finally{await endTurn(answer);}
}
// A saved answer: pictures and terminal commands come back as cards, everything else as Markdown.
function renderSaved(a,content){
  const img=IMAGE_TAG.exec(content);
  if(img){a.body.append(imageCard(img[1],img[2],content.replace(img[0],'').trim()));return;}
  if(mode==='print3d'&&cadCode(content)){renderCad(a,content);return;}
  const cmd=mode==='code'&&!/\*\*Steps\*\*/.test(content)?savedCommand(content):null;
  if(cmd){a.body.append(commandCard(cmd,{...cardCtx,suggest:()=>{}}));return;}
  const md=new MarkdownStream(a.body);md.append(content);md.flush(true);
}

async function run(switching=false) {
  if(!switching&&mode==='code')return runAgent(true);
  if(!switching&&mode==='images')return runImage();
  if(!switching&&mode==='print3d')return runCad();
  // Chat: requests about files and folders on this PC go to the file agent (every file asks first).
  if(!switching&&$('pc-tools').checked&&!attached.length&&PC_HINT.test($('message').value)&&!DOC_HINT.test($('message').value))return runAgent(false);
  if (!switching && !online && engineStarting && $('message').value.trim() && !busy) { queued=true; $('status').textContent='Your message goes out as soon as the engine is ready…'; controls(); return; }
  if (busy || !online || (!switching && !$('message').value.trim())) return;
  busy=true; controls();
  if (!(await confirmUse(switching))) {busy=false;controls();return;}
  requestId=null; stopped=false;
  let renderer=null;
  let answer=null, think=null, done=false, first=null, firstWord=null;
  const typed=$('message').value;
  const prefix=switching?'':attachmentPrefix();
  // Hints go after the user's words, so the chat title (taken from the first message) stays readable.
  const keyword=switching?'':modePrefix(prefix+typed).replace(/:\s*$/,'');
  const notes=[prefix,keyword?`(${keyword.toLowerCase()} request)`:''].filter(Boolean).join('\n');
  const submittedMessage=notes?typed.trimEnd()+'\n\n'+notes:typed;
  const sentAttachments=[...attached];
  if(!switching){$('message').value='';grow();attached=[];renderAttachments();}  // clear at once; restored below if sending fails
  const frames=[];let frameId,previousFrame=null;
  const sample=t=>{if(previousFrame!==null)frames.push(t-previousFrame);previousFrame=t;frameId=requestAnimationFrame(sample);};
  frameId=requestAnimationFrame(sample);
  const started=performance.now();
  $('status').textContent=switching?'Loading selected model…':'';
  // Until the first words arrive, say what the wait is: a model load (measured times) or the prompt being read.
  const want=$('model').value,swapping=switching||(lastModel&&lastModel!==want);
  const waitTimer=setInterval(()=>{if(first!==null||stopped)return;const s=Math.round((performance.now()-started)/1000);if(s>=2)$('status').textContent=(swapping?`Loading ${want} into the engine (usually about ${LOAD_SECONDS[want]||20} s)…`:`Reading your message…`)+` ${s} s`;},1000);
  if (!switching) {
    const isNew=!!$('empty');$('empty')?.remove(); article('YOU',submittedMessage.trim(),true); answer=article(state.settings.assistant_name.toUpperCase(),'',true,false);renderer=new MarkdownStream(answer.body);answer.body.classList.add('streaming');answer.el.classList.add('live');
    if(isNew)document.body.dataset.fresh='false';
    $('conversation').scrollTop=$('conversation').scrollHeight;
    const details=document.createElement('details'), summary=document.createElement('summary');details.className='thinking';
    summary.textContent='Thinking'; think=document.createElement('pre'); details.append(summary,think); details.hidden=true; answer.el.append(details);
  }
  try {
    if(!switching){if(!currentChat){const c=await api('/api/store',{action:'chat',workspace:currentWorkspace,model:$('model').value});currentChat=c.id;rememberMode(currentChat,mode);}await saveOptions();}
    const r=await fetch(switching?'/api/switch':'/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Tsubasa':'1'},body:JSON.stringify({model:$('model').value,message:submittedMessage,confirmed:true,chat_id:currentChat,terminal_tools:$('terminal-tools').checked,knowledge_tools:$('knowledge-tools').checked,knowledge_area:$('knowledge-area').value,file_tools:$('file-tools').checked,practice_tools:$('practice-tools').checked,library:$('library-tools').checked})});
    if(!switching)flap();
    if (!r.ok) throw new Error((await r.json()).error || `HTTP ${r.status}`);
    const reader=r.body.getReader(), decoder=new TextDecoder(); let buffer='';
    function event(ev) {
      if(ev.type==='library'&&answer)libraryNote(answer,ev.data);
      if(ev.type==='attach_notes')$('status').textContent=ev.data.join(' · ');
      if(ev.type==='permission'){
        const p=ev.data, dialog=$('tool-permission');
        $('tool-preview').textContent=p.name+' · '+p.risk+'\n'+p.target+'\n'+JSON.stringify(p.arguments,null,2);
        dialog.returnValue='deny';
        dialog.addEventListener('close',()=>api('/api/tool-decision',{ticket:p.ticket,request_id:p.request_id,allow:dialog.returnValue==='allow'}).catch(fail),{once:true});
        dialog.showModal();
      }
      if(ev.type==='knowledge_proposal' && answer){const p=ev.data,b=document.createElement('button');b.textContent='Review indexing: '+p.plan.paths.join(', ');b.onclick=async()=>{if(busy){fail(Error('Wait for this response to finish.'));return;}const allow=confirm('Index these workspace sources in '+p.plan.area+'?\n'+p.plan.paths.join('\n'));b.disabled=true;try{await api('/api/knowledge',{workspace:p.workspace,action:'decide',ticket:p.ticket,allow});b.textContent=allow?'Index updated':'Cancelled';}catch(e){fail(e);}};answer.el.append(b);}
      if(ev.type==='image_result' && answer){const a=document.createElement('a'),img=document.createElement('img');const q=new URLSearchParams({workspace:ev.data.workspace,id:ev.data.id});img.alt='Generated image';img.src='/api/image?'+q;a.href='/images?workspace='+encodeURIComponent(ev.data.workspace);a.append(img);answer.el.append(a);}
      if(ev.type==='file_preview' && answer){const img=document.createElement('img');img.alt='Rendered PDF page';img.src='data:image/png;base64,'+ev.data.png;answer.body.append(img);}
      if(ev.type==='tool_result' && answer){
        const p=ev.data,details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');
        details.className='tool';summary.textContent=p.name+' · '+p.decision+' · '+p.duration_ms+' ms';
        if(p.name==='calculate'){details.className='tool calc';summary.textContent='🧮 '+p.result;details.append(summary);answer.body.insertBefore(details,answer.body.querySelector('.stream-tail'));return;}
        pre.textContent=(mode==='terminal'?'':JSON.stringify(p.arguments,null,2)+'\n')+p.result;
        if(mode==='terminal'){details.open=true;summary.textContent='❯ '+(p.arguments?.code||p.arguments?.path||p.name)+' · '+p.decision+' · '+p.duration_ms+' ms';}
        details.append(summary,pre);answer.el.append(details);
      }
      if(ev.type==='start'){requestId=ev.data.request_id;controls();}
      if(ev.type==='status') $('status').textContent=ev.data;
      if(ev.type==='error') throw new Error(ev.data);
      if(ev.type==='text' && answer && !stopped){
        const follow=$('conversation').scrollHeight-$('conversation').scrollTop-$('conversation').clientHeight<80;
        renderer.append(ev.data);if(follow)$('conversation').scrollTop=$('conversation').scrollHeight;
        if(first===null && ev.data.trim()){first=(performance.now()-started)/1000;$('status').textContent='';}
        if(firstWord===null && /\S+\s/.test(answer.body.textContent)) firstWord=(performance.now()-started)/1000;
        $('timing').textContent=`First text after ${first?.toFixed(2) ?? '…'} s`;
      }
      if(ev.type==='thinking' && think && !stopped){think.parentElement.hidden=false;think.append(document.createTextNode(ev.data));}
      if(ev.type==='done') {
        done=true;
        $('status').textContent=ev.data.cancelled?'Stopped.':switching?'Model loaded.':'';
        window.lastMeasurement={...ev.data,browser_first_text_seconds:first,browser_first_word_seconds:firstWord ?? first};
        if(!switching && first!==null) $('timing').textContent=`Last answer: first text after ${first.toFixed(2)} s, first word after ${(firstWord ?? first).toFixed(2)} s`;
        if(!switching && ev.data.usage && (ev.data.usage.prompt_tokens||ev.data.usage.completion_tokens))lastUsage=ev.data.usage;
        lastModel=$('model').value;   // loaded even when the answer was stopped
      }
    }
    for(;;){const {value,done:ended}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!ended});let at;while((at=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,at);buffer=buffer.slice(at+2);for(const line of block.split('\n'))if(line.startsWith('data: '))event(JSON.parse(line.slice(6)));}if(ended)break;}
    if(!done)throw new Error('The response ended early. Please retry.');
  } catch(e){$('status').textContent=e.message;if(!switching&&first===null&&!$('message').value){$('message').value=typed;grow();attached=sentAttachments;renderAttachments();}}
  finally{clearInterval(waitTimer);if($('tool-permission').open)$('tool-permission').close('deny');applyModeTools();cancelAnimationFrame(frameId);const sorted=[...frames].sort((a,b)=>a-b);$('timing').dataset.frameMetrics=JSON.stringify({samples:frames.length,p95_ms:sorted[Math.floor(sorted.length*.95)]||0,max_ms:Math.max(0,...frames),over50ms:frames.filter(n=>n>50).length,visible:document.visibilityState});renderer?.flush(true);answer?.body.classList.remove('streaming');answer?.el.classList.remove('live');busy=false;requestId=null;controls();await loadState();updateContext();}
}
$('chat').addEventListener('submit',e=>{e.preventDefault();if(!slash())run();});
$('load').addEventListener('click',()=>run(true));
$('refresh').addEventListener('click',refresh);
$('stop').addEventListener('click',async()=>{if(!requestId)return;stopped=true;controls();try{if(mode==='code')await api('/api/terminal-ai',{action:'stop'});await api('/api/cancel',{request_id:requestId});$('status').textContent='Stopping…';}catch(e){$('status').textContent=e.message;}});
$('close').addEventListener('click',async()=>{try{await api('/api/close',{});clearInterval(heartbeat);online=false;controls();$('status').textContent='Assistant closed. You can close this window.';}catch(e){$('status').textContent=e.message;}});
const heartbeat=setInterval(()=>api('/api/ping',{}).catch(()=>{}),5000);
api('/api/ping',{}).catch(()=>{});

async function loadState(){
  state=await api('/api/state');document.body.dataset.theme=state.settings.theme;
  $('workspace').replaceChildren(...state.workspaces.map(w=>new Option(w.name,w.id)));$('workspace').value=currentWorkspace;
  const map=modeMap();
  $('chats').replaceChildren(...state.chats.filter(c=>c.workspace===currentWorkspace).map(c=>recentRow(c,map)));
  const open=state.chats.find(c=>c.id===currentChat);
  $('chat-title').textContent=open?chatTitle(open.title):({chat:'New chat',code:'New Code chat',print3d:'New 3D print',images:'New picture'}[mode]||'New chat');
  $('avatar').textContent=(callName()[0]||'✦').toUpperCase();greet();controls();
}
// Older chats may start with hint lines; show the user's words, else the attached file name.
function chatTitle(t){const s=splitHints(t||'');return s.text.split('\n')[0]||(s.files[0]?'📎 '+s.files[0]:'Untitled chat');}
// The persona's "call me" name, ignoring the placeholder default "you".
function callName(){const who=(state?.settings.user_call_name||'').trim();return /^you$/i.test(who)?'':who;}
// Empty-chat greeting: time of day in Chat, the area's own line in the other modes.
function greet(){const h=$('greeting');if(!h||!state)return;const cfg=MODES[mode];if(cfg.greeting){h.textContent=cfg.greeting;}else{const hr=new Date().getHours(),part=hr<5?'Good evening':hr<12?'Good morning':hr<18?'Good afternoon':'Good evening';const who=callName();h.textContent=who?`${part}, ${who}`:part;}const s=$('empty-sub');if(s)s.textContent=cfg.sub;}
function fail(e){$('status').textContent=e.message;}
async function openChat(id,focus=true){
  if(busy)return;const chat=await api('/api/chats/'+id);currentChat=id;currentWorkspace=chat.workspace;
  setMode(modeMap()[id]||'chat');lastUsage=null;
  $('conversation').replaceChildren();if(mode!=='images'&&models[chat.model]){chosen[mode]=chat.model;fillModels();}$('think').checked=!!chat.think;$('thorough').checked=!!chat.thorough;
  for(const m of chat.messages){const a=article(m.role==='user'?'YOU':state.settings.assistant_name.toUpperCase(),m.role==='user'?m.content:'',false,m.role==='user');if(m.role!=='user')renderSaved(a,m.content);if(m.thinking){const d=document.createElement('details'),h=document.createElement('summary'),p=document.createElement('pre');d.className='thinking';h.textContent='Thinking';p.textContent=m.thinking;d.append(h,p);a.el.append(d);}if(m.state!=='complete'){const p=document.createElement('p');p.className='hint';p.textContent='Answer '+m.state+' · send a new message to continue';a.el.append(p);}}
  $('conversation').scrollTop=$('conversation').scrollHeight;
  updateContext();await loadState();if(focus)$('message').focus({preventScroll:true});
  if(narrow.matches)$('app').classList.remove('nav-open');
}
function newChat(nextMode=mode){if(busy)return;currentChat=null;lastUsage=null;attached=[];renderAttachments();const empty=document.createElement('div'),bird=document.createElement('img'),heading=document.createElement('h2'),line=document.createElement('p');empty.id='empty';bird.className='empty-bird';bird.src='/bird.svg';bird.alt='';heading.id='greeting';line.id='empty-sub';empty.append(bird,heading,line);$('conversation').replaceChildren(empty);$('message').value='';grow();
  const p=prefs();chosen.chat='';chosen.code='';chosen.print3d='';$('think').checked=!!p.defaultThink&&!$('think').disabled;$('thorough').checked=!!p.defaultLong;
  setMode(nextMode);loadState().catch(fail);$('message').focus();if(narrow.matches)$('app').classList.remove('nav-open');}
// Composer grows with its text up to the CSS max-height, then scrolls.
function grow(){const m=$('message');if(!m.value){m.style.height='';m.style.overflowY='hidden';return;}m.style.height='auto';m.style.height=Math.min(m.scrollHeight,240)+'px';m.style.overflowY=m.scrollHeight>240?'auto':'hidden';}
async function saveOptions(){if(currentChat&&mode!=='images')await api('/api/store',{action:'options',id:currentChat,model:$('model').value,think:$('think').checked,thorough:$('thorough').checked});}

/* ------------------------------------------------------------------ context meter ------------------------------------------------------------------
   An estimate of what the next message sends, using the same limits as the server (Fast: 6 turns / 3,000 bytes;
   Long memory: 12 turns / 6,000 bytes), plus the persona, any tool schemas and the draft. */
const enc=new TextEncoder();
function updateContext(){
  const long=$('thorough').checked,maxTurns=long?12:6,maxBytes=long?6000:3000;
  $('context-note').textContent=long?'Long memory: up to 12 recent turns are sent.':'Fast: up to 6 recent turns are sent.';
  // Only the turns that can be sent count, so read just the last ones (typing stays fast in very long chats).
  const all=document.querySelectorAll('#conversation article .body');
  const bodies=[...all].slice(-(maxTurns*2+2)).map(b=>b.textContent);
  let bytes=0,turns=0;
  for(let i=bodies.length-1;i>=1&&turns<maxTurns;i-=2){const pair=enc.encode(bodies[i-1]+bodies[i]).length;if(bytes+pair>maxBytes)break;bytes+=pair;turns++;}
  const tools=TOOL_IDS.some(id=>$(id).checked)?650:0;
  const draft=enc.encode($('message').value+attachmentPrefix()).length;
  // Attached documents send up to 16,000 characters per message; a picture costs roughly 1,000 tokens.
  const docs=attached.filter(n=>!PICTURE.test(n)&&!AUDIO.test(n)).length,pics=attached.filter(n=>PICTURE.test(n)).length;
  const est=Math.round(250+tools+(bytes+draft+Math.min(16000,docs*8000))/3.6+pics*1000);
  const ctx=models[$('model').value]?.context_length||32768;
  const pct=Math.min(100,Math.round(est/ctx*1000)/10);
  $('ctx-ring').style.strokeDasharray=`${Math.max(pct,1.5)} 100`;
  $('ctx-label').textContent=(pct<1?pct.toFixed(1):Math.round(pct))+'%';
  $('ctx-bar').style.width=Math.max(pct,1)+'%';
  $('context-menu').dataset.level=pct>75?'high':pct>40?'mid':'low';
  const k=n=>n>=1000?(n/1000).toFixed(n>=10000?0:1)+'k':String(n);
  $('ctx-detail').textContent=`≈ ${k(est)} of ${k(ctx)} tokens next message · ${turns} earlier turn${turns===1?'':'s'}`+(lastUsage?.prompt_tokens?` · last request ${k(lastUsage.prompt_tokens+(lastUsage.completion_tokens||0))}`:'');
}

/* ------------------------------------------------------------------ settings ------------------------------------------------------------------ */
const SERVER_KEYS=['assistant_name','user_call_name','tone','language','theme','about_me','instructions'];
// One click adds a common instruction to "How Tsubasa should answer".
const INSTRUCTION_IDEAS=['Answer briefly; give details only when I ask.','Use metric units and 24-hour time.','Use bullet points for steps.','Explain like a patient teacher, with one example.','Show complete code, not fragments.','Say how sure you are when you are not certain.','Ask a question first when my request is unclear.','Answer in Slovak unless I write in English.'];
function counters(){for(const c of document.querySelectorAll('#persona-form .counter')){const t=$('persona-form').elements.namedItem(c.dataset.for);c.textContent=`${t.value.length.toLocaleString()} / ${t.maxLength.toLocaleString()}`;}}
function renderIdeas(){
  const box=$('instruction-chips'),t=$('persona-form').elements.namedItem('instructions');
  box.replaceChildren(...INSTRUCTION_IDEAS.filter(i=>!t.value.includes(i)).map(i=>{const b=document.createElement('button');b.type='button';b.className='chip-btn';b.textContent='＋ '+i;b.onclick=()=>{t.value=(t.value.trim()?t.value.trimEnd()+'\n':'')+i;counters();renderIdeas();};return b;}));
}
$('persona-form').addEventListener('input',e=>{if(e.target.tagName==='TEXTAREA'){counters();renderIdeas();}});
function showPane(name){document.querySelectorAll('.settings-nav button').forEach(b=>b.setAttribute('aria-current',String(b.dataset.pane===name)));document.querySelectorAll('.settings-panes section').forEach(s=>s.hidden=s.dataset.pane!==name);}
document.querySelectorAll('.settings-nav button').forEach(b=>b.onclick=()=>showPane(b.dataset.pane));
function persona(){if(busy)return;const f=$('persona-form');for(const k of SERVER_KEYS)f.elements.namedItem(k).value=state.settings[k]??'';const p=prefs();for(const el of f.querySelectorAll('[data-pref]')){if(el.type==='checkbox')el.checked=!!p[el.dataset.pref];else el.value=p[el.dataset.pref];}counters();renderIdeas();showPane('profile');$('persona').showModal();}
$('persona-form').onsubmit=async e=>{e.preventDefault();try{const f=e.target;const settings=Object.fromEntries(SERVER_KEYS.map(k=>[k,f.elements.namedItem(k).value]));await api('/api/store',{action:'settings',settings});
  const p=prefs();for(const el of f.querySelectorAll('[data-pref]'))p[el.dataset.pref]=el.type==='checkbox'?el.checked:el.value;try{localStorage.setItem('tsubasa.prefs',JSON.stringify(p));}catch{}
  applyPrefs();if(mode==='print3d'&&!prefs().print3d&&!busy)newChat('chat');await loadState();$('persona').close();$('status').textContent='Settings saved.';setTimeout(()=>{if($('status').textContent==='Settings saved.')$('status').textContent='';},2500);}catch(e){fail(e);}};
$('persona-cancel').onclick=()=>$('persona').close();
// Settings > Engine: start or stop the shared engine on purpose (Stop asks once more).
$('engine-start').onclick=async()=>{try{const r=await api('/api/engine',{action:'start',model:chatModel()});$('settings-engine').textContent=r.model?`Starting the engine with ${r.model}… (about 20 s)`:'Starting the engine…';engineWait=0;setTimeout(refresh,2500);}catch(e){fail(e);}};
$('engine-stop').onclick=async()=>{const b=$('engine-stop');if(!b.classList.contains('armed')){b.classList.add('armed');b.textContent='Press again to stop';setTimeout(()=>{b.classList.remove('armed');b.textContent='■ Stop engine';},3500);return;}
  b.classList.remove('armed');b.textContent='■ Stop engine';try{await api('/api/engine',{action:'stop'});lastModel=null;$('settings-engine').textContent='Engine stopped. Memory is free again.';engineWait=60;refresh();}catch(e){fail(e);}};

/* ------------------------------------------------------------------ commands ------------------------------------------------------------------ */
const commands=[['New chat','/new',()=>newChat()],['Change model','/model',()=>$('model').focus()],['Settings','/settings',persona],['Persona & appearance','/persona',persona],['Toggle Think first','/think',()=>{if($('think').disabled)throw Error('Think first is available with the qwen3.5 models.');$('think').checked=!$('think').checked;saveOptions().catch(fail);}],
  ['3D Print (experimental)','/print',()=>{if(!prefs().print3d)throw Error('3D Print is turned off: Settings → Experimental.');newChat('print3d');}],['Code mode','/code',()=>newChat('code')],['Code mode','/run',()=>newChat('code')],['Images','/img',()=>newChat('images')],['Chat','/chat',()=>newChat('chat')],['Library','/library',()=>openLibrary()],['Workspaces','/workspaces',()=>openWorkspaces()]];
function palette(){if(busy)return;$('command').value='';renderCommands();$('palette').showModal();$('command').focus();}
function renderCommands(){const q=$('command').value.toLowerCase();$('command-list').replaceChildren(...commands.filter(c=>(c[0]+c[1]).toLowerCase().includes(q)).map(c=>{const b=document.createElement('button');b.textContent=c[1]+'  '+c[0];b.disabled=!c[2];b.onclick=()=>{$('palette').close();try{c[2]();}catch(e){fail(e);}};return b;}));}
function slash(){const text=$('message').value.trim();if(!text.startsWith('/'))return false;const [name,...args]=text.split(/\s+/),c=commands.find(c=>c[1]===name);if(!c){fail(Error('Unknown command. Press Ctrl K to see commands.'));return true;}if(!c[2]){fail(Error(c[0]));return true;}try{if(name==='/model'&&args.length){const tag=args.join(' ');if(![...$('model').options].some(o=>o.value===tag))throw Error('Select an installed model.');$('model').value=tag;controls();saveOptions().catch(fail);}else c[2]();$('message').value='';grow();}catch(e){fail(e);}return true;}
$('new-chat').onclick=()=>newChat();$('persona-open').onclick=persona;$('palette-open').onclick=palette;$('command').oninput=renderCommands;
for(const id of TOOL_IDS) $(id).addEventListener('change',()=>{if($(id).checked){if(id==='terminal-tools'){for(const other of ['file-tools','practice-tools','knowledge-tools'])$(other).checked=false;}else $('terminal-tools').checked=false;}updateContext();});
// Sidebar areas switch the chat into that mode (a fresh chat when the current one already has messages).
function switchMode(m){if(busy)return;if(m===mode&&!currentChat)return;if(!currentChat&&$('empty'))setMode(m);else newChat(m);loadState().catch(fail);}
document.querySelectorAll('.tools-nav .nav-item[data-mode], #mode-switch button').forEach(b=>b.onclick=()=>switchMode(b.dataset.mode));
$('workspace').onchange=()=>{currentWorkspace=$('workspace').value||'default';newChat();};
$('add-workspace').onclick=()=>{$('workspace-name').value='';$('workspace-dialog').showModal();};$('workspace-cancel').onclick=()=>$('workspace-dialog').close();
$('workspace-form').onsubmit=async e=>{e.preventDefault();try{const w=await api('/api/store',{action:'workspace',name:$('workspace-name').value});currentWorkspace=w.id;$('workspace-dialog').close();newChat();}catch(e){fail(e);}};
for(const id of ['model','think','thorough'])$(id).addEventListener('change',()=>{
  // Picking RealVisXL in the model menu opens Images mode (a fresh chat if this one already has messages).
  if(id==='model'&&$('model').value===IMAGE_OPTION){fillModels();switchMode('images');return;}
  if(id==='model'&&mode!=='images'){chosen[mode]=$('model').value;preload($('model').value);}
  controls();updateContext();saveOptions().catch(fail);});
$('delete-chat').onclick=()=>{if(!currentChat)return;$('delete-dialog').returnValue='cancel';$('delete-dialog').showModal();};
$('delete-dialog').addEventListener('close',async()=>{if($('delete-dialog').returnValue!=='delete')return;try{await api('/api/store',{action:'delete',id:currentChat});newChat();}catch(e){fail(e);}});
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();palette();}});
// Enter sends (Shift+Enter adds a line), or Ctrl+Enter if chosen in Settings. Ignore Enter while an IME is composing.
$('message').addEventListener('keydown',e=>{if(e.key!=='Enter'||e.isComposing)return;const ctrlMode=prefs().sendKey==='ctrl';const send=ctrlMode?(e.ctrlKey||e.metaKey):(!e.shiftKey);if(send){e.preventDefault();if(!$('send').disabled)$('chat').requestSubmit();}});
$('splash').onclick=()=>$('splash').hidden=true;setTimeout(()=>$('splash').hidden=true,matchMedia('(prefers-reduced-motion: reduce)').matches?0:650);

// Sidebar: a drawer on narrow windows, a collapsible column (remembered) on wide ones.
const narrow=matchMedia('(max-width: 760px)');
try{if(localStorage.getItem('tsubasa.sidebar')==='collapsed')$('app').classList.add('collapsed');}catch{}
function sidebarOpen(){return narrow.matches?$('app').classList.contains('nav-open'):!$('app').classList.contains('collapsed');}
$('mobile-nav').addEventListener('click',()=>{
  if(narrow.matches)$('app').classList.toggle('nav-open');
  else{const c=$('app').classList.toggle('collapsed');try{localStorage.setItem('tsubasa.sidebar',c?'collapsed':'open');}catch{}}
  $('mobile-nav').setAttribute('aria-expanded',String(sidebarOpen()));
});
$('app').addEventListener('click',e=>{if(narrow.matches&&$('app').classList.contains('nav-open')&&!e.target.closest('#sidebar,#mobile-nav'))$('app').classList.remove('nav-open');});
$('mobile-nav').setAttribute('aria-expanded',String(sidebarOpen()));

// Popovers close on an outside click or Escape.
document.addEventListener('click',e=>{for(const d of document.querySelectorAll('details.popover[open]'))if(!d.contains(e.target))d.open=false;});
document.addEventListener('keydown',e=>{if(e.key==='Escape')for(const d of document.querySelectorAll('details.popover[open]'))d.open=false;});
$('message').addEventListener('input',()=>{grow();controls();updateContext();});

/* Platform wording: the page is written for Windows + FastFlowLM; on a Mac the engine is MLX and models are
   downloaded on request (never silently). */
let platformApplied='';
function applyPlatform(info){
  renderDownloads(info.suggested||[]);
  if(platformApplied===info.platform+info.engine)return;platformApplied=info.platform+info.engine;
  document.body.dataset.platform=info.platform;document.body.dataset.engine=info.engine;
  if($('about-version'))$('about-version').textContent='Version '+(info.version||'');
  if(info.engine!=='mlx')return;
  $('engine-intro').textContent='Tsubasa runs models with Apple’s MLX on this Mac, through mlx-lm’s local server (127.0.0.1 only). A model is loaded with the first message and stays in memory until you stop the engine.';
  $('engine-stop-note').textContent='Stop frees the model’s memory. Start is quick; the model loads again with the next message.';
  MODES.code.sub='Your chosen model plans and writes the code. Terminal steps are zsh commands written by the fast model and rated by Tsubasa’s checker. Every step waits for your approval.';
  MODES.code.suggestions=[['❯ Python script','In my Documents/tsubasa-code folder, write a Python script that lists the 10 largest files in a folder I give it, then run it on my Downloads folder'],['❯ My dev setup','Which versions of Python, Node and Git are installed?'],['❯ Explain a project','Look at my project folder and explain what the code does'],['❯ Free disk space','How much free space is on my disks']];
  MODES.images.sub='Images need a stable-diffusion.cpp server with RealVisXL (optional, see MAC.md). Pick the shape below; your message is the prompt.';
  for(const el of document.querySelectorAll('[data-win-only]'))el.hidden=true;
  for(const c of document.querySelectorAll('code'))if(c.textContent==='%LOCALAPPDATA%\\Tsubasa')c.textContent='~/Library/Application Support/Tsubasa';
  setMode(mode);
}
function renderDownloads(list){
  const box=$('engine-downloads');if(!box)return;box.hidden=!list.length;
  box.replaceChildren(...list.map(s=>{const row=document.createElement('p'),b=document.createElement('button');row.className='engine-line';b.type='button';b.className='ghost';b.disabled=!!s.downloading;b.textContent=s.downloading?'Downloading…':'⇩ Download';
    b.onclick=async()=>{try{await api('/api/engine',{action:'download',model:s.id});b.disabled=true;b.textContent='Downloading…';$('status').textContent='Downloading '+s.id+' from Hugging Face. It appears in the model menu when it is complete.';}catch(e){fail(e);}};
    row.append(document.createTextNode(s.id+' · '+s.note+' '),b);return row;}));
}
// Launch on a fresh greeting (like a new conversation); saved chats wait under Recents. ?mode= opens an area directly.
async function boot(){try{applyPrefs();const want=new URLSearchParams(location.search).get('mode');newChat(MODES[want]?want:'chat');await refresh();}catch(e){fail(e);}}
boot();
grow();

/* ------------------------------------------------------------------ recents, workspaces ------------------------------------------------------------------ */
// A saved chat in Recents; the ✕ asks once more ("Delete") before removing it.
function recentRow(c,map){
  const row=document.createElement('div'),b=document.createElement('button'),x=document.createElement('button'),t=chatTitle(c.title),m=ALIAS[map[c.id]]||map[c.id]||'chat';
  row.className='recent';row.dataset.tab=m==='code'?'terminal':m;
  b.className='recent-open';b.textContent=t;b.title=(MODES[m]?.label||'Chat')+' · '+t;b.setAttribute('aria-current',String(c.id===currentChat));b.onclick=()=>openChat(c.id).catch(fail);
  x.className='recent-del';x.type='button';x.title='Delete chat';x.setAttribute('aria-label','Delete chat: '+t);x.textContent='✕';
  x.onclick=async e=>{
    e.stopPropagation();if(busy)return;
    if(!row.classList.contains('confirm')){row.classList.add('confirm');x.textContent='Delete';setTimeout(()=>{row.classList.remove('confirm');x.textContent='✕';},3000);return;}
    row.classList.add('leaving');
    try{await api('/api/store',{action:'delete',id:c.id});if(c.id===currentChat)newChat();else await loadState();}catch(err){row.classList.remove('leaving');fail(err);}
  };
  row.append(b,x);return row;
}
function openWorkspaces(){if(busy)return;renderWorkspaces();$('workspaces-dialog').showModal();}
function renderWorkspaces(){
  $('workspace-list').replaceChildren(...state.workspaces.map(w=>{
    const row=document.createElement('form'),inp=document.createElement('input'),save=document.createElement('button'),del=document.createElement('button');
    const count=state.chats.filter(c=>c.workspace===w.id).length,label=w.id==='default'?'Always kept':`Delete · ${count} chat${count===1?'':'s'}`;
    row.className='workspace-row';inp.value=w.name;inp.maxLength=60;inp.required=true;inp.setAttribute('aria-label','Workspace name');
    save.textContent='Rename';save.className='ghost';del.type='button';del.className='ghost danger';del.textContent=label;del.disabled=w.id==='default';
    row.onsubmit=async e=>{e.preventDefault();try{await api('/api/store',{action:'rename_workspace',id:w.id,name:inp.value});await loadState();renderWorkspaces();}catch(err){fail(err);}};
    del.onclick=async()=>{
      if(!del.classList.contains('armed')){del.classList.add('armed');del.textContent='Press again to delete';setTimeout(()=>{del.classList.remove('armed');del.textContent=label;},3000);return;}
      try{await api('/api/store',{action:'delete_workspace',id:w.id});if(currentWorkspace===w.id){currentWorkspace='default';newChat();}await loadState();renderWorkspaces();}catch(err){fail(err);}
    };
    row.append(inp,save,del);
    // Workspace instructions: like a project brief, read with every chat in this workspace.
    const item=document.createElement('div'),more=document.createElement('details'),sum=document.createElement('summary'),area=document.createElement('textarea'),keep=document.createElement('button');
    item.className='workspace-item';more.className='ws-instructions';sum.textContent='Instructions'+(w.instructions?' · set':'');
    area.maxLength=2000;area.rows=4;area.value=w.instructions||'';area.placeholder='e.g. This workspace is my thesis on river ecology. Cite sources, use British spelling.';
    keep.type='button';keep.className='ghost';keep.textContent='Save instructions';
    keep.onclick=async()=>{try{await api('/api/store',{action:'workspace_instructions',id:w.id,instructions:area.value});keep.textContent='Saved';setTimeout(()=>keep.textContent='Save instructions',1500);await loadState();sum.textContent='Instructions'+(area.value.trim()?' · set':'');}catch(err){fail(err);}};
    more.append(sum,area,keep);item.append(row,more);return item;
  }));
}
$('manage-workspaces').onclick=openWorkspaces;$('workspaces-close').onclick=()=>$('workspaces-dialog').close();

/* ------------------------------------------------------------------ library ------------------------------------------------------------------
   Skills and knowledge packs. Switched-on packs add their instructions and the closest passages to every chat. */
let libraryTimer=null;
async function openLibrary(){if(busy)return;$('pack-form').hidden=true;$('packs').hidden=false;await renderPacks().catch(fail);$('library').showModal();}
function updateLibraryCount(packs){const on=packs.filter(p=>p.enabled);$('library-count').textContent=on.length?String(on.length):'';$('library-hint').textContent=on.length?'On: '+on.map(p=>p.name).join(', '):'No skills switched on yet: open Library in the sidebar';}
async function renderPacks(){
  const {packs}=await api('/api/library',{action:'list'});
  updateLibraryCount(packs);
  $('packs').replaceChildren(...packs.map(packCard));
  clearTimeout(libraryTimer);if(packs.some(p=>p.job)&&$('library').open)libraryTimer=setTimeout(()=>renderPacks().catch(fail),1000);
}
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function packCard(p,i){
  const card=el('article','pack'+(p.enabled?' on':''));card.style.setProperty('--i',i);
  const head=el('div','pack-head'),icon=el('span','pack-icon',p.icon||'✦'),title=el('div','pack-title');
  title.append(el('b','',p.name),el('small','',p.description||''));
  const sw=el('label','switch'),box=el('input');box.type='checkbox';box.checked=!!p.enabled;box.setAttribute('aria-label',(p.enabled?'Switch off ':'Switch on ')+p.name);sw.append(box,el('span'));
  box.onchange=async()=>{card.classList.toggle('on',box.checked);try{await api('/api/library',{action:'toggle',id:p.id,on:box.checked});renderPacks().catch(fail);}catch(e){fail(e);}};
  head.append(icon,title,sw);
  const own=p.sources.filter(s=>s.kind!=='builtin'),builtinChunks=p.sources.filter(s=>s.kind==='builtin').reduce((a,s)=>a+s.chunks,0);
  const meta=el('p','pack-meta',p.job?`Indexing ${p.job.done} of ${p.job.total||'…'} files…`:`${own.length} source${own.length===1?'':'s'} · ${p.chunks.toLocaleString()} passages`+(p.builtin?` · built-in notes (${builtinChunks})`:''));
  if(p.job)meta.classList.add('working');
  const instr=el('p','pack-instr',p.instructions||'No instructions: this pack only adds knowledge.');
  const list=el('ul','pack-sources');
  for(const s of own){const li=el('li'),x=el('button','icon-btn ghost','✕');li.append(el('span','src-path',s.path),el('small','',s.error?s.error:`${s.files} files · ${s.chunks} passages${s.skipped?` · ${s.skipped} skipped`:''}`));x.type='button';x.title='Remove this source';x.onclick=async()=>{try{await api('/api/library',{action:'remove_source',source:s.id});renderPacks().catch(fail);}catch(e){fail(e);}};li.append(x);list.append(li);}
  const acts=el('div','pack-actions');
  const add=kind=>async()=>{try{const r=await api('/api/pick',{kind,title:`Add to ${p.name}`});if(r.path){await api('/api/library',{action:'add_source',id:p.id,path:r.path});await renderPacks();}}catch(e){fail(e);}};
  const f=el('button','ghost','＋ File…'),d=el('button','ghost','＋ Folder…'),edit=el('button','ghost','Edit');
  for(const b of [f,d,edit])b.type='button';
  f.onclick=add('file');d.onclick=add('folder');edit.onclick=()=>packForm(p);
  acts.append(f,d);
  if(own.length){const r=el('button','ghost','↻ Re-index');r.type='button';r.onclick=async()=>{try{await api('/api/library',{action:'refresh',id:p.id});renderPacks();}catch(e){fail(e);}};acts.append(r);}
  acts.append(edit);
  if(!p.builtin){const del=el('button','ghost danger','Delete');del.type='button';del.onclick=async()=>{if(!del.classList.contains('armed')){del.classList.add('armed');del.textContent='Press again';setTimeout(()=>{del.classList.remove('armed');del.textContent='Delete';},3000);return;}try{await api('/api/library',{action:'delete',id:p.id});renderPacks();}catch(e){fail(e);}};acts.append(del);}
  const typed=el('form','pack-path'),inp=el('input');inp.placeholder='…or paste a file or folder path';inp.setAttribute('aria-label','File or folder path');
  const go=el('button','ghost','Add');typed.append(inp,go);typed.onsubmit=async e=>{e.preventDefault();try{await api('/api/library',{action:'add_source',id:p.id,path:inp.value});inp.value='';await renderPacks();}catch(err){fail(err);libraryError(err.message);}};
  card.append(head,meta,instr,list,acts,typed);
  return card;
}
function libraryError(t){const h=$('library').querySelector('.settings-head .hint');h.textContent=t;h.classList.add('error');setTimeout(()=>{h.classList.remove('error');h.textContent='Skills and knowledge Tsubasa uses in every chat while they are switched on. Add your own files or folders to any pack; everything is indexed on this PC.';},4000);}
function packForm(p=null){
  const f=$('pack-form');f.reset();$('pack-form-title').textContent=p?'Edit '+p.name:'New skill';
  for(const k of ['id','name','description','instructions'])f.elements.namedItem(k).value=p?.[k]||'';
  $('packs').hidden=true;f.hidden=false;f.elements.namedItem('name').focus();
}
$('pack-form').onsubmit=async e=>{e.preventDefault();const f=e.target,v=k=>f.elements.namedItem(k).value;
  try{await api('/api/library',v('id')?{action:'update',id:v('id'),name:v('name'),description:v('description'),instructions:v('instructions')}:{action:'create',name:v('name'),description:v('description'),instructions:v('instructions')});f.hidden=true;$('packs').hidden=false;await renderPacks();}catch(err){libraryError(err.message);}};
$('pack-cancel').onclick=()=>{$('pack-form').hidden=true;$('packs').hidden=false;};
$('pack-new').onclick=()=>packForm();
$('library-open').onclick=openLibrary;$('library-close').onclick=()=>$('library').close();
$('library').addEventListener('close',()=>clearTimeout(libraryTimer));

/* ------------------------------------------------------------------ code folder ------------------------------------------------------------------ */
$('code-folder').onclick=async()=>{
  if(busy)return;
  try{const r=await api('/api/pick',{kind:'folder',title:'Project folder for Code mode'});if(!r.path)return;await api('/api/terminal-ai',{action:'cd',path:r.path});await showFolder();$('status').textContent='Code mode now works in '+r.path;}catch(e){fail(e);}
};
renderShapes();
api('/api/library',{action:'list'}).then(d=>updateLibraryCount(d.packs)).catch(()=>{});

/* ------------------------------------------------------------------ 3D Print ------------------------------------------------------------------
   The model thinks the part through and writes OpenSCAD; the server builds it, checks it and saves STL + SCAD.
   The answer shows the explanation, then the interactive model with its editable dimensions. */
var CAD_CODE=/```(?:openscad|scad)?[ \t]*\r?\n([\s\S]*?)```/i, CAD_OPEN=/```(?:openscad|scad)[ \t]*\r?\n([\s\S]*)$/i, materialsList=null;
// The code and the text around it; a code block the model never closed counts too (same rule as the server).
function cadCode(c){const m=CAD_CODE.exec(c);if(m&&m[1].trim())return {code:m[1].trim(),rest:c.replace(m[0],'')};const o=CAD_OPEN.exec(c);return o&&o[1].trim()?{code:o[1].trim(),rest:c.slice(0,o.index)}:null;}
function printOptions(){const p=prefs();return {material:p.printMaterial,infill:Math.min(Math.max(Number(p.printInfill)||20,5),100)/100,bed:(p.printBed||[220,220,250]).map(Number)};}
function printLabel(){const o=printOptions();$('print-label').textContent=`${o.material} · ${o.bed.join('×')}`;}
async function enterPrint(){
  // Designing a printable part is the hard case: Think first is on unless the user turns it off for this chat.
  if(!currentChat)$('think').checked=true;
  printLabel();
  if(!materialsList){try{materialsList=(await api('/api/cad',{action:'materials'})).materials;}catch{return;}}
  const sel=$('print-material'),p=prefs();
  sel.replaceChildren(...Object.keys(materialsList).map(k=>new Option(k,k)));sel.value=p.printMaterial in materialsList?p.printMaterial:'PLA';
  $('print-infill').value=p.printInfill;[$('bed-x').value,$('bed-y').value,$('bed-z').value]=p.printBed;noteMaterial();
}
function noteMaterial(){const m=materialsList?.[$('print-material').value];const note=$('material-note');note.textContent=m?`${m.nozzle==='SLA/MSLA'?'Resin printer':`Nozzle ${m.nozzle} °C · bed ${m.bed} °C`} · softens ≈${m.heat} °C. Good for: ${m.good}.`:'';note.title=m?`Watch out: ${m.weak}`:'';}
$('print-material').onchange=()=>{setPref('printMaterial',$('print-material').value);noteMaterial();printLabel();};
$('print-infill').onchange=()=>{setPref('printInfill',Number($('print-infill').value)||20);printLabel();};
for(const id of ['bed-x','bed-y','bed-z'])$(id).onchange=()=>{setPref('printBed',[$('bed-x'),$('bed-y'),$('bed-z')].map(i=>Math.min(Math.max(Number(i.value)||220,20),2000)));printLabel();};
function cadCtx(){return {workspace:currentWorkspace,notify:t=>{$('status').textContent=t;},
  render:async(script,values,name)=>{const r=await post('/api/cad',{action:'render',script,values,name,workspace:currentWorkspace,...printOptions()});const d=await r.json();if(!r.ok)throw new Error(d.error||'The model did not build.');return d;}};}
// The explanation without the code block (the code lives in the card).
function cadText(a,content){const box=document.createElement('div');box.className='seg-text';const md=new MarkdownStream(box);md.append((cadCode(content)?.rest??content).trim());md.flush(true);a.body.append(box);}
async function renderCad(a,content){
  const script=cadCode(content).code;cadText(a,content);
  const holder=document.createElement('div');holder.className='cad-loading';holder.textContent='Building the 3D model…';a.body.append(holder);
  const title=state?.chats?.find(c=>c.id===currentChat)?.title||'design';
  try{const d=await cadCtx().render(script,{},title.slice(0,40));holder.replaceWith(cadCard(d,script,cadCtx()).el);}
  catch(e){holder.textContent='This model could not be rebuilt: '+e.message;}
}
async function runCad(){
  const typed=$('message').value.trim();
  if(busy||!typed)return;
  busy=true;controls();
  if(!(await confirmUse(false))){busy=false;controls();return;}
  const prefix=attachmentPrefix(),message=prefix?typed+'\n\n'+prefix:typed,sent=[...attached];
  $('message').value='';grow();attached=[];renderAttachments();
  const model=$('model').value,answer=startTurn(message),started=performance.now();
  const thinkBox=document.createElement('details'),thinkSum=document.createElement('summary'),thinkPre=document.createElement('pre');
  thinkBox.className='thinking cad-thinking';thinkSum.textContent='Thinking…';thinkBox.append(thinkSum,thinkPre);thinkBox.hidden=true;answer.body.append(thinkBox);
  let text='',words=0,phase='thinking',first=null,pending=false;
  // While it streams: the explanation as Markdown, the code in a live box with a line count (not raw ``` text).
  const before=document.createElement('div'),live=document.createElement('div'),liveHead=document.createElement('p'),livePre=document.createElement('pre'),after=document.createElement('div');
  before.className=after.className='seg-text';live.className='cad-live';live.hidden=true;live.append(liveHead,livePre);answer.body.append(before,live,after);
  const md=(el,s)=>{el.replaceChildren();if(s.trim()){const m=new MarkdownStream(el);m.append(s);m.flush(true);}};
  const draw=()=>{pending=false;const open=/```(?:openscad|scad)?[ \t]*\r?\n/i.exec(text);
    if(!open){md(before,text);md(after,'');live.hidden=true;return;}
    const body=text.slice(open.index+open[0].length),close=body.indexOf('```'),code=close<0?body:body.slice(0,close),lines=code.split('\n').filter(l=>l.trim()).length;
    md(before,text.slice(0,open.index));md(after,close<0?'':body.slice(close+3));
    live.hidden=false;live.classList.toggle('writing',close<0);liveHead.textContent=(close<0?'Writing the OpenSCAD model':'OpenSCAD model')+` · ${lines} line${lines===1?'':'s'}`;
    livePre.textContent=code;livePre.scrollTop=livePre.scrollHeight;};
  const redraw=()=>{if(!pending){pending=true;setTimeout(()=>{if(phase!=='done')draw();},120);}};
  const seg={flush(){draw();}};
  const timer=setInterval(()=>{const s=Math.round((performance.now()-started)/1000);if(phase==='thinking')$('status').textContent=words?`Thinking the design through… ${s} s · ${words} words`:`Reading your request${sent.some(n=>PICTURE.test(n))?' and pictures':''}… ${s} s`;else if(phase==='writing')$('status').textContent=`Writing the model… ${s} s`;},1000);
  try{
    await ensureChat(model);await saveOptions();flap();
    const r=await post('/api/cad',{action:'design',chat_id:currentChat,message,model,think:$('think').checked,...printOptions()});
    await readEvents(r,ev=>{
      if(ev.type==='start'){requestId=ev.data.request_id;controls();}
      if(ev.type==='thinking'){if(thinkBox.hidden){thinkBox.hidden=false;thinkBox.open=true;}thinkPre.append(document.createTextNode(ev.data));thinkPre.scrollTop=thinkPre.scrollHeight;words+=(ev.data.match(/\S+/g)||[]).length;thinkSum.textContent=`Thinking · ${words} words`;}
      if(ev.type==='text'){if(phase==='thinking'){phase='writing';thinkBox.open=false;}text+=ev.data;first=1;redraw();scrollDown();}
      if(ev.type==='text_reset'){text='';phase='writing';draw();}
      if(ev.type==='status'){phase=ev.data.startsWith('Thinking')?phase:'other';$('status').textContent=ev.data;}
      if(ev.type==='repair'){const p=document.createElement('p');p.className='cad-repair';p.textContent=ev.data.kind==='describe'?`The description mentioned features the model does not have (${ev.data.error}) · rewritten from the real model.`:ev.data.kind==='trim'?`Removed what you did not ask for (${ev.data.error}) · kept the ready-made part with your sizes.`:ev.data.kind==='check'?`Checked the shape against your request: ${ev.data.error} · the designer corrected it.`:ev.data.kind==='review'?`Checked the model: ${ev.data.error} · the designer is joining them.`:`Attempt ${ev.data.attempt} did not build (${ev.data.error}) · the designer is fixing it.`;answer.body.insertBefore(p,before);}
      if(ev.type==='attach_notes')$('status').textContent=ev.data.join(' · ');
      if(ev.type==='part'){const p=document.createElement('p');p.className='library-note';p.textContent='Starts from the ready-made part · '+ev.data.replace(/_/g,' ');answer.el.querySelector('h3').after(p);}
      if(ev.type==='cad'){
        phase='done';before.remove();live.remove();after.remove();cadText(answer,ev.data.answer||text);
        answer.body.append(cadCard(ev.data,ev.data.script,cadCtx()).el);
        thinkSum.textContent=`Thought for ${Math.round((performance.now()-started)/1000)} s · ${words} words`;scrollDown();
      }
      if(ev.type==='done'){lastModel=model;$('status').textContent='';}
      if(ev.type==='error')throw new Error(ev.data);
    });
  }catch(e){$('status').textContent=e.message;if(first===null&&!$('message').value){$('message').value=typed;grow();attached=sent;renderAttachments();}}
  finally{clearInterval(timer);if(phase!=='done')seg.flush();await endTurn(answer);}
}
