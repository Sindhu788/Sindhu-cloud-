import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=fs.readFileSync('sindhu_web/static/js/app.js','utf8');
const tokenSource=source.slice(source.indexOf('  async function ensureToken()'),source.indexOf('  async function apiGet('));
function context(fetch){return vm.createContext({fetch,AbortController,Error,localStorage:{setItem(){}},setTimeout(fn){queueMicrotask(fn);return 1;},clearTimeout(){}});}
let c=context(async()=>({ok:false,status:401}));
await assert.rejects(vm.runInContext('let apiToken="";'+tokenSource+'ensureToken()',c),/HTTP 401/);
c=context(async()=>({ok:true,json:async()=>({})}));
await assert.rejects(vm.runInContext('let apiToken="";'+tokenSource+'ensureToken()',c),/unavailable/);
c=context((url,{signal})=>new Promise((resolve,reject)=>{signal.addEventListener('abort',()=>{let e=new Error();e.name='AbortError';reject(e);});}));
await assert.rejects(vm.runInContext('let apiToken="";'+tokenSource+'ensureToken()',c),/timed out/);
c=context(async()=>({ok:true,json:async()=>({token:'isolated-fixture'})}));
assert.equal(await vm.runInContext('let apiToken="";'+tokenSource+'ensureToken()',c),'isolated-fixture');
const init=source.slice(source.lastIndexOf('  (async function init()'),source.lastIndexOf('})();'));
let retry={};let content={innerHTML:'Loading...'};
c=vm.createContext({ensureToken:async()=>{throw new Error('Service unavailable');},renderNav:async()=>{},content,esc:s=>s,document:{getElementById:()=>retry},location:{reload(){}},connectWs(){},reportClientDiagnostics(){},route:async()=>{}});
await vm.runInContext(init,c);assert.match(content.innerHTML,/Dashboard could not start/);assert.match(content.innerHTML,/Retry dashboard/);assert.equal(typeof retry.onclick,'function');
console.log('PASS: token success, HTTP auth failure, missing token, stalled transport timeout, visible bootstrap retry (5 checks)');
