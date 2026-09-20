/* Demo account handoff only; callback destinations never come from browser input. */
function purchaseCapabilitySelector(ids){
  const caps=ids.map(id=>CAPS.find(c=>c.id===id&&c.status==='available')).filter(Boolean);
  if(!caps.length)return '';
  return '<fieldset id="purchase-capabilities"><legend>网络能力组合</legend>'+caps.map(c=>`<label><input type="checkbox" value="${esc(c.id)}" checked><span>${esc(c.name)}</span></label>`).join('')+'</fieldset>';
}
function purchaseCapabilityIds(){
  return Array.from(document.querySelectorAll('#purchase-capabilities input:checked'),input=>input.value);
}
function purchaseUnitPrice(id){
  const value=String(CAPS.find(c=>c.id===id)?.unit_price||'').match(/\d+(?:\.\d+)?/);
  return value?Number(value[0]):0;
}
function purchaseQuote(scene,ids){
  const original=ids.reduce((sum,id)=>sum+Math.round(purchaseUnitPrice(id)*100),0)/100;
  const discount=scene.discount;
  return {price:discount==null?scene.price:Math.round((original*discount+Number.EPSILON)*100)/100,original,discount};
}
function purchaseQuoteText(q){
  if(q.price==null)return '价格待配置';
  return '¥'+q.price+' / 月'+(q.discount==null?'':' · 原价 ¥'+q.original+' · '+Number((q.discount*10).toFixed(2))+' 折');
}
async function purchaseBootstrap(){
  const params=new URLSearchParams(location.search),values=params.getAll('account_id');
  if(!values.length)return;
  if(values.length!==1||!/^\d{1,32}$/.test(values[0])){
    current='';saveAccounts();throw new Error('跳转账号编号无效');
  }
  const id=values[0];current='';saveAccounts();
  const response=await fetch('/api/v1/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account:id})});
  const data=await response.json();
  if(!response.ok||data.account!==id||!data.api_key)throw new Error('无法接入跳转账号');
  accounts[id]={api_key:data.api_key};current=id;saveAccounts();
}
function purchaseNotice(notification){
  const box=$('#purchase-notice'),text=$('#purchase-notice-text'),button=$('#purchase-notice-retry');
  box.hidden=false;button.hidden=true;
  text.textContent=notification?.action==='delete'?'已取消开通':notification?.status==='delivered'?'订购完成，已同步至合作平台':'订购完成';
  const detail=$('#purchase-notice-detail');
  detail.textContent=[notification?.status,notification?.code,notification?.http_status,notification?.event_id].filter(x=>x!=null).join(' · ');
  if(notification?.event_id&&['failed','submitted','not_configured'].includes(notification.status)){
    button.hidden=false;const account=current;
    button.onclick=async()=>{button.disabled=true;try{
      const result=await api('/api/v1/integration/notifications/'+encodeURIComponent(notification.event_id)+'/retry',{method:'POST'});
      if(current===account)purchaseNotice(result);
    }catch(e){if(current===account)detail.textContent='通知重试失败：'+wbMessage(e);}finally{button.disabled=false;}};
  }
}
