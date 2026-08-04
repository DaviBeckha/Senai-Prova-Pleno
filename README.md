# Manutenção Prescritiva — SENAI SC

Projeto desenvolvido para o processo seletivo de Desenvolvedor Full Stack I.A. e Python
(pleno) do SENAI SC. Autor: Davi Beckhauser.

## 1. Visão geral

O desafio proposto pede um pipeline completo de **manutenção prescritiva** para máquinas
rotativas: dado um evento novo de sensores de vibração, o sistema deve (1) localizar
registros históricos com comportamento semelhante — sem depender de um classificador de
falhas pré-treinado —, (2) apresentar estatísticas sobre essas ocorrências (quantidade,
frequência, distribuição no tempo) e (3) gerar instruções de correção fundamentadas na base
documental da empresa (manuais de procedimento).

A restrição mais importante do enunciado, e a que mais influenciou as decisões deste
projeto, é de natureza comportamental, não técnica: **o sistema só pode responder sobre
problemas que possuem documento correspondente**. Se um defeito é identificado mas não há
procedimento documentado para ele, a resposta correta não é "inventar" uma instrução — é
informar que o problema ainda não está documentado e sugerir o registro de um novo
documento. Esse requisito (RF4 no desenho da solução) é tratado aqui como um **guardrail
estrutural**: a decisão de chamar ou não um modelo de linguagem é tomada em código
determinístico, antes de qualquer prompt ser montado, e não depende de o modelo "se
comportar bem".

Em resumo, o fluxo de ponta a ponta é:

1. Um evento de sensores (23 métricas de vibração/temperatura/rpm) chega via API.
2. Um motor de similaridade (kNN sobre 166.796 registros históricos) identifica a família de
   defeito mais próxima e expõe a distribuição de votos entre vizinhos.
3. Um guardrail decide, de forma determinística, se aquela família tem documento
   orientativo. Sem documento, o fluxo para ali — nenhum LLM é chamado.
4. Com documento, um pipeline de RAG (busca vetorial com FAISS sobre embeddings locais)
   recupera os trechos relevantes do procedimento.
5. Um redator (Ollama local, OpenAI, ou um template determinístico como último recurso)
   formata a resposta final: defeito, ocorrências, frequência, instruções e fonte citada.

## 2. Arquitetura e fluxo

```mermaid
flowchart TD
    A["Evento JSON<br/>23 métricas: vibração, temperatura, rpm"] --> B["API FastAPI<br/>POST /eventos"]
    B --> C["Validação Pydantic (EventIn)"]
    C --> D["SimilarityEngine — kNN (k=50)<br/>166.796 registros históricos<br/>StandardScaler + SimpleImputer"]
    D --> E{"Guardrail<br/>decide()"}
    E -->|"estado (normal, baseline, teste...)"| F["Resposta: estado de operação<br/>(nenhuma falha, sem diagnóstico)"]
    E -->|"falha SEM documento<br/>(ventoinha, falta_fase, eccentric_rotor)"| G["Contenção anti-alucinação<br/>sugere registro de novo documento<br/>— LLM NUNCA é chamado"]
    E -->|"falha COM documento"| H["RAG — VectorIndex.search()<br/>índice FAISS por família"]
    H --> I["Embeddings locais<br/>intfloat/multilingual-e5-base (768d)"]
    I --> J{"algum trecho<br/>recuperado?"}
    J -->|"não"| G
    J -->|"sim"| K["Router — redator escolhido por requisição"]
    K -->|"modo=offline (padrão)"| L["Ollama · qwen2.5:7b-instruct<br/>local, ~5-6 GB VRAM"]
    K -->|"modo=online"| M["OpenAI · gpt-5.6-luna<br/>Responses API"]
    L -->|"exceção"| N["Template determinístico<br/>(fallback, sem rede/LLM)"]
    M -->|"exceção"| N
    L --> O
    M --> O
    N --> O["Resposta final: defeito, ocorrências,<br/>frequência, instruções, fontes, family_votes"]
    F --> O
    G --> O
```

