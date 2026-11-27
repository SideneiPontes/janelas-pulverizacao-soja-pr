# RESUMO PAINEL — notas de especialistas no multicritério

Gerado por `src/painel_especialistas.py`. C1 (ganho de horas, corrigido pelas estações), pesos AHP e os 4 cenários de pesos não mudaram; só as notas C2–C5. Escala 1–9: C2 custo e C3 risco (9 = muito alto, quanto menor melhor); C4 facilidade e C5 conformidade (9 = melhor). Respostas anonimizadas (sem data/hora e sem nomes).

## Respondentes

| Respondente | Formação | Anos de experiência com aplicação | Onde atua | Painel principal |
|---|---|---|---|---|
| E1 | Agronomia | 15 | Universidade/pesquisa | sim |
| E2 | Engenheiro eletricista | 0 | Governo do estado  | não |
| E3 | Agronomo | 8 | Cooperativa | sim |
| E4 | Engenheiro agrônomo | 7 | Cooperativa | sim |

Critério de inclusão: ≥ 1 ano de experiência com aplicação de defensivos. Sem notas faltantes.

## Notas: autores × mediana do painel principal (n = 3)

| Alternativa | C2 custo | C3 risco | C4 facilidade | C5 conformidade |
|---|---|---|---|---|
| A1 Pulverização noturna | 2 → 5 (1–7) | 6 → 2 (1–6) | 6 → 6 (4–6) | 4 → 6 (5–7) |
| A2 Pontas de indução de ar (antideriva) | 2 → 6 (2–6) | 2 → 2 (1–3) | 8 → 3 (3–6) | 9 → 6 (2–8) |
| A3 Adjuvante que reduz o tempo mínimo sem chuva | 3 → 4 (2–6) | 3 → 2 (2–3) | 8 → 4 (3–5) | 7 → 5 (2–8) |
| A4 Pulverização com drone | 8 → 8 (8–9) | 5 → 8 (7–9) | 3 → 6 (1–7) | 4 → 7 (1–7) |
| A5 Estação meteorológica + sistema de suporte à decisão | 5 → 9 (7–9) | 1 → 7 (5–9) | 5 → 6 (1–8) | 9 → 6 (4–8) |
| A6 Aumento da capacidade operacional (mais pulverizadores/terceirização) | 9 → 7 (3–8) | 3 → 6 (6–6) | 3 → 6 (1–8) | 7 → 6 (6–8) |

Formato: autores → mediana do painel (mínimo–máximo do painel).

## Concordância (W de Kendall, com correção para empates)

| Critério | Painel principal (n = 3): W (p) | Todos (n = 4): W (p) |
|---|---|---|
| C2 Custo de implantação | 0,787 (0,038) | 0,706 (0,015) |
| C3 Risco ambiental, à saúde e de deriva | 0,876 (0,022) | 0,539 (0,056) |
| C4 Facilidade de adoção e inclusão de pequenos produtores | 0,151 (0,812) | 0,113 (0,812) |
| C5 Conformidade regulatória e segurança do aplicador | 0,034 (0,992) | 0,025 (0,992) |

## Rankings TOPSIS (CC) com as notas do painel e C1 corrigido

| Cenário | Paraná (média) | Oeste (média) |
|---|---|---|
| base_AHP | A1 (0,948) > A2 (0,909) > A5 (0,484) > A3 (0,342) > A6 (0,206) > A4 (0,107) | A1 (0,957) > A2 (0,835) > A5 (0,363) > A3 (0,306) > A6 (0,192) > A4 (0,101) |
| pequeno_produtor | A1 (0,929) > A2 (0,771) > A5 (0,469) > A3 (0,412) > A6 (0,298) > A4 (0,214) | A1 (0,937) > A2 (0,737) > A3 (0,378) > A5 (0,377) > A6 (0,281) > A4 (0,203) |
| ambiental_saude | A1 (0,927) > A2 (0,883) > A3 (0,565) > A5 (0,365) > A6 (0,280) > A4 (0,151) | A1 (0,932) > A2 (0,846) > A3 (0,534) > A5 (0,300) > A6 (0,268) > A4 (0,145) |
| pesos_iguais | A1 (0,914) > A2 (0,781) > A3 (0,471) > A5 (0,436) > A6 (0,305) > A4 (0,220) | A1 (0,921) > A2 (0,752) > A3 (0,439) > A5 (0,358) > A6 (0,289) > A4 (0,210) |

