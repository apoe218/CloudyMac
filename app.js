const $=s=>document.querySelector(s), view=$('#view');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl=u=>/^https?:\/\//i.test(u||'')?u:'#';
const dt=d=>new Date(d.length===10?d+'T12:00:00':d);
const fmt=(d,o={day:'numeric',month:'short'})=>dt(d).toLocaleDateString('en-GB',o);
const ago=t=>{const m=Math.round((Date.now()-t)/6e4);return m<1?'just now':m<60?m+'m ago':m<1440?Math.round(m/60)+'h ago':Math.round(m/1440)+'d ago'};
const D={}; let comp='pl', filter='all';

/* ---------- LIVE FEEDS ---------- */
const gn=q=>'https://news.google.com/rss/search?q='+encodeURIComponent(q)+'&hl=en-GB&gl=GB&ceid=GB:en';
const FEEDS=[
 {id:'bbc',url:'https://feeds.bbci.co.uk/sport/football/teams/liverpool/rss.xml',cat:'team',src:'BBC Sport'},
 {id:'gt',url:gn('Liverpool FC transfer news when:7d'),cat:'transfers'},
 {id:'gi',url:gn('Liverpool FC injury news when:7d'),cat:'injury'},
 {id:'gx',url:gn('Liverpool FC Iraola when:3d'),cat:'team'}
];
const TTL=2*60*1000; // don't re-hit feeds on rapid reloads
const store={get(k){try{return JSON.parse(localStorage.getItem(k))}catch{return null}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch{}}};
const INJ=/injur|doubt|fitness|ruled out|sidelined|knee|hamstring|ankle|muscle|achilles|surgery|return(s|ing)? (to|from)|back in training|scan|setback/i;
const TRF=/\b(transfers?|sign(?:s|ed|ing|ings)?|bids?|fee|loan|deal|target(?:s|ed)?|£\s?\d+|market|window|release clause|contract|takeover)\b/i;
const utc=s=>/^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/.test(s)?s.replace(' ','T')+'Z':s;
const clean=s=>(s||'').replace(/<[^>]*>/g,'').replace(/&nbsp;/g,' ').trim();

async function viaRss2json(url){
  const r=await fetch('https://api.rss2json.com/v1/api.json?rss_url='+encodeURIComponent(url),{signal:AbortSignal.timeout(6000)});
  const j=await r.json(); if(j.status!=='ok')throw new Error(j.message||'rss2json');
  return j.items.map(i=>({title:clean(i.title),url:i.link,date:new Date(utc(i.pubDate)).toISOString(),img:i.thumbnail||i.enclosure?.thumbnail||i.enclosure?.link||'',desc:clean(i.description)}));
}
async function viaAllOrigins(url){
  const r=await fetch('https://api.allorigins.win/raw?url='+encodeURIComponent(url),{signal:AbortSignal.timeout(6000)});
  const x=new DOMParser().parseFromString(await r.text(),'text/xml');
  const out=[...x.querySelectorAll('item')].map(i=>({title:clean(i.querySelector('title')?.textContent),url:i.querySelector('link')?.textContent,date:new Date(i.querySelector('pubDate')?.textContent||Date.now()).toISOString(),img:i.getElementsByTagName('media:thumbnail')[0]?.getAttribute('url')||'',desc:clean(i.querySelector('description')?.textContent)}));
  if(!out.length)throw new Error('empty');return out;
}
async function pull(f){
  let items;
  try{items=await viaRss2json(f.url)}catch(e){items=await viaAllOrigins(f.url)}
  return items.slice(0,20).map(i=>{
    let title=i.title,src=f.src||'';
    const m=title.match(/^(.*) - ([^-]{2,40})$/); // Google News "Headline - Source"
    if(!f.src&&m){title=m[1];src=m[2]}
    return {title,src:src||'News',url:i.url,date:i.date,img:i.img,cat:f.cat,feed:f.id};
  });
}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let busy=false;
function setStatus(ok,fail,cache){
  const st=$('#status'),newest=Math.max(0,...Object.values(cache).map(c=>c.ts));
  st.className='status '+(ok?(fail?'err':'live'):'err');
  $('#stxt').textContent=ok?(fail?`Live · ${fail} feed${fail>1?'s':''} unavailable`:'Live · updated '+ago(newest)):(newest?'Offline · saved news from '+ago(newest):'Offline · showing bundled news');
}
async function refresh(force=false){
  if(busy)return; busy=true; $('#refresh').classList.add('spin'); $('#stxt').textContent='Fetching live news…';
  const cache=store.get('feeds')||{}; let ok=0,fail=0;
  for(const [n,f] of FEEDS.entries()){
    const c=cache[f.id];
    if(!force&&c&&Date.now()-c.ts<TTL){ok++;continue}
    try{ if(n)await sleep(450); cache[f.id]={ts:Date.now(),items:await pull(f)}; ok++; store.set('feeds',cache); render(true)}
    catch(e){fail++}
    setStatus(ok,fail,cache);
  }
  busy=false; $('#refresh').classList.remove('spin'); setStatus(ok,fail,cache);
}
function allNews(){
  const seen=new Set(), out=[];
  const feeds=store.get('feeds')||{};
  const pool=[...Object.values(feeds).flatMap(c=>c.items),...(D.news?.items||[])];
  for(const i of pool){
    const k=i.title.toLowerCase().replace(/[^a-z0-9]/g,'').slice(0,60); if(seen.has(k))continue; seen.add(k);
    let cat=i.cat; if(cat==='team'&&TRF.test(i.title))cat='transfers'; if(cat==='team'&&INJ.test(i.title))cat='injury';
    out.push({...i,cat});
  }
  return out.sort((a,b)=>b.date.localeCompare(a.date));
}

