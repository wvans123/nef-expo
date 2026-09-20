/* Presentation semantics only. Never fabricates execution steps or progress. */
(function(root){
  'use strict';
  const paths={
    api:{name:'API',client:'业务应用',input:'已知接口 · 明确参数',nef:'API 接入',action:'校验权益 · 参数映射',network:'网络侧服务',delivery:'调用约定 HTTP 接口'},
    tool:{name:'MCP Tool',client:'外部 AF · MCP Client',input:'发现目录 → 选用工具',nef:'MCP Server',action:'工具声明 · 调用映射',network:'网络侧服务',delivery:'复用约定 HTTP 接口'},
    intent:{name:'Intent',client:'外部 AF',input:'提交业务目标',nef:'意图接入',action:'校验权益 · 原文转发',network:'网络侧意图接收方',delivery:'解析与执行由内部承接'}
  };
  function path(mode){return paths[mode]||paths.api;}
  function receipt(result){
    if(result?.data_source==='demo')return {badge:'演示回执',summary:result.summary||'场景示例已呈现'};
    if(result?.data_source==='mock')return {badge:'参考回显',summary:'参考实现返回，非真实网络执行'};
    if(result?.data_source==='live'&&result.upstream){
      const status=result.upstream.http_status;
      return {badge:status>=400?'网络侧异常响应':'已收到网络回执',summary:`HTTP ${status} · ${status>=400?'请查看网络侧返回信息':'请求已有响应，业务结果以场景反馈为准'}`};
    }
    return {badge:'调用回执',summary:result?.summary||'已收到调用响应'};
  }
  function businessResult(result){
    if(result?.data_source==='demo')return result.demo_result?.text||result.summary||'已收到演示回执';
    const body=result?.data_source==='live'?result.upstream?.body:result;
    if(typeof body==='string'&&body.trim())return body;
    const texts=[body?.final_result,body?.text,body?.result,body?.result?.text,body?.result?.summary,body?.summary,body?.message];
    const text=texts.find(t=>typeof t==='string'&&t.trim());
    if(text)return text;
    if(result?.data_source==='live')return '网络侧已响应，尚未返回文字业务结果。可在场景回传区接收后续反馈。';
    return result?.summary||'已收到响应，详情见原始回执。';
  }
  function feedbackChannels(channels,serviceId){
    return channels.filter(c=>serviceId?c.service_id===serviceId:!c.service_id);
  }
  function feedbackHandoff(channel,origin){
    return {url:origin+channel.feedback_endpoint,open_url:channel.open_endpoint?origin+channel.open_endpoint:null,receiver_key:channel.receiver_key,
      json_example:{final_result:channel.service_id==='traffic_flow_detection'?'今天下午3点十字路口东南侧的车流量处于中等水平。':'正在处理'},
      media:'同一地址上传文件原始字节；Content-Type 使用 image/png、image/jpeg、image/webp、video/mp4 或 video/webm'};
  }
  const api={path,receipt,businessResult,feedbackChannels,feedbackHandoff};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.NefStory=api;
})(typeof globalThis!=='undefined'?globalThis:this);
