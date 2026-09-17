"use strict";
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {services:[],serviceId:'robot_patrol',executionMode:'demo',catalogMode:'scenes',caps:[],categories:{},account:null,key:sessionStorage.getItem('nef_portal_key')||'',category:'all',page:'market',mode:'intent',capId:'target_detection',info:{configured_capabilities:[]},channels:[],channel:'',events:[],mediaKey:'',mediaUrl:'',polling:false,epoch:0,lastSignature:'',requestEpoch:0,toastTimer:null,toolQuery:''};
const categoryNames={isac:'通感一体',ai:'AI 服务',computing:'通算一体',connectivity:'连接服务',location:'定位服务',data:'数据服务',security:'安全身份',ecosystem:'生态服务'};
const icons={isac:'<circle cx="12" cy="12" r="3"/><path d="M5 5a10 10 0 0 0 0 14M19 5a10 10 0 0 1 0 14M8 8a5.7 5.7 0 0 0 0 8M16 8a5.7 5.7 0 0 1 0 8"/>',ai:'<rect x="6" y="6" width="12" height="12" rx="3"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4M10 10h4v4h-4z"/>',computing:'<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4M7 8l3 2-3 2M13 12h4"/>',connectivity:'<path d="M3 9a14 14 0 0 1 18 0M6 12a9 9 0 0 1 12 0M9 15a4 4 0 0 1 6 0"/><circle cx="12" cy="19" r="1"/>',location:'<path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0z"/><circle cx="12" cy="10" r="2.5"/>',data:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',security:'<path d="M12 2l8 3v6c0 6-8 11-8 11S4 17 4 11V5zM8 12l3 3 5-6"/>',ecosystem:'<circle cx="12" cy="12" r="3"/><circle cx="4" cy="4" r="2"/><circle cx="20" cy="4" r="2"/><circle cx="4" cy="20" r="2"/><circle cx="20" cy="20" r="2"/><path d="M6 6l4 4M14 14l4 4M6 18l4-4M14 10l4-4"/>'};
function icon(category){return `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[category]||icons.data}</svg>`;}
function toast(text){clearTimeout(state.toastTimer);$('toast').textContent=text;$('toast').classList.add('toast-show');state.toastTimer=setTimeout(()=>$('toast').classList.remove('toast-show'),3500);}
function explain(data){const d=data?.detail??data;if(typeof d==='string')return d;if(d?.message)return d.message;if(d?.status==='payment_required')return '请先订阅该能力';return JSON.stringify(d??{});}
async function request(path,options={}){const headers={...(state.key?{Authorization:'Bearer '+state.key}:{}),...(options.body?{'Content-Type':'application/json'}:{}),...options.headers};const response=await fetch(path,{...options,headers});let data;try{data=await response.json();}catch{data={detail:'服务未返回有效 JSON'};}if(!response.ok){const e=new Error(explain(data));e.status=response.status;e.data=data;throw e;}return data;}
function modal(title,html){$('modal-title').textContent=title;$('modal-body').innerHTML=html;if(!$('modal').open)$('modal').showModal();}
$('close-modal').onclick=()=>$('modal').close();$('modal').addEventListener('click',e=>{if(e.target===$('modal')&&(e.offsetX<0||e.offsetX>$('modal').offsetWidth||e.offsetY<0||e.offsetY>$('modal').offsetHeight))$('modal').close();});
function entitlement(){return new Set(state.account?.entitled_capabilities||[]);}
function subscribed(){return new Set(state.account?.subscribed_capabilities||[]);}
function hasInvocation(){return state.page==='access'||(state.page==='mcp'&&!!mcpClient.state.selected);}
function updateInvocationLayout(){
  const show=hasInvocation();
  $('receiver-panel').classList.toggle('hidden',!show);$('workspace').classList.toggle('with-receiver',show);
  $('external-contract').classList.toggle('hidden',!show);renderInvocationPath();
  if(!show&&$('scene-modal').open)$('scene-modal').close();
}
function pathwayNodes(mode,demo=false){
  const p=NefStory.path(mode);
  return `<div class="exposure-node"><small>${esc(p.client)}</small><strong>${esc(p.input)}</strong></div><span class="path-arrow" aria-hidden="true">→</span><div class="exposure-node nef-node"><small>NEF · ${esc(p.nef)}</small><strong>${esc(p.action)}</strong></div><span class="path-arrow" aria-hidden="true">→</span><div class="exposure-node"><small>${demo?'演示服务':esc(p.network)}</small><strong>${demo?'返回场景示例':esc(p.delivery)}</strong></div>`;
}
function renderEntry(mode){
  document.querySelectorAll('[data-entry]').forEach(b=>{const active=b.dataset.entry===mode;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  $('hero-path').innerHTML=pathwayNodes(mode);
  $('explore-entry').innerHTML=(mode==='tool'?'探索工具目录':'浏览场景服务')+' <span>↗</span>';
  $('explore-entry').onclick=()=>{if(mode==='tool')selectPage('mcp');else{setCatalog('scenes');$('scene-grid').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center'});}};
}
function renderInvocationPath(){
  const show=hasInvocation();$('invocation-path').classList.toggle('hidden',!show);if(!show)return;
  const demo=!!currentService()&&state.executionMode==='demo';
  $('invocation-path').innerHTML=`<div class="invocation-path-head"><strong>${esc(NefStory.path(state.mode).name)} 开放路径</strong><span>${demo?'演示路径 · 不发送至网络内部':'接口路径 · 执行结果以实际回执为准'}</span></div><div class="exposure-nodes">${pathwayNodes(state.mode,demo)}</div>`;
}
document.querySelectorAll('[data-entry]').forEach(b=>b.onclick=()=>renderEntry(b.dataset.entry));
renderEntry('intent');
function selectPage(page){
  if(!['market','subscriptions','access','mcp','compose','federation'].includes(page))return;
  const previous=state.page;state.page=page;
  if(previous!==page){state.requestEpoch++;state.epoch++;clearFeed();}
  if(page==='mcp'&&previous!=='mcp'){
    state.mode='tool';state.serviceId='';state.capId='';state.toolQuery='';$('mcp-search').value='';renderedToolSignature='';mcpClient.reset();
  }else if(previous==='mcp'&&page!=='mcp'){
    mcpClient.reset();state.serviceId='robot_patrol';state.capId='target_detection';state.mode='intent';
  }
  const titles={market:'能力超市',subscriptions:'订阅与鉴权',access:'意图调用',mcp:'MCP 接入',compose:'自助编排',federation:'双向开放'};
  $('page-name').textContent=titles[page];$('access-page-title').textContent=page==='mcp'?'MCP 工具接入':'意图调用';
  document.querySelectorAll('nav [data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===page));
  document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id==='page-'+(page==='mcp'?'access':page)));
  $('hero').classList.toggle('hidden',page!=='market');
  if(page==='subscriptions')renderSubscriptions();
  if(['market','compose','federation'].includes(page))NefNetwork.reload().catch(e=>toast(e.message));
  if(page==='access'||page==='mcp'){renderAccess();poll();}
  updateInvocationLayout();window.scrollTo({top:0,behavior:'instant'});
}
$('market-mcp-entry').onclick=()=>selectPage('mcp');
$('expand-scene').onclick=()=>{if(hasInvocation())$('scene-modal').showModal();};

$('close-scene').onclick=()=>$('scene-modal').close();
$('scene-modal').addEventListener('close',()=>{$('scene-modal').querySelectorAll('video').forEach(v=>v.pause());});

document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>selectPage(b.dataset.page));
function card(cap){const own=entitlement().has(cap.id),planned=cap.status!=='available';const price=String(cap.unit_price||'—').split('/');return `<article class="cap-card ${planned?'planned':''}"><div class="cap-head"><div class="cap-icon">${icon(cap.category)}</div><div style="min-width:0"><h3 class="cap-name">${esc(cap.name)}</h3><div class="cap-category">${esc(categoryNames[cap.category]||cap.category)}</div></div></div><p class="cap-description">${esc(cap.description)}</p><div class="cap-tags"><span>API</span><span>MCP Tool</span>${planned?'<span>规划中</span>':''}</div><div class="cap-footer"><span class="cap-price">${/^\d/.test(price[0])?'¥':''}${esc(price[0])}${price[1]?`<small> / ${esc(price[1])}</small>`:''}</span><button class="subscribe-btn ${own?'owned':''}" ${planned?'disabled':''} data-cap="${esc(cap.id)}" data-action="${own?'invoke':'subscribe'}">${planned?'暂未开放':own?'调用 ↗':'订阅'}</button></div></article>`;}
function bindCards(container){container.querySelectorAll('[data-cap]').forEach(button=>button.onclick=()=>{if(button.dataset.action==='invoke'){state.serviceId='';state.epoch++;clearFeed();state.capId=button.dataset.cap;state.mode='api';selectPage('access');}else subscriptionDialog(button.dataset.cap);});}
function currentService(){return state.services.find(service=>service.id===state.serviceId);}
function sceneEntitlements(){return new Set(state.account?.scene_subscriptions||[]);}
function sceneCard(service){
  const owned=sceneEntitlements().has(service.id);
  return `<article class="scene-card"><div class="scene-art ${esc(service.id)}">${NefScenes.illustration(service.id)}<span class="scene-art-caption">场景示意</span></div><div class="scene-card-body"><span class="scene-mode">${service.modes.includes('intent')?'INTENT · 意图驱动':'API / TOOL · 端网协同'}</span><h3>${esc(service.name)}</h3><p>${esc(service.description)}</p><div class="scene-outputs">${service.outputs.map(o=>`<span>${esc(o)}</span>`).join('')}</div><div class="scene-card-actions"><span>${owned?'场景已开通':'按场景订阅'}</span><button data-scene="${esc(service.id)}">${owned?'进入场景 ↗':'开通体验 ↗'}</button></div></div></article>`;
}
function bindScenes(container){container.querySelectorAll('[data-scene]').forEach(b=>b.onclick=()=>{
  const id=b.dataset.scene;
  if(sceneEntitlements().has(id)){chooseScene(id);return;}
  if(!requireAccount())return;
  const service=state.services.find(s=>s.id===id);
  modal('开通场景服务',`<div class="cap-head"><strong>${esc(service.name)}</strong></div><p class="dialog-note">开通后可使用 ${esc(service.modes.map(m=>m==='intent'?'Intent':m==='tool'?'MCP Tool':'API').join(' / '))} 接入。本次为演示权益，不产生真实扣款。</p><div class="dialog-actions"><button class="primary" id="confirm-scene-subscribe">开通并进入场景</button></div>`);
  $('confirm-scene-subscribe').onclick=async()=>{const b=$('confirm-scene-subscribe');b.disabled=true;try{await request(`/api/v1/services/${id}/subscribe`,{method:'POST'});await refreshAccount();$('modal').close();chooseScene(id);toast('场景已开通');}catch(e){b.disabled=false;toast(e.message);}};
});}
function renderScenes(){$('scene-grid').innerHTML=state.services.map(sceneCard).join('');bindScenes($('scene-grid'));}
function chooseScene(id){const service=state.services.find(s=>s.id===id);if(!service)return;state.serviceId=id;state.mode=service.modes.includes('intent')?'intent':'api';state.epoch++;clearFeed();selectPage('access');}
function setCatalog(mode){state.catalogMode=mode;$('scene-grid').classList.toggle('hidden',mode!=='scenes');$('basic-catalog').classList.toggle('hidden',mode!=='basics');$('show-scenes').classList.toggle('active',mode==='scenes');$('show-basics').classList.toggle('active',mode==='basics');}
$('show-scenes').onclick=()=>setCatalog('scenes');$('show-basics').onclick=()=>setCatalog('basics');
$('scene-select').onchange=()=>{if($('scene-select').value)chooseScene($('scene-select').value);else{state.serviceId='';state.mode='api';state.epoch++;clearFeed();renderAccess();}};
function setExecution(mode){state.executionMode=mode;state.epoch++;clearFeed();renderAccess();poll();}
$('execution-demo').onclick=()=>setExecution('demo');$('execution-live').onclick=()=>setExecution('live');
function renderMarket(){const query=$('search').value.trim().toLowerCase();const caps=state.caps.filter(c=>(state.category==='all'||c.category===state.category)&&(!query||(c.name+' '+c.id+' '+c.description).toLowerCase().includes(query)));$('market-count').textContent=`${caps.length} 项`;$('cap-grid').innerHTML=caps.length?caps.map(card).join(''):'<p class="loading">没有匹配的能力</p>';bindCards($('cap-grid'));$('categories').innerHTML=[['all','全部能力'],...Object.entries(categoryNames).filter(([k])=>state.caps.some(c=>c.category===k))].map(([k,n])=>`<button class="${state.category===k?'active':''}" data-category="${k}">${n}</button>`).join('');$('categories').querySelectorAll('button').forEach(b=>b.onclick=()=>{state.category=b.dataset.category;renderMarket();});}
$('search').oninput=renderMarket;
async function refreshAccount(){if(!state.key){state.account=null;renderAccount();return;}try{state.account=await request('/api/v1/auth/info');}catch(e){if(e.status===401){state.key='';sessionStorage.removeItem('nef_portal_key');state.account=null;}else throw e;}renderAccount();}
function renderAccount(){NefNetwork.reset();NefNetwork.reload().catch(e=>toast(e.message));$('account-button').textContent=state.account?state.account.account+' ↗':'开发者接入 ↗';$('sub-count').textContent=subscribed().size+sceneEntitlements().size;renderScenes();renderMarket();renderSubscriptions();if(state.page==='access'||state.page==='mcp')renderAccess();}
function renderSubscriptions(){
  const a=state.account;$('subscription-account').textContent=a?a.account:'接入后开通场景';
  $('owned-total').textContent=a?subscribed().size+sceneEntitlements().size:'—';$('current-plan').textContent=a?(a.plan||'free').toUpperCase():'—';$('monthly').textContent='按场景开通';
  $('intent-permission').textContent='按所选场景核验权限';$('enable-intent').disabled=true;
  const scenes=state.services.filter(scene=>sceneEntitlements().has(scene.id));
  $('owned-scenes').innerHTML=scenes.length?scenes.map(sceneCard).join(''):'<p class="loading">选择场景，开启业务体验。</p>';bindScenes($('owned-scenes'));
  const caps=state.caps.filter(cap=>entitlement().has(cap.id));$('owned-grid').innerHTML=caps.map(card).join('');bindCards($('owned-grid'));
}

function loginDialog(){if(state.account){modal('开发者账号',`<div class="status-label">当前账号</div><strong>${esc(state.account.account)}</strong><div class="status-label">API Key</div><div class="code-box">${esc(state.key.slice(0,8))}••••••••${esc(state.key.slice(-4))}</div><div class="dialog-actions"><button id="copy-key" class="secondary">复制 API Key</button><button id="sign-out" class="secondary">退出账号</button></div>`);$('copy-key').onclick=()=>copy(state.key);$('sign-out').onclick=()=>{state.key='';sessionStorage.removeItem('nef_portal_key');state.account=null;state.epoch++;state.channels=[];state.channel='';clearFeed();renderChannels();renderAccount();$('modal').close();};return;}modal('开发者接入',`<div class="field"><label for="login-key">使用已有 API Key</label><input id="login-key" type="password" autocomplete="off" placeholder="nef_…"></div><button class="primary" id="login-use">接入</button><div class="split-line"></div><p class="dialog-note">本地演示账号，订阅与权益保存在当前服务内。</p><div class="field"><label for="register-name">创建演示账号</label><input id="register-name" autocomplete="off" maxlength="60" placeholder="填写 AF 名称"></div><button class="secondary" id="register-use">创建账号</button><p class="dialog-error" id="login-error"></p>`);$('login-use').onclick=async()=>{const key=$('login-key').value.trim();if(!key)return;state.key=key;try{await refreshAccount();if(!state.account)throw new Error('API Key 无效');sessionStorage.setItem('nef_portal_key',state.key);await loadChannels();$('modal').close();toast('已接入');}catch(e){$('login-error').textContent=e.message;}};$('register-use').onclick=async()=>{const account=$('register-name').value.trim();if(!account)return;try{const d=await request('/api/v1/register',{method:'POST',body:JSON.stringify({account})});state.key=d.api_key;sessionStorage.setItem('nef_portal_key',state.key);await refreshAccount();await loadChannels();$('modal').close();toast('演示账号已创建');}catch(e){$('login-error').textContent=e.message;}};}
$('account-button').onclick=loginDialog;
function requireAccount(){if(state.account)return true;loginDialog();return false;}
function subscriptionDialog(id){if(!requireAccount())return;const c=state.caps.find(x=>x.id===id);modal('订阅能力',`<div class="cap-head"><div class="cap-icon">${icon(c.category)}</div><div><strong>${esc(c.name)}</strong><div class="muted">${esc(c.unit_price)} · 演示价格</div></div></div><p class="dialog-note">${esc(c.description)}</p><div class="dialog-actions"><button class="primary" id="confirm-subscribe">确认订阅</button></div>`);$('confirm-subscribe').onclick=async()=>{const button=$('confirm-subscribe');button.disabled=true;try{await request('/api/v1/subscribe',{method:'POST',body:JSON.stringify({account:state.account.account,capability_ids:[id]})});await refreshAccount();$('modal').close();toast('订阅已生效');}catch(e){button.disabled=false;toast(e.message);}};}
$('enable-intent').onclick=()=>{if(!requireAccount())return;modal('开通 Intent 接入',`<p class="dialog-note">切换至 PRO 演示权益，包含 Intent 接入权限及 basic 层能力。不会产生真实扣款。</p><div class="dialog-actions"><button class="primary" id="confirm-plan">确认开通</button></div>`);$('confirm-plan').onclick=async()=>{try{await request('/api/v1/account/plan',{method:'POST',body:JSON.stringify({plan:'pro'})});await refreshAccount();$('modal').close();toast('Intent 接入已开通');}catch(e){toast(e.message);}};};
function sampleArgs(cap){const values={area:'园区A',target_id:'target-001',device_id:'device-001',ue_id:'ue-001',app_id:'af-demo',duration_sec:60};const result={};for(const p of cap?.params||[]){if(p.default!==null&&p.default!==undefined)result[p.name]=p.default;else if(p.required)result[p.name]=values[p.name]??(p.enum?.[0]??({string:'example',integer:1,number:1,boolean:true,array:[],object:{}}[p.type]??''));}return result;}
function currentCap(){return state.caps.find(c=>c.id===state.capId)||state.caps.find(c=>c.status==='available');}
let discoveryContext='',renderedToolSignature='',catalogSelection='';
async function mcpTransport(message){
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),10000);
  try{
    const response=await fetch('/mcp',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+state.key,'X-NEF-Execution':'live','MCP-Protocol-Version':NefMcp.VERSION},body:JSON.stringify(message),signal:controller.signal});
    if(!response.ok){let data;try{data=await response.json();}catch{data={detail:'NEF 接入请求未成功'};}throw new Error(explain(data));}
    if(!Object.hasOwn(message,'id')){if(response.status!==202)throw new Error('NEF 未确认初始化通知');return null;}
    const text=await response.text();if(text.length>2000000)throw new Error('协议响应超过展示端接收上限');
    try{return JSON.parse(text);}catch{throw new Error('NEF 未返回有效协议报文');}
  }finally{clearTimeout(timeout);}
}
const mcpClient=NefMcp.createClient(mcpTransport,onDiscoveryChange);
function onDiscoveryChange(){
  if(state.page==='mcp'&&!mcpClient.state.selected){
    if(state.serviceId||state.capId){state.serviceId='';state.capId='';state.requestEpoch++;state.epoch++;clearFeed();}
    renderedToolSignature='';
  }
  renderDiscovery();
}
function syncDiscovery(){
  const context=[state.key,JSON.stringify(state.account?.scene_subscriptions||[]),JSON.stringify(state.account?.entitled_capabilities||[])].join('|');
  if(context!==discoveryContext){discoveryContext=context;renderedToolSignature='';mcpClient.reset();}
  renderDiscovery();
}
function renderToolFields(tool){
  const signature=tool.name+JSON.stringify(tool.inputSchema);if(signature===renderedToolSignature)return;renderedToolSignature=signature;
  const example=currentService()?.sample_arguments||sampleArgs(state.caps.find(cap=>cap.id===tool.name));
  $('mcp-arguments').innerHTML='<p class="mcp-form-note">参数结构来自 NEF 工具声明 · 示例值可修改</p>'+NefMcp.fields(tool).map((field,index)=>{
    const value=field.schema.default??example[field.name]??'';
    const text=typeof value==='object'?JSON.stringify(value,null,2):String(value);
    const id='mcp-input-'+index;
    const options=field.schema.enum||(field.type==='boolean'?[true,false]:null);
    let input;
    if(options)input=`<select id="${id}" data-mcp-key="${esc(field.name)}"><option value="">请选择</option>${options.map(v=>`<option value="${esc(String(v))}" ${String(v)===text?'selected':''}>${esc(String(v))}</option>`).join('')}</select>`;
    else if(['object','array'].includes(field.type))input=`<textarea id="${id}" data-mcp-key="${esc(field.name)}" rows="3">${esc(text)}</textarea>`;
    else input=`<input id="${id}" data-mcp-key="${esc(field.name)}" type="${['number','integer'].includes(field.type)?'number':'text'}" ${field.type==='number'?'step="any"':''} value="${esc(text)}">`;
    return `<div class="field"><label for="${id}">${esc(field.description)}${field.required?' *':''}<small>${esc(field.name)} · ${esc(field.type)} · ${field.required?'必填':'可选'}</small></label>${input}</div>`;
  }).join('');
}
function selectDiscoveredTool(name){
  try{
    mcpClient.select(name);
    const business=NefMcp.selectedBusiness(mcpClient.state.selected,state.services);
    state.serviceId=business.serviceId;state.capId=business.capId;state.mode='tool';
    state.requestEpoch++;state.epoch++;clearFeed();renderedToolSignature='';renderAccess();
  }catch(e){toast(e.message);}
}
function toolDirectoryCard(row){
  const t=row.tool,selected=mcpClient.state.selected?.name===t.name;
  return `<article class="discovered-tool ${selected?'selected':''}"><div class="discovered-tool-header"><h4>${esc(row.title)}</h4>${selected?'<span class="mcp-selected-label">已选用</span>':''}</div><code>${esc(t.name)}</code><p>${esc(t.description||'NEF 发布的工具')}</p><div class="tool-badges"><span>${NefMcp.fields(t).length} 个参数</span><span>${(t.inputSchema.required||[]).length} 个必填</span><span>${t.subscribed===true?'已开通':t.subscribed===false?'待开通':'调用时核验'}</span></div><div class="tool-select-row"><span>${row.group==='scene'?'场景服务工具':'网络能力工具'}</span><button class="${selected?'secondary':'primary'}" data-discovered-tool="${esc(t.name)}" ${selected||mcpClient.state.call==='running'?'disabled':''}>${selected?'已选用':'选用工具'}</button></div></article>`;
}
function renderDiscovery(){
  const toolMode=state.page==='mcp',d=mcpClient.state;
  $('mcp-discovery').classList.toggle('hidden',!toolMode);$('mcp-arguments').classList.toggle('hidden',!toolMode);$('raw-request-field').classList.toggle('hidden',toolMode);
  const ready=!toolMode||!!d.selected;
  for(const id of ['invocation-request','invocation-auth','invocation-response'])$(id).classList.toggle('hidden',!ready);
  if(toolMode){$('scene-context').classList.toggle('hidden',!d.selected);$('scene-select-field').classList.add('hidden');$('access-mode-tabs').classList.add('hidden');}
  updateInvocationLayout();if(!toolMode)return;
  const phases=[d.connected?'done':d.phase==='connecting'?'active':d.error?'error':'',d.phase==='discovering'?'active':d.phase==='discovered'?'done':d.error&&d.connected?'error':'',d.selected?'done':d.tools.length?'active':'',d.call==='running'?'active':d.call==='done'?'done':d.call==='error'?'error':''];
  $('mcp-stages').innerHTML=['连接 NEF','发现工具','选用工具','业务调用'].map((label,i)=>`<div class="mcp-stage ${phases[i]}"><i>0${i+1}</i>${label}</div>`).join('');
  $('mcp-connect').disabled=d.busy||d.call==='running';$('mcp-connect').textContent=d.connected?'重新连接':'连接 NEF';
  $('discover-tools').disabled=!d.connected||d.busy||d.call==='running';$('discover-tools').textContent=d.phase==='discovered'?'刷新工具目录':'发现工具';
  $('mcp-server-status').textContent=d.server?d.server.name+' · '+(d.server.version||'已响应'):d.phase==='connecting'?'正在建立协议连接…':'等待接入';
  $('mcp-filter').classList.toggle('hidden',d.phase!=='discovered');
  if(!d.selected)$('mcp-catalog').open=true;
  else if(catalogSelection!==d.selected.name)$('mcp-catalog').open=false;
  catalogSelection=d.selected?.name||'';
  $('mcp-catalog-summary').textContent=d.selected?'已选用 '+(state.services.find(s=>s.tool_name===d.selected.name)?.name||state.caps.find(c=>c.id===d.selected.name)?.name||d.selected.name)+' · 展开目录更换工具':'NEF 工具目录';
  let content=d.error?`<p class="discovery-error">${esc(d.error)}</p>`:'';
  if(d.phase==='discovered'){
    const rows=NefMcp.describeTools(d.tools,state.services,state.caps,state.toolQuery);
    content+=`<div class="directory-summary">NEF 已发布 ${d.tools.length} 个工具${state.toolQuery?' · 筛选 '+rows.length+' 个':''} · 请选择需要的业务能力</div>`;
    for(const [group,label] of [['scene','场景服务工具'],['capability','基础能力工具']]){
      const items=rows.filter(row=>row.group===group);if(!items.length)continue;
      content+=`<section class="tool-directory-group"><h3>${label}<span>${items.length}</span></h3><div class="discovery-card-grid">${items.map(toolDirectoryCard).join('')}</div></section>`;
    }
    if(!rows.length)content+='<p class="discovery-placeholder">没有可选工具，请调整搜索或刷新目录。</p>';
  }else if(!d.error)content+=`<p class="discovery-placeholder">${d.phase==='discovering'?'正在读取 NEF 发布的完整工具目录…':d.connected?'连接已建立。发现网络能力，再选择你的业务工具。':'从连接开始，发现 NEF 提供的工具与业务能力。'}</p>`;
  $('mcp-directory').innerHTML=content;$('mcp-trace').textContent=JSON.stringify(d.trace,null,2);
  $('mcp-directory').querySelectorAll('[data-discovered-tool]').forEach(b=>b.onclick=()=>selectDiscoveredTool(b.dataset.discoveredTool));
  if(d.selected)renderToolFields(d.selected);else{renderedToolSignature='';$('mcp-arguments').replaceChildren();}
  const needsSubscription=d.selected?.subscribed===false;
  $('mcp-subscription').classList.toggle('hidden',!needsSubscription);
  $('mcp-subscription').innerHTML=needsSubscription?'<span>该工具尚未开通，调用前需获得服务使用权。</span><button class="secondary" id="mcp-open-subscription">开通使用</button>':'';
  if(needsSubscription)$('mcp-open-subscription').onclick=()=>openToolSubscription(d.selected);
  $('send-request').disabled=!d.selected||d.busy||d.call==='running';
}
function openToolSubscription(tool){
  if(!requireAccount())return;
  const service=state.services.find(s=>s.tool_name===tool.name),cap=state.caps.find(c=>c.id===tool.name);
  if(!service&&!cap){toast('请联系服务提供方开通此工具');return;}
  modal('开通工具使用权',`<strong>${esc(service?.name||cap.name)}</strong><p class="dialog-note" style="margin-top:12px">本次开通演示权益，不产生真实扣款。开通后重新获取目录确认权限。</p><div class="dialog-actions"><button id="mcp-confirm-subscription" class="primary">确认开通</button></div>`);
  $('mcp-confirm-subscription').onclick=async()=>{
    const button=$('mcp-confirm-subscription');button.disabled=true;
    try{
      if(service)await request(`/api/v1/services/${service.id}/subscribe`,{method:'POST'});
      else await request('/api/v1/subscribe',{method:'POST',body:JSON.stringify({account:state.account.account,capability_ids:[cap.id]})});
      await refreshAccount();$('modal').close();toast('权益已更新，请连接并刷新工具目录');
    }catch(e){button.disabled=false;toast(e.message);}
  };
}
$('mcp-search').oninput=()=>{state.toolQuery=$('mcp-search').value;renderDiscovery();};

