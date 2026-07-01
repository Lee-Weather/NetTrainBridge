#!/usr/bin/env python3
"""步骤 6 Mock 验收：gm_client + fetch_runner（无需真实 gm）。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import httpx

_AGENT_DIR = Path(__file__).resolve().parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from config import AgentConfig  # noqa: E402
from fetch_runner import FetchRunner  # noqa: E402
from gm_client import GMClient, select_model  # noqa: E402

FAKE_PT = b"mock checkpoint bytes for step6"


def _mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/task/model/info"):
            body = {
                "data": {
                    "list": [
                        {
                            "checkpoint": "1000",
                            "fileName": "model_1000.pt",
                            "policUrlDown": "http://mock-gm.local/files/model_1000.pt",
                        },
                        {
                            "checkpoint": "3000",
                            "fileName": "model_3000.pt",
                            "policUrlDown": "http://mock-gm.local/files/model_3000.pt",
                        },
                    ],
                },
            }
            return httpx.Response(200, json=body)
        if "/files/model_3000.pt" in str(request.url):
            return httpx.Response(200, content=FAKE_PT)
        return httpx.Response(404, text=f"unexpected {request.method} {request.url}")

    return httpx.MockTransport(handler)


def main() -> int:
    transport = _mock_transport()
    config = AgentConfig()
    config.gm_api_key = "mock-key"
    config.gm_base_url = "http://mock-gm.local"

    client = GMClient(config, transport=transport)
    models = client.list_models("task_mock_001")
    assert len(models) == 2, models

    latest = select_model(models, "latest")
    assert latest["checkpoint"] == "3000", latest

    selected = select_model(models, "model_3000.pt")
    assert selected["fileName"] == "model_3000.pt"

    runner = FetchRunner(config)
    runner.gm = GMClient(config, transport=transport)

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        path = runner.fetch_checkpoint("task_mock_001", "latest", dest)
        assert path.name == "model_3000.pt"
        assert path.read_bytes() == FAKE_PT

    print("test_fetch_mock passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
