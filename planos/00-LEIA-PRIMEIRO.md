# Planos de correção pré-entrega — Manutenção Prescritiva SENAI

Data: 2026-08-05 · Entrega: 2026-08-07 · Baseline: **98 testes verdes** (`python -m pytest -q`, ~2min10s)

## Contexto para o executor (leia antes de qualquer plano)

Projeto da prova de seleção SENAI (dev pleno IA/Python): pipeline de manutenção prescritiva
— evento de sensores → kNN sobre histórico (166.796 registros, hoje lidos do PostgreSQL via
`app/data/dataset_store.ensure_dataset` com seed automático do `banner.xlsx`) → guardrail
documental (`app/guardrails/policy.py`) → RAG (FAISS por família + embeddings e5 locais) →
redator LLM (Ollama offline padrão / OpenAI `gpt-5.6-luna` online por request / template
determinístico como fallback) com **validação de fundamentação** (`app/llm/grounding.py`:
o JSON do modelo é conferido afirmação por afirmação contra a evidência recuperada).
O chat (`app/chat/`) é determinístico no roteamento de intenção (`analyzer.py`) e usa o
LLM só para redigir procedimentos com evidência (`ChatReport` em `app/chat/types.py`).

## Regras invioláveis do projeto (valem para TODOS os planos)

1. **TDD**: teste primeiro (vermelho), implementação, teste (verde), depois `python -m pytest -q` completo. Zero regressões sobre os 98 atuais.
2. **Testes SÃO versionados** (regra vigente desde 2026-08-05): arquivos de teste novos entram no commit da feature correspondente; commit só de testes usa prefixo `test:`.
3. **Commits**: atômicos por plano/etapa, mensagens em pt-BR com prefixos `feat:`/`fix:`/`test:`/`docs:`/`chore:`, **NUNCA com trailer de IA** (sem `Co-Authored-By`/`Generated with`). **Push somente quando o Davi pedir.**
4. **Nenhum arquivo versionado pode mencionar** IA/assistentes/agentes/Claude/processo de orquestração ("Task N", "controlador", "plano N" em comentários de código).
5. Código e identificadores em inglês; docs, mensagens de UI e commits em pt-BR.
6. NÃO versionar: `CLAUDE.md`, `docs/superpowers/`, `.superpowers/`, `.env`, `data_local/`, o PDF do enunciado da prova.
7. Escopo fechado: NÃO adicionar autenticação, OCR, streaming, MLOps ou novos modelos.

## Ordem de execução (dependências)

| Plano | Título | Esforço | Depende de |
|---|---|---|---|
| 01 | Testes adversariais dos guardrails de fundamentação | M | — (fazer 1º: destrava exclusão local de tests/) |
| 02 | Persistência e reindexação de documentos enviados | M | — |
| 03 | Blindagem do ambiente de demonstração | S-M | 02 (volume de uploads no compose) |
| 04 | Contrato completo da resposta de /chat | S | — |
| 05 | Semântica das estatísticas (neighbor_count aditivo) | S | — |
| 06 | Sincronização de documentação + CI GitHub Actions | S | 01-05 (documenta o estado final) |
| 07 | Integridade transacional Event/Diagnosis + FK | S-M | — (por último; mexe em migration) |

Planos 01, 02, 04, 05 e 07 são independentes entre si. 03 depende de 02. 06 é o último
antes do ensaio final da demo.

## Verificação final (após todos os planos)

1. `python -m pytest -q` → tudo verde.
2. `docker compose config` válido; subir stack completa e rodar o roteiro de
   `docs/arquitetura.md` de ponta a ponta (incluindo o novo passo de reinício após
   cadastro de documento).
3. `git status` limpo; nenhum arquivo proibido staged.
