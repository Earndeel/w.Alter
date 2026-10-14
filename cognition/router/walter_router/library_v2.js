
const links=document.querySelectorAll('nav a'),panes=document.querySelectorAll('.pane'),q=document.getElementById('q'),
d=document.getElementById('diff');let cur='home';
function show(t){cur=t;links.forEach(a=>a.classList.toggle('on',a.dataset.tab===t));panes.forEach(p=>p.hidden=p.dataset.pane!==t);filter()}
function filter(){const s=(q.value||'').trim().toLowerCase();if((s||d.checked)&&cur==='home'){show(d.checked?'video':'chat');return}
document.querySelectorAll('tbody tr[data-search]').forEach(r=>r.classList.toggle('hide',!((!s||r.dataset.search.includes(s))&&(!d.checked||r.dataset.differs==='1'))))}
links.forEach(a=>a.onclick=e=>{e.preventDefault();show(a.dataset.tab);history.replaceState(null,'','#'+a.dataset.tab)});
q.oninput=filter;d.onchange=filter;
document.querySelectorAll('#costseg button').forEach(b=>b.onclick=()=>{
document.querySelectorAll('#costseg button').forEach(x=>x.classList.toggle('on',x===b));
document.querySelectorAll('figure.chart').forEach(f=>f.hidden=f.dataset.cost!==b.dataset.cost)});
document.querySelectorAll('[data-tip]').forEach(el=>{const tip=el.closest('figure').querySelector('.tip');
el.addEventListener('mouseenter',()=>{const o=JSON.parse(el.dataset.tip);tip.innerHTML='<b>'+o.n+'</b><br>Indice '+o.s+' · '+o.c+' $ par tâche'+(o.p?' · '+o.p:'');tip.style.display='block'});
el.addEventListener('mousemove',e=>{const r=tip.parentElement.getBoundingClientRect();tip.style.left=(e.clientX-r.left+12)+'px';tip.style.top=(e.clientY-r.top-8)+'px'});
el.addEventListener('mouseleave',()=>tip.style.display='none')});
show((location.hash||'#home').slice(1)||'home');
const rb=document.getElementById('runbtn'),rs=document.getElementById('runstate');let poll=null;
function fmt(t){if(!t)return'';const d=new Date(t.replace(/^\w+ /,''));return isNaN(d)?t:d.toLocaleString('fr-FR',{dateStyle:'short',timeStyle:'short'})}
async function state(){try{const r=await fetch('/api/status',{cache:'no-store'});const o=await r.json();
if(o.running){rb.disabled=true;rs.textContent='Cycle en cours — '+(o.step||'démarrage')}
else{rb.disabled=false;rs.textContent=o.finished?('Dernier cycle complet : '+fmt(o.finished)+(o.result&&o.result!=='success'?' (échec)':'')):''; if(poll){clearInterval(poll);poll=null;if(o.result==='success')setTimeout(()=>location.reload(),20000)}}
if(o.running&&!poll)poll=setInterval(state,15000)}catch(e){rs.textContent='Statut indisponible'}}
rb.onclick=async()=>{if(!confirm('Lancer maintenant le cycle complet ? Collecte des classements, recalcul, analyse par le modèle économique, notifications et republication de cette page (20 à 60 minutes).'))return;
rb.disabled=true;rs.textContent='Lancement…';try{const r=await fetch('/api/run',{method:'POST'});const o=await r.json();rs.textContent=o.message||'';}catch(e){rs.textContent='Échec du lancement'}setTimeout(state,1500)};
state();
