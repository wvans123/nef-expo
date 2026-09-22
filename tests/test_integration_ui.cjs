/* Run only against tests/workbench_fixture.py, never the live demo service. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const origin=process.argv[2],url=new URL(origin);
const runId=Date.now().toString(36);
assert.equal(url.hostname,'127.0.0.1');
assert(url.port&&url.port!=='8069','Use an isolated fixture port');
const output=path.resolve('.runtime/integration-ui');
fs.mkdirSync(output,{recursive:true});

(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.NEF_TEST_BROWSER_CHANNEL?{channel:process.env.NEF_TEST_BROWSER_CHANNEL}:{})});
  try{
    for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
      const context=await browser.newContext({viewport}),page=await context.newPage(),errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.goto(origin);
      await page.waitForFunction(()=>wb.scenes.length===3&&CAPS.length>0);
      assert.deepEqual(await page.evaluate(()=>wb.scenes.map(s=>s.price)),[115.68,119.76,119.6]);
      assert.equal(await page.locator('.wb-trf-management').isVisible(),false);
      assert.doesNotMatch(await page.locator('#pane-market').innerText(),/ARF|网络与自建目录/);
      const peer=(await (await context.request.get(origin+'/__fixture__/peer')).json()).url;
      assert.equal(new URL(peer).hostname,'127.0.0.1');
      const probe=async()=> (await (await context.request.get(peer+'/probe')).json()).requests;

      // Open feedback is readable even without an account or subscription.
      const marker='Shared result '+viewport.width;
      const feedback=await context.request.post(origin+'/api/v1/scene-feedback/traffic_flow_detection',{data:{final_result:marker}});
      assert.equal(feedback.status(),200);
      await page.evaluate(()=>{wb.sceneId='traffic_flow_detection';activateTab('intent',true);});
      await page.waitForFunction(marker=>document.querySelector('#wb-feedback-text').textContent===marker,marker);
      assert.equal(await page.locator('#wb-feedback-create').isVisible(),false);
      assert.equal(await page.locator('#wb-feedback-pull').isVisible(),false);
      assert.equal((await context.request.post(origin+'/api/v1/scene-feedback/traffic_flow_detection',{data:{kind:'data',data:{vehicle_count:18}}})).status(),200);
      await page.waitForFunction(()=>!document.querySelector('#wb-feedback-data-wrap').hidden);
      assert.match(await page.locator('#wb-feedback-data').innerText(),/vehicle_count/);
      // Once data leaves the server's retained history, it must leave the page too.
      await page.route('**/api/v1/scene-feedback/traffic_flow_detection',route=>route.fulfill({
        status:200,contentType:'application/json',body:JSON.stringify({events:[{kind:'status',id:103,text:marker}],history_truncated:true})
      }));
      await page.waitForFunction(()=>!wb.feedbackBusy);
      await page.evaluate(()=>wbPollFeedback());
      assert.equal(await page.locator('#wb-feedback-data-wrap').isVisible(),false);
      await page.unroute('**/api/v1/scene-feedback/traffic_flow_detection');
      await page.route('**/api/v1/scene-feedback/traffic_flow_detection',route=>route.fulfill({
        status:200,contentType:'application/json',body:JSON.stringify({events:[{kind:'data',id:104,data:{vehicle_count:20}}],history_truncated:true})
      }));
      await page.waitForFunction(()=>!wb.feedbackBusy);
      await page.evaluate(()=>wbPollFeedback());
      assert.equal(await page.locator('#wb-feedback-text').innerText(),'等待回传');
      assert.match(await page.locator('#wb-feedback-data').innerText(),/20/);
      await page.unroute('**/api/v1/scene-feedback/traffic_flow_detection');

      await page.locator('#btn-register-acct').click();
      await page.locator('#wb-account-name').fill('integration-ui-'+runId+'-'+viewport.width);
      await page.locator('#wb-account-create').click();
      await page.waitForFunction(()=>!!apiKey());
      await page.evaluate(()=>activateTab('market',true));
      await page.locator('[data-wb-scene="robot_patrol"]').click();
      assert.match(await page.locator('#wb-purchase-quote').innerText(),/115\.68/);
      const choices=page.locator('#purchase-capabilities input');
      for(const choice of await choices.all())await choice.uncheck();
      assert.equal(await page.locator('#wb-confirm-scene').isDisabled(),true);
      await page.locator('#purchase-capabilities input[value="target_detection"]').check();
      assert.match(await page.locator('#wb-purchase-quote').innerText(),/15\.92/);
      await page.screenshot({path:path.join(output,'quote-'+viewport.width+'.png')});
      await page.locator('#wb-confirm-scene').click();
      await page.waitForFunction(()=>!document.querySelector('#modal-bg').classList.contains('show')&&!document.querySelector('#purchase-notice').hidden);
      assert.equal(await page.evaluate(()=>wbActive()),'market');
      assert.equal(await page.evaluate(()=>location.hash),'#market');
      assert.match(await page.locator('#purchase-notice').innerText(),/订购完成，已同步至合作平台/);
      assert.equal(await page.locator('#purchase-notice-detail').isVisible(),false);
      const event=await page.evaluate(async()=> (await api('/api/v1/integration/notifications')).notifications[0]);
      assert.equal(event.price,15.92);
      assert.equal(event.action,'create');
      assert.equal(event.request.body.subscriberId,'subscriber-001');
      assert.equal(event.request.body.servicePlan.networkCapabilities[0].price,19.9);

      // Purchased scene prices are reflected immediately, including PRO/MAX base prices.
      await page.evaluate(()=>activateTab('subs',true));
      const cost=page.locator('#subs-content .stat').filter({hasText:'估算月费用'}).locator('b');
      await cost.filter({hasText:'¥15.92'}).waitFor();
      for(const [tier,price] of [['pro','114.92'],['max','314.92']]){
        await page.locator('#subs-content button').filter({hasText:new RegExp('^'+tier.toUpperCase()+' ¥')}).click();
        await cost.filter({hasText:'¥'+price}).waitFor();
        const cap=page.locator('[data-subs-cap]').first(),id=await cap.getAttribute('data-subs-cap');
        await cap.click();
        const description=await page.evaluate(id=>CAPS.find(c=>c.id===id).description,id);
        assert((await page.locator('#modal').innerText()).includes(description));
        await page.locator('#wb-subs-detail-close').click();
      }
      await page.locator('#subs-content button').filter({hasText:/^FREE$/}).click();
      await cost.filter({hasText:'¥15.92'}).waitFor();
      await page.evaluate(()=>activateTab('market',true));
      await page.locator('[data-wb-scene="robot_patrol"]').click();
      await page.waitForFunction(()=>wbActive()==='intent'&&wb.sceneId==='robot_patrol');
      const automaticPull=page.waitForResponse(response=>response.url().endsWith('/api/v1/services/robot_patrol/result')&&response.request().method()==='POST');
      await page.locator('#intent-input').fill('Test robot intent');
      await page.locator('#intent-send').click();
      await page.waitForFunction(()=>document.querySelector('#wb-feedback-text').textContent==='Local fixture perception result');
      await page.waitForFunction(()=>wb.resultTimer!==null);
      assert.match(await page.locator('#wb-intent-text').innerText(),/Test robot intent/);
      assert.equal((await (await automaticPull).json()).status,'unchanged');
      const robotRequests=await probe(),robotStart=robotRequests.findLastIndex(r=>r.path==='/robot-intent');
      assert.equal(robotRequests[robotStart].body,'Test robot intent');
      const pulls=robotRequests.slice(robotStart).filter(r=>r.path==='/latest');
      assert(pulls.length>=2&&pulls.every(r=>r.method==='GET'));
      assert(pulls[1].time-pulls[0].time>=2,'Robot result polling must not run in a tight loop');
      await page.locator('#wb-feedback-pull').click();
      await page.waitForFunction(()=>!wb.resultBusy);
      await page.locator('#wb-feedback').scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(output,'feedback-'+viewport.width+'.png')});
      await page.screenshot({path:path.join(output,'result-'+viewport.width+'.png')});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
      await page.route('**/api/v1/services/robot_patrol/result',route=>route.fulfill({
        status:200,contentType:'application/json',body:JSON.stringify({status:'unavailable',detail:'fixture pull unavailable'})
      }));
      await page.locator('#wb-feedback-pull').click();
      await page.waitForFunction(()=>document.querySelector('#wb-feedback-note').textContent.includes('fixture pull unavailable'));
      assert.match(await page.locator('#wb-intent-text').innerText(),/Test robot intent/);
      await page.unroute('**/api/v1/services/robot_patrol/result');

      // A response to an old scene cannot overwrite the selected scene.
      let release,started;
      const gate=new Promise(r=>release=r),seen=new Promise(r=>started=r);
      await page.route('**/api/v1/services/robot_patrol/result',async route=>{
        started();await gate;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'unavailable',detail:'stale result'})});
      });
      await page.evaluate(()=>{window.pendingPull=wbPullResult();});
      await seen;
      await page.locator('#wb-intent-scene').selectOption('traffic_flow_detection');
      release();await page.evaluate(()=>window.pendingPull);
      await page.waitForFunction(marker=>document.querySelector('#wb-feedback-text').textContent===marker,marker);
      assert.doesNotMatch(await page.locator('#wb-feedback-note').innerText(),/stale result/);
      assert.equal(await page.evaluate(()=>wb.resultTimer),null);
      await page.unroute('**/api/v1/services/robot_patrol/result');

      // Traffic receives a delayed POST callback; it must not start robot-style GET polling.
      await page.locator('#wb-intent-subscribe').click();
      await page.locator('#wb-confirm-scene').click();
      await page.waitForFunction(()=>!document.querySelector('#modal-bg').classList.contains('show'));
      assert.equal(await page.evaluate(()=>wbActive()),'intent');
      const getCount=(await probe()).filter(r=>r.path==='/latest').length;
      await page.locator('#intent-input').fill('Test traffic intent');
      await page.locator('#intent-send').click();
      try{
        await page.waitForFunction(()=>document.querySelector('#wb-feedback-text').textContent.includes('【本地验证回传】车流量中等'));
      }catch(error){
        console.error('Traffic feedback diagnostic',await page.evaluate(()=>({
          scene:wb.sceneId,channel:wb.channel,busy:wb.feedbackBusy,invocation:wbInvocation(),
          text:$('#wb-feedback-text').textContent,note:$('#wb-feedback-note').textContent,
          receipt:$('#intent-result').textContent
        })));
        throw error;
      }
      assert.equal(await page.evaluate(()=>wb.resultTimer),null);
      const trafficRequests=await probe();
      assert.deepEqual(JSON.parse(trafficRequests.findLast(r=>r.path==='/traffic-intent').body),{user_request:'Test traffic intent'});
      assert.equal(trafficRequests.filter(r=>r.path==='/latest').length,getCount);

      await page.evaluate(()=>activateTab('market',true));
      await page.locator('.wb-scene-card').filter({has:page.locator('[data-wb-scene="robot_patrol"]')}).getByRole('button',{name:'取消开通',exact:true}).click();
      await page.locator('#wb-confirm-cancel').click();
      await page.waitForFunction(()=>document.querySelector('[data-wb-scene="robot_patrol"]').textContent==='开通场景');
      const cancelled=await page.evaluate(async()=> (await api('/api/v1/integration/notifications')).notifications[0]);
      assert.equal(cancelled.action,'delete');
      assert.equal(cancelled.request.method,'DELETE');
      assert.match(cancelled.request.path,/subscriberId=subscriber-001$/);

      // Discovery is private; only an explicit publication exposes the tool and POSTs to TRF.
      await page.evaluate(()=>activateTab('afreg',true));
      assert.equal(await page.locator('#wb-server-name').inputValue(),'patrol-car-managementx');
      assert.equal(await page.locator('#wb-server-url').inputValue(),'');
      assert.match(await page.locator('#wb-server-description').inputValue(),/巡检/);
      assert.equal(await page.locator('.wb-trf-management').isVisible(),false);
      // Reproduce the failed discovery from the reported screenshot and delete its draft.
      const serverName='patrol-ui-'+runId+'-'+viewport.width;
      await page.locator('#wb-server-name').fill(serverName);
      await page.locator('#wb-server-url').fill(peer+'/not-allowed');
      await page.locator('#wb-register-server').click();
      await page.waitForFunction(()=>wb.servers.some(s=>s.discovery_status==='failed'));
      const failedId=await page.evaluate(()=>wb.servers.find(s=>s.discovery_status==='failed').id);
      assert.equal(await page.locator('[data-publish-server="'+failedId+'"]').isDisabled(),true);
      const failedDelete=page.locator('[data-delete-server="'+failedId+'"]');
      assert.equal(await failedDelete.isEnabled(),true);
      await page.screenshot({path:path.join(output,'failed-discovery-delete-'+viewport.width+'.png')});
      await failedDelete.click();
      await page.locator('#wb-confirm-delete-server').click();
      await page.waitForFunction(id=>!wb.servers.some(s=>s.id===id),failedId);
      await page.locator('#wb-server-url').fill(peer+'/mcp');
      const trfPath='/trf/api/v1/mcp-servers';
      const publishedBefore=(await probe()).filter(r=>r.path===trfPath&&r.method==='POST').length;
      await page.locator('#wb-register-server').click();
      await page.waitForFunction(()=>wb.servers.some(s=>s.discovery_status==='discovered'));
      const serverId=await page.evaluate(()=>wb.servers[0].id);
      const publishedTool=async()=> (await (await context.request.get(origin+'/api/v1/network/market')).json()).items.find(x=>x.server_id===serverId);
      assert.equal(await publishedTool(),undefined);
      assert.equal((await probe()).filter(r=>r.path===trfPath&&r.method==='POST').length,publishedBefore);
      await page.locator('[data-publish-server="'+serverId+'"]').click();
      await page.waitForFunction(id=>wb.servers.find(s=>s.id===id)?.sync_status==='synced',serverId);
      assert.equal((await publishedTool()).name,'inspect_frame');
      const publication=JSON.parse((await probe()).findLast(r=>r.path===trfPath&&r.method==='POST').body);
      assert.deepEqual(publication,{serverName,serverType:'Streamable HTTP',toolType:'third-party tool',
        description:await page.locator('#wb-server-description').inputValue(),url:peer+'/mcp',serverStatus:'active',isThirdParty:true});
      assert.equal((await publishedTool()).serverName,serverName);
      assert.equal((await publishedTool()).toolType,'third-party tool');
      assert.equal(await page.locator('[data-delete-server="'+serverId+'"]').count(),0);
      await page.evaluate(()=>activateTab('market',true));
      const card=page.locator('#wb-network-market .tile').filter({hasText:'inspect_frame'}).first();
      await card.waitFor();
      assert.equal(await card.locator('.ticon').count(),1);
      assert.match(await card.innerText(),/本地联调图像检查工具/);
      assert((await card.innerText()).includes(serverName));
      assert.match(await page.locator('#wb-network-market').innerText(),/第三方扩展能力/);
      assert.doesNotMatch(await page.locator('#wb-network-market').innerText(),/fixture-nf|fixture-sensing/);
      await card.scrollIntoViewIfNeeded();
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
      await page.screenshot({path:path.join(output,'published-tools-'+viewport.width+'.png')});
      await page.evaluate(()=>activateTab('afreg',true));
      await page.screenshot({path:path.join(output,'external-service-'+viewport.width+'.png')});
      await page.locator('[data-publish-server="'+serverId+'"]').click();
      await page.waitForFunction(id=>wb.servers.find(s=>s.id===id)?.publication_status==='unpublished'&&wb.servers.find(s=>s.id===id)?.sync_status==='synced',serverId);
      assert.equal(await publishedTool(),undefined);
      const deletion=(await probe()).findLast(r=>r.method==='DELETE'&&r.path.startsWith(trfPath));
      assert.equal(deletion.path,trfPath+'/'+serverName);
      assert.equal(deletion.body,'');
      await page.locator('[data-delete-server="'+serverId+'"]').click();
      await page.locator('#wb-confirm-delete-server').click();
      await page.waitForFunction(id=>!wb.servers.some(s=>s.id===id),serverId);
      await page.evaluate(()=>activateTab('market',true));
      assert.equal(await page.locator('#wb-network-market .tile').filter({hasText:'inspect_frame'}).count(),0);

      await page.goto(origin+'/?ops=1#intent');
      await page.waitForFunction(()=>wb.scenes.length===3&&wbActive()==='intent');
      await page.locator('#wb-intent-scene').selectOption('robot_patrol');
      await page.waitForFunction(()=>!!wb.access);
      assert.equal(await page.locator('#wb-feedback-create').isVisible(),true);
      await page.locator('#wb-feedback-create').click();
      assert.match(await page.locator('#modal').innerText(),/scene-feedback\/robot_patrol/);
      await page.locator('#wb-source-close').click();

      // A process change clears old browser accounts on the 401 path.
      await page.route('**/api/v1/instance',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({instance_id:'0123456789abcdef'})}));
      await page.route('**/api/v1/auth/info',route=>route.fulfill({status:401,contentType:'application/json',body:JSON.stringify({detail:'expired'})}));
      await page.evaluate(async()=>{try{await api('/api/v1/auth/info');}catch{}});
      await page.waitForFunction(()=>!apiKey()&&Object.keys(accounts).length===0);
      assert.equal(await page.evaluate(()=>localStorage.getItem('nef_instance')),'0123456789abcdef');
      assert.deepEqual(errors,[]);
      console.log('Integration UI passed: '+viewport.width+'px; failed draft deletion, exact TRF POST/GET/DELETE, source and classification, billing, robot GET/traffic callback, ops and restart');
      await context.close();
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
