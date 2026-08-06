import logging
import re
import unicodedata
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from sqlalchemy.exc import IntegrityError

from app.api.schemas import (
    AmostraOut,
    ChatIn,
    ChatOut,
    DiagnosticoOut,
    DocumentoOut,
    DocumentoRegistradoOut,
    EventIn,
    FamiliaOut,
    HistoricoDiaOut,
    HistoricoFamiliaOut,
    HistoricoResumoOut,
    JanelaHistorico,
)
from app.api.state import AppState
from app.core.config import get_settings
from app.data.labels import FAULT_FAMILIES, STATE_FAMILIES, display_label
from app.data.loader import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

# Familias validas para o parametro ?familia= de GET /eventos/amostra. Sem a
# checagem de pertinencia, qualquer string que passe a allowlist _FAMILY_RE
# viraria um filtro aceito com resultado vazio (404 confuso) em vez de um 422
# dizendo que a familia nao existe.
_KNOWN_FAMILIES = FAULT_FAMILIES | STATE_FAMILIES

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

    @app.post("/eventos", response_model=DiagnosticoOut)
    def eventos(body: EventIn, state: AppState = Depends(get_state)) -> DiagnosticoOut:
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
                try:
                    session.flush()  # gera event.id sem commitar
                    session.add(Diagnosis(event_id=event.id, status=report.status,
                                          family=report.family, renderer=report.renderer,
                                          message=report.message,
                                          freq_per_day=report.freq_per_day))
                    session.commit()  # unico commit: tudo ou nada
                except Exception as exc:
                    session.rollback()
                    raise HTTPException(500, "falha ao registrar o diagnóstico") from exc
        return DiagnosticoOut.de_relatorio(report)

    @app.post("/chat", response_model=ChatOut)
    def chat(body: ChatIn, state: AppState = Depends(get_state)) -> ChatOut:
        if body.modo not in (None, "offline", "online"):
            raise HTTPException(422, "modo invalido: use 'offline' ou 'online'")
        report = state.pipeline.answer_question(body.pergunta, mode=body.modo)
        return ChatOut.de_relatorio(report)

    @app.get("/familias", response_model=list[FamiliaOut])
    def familias(state: AppState = Depends(get_state)) -> list[FamiliaOut]:
        """Vocabulario do dominio: slug, rotulo em portugues, tipo e cobertura.

        Uma leitura do registry para todas as familias (em vez de um
        has_document por familia) — 17 familias sao 17 queries desnecessarias
        para responder a mesma pergunta.
        """
        documentadas = {doc.family for doc in state.registry.list_documents()}

        def _itens(nomes: set[str], tipo: str) -> list[FamiliaOut]:
            return sorted(
                (
                    FamiliaOut(familia=nome, rotulo=display_label(nome), tipo=tipo,
                               documentado=nome in documentadas)
                    for nome in nomes
                ),
                key=lambda item: item.rotulo,
            )

        # Falhas antes dos estados: e a ordem em que o dashboard as apresenta,
        # e estados de operacao nunca tem documento orientativo (nao ha acao
        # corretiva para "normal").
        return _itens(FAULT_FAMILIES, "falha") + _itens(STATE_FAMILIES, "estado")

    @app.get("/documentos", response_model=list[DocumentoOut])
    def listar_documentos(state: AppState = Depends(get_state)) -> list[DocumentoOut]:
        return [
            DocumentoOut(familia=doc.family, rotulo=display_label(doc.family),
                         titulo=doc.title, cadastrado_em=doc.created_at)
            for doc in sorted(state.registry.list_documents(),
                              key=lambda doc: (doc.family, doc.title))
        ]

    @app.get("/historico/resumo", response_model=HistoricoResumoOut)
    def historico_resumo(state: AppState = Depends(get_state)) -> HistoricoResumoOut:
        """Agregados do MESMO DataFrame que alimenta o kNN.

        Antes, o dashboard lia banner.xlsx do proprio disco e reaplicava
        normalize_label — duas fontes de verdade para o mesmo dado, com o risco
        de o grafico divergir do que o motor de similaridade realmente usa.

        Os dois groupby correm sobre as ~167 mil linhas ja em memoria a cada
        requisicao (~30 ms). Nao ha cache no servidor de proposito: o dashboard
        cacheia a resposta por 5 minutos e um cache aqui so acrescentaria uma
        invalidacao para manter correta.
        """
        df = state.df
        if df is None or df.empty:
            raise HTTPException(503, "histórico indisponível")

        por_familia = (
            df.groupby(["family", "kind"]).size()
            .reset_index(name="ocorrencias")
            .sort_values("ocorrencias", ascending=False)
        )
        dias = df["created_at"].dt.strftime("%Y-%m-%d")
        por_dia = (
            df.assign(dia=dias).groupby(["dia", "family"]).size()
            .reset_index(name="ocorrencias")
            .sort_values(["dia", "family"])
        )
        return HistoricoResumoOut(
            total_leituras=int(len(df)),
            janela=JanelaHistorico(
                primeira=df["created_at"].min().strftime("%Y-%m-%d"),
                ultima=df["created_at"].max().strftime("%Y-%m-%d"),
            ),
            por_familia=[
                HistoricoFamiliaOut(familia=row.family, tipo=row.kind,
                                    ocorrencias=int(row.ocorrencias))
                for row in por_familia.itertuples()
            ],
            por_dia=[
                HistoricoDiaOut(dia=row.dia, familia=row.family,
                                ocorrencias=int(row.ocorrencias))
                for row in por_dia.itertuples()
            ],
        )

    @app.get("/eventos/amostra", response_model=AmostraOut)
    def eventos_amostra(familia: str,
                        state: AppState = Depends(get_state)) -> AmostraOut:
        """Sorteia uma leitura real da familia e devolve o payload de /eventos.

        Substitui a leitura local de banner.xlsx pelo dashboard: a linha vem do
        mesmo historico que o kNN indexou, nao de um arquivo que pode ter
        divergido do banco.
        """
        familia = familia.strip().casefold()
        if not _FAMILY_RE.match(familia) or familia not in _KNOWN_FAMILIES:
            raise HTTPException(422, "família desconhecida")
        if state.df is None or state.df.empty:
            raise HTTPException(503, "histórico indisponível")

        sub = state.df[state.df["family"] == familia]
        if sub.empty:
            raise HTTPException(404, "nenhuma leitura histórica para esta família")
        row = sub.sample(1).iloc[0]

        # Mesmo contrato de scripts/simulator.py::build_payload: EventIn exige
        # float em todas as 23 features, e ~38% das linhas do banner.xlsx tem
        # artefato de datetime em coluna numerica (virou NULL no seed). Enviar
        # None resultaria em 422; 0.0 com a coluna NOMEADA na resposta permite
        # ao dashboard dizer o que foi substituido.
        features: dict[str, float] = {}
        substituidas: list[str] = []
        for coluna in FEATURE_COLUMNS:
            valor = pd.to_numeric(row[coluna], errors="coerce")
            if pd.isna(valor):
                substituidas.append(coluna)
                features[coluna] = 0.0
            else:
                features[coluna] = float(valor)

        id_externo = row["id"] if "id" in sub.columns else None
        return AmostraOut(
            id_externo=int(id_externo) if pd.notna(id_externo) else None,
            rotulo_original=str(row["fault"]),
            familia=familia,
            features=features,
            features_substituidas=substituidas,
        )

    @app.post("/documentos", response_model=DocumentoRegistradoOut)
    async def documentos(file: UploadFile, familia: str = Form(...),
                         titulo: str = Form(...),
                         state: AppState = Depends(get_state)
                         ) -> DocumentoRegistradoOut:
        from app.rag.ingest import ingest_pdf

        # Nomes internos em ingles a partir daqui: e o vocabulario do registry,
        # do modelo Document e do filtro do RAG. O contrato HTTP fala portugues,
        # o nucleo continua com os identificadores que persiste.
        family = familia.strip().casefold()
        title = titulo
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
        except IntegrityError as exc:
            # Race verdadeira: dois requests concorrentes passaram pelo
            # pre-check de dedup (has_document) antes de qualquer um
            # commitar. A UniqueConstraint do banco (family, title) pega o
            # que o pre-check em memória não pegou — mesmo 409 dos outros
            # caminhos de dedup.
            dest.unlink(missing_ok=True)
            raise HTTPException(409, "documento já cadastrado para esta família com este título") from exc
        except Exception:
            # Arquivo e removido, mas os chunks ja ingeridos permanecem no
            # VectorIndex em memoria ate o proximo restart (nao ha remocao
            # de chunks); o estado se autocorrige no reboot, que reindexa
            # so os documentos efetivamente registrados (ver scripts/bootstrap.py).
            dest.unlink(missing_ok=True)
            raise

        return DocumentoRegistradoOut(trechos_indexados=n)

    return app


app = create_app()
