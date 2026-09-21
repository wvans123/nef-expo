/* TRF operations UI; run only against tests/workbench_fixture.py. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const origin=process.argv[2],url=new URL(origin),runId=Date.now().toString(36);
assert.equal(url.hostname,'127.0.0.1');
assert(url.port&&url.port!=='8069','Use an isolated fixture port');
const output=path.resolve('.runtime/catalog-ui');fs.mkdirSync(output,{recursive:true});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};

(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.NEF_TEST_BROWSER_CHANNEL?{channel:process.env.NEF_TEST_BROWSER_CHANNEL}:{})});
  try{
    for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
      const context=await browser.newContext({viewport}),page=await context.newPage(),errors=[],sent=[];
      page.on('pageerror',error=>errors.push(error.message));
      page.on('request',request=>{if(request.url().endsWith('/api/v1/network/trf/servers'))sent.push(request.method());});
      await page.goto(origin+'/#afreg');
      await page.waitForFunction(()=>wb.scenes.length===3&&CAPS.length>0&&wbActive()==='afreg');
      assert.equal(await page.locator('.wb-trf-management').isVisible(),false);
      assert.equal(sent.length,0);
      await page.goto(origin+'/?ops=1#afreg');
      await page.waitForFunction(()=>wb.scenes.length===3&&wbActive()==='afreg');
      await page.locator('.wb-trf-management > summary').click();
      await page.locator('#wb-refresh-trf').click();
      assert.match(await page.locator('#toast').innerText(),/注册或选择账号/);
      assert.equal(sent.length,0);
      await page.locator('#btn-register-acct').click();
      await page.locator('#wb-account-name').fill('trf-ui-'+runId+'-'+viewport.width);
      await page.locator('#wb-account-create').click();
      await page.waitForFunction(()=>!!apiKey());
      await page.waitForFunction(()=>!wb.networkBusy);
      const before=await page.evaluate(()=>({market:wb.market,pool:wbSources()}));
      await page.locator('#wb-refresh-trf').click();
      await page.waitForFunction(()=>document.querySelector('#wb-trf-status').textContent.includes('已读取'));
      assert.equal(await page.locator('#wb-trf-servers .wb-trf-row').count(),4);
      for(const kind of ['nf tool','computing tool','sensing tool','third-party tool']){
        assert((await page.locator('#wb-trf-servers').innerText()).includes(kind));
      }
      assert.deepEqual(await page.evaluate(()=>({market:wb.market,pool:wbSources()})),before);
      assert(sent.every(method=>method==='GET'));
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
      await page.screenshot({path:path.join(output,'trf-query-'+viewport.width+'.png'),fullPage:true});

      // Configuration absence and malformed upstream responses must not leave stale rows.
      for(const [status,body,message] of [
        [200,{status:'not_configured',servers:[]},'TRF 地址未配置'],
        [502,{detail:{message:'TRF 返回列表格式不支持'}},'TRF 返回列表格式不支持']
      ]){
        await page.route('**/api/v1/network/trf/servers',route=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)}));
        await page.locator('#wb-refresh-trf').click();
        await page.waitForFunction(message=>document.querySelector('#wb-trf-status').textContent===message,message);
        assert.equal(await page.locator('#wb-trf-servers .wb-trf-row').count(),0);
        await page.unroute('**/api/v1/network/trf/servers');
      }
      // Switching accounts while a query is in flight cannot display the old result.
      const started=deferred(),release=deferred();
      await page.route('**/api/v1/network/trf/servers',async route=>{
        started.resolve();await release.promise;
        await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'loaded',servers:[
          {serverName:'stale-account-server',serverType:'Steamable HTTP',toolType:'third-party tool',description:'stale',url:'http://127.0.0.1/mcp',serverStatus:'active'}
        ]})});
      });
      await page.evaluate(()=>{window.pendingTrf=document.querySelector('#wb-refresh-trf').onclick();});
      await started.promise;
      const other=await (await context.request.post(origin+'/api/v1/register',{data:{account:'trf-other-'+runId+'-'+viewport.width}})).json();
      await page.evaluate(async account=>{
        accounts[account.account]={api_key:account.api_key};current=account.account;saveAccounts();await refreshAll();
      },other);
      release.resolve();await page.evaluate(()=>window.pendingTrf);
      assert.equal(await page.locator('#wb-trf-status').innerText(),'尚未查询');
      assert.equal(await page.locator('#wb-trf-servers .wb-trf-row').count(),0);
      assert.deepEqual(errors,[]);
      console.log('TRF operations UI passed: '+viewport.width+'px; hidden by default, four categories, no automatic tool import, failure and account race');
      await context.close();
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