Os pontos de decisão em amarelo/losango do diagrama (`Guardrail` e `algum trecho
recuperado?`) são exatamente onde o anti-alucinação acontece: os dois só levam a `G`
(contenção) — nunca chegam a montar um prompt para o LLM. Isso está implementado em
`app/pipeline.py` (`PrescriptivePipeline.diagnose`/`answer_question`) e `app/guardrails/policy.py`
(`decide`) — o roteador de LLM não é sequer invocado nesses ramos: a contenção acontece
antes, por construção.

Contratos entre camadas (independência deliberada):
- `app/similarity` e `app/rag` não conhecem FastAPI nem LLM.
- `app/llm` recebe um contexto já pronto (`DiagnosisContext`: defeito, estatísticas, chunks) e
  devolve texto — não decide se deve ou não ser chamado.
- `app/guardrails` é a única camada que decide se o LLM entra no fluxo.
- `app/pipeline.py` (`PrescriptivePipeline`) orquestra as camadas acima e nunca é
  contornado pela API — `app/api/main.py` só chama `pipeline.diagnose`/`answer_question`.

## 3. Decisões técnicas e justificativas

| Decisão | Escolha | Justificativa |
|---|---|---|
| Linguagem | Python | Restrição obrigatória do enunciado |
| Framework web | FastAPI + Pydantic | Diferencial "APIs" citado na prova; validação de schema nativa; Swagger (`/docs`) gerado automaticamente, útil na demo |
| Similaridade de eventos | kNN (scikit-learn, `k=50`) sobre features escaladas (`StandardScaler` + `SimpleImputer`), sem classificação prévia | O enunciado pede explicitamente que a solução "não dependa da classificação prévia de falhas conhecidas", e sim de busca por padrões similares no histórico — kNN atende isso de forma simples, determinística e auditável |
| Transparência da decisão | Campo `family_votes` exposto em toda resposta de `/eventos` | Ver seção 4(d): a votação k=50 não é unânime: em vez de esconder a incerteza atrás de um único rótulo, a distribuição completa de votos é devolvida ao cliente |
| Banco de dados | PostgreSQL 16 + SQLAlchemy 2.0 + Alembic (migrations versionadas em `migrations/`) | Diferencial "Bancos de Dados"; schema versionado por migration reforça também o critério "Versionamento" |
| RAG | PDFs → chunking por seção numerada → embeddings `intfloat/multilingual-e5-base` (local, 768 dimensões) → índice FAISS por família | Modelo multilíngue (documentos em pt-BR), roda 100% offline, respeita a restrição de hardware |
| LLM — modo offline (padrão) | Ollama + `qwen2.5:7b-instruct` | Quantizado, usa ~5-6 GB de VRAM — cabe folgado nos 16 GB de GPU exigidos pela estação de trabalho da prova; funciona sem internet, coerente com um ambiente de chão de fábrica |
| LLM — modo online (opcional) | OpenAI `gpt-5.6-luna` via Responses API | Redação de melhor qualidade quando há conectividade; custo por resposta desprezível; **selecionável por requisição** (campo `modo`), não fixo por processo |
| Fallback | Template determinístico (`TemplateRenderer`, sem LLM) | O sistema nunca fica sem resposta: cobre indisponibilidade do Ollama local ou falha/ausência de chave da OpenAI. Toda resposta degradada é sinalizada com `degraded: true` |
| Dashboard | Streamlit multipage (3 abas) | Diferencial "Dashboards"; ferramenta explicitamente aceita pelo enunciado da prova; rápido de construir sem sacrificar interatividade |
| Deploy | Docker + docker-compose (`postgres`, `ollama`, `api`, `dashboard`) | Diferencial "Soluções de Deploy"; sobe o ambiente completo com um único comando |
| Integração industrial | Script simulador de eventos (`scripts/simulator.py`) publicando no `/eventos` em intervalo configurável | Diferencial "Integrações em ambiente industrial" com custo de implementação mínimo — simula um gateway industrial publicando leituras de sensor |

### Restrição de hardware e como o modo offline a atende

A prova exige que a inferência final rode em uma estação comercial com **até 32 GB de RAM
e GPU de 16 GB**. O modo offline (padrão do sistema) foi dimensionado para essa margem:

- `qwen2.5:7b-instruct` quantizado consome ~5-6 GB de VRAM — deixa folga considerável nos
  16 GB disponíveis, inclusive para rodar ao lado do modelo de embeddings.