$('mcp-connect').onclick=()=>{if(requireAccount()){state.requestEpoch++;mcpClient.connect();}};
$('discover-tools').onclick=()=>{if(requireAccount())mcpClient.discover();};
function selectedToolArguments(){
  if(!mcpClient.state.selected)throw new Error('请先发现并选用工具');
  const values=Object.create(null);$('mcp-arguments').querySelectorAll('[data-mcp-key]').forEach(input=>values[input.dataset.mcpKey]=input.value);
  return NefMcp.parseArguments(mcpClient.state.selected,values);
}
function renderAccess(){
  state.requestEpoch++;
  syncChannelSelection();
  const toolMode=state.page==='mcp',service=currentService(),selected=toolMode?mcpClient.state.selected:null,cap=toolMode?state.caps.find(c=>c.id===state.capId):currentCap();if(cap)state.capId=cap.id;
  const modes=toolMode?['tool']:service?service.modes:['api','tool'];if(!modes.includes(state.mode))state.mode=service?.preferred_mode||'api';
  document.querySelectorAll('[data-mode]').forEach(b=>{b.classList.toggle('active',b.dataset.mode===state.mode);b.disabled=!modes.includes(b.dataset.mode);});
  $('scene-context').classList.toggle('hidden',toolMode?!selected:!service);$('scene-select-field').classList.toggle('hidden',toolMode);$('access-mode-tabs').classList.toggle('hidden',toolMode);
  $('scene-select').innerHTML='<option value="">基础能力 · 按接口调用</option>'+state.services.map(s=>`<option value="${esc(s.id)}" ${s.id===state.serviceId?'selected':''}>${esc(s.name)}</option>`).join('');
  if(toolMode&&selected&&!service){$('scene-kicker').textContent='DISCOVERED NETWORK TOOL';$('scene-call-name').textContent=cap?.name||selected.name;$('scene-call-description').textContent=selected.description||'已选用 NEF 工具';}
  document.querySelector('.execution-toggle').classList.toggle('hidden',!service);
  if(service){$('scene-kicker').textContent=service.tag;$('scene-call-name').textContent=service.name;$('scene-call-description').textContent=service.headline;}
  $('execution-demo').classList.toggle('active',state.executionMode==='demo');$('execution-live').classList.toggle('active',state.executionMode==='live');
  const demo=!!service&&state.executionMode==='demo';$('channel-select').disabled=demo;document.querySelector('.receiver-controls').classList.toggle('hidden',demo);$('connect-source').classList.toggle('hidden',demo);
  $('receiver-health').textContent=demo?'演示数据 · 非现场回传':'场景数据源实时接收通道';
  $('capability-field').classList.toggle('hidden',toolMode||!!service||state.mode==='intent');
  $('capability-select').innerHTML=state.caps.filter(c=>c.status==='available').map(c=>`<option value="${esc(c.id)}" ${c.id===state.capId?'selected':''}>${esc(c.name)}${entitlement().has(c.id)?' · 已授权':''}</option>`).join('');
  $('endpoint').textContent=state.mode==='tool'?'/mcp':service?`/api/v1/services/${service.id}/${state.mode==='intent'?'intent':'invoke'}`:`/api/v1/capabilities/${state.capId}/invoke`;
  $('input-label').textContent=state.mode==='intent'?'业务意图':state.mode==='tool'?'工具调用参数':'调用参数';
  $('request-input').value=state.mode==='intent'?service.intent_example:JSON.stringify(service?service.sample_arguments:sampleArgs(cap),null,2);
  $('request-input').placeholder=state.mode==='intent'?'描述希望完成的业务目标':'';
  $('route-status').textContent=demo?'场景演示通道':service?'真实转发 · 按场景接口配置':state.info.configured_capabilities?.includes(state.capId)?'已配置内部接口':'内部接口待对接';
  $('route-status').classList.toggle('ready',demo);$('send-request').textContent=demo?'运行场景演示 ↗':'发起场景调用 ↗';
  $('business-result').textContent='等待业务意图或调用结果';$('response-summary').textContent=service||selected?'业务结果将在此呈现':'—';$('response-json').textContent='{}';$('response-badge').textContent='等待发起';renderAuth(null,0);$('send-request').disabled=false;syncDiscovery();
}

