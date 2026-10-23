// Real generated URLs, clipboard representations and async navigation ordering.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync('public/clipboard.js','utf8');
function load(navigator={},ClipboardItem){
 const context={navigator,Blob,ClipboardItem};context.globalThis=context;
 vm.createContext(context);vm.runInContext(code,context);
 return context.PaipuClipboard;
}
const parserScope={};parserScope.globalThis=parserScope;
vm.createContext(parserScope);vm.runInContext(fs.readFileSync('public/converter.js','utf8'),parserScope);
const parser=parserScope.NagaParser;
const rounds=parser.parseText(fs.readFileSync('tests/fixture.json','utf8'));
const text=parser.urlsForSelection(rounds,new Set(rounds.map(r=>r.id)),false);
class Item{constructor(data){this.data=data;}}
function legacy(success=true,html=false){
 let handler,removed=false,prevented=false,selected=false;const values={};
 const document={
  addEventListener(type,callback,capture){assert.equal(type,'copy');assert.equal(capture,true);handler=callback;},
  removeEventListener(type,callback,capture){assert.equal(callback,handler);assert.equal(capture,true);removed=true;},
  execCommand(command){
   assert.equal(command,'copy');assert.equal(selected,true);
   if(success)handler({clipboardData:{setData(type,data){values[type]=data;}},preventDefault(){prevented=true;}});
   return success;
  }
 };
 const textarea={ownerDocument:document,focus(){},select(){selected=true;},setSelectionRange(a,b){assert.equal(a,0);assert.equal(b,text.length);}};
 return {textarea,check(){assert.equal(removed,true);if(success){assert.equal(values['text/plain'],text);if(html)assert.equal(values['text/html'],'<pre>'+text+'</pre>');else assert.equal(values['text/html'],undefined);assert.equal(prevented,true);}}};
}
(async()=>{
 let calls=0;
 const modern=load({userAgent:'Mozilla/5.0 (Linux; Android 16; SM-S911N)',clipboard:{
  async write(){assert.fail('Android must not write HTML or use ClipboardItem before writeText');},
  async writeText(value){calls++;assert.equal(value,text);}
 }},Item);
 assert.equal(await modern.copyText(text),true);assert.equal(calls,1);
 assert.equal(text.split('\n').length,rounds.length);
 for(const line of text.split('\n'))assert.equal(parser.parseUrlJSON(line).log.length,1);
 let blobCalls=0;
 const plainBlob=load({clipboard:{async writeText(){throw Error('writeText unsupported');},async write(items){
  blobCalls++;assert.equal(items.length,1);assert.deepEqual(Object.keys(items[0].data),['text/plain']);
  const blob=items[0].data['text/plain'];assert.equal(blob.type,'text/plain');assert.equal(await blob.text(),text);
 }}},Item);
 assert.equal(await plainBlob.copyText(text),true);assert.equal(blobCalls,1);
 const blobOnly=load({clipboard:{async write(items){assert.deepEqual(Object.keys(items[0].data),['text/plain']);assert.equal(await items[0].data['text/plain'].text(),text);}}},Item);
 assert.equal(await blobOnly.copyText(text),true);
 const oldApi=load({clipboard:{async writeText(value){assert.equal(value,text);}}});
 assert.equal(await oldApi.copyText(text),true);
 const selection=legacy(true,true);
 const selectionFirst=load({userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X)',clipboard:{async write(){assert.fail('iOS copy event must precede async APIs');},async writeText(){assert.fail('iOS copy event must precede async APIs');}}},Item);
 assert.equal(await selectionFirst.copyText(text,selection.textarea),true);selection.check();
 const desktopIpad=legacy(true,true);
 assert.equal(await load({platform:'MacIntel',maxTouchPoints:5}).copyText(text,desktopIpad.textarea),true);desktopIpad.check();
 const fallbackSelection=legacy();
 const denied=load({clipboard:{async write(){throw Error('denied');},async writeText(){throw Error('denied');}}},Item);
 assert.equal(await denied.copyText(text,fallbackSelection.textarea),true);fallbackSelection.check();
 const failed=legacy(false);
 assert.equal(await load().copyText(text,failed.textarea),false);failed.check();
 assert.equal(await modern.copyText(''),false);
 const inspect=load().inspectPaste;
 assert.equal(inspect(text,text).state,'match');
 assert.equal(inspect(text,text.replaceAll('\n','\r\n')).state,'match');
 assert.equal(inspect(text,text.replaceAll('\n','')).state,'linebreaks');
 assert.equal(inspect(text,text.replaceAll('\n',' ')).state,'linebreaks');
 assert.equal(inspect(text,text.replaceAll('\n','\t  ')).state,'linebreaks');
 assert.equal(inspect(text,text.replaceAll('%','%25')).state,'changed');
 assert.equal(inspect(text,'').state,'empty');
 const exactText=load({clipboard:{async writeText(value){assert.equal(value,'<img src=x>&\nhttps://tenhou.net/5/#json=%7B%7D');}}},Item);
 assert.equal(await exactText.copyText('<img src=x>&\nhttps://tenhou.net/5/#json=%7B%7D'),true);

 const app=fs.readFileSync('public/app.js','utf8');
 const begin=app.indexOf('async function openNaga()');
 assert.ok(begin>=0,'NAGA handoff must await copying');
 const fn=app.slice(begin,app.indexOf('\nfunction saveOutput()',begin));
 for(const succeeds of [false,true]){
  const visits=[];let settle;
  const pending=new Promise(resolve=>{settle=resolve;});
  const scope={copyOutput:()=>pending,location:{assign:url=>visits.push(url)}};
  vm.createContext(scope);vm.runInContext(fn,scope);
  const handoff=scope.openNaga();
  assert.equal(visits.length,0,'must retain focus while clipboard write is pending');
  settle(succeeds);assert.equal(await handoff,succeeds);
  assert.deepEqual(visits,succeeds?['https://naga.dmv.nico/naga_report/order_form/?show_tab=1']:[]);
 }
 const html=fs.readFileSync('public/index.html','utf8');
 assert.ok(html.indexOf('./clipboard.js')<html.indexOf('./app.js'));
 console.log(`PASS: ${rounds.length} generated URLs retain newlines and percent encoding; Android/PC plain-text-only copy, iOS synchronous fallback, space-flattened paste diagnostics; no navigation before copy or after failure`);
})().catch(error=>{console.error(error);process.exitCode=1;});
