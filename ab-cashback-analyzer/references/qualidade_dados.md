# Catálogo de qualidade de dados

Princípio: o arquivo é sempre tratado como potencialmente sujo. **Nunca imputamos
valores.** Toda linha que não passa numa checagem é **descartada** (defeito que
invalida a linha) ou posta em **quarentena** (linha suspeita, isolada da análise mas
preservada para auditoria). O motivo e a contagem vão para o relatório de qualidade,
porque quem decide precisa saber em que fração dos dados a decisão se apoia.

## Detecção e leitura do arquivo

- **Encoding variável**: tenta `utf-8-sig`, `utf-8`, `latin-1` em ordem.
- **Separador variável**: detecta `;` vs `,` por amostragem do cabeçalho.
- **Cabeçalhos com acento/caixa/espaços**: normalizados e mapeados para nomes
  canônicos via lista de sinônimos (ex.: "Grupos de usuários", "grupo", "variante").
- **Coluna essencial ausente**: erro fatal — não dá para analisar com honestidade;
  a skill informa quais colunas faltaram.

## Tabela de tratamento

| Defeito | Ação | Motivo |
|---|---|---|
| Data ausente ou formato inválido (ex.: `31/02/2011`) | descarte | sem data não há série temporal |
| Campo numérico essencial vazio (`compradores`, `comissão`, `cashback`, `GMV`) | descarte | não se inventa valor |
| Moeda em formato BR (`R$ 1.234,56`, `R$ 769`, `5850`) | convertida | ponto = milhar, vírgula = decimal |
| Valor negativo em compradores/comissão/cashback/GMV | quarentena | impossível fisicamente (lucro pode ser negativo; estes não) |
| `cashback > GMV` ou `comissão > GMV` | quarentena | inconsistência lógica |
| `compradores > 0` mas `GMV = 0` | quarentena | inconsistência lógica |
| Rótulo de variante com typo (`Gurpo 2`, `grupo1`, `GRUPO 3`) | normalizado → `Grupo N` | erro de digitação recuperável |
| Rótulo de variante irreconhecível (não vira `Grupo N`) | quarentena | não se assume a qual grupo pertence |
| Linha totalmente duplicada | descarte | dupla contagem |
| Chave repetida (mesma Data+Variante+Parceiro) com valores divergentes | quarentena | não se escolhe sozinho qual é a verdadeira |
| Linhas fora de ordem cronológica | reordenadas | não é defeito; normalização |

## Alertas (não descartam linhas, mas informam a decisão)

- **Variantes com número de dias diferente** — comparação de totais fica enviesada;
  a análise prioriza métricas normalizadas (por dia / por comprador).
- **Variantes com janelas de datas diferentes** — verificar se o teste foi simultâneo.
- **Grupo fantasma** — variante com volume de dias irrisório (< 30% da maior
  variante). Costuma ser grupo de teste residual ou erro de rotulagem em massa. É
  mantida, mas sinalizada, e **não deve ser escalada**.
- **Múltiplos parceiros no mesmo arquivo** — informado para conferência.

## Saída do relatório de qualidade

Cada análise reporta: linhas lidas, linhas válidas, taxa de aproveitamento (%),
encoding e separador detectados, lista de descartes com contagem, lista de
quarentena com contagem, e alertas. Esses números aparecem no rodapé do dashboard e
do PDF, e um resumo entra na planilha consolidada.