- `intfloat/multilingual-e5-base` é um modelo de embeddings compacto (base, não large);
  roda confortavelmente em CPU ou GPU. Importante não confundir os dois índices em memória
  do sistema: o **kNN (scikit-learn `NearestNeighbors`)** é ajustado sobre os **166.796
  registros históricos** de sensor (`app/similarity/engine.py`); o **FAISS**
  (`app/rag/index.py`) indexa apenas os **337 trechos** extraídos dos 6 documentos de
  procedimento (chunking por seção, uma vez no bootstrap) — duas ordens de grandeza menor,
  logo sem custo relevante de RAM mesmo reconstruído inteiramente em memória a cada subida.
- O motor de similaridade (kNN) roda em CPU: o ajuste (`fit`) sobre as 166.796 linhas leva
  ~1 segundo após o carregamento do dataset, e cada consulta (`query`) responde em
  milissegundos (medições locais: ~5-8 ms por evento, média ~5,4 ms) — não há necessidade de
  aceleração por GPU nessa camada.

## 4. Desafios reais dos dados e como foram tratados

O `banner.xlsx` fornecido não é um dataset limpo — e tratá-lo exigiu decisões deliberadas em
várias camadas do pipeline, não só no loader.

### a) Rótulos com dezenas de variações e erros de digitação

A coluna `fault` tem **151 rótulos brutos distintos** para apenas **17 famílias canônicas**
reais (12 de falha + 5 de estado): variações de sufixo (`cocked_rotor_2`, `rolamento_ball_pos_2`),
prefixos (`new_desalinhado_4`) e erros de digitação genuínos (`cockecocked_adxl_0`,
`ddesbalanceado_adxl_0`, `normla_carga_3_3`, `mortor_desligado_novo`). Uma normalização
ingênua por igualdade de string deixaria boa parte do histórico sem família reconhecida.

A solução (`app/data/labels.py`) usa uma cadeia ordenada de expressões regulares
tolerantes a erro — por exemplo, a família `desbalanceado` precisou de um padrão que cobre
`desbalanceado`, `desbalanceamento`, `desabalanceado`, `ddesbalanceado`, `dedesbalanceado`
e `desbanlanceado` sem nunca casar com `motor_deslegado` (typo de um **estado**, não de uma
falha) — a ordem das regras e a tensão entre "tolerante o bastante" e "específico o bastante"
foi validada com casos adversariais dedicados, além da validação direta contra o dataset
completo: **zero rótulos caem no fallback `desconhecido`**.

### b) Artefatos de datetime em células numéricas do Excel

Uma fração relevante das linhas do `banner.xlsx` (**medido em ~38% em amostra de 5.000
linhas** — 1.932/5.000) tem, em colunas que deveriam ser puramente numéricas, células com
valores `datetime` (artefato de geração/exportação do arquivo). Um `float(valor)` ingênuo
levanta `TypeError` nessas células.

O tratamento é defensivo em duas camadas independentes:
- `SimilarityEngine` (`app/similarity/engine.py`), tanto no `fit` quanto no `query`, converte
  cada coluna com `pd.to_numeric(..., errors="coerce")` antes de imputar (`SimpleImputer`,
  estratégia `mean`) e escalar.
- `scripts/simulator.py` (reaproveitado pelo dashboard) usa a mesma estratégia de coerção
  para montar o payload de `/eventos` a partir de uma linha do xlsx; quando um valor
  realmente não é conversível (fora do intervalo representável por `pandas.Timestamp`),
  substitui por `0.0` e imprime um aviso no console citando a coluna afetada — o sistema
  nunca envia `null` para a API (que rejeitaria com 422).

### c) Doc1.pdf é um documento digitalizado sem camada de texto

Ao contrário de Doc2–Doc6 (PDFs "nativos", com texto extraível e seções numeradas
reconhecíveis), o `Doc1.pdf` é um documento escaneado: a fonte embutida só mapeia o
caractere de espaço e cada página é essencialmente uma imagem de página inteira — não há
texto real para extrair, com ou sem ajuste de regex de chunking.

