/* Run only against tests/workbench_fixture.py, never the live demo service. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const origin=process.argv[2],url=new URL(origin);
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
      await page.locator('#wb-account-name').fill('integration-ui-'+viewport.width);
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
      await page.waitForFunction(()=>wbActive()==='intent'&&wb.sceneId==='robot_patrol'&&!document.querySelector('#purchase-notice').hidden);
      assert.match(await page.locator('#purchase-notice').innerText(),/订购完成，已同步至合作平台/);
      assert.equal(await page.locator('#purchase-notice-detail').isVisible(),false);
      const event=await page.evaluate(async()=> (await api('/api/v1/integration/notifications')).notifications[0]);
      assert.equal(event.price,15.92);
      assert.equal(event.action,'create');
      assert.equal(event.request.body.subscriberId,'subscriber-001');
      assert.equal(event.request.body.servicePlan.networkCapabilities[0].price,19.9);

      const automaticPull=page.waitForResponse(response=>response.url().endsWith('/api/v1/services/robot_patrol/result')&&response.request().method()==='POST');
      await page.locator('#intent-input').fill('Test robot intent');
      await page.locator('#intent-send').click();
      await page.waitForFunction(()=>document.querySelector('#wb-feedback-text').textContent==='Local fixture perception result');
      await page.waitForFunction(()=>wb.resultTimer!==null);
      assert.match(await page.locator('#wb-intent-text').innerText(),/Test robot intent/);
      assert.equal((await (await automaticPull).json()).status,'unchanged');
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

      await page.evaluate(()=>activateTab('market',true));
      await page.locator('.wb-scene-card').filter({has:page.locator('[data-wb-scene="robot_patrol"]')}).getByRole('button',{name:'取消开通',exact:true}).click();
      await page.locator('#wb-confirm-cancel').click();
      await page.waitForFunction(()=>document.querySelector('[data-wb-scene="robot_patrol"]').textContent==='开通场景');
      const cancelled=await page.evaluate(async()=> (await api('/api/v1/integration/notifications')).notifications[0]);
      assert.equal(cancelled.action,'delete');
      assert.equal(cancelled.request.method,'DELETE');
      assert.match(cancelled.request.path,/subscriberId=subscriber-001$/);

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
      console.log('Integration UI passed: '+viewport.width+'px; shared feedback, quote, subscribe, intent/pull, cancellation, ops and restart');
      await context.close();
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