document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{if(b.dataset.mode==='tool'){selectPage('mcp');return;}state.mode=b.dataset.mode;renderAccess();});$('capability-select').onchange=()=>{state.capId=$('capability-select').value;renderAccess();};
function renderAuth(payload,status,pending=false){
  const result=NefAuthReceipt.assess(payload,status,state.mode,pending),service=currentService();
  const labels={passed:'通过',denied:'待开通',pending:pending?'核验中':'待核验'};
  const visible=result.steps.filter(step=>step.state!=='unimplemented');
  $('auth-steps').innerHTML=visible.map((step,i)=>`<span class="auth-step ${step.state}"><b>${esc(i===2&&service?'场景授权':step.label)}</b><em>${labels[step.state]}</em></span>`).join('');
  $('auth-receipt').textContent=visible.every(s=>s.state==='passed')?'身份可信，访问策略已匹配。':visible.some(s=>s.state==='denied')?'完成所选服务的开通授权，即可发起业务体验。':pending?'正在核验本次访问策略…':'统一接入，按服务核验访问权限。';
}
$('auth-explanation').onclick=()=>modal('统一访问策略',`<p class="dialog-note">识别 AF 身份，校验接口权限，匹配所选场景的订阅权益。API、Tool、Intent 复用统一的准入逻辑。</p><details><summary>实现说明</summary><p class="dialog-note" style="margin-top:12px">当前使用本地 API Key 与场景订阅判定，未实现 mTLS、OAuth 正式接入和区域/设备级资源策略。回执以本次实际检查结果为准。</p></details>`);
function renderSceneDemo(service,result){
  state.epoch++;clearFeed();state.mediaKey='demo:'+service.id;
  for(const id of ['mini-visual','board-visual'])$(id).innerHTML='<div class="demo-scene-frame">'+NefScenes.illustration(service.id)+'</div>';
  $('mini-status').textContent=$('board-status').textContent=result.demo_result.text||result.demo_result.status;
  $('mini-data').textContent=$('board-data').textContent=JSON.stringify(result.demo_result.data,null,2);
  $('receiver-health').textContent='场景演示 · 示例数据，非现场回传';$('received-time').textContent=clock(Date.now()/1000);
  $('event-count').textContent='演示回执';$('event-list').innerHTML='<div class="event-row"><b>'+esc(service.name)+'</b><span>场景演示结果 · 非现场执行记录</span></div>';
}

