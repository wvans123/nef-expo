/* Network registry console. Operator-approved connections only; no simulated discovery. */
(function(root){
  'use strict';
  let ctx, generation=0;
  const store={items:[],servers:[],packages:[],steps:[],status:'not_configured',query:'',owner:null};
  const $=id=>document.getElementById(id), esc=x=>ctx.esc(x);
  const labels={pending:'待发布',submitted:'已提交 · 待确认',synced:'已同步',failed:'失败',not_configured:'待配置网络接口',not_discovered:'未发现',discovered:'已发现'};
  function status(value){return labels[value]||value||'待处理';}
  function message(id,text){$(id).textContent=text;}
  function reset(){generation++;store.items=[];store.servers=[];store.packages=[];store.steps=[];store.status='not_configured';store.owner=ctx.account()?.account||null;render();}
  function sources(){
    return [...ctx.caps().filter(c=>c.status==='available').map(c=>({id:c.id,name:c.name,origin:'基础能力'})),
      ...store.items.filter(c=>c.kind==='tool').map(c=>({...c,origin:'网络目录'})),
      ...store.servers.flatMap(s=>(s.discovery_status==='discovered'?s.tools:[]).map(t=>({id:s.id+':'+t.name,name:t.name,origin:s.name})))];
  }
  async function reload(){
    if(!ctx.account()){reset();return;}
    if(store.owner!==ctx.account().account)reset();
    const epoch=generation;
    const results=await Promise.all(['/catalog','/servers','/packages'].map(p=>ctx.request('/api/v1/network'+p)));
    if(epoch!==generation)return;
    store.items=results[0].items;store.status=results[0].status;store.servers=results[1].servers;store.packages=results[2].packages;render();
  }
  async function action(button,messageId,fn){
    if(!ctx.requireAccount())return;
    const epoch=generation;button.disabled=true;message(messageId,'正在处理…');
    try{const result=await fn();if(epoch!==generation)return;await reload();if(epoch===generation)message(messageId,result||'已更新');}
    catch(e){if(epoch===generation){try{await reload();}catch{}if(epoch===generation)message(messageId,e.message);}}
    finally{button.disabled=false;}
  }
  function render(){
    $('network-catalog-status').textContent=ctx.account()?status(store.status):'接入后同步网络目录';
    $('network-item-count').textContent=store.items.length+' 项网络记录 · '+store.packages.length+' 个自建套餐';
    $('network-items').innerHTML=[...store.items.map(item=>`<article class="cap-card registry-card"><span class="eyebrow">TRF · ${item.kind==='package'?'PACKAGE':'TOOL'}</span><h3>${esc(item.name)}</h3><p>${esc(item.description)}</p><code>${esc(item.id)}</code><button class="secondary" data-network-detail="${esc(item.id)}">查看能力声明 ↗</button></article>`),...store.packages.map(p=>`<article class="cap-card registry-card"><span class="eyebrow">CUSTOM PACKAGE</span><h3>${esc(p.name)}</h3><p>${esc(p.description)}</p><span class="small-tag">${esc(status(p.sync_status))}</span><button class="secondary" data-package-detail="${esc(p.id)}">查看套餐定义 ↗</button></article>`)].join('')||'<p class="empty-registry">网络目录待同步。上方场景套餐与基础能力仍可独立体验。</p>';
    $('network-items').querySelectorAll('[data-network-detail]').forEach(b=>b.onclick=()=>{
      const item=store.items.find(x=>x.id===b.dataset.networkDetail);
      ctx.modal(item.name,`<p class="dialog-note">来自网络目录的${item.kind==='package'?'套餐':'工具'}声明。目录同步不自动授予使用权；实际执行与权益接口待对接。</p><pre>${esc(JSON.stringify(item,null,2))}</pre>`);
    });
    $('network-items').querySelectorAll('[data-package-detail]').forEach(b=>b.onclick=()=>{ctx.selectPage('compose');$('package-list').scrollIntoView({block:'center'});});
    renderSources();renderSteps();renderPackages();renderServers();
  }
  function renderSources(){
    const list=sources().filter(s=>(s.name+' '+s.id+' '+s.origin).toLowerCase().includes(store.query.toLowerCase()));
    $('compose-source-count').textContent=sources().length+' 项';
    $('compose-sources').innerHTML=list.map(c=>`<button class="compose-source" data-add-step="${esc(c.id)}" ${store.steps.some(x=>x.capability_id===c.id)?'disabled':''}><span><strong>${esc(c.name)}</strong><small>${esc(c.origin)}</small></span><b>＋</b></button>`).join('')||'<p class="empty-registry">没有匹配的可编排能力</p>';
    $('compose-sources').querySelectorAll('[data-add-step]').forEach(b=>b.onclick=()=>{if(store.steps.length>=12){ctx.toast('一个套餐最多 12 个步骤');return;}store.steps.push({capability_id:b.dataset.addStep});renderSteps();renderSources();});
  }
  function renderSteps(){
    $('compose-steps').innerHTML=store.steps.map((s,i)=>`<div class="compose-step"><b>${String(i+1).padStart(2,'0')}</b><span>${esc(sources().find(c=>c.id===s.capability_id)?.name||s.capability_id)}</span><button data-up="${i}" ${i===0?'disabled':''} aria-label="上移第 ${i+1} 步">↑</button><button data-remove="${i}" aria-label="移除第 ${i+1} 步">×</button></div>`).join('')||'<div class="compose-placeholder">← 从左侧添加能力<br><small>按业务顺序组合你的套餐</small></div>';
    $('compose-steps').querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{store.steps.splice(Number(b.dataset.remove),1);renderSteps();renderSources();});
    $('compose-steps').querySelectorAll('[data-up]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.up);[store.steps[i-1],store.steps[i]]=[store.steps[i],store.steps[i-1]];renderSteps();});
  }
  function renderPackages(){
    $('package-list').innerHTML=store.packages.map(p=>`<article class="registry-entry"><div class="registry-entry-head"><div><span class="eyebrow">NETWORK EXECUTION PACKAGE</span><h3>${esc(p.name)}</h3></div><span class="small-tag">${esc(status(p.sync_status))}</span></div><p>${esc(p.description)}</p><div class="package-chain">${p.steps.map(s=>`<span>${esc(sources().find(c=>c.id===s.capability_id)?.name||s.capability_id)}</span>`).join('<b>→</b>')}</div><div class="registry-actions"><button class="secondary" data-publish-package="${esc(p.id)}">同步 TRF ↗</button><details><summary>套餐 JSON</summary><pre>${esc(JSON.stringify(p,null,2))}</pre></details></div></article>`).join('')||'<p class="empty-registry">保存套餐后，在这里查看定义与发布状态。</p>';
    $('package-list').querySelectorAll('[data-publish-package]').forEach(b=>b.onclick=()=>action(b,'compose-message',async()=>{const r=await ctx.request('/api/v1/network/packages/'+encodeURIComponent(b.dataset.publishPackage)+'/sync',{method:'POST'});return '套餐发布：'+status((r.package||r).sync_status);}));
  }
  function renderServers(){
    $('server-list').innerHTML=store.servers.map(s=>`<article class="registry-entry"><div class="registry-entry-head"><div><span class="eyebrow">MCP SERVER</span><h3>${esc(s.name)}</h3><code>${esc(s.url)}</code></div><div class="registry-badges"><span class="small-tag">${esc(status(s.discovery_status))} · ${s.tools.length} tools</span><span class="small-tag">${esc(status(s.sync_status))}</span></div></div><p>${esc(s.description)}</p><div class="registry-actions"><button class="primary" data-discover-server="${esc(s.id)}">连接并发现工具</button><button class="secondary" data-sync-server="${esc(s.id)}">同步 TRF ↗</button></div><div class="provider-tools">${s.discovery_status==='discovered'?s.tools.map(t=>`<details><summary><b>${esc(t.name)}</b><span>${esc(t.description||'MCP 工具')}</span></summary><pre>${esc(JSON.stringify(t.inputSchema,null,2))}</pre></details>`).join(''):'<p class="muted">尚无本次有效发现结果</p>'}</div></article>`).join('')||'<p class="empty-registry">暂无能力源。提交上方 JSON 完成注册。</p>';
    $('server-list').querySelectorAll('[data-discover-server]').forEach(b=>b.onclick=()=>action(b,'federation-message',async()=>{await ctx.request('/api/v1/network/servers/'+encodeURIComponent(b.dataset.discoverServer)+'/discover',{method:'POST'});return '工具发现完成，目录来自该 MCP Server 的真实响应。';}));
    $('server-list').querySelectorAll('[data-sync-server]').forEach(b=>b.onclick=()=>action(b,'federation-message',async()=>{const r=await ctx.request('/api/v1/network/servers/'+encodeURIComponent(b.dataset.syncServer)+'/sync',{method:'POST'});return '注册发布：'+status((r.server||r).sync_status);}));
  }
  function init(context){
    ctx=context;
    $('network-refresh').onclick=()=>action($('network-refresh'),'network-catalog-status',async()=>{await ctx.request('/api/v1/network/catalog/refresh',{method:'POST'});return '网络目录已同步';});
    $('network-reload').onclick=()=>action($('network-reload'),'federation-message',async()=>{await reload();return '已读取当前登记状态';});
    $('compose-search').oninput=()=>{store.query=$('compose-search').value;renderSources();};
    $('compose-clear').onclick=()=>{store.steps=[];renderSteps();renderSources();};
    $('package-save').onclick=()=>action($('package-save'),'compose-message',async()=>{
      const name=$('package-name').value.trim();if(!name)throw new Error('请填写套餐名称');if(!store.steps.length)throw new Error('请至少选择一个能力');
      await ctx.request('/api/v1/network/packages',{method:'POST',body:JSON.stringify({name,description:$('package-description').value,steps:store.steps,execution_target:'network'})});
      store.steps=[];$('package-name').value='';$('package-description').value='';return '套餐定义已保存，可继续发布到网络目录。';
    });
    $('server-register').onclick=()=>action($('server-register'),'federation-message',async()=>{
      let body;try{body=JSON.parse($('server-json').value);}catch{throw new Error('JSON 格式有误，请检查引号和逗号');}
      await ctx.request('/api/v1/network/servers',{method:'POST',body:JSON.stringify(body)});return 'MCP Server 已登记。下一步：连接并发现工具。';
    });
    reset();
  }
  root.NefNetwork={init,reload,reset,render};
})(globalThis);