A decisão adotada foi transcrever o conteúdo do Doc1 manualmente para
`docs_fontes/doc1_rolamentos.md`, com a mesma convenção de seções numeradas usada nos
demais documentos. O pipeline de ingestão (`app/rag/chunking.py::chunk_file`) despacha por
extensão de arquivo — `.pdf` via extração real de texto, `.md`/`.txt` como texto puro — então
a mesma função `ingest_pdf` ingere a transcrição sem nenhum tratamento especial no restante
do código. Essa transcrição é a fonte real de RAG para as quatro famílias de rolamento
(`rolamento_inner`, `rolamento_outer`, `rolamento_ball`, `rolamento_combination`) tanto no
bootstrap da aplicação (`scripts/bootstrap.py::PDF_MAP`) quanto no registro de metadados do
documento (`app/data/registry.py`).

### d) Sobreposição física entre famílias no espaço de features

O achado mais relevante para a honestidade do sistema: quando o voto majoritário do kNN
(`k=50`) é comparado com a família real da própria linha consultada, a concordância fica em
torno de **apenas ~46%** — as famílias de defeito se sobrepõem consideravelmente no espaço
bruto das 23 features de vibração/temperatura/rpm (o que é plausível fisicamente: diferentes
falhas mecânicas produzem assinaturas de vibração parecidas nesse conjunto de métricas).

Em vez de mascarar essa incerteza atrás de um único rótulo `family: str`, o pipeline
(`app/pipeline.py`) expõe a distribuição completa de votos dos vizinhos em todo diagnóstico
retornado, no campo `family_votes: dict[str, int]` — nunca vazio quando há um evento de
sensor associado. O dashboard mostra o top-3 desses votos ao lado da comparação entre
rótulo real e diagnóstico obtido. Essa é uma escolha deliberada de transparência: a decisão
final (`family` dominante) continua sendo usada normalmente pelo guardrail e pelo RAG, mas
o cliente da API pode auditar o quão disputada foi aquela votação em vez de receber uma
falsa certeza.

## 5. Guardrail anti-alucinação

Este é o requisito não-negociável do enunciado (RF4) e o critério de avaliação "alucinação do
modelo" da entrevista. A garantia aqui não é de prompt ("instrua o modelo a não inventar") —
é estrutural: existem dois pontos de bloqueio em código, nenhum dos quais depende do
comportamento do LLM.

1. **Família sem documento cadastrado** (`app/guardrails/policy.py::decide`). Das 12 famílias
   de falha reconhecidas pela normalização de rótulos, 9 têm documento associado
   (`rolamento_inner/outer/ball/combination` → Doc1 transcrito; `desalinhado` → Doc2;
   `desbalanceado` → Doc3; `correia` → Doc4; `polia` → Doc5; `cocked_rotor` → Doc6). Três
   **não têm**: `ventoinha`, `falta_fase` e `eccentric_rotor`. Para essas, a resposta é a
   contenção padrão — "problema identificado, mas ainda não documentado; registre um novo
   documento" — e o `Router`/LLM **nunca é instanciado** nesse ramo (não é uma instrução no
   prompt, é um `return` antes de qualquer chamada de rede).

2. **Família documentada, mas sem trecho recuperável** (`app/pipeline.py`). Mesmo quando a
   família tem documento, se a busca no índice FAISS não devolve nenhum chunk (índice vazio,
   reindexação pendente), o pipeline recusa gerar um "diagnóstico" — cairia em um LLM sem
   nenhum trecho de procedimento para se basear, ou seja, sem fonte. A mesma contenção
   honesta é retornada, e o LLM também não é chamado nesse ramo.

### Decisão documentada: `eccentric_rotor` fica sem documento

O `Doc5.pdf` cobre "Polias — excentricidade, desgaste, folga de chaveta". À primeira vista, o
termo "excentricidade" poderia sugerir um mapeamento para a família `eccentric_rotor`
(rotor excêntrico). A decisão tomada neste projeto foi **não fazer esse mapeamento**: a
excentricidade descrita no Doc5 é um defeito de **polia** (desalinhamento do centro
geométrico da polia em relação ao eixo de rotação), fisicamente distinto de um **rotor
excêntrico** (desbalanceamento de massa do próprio rotor) — que também não deve ser
confundido com `cocked_rotor` (Doc6, rotor inclinado/desalinhado angularmente). Tratar os
dois problemas como equivalentes só porque compartilham uma palavra no texto seria
exatamente o tipo de fundamentação frágil que o guardrail existe para evitar. `eccentric_rotor`
portanto dispara a resposta de contenção como as demais famílias sem documento — e, como
qualquer família nessa situação, um novo documento específico pode ser registrado a
qualquer momento via `POST /documentos` (ou pela aba "Documentos" do dashboard), com
efeito imediato: a próxima consulta àquela família já usa o documento recém-indexado, sem
reiniciar a aplicação.

