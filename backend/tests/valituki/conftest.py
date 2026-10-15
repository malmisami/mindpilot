from __future__ import annotations

import pytest

from app.config import settings
from app.valituki import ai, content, intake, records
from app.valituki.scenes import build_scene
from app.valituki.seed import build_seed_state
from app.valituki.store import get_client


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own state file, the deterministic AI mode and no API key – even when the developer's .env
    has a real one (setenv, not delenv, so that a key a test loads from its own .env is undone afterwards too)."""
    monkeypatch.setattr(settings, 'VALITUKI_STATE_PATH', str(tmp_path / 'valituki_state.json'))
    monkeypatch.setattr(settings, 'VALITUKI_AI_MODE', 'DEMO_AI_MODE')
    monkeypatch.setattr(settings, 'VALITUKI_AI_MODEL', settings.VALITUKI_AI_MODEL)
    monkeypatch.setattr(ai, 'ENV_FILE', tmp_path / '.env')
    for name in ai.KEY_VARS:
        monkeypatch.setenv(name, '')


@pytest.fixture
def state():
    return build_seed_state()


@pytest.fixture
def scene():
    return build_scene


def client_of(state, client_id='cl-aino'):
    return get_client(state, client_id)


def run_intake(state, client_id='cl-aino'):
    """Sami's scripted intake through the same functions the UI calls."""
    client = client_of(state, client_id)
    intake.run_scripted(state, client, content.client_spec(client_id)['intake'], records.client_actor(client_id))
    return client
