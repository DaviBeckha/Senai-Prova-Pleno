"""Regressões que precisam da imagem Linux real do dashboard.

São opt-in porque constroem e executam uma imagem Docker. Rode com
``RUN_DOCKER_TESTS=1 pytest tests/test_dashboard_container.py``.
"""

import os
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DOCKER_TESTS") != "1",
    reason="teste de integração Docker desabilitado",
)


def test_dashboard_suporta_conversoes_repetidas_de_dataframe():
    """Reproduz o SIGSEGV do PyArrow que encerrava o dashboard após reruns."""
    root = Path(__file__).resolve().parent.parent
    image = "senai-dashboard-regression-test:local"
    app_source = """\
import streamlit as st
st.dataframe(
    [{
        "Família de falha": "Correia",
        "Ocorrências": 11999,
        "Identificador": "correia",
        "Documento cadastrado": "sim",
    }],
    use_container_width=True,
    hide_index=True,
)
"""
    container_code = f"""\
from streamlit.testing.v1 import AppTest
source = {app_source!r}
for _ in range(50):
    test = AppTest.from_string(source).run(timeout=30)
    if test.exception:
        raise RuntimeError(str(list(test.exception)))
"""

    subprocess.run(
        [
            "docker", "build", "--file", "Dockerfile.dashboard",
            "--tag", image, ".",
        ],
        cwd=root,
        check=True,
    )
    try:
        completed = subprocess.run(
            [
                "docker", "run", "--rm", image,
                "python", "-X", "faulthandler", "-c", container_code,
            ],
            cwd=root,
            text=True,
            capture_output=True,
        )
    finally:
        subprocess.run(
            ["docker", "image", "rm", "--force", image],
            cwd=root,
            check=False,
            capture_output=True,
        )

    assert completed.returncode == 0, completed.stderr
