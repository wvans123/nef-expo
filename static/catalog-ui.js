/* Local catalog export only. Imported records and private AF tools stay separate. */
function wbOpenCatalogPublication(){
  if(!apiKey())return toast('请先在顶栏注册或选择账号',false);
  const choices=(items,kind)=>items.map(item=>`<label><input type="checkbox" data-catalog-kind="${kind}" value="${esc(item.id)}"><span>${esc(item.name)}<small>${esc(item.id)}</small></span></label>`).join('');
  showModal(`<section id="wb-catalog-publication">
    <h2>发布 NEF 目录</h2>
    <div class="wb-catalog-choices">
      <fieldset><legend>原子能力</legend>${choices(CAPS.filter(c=>c.status==='available'),'capability')}</fieldset>
      <fieldset><legend>场景套餐</legend>${choices(wb.scenes,'service')}</fieldset>
    </div>
    <details id="wb-catalog-payload" hidden><summary>发布正文</summary><pre id="wb-catalog-json"></pre></details>
    <p id="wb-catalog-message" role="status">未选择目录项</p>
    <div class="wb-modal-actions"><button id="wb-catalog-close">关闭</button><button id="wb-catalog-preview" disabled>预览正文</button><button id="wb-catalog-publish" class="primary" disabled>发布目录</button></div>
  </section>`);
  const root=$('#wb-catalog-publication'),epoch=wb.epoch,key=apiKey(),account=current;
  const inputs=Array.from(root.querySelectorAll('input[data-catalog-kind]'));
  const preview=root.querySelector('#wb-catalog-preview'),publish=root.querySelector('#wb-catalog-publish');
  const message=root.querySelector('#wb-catalog-message'),payload=root.querySelector('#wb-catalog-payload'),json=root.querySelector('#wb-catalog-json');
  let version=0,busy=false,previewSelection=null;
  const active=()=>root===$('#wb-catalog-publication')&&$('#modal-bg').classList.contains('show')&&epoch===wb.epoch&&account===current&&key===apiKey();
  const selection=()=>({
    capability_ids:inputs.filter(x=>x.checked&&x.dataset.catalogKind==='capability').map(x=>x.value),
    service_ids:inputs.filter(x=>x.checked&&x.dataset.catalogKind==='service').map(x=>x.value)
  });
  function controls(){
    const body=selection(),stamp=JSON.stringify(body),empty=!body.capability_ids.length&&!body.service_ids.length;
    inputs.forEach(x=>x.disabled=busy);
    preview.disabled=busy||empty||!active();
    publish.disabled=busy||empty||previewSelection!==stamp||!active();
  }
  inputs.forEach(input=>input.onchange=()=>{
    version++;previewSelection=null;payload.hidden=true;json.textContent='';
    const body=selection(),count=body.capability_ids.length+body.service_ids.length;
    message.textContent=count?'已选择 '+count+' 项':'未选择目录项';controls();
  });
  async function request(send){
    if(!active()||busy)return;
    const body=selection(),stamp=JSON.stringify(body),revision=version;
    if(!body.capability_ids.length&&!body.service_ids.length)return;
    if(send&&previewSelection!==stamp)return;
    busy=true;previewSelection=null;controls();
    message.textContent=send?'正在发布…':'正在生成预览…';
    if(!send){payload.hidden=true;json.textContent='';}
    try{
      const result=await api('/api/v1/network/catalog/'+(send?'publish':'publication'),{method:'POST',body:stamp});
      if(!active()||revision!==version)return;
      if(send){
        message.textContent=(result.sync_status==='synced'&&result.accepted===true?'已同步 · 对方已确认':'已提交 · 待对方确认')+' · '+result.item_count+' 项';
      }else{
        json.textContent=jfmt(result);payload.hidden=false;payload.open=true;
        previewSelection=stamp;message.textContent='预览已生成 · '+result.items.length+' 项';
      }
    }catch(error){
      if(active()&&revision===version)message.textContent=(send?'发布未确认：':'预览失败：')+wbMessage(error);
    }finally{
      busy=false;if(active())controls();
    }
  }
  root.querySelector('#wb-catalog-close').onclick=hideModal;
  preview.onclick=()=>request(false);publish.onclick=()=>request(true);
}
window.wbCatalogClose=()=>{if($('#wb-catalog-publication'))hideModal();};
$('#wb-open-catalog-publication').onclick=wbOpenCatalogPublication;
