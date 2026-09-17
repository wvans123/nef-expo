"""Composition tests use an actual HTTP peer; no provider credentials required."""
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from composition import check_composition, SYSTEM_PROMPT
from network_registry import build_router, reset_state_for_tests
from test_network_registry import LocalHTTPFixture, fake_auth, headers
from scene_services import SCENES
from skills import CAP_INDEX

@pytest.fixture
def client(monkeypatch, tmp_path):
    reset_state_for_tests()
    monkeypatch.setenv('NEF_COMPOSER_CONFIG', str(tmp_path / 'missing-composer.json'))
    app = FastAPI(); app.include_router(build_router(fake_auth))
    with TestClient(app) as c:
        yield c
    reset_state_for_tests()

@pytest.fixture
def peer(monkeypatch, tmp_path):
    peer = LocalHTTPFixture()
    path = tmp_path/'composer.json'
    path.write_text(json.dumps({'endpoint':peer.url('/chat'),'model':'test-model','api_key_env':'TEST_COMPOSER_KEY'}))
    monkeypatch.setenv('TEST_COMPOSER_KEY','test-secret-not-for-browser')
    monkeypatch.setenv('NEF_COMPOSER_CONFIG',str(path))
    yield peer
    peer.close()

def proposal(steps=None):
    return {'name':'目标观测','description':'检测后追踪','steps':steps or [{'capability_id':'target_detection'},{'capability_id':'target_tracking'}]}

def response(peer, value, status=200):
    peer.add('POST','/chat',lambda r:(status,{},json.dumps({'choices':[{'message':{'content':json.dumps(value)}}]}).encode()))

def test_scene_components_are_actual_available_capabilities():
    for s in SCENES.values():
        refs=s['provenance']['components']
        assert len(refs)>=3
        assert all(CAP_INDEX[r['capability_id']].status=='available' and r['role'] for r in refs)

def test_conditional_conflicts_and_resolutions():
    steps=[{'capability_id':'sensing_fusion','params':{'fusion_mode':'batch'}}]
    assert not check_composition(steps,{'delivery':'realtime'})['valid']
    assert check_composition(steps,{'delivery':'batch'})['valid']
    steps=[{'capability_id':'compute_qos','params':{'gpu_share_pct':80}}]
    assert not check_composition(steps,{'gpu_budget_pct':40})['valid']
    assert check_composition(steps,{'gpu_budget_pct':100})['valid']
    steps=[{'capability_id':'target_tracking'},{'capability_id':'target_detection'}]
    assert not check_composition(steps,{'target_source':'detection'})['valid']
    assert check_composition(list(reversed(steps)),{'target_source':'detection'})['valid']
    assert check_composition(steps,{'target_source':'external'})['valid']

@pytest.mark.parametrize('patch',[
    {'context':{'delivery':'realtime'},'steps':[{'capability_id':'sensing_fusion','params':{'fusion_mode':'batch'}}]},
    {'steps':[{'capability_id':'vital_sign_detection'}]},
    {'steps':[{'capability_id':'qos_guarantee','params':{'unknown':1}}]},
    {'steps':[{'capability_id':'compute_qos','params':{'gpu_share_pct':True}}]},
    {'steps':[{'capability_id':'missing'}]},
    {'steps':[{'capability_id':'target_detection'},{'capability_id':'target_detection'}]},
    {'context':{'gpu_budget_pct':0}},
    {'context':{'unexpected':True}},
])
def test_save_cannot_bypass_validation(client,patch):
    body={'name':'test','execution_target':'network','steps':[{'capability_id':'target_detection'}],**patch}
    assert client.post('/api/v1/network/packages',headers=headers(),json=body).status_code==422
    assert client.get('/api/v1/network/packages',headers=headers()).json()['packages']==[]

