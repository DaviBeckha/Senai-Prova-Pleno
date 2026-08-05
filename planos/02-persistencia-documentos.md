# Plano 02 — Persistência e reindexação de documentos enviados

**Goal:** Uploads via `POST /documentos` devem sobreviver a reinício. Hoje o fluxo é: tempfile → indexa em memória → **apaga o arquivo** → grava só o NOME no registry (`app/api/main.py:74-95`). Após restart, o registry diz "documentado", o índice não tem os vetores, e a consulta cai na contenção "sem trechos" — quebra o RF5 (registro de novos documentos) exatamente no passo 5 do roteiro de demo.

**Estado atual (verificado 2026-08-05):**
- `app/api/main.py::documentos`: salva `NamedTemporaryFile`, chama `ingest_pdf(path, family, state.index)`, `os.unlink` no finally, `state.registry.register(family, title, file.filename or path)`.
- `scripts/bootstrap.py::build_state`: reindexa APENAS o `PDF_MAP` fixo (6 documentos). `registry.list_documents()` existe mas não é usado no bootstrap.
- `DocumentRegistry.register` NÃO deduplica (aceita family+title repetidos à vontade).
- `Settings` (`app/core/config.py`) não tem diretório de uploads.

## Global Constraints

Ver `00-LEIA-PRIMEIRO.md`. Este plano altera: `app/core/config.py`, `app/api/main.py`, `app/data/registry.py`, `scripts/bootstrap.py`, `docker-compose.yml`, `Dockerfile.api` (se necessário), testes.

---

### Task 1: Diretório de uploads persistente + salvamento real

- [ ] `app/core/config.py`: adicionar `uploads_dir: str = "data_uploads"` ao `Settings`.
- [ ] `.gitignore`: adicionar `data_uploads/` (uploads são dados de runtime, não fonte).
- [ ] Teste primeiro (`tests/test_api.py`, ampliar): POST /documentos com um `.md` pequeno →
  o arquivo passa a existir em `<uploads_dir>/` com nome único e o registry guarda esse
  caminho REAL (não o filename original). Usar `tmp_path` + monkeypatch de settings/estado
  para não sujar o repositório.
- [ ] Implementar em `app/api/main.py::documentos`:
```python
import re, unicodedata, uuid
from pathlib import Path

_SAFE = re.compile(r"[^a-z0-9._-]+")

def _safe_filename(family: str, original: str) -> str:
    stem = Path(original or "doc").stem
    stem = unicodedata.normalize("NFKD", stem.casefold())
    stem = _SAFE.sub("-", stem)[:60].strip("-") or "doc"
    suffix = Path(original or "").suffix.lower() or ".pdf"
    return f"{family}--{stem}--{uuid.uuid4().hex[:8]}{suffix}"
```
  Fluxo novo: validar extensão (`{".pdf", ".md", ".txt"}`) e tamanho (`len(content) <= 10 * 1024 * 1024`,
  senão 422 "arquivo excede 10 MB") ANTES de gravar; gravar em
  `Path(get_settings().uploads_dir)` (criar com `mkdir(parents=True, exist_ok=True)`);
  `ingest_pdf(str(dest), family, state.index)`; **se a ingestão falhar, apagar o arquivo**
  (não deixar lixo órfão); `state.registry.register(family, title, str(dest))`. O tempfile
  desaparece do fluxo — grava direto no destino.

### Task 2: Deduplicação no registry

- [ ] Teste primeiro (`tests/test_registry.py`, ampliar): `register("ventoinha", "Proc X", p1)`
  seguido de `register("ventoinha", "Proc X", p2)` → segundo levanta `ValueError`
  ("já existe documento com este título para esta família"); `register` com título
  DIFERENTE para a mesma família continua permitido (famílias podem ter vários docs).
- [ ] Implementar em `DocumentRegistry.register`: `select(Document).where(family==, title==)`
  antes do `add`; se existir, `raise ValueError(...)`.
- [ ] `app/api/main.py`: capturar esse `ValueError` → HTTPException **409**
  ("documento já cadastrado para esta família com este título").

### Task 3: Reindexação completa no bootstrap

- [ ] Teste primeiro (`tests/test_bootstrap.py`, ampliar): dado um registry (sqlite in-memory)
  com um documento extra registrado apontando para um `.md` real em `tmp_path`, a nova
  função `ingest_registry_documents(registry, index, seed_paths)` ingere esse arquivo e
  retorna a contagem; documentos do seed (paths do `PDF_MAP`) são pulados (já ingeridos);
  documento cujo arquivo NÃO existe no disco é pulado com aviso em log (nunca derruba o
  bootstrap) e reportado no retorno.
- [ ] Implementar em `scripts/bootstrap.py`:
```python
def ingest_registry_documents(registry, index, seed_paths: set[str]) -> tuple[int, list[str]]:
    """Reindexa uploads registrados; retorna (docs ingeridos, caminhos ausentes)."""
    ingested, missing = 0, []
    for doc in registry.list_documents():
        if doc.source_path in seed_paths:
            continue
        if not Path(doc.source_path).exists():
            missing.append(doc.source_path)
            continue
        ingest_pdf(doc.source_path, doc.family, index)
        ingested += 1
    return ingested, missing
```
  Chamar em `build_state` logo após o loop do `PDF_MAP`, com
  `seed_paths = {path for path, _ in PDF_MAP} | {"Doc1.pdf"}` (o seed antigo do registry
  para rolamentos usa `docs_fontes/doc1_rolamentos.md`, já coberto). Logar `missing` com
  `logger.warning`.

### Task 4: Volume no Docker e teste de reinício

- [ ] `docker-compose.yml`, serviço `api`: adicionar `UPLOADS_DIR: /srv/data_uploads` no
  environment (conferir que `Settings` lê `UPLOADS_DIR` — pydantic-settings mapeia
  `uploads_dir` automaticamente) e o volume nomeado:
```yaml
    volumes: [uploads:/srv/data_uploads]
```
  e `uploads:` na lista `volumes:` do arquivo. Sem isso, `docker compose down` continuaria
  perdendo os arquivos e o fix resolveria só metade do problema.
- [ ] **Teste de reinício** (o teste-chave do plano, em `tests/test_bootstrap.py` ou novo
  `tests/test_document_persistence.py`): com sqlite em ARQUIVO (`tmp_path/"reg.db"`) e
  uploads em `tmp_path/"uploads"`: (1º ciclo) registrar+ingerir um `.md` de ventoinha via
  fluxo do endpoint (ou funções equivalentes); destruir índice e estado; (2º ciclo)
  reconstruir registry com o MESMO banco + índice novo + `ingest_registry_documents` →
  busca por família `ventoinha` retorna o chunk. Isso simula restart sem Docker.
- [ ] `python -m pytest -q` completo.
- [ ] **Commits sugeridos** (atômicos): `feat: uploads persistidos em disco com validação e dedup`,
  `feat: bootstrap reindexa documentos cadastrados após reinício`,
  `chore: volume de uploads no docker compose`.

## Self-review do plano (feito)

- O ponto de maior risco é o teste de reinício depender de detalhes do `VectorIndex` em
  memória — por isso ele usa as funções de bootstrap reais, não mocks do índice.
- A política de dedup escolhida (family+title únicos, 409) é a mais simples defensável em
  entrevista; versionamento de documentos ficou explicitamente fora do escopo.
