/* Demo account handoff only; callback destinations never come from browser input. */
function purchaseCapabilitySelector(ids){
  const caps=ids.map(id=>CAPS.find(c=>c.id===id&&c.status==='available')).filter(Boolean);
  if(!caps.length)return '';
  return '<fieldset id="purchase-capabilities"><legend>网络能力组合</legend>'+caps.map(c=>`<label><input type="checkbox" value="${esc(c.id)}" checked><span>${esc(c.name)}</span></label>`).join('')+'</fieldset>';
}
function purchaseCapabilityIds(){
  return Array.from(document.querySelectorAll('#purchase-capabilities input:checked'),input=>input.value);
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
  const labels={delivered:'订购完成，套餐已发送',submitted:'订购完成，对接平台尚未确认接收',not_configured:'订购完成，通知配置待补全',failed:'订购完成，通知发送失败',sending:'订购完成，通知发送中',not_applicable:'订阅完成'};
  text.textContent=labels[notification?.status]||'订购完成，通知功能待加载';
  if(notification?.event_id)text.textContent+=' · '+notification.event_id;
  if(notification?.event_id&&['failed','submitted','not_configured'].includes(notification.status)){
    button.hidden=false;const account=current;
    button.onclick=async()=>{button.disabled=true;try{
      const result=await api('/api/v1/integration/notifications/'+encodeURIComponent(notification.event_id)+'/retry',{method:'POST'});
      if(current===account)purchaseNotice(result);
    }catch(e){if(current===account)text.textContent='通知重试失败：'+wbMessage(e);}finally{button.disabled=false;}};
  }
}
