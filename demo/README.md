# Dados de demonstração

Este diretório reúne payloads e um documento de exemplo prontos para uma demonstração
determinística do pipeline, sem depender de sorteio aleatório de linhas do dataset. Os três
eventos abaixo foram extraídos de linhas reais de `banner.xlsx` e conferidos contra o pipeline
real (motor de similaridade treinado no dataset completo, registro de documentos com o seed
padrão e o roteador de laudos) — cada um produz sempre o mesmo resultado, travado por
`tests/test_demo_assets.py`.

## Mapa dos arquivos

| Arquivo | Linha de origem (`id` do dataset) | `fault` original | Família normalizada | Resultado esperado em `POST /eventos` |
|---|---|---|---|---|
| `evento_correia.json` | `id=102543` | `correia` | `correia` (tem documento — `Doc4.pdf`) | `status: "diagnostico"` |
| `evento_ventoinha.json` | `id=122940` | `ventoinha_2` | `ventoinha` (sem documento cadastrado) | `status: "sem_documento"` |
| `evento_normal.json` | `id=1782` | `normal` | `normal` (estado, não é falha) | `status: "estado"` |

Os três payloads têm exatamente os 23 campos numéricos exigidos por `EventIn` — nenhum campo
extra (nem comentário, nem metadado) foi incluído nos JSONs, para manter cada payload idêntico
ao schema documentado, sem misturar metadado de proveniência com dado de sensor (a proveniência
de cada linha está na tabela acima). Os valores vêm sem qualquer "limpeza": alguns campos das linhas reais chegam
com a mesma sujeira de tipo (inteiro em vez de decimal) documentada na seção "Desafios reais
dos dados" do README principal — o pipeline lida com isso normalmente.

`procedimento_ventoinha_demo.md` é um documento orientativo curto (sintomas, diagnóstico e
correção de falha em ventoinha) usado no passo em que se cadastra um documento novo ao vivo e
a família `ventoinha`, antes sem documento, passa a responder com diagnóstico completo.

## Roteiro sugerido

Pré-requisito: API no ar em `http://localhost:8000` (`docker compose up` ou `uvicorn
app.api.main:app --reload`, conforme a seção 6 do README principal).

### Passo 0 — conferir que a API está pronta

```bash
curl http://localhost:8000/health
```

```powershell
Invoke-RestMethod -Method Get -Uri http://localhost:8000/health
```

### Passo 1 — falha documentada (`correia`)

```bash
curl -X POST http://localhost:8000/eventos \
  -H "Content-Type: application/json" \
  --data-binary @demo/evento_correia.json
```

```powershell
$body = Get-Content -Raw demo/evento_correia.json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/eventos `
  -ContentType "application/json" -Body $body
```

Resultado esperado: `status: "diagnostico"`, `family: "correia"`, `sources: ["Doc4.pdf"]`.

### Passo 2 — falha sem documento (`ventoinha`)

```bash
curl -X POST http://localhost:8000/eventos \
  -H "Content-Type: application/json" \
  --data-binary @demo/evento_ventoinha.json
```

```powershell
$body = Get-Content -Raw demo/evento_ventoinha.json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/eventos `
  -ContentType "application/json" -Body $body
```

Resultado esperado: `status: "sem_documento"`, `family: "ventoinha"`, mensagem convidando a
cadastrar um documento novo — nenhuma fonte, nenhum laudo gerado.

### Passo 3 — estado de operação (`normal`)

```bash
curl -X POST http://localhost:8000/eventos \
  -H "Content-Type: application/json" \
  --data-binary @demo/evento_normal.json
```

```powershell
$body = Get-Content -Raw demo/evento_normal.json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/eventos `
  -ContentType "application/json" -Body $body
```

Resultado esperado: `status: "estado"`, `family: "normal"` — não é tratado como falha.

### Passo 4 — cadastrar o documento de ventoinha ao vivo

```bash
curl -X POST http://localhost:8000/documentos \
  -F "file=@demo/procedimento_ventoinha_demo.md" \
  -F "family=ventoinha" \
  -F "title=Procedimento Ventoinha Demo"
```

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/documentos -Form @{
  file   = Get-Item "demo/procedimento_ventoinha_demo.md"
  family = "ventoinha"
  title  = "Procedimento Ventoinha Demo"
}
```

`-Form` exige PowerShell 6.1+ (não funciona no Windows PowerShell 5.1 padrão) — alternativa com
o `curl.exe` nativo do Windows (o binário em `System32`, não o alias do PowerShell para
`Invoke-WebRequest`):

```powershell
curl.exe -X POST http://localhost:8000/documentos `
  -F "file=@demo/procedimento_ventoinha_demo.md" `
  -F "family=ventoinha" `
  -F "title=Procedimento Ventoinha Demo"
```

Resultado esperado: `{"chunks": 3}` — o documento tem três seções (sintomas, diagnóstico,
correção).

### Passo 5 — repetir o Passo 2 e mostrar a mudança de resultado

```bash
curl -X POST http://localhost:8000/eventos \
  -H "Content-Type: application/json" \
  --data-binary @demo/evento_ventoinha.json
```

```powershell
$body = Get-Content -Raw demo/evento_ventoinha.json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/eventos `
  -ContentType "application/json" -Body $body
```

Resultado esperado agora: `status: "diagnostico"`, `family: "ventoinha"`, com `sources`
apontando para o arquivo cadastrado no Passo 4 (o nome final em disco leva um sufixo
aleatório, gerado pelo upload) — sem reiniciar a API, só com o cadastro do Passo 4.
