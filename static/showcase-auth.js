/* Interpret backend evidence, never infer authorization from transport success. */
(function (root) {
  'use strict';
  function assess(payload, httpStatus, mode, pending) {
    const auth = payload?.nef_auth || payload?.auth || payload?.detail?.nef_auth || payload?.detail?.auth;
    const stages = Array.isArray(auth?.pipeline) ? auth.pipeline : [];
    const stage = code => stages.find(item => item.code === code)?.status;
    const identity = stage('validate') === 'passed' && stage('identify') === 'passed' ? 'passed' : httpStatus === 401 ? 'denied' : 'pending';
    const normalize = value => ['passed', 'denied'].includes(value) ? value : 'pending';
    const steps = [
      {label: 'AF 身份', state: identity},
      {label: '入口权限', state: normalize(stage('scope'))},
      {label: mode === 'intent' ? 'Intent 入口权益' : '能力使用权', state: normalize(stage('authorize'))},
      {label: '资源范围', state: 'unimplemented'}
    ];
    let note = pending ? '等待后端校验回执…' : '等待调用';
    if (auth) note = auth.authorization_target?.service_id ? '本次已按所选场景核验订阅权益；资源级策略尚未接入。' : '已核对的结果来自后端；区域、设备、有效期等资源约束尚未接入。';
    else if (httpStatus === 401) note = '调用方凭证未通过校验，未证明后续授权。';
    else if (httpStatus >= 400) note = '请求未完成；缺少可核验的授权回执，不标记通过。';
    return {steps, note};
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {assess};
  else root.NefAuthReceipt = {assess};
})(globalThis);