/* ---------- DATA + VIEWS ---------- */
const load=async()=>{for(const k of ['meta','competitions','squad','injuries','history','news']){try{D[k]=await (await fetch(`data/${k}.json`,{cache:'no-cache'})).json()}catch{D[k]=null}}};
const res=m=>m.hs===m.as?'D':((m.h==='Liverpool')===(m.hs>m.as)?'W':'L');
const matchRow=m=>{const r=res(m);return `<div class="row"><div class="l"><b>${esc(m.h)} ${m.hs}–${m.as} ${esc(m.a)}</b><span class="muted">${fmt(m.date)}${m.c?' · '+esc(m.c):''}</span></div><span class="pill ${r}">${r}</span></div>`};
const allMatches=()=>(D.competitions?.competitions||[]).flatMap(c=>c.matches.map(m=>({...m,c:c.name}))).sort((a,b)=>b.date.localeCompare(a.date));
const days=d=>Math.ceil((dt(d)-new Date())/864e5);
function newsCard(i,lead){
  const l={transfers:'Transfers & market',team:'Team news',injury:'Injury news'}[i.cat]||'News';
  const img=i.img?`<img src="${safeUrl(i.img)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">`:'';
  return `<div class="card news ${lead?'lead':''}"><a href="${safeUrl(i.url)}" target="_blank" rel="noopener noreferrer">${lead?img:''}<div class="t"><span class="tag ${i.cat}">${l}</span><b>${esc(i.title)}</b><span class="muted">${esc(i.src)} · ${ago(new Date(i.date).getTime())}</span></div>${lead?'':img}</a></div>`;
}
function summary(c){
  if(!c?.summary)return '';
  const s=c.summary;
  return `<div class="grid"><div class="tile big"><b>${esc(s.pos)}</b><span>Position</span></div><div class="tile big"><b>${esc(s.Pts)}</b><span>Points</span></div>${[['P','Played'],['W','Won'],['D','Drawn'],['L','Lost'],['GF','For'],['GA','Against']].map(([k,l])=>`<div class="tile"><b>${esc(s[k])}</b><span>${l}</span></div>`).join('')}</div>`;
}
const skeleton='<div class="skel"></div><div class="skel"></div>';
const R={
home(){
  const n=D.meta?.next, ms=allMatches().slice(0,5), news=allNews().filter(i=>i.cat!=='injury'), inj=allNews().filter(i=>i.cat==='injury'||INJ.test(i.title)).slice(0,3);
  const d=n?days(n.date):0;
  return `${n?`<div class="card hero"><div class="k">Next up · ${esc(n.competition)}</div><div class="big">vs ${esc(n.opponent)}</div><div>${fmt(n.date,{weekday:'long',day:'numeric',month:'long'})}</div><div class="muted">${esc(n.venue)}</div><span class="cd">${d>0?`⏱ ${d} days to go`:d===0?'⏱ Today':'Played'}</span></div>`:''}
  <div class="card row" style="align-items:center"><div><b>Recent form</b><div class="muted">Last ${ms.length} entered</div></div><div class="form">${ms.map(m=>`<span class="pill ${res(m)}">${res(m)}</span>`).join('')}</div></div>
  <h2>Latest <a href="#/news">All news →</a></h2>${news[0]?newsCard(news[0],true):skeleton}${news.slice(1,4).map(i=>newsCard(i)).join('')}
  <h2>Premier League <a href="#/stats">Stats →</a></h2>${summary(D.competitions?.competitions?.[0])}
  <h2>Injury watch <a href="#/injuries">All →</a></h2><div class="card">${(D.injuries?.items||[]).slice(0,4).map(i=>`<div class="row"><div class="l"><b>${esc(i.n)}</b><span class="muted">${esc(i.window)}</span></div></div>`).join('')}</div>`;
},
stats(){
  const cs=D.competitions?.competitions||[], c=cs.find(x=>x.id===comp)||cs[0];
  return `<div class="chips">${cs.map(x=>`<button class="chip ${x.id===c.id?'on':''}" data-comp="${x.id}">${esc(x.name)}</button>`).join('')}</div>
  ${c.status?`<div class="note">${esc(c.status)}</div>`:''}${summary(c)}
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
  const tabs=[['all','All'],['transfers','Transfers & market'],['team','Team news'],['injury','Injuries']];
  const items=allNews().filter(i=>filter==='all'||i.cat===filter);
  return `<div class="chips">${tabs.map(([k,l])=>`<button class="chip ${filter===k?'on':''}" data-f="${k}">${l}</button>`).join('')}</div>${items.map((i,n)=>newsCard(i,n===0&&filter==='all')).join('')||skeleton}`;
},
injuries(){
  const c={High:'hi',Medium:'me',Low:'lo'}, live=allNews().filter(i=>i.cat==='injury').slice(0,8);
  return `<div class="note">${esc(D.injuries?.note||'')}</div>${(D.injuries?.items||[]).map(i=>`<div class="card"><div class="row" style="border:0;padding:0 0 4px"><b>${esc(i.n)}</b><span class="pill ${c[i.conf]||'nt'}">${esc(i.conf)} confidence</span></div><div class="muted">${esc(i.issue)}</div><p style="margin:8px 0 6px"><b>Return window:</b> ${esc(i.window)}</p><a class="src" href="${safeUrl(i.url)}" target="_blank" rel="noopener">${esc(i.src)} ↗</a></div>`).join('')||'<p class="empty">No injuries listed</p>'}
  <h2>Live injury headlines</h2>${live.map(i=>newsCard(i)).join('')||skeleton}`;
},
more(){
  const h=D.history||{};
  return `<h2>Honours</h2><div class="grid" style="grid-template-columns:repeat(4,1fr)">${(h.honours||[]).map(x=>`<div class="tile"><b>${x.c}</b><span>${esc(x.t)}</span></div>`).join('')}</div><p class="muted" style="margin-top:8px">${esc(h.honours_as_of||'')}</p>
  <h2>Timeline</h2><div class="timeline">${(h.timeline||[]).map(e=>`<div class="ev"><div class="y">${esc(e.y)}</div>${esc(e.e)}</div>`).join('')}</div>
  <h2>Did you know</h2><div class="card">${(h.facts||[]).map(f=>`<p style="margin-bottom:8px">• ${esc(f)}</p>`).join('')}</div>
  <h2>About</h2><div class="card muted">${esc(D.meta?.note||'')}<br><br>Head coach: ${esc(D.meta?.manager||'')}<br>Stadium: ${esc(D.meta?.stadium||'')}<br><br>News is fetched live from BBC Sport and Google News each time you open the app, via the public rss2json service.</div>`;
}};
let lastKey='';
function render(soft){
  const r=(location.hash.replace('#/','')||'home'), name=R[r]?r:'home';
  if(soft&&name==='squad'||soft&&name==='more'||soft&&name==='stats')return; // live news doesn't affect these
  const y=scrollY; document.querySelectorAll('.tabs a').forEach(a=>a.classList.toggle('on',a.dataset.r===name));
  view.innerHTML=R[name](); if(soft)scrollTo(0,y);
}
addEventListener('hashchange',()=>{filter='all';render();scrollTo(0,0)});
view.addEventListener('click',e=>{const b=e.target.closest('.chip');if(!b)return;if(b.dataset.comp)comp=b.dataset.comp;else filter=b.dataset.f;render()});
$('#refresh').addEventListener('click',()=>refresh(true));
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
load().then(()=>{render();refresh()});
if('serviceWorker' in navigator)navigator.serviceWorker.register('sw.js').catch(()=>{});
