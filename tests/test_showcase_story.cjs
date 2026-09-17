const assert=require('node:assert/strict');
const story=require('../static/showcase-story.js');
assert.match(story.path('tool').input,/发现目录.*选用工具/);
assert.match(story.path('tool').delivery,/HTTP/);
assert.match(story.path('intent').action,/原文转发/);
assert.match(story.path('api').input,/已知接口/);
assert.equal(story.receipt({data_source:'demo',summary:'示例'}).badge,'演示回执');
assert.equal(story.receipt({data_source:'mock'}).badge,'参考回显');
assert.equal(story.receipt({summary:'unknown'}).badge,'调用回执');
for(const status of [200,202,204]){
 const receipt=story.receipt({data_source:'live',status:'forwarded',upstream:{http_status:status}});
 assert.equal(receipt.badge,'已收到网络回执');
 assert.match(receipt.summary,/业务结果以场景反馈为准/);
 assert.doesNotMatch(receipt.summary,/执行成功|任务完成/);
}
for(const status of [400,403,500])assert.equal(story.receipt({data_source:'live',upstream:{http_status:status}}).badge,'网络侧异常响应');
console.log('showcase story: paths and truthful receipt classification passed');

const channels=[{id:'patrol',service_id:'robot_patrol'},{id:'traffic',service_id:'traffic_flow_detection'},{id:'legacy'}];
assert.deepEqual(story.feedbackChannels(channels,'robot_patrol').map(c=>c.id),['patrol']);
assert.deepEqual(story.feedbackChannels(channels,'traffic_flow_detection').map(c=>c.id),['traffic']);
assert.deepEqual(story.feedbackChannels(channels,'').map(c=>c.id),['legacy']);
const handoff=story.feedbackHandoff({id:'internal-only',feedback_endpoint:'/api/v1/scene-feedback',receiver_key:'test-key',events_endpoint:'/legacy/events',media_endpoint:'/legacy/media'},'http://localhost');
assert.equal(handoff.url,'http://localhost/api/v1/scene-feedback');
assert.equal(handoff.receiver_key,'test-key');
assert(!JSON.stringify(handoff).includes('internal-only'));
assert(!('events_endpoint' in handoff)&&!('media_endpoint' in handoff)&&!('channel_id' in handoff));
console.log('Scene feedback: scene-bound selection and minimal handoff passed');

const {businessResult}=require('../static/showcase-story.js');
assert.match(businessResult({data_source:'demo',demo_result:{text:'【演示结果】巡检报告'}}),/【演示结果】/);
assert.equal(businessResult({data_source:'live',upstream:{http_status:200,body:{result:{text:'目标已识别'}}}}),'目标已识别');
assert.equal(businessResult({data_source:'live',upstream:{http_status:202,body:{message:'accepted'}}}),'accepted');
assert.match(businessResult({data_source:'live',upstream:{http_status:202,body:{received:true}}}),/尚未返回文字业务结果/);
assert.equal(businessResult({data_source:'live',upstream:{http_status:200,body:'实际文字报告'}}),'实际文字报告');
console.log('Text result: demo, plain text, nested result and acceptance-only behavior passed.');