## O 1º lugar muda nos testes de ±50 % no peso de cada critério?

- Paraná (média): não (1º lugar na base: A1).
- Oeste (média): não (1º lugar na base: A1).

## Comparação de versões (cenário base, Paraná)

| Versão | Descrição | Ordem | CC A1 | CC A2 | CC A5 |
|---|---|---|---|---|---|
| a | notas dos autores + C1 corrigido (resultado anterior) | A2 > A1 > A5 > A3 > A6 > A4 | 0,699 | 0,936 | 0,580 |
| b | mediana do painel principal + C1 corrigido (resultado principal) | A1 > A2 > A5 > A3 > A6 > A4 | 0,948 | 0,909 | 0,484 |
| c | média do painel principal + C1 corrigido | A1 > A2 > A5 > A3 > A6 > A4 | 0,938 | 0,930 | 0,484 |
| d | mediana de todos os respondentes + C1 corrigido | A1 > A2 > A5 > A3 > A6 > A4 | 0,965 | 0,880 | 0,488 |
| e | mediana do painel principal + C1 só ERA5 | A1 > A2 > A5 > A3 > A6 > A4 | 0,963 | 0,577 | 0,387 |
| f1 | mediana do painel, com C2 dos autores + C1 corrigido | A1 > A2 > A5 > A3 > A6 > A4 | 0,952 | 0,918 | 0,492 |
| f2 | mediana do painel, com C3 dos autores + C1 corrigido | A2 > A1 > A5 > A3 > A6 > A4 | 0,722 | 0,890 | 0,566 |
| f3 | mediana do painel, com C4 dos autores + C1 corrigido | A2 > A1 > A5 > A3 > A6 > A4 | 0,931 | 0,943 | 0,480 |
| f4 | mediana do painel, com C5 dos autores + C1 corrigido | A2 > A1 > A5 > A3 > A6 > A4 | 0,836 | 0,919 | 0,501 |

## O que mudou de conclusão

- **O 1º lugar muda: A1 (pulverização noturna) passa à frente de A2 (pontas antideriva)** com as notas
  do painel, nos 4 cenários de pesos, no Paraná e no Oeste. A2 fica em 2º em todos. No cenário base do
  Paraná a diferença é pequena (CC 0,948 × 0,909).
- **O novo 1º lugar é estável**: A1 continua 1º em todos os testes de −50 % a +50 % em cada peso, no
  Paraná e no Oeste, e também com a média do painel, com todos os respondentes (incluindo E2) e com o
  C1 só do ERA5 (versões c, d, e).
- **A troca vem de C3, C4 e C5, não do custo.** Voltar só o C2 às notas dos autores mantém A1 em 1º
  (f1); voltar C3, C4 ou C5 (f2, f3, f4) devolve o 1º lugar a A2. O painel dá a A1 risco 2 (autores: 6) e
  a A2 facilidade de adoção 3 e conformidade 6 (autores: 8 e 9).
- **Concordância só nos critérios de custo e risco.** W de Kendall alto e significativo em C2 (0,79;
  p = 0,04) e C3 (0,88; p = 0,02); praticamente nulo em C4 (0,15; p = 0,81) e C5 (0,03; p = 0,99). As
  medianas de C4 e C5, que decidem parte da troca, não refletem consenso.
- **Alerta de interpretação da escala**: A2 recebeu facilidade de adoção 3, 3 e 6 (1 = muito difícil),
  abaixo do drone (6, 7, 1). Vale confirmar com os respondentes se o sentido da escala de C4/C5 (9 = mais
  fácil / mais conforme) foi entendido como no código.
- **O resto da ordem quase não muda**: A5 continua 3º no cenário base (com CC menor, porque o painel
  vê custo e risco altos), A3 4º, A6 5º e A4 (drone) último em todas as versões.
- **Painel pequeno**: 3 especialistas no painel principal (E2 ficou fora por ter 0 ano de
  experiência com aplicação). O resultado deve ser apresentado como indicativo.

