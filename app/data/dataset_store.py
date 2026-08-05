import time
from pathlib import Path

import pandas as pd
from sqlalchemy import func, insert, select

from app.data.loader import FEATURE_COLUMNS, load_dataset
from app.data.models import SensorReading

# Lotes de insert dentro de UMA transacao: eficiencia de executemany sem abrir
# mao do tudo-ou-nada (seed interrompido nao deixa carga parcial).
_CHUNK = 5_000


def seed_if_empty(session_factory, xlsx_path: str) -> int:
    """Popula sensor_readings a partir do xlsx se (e somente se) estiver vazia.

    Retorna o numero de linhas inseridas; 0 significa que a tabela ja estava
    populada e o xlsx nem foi lido (e o caminho rapido de todo boot apos o
    primeiro).
    """
    with session_factory() as session:
        total = session.scalar(select(func.count()).select_from(SensorReading))
    if total:
        return 0
    if not Path(xlsx_path).exists():
        raise FileNotFoundError(
            f"tabela sensor_readings vazia e arquivo de seed '{xlsx_path}' "
            "inexistente — forneca o dataset para o primeiro boot"
        )
    df = load_dataset(xlsx_path)
    payload = df[["id", "created_at", "fault", "family", "kind", *FEATURE_COLUMNS]]
    payload = payload.rename(columns={"id": "external_id"})
    # Coage SOMENTE as colunas de feature: o banner.xlsx real tem artefatos
    # de datetime nelas (~38% das linhas, sujeira documentada no README §4b)
    # que quebram o insert no Postgres tipado (DatatypeMismatch). Mesma
    # estrategia do SimilarityEngine.fit/query — artefato vira NULL.
    for name in FEATURE_COLUMNS:
        payload[name] = pd.to_numeric(payload[name], errors="coerce")
    # astype(object) antes do where: sem ele o pandas recoloca NaN em colunas
    # float e o banco receberia NaN em vez de NULL.
    payload = payload.astype(object).where(pd.notna(payload), None)
    records = payload.to_dict("records")
    with session_factory() as session, session.begin():
        for start in range(0, len(records), _CHUNK):
            session.execute(insert(SensorReading), records[start:start + _CHUNK])
    return len(records)


def load_from_db(session_factory) -> pd.DataFrame:
    """Le sensor_readings inteira com o MESMO contrato do load_dataset.

    external_id volta como coluna `id` (o id original do xlsx); a PK interna
    fica fora do DataFrame. created_at e coagido para UTC porque o SQLite dos
    testes devolve datetimes naive — no Postgres (timestamptz) a coercao e um
    no-op.
    """
    # sem ORDER BY a ordem física do heap não é garantida e o desempate do kNN é sensível à ordem do corpus
    stmt = select(
        SensorReading.external_id.label("id"),
        SensorReading.created_at,
        SensorReading.fault,
        SensorReading.family,
        SensorReading.kind,
        *[getattr(SensorReading, name) for name in FEATURE_COLUMNS],
    ).order_by(SensorReading.id)
    with session_factory() as session:
        rows = [dict(row) for row in session.execute(stmt).mappings()]
    if not rows:
        raise RuntimeError(
            "tabela sensor_readings vazia — execute o seed (ensure_dataset) "
            "com um xlsx valido antes de carregar o dataset"
        )
    df = pd.DataFrame(rows)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    for name in FEATURE_COLUMNS:
        df[name] = pd.to_numeric(df[name], errors="coerce")
    return df


def ensure_dataset(session_factory, xlsx_path: str) -> pd.DataFrame:
    """Seed (se preciso) + leitura do banco; e o unico ponto de entrada do
    bootstrap para o dataset."""
    started = time.perf_counter()
    inserted = seed_if_empty(session_factory, xlsx_path)
    if inserted:
        print(f"seed do dataset: {inserted} linhas inseridas de {xlsx_path} "
              f"em {time.perf_counter() - started:.1f}s")
    started = time.perf_counter()
    df = load_from_db(session_factory)
    print(f"dataset carregado do banco: {len(df)} linhas "
          f"em {time.perf_counter() - started:.1f}s")
    return df
