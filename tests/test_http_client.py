import pytest
from unittest.mock import patch, MagicMock
from src.infrastructure.http import MsClient
from src.config import settings

def test_msclient_post_success(monkeypatch):
    c = MsClient("co")
    # mock requests.post
    class Resp:
        status_code = 200
        content = b'{"ok": true}'
        def json(self): return {"ok": True}
        text = "ok"
    with patch("src.infrastructure.http.requests.post", return_value=Resp()) as p:
        r = c.post("/v1/foo", json={"a":1})
        assert r["ok"] is True
        p.assert_called_once()

def test_msclient_post_error(monkeypatch):
    c = MsClient("co")
    class RespBad:
        status_code = 400
        content = b'{"detail":"err"}'
        text = "bad"
        request = type("R", (), {"method": "POST"})
        url = "http://x"
    with patch("src.infrastructure.http.requests.post", return_value=RespBad()):
        with pytest.raises(ValueError):
            c.post("/v1/foo", json={})

def test_msclient_get_success():
    c = MsClient("co")
    class Resp:
        status_code = 200
        content = b'{"ok": true}'
        def json(self): return {"ok": True}
        text = "ok"
    with patch("src.infrastructure.http.requests.get", return_value=Resp()) as g:
        r = c.get("/v1/bar", params={"q":1})
        assert r["ok"] is True
        g.assert_called_once()