$('send-request').onclick=async()=>{
  if(!requireAccount())return;
  const service=currentService(),mode=state.mode,execution=service?state.executionMode:'live',epoch=state.requestEpoch,endpoint=$('endpoint').textContent;
  let body;
  try{body=mode==='intent'?{text:$('request-input').value}:mode==='tool'?selectedToolArguments():JSON.parse($('request-input').value);if(mode==='intent'&&!body.text.trim())throw new Error('请填写业务意图');if(!body||typeof body!=='object'||Array.isArray(body))throw new Error('参数需要 JSON 对象');}catch(e){toast(e.message);return;}
  const button=$('send-request');if(mode==='tool')mcpClient.callState('running');button.disabled=true;document.body.classList.add('is-requesting');$('business-result').textContent='请求已发起，等待服务返回…';$('response-badge').textContent='请求处理中';renderAuth(null,0,true);
  try{
    if(mode==='tool')body={jsonrpc:'2.0',id:Date.now(),method:'tools/call',params:{name:mcpClient.state.selected.name,arguments:body}};
    const raw=await request(endpoint,{method:'POST',headers:{'X-NEF-Execution':execution,...(mode==='tool'?{'MCP-Protocol-Version':NefMcp.VERSION}:{})},body:JSON.stringify(body)});
    if(epoch!==state.requestEpoch)return;
    $('response-json').textContent=JSON.stringify(raw,null,2);let result=raw;
    if(mode==='tool'){
      mcpClient.recordCall(body,raw);
      if(raw.jsonrpc!=='2.0'||raw.id!==body.id)throw new Error('工具响应与本次调用不匹配');
      if(raw.error)throw new Error(raw.error.message);
      if(!raw.result||!Array.isArray(raw.result.content))throw new Error('工具响应缺少有效结果');
      const text=raw.result?.content?.find(c=>c.type==='text')?.text;if(text){try{result=JSON.parse(text);}catch{result={summary:text};}}
      if(raw.result?.payment_required||raw.result?.isError){const error=new Error(explain(result));error.status=result.http_status||402;error.data=result;throw error;}
    }
    if(mode==='tool')mcpClient.callState('done');renderAuth(result,200);const receipt=NefStory.receipt(result);$('response-badge').textContent=receipt.badge;$('response-summary').textContent=receipt.summary;$('business-result').textContent=NefStory.businessResult(result);
    if(service&&result.data_source==='demo'&&result.demo_result)renderSceneDemo(service,result);
  }catch(e){if(epoch!==state.requestEpoch)return;if(mode==='tool')mcpClient.callState('error');$('response-badge').textContent=e.status===503?'等待联调':e.status===504?'结果待确认':'访问未完成';$('response-summary').textContent=e.message;$('business-result').textContent=e.status===504?'请求等待超时，网络侧结果尚不确定，请勿直接重复执行。':'本次未获得业务结果';if(e.data)$('response-json').textContent=JSON.stringify(e.data,null,2);renderAuth(e.data,e.status||0);}
  finally{document.body.classList.remove('is-requesting');button.disabled=false;if(state.mode==='tool')renderDiscovery();}
};

