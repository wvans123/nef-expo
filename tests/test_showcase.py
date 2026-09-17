"""Active original workbench contracts and compatibility entry; browser runs verify interactions."""
from html.parser import HTMLParser
from fastapi.testclient import TestClient
from server import app

client=TestClient(app)

class Assets(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.assets=[];self.tabs={}
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if 'data-tab' in a:self.tabs[a['data-tab']]='hidden' in a
        if tag in {'script','link'}:
            url=a.get('src') or a.get('href')
            if url:self.assets.append(url)

def test_original_workbench_is_the_active_ui():
    r=client.get('/');assert r.status_code==200
    html=r.text
    assert all(x in html for x in ['一张网络，无限调用','id="tabs"','id="pkg-row"','id="cap-list"','id="pipe-zone"','id="api-params"','id="mcp-params"','id="intent-result"'])
    parsed=Assets();parsed.feed(html)
    assert {k for k,v in parsed.tabs.items() if not v}=={'market','subs','api','mcp','intent','composer','afreg'}
    assert parsed.tabs['skill'] and parsed.tabs['term']
    assert 'if(!btn||btn.hidden)' in html
    assert len(parsed.ids)==len(set(parsed.ids))
    for url in parsed.assets:
        assert url.startswith('/static/') and client.get(url).status_code==200
    assert '让评委记住' not in html

def test_showcase_bookmark_redirects_to_original_instead_of_parallel_ui():
    html=client.get('/static/showcase.html').text
    assert "location.replace('/'+location.hash)" in html
    assert 'page-market' not in html and '打开 6G NEF' in html

def test_original_drag_sort_and_capability_modals_are_preserved():
    html=client.get('/').text
    assert all(x in html for x in ['window.showCap','window.showPkg','confirmSubscribe','function bindDrag','function renderPipe','p.ondrop','pipeSteps.splice','套餐 JSON 预览'])
    js=client.get('/static/workbench.js').text
    assert 'function composerSteps()' in client.get('/static/composer.js').text
    assert '/api/v1/network/packages' in js
    assert '/api/v1/pipelines/' not in js

def test_three_scene_intent_and_truthful_authorization():
    js=client.get('/static/workbench.js').text
    assert '/api/v1/services' in js and "+'/intent'" in js
    assert "'X-NEF-Execution':mode" in js
    assert 'renderAuthPipeline' in js and 'NefStory.businessResult' in js
    assert 'Planning Agent' not in js and 'intent_id' not in js and 'task_id' not in js
    html=client.get('/').text
    assert '逐级核验' in html and '按所选场景订阅授权' in html
    assert '${s.latency_ms}ms' not in html

def test_mcp_discovery_remains_before_tool_selection():
    js=client.get('/static/workbench.js').text
    assert "'<option value=\"\">先连接并发现工具</option>'" in js
    assert 'await wbMcp.connect()' in js and 'await wbMcp.discover()' in js
    assert 'NefMcp.parseArguments' in js
    assert "api('/mcp'" in js

def test_simple_server_registration_and_network_directory():
    html=client.get('/').text;js=client.get('/static/workbench.js').text
    assert all(f'id="{x}"' in html for x in ['wb-server-json','wb-server-list','wb-catalog-status','wb-network-market'])
    assert 'af-param-rows' not in html
    assert 'JSON.parse($(\'#wb-server-json\').value)' in js
    assert '/api/v1/network/servers' in js
    assert "'discover'" in js and "'sync'" in js

def test_feedback_only_invocations_and_simplified_handoff():
    html=client.get('/').text;js=client.get('/static/workbench.js').text
    assert 'id="wb-feedback" hidden' in html
    assert "if(tab==='intent')" in js and "if(tab==='api')" in js
    assert "if(tab==='mcp'&&wbMcp.state.selected)" in js
    assert 'NefStory.feedbackHandoff(c,location.origin)' in js
    assert "+'/feedback-access'" in js and 'URL.revokeObjectURL' in js
    assert 'wb-feedback-source' not in html and 'wb-source-name' not in js
    assert '场景专用回传接口' in js
    assert 'c.events_endpoint' not in js

def test_original_theme_and_reduced_motion():
    html=client.get('/').text
    assert '--bg:#050b1f' in html and '--accent:#39d2ff' in html
    css=client.get('/static/workbench.css').text
    assert 'prefers-reduced-motion' in css


def test_compact_scenes_automatic_catalog_and_af_provenance():
    html=client.get('/').text;js=client.get('/static/workbench.js').text
    assert 'wb-refresh-catalog' not in html and 'wb-refresh-catalog' not in js
    assert 'Intent 驱动 · 按场景开通' not in html and '>INTENT</span>' not in js
    assert '基础能力组合' in js and 'data-scene-cap' in js
    assert "'/api/v1/network/catalog/refresh'" in js and '30000' in js
    assert '自助编排 · ' in js
    assert 'const afTools=' in js and "source:'AF'" in js and 'source_account' in js
    scenes=client.get('/api/v1/services').json()['services']
    assert all(s['provenance']['source']=='preset' and s['provenance']['components'] for s in scenes)


def test_network_gateway_story_and_publication_are_visible():
    html=client.get('/').text;js=client.get('/static/workbench.js').text
    assert '网络内部 · ARF / TRF 能力目录' in html
    assert '内部网元 / NW Agent' in html and 'AF · tools/call' in html
    assert '查看网络登记内容' in js and 's.gateway_path' in js
    assert '最近网络调用' in js and 's.last_call.caller' in js
    assert "+'/publication'" in js


def test_selected_catalog_publication_is_a_separate_explicit_action():
    html=client.get('/').text
    assert 'id="wb-open-catalog-publication"' in html
    js=client.get('/static/catalog-ui.js').text
    assert "CAPS.filter(c=>c.status==='available')" in js
    assert 'wb.catalog' not in js and 'wb.servers' not in js
    assert 'capability_ids:' in js and 'service_ids:' in js
    assert "'/api/v1/network/catalog/'" in js
