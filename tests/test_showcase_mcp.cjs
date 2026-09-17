const assert=require('node:assert/strict');
const {createClient,fields,parseArguments,VERSION,describeTools,selectedBusiness}=require('../static/showcase-mcp.js');
const tool={name:'from_server',description:'来自响应的参数契约',inputSchema:{type:'object',properties:{device:{type:'string',description:'服务声明的设备',minLength:2},count:{type:'integer',minimum:1},enabled:{type:'boolean'},config:{type:'object'},mode:{type:'string',enum:['a','b']}},required:['device']}};
const init=m=>({jsonrpc:'2.0',id:m.id,result:{protocolVersion:VERSION,capabilities:{tools:{}},serverInfo:{name:'test-nef'}}});
async function run(){
  const services=[{id:'scene-a',name:'场景甲',tool_name:'tool_a'},{id:'unpublished',name:'未发布场景',tool_name:'absent'}];
  const caps=[{id:'basic_b',name:'基础乙'}];
  const returned=[{name:'tool_a',description:'服务 A',inputSchema:{type:'object'}},{name:'basic_b',inputSchema:{type:'object'}},{name:'new_network_tool',inputSchema:{type:'object'}}];
  assert.equal(selectedBusiness(null,services),null);
  assert.deepEqual(describeTools([],services,caps),[]); // local metadata cannot conjure an undiscovered tool
  const rows=describeTools(returned,services,caps);
  assert.deepEqual(rows.map(r=>r.tool.name),['tool_a','basic_b','new_network_tool']);
  assert.deepEqual(rows.map(r=>r.group),['scene','capability','capability']);
  assert.equal(describeTools(returned,services,caps,'基础')[0].tool.name,'basic_b');
  assert.deepEqual(selectedBusiness(returned[0],services),{serviceId:'scene-a',capId:''});
  assert.deepEqual(selectedBusiness(returned[2],services),{serviceId:'',capId:'new_network_tool'});
  const sent=[];let queries=0;
  const client=createClient(async m=>{sent.push(m);if(m.method==='initialize')return init(m);if(m.method==='notifications/initialized')return null;queries++;return {jsonrpc:'2.0',id:m.id,result:queries===1?{tools:[tool],nextCursor:'page2'}:{tools:[{name:'other',inputSchema:{type:'object'}}]}};});
  assert.throws(()=>client.select('from_server'));
  await client.connect();assert.equal(client.state.connected,true);assert.equal(sent[1].method,'notifications/initialized');assert.equal(Object.hasOwn(sent[1],'id'),false);
  await client.discover();assert.equal(client.state.tools.length,2);assert.equal(client.state.pages,2);assert.deepEqual(sent.at(-1).params,{cursor:'page2'});
  assert.equal(client.select('from_server').description,tool.description);assert.equal(fields(tool)[0].description,'服务声明的设备');
  assert.deepEqual(JSON.parse(JSON.stringify(parseArguments(tool,{device:'ue1',count:'2',enabled:'false',config:'{"x":1}',mode:'b'}))),{device:'ue1',count:2,enabled:false,config:{x:1},mode:'b'});
  for(const values of [{},{device:'a'},{device:'ok',count:'0'},{device:'ok',count:'1.2'},{device:'ok',config:'[]'},{device:'ok',mode:'wrong'}])assert.throws(()=>parseArguments(tool,values));
  client.reset();assert.equal(client.state.selected,null);assert.equal(client.state.connected,false);
  const wrongVersion=createClient(async m=>({...init(m),result:{...init(m).result,protocolVersion:'wrong'}}));await wrongVersion.connect();assert.equal(wrongVersion.state.connected,false);assert.match(wrongVersion.state.error,/版本/);
  let oldComplete;const stale=createClient(()=>new Promise(r=>oldComplete=r));const operation=stale.connect();stale.reset();oldComplete({jsonrpc:'2.0',id:1,result:{protocolVersion:VERSION,capabilities:{tools:{}},serverInfo:{name:'stale'}}});await operation;assert.equal(stale.state.connected,false);
  let refreshCount=0;
  const refresh=createClient(async m=>{if(m.method==='initialize')return init(m);if(m.method==='notifications/initialized')return null;if(++refreshCount>1)throw new Error('目录不可用');return {jsonrpc:'2.0',id:m.id,result:{tools:[tool]}};});await refresh.connect();await refresh.discover();refresh.select('from_server');await refresh.discover();assert.equal(refresh.state.selected,null);assert.equal(refresh.state.tools.length,0);assert.match(refresh.state.error,/目录不可用/);
  const noTool=createClient(async m=>{if(m.method==='initialize')return init(m);if(m.method==='notifications/initialized')return null;return {jsonrpc:'2.0',id:m.id,result:{tools:[]}};});await noTool.connect();await noTool.discover();assert.throws(()=>noTool.select('from_server'));assert.equal(noTool.state.phase,'discovered');
  const duplicate=createClient(async m=>{if(m.method==='initialize')return init(m);if(m.method==='notifications/initialized')return null;return {jsonrpc:'2.0',id:m.id,result:{tools:[tool,tool]}};});await duplicate.connect();await duplicate.discover();assert.equal(duplicate.state.tools.length,0);assert.match(duplicate.state.error,/重复/);
  const badShape=createClient(async m=>{if(m.method==='initialize')return init(m);if(m.method==='notifications/initialized')return null;return {jsonrpc:'2.0',id:m.id,result:{tools:[{name:'bad',inputSchema:{type:'object',properties:{x:null}}}]}};});await badShape.connect();await badShape.discover();assert.equal(badShape.state.selected,null);assert.match(badShape.state.error,/声明/);
  console.log('MCP discovery client: handshake, pagination, schema inputs, error, refresh and stale-context tests passed.');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
