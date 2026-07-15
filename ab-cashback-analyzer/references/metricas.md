# Métricas e premissas

Todas as métricas derivam apenas das colunas do CSV. Nada é estimado a partir de
dados externos.

## Premissas (registradas em toda análise)

1. **Sem denominador de exposição.** O CSV traz `compradores` (quem comprou), mas
   não quantos usuários foram **expostos** a cada variante. Logo, **taxa de
   conversão é impossível de calcular** e o teste clássico de proporções A/B fica
   indisponível. Assumimos **alocação de tráfego equilibrada** entre variantes e
   usamos o **dia como unidade amostral**, fazendo inferência sobre médias diárias
   e sobre métricas normalizadas (por comprador), robustas a diferença de volume.
2. **Métrica de decisão = lucro = comissão − cashback.** Definição do negócio.
3. **Sem grupo de controle.** As variantes são comparadas entre si.

## Métricas brutas (direto do CSV, somadas no período por variante)

- `compradores` — usuários únicos que compraram.
- `GMV` (vendas totais) — valor total transacionado.
- `comissão` — quanto o parceiro pagou ao Méliuz.
- `cashback` — quanto foi devolvido aos usuários.

## Métricas derivadas

| Métrica | Fórmula | Por que importa |
|---|---|---|
| **Lucro** | comissão − cashback | Resultado financeiro líquido do Méliuz no teste. É a métrica de decisão. |
| **ROI** | lucro / cashback | Quanto de lucro cada R$1 de cashback investido gerou. Eficiência do incentivo. |
| **Margem** | lucro / GMV | Quanto de cada real transacionado virou lucro. |
| **Ticket médio** | GMV / compradores | Valor médio por comprador. Diagnostica se o cashback atrai compras maiores. |
| **Cashback por comprador** | cashback / compradores | Custo do incentivo por pessoa. |
| **Lucro por comprador** | lucro / compradores | Métrica **normalizada** que sustenta a comparação estatística: não depende do volume de tráfego que cada variante recebeu. |
| **% cashback sobre GMV** | 100 × cashback / GMV | A "alavanca" testada — o nível de cashback praticado. |
| **Take rate** | 100 × comissão / GMV | Quanto o Méliuz cobra do parceiro por real transacionado. |

## Métricas temporais

- **Série diária** de lucro, compradores, GMV e cashback por variante.
- **Lucro acumulado** dia a dia (a distância entre as linhas é a vantagem acumulada).
- **Agregação semanal** para leitura de tendência.
- **Checagem de efeito de novidade**: compara a média de lucro/comprador da 1ª
  metade vs. 2ª metade do período. Queda > 20% é sinalizada, pois uma variante que
  brilha só no início pode não sustentar o ganho após o rollout.

## Por que lucro por comprador é a espinha dorsal da decisão

Sem saber quantos usuários foram expostos, comparar **totais** entre variantes é
enganoso: uma variante pode ter mais lucro absoluto só por ter recebido mais
tráfego. O **lucro por comprador** neutraliza isso — mede a qualidade econômica de
cada compra, independentemente do volume. Por isso a inferência estatística
(intervalos de confiança e comparação entre variantes) é feita sobre a série
diária dessa métrica.
