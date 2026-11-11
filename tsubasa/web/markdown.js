// Deliberately small Markdown subset. All untrusted content enters text nodes.
const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};

// Models sometimes write LaTeX even when asked not to; show it as readable text (√, ², ×) instead of raw backslashes.
const SUP={'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹','+':'⁺','-':'⁻','=':'⁼','(':'⁽',')':'⁾','n':'ⁿ','i':'ⁱ'};
const SUB={'0':'₀','1':'₁','2':'₂','3':'₃','4':'₄','5':'₅','6':'₆','7':'₇','8':'₈','9':'₉','+':'₊','-':'₋','=':'₌','(':'₍',')':'₎',
  a:'ₐ',e:'ₑ',o:'ₒ',x:'ₓ',h:'ₕ',k:'ₖ',l:'ₗ',m:'ₘ',n:'ₙ',p:'ₚ',s:'ₛ',t:'ₜ',i:'ᵢ',r:'ᵣ',u:'ᵤ',v:'ᵥ'};
const SYM={times:'×',cdot:'·',approx:'≈',pi:'π',alpha:'α',beta:'β',gamma:'γ',delta:'δ',Delta:'Δ',theta:'θ',lambda:'λ',mu:'µ',sigma:'σ',
  omega:'ω',Omega:'Ω',rho:'ρ',epsilon:'ε',varepsilon:'ε',phi:'φ',infty:'∞',pm:'±',leq:'≤',le:'≤',geq:'≥',ge:'≥',neq:'≠',
  rightarrow:'→',to:'→',leftarrow:'←',Rightarrow:'⇒',circ:'°',degree:'°',sum:'Σ',int:'∫',partial:'∂',nabla:'∇',cdots:'⋯',ldots:'…'};
const script=(map,s)=>[...s].every(c=>map[c])?[...s].map(c=>map[c]).join(''):(map===SUP?'^':'_')+(s.length>1?'('+s+')':s);
function math(s){
  for(let i=0;i<3;i++)s=s.replace(/\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}/g,(m,a,b)=>`${a.length>1?'('+a+')':a}/${b.length>1?'('+b+')':b}`)
    .replace(/\\sqrt\{([^{}]*)\}/g,(m,a)=>'√'+(a.length>1?'('+a+')':a));
  return s.replace(/\\(?:text|mathrm|mathbf|operatorname)\{([^{}]*)\}/g,'$1')
    .replace(/\^\{([^{}]*)\}|\^([\w+-])/g,(m,a,b)=>script(SUP,a??b)).replace(/_\{([^{}]*)\}|_([\w])/g,(m,a,b)=>script(SUB,a??b))
    .replace(/\\([A-Za-z]+)/g,(m,n)=>SYM[n]??n).replace(/\\[,;:! ]/g,' ').replace(/[{}]/g,'').replace(/\s{2,}/g,' ').trim();
}
const MATH=/\$\$([^$]+)\$\$|\$([^$\n]+?)\$|\\\(([\s\S]+?)\\\)|\\\[([\s\S]+?)\\\]/g;
const delatex=t=>t.replace(MATH,(m,a,b,c,d)=>{const inner=a??b??c??d;return /[\\^_=]/.test(inner)?math(inner):m;});

function inline(parent,text){
  text=delatex(text);
  const re=/(\*\*([^*]+)\*\*|`([^`]+)`|\*([^*\s][^*]*?)\*|\[([^\]]+)\]\((https?:[^)\s]+)\))/g;let at=0,m;
  while((m=re.exec(text))){
    parent.append(document.createTextNode(text.slice(at,m.index)));
    if(m[2])parent.append(el('strong',m[2]));else if(m[3])parent.append(el('code',m[3]));else if(m[4])parent.append(el('em',m[4]));
    else parent.append(document.createTextNode(`${m[5]} (${m[6]})`));   // links stay plain text: this window opens nothing
    at=re.lastIndex;
  }
  parent.append(document.createTextNode(text.slice(at)));
}
// | a | b | tables, with the |---| separator line under the header.
function table(lines){
  const cells=l=>l.trim().replace(/^\||\|$/g,'').split('|').map(c=>c.trim());
  const t=el('table'),head=el('thead'),body=el('tbody'),hr=el('tr');
  for(const c of cells(lines[0])){const th=el('th');inline(th,c);hr.append(th);}
  head.append(hr);
  for(const line of lines.slice(2)){const tr=el('tr');for(const c of cells(line)){const td=el('td');inline(td,c);tr.append(td);}body.append(tr);}
  t.append(head,body);const wrap=el('div');wrap.className='md-table';wrap.append(t);return wrap;
}
function block(text){
  const box=el('div');box.className='md-block';
  if(text.startsWith('```')){
    const lines=text.split('\n'),lang=lines.shift().slice(3).trim();if(lines.at(-1)?.startsWith('```'))lines.pop();
    const code=lines.join('\n'),bar=el('div');bar.className='code-bar';bar.append(el('span',lang||'code'));
    const copy=el('button','Copy');copy.type='button';copy.onclick=async()=>{try{await navigator.clipboard.writeText(code);copy.textContent='Copied';}catch{copy.textContent='Select text to copy';}};
    bar.append(copy);box.append(bar,el('pre',code));
    return box;
  }
  const lines=text.split('\n');
  if(lines.length>=2&&lines.every(l=>l.trim().startsWith('|'))&&/^\s*\|?\s*:?-{2,}/.test(lines[1])){box.append(table(lines));return box;}
  for(const line of lines){const h=/^(#{1,4}) (.*)/.exec(line),li=/^\s*[-*] (.*)/.exec(line),hr=/^\s*(-{3,}|\*{3,})\s*$/.test(line);
    if(hr){box.append(el('hr'));continue;}
    const n=el(h?'h'+(h[1].length+1):'p');inline(n,h?h[2]:li?'• '+li[1]:line);box.append(n);}
  return box;
}
export class MarkdownStream{
  constructor(root){this.root=root;this.pending='';this.tail=el('span');this.tail.className='stream-tail';root.append(this.tail);}
  append(text){this.pending+=text;this.flush(false);}
  flush(final){
    for(;;){let end=-1;
      if(this.pending.startsWith('```')){const close=this.pending.indexOf('\n```',3);if(close>=0){const nl=this.pending.indexOf('\n',close+4);if(nl>=0)end=nl+1;else if(final)end=this.pending.length;}}
      else {const blank=this.pending.indexOf('\n\n');if(blank>=0)end=blank+2;}
      if(end<0){if(final&&this.pending)end=this.pending.length;else break;}
      const text=this.pending.slice(0,end).trimEnd();this.pending=this.pending.slice(end);this.root.insertBefore(block(text),this.tail);
    }
    this.tail.textContent=this.pending;if(final)this.tail.remove();
  }
}
