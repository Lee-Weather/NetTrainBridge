#!/usr/bin/env python3
"""gm_client 单元测试（无网络）。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import httpx
import pytest

_AGENT_DIR = Path(__file__).resolve().parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from config import AgentConfig  # noqa: E402
from gm_client import GMClient, GMClientError, _extract_model_list, _unwrap_payload  # noqa: E402


def test_extract_rows() -> None:
    payload = {"rows": [{"checkpoint": "50", "fileName": "model_50.pt"}]}
    assert len(_extract_model_list(payload)) == 1


def test_unwrap_nested_data() -> None:
    payload = {
        "code": 200,
        "success": True,
        "data": {"rows": [{"checkpoint": "1"}]},
    }
    inner = _unwrap_payload(payload)
    assert len(_extract_model_list(inner)) == 1


def test_unwrap_raises_on_token_expired() -> None:
    payload = {
        "code": 401,
        "msg": "用户token已失效，请重新登录",
        "success": False,
        "data": "",
    }
    with pytest.raises(GMClientError, match="token"):
        _unwrap_payload(payload)


def test_list_models_sends_x_api_key_header() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["X-Api-Key"] = request.headers.get("X-Api-Key", "")
        seen["Authorization"] = request.headers.get("Authorization", "")
        return httpx.Response(
            200,
            json={"code": 200, "success": True, "data": {"rows": [{"checkpoint": "1"}]}},
        )

    config = AgentConfig()
    config.gm_api_key = "gm_sk_test"
    config.gm_base_url = "http://mock-gm.local"
    client = GMClient(config, transport=httpx.MockTransport(handler))
    models = client.list_models("TASK_xxx")
    assert len(models) == 1
    assert seen["X-Api-Key"] == "gm_sk_test"
    assert seen["Authorization"] == ""


def test_download_omits_api_key_header() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["X-Api-Key"] = request.headers.get("X-Api-Key", "")
        seen["Authorization"] = request.headers.get("Authorization", "")
        return httpx.Response(200, content=b"pt-bytes")

    config = AgentConfig()
    config.gm_api_key = "gm_sk_test"
    config.gm_base_url = "http://mock-gm.local"
    config.proxy = "http://proxy.local:8080"
    client = GMClient(config, transport=httpx.MockTransport(handler))
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "model.pt"
        client.download("https://oss.example.com/model_50.pt", dest)
        assert dest.read_bytes() == b"pt-bytes"
    assert seen["X-Api-Key"] == ""
    assert seen["Authorization"] == ""


def test_list_models_raises_on_401_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 401,
                "msg": "用户token已失效，请重新登录",
                "success": False,
                "data": "",
            },
        )

    config = AgentConfig()
    config.gm_api_key = "bad-key"
    config.gm_base_url = "http://mock-gm.local"
    client = GMClient(config, transport=httpx.MockTransport(handler))

    with pytest.raises(GMClientError, match="token"):
        client.list_models("TASK_xxx")


if __name__ == "__main__":
    test_extract_rows()
    test_unwrap_nested_data()
    test_unwrap_raises_on_token_expired()
    test_list_models_sends_x_api_key_header()
    test_download_omits_api_key_header()
    test_list_models_raises_on_401_body()
    print("test_gm_client passed")
