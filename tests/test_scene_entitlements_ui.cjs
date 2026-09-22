/* Desktop regression: purchased scene components share grants without duplicate charges. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const origin=process.argv[2],url=new URL(origin);
assert.equal(url.hostname,'127.0.0.1');assert(url.port&&url.port!=='8069');
const output=path.resolve('.runtime/scene-entitlements-ui');fs.mkdirSync(output,{recursive:true});
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.NEF_TEST_BROWSER_CHANNEL?{channel:process.env.NEF_TEST_BROWSER_CHANNEL}:{})});
  try{
    const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(origin);
    await page.waitForFunction(()=>wbTrf.snapshot&&CAPS.length);
    // The missing address explains its purpose without guessing a Host or LAN address.
    await page.route('**/api/v1/network/trf/catalog',async route=>{
      const response=await route.fetch(),data=await response.json();
      await route.fulfill({response,json:{...data,configured:true,base_configured:false}});
    });
    await page.evaluate(()=>wbLoadTrfCatalog());
    assert.match(await page.locator('#wb-home-trf-note').innerText(),/本 NEF.*TRF.*registry\.nef_base_url/);
    assert.equal(await page.locator('#wb-trf-publish').isDisabled(),true);
    await page.unroute('**/api/v1/network/trf/catalog');
    await page.evaluate(()=>wbLoadTrfCatalog());

    const first='scene-grant-'+Date.now(),second=first+'-other';
    const register=async name=>{
      await page.locator('#btn-register-acct').click();
      await page.locator('#wb-account-name').fill(name);
      await page.locator('#wb-account-create').click();
      await page.waitForFunction(name=>wb.authInfo?.account===name,name);
    };
    const buy=async()=>{
      await page.locator('[data-wb-scene="robot_patrol"]').click();
      for(const input of await page.locator('#purchase-capabilities input').all())await input.uncheck();
      await page.locator('#purchase-capabilities input[value="target_detection"]').check();
      await page.locator('#wb-confirm-scene').click();
      await page.waitForFunction(()=>wb.authInfo?.subscribed_capabilities.includes('target_detection'));
    };
    const cancel=async()=>{
      await page.locator('.wb-scene-card').filter({has:page.locator('[data-wb-scene="robot_patrol"]')}).getByRole('button',{name:'取消开通',exact:true}).click();
      await page.locator('#wb-confirm-cancel').click();
      await page.waitForFunction(()=>wb.authInfo&&!wb.authInfo.scene_subscriptions.includes('robot_patrol'));
    };
    const card=page.locator('[data-home-cap="target_detection"]');
    await register(first);await buy();
    assert.match(await card.locator('.tprice').innerText(),/套餐已包含/);
    assert.equal(await page.evaluate(()=>wbActive()),'market');
    assert.equal(await page.evaluate(()=>wb.authInfo.estimated_monthly_cost),15.92);
    const live=await page.evaluate(()=>api('/api/v1/capabilities/target_detection/invoke',{
      method:'POST',headers:{'X-NEF-Execution':'live'},body:JSON.stringify({area:'fixture-zone'})
    }));
    assert.equal(live.data_source,'live');
    const rpc=await page.evaluate(()=>api('/mcp/capabilities/target_detection',{
      method:'POST',body:JSON.stringify({jsonrpc:'2.0',id:7,method:'tools/call',params:{name:'target_detection',arguments:{area:'fixture-zone'}}})
    }));
    assert.equal(rpc.result.isError,false);
    assert.equal(JSON.parse(rpc.result.content[0].text).data_source,'live');
    await card.click();
    assert.match(await page.locator('#wb-cap-access').innerText(),/机器狗.*无需重复订阅/);
    assert.equal(await page.getByRole('button',{name:'套餐已包含',exact:true}).isDisabled(),true);
    assert.equal(await page.locator('#modal button.success:not(:disabled)').count(),0);
    await page.screenshot({path:path.join(output,'included-capability.png')});
    await page.locator('#modal').getByRole('button',{name:'关闭',exact:true}).click();
    const unselected=await page.evaluate(()=>wb.scenes.find(s=>s.id==='robot_patrol').provenance.components.find(c=>c.capability_id!=='target_detection').capability_id);
    await page.locator(`[data-home-cap="${unselected}"]`).click();
    await page.locator('#modal-bg.show #modal button.success:not(:disabled)').waitFor();
    assert.equal(await page.locator('#wb-cap-access').count(),0);
    assert.equal(await page.locator('#modal button.success:not(:disabled)').count(),1);
    await page.locator('#modal').getByRole('button',{name:'关闭',exact:true}).click();
    await page.getByRole('button',{name:'订阅与鉴权',exact:true}).click();
    await page.locator('[data-subs-cap="target_detection"]').waitFor();
    assert.match(await page.locator('[data-subs-cap="target_detection"]').innerText(),/场景套餐内/);
    await page.getByRole('button',{name:'能力超市',exact:true}).click();
    await register(second);
    assert.doesNotMatch(await card.locator('.tprice').innerText(),/包含|已订阅/);
    await page.locator('#acct-select').selectOption(first);
    await page.waitForFunction(name=>wb.authInfo?.account===name,first);
    assert.match(await card.locator('.tprice').innerText(),/套餐已包含/);
    await cancel();
    assert.doesNotMatch(await card.locator('.tprice').innerText(),/包含|已订阅/);
    assert.equal(await page.evaluate(()=>wb.authInfo.estimated_monthly_cost),0);
    // An existing direct grant survives scene removal and is not charged twice while covered.
    await page.evaluate(()=>api('/api/v1/subscribe',{method:'POST',body:JSON.stringify({account:current,capability_ids:['target_detection']})}));
    await buy();
    assert.equal(await page.evaluate(()=>wb.authInfo.estimated_monthly_cost),15.92);
    await cancel();
    assert.equal(await page.evaluate(()=>wb.authInfo.estimated_monthly_cost),19.9);
    assert.equal(await card.locator('.tprice').innerText(),'已订阅');
    assert.deepEqual(errors,[]);
    console.log('Scene entitlement desktop passed: selected grants, no duplicate purchase, account isolation, cancel retention, monthly cost and NEF address guidance.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
