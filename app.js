const $=s=>document.querySelector(s), view=$('#view');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl=u=>/^https?:\/\//i.test(u)?u:'#';
const fmt=(d,o={day:'numeric',month:'short'})=>new Date(d+(d.length===10?'T12:00:00':'')).toLocaleDateString('en-GB',o);
const D={}; let comp='pl', filter='all';
const load=async()=>{
  for(const k of ['meta','competitions','squad','injuries','history','news']){
    try{D[k]=await (await fetch(`data/${k}.json`,{cache:'no-cache'})).json()}catch(e){D[k]=null}
  }
};
const res=m=>m.hs===m.as?'D':((m.h==='Liverpool')===(m.hs>m.as)?'W':'L');
const matchRow=m=>{const r=res(m);return `<div class="row"><div class="l"><b>${esc(m.h)} ${m.hs}–${m.as} ${esc(m.a)}</b><span class="muted">${fmt(m.date)}</span></div><span class="pill ${r}">${r}</span></div>`};
const allMatches=()=>(D.competitions?.competitions||[]).flatMap(c=>c.matches.map(m=>({...m,c:c.name}))).sort((a,b)=>b.date.localeCompare(a.date));
const days=d=>Math.ceil((new Date(d+'T12:00:00')-new Date())/864e5);

