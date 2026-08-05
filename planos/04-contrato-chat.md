# Plano 04 — Contrato completo da resposta de /chat

**Goal:** O pipeline do chat já produz um relatório rico (`ChatReport` em `app/chat/types.py`: `status`, `families`, `renderer`, `limitations`, `validation_errors`), mas a API descarta quase tudo: `ChatOut` (`app/api/schemas.py:32`) expõe só `resposta/fontes/degraded`. Sem esses campos, nem o Swagger nem o dashboard conseguem diferenciar "resposta fundamentada" de "falta documento", "evidência insuficiente", "modelo fora do ar" ou "texto do modelo rejeitado pelo validador" — distinções que são o coração do projeto e rendem na entrevista.

**Estado atual (verificado 2026-08-05):**
- `ChatReport(status, message, families=(), sources=(), renderer=None, degraded=False, limitations=(), validation_errors=())`.
- Statuses produzidos por `app/chat/responses.py` + caminho LLM: `documented`, `undocumented`, `partially_documented`, `needs_clarification`, `out_of_scope`, `state`, `answered` (confirmar no código se o caminho LLM usa outro rótulo, ex. `grounded`).
- `app/api/main.py::chat`: `return ChatOut(resposta=report.message, fontes=report.sources, degraded=report.degraded)`.
- Dashboard: exibe só `resposta` e `fontes` (`dashboard/app.py` aba chat).

## Global Constraints

Ver `00-LEIA-PRIMEIRO.md`. Mudança ADITIVA: os campos atuais (`resposta`, `fontes`, `degraded`) não mudam de nome nem de tipo — nada de quebrar consumidores existentes.

---

### Task 1: Schema e endpoint

- [ ] Teste primeiro (`tests/test_api.py`, ampliar o fake de chat): o FakePipeline devolve um
  `ChatReport` completo (com families, renderer, limitations, validation_errors preenchidos)
  e o teste asserta que o JSON da resposta contém TODOS os campos novos com os valores
  esperados:
```python
def test_chat_expoe_contrato_completo():
    report = ChatReport(
        status="answered",
        message="- Ajustar tensão [Doc4.pdf — seção 9.1; evidência correia:E1]",
        families=("correia",),
        sources=("Doc4.pdf",),
        renderer="ollama",
        degraded=False,
        limitations=("a evidência não cobre torque exato",),
        validation_errors=(),
    )
    # FakePipeline.answer_question retorna esse report; assert em cada campo do JSON
```
- [ ] `app/api/schemas.py`:
```python
class ChatOut(BaseModel):
    status: str
    resposta: str
    families: list[str]
    fontes: list[str]
    renderer: str | None
    degraded: bool
    limitations: list[str]
    validation_errors: list[str]
```
- [ ] `app/api/main.py::chat`:
```python
return ChatOut(
    status=report.status,
    resposta=report.message,
    families=list(report.families),
    fontes=list(report.sources),
    renderer=report.renderer,
    degraded=report.degraded,
    limitations=list(report.limitations),
    validation_errors=list(report.validation_errors),
)
```
- [ ] Conferir se algum teste existente asserta o shape antigo de `/chat` e atualizar.
- [ ] **Commit** (`feat: contrato completo da resposta do chat na api`).

### Task 2: Dashboard consome os campos novos

- [ ] `dashboard/app.py`, aba do chat, após exibir a resposta:
  - badge do status (`st.caption(f"status: {resp['status']} · redator: {resp.get('renderer') or 'determinístico'}")`);
  - se `degraded` → `st.warning("Resposta em modo degradado (modelo indisponível ou rejeitado pela validação).")`;
  - se `validation_errors` → `st.caption("Motivos da rejeição: " + "; ".join(...))` — é a
    prova visual do anti-alucinação funcionando;
  - se `limitations` → exibir como lista discreta.
- [ ] Validação manual: `streamlit run dashboard/app.py` com a API de pé (ou conferência de
  sintaxe `python -c "import ast; ast.parse(open('dashboard/app.py', encoding='utf-8').read())"` se a stack não estiver disponível).
- [ ] **Commit** (`feat: dashboard exibe status, limitações e validação do chat`).

### Task 3: Exemplos do Swagger

- [ ] Adicionar `model_config = ConfigDict(json_schema_extra={"examples": [...]})` ao
  `ChatOut` com DOIS exemplos: um `answered` fundamentado e um `undocumented` de contenção
  — na demo, abrir o Swagger já mostra a diferença sem precisar provocar os dois casos ao
  vivo. (Os exemplos do README ficam para o Plano 06.)
- [ ] `python -m pytest -q` completo.
- [ ] **Commit** (junto com a Task 1 se preferir um único commit da feature).

## Self-review do plano (feito)

- Verificar durante a execução qual status o caminho LLM real usa (`answered` vs outro) e
  usar esse valor nos exemplos — não inventar rótulo novo.
- Mudança é aditiva: `resposta`/`fontes`/`degraded` intactos; nenhum consumidor quebra.