## 6. Como rodar

### 6.1 Docker Compose (recomendado)

```powershell
# 1. Validar a sintaxe do compose
docker compose config

# 2. Subir tudo: Postgres, Ollama, API (aplica as migrations Alembic no start) e dashboard
docker compose up --build

# 3. Baixar o modelo local dentro do container Ollama (o volume começa vazio)
docker exec -it senai-prova-pleno-ollama-1 ollama pull qwen2.5:7b-instruct
# (o nome exato do container pode variar — conferir com `docker compose ps`)

# 4. Acompanhar o bootstrap da API (dataset, kNN, embeddings e índice FAISS
#    sobem em memória no lifespan da aplicação — pode levar 1-2 min na primeira subida)
curl http://localhost:8000/health

# 5. Abrir o dashboard
# http://localhost:8501
```

**Sem GPU NVIDIA disponível no Docker Desktop**: o serviço `ollama` do compose reserva uma
GPU (bloco `deploy:`) e falha ao subir sem `nvidia-container-toolkit` configurado. Duas
saídas, documentadas como comentário no próprio `docker-compose.yml`:

1. Remover o bloco `deploy:` do serviço `ollama` — roda em CPU dentro do container, mais
   lento, porém funcional.
2. Usar o Ollama nativo do Windows (fora do Docker) e apontar
   `OLLAMA_BASE_URL=http://host.docker.internal:11434` no serviço `api`, sem subir o
   serviço `ollama` do compose (`docker compose up --build api dashboard postgres`).

### 6.2 Execução local (sem Docker)

> Desenvolvido com Python 3.12 (imagem Docker) — localmente testado também em 3.14.

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Copiar .env.example para .env e ajustar DATABASE_URL para um Postgres local
# (ou subir só o serviço postgres do compose: docker compose up postgres -d)
copy .env.example .env

# Aplicar as migrations
alembic upgrade head

# Subir a API (bootstrap roda no lifespan: carrega banner.xlsx, ajusta o kNN,
# carrega o modelo de embeddings e ingere os 6 documentos)
uvicorn app.api.main:app --reload

# Em outro terminal, subir o dashboard
streamlit run dashboard/app.py

# Opcional: simular um gateway industrial publicando eventos na API
python -m scripts.simulator --n 10 --intervalo 3
```

### 6.3 Variáveis de ambiente (`.env.example`)

| Variável | Padrão | Descrição |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://senai:senai@localhost:5432/manutencao` | Conexão com o Postgres |
| `LLM_MODE` | `offline` | Modo padrão do redator (`offline` ou `online`); pode ser sobrescrito por requisição via campo `modo` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Endpoint do Ollama (offline) |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct` | Modelo local |
| `OPENAI_API_KEY` | — | Chave da OpenAI (modo online); sem chave, o modo online degrada silenciosamente para o Ollama local |
| `OPENAI_MODEL` | `gpt-5.6-luna` | Modelo online |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-base` | Modelo de embeddings do RAG |
| `EMBEDDING_DIM` | `768` | Dimensão dos vetores |
| `DATA_FILE` | `banner.xlsx` | Dataset histórico |
| `FAISS_DIR` | `data_local/faiss` | Reservado para uso futuro — o índice atual é reconstruído em memória a cada bootstrap, sem persistência em disco |

### 6.4 Postura de segurança do protótipo

Este protótipo foi desenhado para rodar **localmente** (estação de trabalho do avaliador ou
demonstração), e a configuração reflete isso de forma deliberada:

- Todas as portas do `docker-compose.yml` são publicadas apenas em `127.0.0.1` — nenhum
  serviço (Postgres, Ollama, API, dashboard) fica acessível a partir da rede.