async function copy(text){try{await navigator.clipboard.writeText(text);toast('已复制');}catch{toast('无法访问剪贴板，请选中文本复制');}}
$('external-contract').onclick=()=>{
  const service=currentService(),url=location.origin+$('endpoint').textContent;
  let args=service?service.sample_arguments:sampleArgs(currentCap());
  if(state.page==='mcp'&&mcpClient.state.selected){try{args=selectedToolArguments();}catch{args=Object.fromEntries(NefMcp.fields(mcpClient.state.selected).map(f=>[f.name,f.schema.default??'']));}}
  const body=state.mode==='intent'?{text:service.intent_example}:state.mode==='tool'?{jsonrpc:'2.0',id:1,method:'tools/call',params:{name:mcpClient.state.selected?.name||state.capId,arguments:args}}:args;
  modal('外部接入信息',`<div class="status-label">请求地址</div><div class="code-box">POST ${esc(url)}</div><div class="status-label">请求头</div><div class="code-box">Authorization: Bearer &lt;AF_API_KEY&gt;\nX-NEF-Execution: ${service?state.executionMode:'live'}\nContent-Type: application/json</div><div class="status-label">请求体</div><div class="code-box">${esc(JSON.stringify(body,null,2))}</div><p class="dialog-note" style="margin-top:12px">${state.mode==='intent'?'按选定场景转发意图原文。':'API 与 Tool 可复用同一场景执行接口。'} demo 为示例结果，live 才发送至已配置的内部接口。</p>`);
};