const R={
home(){
  const n=D.meta?.next, ms=allMatches().slice(0,5), inj=D.injuries?.items||[], news=(D.news?.items||[]).slice(0,3);
  const form=ms.map(m=>`<span class="pill ${res(m)}">${res(m)}</span>`).join(' ');
  return `${n?`<div class="card hero"><div class="k">Next match · ${esc(n.competition)}</div><div class="big">vs ${esc(n.opponent)}</div><div>${fmt(n.date,{weekday:'long',day:'numeric',month:'long'})} · ${days(n.date)>=0?`in ${days(n.date)} days`:'played'}</div><div class="muted">${esc(n.venue)} · ${esc(n.note||'')}</div></div>`:''}
  <div class="card"><h3>Recent form</h3>${form||'<span class="muted">No results entered</span>'}</div>
  <h2>Premier League</h2>${summary(D.competitions?.competitions?.[0])}
  <h2>Latest news</h2>${news.map(newsCard).join('')||'<p class="empty">No news yet</p>'}<p><a href="#/news">All news →</a></p>
  <h2>Injury room (${inj.length})</h2><div class="card">${inj.map(i=>`<div class="row"><div class="l"><b>${esc(i.n)}</b><span class="muted">${esc(i.window)}</span></div></div>`).join('')}</div><p><a href="#/injuries">Full list →</a></p>`;
},
stats(){
  const cs=D.competitions?.competitions||[], c=cs.find(x=>x.id===comp)||cs[0];
  return `<div class="chips">${cs.map(x=>`<button class="chip ${x.id===c.id?'on':''}" data-comp="${x.id}">${esc(x.name)}</button>`).join('')}</div>
  ${c.status?`<div class="note">${esc(c.status)}</div>`:''}
  ${summary(c)}
  ${c.table?.length?`<h2>Table</h2><div class="card wrap"><table><tr><th>#</th><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GD</th><th>Pts</th></tr>${c.table.map(t=>`<tr class="${t.me||t.team==='Liverpool'?'me':''}"><td>${t.pos}</td><td>${esc(t.team)}</td><td>${t.P}</td><td>${t.W}</td><td>${t.D}</td><td>${t.L}</td><td>${t.GD}</td><td>${t.Pts}</td></tr>`).join('')}</table></div>`:''}
  <h2>Results</h2><div class="card">${c.matches.length?c.matches.slice().sort((a,b)=>b.date.localeCompare(a.date)).map(matchRow).join(''):'<p class="empty">No matches entered</p>'}</div>
  ${c.scorers?.length?`<h2>Top scorers</h2><div class="card">${c.scorers.map(s=>`<div class="row"><b>${esc(s.name)}</b><span>${s.g} G · ${s.a} A</span></div>`).join('')}</div>`:''}`;
},
squad(){
  const P=D.squad?.players||[], groups=[['all','All'],['GK','GK'],['DEF','DEF'],['MID','MID'],['FWD','FWD']];
  const inj=new Set((D.injuries?.items||[]).map(i=>i.n));
  const list=P.filter(p=>filter==='all'||p.pos===filter);
  return `<div class="chips">${groups.map(([k,l])=>`<button class="chip ${filter===k?'on':''}" data-f="${k}">${l}</button>`).join('')}</div>
  ${D.squad?.note?`<div class="note">${esc(D.squad.note)}</div>`:''}
  <div class="card">${list.map(p=>`<div class="row"><div class="l"><b>${esc(p.n)} ${p.c?`<span class="pill nt">${esc(p.c)}</span>`:''}</b><span class="muted">${esc(p.pos)} · ${esc(p.nat)}${p.new?' · '+esc(p.new):''}</span></div>${inj.has(p.n)||p.inj?'<span class="pill lo">Injured</span>':p.new?'<span class="pill hi">New</span>':''}</div>`).join('')}</div>
  <h2>Left this summer</h2><div class="card">${(D.squad?.departed||[]).map(d=>`<div class="row"><b>${esc(d.n)}</b><span class="muted">${esc(d.to)}</span></div>`).join('')}</div>`;
},
news(){
  const tabs=[['all','All'],['transfers','Transfers & market'],['team','Team news']];
  const items=(D.news?.items||[]).filter(i=>filter==='all'||i.cat===filter);
  return `<div class="chips">${tabs.map(([k,l])=>`<button class="chip ${filter===k?'on':''}" data-f="${k}">${l}</button>`).join('')}</div>${items.map(newsCard).join('')||'<p class="empty">Nothing here yet</p>'}`;
},
injuries(){
  const c={High:'hi',Medium:'me',Low:'lo'};
  return `<div class="note">${esc(D.injuries?.note||'')}</div>${(D.injuries?.items||[]).map(i=>`<div class="card"><div class="row" style="border:0;padding:0"><b>${esc(i.n)}</b><span class="pill ${c[i.conf]||'nt'}">${esc(i.conf)} confidence</span></div><div class="muted">${esc(i.issue)}</div><p style="margin-top:6px"><b>Return:</b> ${esc(i.window)}</p><a class="muted" href="${safeUrl(i.url)}" target="_blank" rel="noopener">${esc(i.src)} ↗</a></div>`).join('')||'<p class="empty">No injuries listed</p>'}`;
},
more(){
  const h=D.history||{};
  return `<h2>Club history</h2><div class="grid">${(h.honours||[]).map(x=>`<div class="tile"><b>${x.c}</b><span>${esc(x.t)}</span></div>`).join('')}</div><p class="muted" style="margin-top:6px">${esc(h.honours_as_of||'')}</p>
  <h2>Timeline</h2><div class="timeline">${(h.timeline||[]).map(e=>`<div class="ev"><div class="y">${esc(e.y)}</div>${esc(e.e)}</div>`).join('')}</div>
  <h2>Did you know</h2><div class="card">${(h.facts||[]).map(f=>`<p style="margin-bottom:6px">• ${esc(f)}</p>`).join('')}</div>
  <h2>About this app</h2><div class="card muted">${esc(D.meta?.note||'')}<br><br>Manager: ${esc(D.meta?.manager||'')}<br>Stadium: ${esc(D.meta?.stadium||'')}</div>`;
}};
function summary(c){
  if(!c?.summary)return '';
  const s=c.summary;
  return `<div class="grid">${[['pos','Position'],['P','Played'],['Pts','Points'],['W','Won'],['D','Drawn'],['L','Lost'],['GF','Goals for'],['GA','Against']].map(([k,l])=>`<div class="tile"><b>${esc(s[k])}</b><span>${l}</span></div>`).join('')}</div>`;
}
function newsCard(i){
  const l={transfers:'Transfers',team:'Team news'}[i.cat]||'News';
  return `<div class="card news"><a href="${safeUrl(i.url)}" target="_blank" rel="noopener"><span class="tag">${l}</span><b>${esc(i.title)}</b><span class="muted">${esc(i.src)}${i.date?' · '+fmt(i.date.slice(0,10)):''}</span></a></div>`;
}
function render(){
  const r=(location.hash.replace('#/','')||'home'); const name=R[r]?r:'home';
  document.querySelectorAll('.tabs a').forEach(a=>a.classList.toggle('on',a.dataset.r===name));
  view.innerHTML=R[name]();
  if(D.meta?.updated)$('#asof').textContent='Liverpool FC · data as of '+fmt(D.meta.updated,{day:'numeric',month:'short',year:'numeric'});
}
addEventListener('hashchange',()=>{filter='all';render();scrollTo(0,0)});
view.addEventListener('click',e=>{const b=e.target.closest('.chip');if(!b)return;if(b.dataset.comp)comp=b.dataset.comp;else filter=b.dataset.f;render()});
load().then(render);
if('serviceWorker' in navigator)navigator.serviceWorker.register('sw.js').catch(()=>{});
