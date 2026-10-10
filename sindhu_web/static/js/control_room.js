'use strict';
const el=id=>document.getElementById(id);
const guest=location.pathname==='/preview';
let definitions=[],sessionId=guest?null:sessionStorage.getItem('sindhu-review-virtual-session'),csrf=null,virtualPaused=false;
const value=v=>v==null?'Unavailable':typeof v==='boolean'?(v?'Yes':'No'):String(v);
function notice(text,error=false){el('notice').textContent=text;el('notice').classList.toggle('error',error);}
function table(target,headers,rows){
  const wrap=el(target);wrap.replaceChildren();
  if(!rows.length){wrap.textContent='No recorded rows in this view.';return;}
  const t=document.createElement('table'),head=document.createElement('tr');
  headers.forEach(h=>{const th=document.createElement('th');th.textContent=h;head.append(th);});t.append(head);
  rows.forEach(row=>{const tr=document.createElement('tr');row.forEach(v=>{const td=document.createElement('td');td.textContent=value(v);tr.append(td);});t.append(tr);});wrap.append(t);
}
function pairs(target,items){const wrap=el(target);wrap.replaceChildren();Object.entries(items).forEach(([k,v])=>{const row=document.createElement('div'),a=document.createElement('span'),b=document.createElement('b');row.className='kv';a.textContent=k;b.textContent=value(v);row.append(a,b);wrap.append(row);});}
async function api(path,body){
  if(guest&&path!=='/api/quality/preview')throw new Error('Sign in to access private measurements or protected controls.');
  if(body!==undefined&&csrf===null)csrf=(await api('/api/token')).token;
  const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json','X-Sindhu-Token':csrf},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(20000)});
  let result;try{result=await response.json();}catch{throw new Error('Unexpected response; service may be waking up.');}
  if(!response.ok){if(response.status===401&&body!==undefined)csrf=null;throw new Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail||result));}
  return result;
}
async function action(id,fn){const b=el(id);b.disabled=true;try{await fn();}catch(e){notice(e.message,true);}finally{b.disabled=guest||((id==='virtual-example'||id==='virtual-pause')&&virtualPaused)||(id==='virtual-resume'&&!virtualPaused);}}
function renderStrategies(){const q=el('strategy-search').value.toLowerCase(),status=el('strategy-status').value;
  const rows=definitions.filter(s=>(!status||(s.archived?'archived':s.status)===status)&&[s.id,s.name,...(s.concepts||[])].join(' ').toLowerCase().includes(q)).sort((a,b)=>el('strategy-sort').value==='version'?(b.version||0)-(a.version||0):String(a.name||a.id).localeCompare(b.name||b.id));
  el('strategy-count').textContent=rows.length+' / '+definitions.length+' definitions';
  table('strategy-table',['Name / ID','Version','Status','Dependencies','Concepts','Validation'],rows.map(s=>[s.name||s.id,s.version,s.archived?'archived':s.status,JSON.stringify(s.dependencies||{}),(s.concepts||[]).join(', '),s.tested_performance||'NOT TESTED']));
  const selector=el('strategy-inspect');selector.replaceChildren();const first=document.createElement('option');first.value='';first.textContent='Choose a definition';selector.append(first);rows.forEach(s=>{const o=document.createElement('option');o.value=s.id;o.textContent=(s.name||s.id)+' · v'+s.version;selector.append(o);});
}
async function journal(){const r=await api('/api/quality/journal');table('journal-table',['UTC','Symbol','Strategy','Decision','Reason','Confidence'],r.entries.map(x=>[x.at_utc,x.symbol,x.strategy,x.decision,x.reason,x.confidence]));}
async function settings(){const [s,h]=await Promise.all([api('/api/paper-trading/settings'),api('/api/paper-trading/settings/history')]);el('risk').value=s.risk_pct_default;el('cooldown').value=s.cooldown_minutes;el('max-open').value=s.max_open_trades;
 table('settings-history',['Changed UTC','Source','Changes'],h.entries.map(x=>[x.changed_at,x.source,x.changes.map(c=>c.field+': '+value(c.old)+' → '+value(c.new)).join('; ')]));}