def test_config_unavailable_and_auth(client):
    assert client.get('/api/v1/composer/status').status_code==401
    assert client.get('/api/v1/composer/status',headers=headers('caller-list')).status_code==403
    r=client.post('/api/v1/composer/recommend',headers=headers(),json={'text':'巡检'})
    assert r.status_code==503 and 'proposal' not in r.json()
    assert r.json()["detail"]["code"] == "composer_config_missing"
    status = client.get('/api/v1/composer/status', headers=headers()).json()
    assert status["configured"] is False
    assert status["code"] == "composer_config_missing"
    assert status["connectivity"] == "not_checked"


@pytest.mark.parametrize("key", [None, "", "   "])
def test_status_identifies_missing_process_key_without_contacting_model(client, peer, monkeypatch, key):
    if key is None:
        monkeypatch.delenv("TEST_COMPOSER_KEY")
    else:
        monkeypatch.setenv("TEST_COMPOSER_KEY", key)
    result = client.get("/api/v1/composer/status", headers=headers())
    assert result.json()["code"] == "composer_key_missing"
    assert result.json()["configured"] is False
    failed = client.post("/api/v1/composer/recommend", headers=headers(), json={"text": "巡检"})
    assert failed.status_code == 503
    assert failed.json()["detail"]["code"] == "composer_key_missing"
    assert peer.requests == []


def test_status_checks_configuration_not_connectivity_and_redacts_secrets(client, peer):
    result = client.get("/api/v1/composer/status", headers=headers())
    assert result.json() == {"configured": True, "code": "configured",
                             "message": "模型已配置", "connectivity": "not_checked"}
    assert peer.requests == []
    assert "test-secret-not-for-browser" not in result.text
    assert peer.url("/chat") not in result.text


@pytest.mark.parametrize("content", ["not json", "[]", '{"model":"private-value"}'])
def test_status_distinguishes_invalid_config_without_echoing_it(client, monkeypatch, tmp_path, content):
    path = tmp_path / "bad-config.json"
    path.write_text(content, encoding="utf-8")
    monkeypatch.setenv("NEF_COMPOSER_CONFIG", str(path))
    result = client.get("/api/v1/composer/status", headers=headers())
    assert result.json()["configured"] is False
    assert result.json()["code"] == "composer_config_invalid"
    assert "private-value" not in result.text


def test_real_llm_request_confirmation_and_account_isolation(client,peer):
    response(peer,proposal())
    r=client.post('/api/v1/composer/recommend',headers=headers(),json={'text':'请识别并追踪目标','context':{'target_source':'detection'}})
    assert r.status_code==200,r.text
    assert r.json()['requires_confirmation'] and r.json()['source']=='llm'
    wire=json.loads(peer.requests[0]['body'])
    assert wire['messages'][0]=={'role':'system','content':SYSTEM_PROMPT}
    assert json.loads(wire['messages'][1]['content'])['requirement']=='请识别并追踪目标'
    assert peer.requests[0]['headers']['authorization']=='Bearer test-secret-not-for-browser'
    assert 'test-secret-not-for-browser' not in r.text
    assert client.get('/api/v1/network/packages',headers=headers()).json()['packages']==[]
    saved=client.post('/api/v1/network/packages',headers=headers(),json={**r.json()['proposal'],'execution_target':'network','context':{'target_source':'detection'}})
    assert saved.status_code==200 and saved.json()['sync_status']=='pending'
    assert client.get('/api/v1/network/packages',headers=headers('caller-b')).json()['packages']==[]
    assert len(peer.requests)==1  # no publication or execution on recommendation/save

