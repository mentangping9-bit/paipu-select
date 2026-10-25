// Exercise the real renderer with a minimal inert DOM; no network or credentials.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes={};
class Element {
 constructor(tag='div'){this.tag=tag;this.children=[];this.attributes={};this.textContent='';this.value='';this.hidden=false;}
 set id(v){this._id=v;nodes[v]=this;} get id(){return this._id;}
 append(...items){this.children.push(...items);} replaceChildren(...items){this.children=items;}
 setAttribute(k,v){this.attributes[k]=v;} focus(){this.focused=true;}
 addEventListener(){}
 createTHead(){const n=new Element('thead');this.append(n);return n;} createTBody(){const n=new Element('tbody');this.append(n);return n;}
 insertRow(){const n=new Element('tr');this.append(n);return n;} insertCell(){const n=new Element('td');this.append(n);return n;}
}
const html=fs.readFileSync('public/index.html','utf8');
for(const m of html.matchAll(/id="([^"]+)"/g)){assert.ok(!nodes[m[1]],'Duplicate HTML ID '+m[1]);const n=new Element();n.id=m[1];}
nodes.usagePeriod.value='7';nodes.accountFilter.value='all';nodes.accountSlot.value='1';
const events={};
const document={documentElement:{lang:'ko'},getElementById:id=>nodes[id],createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag),querySelectorAll:()=>[],createTreeWalker:()=>({nextNode:()=>false}),addEventListener:(k,v)=>events[k]=v,dispatchEvent:e=>events[e.type]?.(e)};
const c={document,navigator:{language:'ko'},NodeFilter:{SHOW_TEXT:4},Event:class{constructor(type){this.type=type;}},localStorage:{getItem:()=>null,setItem(){}},fetch(){throw Error('Dashboard must not fetch');}};
c.globalThis=c;vm.createContext(c);vm.runInContext(fs.readFileSync('public/i18n.js','utf8'),c);vm.runInContext(fs.readFileSync('public/operator-dashboard.js','utf8'),c);
const text=n=>n.textContent+n.children.map(text).join(' ');
const all=(n,tag)=>[...(n.tag===tag?[n]:[]),...n.children.flatMap(x=>all(x,tag))];
const accounts=Array.from({length:20},(_,i)=>({slot:i+1,email:`private${i}@example.com`,region:'jp',authenticated:true,cooldown_seconds:0,rate_limit_seconds:0,usage:{today:{attempts:i,successes:i,failures:0},total:{attempts:i*1000,successes:i*1000,failures:0},last_attempt_at:1792947600-i*60,last_failure_at:1792700000,last_error_code:540}}));
accounts[3].rate_limit_seconds=1000;accounts[3].cooldown_seconds=1000;
const days=Array.from({length:30},(_,i)=>({day:`2026-10-${String(i+1).padStart(2,'0')}`,known:i===29,attempts:i===29?190:null,successes:i===29?189:null,failures:i===29?1:null}));
const data={accounts,daily_usage:{started_day:'2026-10-30',days},next_slot:5,scheduler:{enabled:true,interval_seconds:60,accounts:{}},usage_persistent:true};
const original=JSON.stringify(data),D=c.PaipuOperatorDashboard;
D.render(data);
assert.equal(nodes.usageTodayTotal.textContent,'190');assert.equal(nodes.usageAllTotal.textContent,'190,000');assert.equal(nodes.usageReadyTotal.textContent,'19 / 20');
assert.equal(all(nodes.usageCards,'button').length,20);assert.ok(!text(nodes.usageCards).includes('@example.com'),'Emails must remain folded');
assert.ok(text(nodes.usageCards).includes('정상'),'Old 540 history must not mark recovered accounts as unhealthy');
assert.equal(all(nodes.usageChart,'polyline').length,0,'Unknown days must not become zero-valued history');
assert.equal(all(nodes.usageDailyTable,'tr').length,8);
assert.equal(all(nodes.usageChart,'circle').length,3);
const button=nodes['account-toggle-1'];button.onclick();
assert.equal(nodes['account-toggle-1'].attributes['aria-expanded'],'true');assert.ok(text(nodes['account-detail-1']).includes('private0@example.com'));
nodes['account-toggle-2'].onclick();assert.equal(nodes['account-detail-1'].hidden,true);assert.equal(nodes['account-detail-2'].hidden,false);
nodes['account-toggle-2'].onclick();assert.ok(!text(nodes.usageCards).includes('@example.com'));
nodes.accountFilter.value='attention';nodes.accountFilter.onchange();assert.equal(all(nodes.usageCards,'button').length,1);assert.equal(all(nodes.usageCards,'button')[0].textContent,'4');
accounts[3].rate_limit_seconds=accounts[3].cooldown_seconds=0;D.render(data);assert.equal(nodes.accountFilterEmpty.hidden,false);
nodes.accountFilter.value='all';nodes.usagePeriod.value='30';nodes.usagePeriod.onchange();assert.equal(all(nodes.usageDailyTable,'tr').length,31);
for(const language of ['en','ja','ko']){c.PaipuI18n.setLanguage(language);D.render(data);assert.equal(nodes.usageTodayTotal.textContent,'190');}
// Rendering does not update counters, provider state, or the raw data.
accounts[3].rate_limit_seconds=accounts[3].cooldown_seconds=1000;assert.equal(JSON.stringify(data),original);
assert.equal(nodes.selectedAccountEmail.textContent,'private0@example.com · JP');
D.render({accounts:[],daily_usage:{days:[]}});assert.equal(nodes.usageTodayTotal.textContent,'0');assert.equal(nodes.usageLastAttempt.textContent,'없음');
console.log('PASS: dashboard totals, private folded details, recovered status, filters, period controls, unknown dates, empty data, multilingual rerenders and no network/data mutation');
