# Regra de decisão

## Pergunta

> Qual variante de cashback escalar para 100% do tráfego?

## Métrica de decisão

**Lucro = comissão − cashback.** A variante recomendada é a de maior **lucro por
comprador** (métrica normalizada), validada por estatística — não basta ter a
maior média, a vantagem precisa ser distinguível de ruído.

## Por que estatística, e não só "quem lucrou mais"

"Grupo X lucrou mais" é uma observação, não uma decisão. Diferenças diárias têm
variabilidade natural; escalar uma variante para 100% do tráfego com base numa
vantagem que é ruído queima margem por trimestres. Por isso a skill calcula, sobre
a série diária de lucro por comprador:

- **Intervalo de confiança 95% (bootstrap)** da média de cada variante.
- **IC 95% da diferença** entre a 1ª e a 2ª colocada. Se esse intervalo **não
  cruza zero**, a vantagem é real; se cruza, é indistinguível de ruído.

Bootstrap é usado por não supor normalidade e por ser robusto com poucas
observações. Semente fixa (42) garante reprodutibilidade.

## Estados possíveis do veredito

| Veredito | Quando | Confiança |
|---|---|---|
| **ESCALAR** | A líder em lucro/comprador vence com IC da diferença fora do zero, sem decaimento relevante do efeito. | alta |
| **ESCALAR COM CAUTELA** | Vence com significância, mas há sinal de efeito de novidade (queda > 20% na 2ª metade). Recomenda monitorar após rollout. | média |
| **INCONCLUSIVO** | A diferença para a 2ª colocada cruza zero. Recomenda rodar o teste por mais tempo. | baixa |

Um "inconclusivo" honesto vale mais que um falso positivo. Quando há variante única
válida, não há A/B a decidir e o veredito é ESCALAR (confiança N/A).

## Trade-off explícito: crescimento vs. margem

Quando a variante **mais lucrativa** não é a de **maior GMV**, a skill abre uma
seção de trade-off em vez de esconder o conflito. Ela quantifica quanto de GMV se
abre mão por real de lucro ganho e devolve a escolha ao gestor:

> Escalar a variante mais lucrativa em vez da de maior GMV troca X de GMV por Y de
> lucro extra — abre-se mão de N reais de GMV para cada R$1 de lucro ganho. A
> escolha entre crescimento (GMV) e margem (lucro) é estratégica e cabe ao gestor.

A ferramenta **não** decide entre crescimento e margem — essa é uma decisão de
negócio. Ela expõe o número para que a decisão seja informada. Exemplo real: no
Parceiro A, o Grupo 3 (mais cashback) tem o maior GMV mas o menor lucro; o Grupo 1
(menos cashback) tem o maior lucro. São decisões opostas no mesmo teste.

## Ressalvas de qualidade entram na decisão

Alertas do saneamento (grupo fantasma, variantes com períodos diferentes) são
anexados ao veredito. Uma variante sinalizada como fantasma (volume irrisório)
**não deve ser escalada**, mesmo que apareça bem em alguma métrica pontual.
