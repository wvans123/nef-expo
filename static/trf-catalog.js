/* Homepage taxonomy and explicit TRF synchronization. Reading the page never polls TRF. */
const wbTrf={
  source:localStorage.getItem('nef_market_source')==='trf'?'trf':'local',
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
function wbRegistrationDot(status='unknown'){
  const label=wbRegistrationLabels[status]||'未核对';
  return `<span class="wb-registration wb-registration-${esc(status)}" title="TRF · ${esc(label)}" aria-label="TRF · ${esc(label)}"><span class="cat-dot"></span><span>${esc(label)}</span></span>`;
}
function wbLocalHomeCaps(){return CAPS.filter(c=>c.status==='available'&&c.category!=='ecosystem');}
function wbRenderHomeCatalog(){
  const remote=wbTrf.source==='trf',snap=wbTrf.snapshot;
  const caps=wbLocalHomeCaps(),tools=wb.market.filter(t=>t.kind==='tool');
  const items=remote?(snap?.remote_items||[]).map(t=>({...t,origin:'trf'})):
    [...caps.map(c=>({...c,origin:'cap',registration_status:snap?.items?.find(s=>s.capability_id===c.id)?.registration_status||'unknown'})),
     ...tools.map(t=>({...t,origin:'external'}))];
  const groupHtml=meta=>{
    const rows=items.filter(t=>t.toolType===meta.id);
    return `<section class="wb-home-group" data-tool-type="${esc(meta.id)}"><div class="cat-title"><span class="cat-dot" style="background:${meta.color}"></span>${esc(meta.name)} <small>${esc(meta.id)} · ${rows.length} 项</small></div><div class="tile-grid">${rows.map(t=>{
      const status=t.origin==='trf'?(['stale','failed'].includes(snap?.status)?'unknown':'registered'):t.registration_status||'unknown';
      const action=t.origin==='cap'?'data-home-cap':t.origin==='external'?'data-home-tool':'data-home-trf';
      const name=t.name,description=t.description||'暂无用途说明';
      const caption=t.origin==='cap'?t.standard_basis?.label||'NEF 网络能力':t.origin==='trf'?'TRF 服务目录':t.serverName||t.provider;
      const price=t.origin==='cap'?t.unit_price:t.origin==='trf'?(t.serverStatus==='active'?'服务已登记':'服务状态：'+t.serverStatus):wb.toolSubscriptions.some(s=>s.id===t.id)?'已订阅 · 演示免费':'演示免费 · 点击订阅';
      return `<button class="tile" ${action}="${esc(t.id)}"><div class="ticon">${t.icon||meta.icon}</div><div class="tname" title="${esc(name)}">${esc(name)}</div><span class="wb-standard-label">${esc(caption)}</span><p class="wb-tile-description">${esc(description)}</p><div class="tfoot">${wbRegistrationDot(status)}<span class="tprice">${esc(price)}</span></div></button>`;
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
  $('#wb-trf-withdraw').disabled=!!busy||!snap?.can_withdraw;
  $('#wb-trf-read').disabled=!!busy||!snap?.configured;
  const counts=snap?.summary;
  const summary=counts?`本地能力 ${counts.total} 项 · 已注册 ${counts.registered} 项`:'尚未核对';
  $('#wb-home-trf-summary').textContent=remote?`TRF 目录 ${snap?.remote_items?.length||0} 项${snap?.ignored_count?' · 未识别类型 '+snap.ignored_count+' 项未展示':''}`:summary;
  let note=remote?'仅展示四类服务登记；读取不会注册、订阅或自动连接服务。':'同步所有已开放的本地能力；场景套餐和第三方发布由各自入口管理。';
  if(!snap?.configured)note+=' TRF 地址待配置。';
  else if(!remote&&!snap.base_configured)note+=' NEF 对外访问地址待配置。';
  if(snap?.last_checked)note+=' 上次核对：'+new Date(typeof snap.last_checked==='number'?snap.last_checked*1000:snap.last_checked).toLocaleString();
  if(snap?.status==='failed'||snap?.status==='stale')note+=' 读取失败，当前显示上次记录。';
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
  const epoch=wb.epoch;wbTrf.revision++;wbTrf.busy=true;wbTrf.message=action==='refresh'?'正在读取 TRF…':'正在逐项处理，请稍候…';wbRenderTrfControls();
  try{
    wbTrf.snapshot=await api('/api/v1/network/trf/catalog/'+action,{method:'POST'});
    if(epoch!==wb.epoch){wbTrf.message='';return;}
    const s=wbTrf.snapshot,failed=(s.items||[]).filter(i=>['failed','conflict','submitted'].includes(i.registration_status));
    wbTrf.message=action==='unpublish'&&s.can_withdraw?'仍有登记未能确认撤回（可能在之前的 TRF 地址），请重试或核对对端记录。':
      failed.length?`${failed.length} 项失败或尚待确认，请查看卡片状态后重试。`:
      s.status==='failed'||s.status==='stale'?'TRF 读取未完成，保留上次记录。':
      action==='refresh'?'已读取 TRF 目录与登记状态。':action==='publish'?'同步处理完成，状态以 TRF 读回为准。':'已处理撤回，状态以 TRF 读回为准。';
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
  showModal('<h2>取消本地能力的 TRF 注册</h2><p>仅撤回本平台登记的本地能力，不删除第三方服务，也不取消账号订阅。</p><div class="wb-modal-actions"><button id="wb-trf-keep">保留</button><button id="wb-trf-confirm-withdraw">确认撤回</button></div>');
  $('#wb-trf-keep').onclick=hideModal;
  $('#wb-trf-confirm-withdraw').onclick=()=>{hideModal();wbTrfAction('unpublish');};
};
