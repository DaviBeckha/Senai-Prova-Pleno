import logging
import re
import unicodedata
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile

from app.api.schemas import ChatIn, ChatOut, DiagnosisOut, EventIn
from app.api.state import AppState
from app.core.config import get_settings
from app.data.loader import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_SAFE = re.compile(r"[^a-z0-9._-]+")
# Allowlist estrita para o campo family: apenas letras minusculas, digitos e
# "_" (formato das familias reais do dominio — ver app/data/labels.py).
# Bloqueia qualquer caractere usado em travessia de diretorio ("/", "\\",
# "."), inclusive apos normalizacao (strip + casefold) do valor recebido.
_FAMILY_RE = re.compile(r"^[a-z0-9_]{1,40}$")


def _safe_filename(family: str, original: str) -> str:
    stem = Path(original or "doc").stem
    stem = unicodedata.normalize("NFKD", stem.casefold())
    stem = _SAFE.sub("-", stem)[:60].strip("-") or "doc"
    suffix = Path(original or "").suffix.lower() or ".pdf"
    return f"{family}--{stem}--{uuid.uuid4().hex[:8]}{suffix}"


def get_state(request: Request) -> AppState:
    state = getattr(request.app.state, "container", None)
    if state is None:
        raise HTTPException(503, "aplicacao ainda nao inicializada")
    return state


def create_app(skip_bootstrap: bool = False) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not skip_bootstrap:
            # bootstrap real delegado a scripts/bootstrap.build_state
            from scripts.bootstrap import build_state
            try:
                app.state.container = build_state(get_settings())
            except Exception:
                # Falha no bootstrap (dataset ausente, banco fora do ar,
                # etc.): a API sobe mesmo assim, porem "nao pronta" — sem
                # app.state.container, get_state() responde 503 e /health
                # reporta ready=False, em vez de o processo inteiro morrer.
                logger.exception("falha ao inicializar o pipeline no bootstrap")
        yield

    app = FastAPI(title="Manutencao Prescritiva SENAI", version="1.0.0",
                  lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        ready = getattr(app.state, "container", None) is not None
        return {"status": "ok", "ready": ready, "llm_mode": get_settings().llm_mode}

    @app.post("/eventos", response_model=DiagnosisOut)
    def eventos(body: EventIn, state: AppState = Depends(get_state)) -> DiagnosisOut:
        modo = body.modo
        if modo not in (None, "offline", "online"):
            raise HTTPException(422, "modo invalido: use 'offline' ou 'online'")
        features = {c: getattr(body, c) for c in FEATURE_COLUMNS}
        report = state.pipeline.diagnose(features, mode=modo)
        if state.session_factory:
            from app.data.models import Diagnosis, Event
            with state.session_factory() as session:
                event = Event(external_id=None, payload=features, family=report.family,
                              kind=("estado" if report.status == "estado" else "falha"))
                session.add(event)
                session.commit()
                session.add(Diagnosis(event_id=event.id, status=report.status,
                                      family=report.family, renderer=report.renderer,
                                      message=report.message,
                                      freq_per_day=report.freq_per_day))
                session.commit()
        return DiagnosisOut(**report.__dict__)

    @app.post("/chat", response_model=ChatOut)
    def chat(body: ChatIn, state: AppState = Depends(get_state)) -> ChatOut:
        if body.modo not in (None, "offline", "online"):
            raise HTTPException(422, "modo invalido: use 'offline' ou 'online'")
        report = state.pipeline.answer_question(body.pergunta, mode=body.modo)
        return ChatOut(resposta=report.message, fontes=report.sources,
                       degraded=report.degraded)

    @app.post("/documentos")
    async def documentos(file: UploadFile, family: str = Form(...),
                         title: str = Form(...),
                         state: AppState = Depends(get_state)) -> dict:
        from app.rag.ingest import ingest_pdf

        family = family.strip().casefold()
        if not _FAMILY_RE.match(family):
            raise HTTPException(422, "família inválida (use letras minúsculas, números e _)")

        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in _ALLOWED_EXTENSIONS:
            raise HTTPException(422, "extensão não suportada (use .pdf, .md ou .txt)")

        content = await file.read()
        if len(content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(422, "arquivo excede 10 MB")

        # Verificar deduplicação ANTES de gravar/ingerir (evita chunks órfãos no índice)
        if state.registry.has_document(family, title):
            raise HTTPException(409, "documento já cadastrado para esta família com este título")

        uploads_dir = Path(get_settings().uploads_dir)
        uploads_dir.mkdir(parents=True, exist_ok=True)
        dest = uploads_dir / _safe_filename(family, file.filename or "")
        # Defesa em profundidade: mesmo com family ja validada, garante que o
        # destino final nao escapa de uploads_dir antes de gravar qualquer
        # byte em disco. Falha vira 422 (nunca 500/gravacao fora do lugar).
        if not dest.resolve().is_relative_to(uploads_dir.resolve()):
            raise HTTPException(422, "caminho de destino inválido")
        dest.write_bytes(content)

        try:
            n = ingest_pdf(str(dest), family, state.index)
        except UnicodeDecodeError as exc:
            # UnicodeDecodeError herda de ValueError — precisa ser capturado
            # ANTES do except ValueError abaixo, senao um .md/.txt fora de
            # UTF-8 recebe a mensagem (falsa) de extensão não suportada.
            dest.unlink(missing_ok=True)
            raise HTTPException(422, "arquivo não está em UTF-8") from exc
        except ValueError as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(422, "extensão não suportada (use .pdf, .md ou .txt)") from exc
        except Exception:
            dest.unlink(missing_ok=True)
            raise

        if n == 0:
            # Sem chunks utilizaveis (arquivo vazio, so whitespace, ou PDF
            # escaneado sem texto extraivel): registrar a familia aqui
            # deixaria ela marcada como "documentada" com contencao vazia no
            # indice — todo diagnostico cairia em "sem trechos" e a
            # retentativa com o mesmo titulo tomaria 409.
            dest.unlink(missing_ok=True)
            raise HTTPException(422, "documento sem conteúdo utilizável")

        try:
            state.registry.register(family, title, str(dest))
        except ValueError as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(409, "documento já cadastrado para esta família com este título") from exc
        except Exception:
            # Arquivo e removido, mas os chunks ja ingeridos permanecem no
            # VectorIndex em memoria ate o proximo restart (nao ha remocao
            # de chunks); o estado se autocorrige no reboot, que reindexa
            # so os documentos efetivamente registrados (ver scripts/bootstrap.py).
            dest.unlink(missing_ok=True)
            raise

        return {"chunks": n}

    return app


app = create_app()
