# Ampliação do vocabulário de intervenções físicas

## Contexto

A validação do chatbot no ambiente real encontrou onze formulações de
intervenção que ainda podem atravessar o guardrail quando o equipamento está
ligado: tocar, encostar, manipular, fazer manutenção, puxar, esticar,
tensionar, soltar, calibrar, limpar e medir a tensão. A correção anterior
reconhece famílias verbais de ações como "mexer", mas essas novas famílias não
estão na taxonomia explícita central de manutenção.

## Objetivos

- Reconhecer as onze ações e suas formas verbais naturais, não somente as
  frases exatas exercitadas no teste manual.
- Encerrar consultas de intervenção com equipamento ligado antes de índice,
  RAG ou LLM, preservando a orientação determinística existente.
- Manter o aviso preventivo nas intervenções sem indicação de equipamento
  ligado e continuar o fluxo técnico normal nesses casos.
- Preservar perguntas claramente conceituais ou factuais que não solicitam a
  execução de uma ação.

## Fora de escopo

- Criar um novo status HTTP ou alterar o contrato externo do chat.
- Modificar o texto da orientação determinística de segurança.
- Calibrar recuperação, grounding, geração ou apresentação de fallbacks.
- Introduzir um classificador probabilístico de intenção.

## Desenho

### Taxonomia central

`app/core/maintenance_intent.py` continuará como fonte única para reconhecer
intervenções físicas. O padrão explícito será ampliado com formas delimitadas
das famílias `tocar`, `encostar`, `manipular`, `puxar`, `esticar`, `tensionar`,
`soltar`, `calibrar` e `limpar`.

As expressões genéricas serão restritas pelo objeto ou pelo contexto:

- `fazer manutenção` será reconhecida como uma unidade, sem transformar todo
  uso do verbo "fazer" em intervenção;
- `medir a tensão` e suas formas naturais serão reconhecidas, sem transformar
  qualquer medição ou ocorrência do verbo "medir" em intervenção física.

Perguntas conceituais inequívocas, como "o que significa tensionar uma
correia?", continuarão informativas. Já construções procedurais ou de intenção,
como "posso tensionar", "quero medir a tensão" e comandos coordenados,
continuarão sendo tratadas como ações físicas.

### Guardrail e pipeline

O guardrail continuará consumindo `requests_physical_intervention`, sem manter
uma segunda lista de verbos:

- com equipamento ligado ou em movimento, retorna `answered` com orientação
  determinística e encerra antes de índice, RAG e LLM;
- sem esse marcador, o fluxo normal continua e recebe o aviso preventivo;
- consultas conceituais, factuais, históricas e de estado permanecem no fluxo
  apropriado e não recebem passos físicos indevidos.

### Estratégia escolhida

A taxonomia existente será ampliada de maneira contextual. Cadastrar somente
as onze frases exatas deixaria novas conjugações descobertas. Substituir o
mecanismo por classificação linguística ou probabilística aumentaria o risco e
o escopo sem necessidade para esta correção.

## Testes

Os testes serão escritos antes da implementação e cobrirão:

1. todas as onze famílias com equipamento ligado;
2. conjugações e comandos coordenados representativos;
3. encerramento antes de índice, RAG e LLM;
4. manutenção do aviso em intervenções normais;
5. perguntas conceituais e factuais como controles negativos;
6. restrição contextual de "fazer" e "medir";
7. não regressão dos verbos já reconhecidos, incluindo "mexer".

## Critérios de aceite

- As dezoito formulações adversariais relatadas são interceptadas quando
  representam intervenção com equipamento ligado.
- Nenhuma delas expõe procedimentos executáveis nessas condições.
- Os controles conceituais e factuais definidos nos testes não são
  classificados como pedidos de intervenção.
- Testes focados, suíte completa, lint e verificação do diff ficam verdes.
