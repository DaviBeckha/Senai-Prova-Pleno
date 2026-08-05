# Plano 06 — Sincronização de documentação + CI GitHub Actions

**Goal:** Fazer a documentação bater 100% com o código FINAL (pós-planos 01-05) e adicionar integração contínua. Executar por último entre os planos 1-6.

**Problemas conhecidos hoje (verificados 2026-08-05):**
- `docs/arquitetura.md:121` referencia `tests/rag/test_family_sections.py`, que não existe (o Plano 01 cria `tests/test_rag_family_sections.py` — nome diferente, plano).
- Árvore do projeto no README (seção 8) não mostra `app/chat/`, `app/llm/grounding.py`, `app/llm/contracts.py`, `app/data/dataset_store.py`, `app/rag/search.py`, `migrations` da tabela `sensor_readings`, nem a pasta `demo/` (Plano 03) e `data_uploads/` (Plano 02).
- Exemplos de `/chat` no README (seção 7) mostram o shape antigo (3 campos) — o Plano 04 adiciona 5.
- Semântica vizinhos × total histórico (Plano 05) não explicada.
- Persistência de uploads (Plano 02) não documentada.
- Não há CI.
- **Decisão pendente do Davi**: documentar a suíte de testes no README (os testes agora são versionados e visíveis à banca; a regra antiga de não mencioná-los ficou obsoleta). Default deste plano: DOCUMENTAR (seção curta "Como rodar os testes"); se o Davi vetar, pular a Task 3.

## Global Constraints

Ver `00-LEIA-PRIMEIRO.md`. Regra 4 continua absoluta: nada de menção a IA/assistentes/processo. Todos os números citados em docs devem ser MEDIDOS no código real, nunca estimados.

---

### Task 1: Sincronizar `docs/arquitetura.md`

- [ ] Corrigir a referência da linha ~121 para os arquivos de teste reais criados no Plano 01.
- [ ] Incorporar as mudanças do Plano 03 no roteiro de demo (comando CPU/GPU, healthchecks, payloads de `demo/`, passo de reinício pós-cadastro, quadro "se falhar, faça").
- [ ] Revisar as tabelas de critérios de avaliação: adicionar linha para CI/testes (critério "Qualidade da implementação") e para persistência de documentos (RF5 completo).

### Task 2: Sincronizar README

- [ ] Árvore da seção 8 refletindo o estado final real (gerar com `Get-ChildItem`/`ls` e
  conferir manualmente, sem inventar).
- [ ] Exemplos da seção 7: atualizar `/chat` com o contrato completo (status, families,
  renderer, limitations, validation_errors) — um exemplo `answered` e um `undocumented`,
  com JSON REAL capturado de uma execução local via TestClient (não redigido de cabeça).
- [ ] `/eventos`: incluir `neighbor_count` nos exemplos e um parágrafo curto com a
  semântica canônica definida no Plano 05 Task 3.
- [ ] Nova subseção em "Como rodar": persistência de documentos enviados (diretório
  `data_uploads/`, volume `uploads` no compose, comportamento pós-reinício, política de
  duplicidade 409).
- [ ] Seção 5 (guardrail): um parágrafo sobre a validação de fundamentação
  (`app/llm/grounding.py`): as 4 conferências (evidência existe, família bate, citação
  literal, números/suporte lexical) e o significado de `validation_errors` na resposta.
  É o maior diferencial técnico do projeto e hoje o README mal o menciona.

### Task 3 (condicionada ao OK do Davi): Documentar a suíte de testes

- [ ] Subseção "Como rodar os testes" no README: `pip install -r requirements-dev.txt` +
  `python -m pytest -q`, contagem atual da suíte (medir na hora), tempo aproximado, e
  1 parágrafo sobre a estratégia (unidade + contrato da API com fakes de LLM; testes
  adversariais do validador de fundamentação; nenhum teste depende de rede/GPU).
- [ ] Badge do CI no topo do README (após Task 4 existir).

### Task 4: GitHub Actions

- [ ] Criar `.github/workflows/ci.yml`:
```yaml
name: CI
on:
  push: {branches: [main]}
  pull_request:
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12", cache: pip}
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: python -m pytest -q
```
- [ ] Atenção a dois riscos, com solução preparada:
  1. **Peso do install** (torch/sentence-transformers ~2 GB): se o job passar de ~10min,
     criar `requirements-ci.txt` SEM `sentence-transformers`/`torch`/`faiss-cpu` (os
     testes não os importam: embedding é lazy, o índice tem fallback numpy) e usar no CI.
     Validar localmente antes: `python -m pytest -q` num venv com só o subset.
  2. **Testes que leem `banner.xlsx`**: o arquivo está no repo (~esse é o motivo de ele
     estar versionado), então o CI funciona — mas conferir o tempo total.
- [ ] O workflow só é validável de verdade após um push — combinar com o Davi o momento
  (push é sempre autorizado por ele, nunca automático).
- [ ] **Commits sugeridos**: `docs: sincroniza arquitetura, exemplos e semântica das estatísticas`,
  `chore: integração contínua com github actions`,
  (condicional) `docs: instruções de execução da suíte de testes`.

## Self-review do plano (feito)

- Ordem interna importa: Tasks 1-2 dependem do estado final dos planos 01-05 — não executar
  este plano antes deles.
- Todos os exemplos de JSON devem ser capturados de execução real (TestClient) — regra que
  já pegou erro antes (exemplos redigidos à mão tendem a divergir do shape real).
