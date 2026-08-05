# Plano 07 — Integridade transacional Event/Diagnosis + foreign key

**Goal:** A persistência em `POST /eventos` (`app/api/main.py`, bloco `if state.session_factory:`) usa **dois commits**: um para `Event`, outro para `Diagnosis`. Se o segundo falhar (queda do banco, violação de constraint), sobra um evento órfão sem diagnóstico. Além disso, `Diagnosis.event_id` é `Integer` puro — sem foreign key, o banco aceita diagnóstico apontando para evento inexistente.

**Estado atual (verificado 2026-08-05):**
```python
with state.session_factory() as session:
    event = Event(...)
    session.add(event)
    session.commit()          # commit 1
    session.add(Diagnosis(event_id=event.id, ...))
    session.commit()          # commit 2
```
`app/data/models.py`: `Diagnosis.event_id: Mapped[int] = mapped_column(Integer)` (sem FK). Migrations existentes: `0001_initial` (+ a de `sensor_readings`).

## Global Constraints

Ver `00-LEIA-PRIMEIRO.md`. Executar por ÚLTIMO (mexe em migration; nada depende dele).

---

### Task 1: Transação única

- [ ] Teste primeiro (`tests/test_api.py`, ampliar o teste de persistência existente com um
  caso de rollback): usar um FakePipeline normal e um monkeypatch que faz o INSERT de
  `Diagnosis` falhar (ex.: monkeypatch em `Session.flush`/evento SQLAlchemy, ou mais
  simples: monkeypatch de `app.data.models.Diagnosis.__init__` para levantar RuntimeError
  após o Event ser adicionado). Asserção: a chamada `/eventos` responde 500 (ou o
  comportamento decidido abaixo) E `select(Event)` devolve **zero** linhas — nada de órfão.
  Decisão de comportamento: falha de persistência → HTTP 500 com mensagem genérica
  ("falha ao registrar o diagnóstico") — o diagnóstico em si já foi calculado, mas
  responder 200 sem persistir mentiria sobre o estado do sistema; 500 é honesto e raro.
- [ ] Implementar transação única com `flush()` no lugar do primeiro commit:
```python
with state.session_factory() as session:
    event = Event(external_id=None, payload=features, family=report.family,
                  kind=("estado" if report.status == "estado" else "falha"))
    session.add(event)
    session.flush()            # gera event.id sem commitar
    session.add(Diagnosis(event_id=event.id, status=report.status,
                          family=report.family, renderer=report.renderer,
                          message=report.message,
                          freq_per_day=report.freq_per_day))
    session.commit()           # único commit: tudo ou nada
```
  (O context manager do `sessionmaker` faz rollback automático se algo levantar antes do
  commit — confirmar que `make_session_factory` não usa autocommit; hoje não usa.)
- [ ] **Commit** (`fix: persistência de evento e diagnóstico em transação única`).

### Task 2: Foreign key + migration

- [ ] `app/data/models.py`:
```python
from sqlalchemy import ForeignKey
# em Diagnosis:
event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
```
- [ ] Nova migration `migrations/versions/0003_diagnoses_event_fk.py` (numerar conforme a
  última existente — conferir `alembic history`): `upgrade()` cria a FK e o índice
  (`op.create_foreign_key("fk_diagnoses_event_id", "diagnoses", "events", ["event_id"], ["id"])`
  + `op.create_index`), `downgrade()` remove. Postgres aceita direto; para o SQLite dos
  testes usar `op.batch_alter_table` (padrão batch do Alembic) — OU limitar a migration a
  runtime Postgres e criar as tabelas de teste via `Base.metadata.create_all` (que já
  aplica a FK do model). Escolher batch_alter para manter migration única e universal.
- [ ] Teste: aplicar `alembic upgrade head` num SQLite de arquivo temporário
  (`DATABASE_URL=sqlite+pysqlite:///...`) e conferir via `sqlalchemy.inspect` que a FK
  existe; inserir `Diagnosis` com `event_id` inexistente num banco com
  `PRAGMA foreign_keys=ON` → falha. (No Postgres a FK vale sempre; o teste local usa o
  pragma para simular.)
- [ ] Validar também o caminho real: `docker compose up` com banco já populado deve aplicar
  a migration nova sem erro no CMD (`alembic upgrade head` roda na subida do container).
- [ ] `python -m pytest -q` completo.
- [ ] **Commit** (`feat: foreign key entre diagnósticos e eventos com migration`).

## Self-review do plano (feito)

- `flush()` + commit único é o padrão SQLAlchemy correto para id gerado; sem mudança de
  comportamento no caminho feliz.
- Risco real está na migration com SQLite (batch mode) — por isso o teste aplica o
  `upgrade` de verdade em vez de confiar no autogenerate.
- Dados legados: se já houver `diagnoses` órfãos no volume do Postgres da máquina do Davi
  (improvável, mas possível por causa do bug), a criação da FK falharia — a migration deve
  antes deletar órfãos: `op.execute("DELETE FROM diagnoses WHERE event_id NOT IN (SELECT id FROM events)")`.
