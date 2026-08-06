# Ampliação do Vocabulário de Intervenções Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Impedir que novas famílias de intervenção física atravessem o guardrail quando o equipamento está ligado, sem bloquear perguntas puramente conceituais ou factuais.

**Architecture:** `app/core/maintenance_intent.py` permanece como taxonomia única. Os padrões explícitos reconhecerão famílias verbais delimitadas e duas expressões contextuais (`fazer manutenção` e `medir a tensão`); `app/guardrails/safety.py` e `app/pipeline.py` continuarão apenas consumindo essa decisão central.

**Tech Stack:** Python 3.12, expressões regulares, pytest parametrizado, Ruff e GitHub Actions.

## Global Constraints

- Manter `status="answered"` para orientação preventiva com equipamento ligado.
- Não alterar o texto determinístico atual de EPI, parada total, LOTO e ausência de energia.
- Não acessar índice, RAG ou LLM depois de reconhecer intervenção com equipamento ligado.
- Não criar classificador probabilístico nem dependência nova.
- Preservar perguntas conceituais e factuais que não solicitam ação física.

---

### Task 1: Cobrir as novas famílias na taxonomia e no pipeline

**Files:**
- Modify: `tests/test_safety.py`
- Modify: `tests/test_chat_adversarial.py`
- Modify: `tests/test_acceptance_regressions.py`
- Modify: `app/core/maintenance_intent.py`

**Interfaces:**
- Consumes: `assess_question_safety(question, actions=None) -> SafetyDecision`, `analyze_question(question) -> QuestionAnalysis` e `PrescriptivePipeline.answer_question(pergunta) -> ChatReport`.
- Produces: `has_explicit_physical_intervention(value) -> bool` e `requests_physical_intervention(value, actions=None) -> bool` reconhecendo as novas famílias com contexto.

- [ ] **Step 1: Escrever testes unitários que reproduzem as onze lacunas**

Adicionar a `tests/test_safety.py` uma matriz literal com as frases observadas:

```python
@pytest.mark.parametrize("question", (
    "Posso tocar na correia com o motor ligado?",
    "Posso encostar na correia com o motor ligado?",
    "Posso manipular a correia com o motor ligado?",
    "Posso fazer manutenção na correia com o motor ligado?",
    "Posso puxar a correia com o motor ligado?",
    "Posso esticar a correia com o motor ligado?",
    "Posso tensionar a correia com o motor ligado?",
    "Posso soltar a correia com o motor ligado?",
    "Posso calibrar a correia com o motor ligado?",
    "Posso limpar a correia com o motor ligado?",
    "Posso medir a tensão da correia com o motor ligado?",
))
def test_novas_intervencoes_com_maquina_ligada_geram_orientacao(question):
    decision = assess_question_safety(question)
    assert decision.outcome is SafetyOutcome.ADVISE_LIVE_INTERVENTION
```

- [ ] **Step 2: Escrever testes de conjugações e controles negativos**

Adicionar casos representativos para `toque`, `encostando`, `manipule`, `faça manutenção`, `puxe`, `esticando`, `tensione`, `solte`, `calibre`, `limpe` e `meça a tensão`. Adicionar controles literais:

```python
@pytest.mark.parametrize("question", (
    "O que significa tensionar uma correia?",
    "O que significa fazer manutenção na correia?",
    "Qual o custo da limpeza da correia?",
    "A medição da tensão está correta?",
))
def test_novos_termos_sem_pedido_fisico_nao_acionam_guardrail(question):
    assert assess_question_safety(question).outcome is SafetyOutcome.ALLOW
```

- [ ] **Step 3: Escrever o teste de aceitação que prova o encerramento antes das dependências**

Ampliar `tests/test_acceptance_regressions.py` com as onze perguntas usando `_RaisingIndex` e `_RaisingRouter`; exigir `status == "answered"`, `sources == ()` e a orientação "Não realize a intervenção". Esse teste falha se o pipeline alcançar busca ou geração.

- [ ] **Step 4: Executar os testes e confirmar RED pelo motivo correto**

Run:

```powershell
python -m pytest tests/test_safety.py tests/test_acceptance_regressions.py -q
```

Expected: as novas linhas falham com `SafetyOutcome.ALLOW` ou alcançam `_RaisingIndex`; os testes antigos permanecem verdes.