@pytest.mark.parametrize('value',[
    proposal([{'capability_id':'invented_tool'}]),
    proposal([{'capability_id':'target_detection'},{'capability_id':'target_detection'}]),
    proposal([{'capability_id':'sensing_fusion','params':{'fusion_mode':'batch'}}]),
    proposal([{'capability_id':'qos_guarantee','params':{'latency_ms':'wrong'}}]),
    {'unavailable':'no match'},
    {'name':'test-secret-not-for-browser','description':'x','steps':[{'capability_id':'target_detection'}]},
    ['not an object'],
])
def test_invalid_model_output_never_becomes_saved_package(client,peer,value):
    response(peer,value)
    r=client.post('/api/v1/composer/recommend',headers=headers(),json={'text':'实时识别','context':{'delivery':'realtime'}})
    assert r.status_code in (422,502),r.text
    assert 'test-secret-not-for-browser' not in r.text
    assert client.get('/api/v1/network/packages',headers=headers()).json()['packages']==[]

def test_provider_errors_are_redacted_and_redirect_not_followed(client,peer):
    peer.add('POST','/chat',lambda r:(302,{'Location':peer.url('/stolen')},b'test-secret-not-for-browser'))
    r=client.post('/api/v1/composer/recommend',headers=headers(),json={'text':'目标检测'})
    assert r.status_code==502 and 'test-secret-not-for-browser' not in r.text
    assert len(peer.requests)==1


def test_customer_page_has_composition_not_implementation_notes():
    from pathlib import Path
    html=Path('static/index.html').read_text(encoding='utf-8')
    js=Path('static/workbench.js').read_text(encoding='utf-8')
    assert 'composer-confirm' in Path('static/composer.js').read_text(encoding='utf-8-sig')
    assert '基础能力组合' in js and 'data-scene-cap' in js
    for phrase in ['访问策略实现说明','NEF 保存有序能力声明，不在本地虚构','定义不等于执行，网络侧承接']:
        assert phrase not in html

def test_all_atomic_capabilities_have_explicit_standard_basis_and_safe_extension_default():
    from skills import CAPABILITY_STANDARDS, Capability
    assert set(CAPABILITY_STANDARDS)==set(CAP_INDEX)
    assert all(c.to_dict()['standard_basis']['api_contract']=='project_defined' for c in CAP_INDEX.values())
    assert Capability('external','外部','外部能力','ecosystem','basic').to_dict()['standard_basis']['api_contract']=='provider_defined'
    assert 'AKMA' not in CAP_INDEX['identity_service'].description
    assert '亚米级' not in CAP_INDEX['precision_location'].description
    assert '全天候高置信' not in CAP_INDEX['sensing_fusion'].description


def test_base_url_builds_real_chat_completions_request(client, peer, monkeypatch, tmp_path):
    path = tmp_path / "base-url.json"
    path.write_text(json.dumps({
        "base_url": peer.url("/v1/"), "model": "test-model", "api_key_env": "TEST_COMPOSER_KEY",
    }), encoding="utf-8")
    monkeypatch.setenv("NEF_COMPOSER_CONFIG", str(path))
    peer.add("POST", "/v1/chat/completions", lambda r: (
        200, {}, json.dumps({"choices": [{"message": {"content": json.dumps(proposal())}}]}).encode(),
    ))
    response = client.post("/api/v1/composer/recommend", headers=headers(), json={"text": "track"})
    assert response.status_code == 200, response.text
    assert json.loads(peer.requests[0]["body"])["model"] == "test-model"
    assert peer.requests[0]["headers"]["authorization"] == "Bearer test-secret-not-for-browser"


@pytest.mark.parametrize("patch", [
    {"base_url": "https://example.com/v1?secret=x"},
    {"base_url": "https://example.com/v1#fragment"},
    {"base_url": "http://example.com/v1"},
    {"base_url": "https://user:password@example.com/v1"},
    {"base_url": "https://example.com/v1", "endpoint": "https://other.example.com/chat"},
    {"base_url": 123},
    {"model": ""},
    {"api_key_env": ""},
    {"api_key_env": "invalid variable"},
    {"api_key_env": None},
    {"wire_api": "unknown"},
    {"wire_api": "responses", "reasoning_effort": "invalid"},
    {"wire_api": "chat", "reasoning_effort": "high"},
])
def test_invalid_base_url_config_fails_closed(monkeypatch, tmp_path, patch):
    from composition import load_llm_config
    from fastapi import HTTPException
    config = {"base_url": "http://127.0.0.1:8317/v1", "model": "model",
              "api_key_env": "TEST_COMPOSER_KEY", **patch}
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("NEF_COMPOSER_CONFIG", str(path))
    monkeypatch.setenv("TEST_COMPOSER_KEY", "secret")
    with pytest.raises(HTTPException) as exc:
        load_llm_config()
    assert exc.value.status_code == 503


