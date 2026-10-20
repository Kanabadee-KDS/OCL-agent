import pytest
from fastapi.testclient import TestClient
from ocl_api.config import Settings
from ocl_api.main import create_app


def test_health_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:26b")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["ollama_model"] == "gemma4:26b"


def test_settings_reject_keep_alive_on_hris_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:12b")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    with pytest.raises(ValueError, match="OLLAMA_KEEP_ALIVE must be empty"):
        Settings(_env_file=None)


def test_settings_allow_hris_model_without_keep_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:12b")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "")
    s = Settings(_env_file=None)
    assert s.ollama_keep_alive is None


def test_settings_require_positive_num_ctx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:26b")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "0")
    with pytest.raises(ValueError, match="OLLAMA_NUM_CTX"):
        Settings(_env_file=None)
