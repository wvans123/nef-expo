const assert = require('node:assert/strict');
const {assess} = require('../static/showcase-auth.js');
const evidence = {pipeline:['validate','identify','scope','authorize'].map(code=>({code,status:'passed'}))};
assert.deepEqual(assess(null,0,'api',false).steps.map(s=>s.state),['pending','pending','pending','unimplemented']);
assert.equal(assess(null,401,'api').steps[0].state,'denied');
assert.equal(assess({},200,'api').steps[0].state,'pending');
assert.equal(assess({},503,'api').steps[2].state,'pending');
assert.deepEqual(assess({detail:{nef_auth:evidence}},503,'api').steps.map(s=>s.state),['passed','passed','passed','unimplemented']);
assert.equal(assess({nef_auth:evidence},200,'intent').steps[2].label,'Intent 入口权益');
assert.match(assess({nef_auth:evidence},200,'intent').note,/区域、设备、有效期/);
const denied = {pipeline:evidence.pipeline.map(s=>({...s,status:s.code==='authorize'?'denied':s.status}))};
assert.equal(assess({nef_auth:denied},402,'api').steps[2].state,'denied');
console.log('Authorization presentation: 8 assertions passed.');

assert.match(assess({nef_auth:{...evidence,authorization_target:{service_id:"robot_patrol"}}},200,"intent").note,/按所选场景核验订阅权益/);