function clearMedia(){state.mediaKey='';if(state.mediaUrl)URL.revokeObjectURL(state.mediaUrl);state.mediaUrl='';for(const id of ['mini-visual','board-visual'])$(id).innerHTML='<div class="empty-visual"><span class="visual-symbol">▧</span><strong>等待图像或视频</strong><span>由场景数据源推送</span></div>';}
function clearFeed(){state.events=[];state.lastSignature='';clearMedia();$('mini-status').textContent=$('board-status').textContent='等待回传';$('mini-data').textContent=$('board-data').textContent='—';$('event-list').replaceChildren();$('event-count').textContent='0 条';$('received-time').textContent='—';$('receiver-health').textContent='通道独立于调用结果';document.querySelector('.live-dot').classList.remove('connected');}
function matchingChannels(){return NefStory.feedbackChannels(state.channels,currentService()?.id||'');}
function syncChannelSelection(){
  const channels=matchingChannels();
  if(!channels.some(c=>c.id===state.channel)){state.channel=channels[0]?.id||'';state.epoch++;clearFeed();}
  renderChannels();
}
function renderChannels(){const channels=matchingChannels();$('channel-select').innerHTML=channels.length?channels.map(c=>`<option value="${esc(c.id)}" ${c.id===state.channel?'selected':''}>${esc(c.name)}</option>`).join(''):'<option value="">未连接数据源</option>';}
async function loadChannels(){if(!state.account)return;const d=await request('/api/v1/exhibition/channels');state.channels=d.channels;syncChannelSelection();await poll();}
$('channel-select').onchange=()=>{state.epoch++;state.channel=$('channel-select').value;clearFeed();poll();};
$('connect-source').onclick=()=>{
  if(!requireAccount())return;
  const service=currentService();
  modal('连接场景数据源',`<p class="dialog-note">${service?'为「'+esc(service.name)+'」生成专用 Key，回传自动进入本场景。':'为当前数据源生成专用 Key。'} 同事只需要一个地址和 Key，无需通道 ID。</p><div class="field"><label for="channel-name">数据源名称</label><input id="channel-name" maxlength="40" value="${esc(service?.name||'')}" placeholder="例如：园区巡检"></div><div class="dialog-actions"><button class="primary" id="create-channel">生成接入信息</button></div>`);
  $('create-channel').onclick=async()=>{
    const name=$('channel-name').value.trim();if(!name)return;
    const button=$('create-channel');button.disabled=true;
    try{
      const c=await request('/api/v1/exhibition/channels',{method:'POST',body:JSON.stringify({name,...(service?{service_id:service.id}:{})})});
      state.channel=c.id;state.epoch++;clearFeed();await loadChannels();
      const handoff=NefStory.feedbackHandoff(c,location.origin);
      modal('场景回传接入信息',`<p class="dialog-note">将地址和专用 Key 交给场景侧。Key 仅本次显示，服务重启后需重新生成；请勿在投屏时展开。对方需使用可访问的部署地址，不能使用你电脑的 localhost。</p><div class="status-label">统一回传地址 · JSON / 图片 / 视频</div><div class="code-box">POST ${esc(handoff.url)}</div><div class="status-label">专用接收凭证</div><div class="code-box">Authorization: Bearer ${esc(c.receiver_key)}</div><div class="status-label">状态回传 · Content-Type: application/json</div><div class="code-box">${esc(JSON.stringify(handoff.json_example,null,2))}</div><p class="dialog-note" style="margin-top:12px">图片、视频向同一地址直接上传文件原始字节，自动展示，无需再发布事件。设置对应 Content-Type；单文件上限 16 MiB，支持图片及 MP4 / WebM 文件，非直播流。</p><div class="dialog-actions"><button class="secondary" id="copy-channel">复制对接信息</button></div>`);
      $('copy-channel').onclick=()=>copy(JSON.stringify(handoff,null,2));
    }catch(e){button.disabled=false;toast(e.message);}
  };
};
function clock(ts){return new Date(ts*1000).toLocaleTimeString('zh-CN',{hour12:false});}
async function loadMedia(event,epoch){const key=state.channel+':'+event.asset_id;if(state.mediaKey===key)return;state.mediaKey=key;const channel=state.channel;try{const response=await fetch(`/api/v1/exhibition/channels/${encodeURIComponent(channel)}/media/${encodeURIComponent(event.asset_id)}`,{headers:{Authorization:'Bearer '+state.key}});if(!response.ok)throw new Error('媒体读取失败');const blob=await response.blob();if(epoch!==state.epoch||state.mediaKey!==key)return;const url=URL.createObjectURL(blob);if(state.mediaUrl)URL.revokeObjectURL(state.mediaUrl);state.mediaUrl=url;for(const id of ['mini-visual','board-visual']){const media=document.createElement(event.kind==='video'?'video':'img');media.src=url;if(event.kind==='video'){media.controls=true;media.preload='metadata';media.playsInline=true;}else media.alt=event.title||'场景回传图像';media.onerror=()=>{if(state.mediaKey===key)$(id).textContent='媒体无法解码，请核对文件格式';};$(id).replaceChildren(media);}}catch(e){if(epoch===state.epoch){state.mediaKey='';$('receiver-health').textContent=e.message;}}}
function renderEvents(events,epoch){state.events=events;const last=events.at(-1);$('received-time').textContent=last?clock(last.received_at):'—';$('event-count').textContent=events.length+' 条';const status=events.findLast(e=>e.kind==='status'),data=events.findLast(e=>e.kind==='data'),media=events.findLast(e=>e.kind==='image'||e.kind==='video');if(status){$('mini-status').textContent=[status.title,status.text].filter(Boolean).join(' · ')||'已收到状态';$('board-status').textContent=$('mini-status').textContent;}if(data){const text=data.data!==undefined?JSON.stringify(data.data,null,2):[data.title,data.text].filter(Boolean).join('\n');$('mini-data').textContent=text;$('board-data').textContent=text;}$('event-list').innerHTML=events.slice(-12).reverse().map(e=>`<div class="event-row"><time>${esc(clock(e.received_at))}</time><div><b>${esc(e.title||{status:'状态',data:'数据',image:'图像',video:'视频'}[e.kind])}</b><span> · ${esc(e.source||'场景数据源')}</span></div></div>`).join('');if(media)loadMedia(media,epoch);}
async function poll(){if(state.polling||!hasInvocation()||(currentService()&&state.executionMode==='demo')||!state.account||!state.channel)return;state.polling=true;const epoch=state.epoch;try{const data=await request(`/api/v1/exhibition/channels/${encodeURIComponent(state.channel)}/events`);if(epoch!==state.epoch)return;document.querySelector('.live-dot').classList.add('connected');$('receiver-health').textContent=data.events.length?'接收通道可用 · 数据按回传更新':'接收通道可用 · 等待场景推送';const signature=JSON.stringify(data.events);if(signature!==state.lastSignature){state.lastSignature=signature;renderEvents(data.events,epoch);}}catch(e){if(epoch===state.epoch){$('receiver-health').textContent='连接中断 · 保留最近回传';document.querySelector('.live-dot').classList.remove('connected');}}finally{state.polling=false;}}
async function start(){
  try{const [caps,info,services]=await Promise.all([request('/api/v1/capabilities'),request('/api/v1/exhibition/info'),request('/api/v1/services')]);state.caps=caps.capabilities;state.categories=caps.categories;state.info=info;state.services=services.services;
  $('scene-count').textContent=state.services.length;$('cap-count').textContent=state.caps.filter(c=>c.status==='available').length;$('category-count').textContent=Object.keys(state.categories).length;$('connection-label').textContent='场景服务 · 统一开放';renderScenes();renderMarket();await refreshAccount();await loadChannels();}
  catch(e){$('scene-grid').innerHTML='<p class="loading">'+esc(e.message)+'</p>';$('connection-label').textContent='平台暂不可用';}
  setInterval(poll,2000);
}

NefNetwork.init({request,esc,toast,modal,requireAccount,selectPage,account:()=>state.account,caps:()=>state.caps});
window.addEventListener('pagehide',()=>{state.epoch++;if(state.mediaUrl)URL.revokeObjectURL(state.mediaUrl);});start();
