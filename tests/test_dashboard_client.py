import pytest

from dashboard.tempo import medir


def test_medir_retorna_valor_e_tempo_decorrido():
    timestamps = iter((10.0, 12.345))

    result = medir(
        lambda: {"status": "respondido"},
        clock=lambda: next(timestamps),
    )

    assert result.valor == {"status": "respondido"}
    assert result.elapsed_seconds == pytest.approx(2.345)