- [ ] **Step 5: Implementar as famílias verbais mínimas**

Em `app/core/maintenance_intent.py`, acrescentar fragmentos delimitados para:

```python
_ADDITIONAL_PHYSICAL_FRAGMENT = (
    r"toc(?:ar|ando|ou|o|a|am|amos|aram|ava|avam|e|em)|"
    r"encost(?:ar|ando|ou|o|a|am|amos|aram|ava|avam|e|em)|"
    r"manipul(?:ar|ando|ou|o|a|am|amos|aram|ava|avam|e|em)|"
    r"pux(?:ar|ando|ou|o|a|am|amos|aram|ava|avam|e|em)|"
    r"estic(?:ar|ando|ou|o|a|am|amos|aram|ava|avam)|estiqu(?:e|em)|"
    r"tension(?:ar|ando|ou|o|a|am|amos|aram|ava|avam|e|em)|"
    r"solt(?:ar|ando|ou|o|a|am|amos|aram|ava|avam|e|em)|"
    r"calibr(?:ar|ando|ou|o|a|am|amos|aram|ava|avam|e|em)|"
    r"limp(?:ar|ando|ou|o|a|am|amos|aram|ava|avam|e|em)"
)
```

Adicionar padrões contextuais separados para formas de `fazer + manutenção` e `medir + tensão`, incluindo `faça`/`fazendo` e `meça`/`medindo`. Associar ajuste/tensionamento a `MaintenanceAction.ADJUST`, medição de tensão a `MaintenanceAction.INSPECT` e as demais intervenções genéricas a `MaintenanceAction.REPAIR`.

- [ ] **Step 6: Preservar explicações conceituais inequívocas**

Antes de considerar o infinitivo uma ordem física, reconhecer prefixos conceituais exatos como `o que significa`, `qual a definição`, `defina` e `conceitue`. Não aplicar essa exceção a `explique como`, `passo a passo`, `posso`, `quero`, `devo` ou comandos coordenados.

- [ ] **Step 7: Executar testes focados e confirmar GREEN**

Run:

```powershell
python -m pytest tests/test_safety.py tests/test_chat_adversarial.py tests/test_acceptance_regressions.py tests/test_pipeline.py -q
```

Expected: todos os testes passam e nenhuma dependência proibida é chamada nos casos com máquina ligada.

- [ ] **Step 8: Commitar a implementação e as regressões**

```powershell
git add app/core/maintenance_intent.py tests/test_safety.py tests/test_chat_adversarial.py tests/test_acceptance_regressions.py
git commit -m "fix: ampliar vocabulario de intervencoes fisicas"
```

### Task 2: Verificação completa e preparação da branch

**Files:**
- Verify: all tracked source and test files

**Interfaces:**
- Consumes: árvore completa da branch após Task 1.
- Produces: evidência reproduzível de testes, lint, diff limpo e histórico pronto para revisão.

- [ ] **Step 1: Executar a suíte completa em diretório temporário isolado**

```powershell
$testRoot = Join-Path $env:TEMP ('senai-vocabulario-' + [guid]::NewGuid().ToString('N'))
python -m pytest -q --basetemp $testRoot
```

Expected: zero falhas e zero erros.

- [ ] **Step 2: Executar verificações estáticas e de diff**

```powershell
python -m ruff check .
git diff --check origin/main...HEAD
git status --short --branch
```

Expected: Ruff e diff sem erros; somente a branch e os commits planejados aparecem.

- [ ] **Step 3: Solicitar revisão independente do intervalo**

Revisar `origin/main...HEAD` contra estes requisitos: onze famílias e conjugações, interrupção antes do índice/modelo, controles conceituais/factuais e ausência de mudança no contrato HTTP.

- [ ] **Step 4: Corrigir achados bloqueadores com novo ciclo RED-GREEN**

Para cada achado válido, escrever primeiro o menor teste que reproduz o problema, confirmar a falha, aplicar a correção mínima e executar novamente os testes focados.

- [ ] **Step 5: Publicar a branch após todas as verificações verdes**

```powershell
git push -u origin fix/ampliar-vocabulario-intervencoes
```

Expected: branch remota criada no mesmo SHA local, pronta para PR e CI.
