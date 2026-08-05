import math

import pandas as pd

from app.data.loader import FEATURE_COLUMNS
from scripts.simulator import _num, build_payload


def test_num_handles_plain_float_and_non_coercible_values():
    assert _num(3.5) == 3.5
    assert _num("2.1") == 2.1
    assert _num(None) is None
    assert _num("nao-e-numero") is None


def test_build_payload_never_emits_none_and_warns_on_fallback(capsys):
    row = pd.Series({c: "abc" for c in FEATURE_COLUMNS})
    payload = build_payload(row)
    assert set(payload) == set(FEATURE_COLUMNS)
    assert all(v == 0.0 for v in payload.values())
    out = capsys.readouterr().out
    assert "aviso" in out
    assert FEATURE_COLUMNS[0] in out


def test_build_payload_over_200_real_rows_no_exceptions_all_floats():
    """Validacao obrigatoria (fix round 1, finding 1): monta o payload de
    /eventos (via build_payload/_num, sem rede) para 200 linhas reais do
    banner.xlsx — incluindo os artefatos datetime presentes em ~37,7% das
    linhas — e confirma zero excecoes e nenhum None/NaN no payload final
    (contrato exigido por EventIn.validate_features, que faz float(v) em
    cada campo)."""
    df = pd.read_excel("banner.xlsx").head(200)
    assert len(df) == 200

    fallback_columns: set[str] = set()
    for _, row in df.iterrows():
        payload = build_payload(row)  # nao deve levantar excecao
        assert set(payload.keys()) == set(FEATURE_COLUMNS)
        for c in FEATURE_COLUMNS:
            v = payload[c]
            assert isinstance(v, float), f"{c}={v!r} nao e float"
            assert not math.isnan(v), f"{c} veio NaN no payload final"
            if v == 0.0 and _num(row[c]) is None:
                fallback_columns.add(c)

    # Nao e uma asserção de negocio (o objetivo e so provar ausencia de
    # excecao/None/NaN); serve de evidencia no report de quais colunas, se
    # houver, precisaram do fallback 0.0 nas 200 linhas amostradas.
    print(f"colunas com fallback 0.0 nas 200 linhas: {sorted(fallback_columns)}")
