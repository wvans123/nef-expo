/* Incremental integration for the original workbench. Native tabs, forms and drag/drop remain in index.html. */
const wb={networkBusy:false,networkError:'',access:null,scenes:[],sceneId:'',catalog:[],market:[],toolSubscriptions:[],servers:[],packages:[],networkStatus:'not_configured',epoch:0,channels:[],channel:'',feedbackContext:'',feedbackSignature:'',feedbackBusy:false,resultTimer:null,resultBusy:false};
const wbStatus=x=>({not_configured:'待对接',not_discovered:'未发现',discovering:'发现中',discovered:'已发现',pending:'待同步',submitted:'已提交 · 待确认',synced:'已同步',syncing:'同步中',calling:'转发中',returned:'已收到 AF 回执',tool_error:'AF 返回工具错误',failed:'失败'}[x]||x||'待处理');
function wbMessage(e){const d=e?.data?.detail??e?.detail;return typeof d==='string'?d:d?.message||e?.message||'请求未完成';}
function wbError(e){toast(wbMessage(e),false);}
function wbActive(){return document.querySelector('#tabs .active')?.dataset.tab||'market';}
function wbScene(){return wb.scenes.find(s=>s.id===wb.sceneId);}
function wbPrice(scene,plain=false){const text=scene.price==null?'价格待配置':'¥'+scene.price+' / 月';return plain?text:`<div class="wb-price">${esc(text)}${scene.discount==null?'':`<small>组合价 ${Number((scene.discount*10).toFixed(2))} 折</small>`}</div>`;}
function wbSceneActions(selector,owned){
  $$(selector).forEach(button=>{
    const id=button.dataset.wbScene||button.dataset.subsScene,scene=wb.scenes.find(s=>s.id===id);
    button.insertAdjacentHTML('beforebegin',wbPrice(scene));
    if(owned.has(id)){const cancel=document.createElement('button');cancel.textContent='取消开通';cancel.onclick=()=>wbCancelScene(id);button.after(cancel);}
  });
}
function wbCancelScene(id){
  const scene=wb.scenes.find(s=>s.id===id);if(!scene||!apiKey())return;
  showModal(`<h2>取消「${esc(scene.name)}」</h2><div class="wb-modal-actions"><button id="wb-keep-scene">保留</button><button id="wb-confirm-cancel">取消开通</button></div><p id="wb-cancel-message" role="status"></p>`);
  $('#wb-keep-scene').onclick=hideModal;
  $('#wb-confirm-cancel').onclick=()=>wbJob($('#wb-confirm-cancel'),$('#wb-cancel-message'),async epoch=>{
    const result=await api('/api/v1/services/'+encodeURIComponent(id)+'/subscribe',{method:'DELETE'});
    if(epoch!==wb.epoch)return;wbStopResultLoop();hideModal();purchaseNotice(result.notification);await wbLoadScenes();if(wbActive()==='subs')await renderSubs();
  });
}
async function wbJob(button,target,fn){if(!apiKey())return toast('请先在顶栏注册或选择账号',false);const epoch=wb.epoch;button.disabled=true;if(target)target.textContent='正在处理…';try{const text=await fn(epoch);if(epoch===wb.epoch&&target)target.textContent=text||'已更新';}catch(e){if(epoch===wb.epoch){if(target)target.textContent=wbMessage(e);else wbError(e);}}finally{button.disabled=false;}}
$('#btn-register-acct').onclick=()=>{
  showModal('<h2>注册演示账号</h2><p class="muted">账号、订阅与密钥保存在本次服务内，不产生真实费用。</p><label for="wb-account-name">AF 名称</label><input id="wb-account-name" maxlength="60" autocomplete="off"><div class="wb-modal-actions"><button id="wb-account-cancel">取消</button><button id="wb-account-create" class="primary">创建账号</button></div><p id="wb-account-error" class="muted"></p>');
  $('#wb-account-cancel').onclick=hideModal;
  $('#wb-account-create').onclick=async()=>{const name=$('#wb-account-name').value.trim();if(!name)return;const b=$('#wb-account-create');b.disabled=true;try{const r=await api('/api/v1/register',{method:'POST',body:JSON.stringify({account:name})});accounts[name]={api_key:r.api_key};current=name;saveAccounts();hideModal();await refreshAll();toast('演示账号已创建');}catch(e){$('#wb-account-error').textContent=wbMessage(e);b.disabled=false;}};
};
async function wbLoadScenes(){
  const epoch=wb.epoch;const r=await fetch('/api/v1/services');if(!r.ok)throw new Error('场景目录读取失败');const data=await r.json();if(epoch!==wb.epoch)return;wb.scenes=data.services;
  let info=null;if(apiKey())try{info=await api('/api/v1/auth/info');}catch{}
  if(epoch!==wb.epoch)return;
  const owned=new Set(info?.scene_subscriptions||[]);
  $('#wb-scene-market').innerHTML=wb.scenes.map(s=>`<article class="pkg-chip wb-scene-card"><span class="method-chip">场景套餐</span><h3>${esc(s.name)}</h3><p class="muted">${esc(s.description)}</p><div class="wb-scene-outputs">${s.outputs.map(t=>`<span>${esc(t)}</span>`).join('')}</div><div class="wb-components"><label>基础能力组合</label>${(s.provenance?.components||[]).map(c=>`<button class="wb-component" data-scene-cap="${esc(c.capability_id)}" title="${esc(c.role)}">${esc(CAPS.find(x=>x.id===c.capability_id)?.name||c.capability_id)}</button>`).join('')}<small>套餐设计 · NEF / 场景服务方</small></div><button data-wb-scene="${esc(s.id)}" class="${owned.has(s.id)?'primary':'success'}">${owned.has(s.id)?'进入场景 →':'开通场景'}</button></article>`).join('');
  $$('#wb-scene-market [data-scene-cap]').forEach(b=>b.onclick=()=>showCap(b.dataset.sceneCap));
  $$('#wb-scene-market [data-wb-scene]').forEach(b=>b.onclick=()=>wbOpenScene(b.dataset.wbScene,owned.has(b.dataset.wbScene)));
  wbSceneActions('#wb-scene-market [data-wb-scene]',owned);
  wbRenderSceneSubscriptions(info);
  if(wbActive()==='intent')wbRenderIntent();
}
function wbRenderSceneSubscriptions(info){
  const owned=new Set(info?.scene_subscriptions||[]);
  $('#wb-scene-subs').innerHTML='<h3 class="sec">场景订阅权益</h3><div class="wb-scene-grid">'+wb.scenes.map(s=>`<div class="step-card"><b>${esc(s.name)}</b><p class="muted">场景入口 · 调用时核验使用权</p><button data-subs-scene="${esc(s.id)}" class="${owned.has(s.id)?'primary':'success'}">${owned.has(s.id)?'已开通 · 进入场景':'开通场景'}</button></div>`).join('')+'</div>';
  $$('#wb-scene-subs [data-subs-scene]').forEach(b=>b.onclick=()=>wbOpenScene(b.dataset.subsScene,owned.has(b.dataset.subsScene)));
  wbSceneActions('#wb-scene-subs [data-subs-scene]',owned);
}
function wbOpenScene(id,owned){
  if(!apiKey())return toast('请先在顶栏注册账号',false);
  const s=wb.scenes.find(x=>x.id===id);if(!s)return;
  if(owned){wb.sceneId=id;activateTab('intent',true);return;}
  showModal(`<h2>开通「${esc(s.name)}」</h2><p class="muted">开通后获得该场景的调用权益。当前为演示订阅，不产生真实费用。</p>${purchaseCapabilitySelector((s.provenance?.components||[]).map(c=>c.capability_id))}<div class="wb-modal-actions"><button id="wb-cancel">取消</button><button class="success" id="wb-confirm-scene">确认开通</button></div><p id="wb-sub-message" class="muted"></p>`);
  $('#purchase-capabilities').insertAdjacentHTML('afterend','<div id="wb-purchase-quote" class="wb-price"></div>');
  const quote=()=>{const ids=purchaseCapabilityIds();$('#wb-purchase-quote').textContent=purchaseQuoteText(purchaseQuote(s,ids));$('#wb-confirm-scene').disabled=!ids.length;};
  $$('#purchase-capabilities input').forEach(input=>input.onchange=quote);quote();
  $('#wb-cancel').onclick=hideModal;$('#wb-confirm-scene').onclick=()=>wbJob($('#wb-confirm-scene'),$('#wb-sub-message'),async epoch=>{const result=await api('/api/v1/services/'+encodeURIComponent(id)+'/subscribe',{method:'POST',body:JSON.stringify({network_capability_ids:purchaseCapabilityIds()})});if(epoch!==wb.epoch)return;hideModal();purchaseNotice(result.notification);await wbLoadScenes();if(wbActive()==='subs')await renderSubs();return '已开通';});
}
function wbRenderIntent(){
  const sel=$('#wb-intent-scene');sel.innerHTML='<option value="">不指定场景</option>'+wb.scenes.map(s=>`<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('');sel.value=wb.sceneId;
  $('#wb-intent-subscribe').hidden=!wb.sceneId;
  $('#wb-intent-subscribe').disabled=false;$('#wb-intent-subscribe').textContent='开通当前场景';
  $('#wb-intent-subscribe').onclick=()=>wbOpenScene(wb.sceneId,false);
  if(apiKey()){const epoch=wb.epoch;api('/api/v1/auth/info').then(info=>{if(epoch!==wb.epoch)return;const has=info.scene_subscriptions?.includes(wb.sceneId);$('#wb-intent-subscribe').disabled=!!has;$('#wb-intent-subscribe').textContent=has?'✓ 场景已授权':'开通当前场景';}).catch(()=>{});}
}
function wbResetResult(){$('#intent-result').innerHTML='<div class="step-card muted">提交业务目标，查看接入核验与文字结果。</div>';}
$('#wb-intent-scene').onchange=e=>{wbStopResultLoop();wb.sceneId=e.target.value;wb.epoch++;wbRenderIntent();wbResetResult();wbUpdateFeedback();};
$('#intent-send').onclick=()=>wbJob($('#intent-send'),null,async epoch=>{
  const text=$('#intent-input').value,scene=wbScene()||{id:'',name:'不指定场景'},mode='live';if(!text.trim())throw new Error('请填写业务目标');
  wbStopResultLoop();
  await wbUpdateFeedback();if(epoch!==wb.epoch)return;
  $('#intent-result').innerHTML='<div class="agent-block"><b>◌ NEF · 可信接入</b><p class="muted">请求处理中，等待服务回执…</p></div>';
  const endpoint=scene.id?'/api/v1/services/'+encodeURIComponent(scene.id)+'/intent':'/api/v1/intent';
  try{const res=await api(endpoint,{method:'POST',headers:{'X-NEF-Execution':mode},body:JSON.stringify({text})});if(epoch!==wb.epoch)return;wbIntentResult(res,scene,mode);if(scene.result_pull){await wbPollFeedback();wbStartResultLoop();}}
  catch(e){if(epoch!==wb.epoch)return;wbIntentResult(e.data||{},scene,mode,e);}
});
function wbIntentResult(res,scene,mode,error){
  const auth=res.nef_auth||res.detail?.nef_auth;const receipt=NefStory.receipt(res);
  $('#intent-result').innerHTML=`<h3 class="sec">① NEF 可信接入 · 场景授权</h3><div id="wb-intent-auth"></div><div class="agent-block wb-intent-route"><b>② ${mode==='demo'?'场景演示服务':'网络侧意图接收方'}</b><div class="kv"><b>开放场景</b>${esc(scene.name)}</div><div class="kv"><b>交付方式</b>${mode==='demo'?'演示响应 · 不发送至网络内部':'原文转发 · 网络侧解析与执行'}</div></div><h3 class="sec">③ 业务结果 <span class="method-chip">${esc(error?'未获得结果':receipt.badge)}</span></h3><div id="wb-intent-text" class="agent-block wb-business-text">${esc(error?wbMessage(error):NefStory.businessResult(res))}</div><details><summary>接口原始回执</summary><pre>${esc(jfmt(res))}</pre></details>`;
  if(auth)renderAuthPipeline($('#wb-intent-auth'),auth,null);
  else $('#wb-intent-auth').innerHTML='<div class="step-card muted">未收到鉴权回执</div>';
  if(mode==='demo'&&!error){$('#wb-feedback-text').textContent=res.demo_result?.text||'演示结果';$('#wb-feedback-data').textContent=jfmt(res.demo_result?.data||{});$('#wb-feedback-note').textContent='演示数据 · 非现场回传';}
}
async function wbLoadNetwork(){
  if(wb.networkBusy){wb.networkPending=true;return;}wb.networkBusy=true;const epoch=wb.epoch;
  try{
    wb.networkError='';
    const response=await fetch('/api/v1/network/market',{cache:'no-store'});if(!response.ok)throw new Error('已发布能力读取失败');
    const market=await response.json();
    if(epoch!==wb.epoch)return;
    wb.market=market.items;
    if(!apiKey()){wb.catalog=[];wb.servers=[];wb.packages=[];wb.toolSubscriptions=[];wb.networkStatus='not_configured';wbRenderNetwork();return;}
    const [c,s,p,t]=await Promise.all(['/catalog','/servers','/packages','/market/subscriptions'].map(x=>api('/api/v1/network'+x)));if(epoch!==wb.epoch)return;
    wb.catalog=c.items;wb.networkStatus=c.status;wb.servers=s.servers;wb.packages=p.packages;wb.toolSubscriptions=t.subscriptions;wbRenderNetwork();
  }finally{wb.networkBusy=false;if(wb.networkPending){wb.networkPending=false;wbLoadNetwork().catch(wbError);}}
}
function wbRenderNetwork(){
  const signature=jfmt([current,wb.networkStatus,wb.networkError,wb.catalog,wb.market,wb.servers,wb.packages,wb.toolSubscriptions]);
  if(wb.networkRenderSignature===signature)return;wb.networkRenderSignature=signature;
  if($('#wb-af-count'))$('#wb-af-count').textContent=new Set(wb.market.filter(x=>x.source==='AF').map(x=>x.server_id)).size;
  const items=wb.market;
  const groups=[...new Set(items.map(x=>x.kind==='package'?'package':x.toolType||'third-party tool'))];
  $('#wb-network-market').innerHTML=groups.map(group=>'<div class="cat-title"><span class="cat-dot" style="background:#f0883e"></span>'+esc(group==='package'?'自助编排套餐':wbToolType(group))+'</div><div class="tile-grid">'+items.map((x,i)=>({x,i})).filter(({x})=>(x.kind==='package'?'package':x.toolType||'third-party tool')===group).map(({x,i})=>`<button class="tile wb-network-item" data-net-item="${i}"><div class="ticon">${wbToolIcon(x)}</div><div class="tname" title="${esc(x.name)}">${esc(x.name)}</div><span class="wb-standard-label">${esc(x.serverName||x.provider||(x.kind==='package'?'自助编排套餐':'外部能力'))}</span><p class="wb-tile-description">${esc(x.description||'查看能力详情')}</p><div class="tfoot"><span class="cat-dot" style="background:#f0883e;width:7px;height:7px;margin:0"></span><span class="tprice">${x.kind==='package'?'组合套餐':wb.toolSubscriptions.some(t=>t.id===x.id)?'已订阅 · 演示免费':'演示免费 · 点击订阅'}</span></div></button>`).join('')+'</div>').join('');
  $$('#wb-network-market [data-net-item]').forEach(b=>b.onclick=()=>wbShowNetworkTool(items[Number(b.dataset.netItem)].id));
  $('#wb-server-list').innerHTML=wb.servers.map(s=>{
    const published=s.publication_status==='published',busy=['discovering'].includes(s.discovery_status)||s.sync_status==='syncing';
    const retry=(published&& !['synced','not_required'].includes(s.sync_status))||(!published&&s.trf_may_exist);
    return `<article class="step-card" data-server-id="${esc(s.id)}"><div class="wb-record-head"><b>🚙 ${esc(s.serverName||s.name)}</b><span class="method-chip">${published?'已发布':s.publication_status==='unpublished'?'已取消发布':'未发布'}</span><span class="method-chip">${esc(wbStatus(s.discovery_status))} · ${s.tools.length} 个工具</span></div><p class="muted">${esc(s.description||'')}</p><code class="wb-record-url">${esc(s.url)}</code><div class="wb-record-actions"><button data-discover="${esc(s.id)}" ${published||busy?'disabled':''}>重新发现工具</button><button class="${published?'':'primary'}" data-publish-server="${esc(s.id)}" data-action="${published?'unpublish':'publish'}" ${busy||(!published&&(!s.tools.length||s.discovery_status!=='discovered'))?'disabled':''}>${published?'取消发布':'发布'}</button>${!published?`<button class="wb-delete-record" data-delete-server="${esc(s.id)}" ${busy||s.trf_may_exist?'disabled':''} title="${s.trf_may_exist?'请先完成 TRF 撤回，再删除记录':'删除本地登记'}">删除记录</button>`:''}</div><p class="muted wb-sync-note" role="status">${esc(s.sync_note||'未发布；发现工具后可发布，或删除这条记录。')}</p>${retry?`<button class="wb-sync-retry" data-retry-server="${esc(s.id)}" data-action="${published?'publish':'unpublish'}" ${busy?'disabled':''}>重试 TRF ${published?'登记':'撤回'}</button>`:''}<div>${s.tools.map(t=>`<details class="wb-tool"><summary>${wbToolIcon(t)} <b>${esc(t.name)}</b> · ${esc(t.description||'MCP 工具')}</summary><pre>${esc(jfmt(t.inputSchema))}</pre></details>`).join('')||'<p class="muted">尚未发现可用工具</p>'}</div></article>`;
  }).join('')||'<p class="muted">填入地址并连接后，工具会显示在这里。</p>';
  $$('#wb-server-list [data-discover]').forEach(b=>b.onclick=()=>wbServerAction(b,b.dataset.discover,'discover'));
  $$('#wb-server-list [data-publish-server]').forEach(b=>b.onclick=()=>wbServerAction(b,b.dataset.publishServer,b.dataset.action));
  $$('#wb-server-list [data-retry-server]').forEach(b=>b.onclick=()=>wbServerAction(b,b.dataset.retryServer,b.dataset.action));
  $$('#wb-server-list [data-delete-server]').forEach(b=>b.onclick=()=>wbDeleteServer(b.dataset.deleteServer));
  if(wbActive()==='composer')wbRenderPool();loadPipeList();
}
async function wbServerAction(b,id,action){
  await wbJob(b,$('#wb-register-message'),async epoch=>{try{const r=await api('/api/v1/network/servers/'+encodeURIComponent(id)+'/'+action,{method:'POST'});if(epoch!==wb.epoch)return;await wbLoadNetwork();return action==='discover'?'已连接并发现工具，点击发布后在首页展示。':r.sync_note||'发布状态已更新';}catch(e){if(epoch===wb.epoch)await wbLoadNetwork().catch(()=>{});throw e;}});
}
function wbToolIcon(tool){const name=(tool.name||'')+' '+(tool.description||'');return /巡检|patrol|robot|rover/i.test(name)?'🚙':/检测|视觉|detect|vision|camera/i.test(name)?'👁️':/追踪|track|定位|position/i.test(name)?'📍':/告警|异常|alert/i.test(name)?'🔔':tool.kind==='package'?'📦':'🔧';}
function wbToolType(type){return {'nf tool':'网络功能能力','computing tool':'计算能力','sensing tool':'感知能力','third-party tool':'第三方扩展能力'}[type]||'其他扩展能力';}
function wbDeleteServer(id){
  const record=wb.servers.find(s=>s.id===id);if(!record)return;
  showModal(`<h2>删除「${esc(record.serverName||record.name)}」</h2><p>删除这条未发布的本地登记及其发现结果。</p><div class="wb-modal-actions"><button id="wb-keep-server">保留</button><button id="wb-confirm-delete-server" class="wb-delete-record">删除记录</button></div><p id="wb-delete-message" role="status"></p>`);
  $('#wb-keep-server').onclick=hideModal;
  $('#wb-confirm-delete-server').onclick=()=>wbJob($('#wb-confirm-delete-server'),$('#wb-delete-message'),async epoch=>{
    await api('/api/v1/network/servers/'+encodeURIComponent(id),{method:'DELETE'});
    if(epoch!==wb.epoch)return;hideModal();await wbLoadNetwork();$('#wb-register-message').textContent='已删除记录';
  });
}
function wbShowNetworkTool(id,notice=''){
  const subscription=wb.toolSubscriptions.find(t=>t.id===id),item=subscription||wb.market.find(t=>t.id===id);if(!item)return;
  const isTool=!!item.server_id,subscribed=!!subscription;
  const available=subscription?subscription.available:wb.market.some(t=>t.id===id);
  showModal(`<div id="wb-tool-detail"><h2>${wbToolIcon(item)} ${esc(item.name)}</h2><p>${esc(item.description||'服务提供方尚未填写说明')}</p><p class="muted">提供服务：${esc(item.serverName||item.provider||'自助编排套餐')}</p>${isTool?`<p class="muted">演示免费订阅 · 按账号记录，PRO/MAX 不自动开通第三方工具。</p><p id="wb-tool-state">${subscribed?'已订阅':'尚未订阅'}${!available?' · 提供方已下架，暂不可调用':''}</p>`:'<p class="muted">套餐定义展示，尚未接入此类套餐的订购与执行。</p>'}${item.inputSchema?`<details><summary>调用参数</summary><pre>${esc(jfmt(item.inputSchema))}</pre></details>`:''}<div class="wb-modal-actions"><button id="wb-close-detail">关闭</button>${isTool?(subscribed?`<button id="wb-unsubscribe-tool">取消订阅</button><button id="wb-use-tool" class="primary" ${available?'':'disabled'}>去 MCP 调用</button>`:`<button id="wb-subscribe-tool" class="success" ${available?'':'disabled'}>${apiKey()?'订阅工具 · 演示免费':'登录后订阅'}</button>`):''}</div><p id="wb-tool-message" role="status">${esc(notice)}</p></div>`);
  $('#wb-close-detail').onclick=hideModal;
  if($('#wb-subscribe-tool'))$('#wb-subscribe-tool').onclick=()=>wbChangeToolSubscription(id,true);
  if($('#wb-unsubscribe-tool'))$('#wb-unsubscribe-tool').onclick=()=>wbChangeToolSubscription(id,false);
  if($('#wb-use-tool'))$('#wb-use-tool').onclick=()=>wbUseNetworkTool(item).catch(wbError);
}
async function wbChangeToolSubscription(id,subscribe){
  const detail=$('#wb-tool-detail'),button=$(subscribe?'#wb-subscribe-tool':'#wb-unsubscribe-tool'),useButton=$('#wb-use-tool');
  await wbJob(button,$('#wb-tool-message'),async epoch=>{
    if(useButton)useButton.disabled=true;
    await api('/api/v1/network/market/subscriptions',{method:subscribe?'POST':'DELETE',body:JSON.stringify({tool_id:id})});
    if(epoch!==wb.epoch)return;
    const result=await api('/api/v1/network/market/subscriptions');if(epoch!==wb.epoch)return;
    wb.toolSubscriptions=result.subscriptions;wbRenderNetwork();wbMcp.reset();
    if(wbActive()==='subs')await renderSubs();
    if(epoch!==wb.epoch)return;
    if(detail===$('#wb-tool-detail')&&$('#modal-bg').classList.contains('show')){
      if(wb.market.some(t=>t.id===id)||wb.toolSubscriptions.some(t=>t.id===id))wbShowNetworkTool(id,subscribe?'已为当前账号订阅，可前往 MCP 调用。':'已取消订阅，后续调用将被拒绝。');
      else{hideModal();toast('已取消订阅');}
    }
  });
  if(useButton?.isConnected)useButton.disabled=!wb.toolSubscriptions.some(t=>t.id===id&&t.available);
}
async function wbUseNetworkTool(item){
  hideModal();activateTab('mcp',true);const epoch=wb.epoch;
  await $('#mcp-list-btn').onclick();
  if(epoch!==wb.epoch)return;
  const tool=wbMcp.state.tools.find(t=>t.name===item.mcp_name);
  if(!tool)throw new Error('该工具当前不可发现，请确认提供方仍已发布');
  $('#mcp-tool-select').value=tool.name;$('#mcp-tool-select').onchange();
}
function wbRenderToolSubscriptions(info,el){
  wb.toolSubscriptions=info.external_tool_subscriptions||[];
  el.insertAdjacentHTML('beforeend',`<h3 class="sec">第三方工具订阅（${wb.toolSubscriptions.length}）</h3><p class="muted">演示免费，不增加估算月费用。订阅按账号独立记录；提供方下架后暂停调用。</p><div class="grid">${wb.toolSubscriptions.map(t=>`<button class="card wb-subs-cap" data-subs-tool="${esc(t.id)}"><b>${wbToolIcon(t)} ${esc(t.name)}</b><span class="method-chip">${t.available?'已订阅':'已下架 · 暂不可用'}</span><p>${esc(t.description)}</p><small class="muted">${esc(t.serverName)}</small><small class="wb-cap-hint">查看工具 / 管理订阅 →</small></button>`).join('')||'<p class="muted">尚未订阅第三方工具，可到能力超市选择。</p>'}</div>`);
  el.querySelectorAll('[data-subs-tool]').forEach(b=>b.onclick=()=>wbShowNetworkTool(b.dataset.subsTool));
}
$('#wb-register-server').onclick=()=>wbJob($('#wb-register-server'),$('#wb-register-message'),async epoch=>{
  const body={serverName:$('#wb-server-name').value.trim(),description:$('#wb-server-description').value.trim(),url:$('#wb-server-url').value.trim()};
  if(!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(body.serverName))throw new Error('服务名称请使用英文字母、数字、点、下划线或短横线，最多128个字符');
  if(!body.description)throw new Error('请填写服务描述');
  if(!body.url)throw new Error('请填写巡检小车的 MCP 地址');
  try{const record=await api('/api/v1/network/servers',{method:'POST',body:JSON.stringify(body)});if(epoch!==wb.epoch)return;await api('/api/v1/network/servers/'+encodeURIComponent(record.id)+'/discover',{method:'POST'});return '已连接并发现工具，确认后点击发布。';}
  finally{if(epoch===wb.epoch)await wbLoadNetwork();}
});
$('#wb-refresh-trf').onclick=()=>wbJob($('#wb-refresh-trf'),$('#wb-trf-status'),async epoch=>{
  $('#wb-trf-servers').innerHTML='';
  const result=await api('/api/v1/network/trf/servers');if(epoch!==wb.epoch)return;
  if(result.status==='not_configured')return 'TRF 地址未配置';
  const servers=result.servers||[],types=['nf tool','computing tool','sensing tool','third-party tool',...new Set(servers.map(s=>s.toolType).filter(t=>!['nf tool','computing tool','sensing tool','third-party tool'].includes(t)))];
  $('#wb-trf-servers').innerHTML=types.map(type=>`<h4>${esc(wbToolType(type))} <small>${esc(type)}</small></h4>`+servers.filter(s=>s.toolType===type).map(s=>`<article class="wb-trf-row"><b>${esc(s.serverName)}</b> <span class="method-chip">${esc(s.serverStatus)}</span><p>${esc(s.description)}</p><code>${esc(s.url)}</code></article>`).join('')).join('');
  return '已读取 '+servers.length+' 个 MCP 服务登记；尚未作为工具开放';
});

function wbSources(){const rows=[...CAPS.filter(c=>c.status==='available'),...wb.catalog.filter(c=>c.kind==='tool'),...wb.servers.flatMap(s=>s.discovery_status==='discovered'?s.tools.map(t=>({id:s.id+':'+t.name,name:t.name})):[]),...wb.toolSubscriptions.filter(t=>t.available)];return [...new Map(rows.map(x=>[x.id,x])).values()];}
function wbRenderPool(){
  $('#cap-pool').innerHTML=wbSources().map(c=>`<button class="pill" draggable="true" data-cap="${esc(c.id)}">⠿ ${esc(c.name)}</button>`).join('');bindDrag();
  $$('#cap-pool .pill').forEach(b=>b.onclick=()=>{if(pipeSteps.length>=12)return toast('每个套餐最多 12 个步骤',false);if(pipeSteps.includes(b.dataset.cap))return;pipeSteps.push(b.dataset.cap);renderPipe();});renderPipe();
}
async function renderComposer(){wbRenderPool();loadPipeList();await wbLoadNetwork().catch(wbError);}
function loadPipeList(){
  $('#pipe-list').innerHTML=wb.packages.map(p=>`<div class="step-card"><b>${esc(p.name)}</b><span class="method-chip">${p.publication_status==='published'?'已发布':'未发布'}</span><div class="kv"><b>步骤</b>${p.steps.map(s=>esc(wbSources().find(c=>c.id===s.capability_id)?.name||s.capability_id)).join(' → ')}</div><div class="wb-record-actions"><button class="primary" data-publish-package="${esc(p.id)}" data-action="${p.publication_status==='published'?'unpublish':'publish'}">${p.publication_status==='published'?'取消发布':'发布'}</button><button data-preview-package="${esc(p.id)}">查看 JSON</button></div><p class="muted">${esc(p.sync_note||'保存后需确认发布')}</p>${((p.publication_status==='published'&&!['synced','not_required'].includes(p.sync_status))||(p.publication_status!=='published'&&p.trf_may_exist))?`<button data-publish-package="${esc(p.id)}" data-action="${p.publication_status==='published'?'publish':'unpublish'}">重试 TRF 同步</button>`:''}</div>`).join('')||'<span class="muted">暂无场景套餐</span>';
  $$('#pipe-list [data-preview-package]').forEach(b=>b.onclick=()=>{$('#pipe-json').textContent=jfmt(wb.packages.find(p=>p.id===b.dataset.previewPackage));});
  $$('#pipe-list [data-publish-package]').forEach(b=>b.onclick=()=>wbJob(b,$('#pipe-run-result'),async epoch=>{const r=await api('/api/v1/network/packages/'+encodeURIComponent(b.dataset.publishPackage)+'/'+b.dataset.action,{method:'POST'});if(epoch!==wb.epoch)return;await wbLoadNetwork();return r.sync_note||'发布状态已更新';}));
}
/* REST retains original selection, generated parameter forms, request, authorization and response panes. */
function wbTrackingCap(){const s=wb.scenes.find(x=>x.id==='collaborative_tracking');return s?{id:'scene:collaborative_tracking',name:s.name,params:[{name:'device_id',type:'string',required:true,description:'协同终端',default:'terminal-01'},{name:'video_source',type:'string',required:true,description:'视频源引用',default:'camera-01'},{name:'target',type:'string',required:true,description:'追踪目标',default:'指定移动目标'}]}:null;}
function wbApiCap(){return $('#api-cap-select').value==='scene:collaborative_tracking'?wbTrackingCap():CAPS.find(c=>c.id===$('#api-cap-select').value);}
async function renderApiTab(){
  const caps=[wbTrackingCap(),...CAPS.filter(c=>c.status==='available')].filter(Boolean);const sel=$('#api-cap-select');const prev=sel.value;
  sel.innerHTML=caps.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');if(caps.some(c=>c.id===prev))sel.value=prev;
  sel.onchange=()=>{wb.epoch++;const c=wbApiCap();$('#api-params').innerHTML=c?paramForm(c,'apip'):'';$('#api-endpoint').textContent=c?.id.startsWith('scene:')?'/api/v1/services/collaborative_tracking/invoke':'/api/v1/capabilities/'+(c?.id||'')+'/invoke';$('#api-chain').innerHTML='<span class="method-chip">AF 已知接口</span> → <span class="method-chip">NEF · 权限与参数映射</span> → <span class="method-chip">网络服务</span>';$('#api-pipeline').innerHTML='';$('#api-req').textContent=$('#api-resp').textContent='--';wbUpdateFeedback();};sel.onchange();
}
$('#api-send').onclick=()=>wbJob($('#api-send'),null,async epoch=>{
  const cap=wbApiCap();if(!cap)throw new Error('请选择能力');const args=collectParams(cap,'apip');const endpoint=$('#api-endpoint').textContent;const mode='live';
  $('#api-req').textContent=jfmt({method:'POST',url:endpoint,headers:{Authorization:'Bearer <AF Key>','X-NEF-Execution':mode},body:args});$('#api-resp').textContent='请求处理中…';$('#api-pipeline').innerHTML='';
  try{const r=await api(endpoint,{method:'POST',headers:{'X-NEF-Execution':mode},body:JSON.stringify(args)});if(epoch!==wb.epoch)return;renderAuthPipeline($('#api-pipeline'),r.nef_auth,null);$('#api-resp').textContent=NefStory.receipt(r).badge+'\n'+NefStory.businessResult(r)+'\n\n'+jfmt(r);}
  catch(e){if(epoch!==wb.epoch)return;renderAuthPipeline($('#api-pipeline'),e.data?.detail?.nef_auth,null);$('#api-resp').textContent=wbMessage(e)+'\n'+jfmt(e.data||{});}
});
/* AF discovery still happens before tool selection, now within the original MCP pane. */
const wbMcp=NefMcp.createClient(async message=>{
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
  try{const r=await fetch('/mcp',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+apiKey(),'MCP-Protocol-Version':NefMcp.VERSION,'X-NEF-Execution':'live'},body:JSON.stringify(message),signal:controller.signal});if(!r.ok)throw new Error('MCP 连接失败 · HTTP '+r.status);if(!Object.hasOwn(message,'id')){if(r.status!==202)throw new Error('初始化通知未确认');return null;}return await r.json();}finally{clearTimeout(timer);}
},()=>{
  $('#wb-mcp-stages').textContent=wbMcp.state.error||({idle:'尚未连接',connecting:'initialize · 连接中',connected:'initialize ✓ · 等待 tools/list',discovering:'tools/list · 发现中',discovered:'tools/list ✓ · '+wbMcp.state.tools.length+' 项工具',selected:'工具已选用'}[wbMcp.state.phase]||wbMcp.state.phase);
  $('#mcp-call').disabled=!wbMcp.state.selected||wbMcp.state.busy||(wbMcp.state.selected?.name.startsWith('external_')&&!wbMcp.state.selected.subscribed);
});
function renderMcpTab(){wbMcp.reset();$('#mcp-tool-select').innerHTML='<option value="">先连接并发现工具</option>';$('#mcp-params').innerHTML='';$('#mcp-req').textContent=$('#mcp-resp').textContent='--';$('#mcp-pipeline').innerHTML='';wbUpdateFeedback();}
$('#mcp-list-btn').onclick=()=>wbJob($('#mcp-list-btn'),null,async epoch=>{
  wbMcp.reset();$('#mcp-tool-select').innerHTML='<option value="">正在发现…</option>';$('#mcp-params').innerHTML='';wbUpdateFeedback();await wbMcp.connect();if(wbMcp.state.error)throw new Error(wbMcp.state.error);await wbMcp.discover();if(epoch!==wb.epoch)return;if(wbMcp.state.error)throw new Error(wbMcp.state.error);
  $('#mcp-tool-select').innerHTML='<option value="">选择发现的工具</option>'+NefMcp.describeTools(wbMcp.state.tools,wb.scenes,CAPS).map(row=>`<option value="${esc(row.tool.name)}">${esc(row.title)} · ${esc(row.tool.name)}</option>`).join('');$('#mcp-req').textContent=wbMcp.state.trace.map(t=>jfmt(t.request)).join('\n\n');$('#mcp-resp').textContent=jfmt({tools:wbMcp.state.tools});wbUpdateFeedback();
});
$('#mcp-tool-select').onchange=()=>{wb.epoch++;const name=$('#mcp-tool-select').value;if(!name){wbMcp.state.selected=null;$('#mcp-params').innerHTML='';$('#mcp-call').disabled=true;wbUpdateFeedback();return;}wbMcp.select(name);const tool=wbMcp.state.selected;$('#mcp-pipeline').innerHTML='';$('#mcp-resp').textContent='--';if(!tool){$('#mcp-params').innerHTML='';wbUpdateFeedback();return;}
  $('#mcp-params').innerHTML=(tool.name.startsWith('external_')&&!tool.subscribed?'<p class="warn">当前账号尚未订阅，请到能力超市订阅此工具。</p>':'')+'<p class="muted">参数来自发现的 inputSchema</p>'+NefMcp.fields(tool).map((f,i)=>`<label for="wb-mcp-param-${i}">${esc(f.description)} ${f.required?'*':''}</label><input id="wb-mcp-param-${i}" data-mcp-param="${esc(f.name)}" placeholder="${esc(f.type)}" value="${esc(typeof f.schema.default==='object'?jfmt(f.schema.default):(f.schema.default??''))}">`).join('');wbUpdateFeedback();};
$('#mcp-call').onclick=()=>wbJob($('#mcp-call'),null,async epoch=>{
  const tool=wbMcp.state.selected;if(!tool)throw new Error('请先发现并选择工具');const values=Object.fromEntries($$('#mcp-params [data-mcp-param]').map(el=>[el.dataset.mcpParam,el.value]));const args=NefMcp.parseArguments(tool,values);const req={jsonrpc:'2.0',id:Date.now(),method:'tools/call',params:{name:tool.name,arguments:args}};
  $('#mcp-req').textContent=jfmt(req);$('#mcp-resp').textContent='调用中…';$('#mcp-pipeline').innerHTML='';
  try{const res=await api('/mcp',{method:'POST',headers:{'X-NEF-Execution':'live','MCP-Protocol-Version':NefMcp.VERSION},body:JSON.stringify(req)});if(epoch!==wb.epoch)return;if(res.error)throw new Error(res.error.message);if(res.id!==req.id)throw new Error('响应与本次请求不匹配');if(tool.name.startsWith('external_')){$('#mcp-resp').textContent=(res.result?.isError?'第三方工具返回错误':'已收到第三方工具回执')+'\n'+(res.result?.content||[]).filter(c=>c.type==='text').map(c=>c.text).join('\n')+'\n\n'+jfmt(res);return;}let inner;try{inner=JSON.parse(res.result.content.find(c=>c.type==='text').text);}catch{inner={summary:res.result?.content?.find(c=>c.type==='text')?.text};}renderAuthPipeline($('#mcp-pipeline'),inner?.nef_auth||inner?.detail?.nef_auth,null);$('#mcp-resp').textContent=(res.result?.isError?'工具执行未完成':NefStory.receipt(inner).badge)+'\n'+(res.result?.isError?wbMessage({data:{detail:inner}}):NefStory.businessResult(inner))+'\n\n'+jfmt(res);}
  catch(e){if(epoch===wb.epoch)$('#mcp-resp').textContent=wbMessage(e)+'\n'+jfmt(e.data||{});}
});
/* Shared scene feedback and private general channels, invocation panes only. */
function wbInvocation(){const tab=wbActive();if(tab==='intent')return {sceneId:wb.sceneId,mode:'live'};if(tab==='api')return {sceneId:$('#api-cap-select').value.startsWith('scene:')?'collaborative_tracking':'',mode:'live'};if(tab==='mcp'&&wbMcp.state.selected)return {sceneId:wb.scenes.find(s=>s.tool_name===wbMcp.state.selected.name)?.id||'',mode:'live'};return null;}
function wbClearFeedback(){wb.feedbackSignature='';$('#wb-feedback-text').textContent='等待回传';$('#wb-feedback-data').textContent='—';$('#wb-feedback-data-wrap').hidden=true;}
async function wbUpdateFeedback(){
  const epoch=wb.epoch;
  const inv=wbInvocation();$('#wb-feedback').hidden=!inv;
  if(!inv){wb.feedbackContext='';wb.access=null;wbClearFeedback();return;}
  const context=[current,inv.sceneId,inv.mode].join(':');
  if(wb.feedbackContext!==context){wb.feedbackContext=context;wb.channel='';wb.access=null;wbClearFeedback();}
  const demo=inv.mode==='demo';$('#wb-feedback-create').disabled=true;wbResultButton();
  $('#wb-feedback-note').textContent=demo?'演示模式 · 不接收现场回传':wbScene()?.result_pull?'发送业务目标后自动向现场拉取感知结果':'等待现场服务回传结果';
  if(inv.sceneId&&!demo){wb.channel='scene_'+inv.sceneId;await wbPollFeedback();}
  if(epoch!==wb.epoch||context!==wb.feedbackContext)return;
  if(!apiKey()||demo)return;
  try{
    const c=await api('/api/v1/services/'+encodeURIComponent(inv.sceneId||'general')+'/feedback-access',{method:'POST'});
    if(epoch!==wb.epoch||context!==wb.feedbackContext)return;
    wb.access=c;wb.channel=c.id;$('#wb-feedback-create').disabled=false;await wbPollFeedback();
  }catch(e){if(epoch===wb.epoch)$('#wb-feedback-note').textContent='接口暂不可用 · '+wbMessage(e);}
}
$('#wb-feedback-create').onclick=()=>{
  const c=wb.access;if(!c)return;
  const handoff=NefStory.feedbackHandoff(c,location.origin);
  showModal(`<h2>${esc(c.name)} · 回传地址</h2><label>回传地址${handoff.open_url?'（无需 Key）':''}</label><pre>POST ${esc(handoff.open_url||handoff.url)}</pre><label>文字结果 JSON</label><pre>${esc(jfmt(handoff.json_example))}</pre><details><summary>备用凭证接口</summary><pre>POST ${esc(handoff.url)}\nAuthorization: Bearer ${esc(c.receiver_key)}</pre></details><div class="wb-modal-actions"><button id="wb-source-copy">复制对接信息</button><button id="wb-source-close">关闭</button></div>`);
  $('#wb-source-close').onclick=hideModal;
  $('#wb-source-copy').onclick=async()=>{try{await navigator.clipboard.writeText(jfmt(handoff));toast('已复制');}catch{toast('剪贴板不可用，请手动复制',false);}};
};
async function wbPollFeedback(){
  const inv=wbInvocation();if(!inv||inv.mode!=='live'||!wb.channel||(!inv.sceneId&&!apiKey())||wb.feedbackBusy)return;wb.feedbackBusy=true;const epoch=wb.epoch,channel=wb.channel;
  try{let r;if(inv.sceneId){const response=await fetch('/api/v1/scene-feedback/'+encodeURIComponent(inv.sceneId),{cache:'no-store'});if(!response.ok)throw new Error('场景回传读取失败');r=await response.json();}else r=await api('/api/v1/exhibition/channels/'+encodeURIComponent(channel)+'/events');if(epoch!==wb.epoch||channel!==wb.channel)return;const sig=jfmt(r.events);if(sig===wb.feedbackSignature)return;wb.feedbackSignature=sig;
    if(r.events.length)$('#wb-feedback-note').textContent='已接收 '+r.events.length+' 条回传 · 场景级反馈';
    else {wbClearFeedback();$('#wb-feedback-note').textContent='等待现场服务回传结果';}
    const text=r.events.findLast(e=>e.kind==='status'),data=r.events.findLast(e=>e.kind==='data');
    $('#wb-feedback-text').textContent=text?[text.title,text.text].filter(Boolean).join('\n'):'等待回传';
    $('#wb-feedback-data').textContent=data?jfmt(data.data??data.text):'—';$('#wb-feedback-data-wrap').hidden=!data;
  }catch(e){if(epoch===wb.epoch)$('#wb-feedback-note').textContent='回传读取失败 · '+wbMessage(e);}finally{wb.feedbackBusy=false;}
}
function wbResultButton(){const inv=wbInvocation(),scene=wb.scenes.find(s=>s.id===inv?.sceneId);$('#wb-feedback-pull').hidden=!scene?.result_pull||inv?.mode!=='live';$('#wb-feedback-pull').disabled=!apiKey()||wb.resultBusy;}
function wbStopResultLoop(){clearTimeout(wb.resultTimer);wb.resultTimer=null;wb.resultGeneration=(wb.resultGeneration||0)+1;}
function wbStartResultLoop(){
  wbStopResultLoop();const epoch=wb.epoch,generation=wb.resultGeneration;
  const tick=async()=>{if(epoch!==wb.epoch||generation!==wb.resultGeneration)return;await wbPullResult();if(epoch===wb.epoch&&generation===wb.resultGeneration&&apiKey())wb.resultTimer=setTimeout(tick,3000);};
  wb.resultTimer=setTimeout(tick,3000);
}
async function wbPullResult(){
  const inv=wbInvocation(),scene=wb.scenes.find(s=>s.id===inv?.sceneId),epoch=wb.epoch;if(wb.resultBusy||!apiKey()||!scene?.result_pull||inv.mode!=='live')return;
  wb.resultBusy=true;wbResultButton();
  try{const result=await api('/api/v1/services/'+encodeURIComponent(scene.id)+'/result',{method:'POST'});if(epoch!==wb.epoch)return;
    if(result.status==='stored')await wbPollFeedback();else if(result.status==='unavailable')$('#wb-feedback-note').textContent='感知结果暂不可用：'+wbMessage(result);
  }catch(e){if(epoch===wb.epoch)$('#wb-feedback-note').textContent='感知结果读取失败：'+wbMessage(e);}finally{wb.resultBusy=false;wbResultButton();}
}
$('#wb-feedback-pull').onclick=wbPullResult;
function wbTabChanged(name){if($('#wb-tool-detail'))hideModal();wbStopResultLoop();wb.epoch++;window.wbCatalogClose?.();if(name!=='mcp')wbMcp.reset();wbUpdateFeedback();}
async function refreshAll(){
  if($('#wb-tool-detail'))hideModal();
  wbStopResultLoop();
  $('#wb-trf-servers').innerHTML='';$('#wb-trf-status').textContent='尚未查询';
  wb.epoch++;window.wbCatalogClose?.();wbMcp.reset();wb.catalog=[];wb.market=[];wb.toolSubscriptions=[];wb.servers=[];wb.packages=[];wb.channels=[];wb.channel='';wb.feedbackContext='';pipeSteps.length=0;window.wbComposerReset?.();wbClearFeedback();wbResetResult();$('#wb-register-message').textContent='';$('#purchase-notice').hidden=true;renderAccounts();wbRenderNetwork();
  try{await loadMarket();if(wbActive()==='subs')await renderSubs();if(wbActive()==='intent')wbRenderIntent();if(wbActive()==='api')await renderApiTab();if(wbActive()==='mcp')renderMcpTab();if(wbActive()==='composer')await renderComposer();await wbUpdateFeedback();}catch(e){wbError(e);}
}
window.addEventListener('pagehide',()=>{wbStopResultLoop();wb.epoch++;});
setInterval(wbPollFeedback,2000);
setInterval(()=>{if(['market','afreg'].includes(wbActive()))wbLoadNetwork().catch(wbError);},30000);
checkInstance().then(purchaseBootstrap).catch(wbError).then(refreshAll).then(()=>{const hash=location.hash.slice(1);if(hash&&!activateTab(hash,false))activateTab('market',true);});
