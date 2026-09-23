/* Homepage taxonomy and explicit TRF synchronization. Reading the page never polls TRF. */
const wbTrf={
  source:document.body.classList.contains('ops')&&localStorage.getItem('nef_market_source')==='trf'?'trf':'local',
  snapshot:null,busy:false,message:'',revision:0,
};
const wbToolTypes=[
  {id:'nf tool',name:'网络功能能力',color:'#58a6ff',icon:'📶'},
  {id:'computing tool',name:'计算能力',color:'#bc8cff',icon:'⚡'},
  {id:'sensing tool',name:'感知能力',color:'#ff9e3d',icon:'👁️'},
  {id:'third-party tool',name:'第三方扩展能力',color:'#f0883e',icon:'🔧'},
];
const wbRegistrationLabels={
  registered:'已注册',unregistered:'未注册',unknown:'未核对',
  submitted:'待确认',failed:'同步失败',conflict:'同名冲突',
};
function wbTrfFailureText(item){
  if(!item?.sync_error)return '';
  const reasons={
    trf_schema_invalid:'GET 回包结构或字段不符合约定',
    trf_incomplete_list:'GET 返回了分页数据，需提供完整服务列表',
    trf_response_rejected:'TRF 回包表示请求失败',
    invalid_json:'TRF 返回的不是有效 JSON',
    unsupported_transport:'TRF 返回的 Content-Type 不是 JSON',
    upstream_http_error:'TRF 返回错误状态码',
    upstream_timeout:'连接 TRF 超时',
    upstream_request_failed:'无法连接 TRF，请核对地址及网络',
    redirect_not_allowed:'TRF 返回重定向，请配置最终集合地址',
    missing_operator_token:'TRF 鉴权凭证未配置',
    trf_name_conflict:'同名服务的地址、分类或第三方标识不同，未覆盖或删除',
    trf_legacy_group_url:'此前登记的 NEF 地址需要迁移；点击同步可更新',
    trf_confirmation_unknown:'请求已提交，GET 尚未确认结果',
    nef_base_not_configured:'NEF 对外访问地址未配置',
    trf_not_configured:'TRF 集合地址未配置',
    invalid_config:'登记配置无效',
  };
  const d=item.sync_diagnostic||{};
  const request=[d.method,d.http_status!=null?'HTTP '+d.http_status:''].filter(Boolean).join(' ');
  return (request?request+'：':'')+(reasons[item.sync_error]||'TRF 请求失败')+' ('+item.sync_error+')';
}
function wbRegistrationDot(status='unknown',item=null){
  const label=wbRegistrationLabels[status]||'未核对';
  const detail=wbTrfFailureText(item)||(item?.metadata_differences?.length?'登记已存在，以下字段不同或未返回：'+item.metadata_differences.join(', '):'');
  return `<span class="wb-registration wb-registration-${esc(status)}" title="TRF · ${esc(label)}${detail?' · '+esc(detail):''}" aria-label="TRF · ${esc(label)}"><span class="cat-dot"></span><span>${esc(label)}</span></span>`;
}
function wbLocalHomeCaps(){return CAPS.filter(c=>c.status==='available'&&c.category!=='ecosystem');}
function wbCapabilityAccess(info,id){
  if(!info)return {label:'',detail:'',available:false};
  const sources=info.capability_grant_sources?.[id]||[];
  const sceneNames=sources.filter(s=>s.startsWith('scene:')).map(s=>wb.scenes.find(scene=>scene.id===s.slice(6))?.name||s.slice(6));
  if(sceneNames.length)return {label:'套餐已包含',detail:'已由「'+sceneNames.join('」「')+'」开通，可直接使用，无需重复订阅。',available:true};
  if((info.direct_subscriptions||[]).includes(id))return {label:'已订阅',detail:'当前账号已单独订阅，可直接使用。',available:true};
  if((info.subscribed_capabilities||[]).includes(id))return {label:'套餐已包含',detail:'已由能力套餐开通，无需重复订阅。',available:true};
  if((info.entitled_capabilities||[]).includes(id))return {label:'等级已包含',detail:'当前账号等级已包含此能力，无需重复订阅。',available:true};
  return {label:'',detail:'',available:false};
}
function wbRenderHomeCatalog(){
  const remote=wbTrf.source==='trf',snap=wbTrf.snapshot;
  const caps=wbLocalHomeCaps(),tools=wb.market.filter(t=>t.kind==='tool');
  const items=remote?(snap?.remote_items||[]).map(t=>({...t,origin:'trf'})):
    [...caps.map(c=>({...c,...snap?.items?.find(s=>s.capability_id===c.id),origin:'cap'})),
     ...tools.map(t=>({...t,origin:'external'}))];
  const groupHtml=meta=>{
    const rows=items.filter(t=>t.toolType===meta.id);
    return `<section class="wb-home-group" data-tool-type="${esc(meta.id)}"><div class="cat-title"><span class="cat-dot" style="background:${meta.color}"></span>${esc(meta.name)} <small>${esc(meta.id)} · ${rows.length} 项</small></div><div class="tile-grid">${rows.map(t=>{
      const status=t.origin==='trf'?(['stale','failed'].includes(snap?.status)?'unknown':'registered'):t.registration_status||'unknown';
      const action=t.origin==='cap'?'data-home-cap':t.origin==='external'?'data-home-tool':'data-home-trf';
      const name=t.name,description=t.description||'暂无用途说明';
      const caption=t.origin==='cap'?t.standard_basis?.label||'NEF 网络能力':t.origin==='trf'?'TRF 服务目录':t.serverName||t.provider;
      const price=t.origin==='cap'?(wbCapabilityAccess(wb.authInfo,t.id).label||t.unit_price):t.origin==='trf'?(t.serverStatus==='active'?'服务已登记':'服务状态：'+t.serverStatus):wb.toolSubscriptions.some(s=>s.id===t.id)?'已订阅 · 演示免费':'演示免费 · 点击订阅';
      return `<button class="tile" ${action}="${esc(t.id)}"><div class="ticon">${t.icon||meta.icon}</div><div class="tname" title="${esc(name)}">${esc(name)}</div><span class="wb-standard-label">${esc(caption)}</span><p class="wb-tile-description">${esc(description)}</p><div class="tfoot">${wbRegistrationDot(status,t)}<span class="tprice">${esc(price)}</span></div></button>`;
    }).join('')||'<p class="muted">暂无能力</p>'}</div></section>`;
  };
  $('#cap-list').innerHTML=wbToolTypes.slice(0,3).map(groupHtml).join('');
  $('#wb-network-market').innerHTML=groupHtml(wbToolTypes[3]);
  if(!remote){
    const packages=wb.market.filter(t=>t.kind==='package');
    if(packages.length)$('#wb-network-market').insertAdjacentHTML('beforeend','<h3 class="sec">自助编排套餐</h3><div class="tile-grid">'+packages.map(t=>`<button class="tile" data-home-tool="${esc(t.id)}"><div class="ticon">📦</div><div class="tname">${esc(t.name)}</div><p class="wb-tile-description">${esc(t.description)}</p><small class="muted">本地套餐定义</small></button>`).join('')+'</div>');
  }
  $$('#pane-market [data-home-cap]').forEach(b=>b.onclick=()=>showCap(b.dataset.homeCap));
  $$('#pane-market [data-home-tool]').forEach(b=>b.onclick=()=>wbShowNetworkTool(b.dataset.homeTool));
  $$('#pane-market [data-home-trf]').forEach(b=>b.onclick=()=>wbShowTrfRecord(b.dataset.homeTrf));
  if($('#wb-home-cap-count'))$('#wb-home-cap-count').textContent=items.length;
  if($('#wb-af-count'))$('#wb-af-count').textContent=new Set(tools.map(t=>t.server_id)).size;
  wbRenderTrfControls();
}
function wbShowTrfRecord(id){
  const item=wbTrf.snapshot?.remote_items?.find(t=>t.id===id);if(!item)return;
  showModal(`<h2>${esc(item.name)}</h2><p>${esc(item.description)}</p><p class="muted">${esc(item.toolType)} · ${esc(item.serverType)} · ${esc(item.serverStatus)}</p><p>这是从 TRF 读取的服务登记，尚未发现工具参数，不代表已获得调用权益。</p><div class="wb-modal-actions"><button id="wb-trf-detail-close">关闭</button></div>`);
  $('#wb-trf-detail-close').onclick=hideModal;
}
function wbRenderTrfControls(){
  const snap=wbTrf.snapshot,busy=wbTrf.busy||snap?.busy,remote=wbTrf.source==='trf';
  $('#wb-home-source').value=wbTrf.source;
  $('#wb-trf-publish').hidden=$('#wb-trf-withdraw').hidden=remote;
  $('#wb-trf-publish').disabled=!!busy||!snap?.configured||!snap?.base_configured;
  $('#wb-trf-withdraw').disabled=!!busy||!(snap?.can_withdraw||(snap?.configured&&snap?.base_configured));
  $('#wb-trf-read').disabled=!!busy||!snap?.configured;
  $('#wb-trf-read').textContent=remote?'刷新目录':'核对状态';
  const counts=snap?.summary;
  let summary='尚未核对';
  if(counts){
    const state=[];
    if(counts.registered||(!counts.unknown&&!counts.failed))state.push(`已注册 ${counts.registered} 个`);
    if(counts.unregistered)state.push(`未注册 ${counts.unregistered} 个`);
    if(counts.unknown)state.push(`待确认 ${counts.unknown} 个`);
    if(counts.failed)state.push(`失败或冲突 ${counts.failed} 个`);
    summary=`MCP Server ${counts.total} 个 · ${state.join(' · ')} · 覆盖能力 ${snap.capability_summary?.total||0} 项`;
  }
  $('#wb-home-trf-summary').textContent=remote?`TRF 目录 ${snap?.remote_items?.length||0} 项${snap?.ignored_count?' · 未识别类型 '+snap.ignored_count+' 项未展示':''}`:summary;
  let note=remote?'仅展示服务登记，不自动开通调用权限。':'';
  if(!snap?.configured)note+=' TRF 地址待配置。';
  else if(!remote&&!snap.base_configured)note+=' 还需配置本 NEF 的访问地址，供 TRF 调用这些能力（registry.nef_base_url）。';
  if(snap?.last_checked)note+=' 上次 GET 读到 '+(snap.remote_items.length+(snap.ignored_count||0))+' 条服务；核对时间：'+new Date(typeof snap.last_checked==='number'?snap.last_checked*1000:snap.last_checked).toLocaleString()+'。';
  if(snap?.legacy_items?.length)note+=' 检测到 '+snap.legacy_items.length+' 条旧版逐能力登记；取消注册会一并撤回已核对归属的旧记录。';
  const records=[...(snap?.groups||[]),...(snap?.legacy_items||[])];
  const failures=[...new Set(records.filter(i=>i.sync_error).map(wbTrfFailureText))];
  if(failures.length)note+=' '+failures.slice(0,3).join('；');
  const drift=(snap?.groups||[]).filter(group=>group.metadata_differences?.length);
  if(drift.length)note+=' '+drift.map(group=>group.name+'已注册，以下字段不同或未返回：'+group.metadata_differences.join(', ')).join('；');
  $('#wb-home-trf-note').textContent=note;
  $('#wb-home-trf-message').textContent=wbTrf.message;
}
async function wbLoadTrfCatalog(){
  const revision=wbTrf.revision;
  const response=await fetch('/api/v1/network/trf/catalog',{cache:'no-store'});
  if(!response.ok)throw new Error('能力同步状态读取失败');
  const snapshot=await response.json();if(revision!==wbTrf.revision||wbTrf.busy)return;
  wbTrf.snapshot=snapshot;wbRenderHomeCatalog();
}
async function wbTrfAction(action){
  if(!apiKey())return toast('请先注册或选择账号',false);
  if(wbTrf.busy)return;
  const epoch=wb.epoch;wbTrf.revision++;wbTrf.busy=true;wbTrf.message=action==='refresh'?'正在核对注册状态…':'正在逐项处理，请稍候…';wbRenderTrfControls();
  try{
    wbTrf.snapshot=await api('/api/v1/network/trf/catalog/'+action,{method:'POST'});
    if(epoch!==wb.epoch){wbTrf.message='';return;}
    const s=wbTrf.snapshot,failed=[...(s.groups||[]),...(s.legacy_items||[])].filter(i=>i.sync_error||['failed','conflict','submitted'].includes(i.registration_status));
    wbTrf.message=s.status==='not_configured'?'配置尚未完成，未发送 TRF 请求。':
      action==='unpublish'&&s.can_withdraw?'仍有登记未能确认撤回（可能在之前的 TRF 地址），请查看下方错误或核对对端记录。':
      failed.length?`${failed.length} 项失败或尚待确认，请查看卡片状态后重试。`:
      s.status==='failed'||s.status==='stale'?'状态核对未完成，保留上次记录。':
      action==='refresh'?'注册状态已更新。':action==='publish'?'同步处理完成，请查看登记状态。':'撤回处理完成，请查看登记状态。';
    wbRenderHomeCatalog();
  }catch(e){if(epoch===wb.epoch)wbTrf.message=wbMessage(e);}
  finally{wbTrf.busy=false;wbRenderTrfControls();}
}
$('#wb-home-source').onchange=e=>{
  wbTrf.source=e.target.value;localStorage.setItem('nef_market_source',wbTrf.source);wbTrf.message='';wbRenderHomeCatalog();
};
$('#wb-trf-read').onclick=()=>wbTrfAction('refresh');
$('#wb-trf-publish').onclick=()=>wbTrfAction('publish');
$('#wb-trf-withdraw').onclick=()=>{
  showModal('<h2>取消内部 MCP Server 的 TRF 注册</h2><p>撤回三个分类的登记及能核对归属的旧版逐能力登记。不删除第三方服务，也不取消账号订阅。</p><div class="wb-modal-actions"><button id="wb-trf-keep">保留</button><button id="wb-trf-confirm-withdraw">确认撤回</button></div>');
  $('#wb-trf-keep').onclick=hideModal;
  $('#wb-trf-confirm-withdraw').onclick=()=>{hideModal();wbTrfAction('unpublish');};
};