- As credenciais do Postgres são parametrizáveis por variável de ambiente
  (`POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`), com defaults simples adequados apenas
  ao uso local.
- A API **não tem autenticação** — decisão de escopo documentada na seção 9. O ponto mais
  sensível é o `POST /documentos`: como os documentos registrados alimentam diretamente as
  respostas do assistente, em produção esse endpoint sem controle de acesso permitiria que
  um agente mal-intencionado "envenenasse" a base de conhecimento com procedimentos falsos.
  O caminho de produção é autenticação (token/OIDC), aprovação humana de documentos antes
  da indexação e segregação de rede por planta.

## 7. Endpoints (exemplos de request/response)

Todas as rotas estão documentadas interativamente em `/docs` (Swagger, gerado
automaticamente pelo FastAPI).

### `GET /health`

```json
{"status": "ok", "ready": true, "llm_mode": "offline"}
```

### `POST /eventos` — caso 1: falha documentada (diagnóstico completo)

Payload de exemplo (o mesmo evento de exemplo do enunciado da prova, `fault: cocked_rotor_2`
→ família `cocked_rotor`, documentada por `Doc6.pdf`):

```json
{
  "z_rms_velocity_in_s": 0.0597, "z_rms_velocity_mm_s": 1.517,
  "temperature_f": 76.44, "temperature_c": 24.69,
  "x_rms_velocity_in_s": 0.0787, "x_rms_velocity_mm_s": 2.0,
  "z_peak_acceleration_g": 0.484, "x_peak_acceleration_g": 0.631,
  "z_peak_vel_comp_freq_hz": 61.0, "x_peak_vel_comp_freq_hz": 61.0,
  "z_rms_acceleration_g": 0.09, "x_rms_acceleration_g": 0.114,
  "z_kurtosis": 2.392, "x_kurtosis": 2.77,
  "z_crest_factor": 3.747, "x_crest_factor": 4.269,
  "z_peak_velocity_in_s": 0.0844, "z_peak_velocity_mm_s": 2.146,
  "x_peak_velocity_in_s": 0.1113, "x_peak_velocity_mm_s": 2.829,
  "z_high_freq_rms_accel_g": 0.129, "x_high_freq_rms_accel_g": 0.147,
  "rpm": 1000.0,
  "modo": "offline"
}
```

Resposta (ilustrativa — o texto de `message` varia conforme o redator ativo; `total_ocorrencias`
e `freq_per_day` são estatísticas reais computadas sobre o histórico para a família
`cocked_rotor`):

```json
{
  "status": "diagnostico",
  "family": "cocked_rotor",
  "message": "DEFEITO IDENTIFICADO: cocked_rotor\nHISTORICO: 14275 ocorrencias similares (594.79/dia, de 2026-05-18 a 2026-06-11).\nACOES DE CORRECAO (extraidas dos procedimentos):\n- [Doc6.pdf — secao 4. Principais Causas] ...\nFONTE: Doc6.pdf",
  "total_ocorrencias": 14275,
  "freq_per_day": 594.79,
  "sources": ["Doc6.pdf"],
  "renderer": "ollama",
  "degraded": false,
  "family_votes": {"cocked_rotor": 31, "rolamento_outer": 9, "correia": 6, "polia": 4}
}
```

### `POST /eventos` — caso 2: falha sem documento (`ventoinha`)

```json
{
  "z_rms_velocity_in_s": 583.0, "z_rms_velocity_mm_s": 1481.0,
  "temperature_f": 76.06, "temperature_c": 24.48,
  "x_rms_velocity_in_s": 1056.0, "x_rms_velocity_mm_s": 2684.0,
  "z_peak_acceleration_g": 599.0, "x_peak_acceleration_g": 465.0,
  "z_peak_vel_comp_freq_hz": 61.0, "x_peak_vel_comp_freq_hz": 56.1,
  "z_rms_acceleration_g": 71.0, "x_rms_acceleration_g": 119.0,
  "z_kurtosis": 2534.0, "x_kurtosis": 2554.0,
  "z_crest_factor": 4813.0, "x_crest_factor": 3432.0,
  "z_peak_velocity_in_s": 825.0, "z_peak_velocity_mm_s": 2095.0,
  "x_peak_velocity_in_s": 1494.0, "x_peak_velocity_mm_s": 3796.0,
  "z_high_freq_rms_accel_g": 124.0, "x_high_freq_rms_accel_g": 135.0,
  "rpm": 500.0,
  "modo": "offline"
}
```

