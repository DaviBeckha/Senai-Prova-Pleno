import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile

from app.api.schemas import ChatIn, ChatOut, DiagnosisOut, EventIn
from app.api.state import AppState
from app.core.config import get_settings
from app.data.loader import FEATURE_COLUMNS

logger = logging.getLogger(__name__)


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
        import os, pathlib, tempfile
        from app.rag.ingest import ingest_pdf
        suffix = pathlib.Path(file.filename or "doc.pdf").suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            path = tmp.name
        try:
            n = ingest_pdf(path, family, state.index)
        except ValueError as exc:
            raise HTTPException(422, "extensão não suportada (use .pdf, .md ou .txt)") from exc
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        state.registry.register(family, title, file.filename or path)
        return {"chunks": n}

    return app


app = create_app()
