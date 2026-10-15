"""VALITUKI_AI_PROVIDER=openai: the same live calls go to an OpenAI-compatible server (vLLM on an AMD GPU)."""
from __future__ import annotations

import json

import httpx

from app.config import settings
from app.valituki import ai

REAL_CLIENT = httpx.Client


def _server(monkeypatch, handler):
    """Route the module's httpx.Client to a fake vLLM server and record its requests."""
    seen = []

    def fake_client(**kwargs):
        def record(request):
            seen.append(request)
            return handler(request)
        return REAL_CLIENT(transport=httpx.MockTransport(record), **kwargs)

    monkeypatch.setattr(httpx, 'Client', fake_client)
    return seen


def _vllm(request):
    if request.url.path.endswith('/models'):
        return httpx.Response(200, json={'data': [{'id': 'Qwen/Qwen2.5-72B-Instruct'}]})
    body = json.loads(request.content)
    content = '<think>hmm</think>{"reply": "Yhteys toimii."}' if body.get('response_format') else 'Hei, kuulostaa raskaalta.'
    return httpx.Response(200, json={'model': body['model'],
                                     'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}]})


def _use_vllm(monkeypatch, key=''):
    monkeypatch.setattr(settings, 'VALITUKI_AI_MODE', 'LIVE_AI_MODE')
    monkeypatch.setattr(settings, 'VALITUKI_AI_PROVIDER', 'openai')
    monkeypatch.setattr(settings, 'VALITUKI_OPENAI_BASE_URL', 'http://127.0.0.1:8000/v1/')
    monkeypatch.setenv(ai.OPENAI_KEY_VAR, key)


def test_the_server_address_alone_enables_live_mode(monkeypatch):
    monkeypatch.setattr(settings, 'VALITUKI_AI_MODE', 'LIVE_AI_MODE')
    monkeypatch.setattr(settings, 'VALITUKI_AI_PROVIDER', 'openai')
    assert ai.effective_mode() == 'DEMO_AI_MODE' and 'VALITUKI_OPENAI_BASE_URL puuttuu' in ai.status()['note']
    _use_vllm(monkeypatch)
    status = ai.status()
    assert ai.effective_mode() == 'LIVE_AI_MODE' and status['provider'] == 'openai' and status['providerLabel'] == 'AMD GPU'


def test_a_connection_check_uses_the_served_model_and_guided_json(monkeypatch):
    _use_vllm(monkeypatch, key='vllm-secret')
    seen = _server(monkeypatch, _vllm)
    check = ai.check_connection()
    assert check['ok'] and check['reply'] == 'Yhteys toimii.' and check['model'] == 'Qwen/Qwen2.5-72B-Instruct'
    models, chat = seen
    assert str(models.url) == 'http://127.0.0.1:8000/v1/models'
    assert chat.headers['authorization'] == 'Bearer vllm-secret'
    body = json.loads(chat.content)
    assert body['messages'][0] == {'role': 'system', 'content': ai.VALITUKI_SYSTEM_PROMPT}
    assert body['response_format']['json_schema']['schema'] == ai.CHECK_SCHEMA
    assert ai.status()['model'] == 'Qwen/Qwen2.5-72B-Instruct'
    ai.check_connection()
    assert len(seen) == 3  # the model list is asked once


def test_a_named_model_and_plain_text_replies(monkeypatch):
    _use_vllm(monkeypatch)
    monkeypatch.setattr(settings, 'VALITUKI_OPENAI_MODEL', 'meta-llama/Llama-3.3-70B-Instruct')
    seen = _server(monkeypatch, _vllm)
    text, failure = ai._llm('Sano jotain.')
    assert (text, failure) == ('Hei, kuulostaa raskaalta.', None)
    assert len(seen) == 1 and json.loads(seen[0].content)['model'] == 'meta-llama/Llama-3.3-70B-Instruct'
    assert 'response_format' not in json.loads(seen[0].content)


def test_server_errors_become_readable_reasons(monkeypatch):
    _use_vllm(monkeypatch)
    monkeypatch.setattr(settings, 'VALITUKI_OPENAI_MODEL', 'x')
    _server(monkeypatch, lambda request: httpx.Response(404, json={'object': 'error', 'message': 'The model `x` does not exist.'}))
    assert ai._llm('Hei') == (None, 'mallia tai osoitetta ei löydy (404): The model `x` does not exist.')
    _server(monkeypatch, lambda request: httpx.Response(401, json={'error': 'Unauthorized'}))
    assert ai._llm('Hei') == (None, 'API-avain ei kelpaa (401)')

    def unreachable(request):
        raise httpx.ConnectError('refused', request=request)
    _server(monkeypatch, unreachable)
    assert ai._llm('Hei') == (None, 'yhteysvirhe')


def test_the_provider_is_read_from_env_without_a_restart(monkeypatch):
    monkeypatch.setattr(settings, 'VALITUKI_AI_MODE', 'LIVE_AI_MODE')
    assert ai.status()['providerLabel'] == 'Claude'
    ai.ENV_FILE.write_text('VALITUKI_AI_PROVIDER=openai\nVALITUKI_OPENAI_BASE_URL=http://127.0.0.1:8000/v1\n'
                           'VALITUKI_OPENAI_LABEL=AMD MI300X\nVALITUKI_OPENAI_API_KEY=from-env-file\n')
    seen = _server(monkeypatch, _vllm)
    assert ai.set_mode('LIVE_AI_MODE')['check']['ok']
    assert ai.status()['providerLabel'] == 'AMD MI300X' and seen[-1].headers['authorization'] == 'Bearer from-env-file'
