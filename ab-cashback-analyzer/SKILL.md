---
name: ab-cashback-analyzer
description: Analisa testes A/B de cashback do Méliuz a partir de um CSV e responde "qual variante escalar para 100% do tráfego?". Use SEMPRE que o usuário pedir para analisar um teste A/B, comparar variantes/grupos de cashback, avaliar resultado de um teste de um parceiro, decidir qual grupo escalar, ou mencionar um arquivo de dados de teste de cashback (colunas Data, Grupos de usuários, Parceiro, compradores, comissão, cashback, vendas totais). Gera dashboard interativo, PDF e registra o teste numa planilha consolidada. Funciona para qualquer parceiro, período ou número de variantes sem alterar código — basta indicar o arquivo. Dispare mesmo quando o usuário não disser a palavra "skill", desde que o pedido seja analisar/decidir sobre um teste de cashback.
---

# Analisador de testes A/B de cashback — Méliuz

## O que esta skill faz

Recebe um CSV de teste A/B de cashback e entrega, sem intervenção manual no código:

1. **Saneamento** dos dados com relatório de qualidade transparente.
2. **Análise** com métricas de negócio e validação estatística.
3. **Decisão acionável**: qual variante escalar, com nível de confiança.
4. **Dashboard HTML interativo** (cores Méliuz) + **PDF** compacto de 1–2 páginas.
5. **Registro** do teste numa planilha Google Sheets consolidada (uma linha por teste).

A mesma solução processa qualquer parceiro, período ou número de variantes **sem editar código** — descobre tudo lendo o arquivo. A palavra "grupo" no CSV = uma variante do teste.

## Pergunta central

> Dado este teste A/B, qual variante de cashback devemos escalar para 100% do tráfego?

A resposta é sempre **lucro (comissão − cashback)** como métrica de decisão, validada estatisticamente, com um estado honesto entre **ESCALAR**, **ESCALAR COM CAUTELA** ou **INCONCLUSIVO**. Detalhes em `references/regras_decisao.md`.

## Formato de entrada esperado

CSV com as colunas (nomes toleram acento/caixa/espaços): `Data` (YYYY-MM-DD), `Grupos de usuários` (a variante), `Parceiro`, `compradores` (int), `comissão`, `cashback`, `vendas totais` (GMV) — os três últimos em `R$`. Não há coluna de usuários **expostos**, só de compradores; por isso taxa de conversão não é calculável (ver premissas em `references/metricas.md`).

## Fluxo de execução

Sempre rode o orquestrador — ele encadeia saneamento → análise → relatórios → registro:

```bash
cd scripts
python run.py --csv <ARQUIVO.csv> --nome "<Nome do teste>" \
              --descricao "<descrição curta>" \
              --out <dir_saida> --master <caminho/registro_mestre.csv>
```

O comando gera, no diretório de saída: `dashboard_*.html`, `relatorio_*.pdf`, `analise_*.json`; e acrescenta uma linha ao `registro_mestre.csv`. Ele imprime um JSON com os caminhos e o resumo da decisão — leia esse JSON e apresente ao usuário a recomendação em linguagem natural, com o veredito, a confiança e (se houver) o trade-off.

Se o usuário só quiser inspecionar o saneamento ou a análise isoladamente:
`python ingest.py <csv>` (relatório de qualidade) ou `python analyze.py <csv>` (análise completa em JSON).

## Passo obrigatório: registrar na planilha Google Sheets

O `run.py` mantém o histórico em `registro_mestre.csv` (fonte de verdade), mas **não** sobe para o Google — a API do Google está fora dos domínios liberados do sandbox e o conector do Drive não edita células de uma planilha existente. Portanto, **o Claude** faz o registro assim, via conector do Google Drive:

- **Primeiro teste / não existe planilha ainda:** crie uma planilha Google a partir do `registro_mestre.csv` usando `Google Drive:create_file` com `contentMimeType: "text/csv"` e `title: "Registro de Testes A/B — Méliuz"` (o Drive converte CSV em Google Sheets nativo). Guarde o `fileId`/link e informe o usuário: **abra a planilha → Compartilhar → "Qualquer pessoa com o link"** (essa etapa é sempre manual — nenhum conector define permissão pública).
- **Testes seguintes:** como o conector não edita células, gere a planilha atualizada a partir do `registro_mestre.csv` completo (que já contém todas as linhas anteriores + a nova). Deixe claro ao usuário que o histórico está preservado no CSV mestre.

Nunca invente o link da planilha. Se a criação falhar, diga isso e ofereça o CSV mestre para o usuário importar manualmente.

### Opção de link fixo + append automático (Apps Script Web App)

Se o usuário quiser manter **sempre a mesma planilha (mesmo link)** e ter as linhas entrando automaticamente, há um Web App do Google Apps Script (código em `assets/apps_script_webhook.gs`) que recebe um POST e acrescenta a linha. Uma vez configurado, rode:

```bash
python run.py --csv <CSV> --nome "..." --out <dir> --master <master.csv> \
              --webhook "<URL_do_/exec>" --secret "<segredo>"
```

Atenção ao ambiente: o domínio do Google é bloqueado dentro do sandbox do Claude (claude.ai), então o POST **falha se a skill roda no chat** — nesse caso o `run.py` imprime, no campo `sheets_sync.rode_este_curl`, o comando `curl` pronto para o usuário rodar de uma máquina com acesso ao Google. Quando a skill roda localmente (ex.: Claude Code na máquina do usuário), o append é direto e automático. Apresente o resultado de `sheets_sync` ao usuário: sucesso, ou o curl de fallback.

## Como apresentar o resultado ao usuário

Seja direto e visual, com pouco texto. Responda primeiro a pergunta central (qual variante escalar), depois mostre a confiança e o trade-off se existir, e por fim aponte os arquivos gerados (dashboard, PDF) e o link da planilha. Use `present_files` para entregar o dashboard e o PDF. Não repita tabelas gigantes na conversa — elas já estão no dashboard.

Quando houver alertas de qualidade relevantes (descartes, quarentena, grupo fantasma, variantes com períodos diferentes), mencione-os brevemente — a transparência sobre em que dados a decisão se apoia é parte da entrega.

A análise também detecta automaticamente **destaques e exceções** (variante sem lucro / repasse de ~100% da comissão, ROI abaixo de 1, resposta monotônica ao cashback, trade-off, efeito de novidade) e monta uma **curva de resposta ao cashback** (nível de cashback × lucro por comprador). Esses achados aparecem no dashboard, na 2ª página do relatório e na coluna "Destaques" da planilha; ao apresentar, chame atenção para a exceção mais relevante do teste (por exemplo, uma variante que zera o lucro).

## Robustez a dados ruins

O saneamento trata: campos vazios, moeda em formato BR (`R$ 1.234,56`), encoding e separador variáveis, linhas duplicadas, dados fora de ordem, datas inválidas, valores negativos, grupos com typo (`Gurpo 2` → `Grupo 2`), grupos fantasma (volume irrisório) e inconsistências lógicas (cashback > GMV). Linhas irrecuperáveis são **descartadas** ou postas em **quarentena**, nunca imputadas, e tudo fica registrado no relatório de qualidade. Catálogo completo em `references/qualidade_dados.md`.

## Arquivos da skill

- `scripts/run.py` — orquestrador (ponto de entrada único).
- `scripts/ingest.py` — leitura e saneamento; produz o relatório de qualidade.
- `scripts/analyze.py` — métricas, estatística (bootstrap) e decisão.
- `scripts/report.py` — dashboard HTML + PDF.
- `scripts/registry.py` — linha do registro e manutenção do CSV mestre.
- `references/metricas.md` — definição de cada métrica e as premissas.
- `references/regras_decisao.md` — a árvore de decisão e o trade-off.
- `references/qualidade_dados.md` — catálogo de defeitos e tratamento.

Leia o arquivo de referência pertinente quando precisar justificar uma métrica, explicar a regra de decisão ou detalhar como um defeito foi tratado.
