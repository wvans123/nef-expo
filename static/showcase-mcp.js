/* Small client for the project's 2025-03-26 MCP compatibility path. */
(function(root){
  'use strict';
  const VERSION='2025-03-26';
  function createClient(send, changed=()=>{}){
    let generation=0,serial=0;
    const state={connected:false,busy:false,tools:[],selected:null,server:null,phase:'idle',error:'',call:'idle',trace:[],pages:0};
    function reset(){generation++;Object.assign(state,{connected:false,busy:false,tools:[],selected:null,server:null,phase:'idle',error:'',call:'idle',trace:[],pages:0});changed();}
    function active(g){if(g!==generation){const e=new Error('接入上下文已切换');e.stale=true;throw e;}}
    async function rpc(method,params,g,notification=false){
      active(g);
      const message={jsonrpc:'2.0',...(notification?{}:{id:++serial}),method,...(params?{params}:{})};
      let result;
      try{result=await send(message);}catch(error){active(g);state.trace.push({request:message,error:error.message});throw error;}
      active(g);state.trace.push({request:message,response:result});
      if(notification)return;
      if(!result||result.jsonrpc!=='2.0'||result.id!==message.id)throw new Error('NEF 返回了不匹配的协议响应');
      if(result.error)throw new Error(result.error.message||'NEF 协议请求被拒绝');
      if(!Object.hasOwn(result,'result'))throw new Error('NEF 响应缺少 result');
      return result.result;
    }
    async function connect(){
      if(state.busy)return;
      reset();const g=generation;state.busy=true;state.phase='connecting';changed();
      try{
        const result=await rpc('initialize',{protocolVersion:VERSION,capabilities:{},clientInfo:{name:'nef-af-exhibition-client',version:'1.0.0'}},g);
        if(result.protocolVersion!==VERSION)throw new Error('协议版本不兼容，未进入工具发现');
        if(!result.capabilities?.tools||typeof result.capabilities.tools!=='object')throw new Error('NEF 未声明工具能力');
        if(typeof result.serverInfo?.name!=='string')throw new Error('NEF 未返回服务器身份信息');
        await rpc('notifications/initialized',null,g,true);
        state.server=result.serverInfo;state.connected=true;state.phase='connected';
      }catch(e){if(!e.stale){state.error=e.message;state.phase='error';}else return;}
      finally{if(g===generation){state.busy=false;changed();}}
    }
    async function discover(){
      if(!state.connected||state.busy)return;
      const g=generation;state.busy=true;state.tools=[];state.selected=null;state.error='';state.call='idle';state.phase='discovering';changed();
      try{
        const all=[],names=new Set(),cursors=new Set();let cursor;
        for(let page=0;page<20;page++){
          const result=await rpc('tools/list',cursor?{cursor}:{},g);
          if(!Array.isArray(result.tools))throw new Error('NEF 工具目录格式不正确');
          for(const tool of result.tools){
            if(typeof tool?.name!=='string'||!tool.name||tool.inputSchema?.type!=='object'||names.has(tool.name))throw new Error('目录包含重复工具或缺少有效参数声明');
            const props=tool.inputSchema.properties,required=tool.inputSchema.required;
            if((props!==undefined&&(!props||typeof props!=='object'||Array.isArray(props)))||(required!==undefined&&(!Array.isArray(required)||required.some(k=>typeof k!=='string'))))throw new Error('工具的参数声明格式不正确');
            if(Object.values(props||{}).some(p=>!p||typeof p!=='object'||Array.isArray(p)))throw new Error('当前展示端不支持该参数声明形式');
            names.add(tool.name);all.push(tool);
            if(all.length>1000)throw new Error('工具目录超过本演示端的接收上限');
          }
          state.pages=page+1;
          if(!result.nextCursor){state.tools=all;state.phase='discovered';return;}
          if(typeof result.nextCursor!=='string'||cursors.has(result.nextCursor))throw new Error('工具目录分页游标异常');
          cursors.add(result.nextCursor);cursor=result.nextCursor;
        }
        throw new Error('工具目录分页超过接收上限');
      }catch(e){if(!e.stale){state.tools=[];state.selected=null;state.error=e.message;state.phase='error';}}
      finally{if(g===generation){state.busy=false;changed();}}
    }
    function select(name){
      if(state.busy||state.phase!=='discovered')throw new Error('请先完成工具发现');
      const tool=state.tools.find(t=>t.name===name);if(!tool)throw new Error('工具不在 NEF 返回的目录中');
      state.selected=tool;state.call='idle';changed();return tool;
    }
    function callState(value){state.call=value;changed();}
    function recordCall(request,response){state.trace.push({request,response});changed();}
    return {state,reset,connect,discover,select,callState,recordCall};
  }
  function fields(tool){
    const schema=tool.inputSchema,required=new Set(schema.required||[]);
    return Object.entries(schema.properties||{}).map(([name,spec])=>({name,type:spec.type||'string',description:spec.description||name,required:required.has(name),schema:spec}));
  }
  function parseArguments(tool,values){
    const args=Object.create(null);
    for(const field of fields(tool)){
      const raw=values[field.name];
      if(raw===undefined||raw===''){if(field.required)throw new Error('请填写 '+field.description);continue;}
      let value;
      if(field.type==='string')value=String(raw);
      else if(field.type==='number'||field.type==='integer'){value=Number(raw);if(!Number.isFinite(value)||(field.type==='integer'&&!Number.isInteger(value)))throw new Error(field.description+' 需要有效数字');}
      else if(field.type==='boolean'){if(raw!==true&&raw!==false&&raw!=='true'&&raw!=='false')throw new Error(field.description+' 需要布尔值');value=raw===true||raw==='true';}
      else if(field.type==='array'||field.type==='object'){try{value=JSON.parse(raw);}catch{throw new Error(field.description+' 需要有效 JSON');}if(field.type==='array'?!Array.isArray(value):!value||typeof value!=='object'||Array.isArray(value))throw new Error(field.description+' 类型不匹配');}
      else throw new Error('暂不支持参数类型：'+field.type);
      if(field.schema.enum&&!field.schema.enum.includes(value))throw new Error(field.description+' 不在允许值范围内');
      if(typeof value==='string'&&((field.schema.minLength!==undefined&&value.length<field.schema.minLength)||(field.schema.maxLength!==undefined&&value.length>field.schema.maxLength)))throw new Error(field.description+' 长度超出工具声明范围');
      if(typeof value==='number'&&((field.schema.minimum!==undefined&&value<field.schema.minimum)||(field.schema.maximum!==undefined&&value>field.schema.maximum)))throw new Error(field.description+' 超出工具声明范围');
      args[field.name]=value;
    }
    return args;
  }
  // Metadata can enrich returned tools, but never create or preselect a tool.
  function describeTools(tools,services,caps,query=''){
    const needle=query.trim().toLowerCase();
    return tools.map(tool=>{
      const service=services.find(s=>s.tool_name===tool.name);
      const cap=caps.find(c=>c.id===tool.name);
      return {tool,serviceId:service?.id||'',capId:cap?.id||tool.name,
        title:service?.name||cap?.name||tool.name,group:service?'scene':'capability'};
    }).filter(row=>!needle||(row.title+' '+row.tool.name+' '+(row.tool.description||'')).toLowerCase().includes(needle));
  }
  function selectedBusiness(selected,services){
    if(!selected)return null;
    const service=services.find(s=>s.tool_name===selected.name);
    return {serviceId:service?.id||'',capId:service?'':selected.name};
  }
  const api={VERSION,createClient,fields,parseArguments,describeTools,selectedBusiness};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.NefMcp=api;
})(globalThis);
