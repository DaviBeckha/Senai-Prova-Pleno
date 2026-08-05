# Plano 05 — Semântica das estatísticas de similaridade (aditivo, sem renomear)

**Goal:** Hoje a resposta de `/eventos` mistura duas grandezas sob um rótulo só: o kNN consulta **50 vizinhos** (`SimilarityEngine.query`, k=50), mas `total_ocorrencias` é o **total histórico da família vencedora** (ex.: 11.999 para correia, via `occurrence_stats`). Chamar milhares de registros de "ocorrências similares" quando 50 participaram da consulta é uma imprecisão que a banca pode explorar ("quantos vizinhos seu kNN consultou?").

**Decisão de escopo (importante):** o enunciado da prova pede "quantidade de eventos similares já registrados" e "frequência de ocorrência" — o total histórico da família É uma leitura legítima do requisito. O problema é só o rótulo ambíguo. Portanto: **NÃO renomear** `total_ocorrencias`/`freq_per_day` (renomear quebraria dashboard, testes e exemplos em cascata a dias da entrega). A correção é ADITIVA: expor `neighbor_count` e deixar a semântica explícita na documentação.

**Estado atual (verificado 2026-08-05):** `DiagnosisReport` (`app/pipeline.py`) tem `total_ocorrencias`, `freq_per_day`, `family_votes` (soma dos votos = k consultado); `SimilarityResult.neighbor_ids` tem os 50 ids; `DiagnosisOut` espelha o report.

## Global Constraints

Ver `00-LEIA-PRIMEIRO.md`. Mudança 100% aditiva na API; proibido renomear campos existentes.

---

### Task 1: `neighbor_count` no report e na API

- [ ] Teste primeiro (`tests/test_pipeline.py`, ampliar): `diagnose()` num pipeline real em
  miniatura → `report.neighbor_count == len(result.neighbor_ids)` (com o df sintético de 20
  linhas do helper existente, `neighbor_count == 20`, pois k=50 é clampado ao tamanho do
  histórico); e `sum(report.family_votes.values()) == report.neighbor_count`.
- [ ] `app/pipeline.py`: adicionar `neighbor_count: int` ao dataclass `DiagnosisReport` e
  preencher em TODOS os retornos de `diagnose` (`len(result.neighbor_ids)`); nos retornos
  de `answer_question` (que não roda kNN), `neighbor_count=0`.
- [ ] `app/api/schemas.py`: `neighbor_count: int` no `DiagnosisOut`.
- [ ] Ajustar testes existentes que constroem `DiagnosisReport` na mão (test_api usa fakes
  com `DiagnosisReport(...)` posicional/nominal — adicionar o campo).
- [ ] **Commit** (`feat: contagem de vizinhos consultados exposta no diagnóstico`).

### Task 2: Dashboard diferencia as grandezas

- [ ] `dashboard/app.py`, resultado do diagnóstico: trocar a linha única de info por texto
  que separa as grandezas, ex.:
  `st.info(f"Família: {r['family']} — voto de {r['neighbor_count']} vizinhos mais próximos (top-3: ...). Histórico da família: {r['total_ocorrencias']} ocorrências ({r['freq_per_day']}/dia).")`
  Reutilizar o caption de `family_votes` existente.
- [ ] Validação de sintaxe do arquivo.
- [ ] **Commit** (`feat: dashboard separa vizinhos consultados de total histórico`).

### Task 3: Semântica na documentação técnica

- [ ] `docs/arquitetura.md` e README serão sincronizados no Plano 06 — este plano só
  garante que o CÓDIGO exponha os números certos. Deixar anotado para o Plano 06: a
  explicação canônica é "o kNN vota entre os 50 vizinhos mais próximos (neighbor_count /
  family_votes); identificada a família, as estatísticas de histórico (total_ocorrencias /
  freq_per_day / distribuição) cobrem TODOS os registros daquela família, que é o que o
  enunciado pede em 'quantidade de eventos similares já registrados'".
- [ ] `python -m pytest -q` completo.

## Self-review do plano (feito)

- `neighbor_count=0` no chat é coerente (chat não roda kNN) e já tem precedente:
  `family_votes={}` no mesmo caminho.
- Conferido que nenhum consumidor depende de `DiagnosisReport.__dict__` com conjunto fixo
  de chaves além de `DiagnosisOut(**report.__dict__)` — que continua funcionando porque o
  schema ganha o campo junto.
