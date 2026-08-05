# Plano 03 — Blindagem do ambiente de demonstração

**Goal:** A demo da entrevista não pode depender de sorte. Hoje o `docker compose up` FALHA em máquina sem NVIDIA container toolkit (bloco `deploy:` obrigatório no serviço `ollama`), os timeouts do dashboard (180s) são menores que o timeout do Ollama (300s), não há healthcheck do Ollama nem verificação do modelo, e não existem dados determinísticos preparados para os 3 casos da demo.

**Estado atual (verificado 2026-08-05):** `docker-compose.yml` com 4 serviços, portas em 127.0.0.1, `OLLAMA_TIMEOUT=300`/`OLLAMA_NUM_CTX=8192` no serviço api; dashboard usa `timeout=180` em `/eventos` e `/chat` e `300` no upload (`dashboard/app.py:83,120,139`); GPU obrigatória nas linhas ~31-40.

## Global Constraints

Ver `00-LEIA-PRIMEIRO.md`. Depende do Plano 02 (volume `uploads` já no compose).

---

### Task 1: GPU opcional via arquivo de override

- [ ] `docker-compose.yml`: REMOVER o bloco `deploy:` inteiro do serviço `ollama` (CPU vira o
  default universal que sobe em qualquer máquina).
- [ ] Criar `docker-compose.gpu.yml` (novo, versionado):
```yaml
# Override opcional: roda o Ollama com GPU NVIDIA.
# Uso: docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
# Requer nvidia-container-toolkit configurado no Docker.
services:
  ollama:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```
- [ ] Atualizar o comentário do serviço `ollama` no compose base: modo CPU é o padrão
  oficial; GPU é opt-in via override; terceira opção (Ollama nativo no Windows +
  `OLLAMA_BASE_URL=http://host.docker.internal:11434`) continua documentada.
- [ ] Validar: `docker compose config` e `docker compose -f docker-compose.yml -f docker-compose.gpu.yml config` (se Docker disponível; senão, validar com PyYAML e deixar a execução real para o checkpoint final).

### Task 2: Healthchecks do Ollama e da API

- [ ] Serviço `ollama` no compose:
```yaml
    healthcheck:
      test: ["CMD-SHELL", "ollama list | grep -q 'qwen2.5:7b-instruct' || exit 1"]
      interval: 15s
      retries: 20
      start_period: 60s
```
  Nota: o healthcheck fica "unhealthy" até o `ollama pull` manual do primeiro uso — isso é
  DESEJADO como sinal visível de "faltou puxar o modelo". Não usar `depends_on: condition:
  service_healthy` do api para o ollama (a API deve subir mesmo sem modelo; o Router degrada
  para template). Documentar isso no comentário do compose.
- [ ] Serviço `api`:
```yaml
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request,sys,json; r=json.load(urllib.request.urlopen('http://localhost:8000/health', timeout=5)); sys.exit(0 if r.get('ready') else 1)\""]
      interval: 15s
      retries: 40
      start_period: 120s
```
  (curl não existe na imagem python:3.12-slim — usar o próprio python.) `start_period`
  generoso: o bootstrap baixa o modelo e5 (~1 GB) na primeira subida.
- [ ] `dashboard`: `depends_on: {api: {condition: service_started}}` (manter started, não
  healthy — o dashboard já mostra mensagem amigável enquanto a API prepara).

### Task 3: Alinhar timeouts do dashboard

- [ ] `dashboard/app.py`: trocar os `timeout=180` por `timeout=330` (OLLAMA_TIMEOUT máximo
  de 300s + folga de rede) nas chamadas de `/eventos` e `/chat`; manter 300 no upload.
  Definir constante única `REQUEST_TIMEOUT = float(os.environ.get("DASHBOARD_TIMEOUT", "330"))`
  no topo e usar nas três chamadas.
- [ ] Compose, serviço `dashboard`: `DASHBOARD_TIMEOUT: ${DASHBOARD_TIMEOUT:-330}`.

### Task 4: Dados determinísticos da demo

- [ ] Criar `demo/` (versionado) com:
  - `demo/evento_correia.json`, `demo/evento_ventoinha.json`, `demo/evento_normal.json` —
    3 payloads completos de `/eventos` (23 features) extraídos de linhas REAIS do
    `banner.xlsx` cujo kNN comprovadamente devolve a família esperada. Como gerar: carregar
    o dataset, montar o pipeline real com TemplateRenderer, iterar linhas da família até
    achar uma cujo `diagnose()` retorna `dominant_family` correta, e serializar o payload.
    Registrar no JSON um campo `"_comentario"` com o id da linha e o fault original
    (a API ignora campos extras? NÃO — `EventIn` é estrito; guardar o comentário em um
    arquivo irmão `demo/README.md` em vez de dentro do JSON).
  - `demo/procedimento_ventoinha_demo.md` — documento pequeno (~15 linhas, 2-3 seções
    numeradas no padrão dos docs reais: sintomas/diagnóstico/correção de ventoinha) para o
    passo "cadastrar documento ao vivo e a família passar a responder".
  - `demo/README.md` — mapa dos arquivos (linha de origem, fault original, resultado
    esperado de cada payload) e os comandos `curl`/PowerShell prontos para cada passo.
- [ ] Teste (`tests/test_demo_assets.py`): cada JSON valida contra `EventIn`; o pipeline
  real (df do xlsx + registry seed real + índice fake + TemplateRenderer) responde
  `diagnostico`/`sem_documento`/`estado` respectivamente para os 3 arquivos. Esse teste
  TRAVA a demo: se alguém mexer no kNN e um payload mudar de resultado, a suíte acusa.

### Task 5: Fallback ensaiado e roteiro atualizado

- [ ] Teste explícito de degradação já existe (Router → template). Adicionar teste do
  caminho de PONTA: `/eventos` com modo offline e Ollama fora do ar (base_url inválida em
  um Router real com OllamaRenderer apontando para porta morta + fallback template) →
  HTTP 200, `degraded: true`, `renderer: "template"`. A demo pode continuar mesmo se o
  Ollama morrer no meio da entrevista — este teste prova.
- [ ] `docs/arquitetura.md`: atualizar o roteiro com: comando CPU vs GPU (`-f` override),
  passo de `ollama pull`, o healthcheck como diagnóstico visual (`docker compose ps`),
  os 3 payloads de `demo/`, o passo de reinício pós-cadastro (`docker compose restart api`
  → consulta de ventoinha continua respondendo, prova da persistência do Plano 02), e um
  quadro "se X falhar, faça Y" (Ollama fora → mostrar degraded:true como FEATURE;
  sem internet → modo offline é o padrão; Postgres não sobe → `docker compose logs postgres`).
- [ ] Ensaio real (manual, com Docker): banco zerado (`docker compose down -v` → up) e
  banco populado (up de novo sem -v) — os dois cenários de bootstrap documentados com o
  tempo medido de cada um.
- [ ] **Commits sugeridos**: `feat: modo cpu padrão com override opcional de gpu no compose`,
  `feat: healthchecks de ollama e api e timeouts alinhados`,
  `feat: dados determinísticos e roteiro blindado de demonstração`.

## Self-review do plano (feito)

- O healthcheck do Ollama exige o binário `ollama` no container — verdadeiro na imagem
  oficial `ollama/ollama`. O da API usa python puro por falta de curl no slim. Conferido.
- O teste da Task 4 depende do xlsx (lento ~90s de carga) — aceitável; já há testes assim
  na suíte. Se o tempo total passar de ~4min, marcar com `@pytest.mark.slow` e documentar.
