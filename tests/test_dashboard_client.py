import pytest

from dashboard.client import request_json


class _Response:
    def __init__(self):
        self.checked = False

    def raise_for_status(self):
        self.checked = True

    def json(self):
        return {"status": "answered"}


def test_request_json_retorna_payload_tempo_e_valida_http():
    captured = {}
    response = _Response()

    def post(url, *, json, timeout):
        captured.update(url=url, json=json, timeout=timeout)
        return response

    timestamps = iter((10.0, 12.345))

    result = request_json(
        post,
        "http://api/chat",
        {"pergunta": "como ajustar correia?"},
        timeout=330.0,
        clock=lambda: next(timestamps),
    )

    assert result.payload == {"status": "answered"}
    assert result.elapsed_seconds == pytest.approx(2.345)
    assert response.checked is True
    assert captured == {
        "url": "http://api/chat",
        "json": {"pergunta": "como ajustar correia?"},
        "timeout": 330.0,
    }
