/* Account-isolated external tool subscriptions; local fixture only. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const origin=process.argv[2],url=new URL(origin),runId=Date.now().toString(36);
assert.equal(url.hostname,'127.0.0.1');assert(url.port&&url.port!=='8069');
const output=path.resolve('.runtime/market-subscriptions-ui');fs.mkdirSync(output,{recursive:true});
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.NEF_TEST_BROWSER_CHANNEL?{channel:process.env.NEF_TEST_BROWSER_CHANNEL}:{})});
  try{
    for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
      const context=await browser.newContext({viewport}),page=await context.newPage(),errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      const users=[];
      for(const role of ['provider','buyer','other']){
        const response=await context.request.post(origin+'/api/v1/register',{data:{account:`${role}-${runId}-${viewport.width}`}});
        assert.equal(response.status(),200);users.push(await response.json());
      }
      const [provider,buyer,other]=users;
      const peer=(await (await context.request.get(origin+'/__fixture__/peer')).json()).url;
      const probe=async()=> (await (await context.request.get(peer+'/probe')).json()).requests;
      const trfWrites=async()=> (await probe()).filter(r=>r.path.startsWith('/trf/')&&r.method!=='GET').length;
      await page.goto(origin);
      await page.waitForFunction(()=>wb.scenes.length===3&&CAPS.length>0);
      await page.evaluate(async users=>{
        for(const user of users)accounts[user.account]={api_key:user.api_key};
        current=users[0].account;saveAccounts();await refreshAll();activateTab('afreg',true);
      },users);
      const switchTo=async user=>{
        await page.locator('#acct-select').selectOption(user.account);
        await page.waitForFunction(account=>current===account&&!wb.networkBusy, user.account);
      };
      await page.locator('#wb-server-name').fill('patrol-subs-'+runId+'-'+viewport.width);
      await page.locator('#wb-server-url').fill(peer+'/mcp');
      await page.locator('#wb-register-server').click();
      await page.waitForFunction(()=>wb.servers.some(s=>s.discovery_status==='discovered'));
      const serverId=await page.evaluate(()=>wb.servers[0].id);
      assert.equal(await page.getByRole('button',{name:'连接并发现工具',exact:true}).count(),1);
      assert.equal(await page.locator('[data-discover="'+serverId+'"]').innerText(),'重新发现工具');
      await page.locator('[data-publish-server="'+serverId+'"]').click();
      await page.waitForFunction(id=>wb.servers.find(s=>s.id===id)?.sync_status==='synced',serverId);
      const item=await page.evaluate(id=>wb.market.find(t=>t.server_id===id),serverId);
      const initialWrites=await trfWrites();
      await switchTo(buyer);
      await page.waitForFunction(()=>wb.servers.length===0);
      await page.evaluate(()=>activateTab('market',true));
      const card=page.locator('#wb-network-market .tile').filter({hasText:item.serverName});
      await card.waitFor();await card.click();
      assert.equal(await page.locator('#wb-subscribe-tool').isVisible(),true);
      assert.match(await page.locator('#wb-tool-state').innerText(),/尚未订阅/);
      await page.locator('#wb-subscribe-tool').click();
      await page.locator('#wb-use-tool').waitFor();
      assert.match(await page.locator('#wb-tool-message').innerText(),/当前账号订阅/);
      await page.locator('#wb-close-detail').click();
      assert.match(await card.innerText(),/已订阅/);
      await page.reload();
      await page.waitForFunction(id=>wb.toolSubscriptions.some(t=>t.id===id),item.id);
      await card.click();
      await page.locator('#wb-use-tool').click();
      await page.waitForFunction(name=>wbMcp.state.selected?.name===name,item.mcp_name);
      assert.equal(await page.locator('#mcp-call').isEnabled(),true);
      await page.locator('[data-mcp-param="frame_ref"]').fill('frame-ui-'+viewport.width);
      await page.locator('#mcp-call').click();
      await page.waitForFunction(()=>document.querySelector('#mcp-resp').textContent.includes('【本地 AF 回执】'));
      assert.match(await page.locator('#mcp-resp').innerText(),/已收到第三方工具回执/);
      assert.equal(await trfWrites(),initialWrites,'Subscribing or invoking must not republish to TRF');
      const request=JSON.parse((await probe()).findLast(r=>r.path==='/mcp'&&JSON.parse(r.body).method==='tools/call').body);
      assert.deepEqual(request.params,{name:'inspect_frame',arguments:{frame_ref:'frame-ui-'+viewport.width}});

      await page.evaluate(()=>activateTab('subs',true));
      const subCard=page.locator('[data-subs-tool="'+item.id+'"]');
      await subCard.waitFor();
      assert.match(await subCard.innerText(),/已订阅/);
      const cost=page.locator('#subs-content .stat').filter({hasText:'估算月费用'}).locator('b');
      assert.equal(await cost.innerText(),'¥0');
      const snapshot=await (await context.request.get(origin+'/api/v1/integration/subscriptions?account_id='+encodeURIComponent(buyer.account))).json();
      assert.equal(snapshot.external_tool_subscriptions[0].id,item.id);
      assert.equal(snapshot.external_tool_subscriptions[0].available,true);
      assert(!JSON.stringify(snapshot).includes(peer+'/mcp'));
      await subCard.click();
      await page.screenshot({path:path.join(output,'subscribed-'+viewport.width+'.png')});
      await page.locator('#wb-unsubscribe-tool').click();
      await page.locator('#wb-subscribe-tool').waitFor();
      assert.match(await page.locator('#wb-tool-message').innerText(),/已取消订阅/);
      assert.equal(await subCard.count(),0);
      await page.locator('#wb-subscribe-tool').click();
      await page.locator('#wb-use-tool').waitFor();
      await switchTo(other);
      assert.equal(await page.locator('#modal-bg').evaluate(el=>el.classList.contains('show')),false);
      await page.waitForFunction(()=>wb.toolSubscriptions.length===0);
      await page.evaluate(()=>activateTab('market',true));
      await card.click();
      assert.equal(await page.locator('#wb-subscribe-tool').isVisible(),true);
      await page.locator('#wb-close-detail').click();

      // The provider withdraws: buyer keeps a cancellable record but cannot call.
      const withdrawal=await context.request.post(origin+'/api/v1/network/servers/'+serverId+'/unpublish',{headers:{Authorization:'Bearer '+provider.api_key}});
      assert.equal((await withdrawal.json()).sync_status,'synced');
      await switchTo(buyer);
      await page.waitForFunction(id=>wb.toolSubscriptions.some(t=>t.id===id&&!t.available),item.id);
      await page.evaluate(()=>activateTab('subs',true));
      await subCard.waitFor();assert.match(await subCard.innerText(),/已下架/);
      await subCard.click();
      assert.equal(await page.locator('#wb-use-tool').isDisabled(),true);
      assert.equal(await page.locator('#wb-unsubscribe-tool').isEnabled(),true);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
      await page.screenshot({path:path.join(output,'withdrawn-'+viewport.width+'.png')});
      await page.locator('#wb-unsubscribe-tool').click();
      await page.waitForFunction(()=>wb.toolSubscriptions.length===0);
      assert.equal((await context.request.delete(origin+'/api/v1/network/servers/'+serverId,{headers:{Authorization:'Bearer '+provider.api_key}})).status(),200);
      assert.deepEqual(errors,[]);
      console.log(`External subscriptions UI passed: ${viewport.width}px; three accounts, purchase/cancel, MCP call, reload, monthly cost, query, withdrawal and distinct discovery buttons`);
      await context.close();
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