```json
{
  "status": "sem_documento",
  "family": "ventoinha",
  "message": "Problema identificado como 'ventoinha', porém ainda não existe documento orientativo cadastrado para ele. Registre um novo documento para habilitar as recomendações.",
  "total_ocorrencias": 12299,
  "freq_per_day": 878.5,
  "sources": [],
  "renderer": null,
  "degraded": false,
  "family_votes": {"ventoinha": 22, "rolamento_outer": 10, "polia": 7}
}
```

Nesse caso o LLM não é chamado — `renderer` vem `null` e `sources` vem vazio porque não há
nenhuma fonte a citar.

### `POST /eventos` — caso 3: estado de operação (`normal`)

```json
{
  "z_rms_velocity_in_s": 0.564, "z_rms_velocity_mm_s": 1.433,
  "temperature_f": 73.4, "temperature_c": 23.0,
  "x_rms_velocity_in_s": 0.702, "x_rms_velocity_mm_s": 1.784,
  "z_peak_acceleration_g": 0.362, "x_peak_acceleration_g": 0.346,
  "z_peak_vel_comp_freq_hz": 61.0, "x_peak_vel_comp_freq_hz": 61.0,
  "z_rms_acceleration_g": 0.058, "x_rms_acceleration_g": 0.084,
  "z_kurtosis": 5.323, "x_kurtosis": 4.758,
  "z_crest_factor": 4.855, "x_crest_factor": 4.28,
  "z_peak_velocity_in_s": 0.798, "z_peak_velocity_mm_s": 2.027,
  "x_peak_velocity_in_s": 0.993, "x_peak_velocity_mm_s": 2.524,
  "z_high_freq_rms_accel_g": 0.074, "x_high_freq_rms_accel_g": 0.081,
  "rpm": 500.0,
  "modo": "offline"
}
```

```json
{
  "status": "estado",
  "family": "normal",
  "message": "Evento classificado como estado de operação 'normal' — nenhuma falha identificada.",
  "total_ocorrencias": 15058,
  "freq_per_day": 320.38,
  "sources": [],
  "renderer": null,
  "degraded": false,
  "family_votes": {"normal": 44, "desbalanceado": 3, "motor_desligado": 2, "baseline": 1}
}
```

### `POST /chat`

```json
{"pergunta": "como corrigir correia frouxa?", "modo": "offline"}
```

```json
{
  "resposta": "DEFEITO IDENTIFICADO: correia\n...\nFONTE: Doc4.pdf",
  "fontes": ["Doc4.pdf"],
  "degraded": false
}
```

Perguntas fora do domínio documentado (ex.: nenhuma família reconhecida no texto) recebem a
mesma contenção honesta: `"Não identifiquei na pergunta nenhuma falha com documento
orientativo cadastrado. Especifique o problema (ex.: correia, polia, desbalanceamento) ou
registre um novo documento para o defeito."`

### `POST /documentos` — registrar novo documento (habilita a família imediatamente)

Multipart form: `file` (PDF), `family` (ex. `ventoinha`), `title`.

```
POST /documentos
Content-Type: multipart/form-data

file=@doc_ventoinha.pdf
family=ventoinha
title=Doc7 - Ventoinhas
```

```json
{"chunks": 18}
```

A partir dessa chamada, `state.registry.register("ventoinha", ...)` passa a responder
`True` em `has_document("ventoinha")` e o índice FAISS já contém os novos chunks — a
**próxima** consulta a `/eventos` ou `/chat` sobre `ventoinha` deixa de cair em
`sem_documento` e passa a gerar diagnóstico completo, sem reiniciar a API.

## 8. Estrutura do projeto