async function refresh(){
 const r=await api('/api/quality/diagnostics');el('mode').textContent=r.mode.toUpperCase()+' · VIRTUAL';el('as-of').textContent=r.as_of_utc+' · UTC';el('scanner').textContent=r.scanner.running?'Running':'Stopped';el('last-scan').textContent='Last successful: '+value(r.scanner.last_successful_scan);el('database').textContent=r.database.connected?'Connected':'Disconnected';el('decisions').textContent=value(r.counts.saved_decisions);el('accepted').textContent='Accepted '+value(r.counts.accepted)+' · rejected '+value(r.counts.rejected);el('delivery').textContent=value(r.notifications.delivered)+' delivered';el('attempts').textContent='Logged attempts '+value(r.notifications.attempts)+' · errors '+value(r.notifications.errors);
 el('blockers').replaceChildren();(r.blockers.length?r.blockers:['No startup blocker recorded; entry rules and risk gates still apply.']).forEach(t=>{const li=document.createElement('li');li.textContent=t;el('blockers').append(li);});pairs('funnel',{'Scan receipts':r.counts.scans,'Coins scanned':r.counts.coins_scanned,'Candidates':r.counts.candidates,'Accepted decisions':r.counts.accepted,'Rejected decisions':r.counts.rejected,'NO_TRADE decisions':r.counts.no_trade});el('coverage').textContent=r.telemetry_coverage;table('reasons',['Reason','24h count'],r.top_rejections.map(x=>[x.reason,x.count]));
 pairs('health-values',{'Database backend':r.database.backend,'Database connected':r.database.connected,'Safe startup':r.scanner.safe_start,'Saved engine enabled':r.scanner.engine_enabled,'Worker running':r.scanner.running,'Enabled strategies':r.scanner.enabled_strategies,'Last saved decision':r.latest_saved_decision,'Last tick in this process':r.scanner.last_tick_this_process});el('market-status').textContent=r.market_data.status;
 pairs('telegram-values',{'Dry-run':r.telegram.dry_run,'Master send switch':r.telegram.master_send_enabled,'Token configured':r.telegram.token_present,'Private target configured':r.telegram.private_target_present,'Public publisher':r.telegram.public_owner});table('notification-types',['Notification type','Success','24h count'],r.notifications.by_type.map(x=>[x.type,x.success,x.count]));notice('Measured data loaded. '+r.window+'. Missing telemetry is shown as unavailable.');
}
el('refresh').onclick=()=>action('refresh',refresh);el('journal-refresh').onclick=()=>action('journal-refresh',journal);
el('logout').onclick=()=>action('logout',async()=>{await api('/api/auth/logout',{});location.href='/login';});
for(const id of ['strategy-search','strategy-status','strategy-sort'])el(id).addEventListener(id==='strategy-search'?'input':'change',renderStrategies);
el('strategy-inspect').onchange=()=>{const s=definitions.find(x=>x.id===el('strategy-inspect').value);el('strategy-detail').textContent=s?JSON.stringify({id:s.id,version:s.version,definition_sha256:s.definition_sha256,entry:s.entry,exit:s.exit,invalidation:s.invalidation,take_profit:s.take_profit,dependencies:s.dependencies,status:s.status,archived:s.archived,validation:s.uncertainty},null,2):'Choose a definition to inspect its saved rules.';};
el('start').onclick=()=>action('start',async()=>{await api('/api/paper-trading/start',{});await refresh();});el('stop').onclick=()=>action('stop',async()=>{await api('/api/paper-trading/stop',{});await refresh();});
function showSession(r){virtualPaused=Boolean(r.paused);el('virtual-result').textContent=JSON.stringify(r,null,2);el('virtual-example').disabled=virtualPaused;el('virtual-pause').disabled=virtualPaused;el('virtual-resume').disabled=!virtualPaused;}
el('virtual-create').onclick=()=>action('virtual-create',async()=>{const r=await api('/api/intelligence/virtual-sessions',{});sessionId=r.session_id;sessionStorage.setItem('sindhu-review-virtual-session',sessionId);showSession(r);});
el('virtual-example').onclick=()=>action('virtual-example',async()=>{el('virtual-result').textContent=JSON.stringify(await api('/api/intelligence/virtual-sessions/'+encodeURIComponent(sessionId)+'/example',{}),null,2);});
el('virtual-pause').onclick=()=>action('virtual-pause',async()=>showSession(await api('/api/intelligence/virtual-sessions/'+encodeURIComponent(sessionId)+'/pause',{})));
el('virtual-resume').onclick=()=>action('virtual-resume',async()=>showSession(await api('/api/intelligence/virtual-sessions/'+encodeURIComponent(sessionId)+'/resume',{})));
el('private-dry-run').onclick=()=>{el('notification-preview').textContent='PRIVATE DRY-RUN\nDecision: NO_TRADE\nReason: Diagnostic preview only; no market signal evaluated.\nNetwork calls: 0\nSent: false';};
el('board-refresh').onclick=()=>action('board-refresh',async()=>{const r=await api('/api/intelligence/leaderboard');table('board-table',['Strategy / recorded version','Trades','Win %','Profit factor','Expectancy','Avg win','Avg loss','Realized drawdown','Validation'],r.rows.map(s=>[(s.name||s.strategy_id)+' / '+value(s.version),s.trades,s.win_rate_pct,s.profit_factor,s.expectancy,s.average_win,s.average_loss,s.max_drawdown,[s.validation_status||s.status,s.version_provenance].filter(Boolean).join(' · ')]));});
el('settings-form').onsubmit=e=>{e.preventDefault();action('settings-save',async()=>{await api('/api/paper-trading/settings',{risk_pct_default:Number(el('risk').value),cooldown_minutes:Number(el('cooldown').value),max_open_trades:Number(el('max-open').value)});await settings();notice('Paper settings saved and reloaded from storage.');});};
if(guest){document.querySelectorAll('button,input,select').forEach(x=>x.disabled=true);el('mode').textContent='GUEST · READ ONLY';notice('Read-only layout preview. Private measurements are unavailable. Sign in for protected controls.');}
else{if(sessionId)api('/api/intelligence/virtual-sessions/'+encodeURIComponent(sessionId)).then(showSession).catch(e=>notice(e.message,true));Promise.allSettled([refresh(),journal(),settings(),api('/api/quality/strategies').then(r=>{definitions=r.strategies;renderStrategies();})]).then(results=>{const failed=results.filter(x=>x.status==='rejected');if(failed.length)notice(failed.map(x=>x.reason.message).join(' · '),true);});}