def test_shipped_config_matches_remote_provider_without_secret():
    from pathlib import Path
    config = json.loads(Path("config/composer.example.json").read_text(encoding="utf-8"))
    assert config == {"base_url": "https://sub2api.2012wtlab.com/v1", "model": "gpt-6-astra",
                      "wire_api": "responses", "reasoning_effort": "low",
                      "api_key_env": "NEF_COMPOSER_API_KEY"}


def responses_payload():
    return {"status": "completed", "output": [
        {"type": "reasoning", "summary": []},
        {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": json.dumps(proposal())},
        ]},
    ]}


@pytest.fixture
def responses_peer(peer, monkeypatch, tmp_path):
    path = tmp_path / "responses.json"
    path.write_text(json.dumps({
        "base_url": peer.url("/v1"), "model": "gpt-6-astra",
        "wire_api": "responses", "reasoning_effort": "high", "api_key_env": "TEST_COMPOSER_KEY",
    }), encoding="utf-8")
    monkeypatch.setenv("NEF_COMPOSER_CONFIG", str(path))
    return peer


def test_responses_request_and_output_over_real_http(client, responses_peer):
    peer = responses_peer
    peer.add("POST", "/v1/responses", lambda r: (200, {}, json.dumps(responses_payload()).encode()))
    response = client.post("/api/v1/composer/recommend", headers=headers(), json={"text": "track"})
    assert response.status_code == 200, response.text
    assert response.json()["proposal"] == proposal()
    wire = json.loads(peer.requests[0]["body"])
    assert wire["model"] == "gpt-6-astra" and wire["reasoning"] == {"effort": "high"}
    assert wire["instructions"] == SYSTEM_PROMPT
    assert json.loads(wire["input"][0]["content"])["requirement"] == "track"
    assert wire["store"] is False and wire["stream"] is False
    assert not {"messages", "temperature", "max_tokens"} & wire.keys()
    assert peer.requests[0]["headers"]["authorization"] == "Bearer test-secret-not-for-browser"
    assert "test-secret-not-for-browser" not in response.text


@pytest.mark.parametrize("protocol", ["chat", "responses"])
def test_model_receives_current_available_catalog_and_source(client, request, protocol, monkeypatch):
    from dataclasses import replace
    peer = request.getfixturevalue("responses_peer" if protocol == "responses" else "peer")
    if protocol == "responses":
        peer.add("POST", "/v1/responses", lambda r: (200, {}, json.dumps(responses_payload()).encode()))
    else:
        response(peer, proposal())
    for text in ("首次设计", "更新能力后设计"):
        if text == "更新能力后设计":
            cap = CAP_INDEX["target_detection"]
            monkeypatch.setitem(CAP_INDEX, cap.id, replace(cap, description="updated capability description"))
        result = client.post("/api/v1/composer/recommend", headers=headers(), json={
            "text": text, "context": {"target_source": "detection", "gpu_budget_pct": 40},
        })
        assert result.status_code == 200, result.text
        wire = json.loads(peer.requests[-1]["body"])
        data = json.loads(wire["input"][0]["content"] if protocol == "responses" else wire["messages"][1]["content"])
        catalog = {c["capability_id"]: c for c in data["catalog"]}
        assert set(catalog) == {c.id for c in CAP_INDEX.values() if c.status == "available"}
        assert "vital_sign_detection" not in catalog
        assert data["constraints"] == {"target_source": "detection", "gpu_budget_pct": 40}
        assert data["catalog_source"]["lookup_enabled"] is False
        assert data["catalog_source"]["includes_private_af_tools"] is False
        assert data["catalog_source"]["discovery_path"] == "/api/v1/capabilities"
        for cap_id, entry in catalog.items():
            cap = CAP_INDEX[cap_id]
            assert entry["description"] == cap.description
            assert entry["parameters"] == cap.mcp_tool()["inputSchema"]
            assert entry["standard_basis"] == cap.to_dict()["standard_basis"]
            assert entry["source"] == cap.source and entry["status"] == "available"
        assert "test-secret-not-for-browser" not in json.dumps(data)
    assert len(peer.requests) == 2


