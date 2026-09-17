/* Incremental integration for the original workbench. Native tabs, forms and drag/drop remain in index.html. */
const wb={networkBusy:false,networkError:'',access:null,scenes:[],sceneId:'',catalog:[],servers:[],packages:[],networkStatus:'not_configured',epoch:0,channels:[],channel:'',mediaUrl:'',mediaId:'',feedbackKey:'',feedbackContext:'',feedbackSignature:'',feedbackBusy:false};
const wbStatus=x=>({not_configured:'待对接',not_discovered:'未发现',discovering:'发现中',discovered:'已发现',pending:'待同步',submitted:'已提交 · 待确认',synced:'已同步',syncing:'同步中',calling:'转发中',returned:'已收到 AF 回执',tool_error:'AF 返回工具错误',failed:'失败'}[x]||x||'待处理');
function wbMessage(e){const d=e?.data?.detail??e?.detail;return typeof d==='string'?d:d?.message||e?.message||'请求未完成';}
function wbError(e){toast(wbMessage(e),false);}
function wbActive(){return document.querySelector('#tabs .active')?.dataset.tab||'market';}
function wbScene(){return wb.scenes.find(s=>s.id===wb.sceneId);}
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
  wbRenderSceneSubscriptions(info);
  if(wbActive()==='intent')wbRenderIntent();
}
function wbRenderSceneSubscriptions(info){
  const owned=new Set(info?.scene_subscriptions||[]);
  $('#wb-scene-subs').innerHTML='<h3 class="sec">场景订阅权益</h3><div class="wb-scene-grid">'+wb.scenes.map(s=>`<div class="step-card"><b>${esc(s.name)}</b><p class="muted">场景入口 · 调用时核验使用权</p><button data-subs-scene="${esc(s.id)}" class="${owned.has(s.id)?'primary':'success'}">${owned.has(s.id)?'已开通 · 进入场景':'开通场景'}</button></div>`).join('')+'</div>';
  $$('#wb-scene-subs [data-subs-scene]').forEach(b=>b.onclick=()=>wbOpenScene(b.dataset.subsScene,owned.has(b.dataset.subsScene)));
}
function wbOpenScene(id,owned){
  if(!apiKey())return toast('请先在顶栏注册账号',false);
  const s=wb.scenes.find(x=>x.id===id);if(!s)return;
  if(owned){wb.sceneId=id;activateTab('intent',true);return;}
  showModal(`<h2>开通「${esc(s.name)}」</h2><p class="muted">开通后获得该场景的调用权益。当前为演示订阅，不产生真实费用。</p>${purchaseCapabilitySelector((s.provenance?.components||[]).map(c=>c.capability_id))}<div class="wb-modal-actions"><button id="wb-cancel">取消</button><button class="success" id="wb-confirm-scene">开通并进入</button></div><p id="wb-sub-message" class="muted"></p>`);
  $('#wb-cancel').onclick=hideModal;$('#wb-confirm-scene').onclick=()=>wbJob($('#wb-confirm-scene'),$('#wb-sub-message'),async epoch=>{const result=await api('/api/v1/services/'+encodeURIComponent(id)+'/subscribe',{method:'POST',body:JSON.stringify({network_capability_ids:purchaseCapabilityIds()})});if(epoch!==wb.epoch)return;wb.sceneId=id;hideModal();purchaseNotice(result.notification);await wbLoadScenes();activateTab('intent',true);return '已开通';});
}
function wbRenderIntent(){
  const sel=$('#wb-intent-scene');sel.innerHTML='<option value="">不指定场景</option>'+wb.scenes.map(s=>`<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('');sel.value=wb.sceneId;
  $('#wb-intent-subscribe').hidden=!wb.sceneId;
  $('#wb-intent-subscribe').onclick=()=>wbOpenScene(wb.sceneId,false);
  if(apiKey()){const epoch=wb.epoch;api('/api/v1/auth/info').then(info=>{if(epoch!==wb.epoch)return;const has=info.scene_subscriptions?.includes(wb.sceneId);$('#wb-intent-subscribe').disabled=!!has;$('#wb-intent-subscribe').textContent=has?'✓ 场景已授权':'开通当前场景';}).catch(()=>{});}
}
function wbResetResult(){$('#intent-result').innerHTML='<div class="step-card muted">提交业务目标，查看接入核验与文字结果。</div>';}
$('#wb-intent-scene').onchange=e=>{wb.sceneId=e.target.value;wb.epoch++;wbRenderIntent();wbResetResult();wbUpdateFeedback();};
$('#intent-send').onclick=()=>wbJob($('#intent-send'),null,async epoch=>{
  const text=$('#intent-input').value,scene=wbScene()||{id:'',name:'不指定场景'},mode='live';if(!text.trim())throw new Error('请填写业务目标');
  await wbUpdateFeedback();if(epoch!==wb.epoch)return;
  $('#intent-result').innerHTML='<div class="agent-block"><b>◌ NEF · 可信接入</b><p class="muted">请求处理中，等待服务回执…</p></div>';
  const endpoint=scene.id?'/api/v1/services/'+encodeURIComponent(scene.id)+'/intent':'/api/v1/intent';
  try{const res=await api(endpoint,{method:'POST',headers:{'X-NEF-Execution':mode},body:JSON.stringify({text})});if(epoch!==wb.epoch)return;wbIntentResult(res,scene,mode);}
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
  if(!apiKey()){wb.catalog=[];wb.servers=[];wb.packages=[];wb.networkStatus='not_configured';wbRenderNetwork();return;}
  if(wb.networkBusy){wb.networkPending=true;return;}wb.networkBusy=true;const epoch=wb.epoch;
  try{
    wb.networkError='';
    try{await api('/api/v1/network/catalog/refresh',{method:'POST'});}catch(e){wb.networkError=wbMessage(e);}
    if(epoch!==wb.epoch)return;
    const [c,s,p]=await Promise.all(['/catalog','/servers','/packages'].map(x=>api('/api/v1/network'+x)));if(epoch!==wb.epoch)return;
    wb.catalog=c.items;wb.networkStatus=c.status;wb.servers=s.servers;wb.packages=p.packages;wbRenderNetwork();
  }finally{wb.networkBusy=false;if(wb.networkPending){wb.networkPending=false;wbLoadNetwork().catch(wbError);}}
}
function wbRenderNetwork(){
  const signature=jfmt([current,wb.networkStatus,wb.networkError,wb.catalog,wb.servers,wb.packages]);
  if(wb.networkRenderSignature===signature)return;wb.networkRenderSignature=signature;
  if($('#wb-af-count'))$('#wb-af-count').textContent=wb.servers.length;
  $('#wb-catalog-status').textContent=apiKey()?(wb.networkError&&wb.networkStatus!=='not_configured'?'同步未完成':wbStatus(wb.networkStatus))+' · '+wb.catalog.length+' 条网络记录':'接入账号后自动同步';
  $('#wb-catalog-status').title=wb.networkError||'进入页面及每 30 秒自动检查网络目录';
  const afTools=wb.servers.flatMap(server=>(server.tools?.length?server.tools:[{name:server.name,description:'MCP Server · '+wbStatus(server.discovery_status),_server:true}]).map(tool=>({id:server.id+':'+tool.name,name:tool.name,description:tool.description||'AF 注册的 MCP Tool',kind:tool._server?'server':'tool',source:'AF',source_account:server.source_account||current,server:server.name,discovery_status:server.discovery_status,sync_status:server.sync_status,inputSchema:tool.inputSchema})));
  const items=wb.catalog.concat(wb.packages.map(p=>({...p,kind:'package',source:'local'})),afTools);
  $('#wb-network-market').innerHTML=items.length?'<h3 class="sec">网络与自建目录</h3><div class="tile-grid">'+items.map((x,i)=>`<button class="tile wb-network-item" data-net-item="${i}"><div class="tname">${esc(x.name)}</div><span class="muted">${x.kind==='package'?'场景套餐':x.kind==='server'?'MCP Server':'工具'} · ${x.source==='local'?'自助编排 · '+wbStatus(x.sync_status):x.source==='AF'?'AF · '+(x.source_account||'外部提供方')+' · '+(x.sync_status?wbStatus(x.sync_status):'网络目录'):'TRF / ARF'}</span></button>`).join('')+'</div>':'';
  $$('#wb-network-market [data-net-item]').forEach(b=>b.onclick=()=>{const item=items[Number(b.dataset.netItem)];showModal(`<h2>${esc(item.name)}</h2><p class="muted">能力来源与服务信息</p><pre>${esc(jfmt(item))}</pre><button id="wb-close-detail">关闭</button>`);$('#wb-close-detail').onclick=hideModal;});
  $('#wb-server-list').innerHTML=wb.servers.map(s=>`<article class="step-card"><div class="wb-record-head"><b>${esc(s.name)}</b><span class="method-chip">来源：AF · ${esc(s.source_account||current)}</span><span class="method-chip">NEF 已登记</span><span class="method-chip">${esc(wbStatus(s.discovery_status))} · ${s.tools.length} tools</span><span class="method-chip">${esc(wbStatus(s.sync_status))}</span></div><div class="wb-route-detail"><label>AF 原始服务 · 由 NEF 连接</label><code>${esc(s.url)}</code><label>网络侧调用入口 · 经过 NEF</label><code>${esc(s.gateway_path||'服务更新后可用')}</code></div><p class="muted">${esc(s.description||'')}</p><div class="wb-record-actions"><button class="primary" data-discover="${esc(s.id)}">连接并发现工具</button><button data-preview-server="${esc(s.id)}">查看网络登记内容</button><button data-sync-server="${esc(s.id)}">同步 ARF / TRF</button></div><div>${s.discovery_status==='discovered'?s.tools.map(t=>`<details class="wb-tool"><summary><b>${esc(t.name)}</b> · ${esc(t.description||'MCP Tool')}</summary><pre>${esc(jfmt(t.inputSchema))}</pre></details>`).join(''):'<p class="muted">尚无有效工具发现结果</p>'}</div><div class="wb-call-state">${s.last_call?`<b>最近网络调用</b> ${esc(s.last_call.caller)} → NEF → ${esc(s.last_call.tool)}<span class="method-chip">${esc(wbStatus(s.last_call.status))}</span>`:'等待网络侧调用 · 不绕过 NEF'}</div><p data-server-message="${esc(s.id)}" class="muted" role="status"></p></article>`).join('')||'<p class="muted">暂无登记的 MCP Server</p>';
  $$('#wb-server-list [data-preview-server]').forEach(b=>b.onclick=()=>wbJob(b,null,async epoch=>{const payload=await api('/api/v1/network/servers/'+encodeURIComponent(b.dataset.previewServer)+'/publication');if(epoch!==wb.epoch)return;showModal(`<h2>发布至网络内部 ARF / TRF</h2><p class="muted">工具声明、AF 来源和 NEF 的 MCP 入口。AF 原始地址与凭证不作为网络调用入口发布。</p><pre>${esc(jfmt(payload))}</pre><button id="wb-publication-close">关闭</button>`);$('#wb-publication-close').onclick=hideModal;}));
  $$('#wb-server-list [data-discover]').forEach(b=>b.onclick=()=>wbServerAction(b,b.dataset.discover,'discover'));
  $$('#wb-server-list [data-sync-server]').forEach(b=>b.onclick=()=>wbServerAction(b,b.dataset.syncServer,'sync'));
  if(wbActive()==='composer')wbRenderPool();loadPipeList();
}
async function wbServerAction(b,id,action){
  await wbJob(b,$('#wb-register-message'),async epoch=>{try{const r=await api('/api/v1/network/servers/'+encodeURIComponent(id)+'/'+action,{method:'POST'});if(epoch!==wb.epoch)return;await wbLoadNetwork();return action==='discover'?'已完成 MCP 握手与工具发现，展开工具可查看参数声明。':'注册发布：'+wbStatus(r.sync_status);}catch(e){if(epoch===wb.epoch)await wbLoadNetwork().catch(()=>{});throw e;}});
}
$('#wb-register-server').onclick=()=>wbJob($('#wb-register-server'),$('#wb-register-message'),async epoch=>{let body;try{body=JSON.parse($('#wb-server-json').value);}catch{throw new Error('JSON 格式有误');}await api('/api/v1/network/servers',{method:'POST',body:JSON.stringify(body)});if(epoch!==wb.epoch)return;await wbLoadNetwork();return '已登记。下一步：连接并发现工具。';});
$('#wb-reload-servers').onclick=()=>wbLoadNetwork().catch(wbError);

function wbSources(){const rows=[...CAPS.filter(c=>c.status==='available'),...wb.catalog.filter(c=>c.kind==='tool'),...wb.servers.flatMap(s=>s.discovery_status==='discovered'?s.tools.map(t=>({id:s.id+':'+t.name,name:t.name})):[])];return [...new Map(rows.map(x=>[x.id,x])).values()];}
function wbRenderPool(){
  $('#cap-pool').innerHTML=wbSources().map(c=>`<button class="pill" draggable="true" data-cap="${esc(c.id)}">⠿ ${esc(c.name)}</button>`).join('');bindDrag();
  $$('#cap-pool .pill').forEach(b=>b.onclick=()=>{if(pipeSteps.length>=12)return toast('每个套餐最多 12 个步骤',false);if(pipeSteps.includes(b.dataset.cap))return;pipeSteps.push(b.dataset.cap);renderPipe();});renderPipe();
}
async function renderComposer(){wbRenderPool();loadPipeList();await wbLoadNetwork().catch(wbError);}
function loadPipeList(){
  $('#pipe-list').innerHTML=wb.packages.map(p=>`<div class="step-card"><b>${esc(p.name)}</b><span class="method-chip">${esc(wbStatus(p.sync_status))}</span><div class="kv"><b>步骤</b>${p.steps.map(s=>esc(wbSources().find(c=>c.id===s.capability_id)?.name||s.capability_id)).join(' → ')}</div><div class="wb-record-actions"><button class="primary" data-publish-package="${esc(p.id)}">同步 TRF / ARF</button><button data-preview-package="${esc(p.id)}">查看 JSON</button></div></div>`).join('')||'<span class="muted">暂无场景套餐</span>';
  $$('#pipe-list [data-preview-package]').forEach(b=>b.onclick=()=>{$('#pipe-json').textContent=jfmt(wb.packages.find(p=>p.id===b.dataset.previewPackage));});
  $$('#pipe-list [data-publish-package]').forEach(b=>b.onclick=()=>wbJob(b,$('#pipe-run-result'),async epoch=>{const r=await api('/api/v1/network/packages/'+encodeURIComponent(b.dataset.publishPackage)+'/sync',{method:'POST'});if(epoch!==wb.epoch)return;await wbLoadNetwork();return '网络交付：'+wbStatus(r.sync_status)+'\n'+jfmt(r);}));
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
  $('#mcp-call').disabled=!wbMcp.state.selected||wbMcp.state.busy;
});
function renderMcpTab(){wbMcp.reset();$('#mcp-tool-select').innerHTML='<option value="">先连接并发现工具</option>';$('#mcp-params').innerHTML='';$('#mcp-req').textContent=$('#mcp-resp').textContent='--';$('#mcp-pipeline').innerHTML='';wbUpdateFeedback();}
$('#mcp-list-btn').onclick=()=>wbJob($('#mcp-list-btn'),null,async epoch=>{
  wbMcp.reset();$('#mcp-tool-select').innerHTML='<option value="">正在发现…</option>';$('#mcp-params').innerHTML='';wbUpdateFeedback();await wbMcp.connect();if(wbMcp.state.error)throw new Error(wbMcp.state.error);await wbMcp.discover();if(epoch!==wb.epoch)return;if(wbMcp.state.error)throw new Error(wbMcp.state.error);
  $('#mcp-tool-select').innerHTML='<option value="">选择发现的工具</option>'+NefMcp.describeTools(wbMcp.state.tools,wb.scenes,CAPS).map(row=>`<option value="${esc(row.tool.name)}">${esc(row.title)} · ${esc(row.tool.name)}</option>`).join('');$('#mcp-req').textContent=wbMcp.state.trace.map(t=>jfmt(t.request)).join('\n\n');$('#mcp-resp').textContent=jfmt({tools:wbMcp.state.tools});wbUpdateFeedback();
});
$('#mcp-tool-select').onchange=()=>{wb.epoch++;const name=$('#mcp-tool-select').value;if(!name){wbMcp.state.selected=null;$('#mcp-params').innerHTML='';$('#mcp-call').disabled=true;wbUpdateFeedback();return;}wbMcp.select(name);const tool=wbMcp.state.selected;$('#mcp-pipeline').innerHTML='';$('#mcp-resp').textContent='--';if(!tool){$('#mcp-params').innerHTML='';wbUpdateFeedback();return;}
  $('#mcp-params').innerHTML='<p class="muted">参数来自发现的 inputSchema</p>'+NefMcp.fields(tool).map((f,i)=>`<label for="wb-mcp-param-${i}">${esc(f.description)} ${f.required?'*':''}</label><input id="wb-mcp-param-${i}" data-mcp-param="${esc(f.name)}" placeholder="${esc(f.type)}" value="${esc(typeof f.schema.default==='object'?jfmt(f.schema.default):(f.schema.default??''))}">`).join('');wbUpdateFeedback();};
$('#mcp-call').onclick=()=>wbJob($('#mcp-call'),null,async epoch=>{
  const tool=wbMcp.state.selected;if(!tool)throw new Error('请先发现并选择工具');const values=Object.fromEntries($$('#mcp-params [data-mcp-param]').map(el=>[el.dataset.mcpParam,el.value]));const args=NefMcp.parseArguments(tool,values);const req={jsonrpc:'2.0',id:Date.now(),method:'tools/call',params:{name:tool.name,arguments:args}};
  $('#mcp-req').textContent=jfmt(req);$('#mcp-resp').textContent='调用中…';$('#mcp-pipeline').innerHTML='';
  try{const res=await api('/mcp',{method:'POST',headers:{'X-NEF-Execution':'live','MCP-Protocol-Version':NefMcp.VERSION},body:JSON.stringify(req)});if(epoch!==wb.epoch)return;if(res.error)throw new Error(res.error.message);if(res.id!==req.id)throw new Error('响应与本次请求不匹配');let inner;try{inner=JSON.parse(res.result.content.find(c=>c.type==='text').text);}catch{inner={summary:res.result?.content?.find(c=>c.type==='text')?.text};}renderAuthPipeline($('#mcp-pipeline'),inner?.nef_auth||inner?.detail?.nef_auth,null);$('#mcp-resp').textContent=(res.result?.isError?'工具执行未完成':NefStory.receipt(inner).badge)+'\n'+(res.result?.isError?wbMessage({data:{detail:inner}}):NefStory.businessResult(inner))+'\n\n'+jfmt(res);}
  catch(e){if(epoch===wb.epoch)$('#mcp-resp').textContent=wbMessage(e)+'\n'+jfmt(e.data||{});}
});
/* One feedback address and scenario-specific Key, original invocation panes only. */
function wbInvocation(){const tab=wbActive();if(tab==='intent')return {sceneId:wb.sceneId,mode:'live'};if(tab==='api')return {sceneId:$('#api-cap-select').value.startsWith('scene:')?'collaborative_tracking':'',mode:'live'};if(tab==='mcp'&&wbMcp.state.selected)return {sceneId:wb.scenes.find(s=>s.tool_name===wbMcp.state.selected.name)?.id||'',mode:'live'};return null;}
function wbClearFeedback(){wb.feedbackSignature='';wb.mediaId='';if(wb.mediaUrl)URL.revokeObjectURL(wb.mediaUrl);wb.mediaUrl='';$('#wb-feedback-text').textContent='等待回传';$('#wb-feedback-data').textContent='—';$('#wb-feedback-media').textContent='等待媒体回传';}
async function wbUpdateFeedback(){
  const inv=wbInvocation();$('#wb-feedback').hidden=!inv;
  if(!inv){wb.feedbackContext='';wb.access=null;wbClearFeedback();return;}
  const context=[current,inv.sceneId,inv.mode].join(':');
  if(wb.feedbackContext!==context){wb.feedbackContext=context;wb.channel='';wb.access=null;wbClearFeedback();}
  const demo=inv.mode==='demo';$('#wb-feedback-create').disabled=true;
  $('#wb-feedback-note').textContent=demo?'演示模式 · 不接收现场回传':'当前场景回传接口 · 等待数据';
  if(!apiKey()||demo)return;
  const epoch=wb.epoch;
  try{
    const c=await api('/api/v1/services/'+encodeURIComponent(inv.sceneId||'general')+'/feedback-access',{method:'POST'});
    if(epoch!==wb.epoch||context!==wb.feedbackContext)return;
    wb.access=c;wb.channel=c.id;$('#wb-feedback-create').disabled=false;await wbPollFeedback();
  }catch(e){if(epoch===wb.epoch)$('#wb-feedback-note').textContent='接口暂不可用 · '+wbMessage(e);}
}
$('#wb-feedback-create').onclick=()=>{
  const c=wb.access;if(!c)return;
  const handoff=NefStory.feedbackHandoff(c,location.origin);
  showModal(`<h2>${esc(c.name)} · 回传接口</h2><p class="muted">场景专用回传接口</p><label>回传地址</label><pre>POST ${esc(handoff.url)}</pre><details><summary>查看专用 Key（投屏时勿展开）</summary><pre>Authorization: Bearer ${esc(c.receiver_key)}</pre></details><label>文字结果 JSON</label><pre>${esc(jfmt(handoff.json_example))}</pre><p class="muted">图片 / 视频也向同一地址上传原始文件字节，设置对应 Content-Type；单文件最多 16 MiB。其他机器请使用本机网卡地址。Key 在本次服务内复用，重启后需重新获取。</p><div class="wb-modal-actions"><button id="wb-source-copy">复制对接信息</button><button id="wb-source-close">关闭</button></div>`);
  $('#wb-source-close').onclick=hideModal;
  $('#wb-source-copy').onclick=async()=>{try{await navigator.clipboard.writeText(jfmt(handoff));toast('已复制');}catch{toast('剪贴板不可用，请手动复制',false);}};
};
async function wbPollFeedback(){
  const inv=wbInvocation();if(!inv||inv.mode!=='live'||!wb.channel||!apiKey()||wb.feedbackBusy)return;wb.feedbackBusy=true;const epoch=wb.epoch,channel=wb.channel;
  try{const r=await api('/api/v1/exhibition/channels/'+encodeURIComponent(channel)+'/events');if(epoch!==wb.epoch||channel!==wb.channel)return;$('#wb-feedback-note').textContent=r.events.length?'已接收 '+r.events.length+' 条回传 · 场景级反馈':'回传接口可用 · 等待数据源';const sig=jfmt(r.events);if(sig===wb.feedbackSignature)return;wb.feedbackSignature=sig;
    const text=r.events.findLast(e=>e.kind==='status'),data=r.events.findLast(e=>e.kind==='data'),media=r.events.findLast(e=>e.kind==='image'||e.kind==='video');
    if(text)$('#wb-feedback-text').textContent=[text.title,text.text].filter(Boolean).join('\n');if(data)$('#wb-feedback-data').textContent=jfmt(data.data??data.text);
    if(media&&media.asset_id!==wb.mediaId){const response=await fetch('/api/v1/exhibition/channels/'+encodeURIComponent(channel)+'/media/'+encodeURIComponent(media.asset_id),{headers:{Authorization:'Bearer '+apiKey()}});if(!response.ok)throw new Error('媒体读取失败');const blob=await response.blob();if(epoch!==wb.epoch||channel!==wb.channel)return;if(wb.mediaUrl)URL.revokeObjectURL(wb.mediaUrl);wb.mediaUrl=URL.createObjectURL(blob);wb.mediaId=media.asset_id;const el=document.createElement(media.kind==='video'?'video':'img');el.src=wb.mediaUrl;if(media.kind==='video'){el.controls=true;el.preload='metadata';}else el.alt=media.title||'场景图像';el.onerror=()=>{$('#wb-feedback-media').textContent='媒体无法解码，请核对文件内容';};$('#wb-feedback-media').replaceChildren(el);}
  }catch(e){if(epoch===wb.epoch)$('#wb-feedback-note').textContent='回传读取失败 · '+wbMessage(e);}finally{wb.feedbackBusy=false;}
}
function wbTabChanged(name){wb.epoch++;if(name!=='mcp')wbMcp.reset();wbUpdateFeedback();}
async function refreshAll(){
  wb.epoch++;wbMcp.reset();wb.catalog=[];wb.servers=[];wb.packages=[];wb.channels=[];wb.channel='';wb.feedbackContext='';pipeSteps.length=0;window.wbComposerReset?.();wbClearFeedback();wbResetResult();$('#wb-register-message').textContent='';$('#purchase-notice').hidden=true;renderAccounts();wbRenderNetwork();
  try{await loadMarket();if(wbActive()==='subs')await renderSubs();if(wbActive()==='intent')wbRenderIntent();if(wbActive()==='api')await renderApiTab();if(wbActive()==='mcp')renderMcpTab();if(wbActive()==='composer')await renderComposer();await wbUpdateFeedback();}catch(e){wbError(e);}
}
window.addEventListener('pagehide',()=>{wb.epoch++;if(wb.mediaUrl)URL.revokeObjectURL(wb.mediaUrl);});
setInterval(wbPollFeedback,2000);
setInterval(()=>{if(['market','afreg'].includes(wbActive())&&apiKey())wbLoadNetwork().catch(wbError);},30000);
purchaseBootstrap().catch(wbError).then(refreshAll).then(()=>{const hash=location.hash.slice(1);if(hash&&!activateTab(hash,false))activateTab('market',true);});
