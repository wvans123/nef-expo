/* Run only against tests/workbench_fixture.py, never the live demo service. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const origin=process.argv[2],url=new URL(origin);
assert.equal(url.hostname,'127.0.0.1');
assert(url.port&&url.port!=='8069','Use an isolated fixture port');
const output=path.resolve('.runtime/catalog-ui');
fs.mkdirSync(output,{recursive:true});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};

(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.NEF_TEST_BROWSER_CHANNEL?{channel:process.env.NEF_TEST_BROWSER_CHANNEL}:{})});
  try{
    for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
      const context=await browser.newContext({viewport});
      const page=await context.newPage(),errors=[],sent=[];
      page.on('pageerror',error=>errors.push(error.message));
      page.on('request',request=>{
        if(/\/catalog\/(publication|publish)$/.test(new URL(request.url()).pathname))sent.push({path:new URL(request.url()).pathname,body:request.postDataJSON()});
      });
      await page.goto(origin);
      await page.waitForFunction(()=>wb.scenes.length===3&&CAPS.length>0);
      await page.locator('#wb-open-catalog-publication').click();
      assert.equal(await page.locator('#modal-bg').evaluate(el=>el.classList.contains('show')),false);
      assert.match(await page.locator('#toast').innerText(),/注册或选择账号/);
      await page.locator('#btn-register-acct').click();
      await page.locator('#wb-account-name').fill('catalog-ui-'+viewport.width);
      await page.locator('#wb-account-create').click();
      await page.waitForFunction(()=>apiKey()&&wb.catalog.length===2);
      await page.locator('#wb-open-catalog-publication').click();
      assert.equal(await page.locator('#wb-catalog-preview').isDisabled(),true);
      assert.equal(await page.locator('#wb-catalog-publish').isDisabled(),true);
      const capability=page.locator('[data-catalog-kind="capability"][value="target_detection"]');
      const scene=page.locator('[data-catalog-kind="service"][value="robot_patrol"]');
      assert.equal(await page.locator('[data-catalog-kind][value^="fixture."]').count(),0);
      const choices=await page.locator('[data-catalog-kind]').count();
      assert.equal(choices,await page.evaluate(()=>CAPS.filter(c=>c.status==='available').length+wb.scenes.length));
      await capability.check();
      await page.locator('#wb-catalog-preview').click();
      await page.waitForFunction(()=>document.querySelector('#wb-catalog-message').textContent.includes('预览已生成'));
      assert.equal(sent.filter(x=>x.path.endsWith('/publish')).length,0);
      assert.deepEqual(sent.at(-1).body,{capability_ids:['target_detection'],service_ids:[]});
      await scene.check();
      assert.equal(await page.locator('#wb-catalog-publish').isDisabled(),true);
      assert.equal(await page.locator('#wb-catalog-payload').isHidden(),true);
      await page.locator('#wb-catalog-preview').click();
      await page.waitForFunction(()=>!document.querySelector('#wb-catalog-publish').disabled);
      const preview=JSON.parse(await page.locator('#wb-catalog-json').textContent());
      assert.deepEqual(preview.items.map(x=>x.id).sort(),['robot_patrol','target_detection']);
      assert(preview.items.every(x=>x.interfaces.every(i=>i.url.startsWith(origin))));
      await page.screenshot({path:path.join(output,'preview-'+viewport.width+'.png')});
      const bounds=await page.locator('#modal').boundingBox();
      assert(bounds.x>=0&&bounds.x+bounds.width<=viewport.width+1);
      assert(bounds.y>=0&&bounds.y+bounds.height<=viewport.height+1);
      assert.equal(await page.locator('#wb-catalog-publication').evaluate(el=>el.scrollWidth>el.clientWidth+1),false);
      await page.locator('#wb-catalog-publish').evaluate(button=>{button.click();button.click();});
      await page.waitForFunction(()=>document.querySelector('#wb-catalog-message').textContent.includes('对方已确认'));
      assert.equal(sent.filter(x=>x.path.endsWith('/publish')).length,1);
      assert.deepEqual(sent.at(-1).body,{capability_ids:['target_detection'],service_ids:['robot_patrol']});
      assert.equal(await page.locator('#wb-catalog-publish').isDisabled(),true);
      await page.screenshot({path:path.join(output,'published-'+viewport.width+'.png')});

      // A successful HTTP response without confirmation must not be labelled synced.
      await page.route('**/api/v1/network/catalog/publish',route=>route.fulfill({
        status:200,contentType:'application/json',body:JSON.stringify({sync_status:'submitted',accepted:false,item_count:2})
      }));
      await page.locator('#wb-catalog-preview').click();
      await page.waitForFunction(()=>!document.querySelector('#wb-catalog-publish').disabled);
      await page.locator('#wb-catalog-publish').click();
      await page.waitForFunction(()=>document.querySelector('#wb-catalog-message').textContent.includes('待对方确认'));
      assert.doesNotMatch(await page.locator('#wb-catalog-message').textContent(),/已同步/);
      await page.unroute('**/api/v1/network/catalog/publish');

      // Configuration failures must disable sending, even after a valid earlier preview.
      await page.route('**/api/v1/network/catalog/publication',route=>route.fulfill({
        status:503,contentType:'application/json',body:JSON.stringify({detail:{message:'fixture configuration missing'}})
      }));
      await page.locator('#wb-catalog-preview').click();
      await page.waitForFunction(()=>document.querySelector('#wb-catalog-message').textContent.includes('fixture configuration missing'));
      assert.equal(await page.locator('#wb-catalog-publish').isDisabled(),true);
      assert.equal(await page.locator('#wb-catalog-payload').isHidden(),true);
      await page.unroute('**/api/v1/network/catalog/publication');

      // Delayed previews cannot leak across modal instances or account changes.
      for(const change of ['close','account']){
        const started=deferred(),release=deferred();
        await page.route('**/api/v1/network/catalog/publication',async route=>{
          started.resolve();await release.promise;
          await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(preview)});
        });
        await capability.check();
        await page.evaluate(()=>{window.catalogPending=document.querySelector('#wb-catalog-preview').onclick();});
        await started.promise;
        if(change==='close'){
          await page.locator('#wb-catalog-close').click();
        }else{
          const other=await (await context.request.post(origin+'/api/v1/register',{data:{account:'catalog-ui-other-'+viewport.width}})).json();
          await page.evaluate(async account=>{
            accounts[account.account]={api_key:account.api_key};current=account.account;saveAccounts();await refreshAll();
          },other);
        }
        assert.equal(await page.locator('#modal-bg').evaluate(el=>el.classList.contains('show')),false);
        await page.locator('#wb-open-catalog-publication').click();
        release.resolve();await page.evaluate(()=>window.catalogPending);
        assert.equal(await page.locator('#wb-catalog-message').textContent(),'未选择目录项');
        assert.equal(await page.locator('#wb-catalog-publish').isDisabled(),true);
        assert.equal(await page.locator('#wb-catalog-payload').isHidden(),true);
        await page.unroute('**/api/v1/network/catalog/publication');
      }
      await page.evaluate(()=>activateTab('subs',true));
      assert.equal(await page.locator('#modal-bg').evaluate(el=>el.classList.contains('show')),false);
      assert.deepEqual(errors,[]);
      console.log('Catalog UI passed: '+viewport.width+'px; real local publication plus isolated failure/race checks');
      await context.close();
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