```
app/
├── api/
│   ├── main.py          # create_app(): rotas /health, /eventos, /chat, /documentos
│   ├── schemas.py        # EventIn, DiagnosisOut, ChatIn, ChatOut (Pydantic)
│   └── state.py           # AppState: pipeline, registry, index, df — injetado por rota
├── core/
│   └── config.py           # Settings (pydantic-settings) via .env
├── data/
│   ├── labels.py            # normalize_label(): 151 rótulos brutos -> 17 famílias canônicas
│   ├── loader.py              # load_dataset(): lê banner.xlsx, valida colunas, normaliza fault
│   ├── models.py                # SQLAlchemy: Event, Diagnosis, Document
│   ├── db.py                     # make_session_factory()
│   └── registry.py                # DocumentRegistry: seed dos 6 docs + registro de novos
├── similarity/
│   ├── engine.py                   # SimilarityEngine: kNN (k=50) sobre features escaladas
│   └── stats.py                     # occurrence_stats(): contagem, frequência, janela temporal
├── rag/
│   ├── chunking.py                   # chunk_pdf/chunk_file: segmentação por seção numerada
│   ├── embedding.py                   # EmbeddingService (e5-base local, import pesado lazy)
│   ├── index.py                        # VectorIndex: FAISS IndexFlatIP por família
│   └── ingest.py                        # ingest_pdf(): orquestra chunking + indexação
├── llm/
│   ├── base.py                          # DiagnosisContext, prompt do sistema, build_user_prompt
│   ├── router.py                         # Router: redator primário + fallback com degradação
│   ├── template_fallback.py               # TemplateRenderer: fallback determinístico sem LLM
│   ├── ollama_adapter.py                   # OllamaRenderer (modo offline)
│   └── openai_adapter.py                    # OpenAIRenderer (modo online)
├── guardrails/
│   └── policy.py                             # decide(): estado | documentado | nao_documentado
└── pipeline.py                                 # PrescriptivePipeline: orquestra tudo acima

dashboard/
└── app.py            # Streamlit: Histórico (gráficos), Diagnóstico & Chat, Documentos

scripts/
├── bootstrap.py       # build_state(): monta pipeline completo a partir de Settings
└── simulator.py         # CLI: publica eventos reais do xlsx em /eventos (gateway industrial)

migrations/
└── versions/0001_initial.py   # Alembic: schema inicial (events, diagnoses, documents)

docs_fontes/
└── doc1_rolamentos.md   # transcrição do Doc1.pdf (PDF escaneado, sem texto extraível)

docker-compose.yml, Dockerfile.api, Dockerfile.dashboard, .dockerignore
requirements.txt, .env.example, alembic.ini
banner.xlsx, Doc2.pdf..Doc6.pdf   # dataset e base documental
docs/arquitetura.md   # roteiro de demo da entrevista + mapa de critérios de avaliação
```

## 9. Evolução futura

Fora de escopo deliberado para o prazo desta entrega (YAGNI), registrado aqui como caminho
natural de evolução:

- **Autenticação e multiusuário**: hoje a API não tem controle de acesso; um ambiente de
  produção real exigiria autenticação (JWT/OAuth), escopo por planta/linha de produção e,
  em especial, controle de quem pode registrar documentos orientativos — ver a análise de
  risco na seção 6.4.
- **Streaming de resposta**: o redator online (OpenAI) e o local (Ollama) suportam streaming
  nativamente; expor isso via SSE/WebSocket melhoraria a percepção de latência no chat.
- **MLOps e monitoramento de produção**: versionamento de modelo de embeddings,
  observabilidade de latência/erro por redator, alertas de degradação (`degraded: true`)
  agregados — hoje o único sinal é o log da aplicação.
- **OCR automatizado para documentos digitalizados**: a solução atual para o `Doc1.pdf`
  (transcrição manual) não escala para um fluxo real de registro de novos documentos
  escaneados via `POST /documentos`; um pipeline de OCR (ex. Tesseract) resolveria isso de
  forma automática antes do chunking.
- **Features espectrais (FFT/envelope) para melhorar a separação de famílias**: o achado da
  seção 4(d) (~46% de concordância do voto kNN com a família real) sugere que as 23
  features estatísticas atuais (RMS, kurtosis, crest factor, pico) não separam bem todas as
  famílias de defeito no espaço bruto. Extrair features no domínio da frequência
  (FFT, envelope de aceleração, harmônicos de rotação) tende a discriminar melhor defeitos
  mecânicos com assinaturas espectrais características (ex. defeitos de rolamento têm
  frequências de falha bem definidas: BPFO, BPFI, BSF, FTF).
