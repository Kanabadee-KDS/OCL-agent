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


@pytest.mark.parametrize("keep_alive", ["10m", "", "5m"])
def test_hris_model_requires_keep_alive_minus_one(
    monkeypatch: pytest.MonkeyPatch, keep_alive: str
) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:12b")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", keep_alive)
    monkeypatch.setenv("OLLAMA_NUM_CTX", "")
    with pytest.raises(ValueError, match="OLLAMA_KEEP_ALIVE must be -1"):
        Settings(_env_file=None)


def test_hris_model_rejects_num_ctx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:12b")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "-1")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "32768")
    with pytest.raises(ValueError, match="OLLAMA_NUM_CTX must be empty"):
        Settings(_env_file=None)


def test_hris_model_ok_with_pin_and_no_ctx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:12b")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "-1")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "")
    s = Settings(_env_file=None)
    assert s.ollama_keep_alive == "-1" and s.ollama_num_ctx is None


def test_ocl_model_requires_num_ctx_and_keep_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:26b")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "0")
    with pytest.raises(ValueError, match="OLLAMA_NUM_CTX"):
        Settings(_env_file=None)
    monkeypatch.setenv("OLLAMA_NUM_CTX", "32768")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "")
    with pytest.raises(ValueError, match="OLLAMA_KEEP_ALIVE must be set"):
        Settings(_env_file=None)
