const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map(),requests=[];
const ctx={URLSearchParams,current:'old',accounts:{old:{api_key:'old-key'}},location:{search:'?account_id=1'},
  CAPS:[{id:'target_detection',name:'Detect',status:'available'},{id:'planned',name:'Later',status:'planned'}],
  esc:s=>String(s).replaceAll('<','&lt;'),
  document:{querySelectorAll:()=>[{value:'target_detection'}]},
  saveAccounts(){},console,$:id=>{if(!nodes.has(id))nodes.set(id,{hidden:false,textContent:'',disabled:false});return nodes.get(id);},
  fetch:async(path,opts)=>{requests.push({path,body:JSON.parse(opts.body)});return {ok:true,json:async()=>({account:'1',api_key:'new-key'})};},
  wbMessage:e=>e.message,api:async()=>({status:'delivered',event_id:'sub-test'})};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('static/purchase.js','utf8'),ctx);
(async()=>{
  const selector=ctx.purchaseCapabilitySelector(['target_detection','planned','unknown']);
  assert.match(selector,/type="checkbox" value="target_detection" checked/);
  assert.doesNotMatch(selector,/Later|unknown/);
  assert.deepEqual(Array.from(ctx.purchaseCapabilityIds()),['target_detection']);
  await ctx.purchaseBootstrap();
  assert.equal(ctx.current,'1');assert.equal(ctx.accounts['1'].api_key,'new-key');
  assert.deepEqual(requests[0].body,{account:'1'});
  ctx.location.search='?account_id=1&account_id=2';
  await assert.rejects(ctx.purchaseBootstrap());assert.equal(ctx.current,'');
  assert.equal(requests.length,1);
  ctx.location.search='?account_id=1&callback_url=http://unsafe';
  await ctx.purchaseBootstrap();assert.deepEqual(requests[1].body,{account:'1'});
  ctx.purchaseNotice({status:'failed',event_id:'sub-test'});
  assert.equal(ctx.$('#purchase-notice-retry').hidden,false);
  await ctx.$('#purchase-notice-retry').onclick();
  assert.match(ctx.$('#purchase-notice-text').textContent,/套餐已发送/);
  assert.equal(ctx.$('#purchase-notice-retry').hidden,true);
  console.log('Purchase handoff, exact numeric identity and retry display passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