@pytest.mark.parametrize("payload", [
    {"status": "incomplete", "output": responses_payload()["output"]},
    {"status": "failed", "output": []},
    {"status": "completed", "output": []},
    {"status": "completed", "output": [{"type": "message", "role": "assistant",
                                      "content": [{"type": "refusal", "refusal": "no"}]}]},
    {"status": "completed", "output": [{"type": "function_call", "name": "execute"}]},
    {"status": "completed", "output": [None]},
    {"status": "completed", "output": [{"type": "message", "role": "assistant",
                                      "content": [{"type": "output_text", "text": "not JSON"}]}]},
    {"status": "completed", "output": [{"type": "message", "role": "assistant",
                                      "content": [{"type": "output_text", "text": json.dumps({
                                          "name": "test-secret-not-for-browser", "description": "",
                                          "steps": [{"capability_id": "target_detection"}],
                                      })}]}]},
])
def test_bad_responses_fail_closed(client, responses_peer, payload):
    responses_peer.add("POST", "/v1/responses", lambda r: (200, {}, json.dumps(payload).encode()))
    response = client.post("/api/v1/composer/recommend", headers=headers(), json={"text": "track"})
    assert response.status_code == 502, response.text
    assert "test-secret-not-for-browser" not in response.text
    assert client.get("/api/v1/network/packages", headers=headers()).json()["packages"] == []


def test_safe_error_code_and_request_id_for_upstream_failure(client, peer, caplog):
    response(peer, {"error": "test-secret-not-for-browser"}, status=429)
    result = client.post("/api/v1/composer/recommend", headers=headers(), json={"text": "private-user-text"})
    assert result.status_code == 502
    detail = result.json()["detail"]
    assert detail["code"] == "model_upstream_error" and detail["request_id"].startswith("compose_")
    assert detail["request_id"] in caplog.text and "upstream_status=429" in caplog.text
    assert "test-secret-not-for-browser" not in result.text + caplog.text
    assert "private-user-text" not in caplog.text and peer.url("/chat") not in caplog.text


def test_invalid_json_has_distinct_diagnostic(client, peer, caplog):
    peer.add("POST", "/chat", lambda r: (200, {}, b"not-json"))
    result = client.post("/api/v1/composer/recommend", headers=headers(), json={"text": "private-user-text"})
    assert result.json()["detail"]["code"] == "model_invalid_response"
    assert "not-json" not in result.text + caplog.text


def test_timeout_has_distinct_diagnostic(client, peer, monkeypatch, caplog):
    import composition
    original = composition.httpx.AsyncClient

    def timed_client(**kwargs):
        def timeout(_request):
            raise composition.httpx.ReadTimeout("test-secret-not-for-browser")
        return original(**kwargs, transport=composition.httpx.MockTransport(timeout))

    monkeypatch.setattr(composition.httpx, "AsyncClient", timed_client)
    result = client.post("/api/v1/composer/recommend", headers=headers(), json={"text": "test"})
    assert result.status_code == 504 and result.json()["detail"]["code"] == "model_timeout"
    assert "test-secret-not-for-browser" not in result.text + caplog.text
