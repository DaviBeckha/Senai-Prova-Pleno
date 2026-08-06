from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_env_example_define_database_url_externa_ativa():
    lines = _read(".env.example").splitlines()
    database_urls = [line for line in lines if line.startswith("DATABASE_URL=")]

    assert database_urls == [
        "DATABASE_URL=postgresql+psycopg://usuario:senha@host.docker.internal:5432/manutencao"
    ]


def test_compose_suporta_banco_do_host_no_docker_engine_linux():
    compose = _read("docker-compose.yml")

    assert "host.docker.internal=host-gateway" in compose
    assert "\n  postgres:" not in compose
    assert "${DATABASE_URL:?DATABASE_URL precisa estar definida no .env}" in compose


def test_readme_tem_inicio_rapido_copiavel_sem_nome_fixo_de_container():
    readme = _read("README.md")

    assert "## Comece aqui" in readme
    assert "docker compose config --quiet" in readme
    assert "docker compose up --build -d" in readme
    assert "docker compose exec ollama ollama pull" in readme
    assert "senai-prova-pleno-ollama-1" not in readme


def test_readme_explica_as_tres_localizacoes_do_postgresql_externo():
    readme = _read("README.md")

    assert "Banco no host + API no Docker" in readme
    assert "Banco em outro servidor" in readme
    assert "API e banco executados localmente" in readme
    assert "host.docker.internal" in readme
    assert "sslmode=require" in readme


def test_documentacao_reflete_os_contratos_atuais():
    readme = _read("README.md")
    demo = _read("demo/README.md")
    architecture = _read("docs/arquitetura.md")
    ci_requirements = _read("requirements-ci.txt")

    assert "681 testes" in readme
    assert "681 passed" in ci_requirements
    assert 'status: "diagnostico_inconclusivo"' in demo
    assert "refused_unsafe" not in readme
    assert "refused_unsafe" not in architecture
    assert "Docker indisponível" not in architecture
