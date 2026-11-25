# RESUMO V4 — janelas de pulverização na soja do Paraná

**v3**: ERA5 1995–2024 (safras 1995/96–2023/24, 29 safras); validação INMET 2010–2016 (anos civis completos, 6 estações).  
**v4**: ERA5 safras 2000/01–2025/26 (1º/set/2000 a 30/abr/2026, 26 safras); validação INMET em todo o período disponível nos arquivos locais, só set–abr das estação-safras válidas (≥ 70 % de horas válidas em T, UR e vento). Critérios, limiares, fases, municípios, notas C2–C5, pesos AHP e cenários: iguais.  
Gerado por `src/resumo_v4.py` a partir de `outputs_v3_1995-2024/tables` e `outputs/tables`. Formato "estação × ERA5" = estação primeiro. Viés = ERA5 − estação.


## 1. Dados e estações

| Indicador | v3 (ERA5 1995–2024; INMET 2010–2016) | v4 (2000–2026) |
|---|---|---|
| Período da validação | 2010–2016 | safras 2006/07–2025/26 (set–abr, estação-safras válidas) |
| Nº de estações usadas | 6 | 7 |
| Nº de estações nas médias | 5 (B803 fora) | 7 |
| Estação-safras válidas (set–abr, ≥ 70 %) | – | 98 |
| Estação-safras no período de fungicidas (T12) | 23 | 88 |
| Estações (distância ao município) | A819 Castro (1,3 km de Castro); A835 Maringa (3,0 km de Maringá); A820 Mal. Candido Rondon (4,4 km de Marechal Cândido Rondon); A846 Foz Do Iguacu (12,1 km de Foz do Iguaçu); B803 Campina Da Lagoa (19,0 km de Ubiratã); A842 Nova Fatima (26,1 km de Cornélio Procópio) | A835 Maringa (2,3 km de Maringá); A819 Castro (3,6 km de Castro); A820 Mal. Candido Rondon (4,6 km de Marechal Cândido Rondon); A846 Foz Do Iguacu (12,1 km de Foz do Iguaçu); B803 Campina Da Lagoa (19,2 km de Ubiratã); A816 Novo Horizonte (26,7 km de Pato Branco); A842 Nova Fatima (27,0 km de Cornélio Procópio) |
| Registros horários ERA5 por município | 262.992 (todos os 24 municípios) | 230.832 (todos os 24 municípios) |
| Período bruto ERA5 baixado | 1995-01-01 a 2024-12-31 | 2000-01-01 a 2026-05-01 |
| Valores fora dos limites físicos — ERA5 | dew_point_2m: 1 | dew_point_2m: 3 |
| Valores fora dos limites físicos — INMET bruto | nenhum (valores brutos dentro dos limites físicos) | nenhum (valores brutos dentro dos limites físicos) |
| % de falhas INMET por variável, do 1º ao último registro (média das estações) | T 6,3 %, UR 6,6 %, u10 6,3 %, precip 11,4 % | T 20,8 %, UR 21,0 %, u10 23,9 %, precip 25,7 % |
| % de falhas INMET nas estação-safras válidas (set–abr) | – | T 6,4 %, UR 6,5 %, u10 6,4 %, precip 11,3 % |

## 2. Validação horária (viés / RMSE / r)

| Indicador | v3 (ERA5 1995–2024; INMET 2010–2016) | v4 (2000–2026) |
|---|---|---|
| Temperatura (°C) | +0,18 / 1,72 / 0,954 | +0,03 / 1,69 / 0,941 |
| UR (%) | +1,98 / 9,68 / 0,869 | +1,55 / 9,36 / 0,873 |
| Delta T (°C) | -0,33 / 1,45 / 0,883 | -0,27 / 1,44 / 0,887 |
| Vento a 10 m (km/h) | +0,94 / 6,06 / 0,494 | +0,37 / 5,84 / 0,494 |
| % horas com vento OK, crit. A (estação × ERA5) | 52,2 × 71,6 | 54,9 × 71,1 |
| % horas com chuva OK, crit. A | 90,3 × 80,7 | 89,4 × 78,0 |
| % horas com vento OK, crit. B | 50,1 × 68,1 | 52,7 × 68,3 |
| % horas com chuva OK, crit. B | 92,3 × 84,5 | 91,8 × 83,1 |
| % horas aptas, crit. A | 23,3 × 30,4 | 24,9 × 29,9 |
| % horas aptas, crit. B | 35,1 × 48,4 | 36,6 × 46,3 |
| Kappa A | 0,264 | 0,268 |
| Kappa A (chuva ERA5 < 0,2 = 0) | 0,271 | 0,278 |
| Kappa B | 0,172 | 0,196 |
| Kappa B (chuva ERA5 < 0,2 = 0) | 0,172 | 0,196 |

## 3. Validação agregada (viés h / RMSE / r)

| Indicador | v3 (ERA5 1995–2024; INMET 2010–2016) | v4 (2000–2026) |
|---|---|---|
| Horas aptas mensais, A | +50,6 h / 98,5 / 0,36 (n=370) | +35,5 h / 93,8 / 0,25 (n=696) |
| Horas aptas mensais, B | +97,2 h / 138,6 / 0,39 (n=375) | +70,2 h / 123,3 / 0,34 (n=705) |
| Horas aptas por safra no período de fungicidas, A | +29,5 h / 172,9 / 0,27 (n=23) | +22,1 h / 210,7 / 0,09 (n=88) |
| Horas aptas por safra no período de fungicidas, B | +162,6 h / 235,0 / 0,62 (n=24) | +159,1 h / 281,0 / 0,14 (n=90) |
| Spearman entre estações, ano todo (mensal), A | +0,77 (p=0,07) | +0,32 (p=0,48) |
| Spearman entre estações, ano todo (mensal), B | -0,03 (p=0,96) | +0,29 (p=0,53) |
| Spearman entre estações, fungicidas, A | +0,10 (p=0,87) | -0,18 (p=0,70) |
| Spearman entre estações, fungicidas, B | +0,70 (p=0,19) | +0,43 (p=0,34) |
| Decomposição (estação − ERA5), crit. A, h/mês, média set–abr | vento -51,7, chuva +30,6, UR -14,2, DeltaT -6,9, temperatura -0,1, total -42,2 | vento -46,3, chuva +29,4, UR -11,4, DeltaT -3,8, temperatura -0,5, total -32,6 |
| Razão estação/ERA5 por mês, crit. A | set 0,60, out 0,73, nov 0,79, dez 0,94, jan 0,98, fev 0,94, mar 0,85, abr 0,72 | set 0,63, out 0,77, nov 0,84, dez 0,93, jan 0,99, fev 0,94, mar 0,91, abr 0,83 |

## 4. T13c, T13d e T13e

| Indicador | v3 (ERA5 1995–2024; INMET 2010–2016) | v4 (2000–2026) |
|---|---|---|
| T13c — % aptas por fase, média (estação × ERA5) | Dessecação 19,6 × 31,2 (razão 0,63); Pós-emergência 24,3 × 29,3 (razão 0,83); Fungicidas 23,8 × 24,8 (razão 0,96); Pré-colheita 26,2 × 33,6 (razão 0,78) | Dessecação 21,0 × 30,1 (razão 0,70); Pós-emergência 26,2 × 30,3 (razão 0,86); Fungicidas 26,1 × 27,1 (razão 0,96); Pré-colheita 28,8 × 33,2 (razão 0,87) |
| T13c — Dessecação, por estação | A819 16,9×21,8; A820 14,5×31,0; A835 25,7×34,5; A842 19,8×33,0; A846 21,2×35,8; B803 30,4×37,2 | A816 22,1×25,7; A819 16,7×21,9; A820 14,6×28,5; A835 27,6×34,0; A842 19,9×33,9; A846 21,0×33,2; B803 25,1×33,6 |
| T13c — Pós-emergência, por estação | A819 20,8×17,3; A820 20,7×34,6; A835 35,1×33,9; A842 27,5×27,7; A846 17,5×32,9; B803 30,6×35,9 | A816 29,1×26,6; A819 22,5×18,7; A820 19,7×33,5; A835 34,8×34,9; A842 26,0×28,3; A846 20,7×35,3; B803 30,9×35,1 |
| T13c — Fungicidas, por estação | A819 19,6×16,4; A820 18,1×28,5; A835 32,3×29,7; A842 31,4×21,9; A846 17,5×27,4; B803 19,5×16,1 | A816 30,0×24,6; A819 21,2×16,3; A820 16,5×32,8; A835 36,6×32,0; A842 30,6×23,0; A846 19,6×29,7; B803 28,3×31,6 |
| T13c — Pré-colheita, por estação | A819 18,7×21,7; A820 22,0×40,4; A835 38,1×41,1; A842 32,1×31,9; A846 20,3×33,0; B803 –×– | A816 35,4×27,7; A819 19,6×22,2; A820 21,0×41,4; A835 38,8×40,5; A842 31,7×33,9; A846 21,2×34,1; B803 34,1×32,8 |
| T13d — fungicidas, noite × dia | calmaria noturna (u2<3 km/h) 38,0 % × 12,1 %; aptas à noite 19,0 % × 28,5 %; aptas de dia 27,1 % × 22,3 %; ganho A1 113 × 204 h/safra | calmaria noturna (u2<3 km/h) 30,3 % × 10,3 %; aptas à noite 23,1 % × 30,2 %; aptas de dia 28,2 % × 25,0 %; ganho A1 144 × 216 h/safra |
| T13e — Paraná, % do tempo apto ERA5 bruto → ajustado | Dessecação 28,5 → 18,9 %; Pós-emergência 28,1 → 23,6 %; Fungicidas 24,0 → 23,0 %; Pré-colheita 32,0 → 25,0 % | Dessecação 28,7 → 20,0 %; Pós-emergência 27,9 → 24,2 %; Fungicidas 25,2 → 24,1 %; Pré-colheita 32,6 → 28,3 % |

## 5. ERA5 — período de fungicidas e fases (Paraná, média)

| Indicador | v3 (ERA5 1995–2024; INMET 2010–2016) | v4 (2000–2026) |
|---|---|---|
| Horas aptas por safra (média e DP) | 433 h (DP 99) | 455 h (DP 86) |
| % do tempo apto | 24,0 % | 25,2 % |
| Dias aptos | 44,8 de 75 | 46,7 de 75 |
| % do tempo apto por fase | Dessecação 28,5 %; Pós-emergência 28,1 %; Fungicidas 24,0 %; Pré-colheita 32,0 % | Dessecação 28,7 %; Pós-emergência 27,9 %; Fungicidas 25,2 %; Pré-colheita 32,6 % |
| Piores decêndios (set–abr) | Fev-3 45,1 h, Fev-2 51,8 h, Jan-2 52,7 h | Fev-3 49,8 h, Jan-2 55,4 h, Fev-2 56,2 h |
| Piores decêndios do período de fungicidas | Fev-3 45,1 h, Fev-2 51,8 h, Jan-2 52,7 h | Fev-3 49,8 h, Jan-2 55,4 h, Fev-2 56,2 h |
| Motivos de inaptidão — fungicidas (motivo principal) | DeltaT baixo 59,9 %, chuva 13,0 %, vento forte 11,6 % | DeltaT baixo 58,1 %, chuva 13,1 %, vento forte 12,1 % |
| Motivos de inaptidão — dessecação | DeltaT baixo 50,0 %, vento forte 23,5 %, DeltaT alto 12,7 % | DeltaT baixo 47,9 %, vento forte 23,5 %, DeltaT alto 14,6 % |
| Fração noturna das horas aptas em fungicidas | mín. 24,0 % (Guarapuava); máx. 56,8 % (Santa Helena) | mín. 25,2 % (Guarapuava); máx. 58,2 % (Santa Helena) |
| % apto em fungicidas: município mais e menos favorável | mais favorável São Miguel do Iguaçu 32,3 %; menos favorável Castro 14,8 % | mais favorável Marechal Cândido Rondon 33,6 %; menos favorável Castro 15,5 % |

## 6. Markov, tendências e agrupamento

| Indicador | v3 (ERA5 1995–2024; INMET 2010–2016) | v4 (2000–2026) |
|---|---|---|
| Markov: pares município-decêndio dependentes (qui², 5 %) | 516 de 576 (89,6 %) | 509 de 576 (88,4 %) |
| Markov: pior decêndio | Fev-2: P(apto) 0,56; P(apto|ontem apto) 0,71; P(apto|ontem inapto) 0,38 (média dos municípios) | Fev-2: P(apto) 0,59; P(apto|ontem apto) 0,72; P(apto|ontem inapto) 0,40 (média dos municípios) |
| Sen/Mann-Kendall, Paraná (média) | Dessecação +11,4 h/déc (p=0,42); Pós-emergência +11,6 h/déc (p=0,46); Fungicidas +46,0 h/déc (p=0,02); Pré-colheita +9,1 h/déc (p=0,69) | Dessecação -24,5 h/déc (p=0,10); Pós-emergência +0,1 h/déc (p=1,00); Fungicidas +20,6 h/déc (p=0,34); Pré-colheita -7,1 h/déc (p=0,69) |
| Sen nos municípios, fungicidas | 24 de 24 positivas; 5 significativas | 21 de 24 positivas; 0 significativas |
| k-means | k = 2, silhueta 0,559 | k = 2, silhueta 0,558 |
| Grupo restritivo | 6 municípios: Guarapuava, Ponta Grossa, Castro, Tibagi, Pato Branco, Palmas; 1.073–1.532 h (média 1.249 h set–abr) | 6 municípios: Guarapuava, Ponta Grossa, Castro, Tibagi, Pato Branco, Palmas; 1.107–1.562 h (média 1.278 h set–abr) |
| Grupo favorável | 18 municípios: Cascavel, Toledo, Assis Chateaubriand, Londrina, Cornélio Procópio, Campo Mourão, Ubiratã, Umuarama, Ivaiporã, Maringá, São Pedro do Iguaçu, Marechal Cândido Rondon, Medianeira, São Miguel do Iguaçu, Foz do Iguaçu, Matelândia, Santa Helena, Guaíra; 1.631–2.014 h (média 1.867 h set–abr) | 18 municípios: Cascavel, Toledo, Assis Chateaubriand, Londrina, Cornélio Procópio, Campo Mourão, Ubiratã, Umuarama, Ivaiporã, Maringá, São Pedro do Iguaçu, Marechal Cândido Rondon, Medianeira, São Miguel do Iguaçu, Foz do Iguaçu, Matelândia, Santa Helena, Guaíra; 1.667–2.048 h (média 1.898 h set–abr) |

## 7. Épocas de semeadura (fase de florescimento e enchimento, Paraná)

| Indicador | v3 (ERA5 1995–2024; INMET 2010–2016) | v4 (2000–2026) |
|---|---|---|
| Horas aptas por época | 25/09: 344 h; 15/11: 295 h | 25/09: 342 h; 15/11: 309 h |
| Ganho melhor × pior época por município | mín. 14,2 h (Marechal Cândido Rondon); máx. 76,7 h (Tibagi) | mín. 10,3 h (Marechal Cândido Rondon); máx. 67,7 h (Tibagi) |
| Melhor época pelo P20, por município | 25/09: 15 municípios (Cascavel, Toledo, Assis Chateaubriand, Guarapuava, Ponta Grossa, Castro, Tibagi, Londrina, Ubiratã, Pato Branco, Palmas, Medianeira, São Miguel do Iguaçu, Foz do Iguaçu, Guaíra); 05/10: 5 municípios (Campo Mourão, Umuarama, Ivaiporã, Maringá, São Pedro do Iguaçu); 15/10: 4 municípios (Cornélio Procópio, Marechal Cândido Rondon, Matelândia, Santa Helena) | 25/09: 15 municípios (Cascavel, Toledo, Assis Chateaubriand, Guarapuava, Ponta Grossa, Castro, Tibagi, Campo Mourão, Ubiratã, Palmas, Medianeira, São Miguel do Iguaçu, Foz do Iguaçu, Matelândia, Guaíra); 05/10: 8 municípios (Londrina, Cornélio Procópio, Pato Branco, Umuarama, Ivaiporã, Maringá, São Pedro do Iguaçu, Marechal Cândido Rondon); 15/10: 1 municípios (Santa Helena) |

## 8. T8b — C1 corrigido pelas estações (h/safra)

| Alt. | Estação v3 | ERA5 mesmos pontos v3 | Razão v3 | Estação v4 | ERA5 mesmos pontos v4 | Razão v4 | PR orig.→corr. v3 | PR orig.→corr. v4 | Oeste orig.→corr. v3 | Oeste orig.→corr. v4 |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 noturna | 100,6 | 179,3 | 0,56 | 133,4 | 201,1 | 0,66 | 156,3→87,7 | 168,9→112,1 | 248,1→139,2 | 264,7→175,7 |
| A2 antideriva | 97,1 | 72,0 | 1,35 | 111,5 | 74,8 | 1,49 | 75,3→101,7 | 77,6→115,5 | 93,1→125,6 | 97,0→144,5 |
| A3 adjuvante | 6,8 | 5,0 | 1,36 | 7,3 | 5,1 | 1,44 | 5,5→7,5 | 5,3→7,6 | 4,2→5,7 | 3,9→5,6 |
| A4 drone | -14,0 | -30,9 | 0,45 | -23,9 | -38,9 | 0,61 | -36,7→-16,6 | -37,5→-23,1 | -51,0→-23,1 | -51,8→-31,8 |
| A5 estação+SSD | 46,3 | 41,9 | 1,10 | 48,1 | 43,8 | 1,10 | 43,8→48,4 | 44,6→48,8 | 41,5→45,8 | 41,9→45,9 |
| A6 capacidade | 0,0 | 0,0 | – | 0,0 | 0,0 | – | 0,0→0,0 | 0,0→0,0 | 0,0→0,0 | 0,0→0,0 |

## 9. TOPSIS (CC) com C1 corrigido — 4 cenários de pesos

| Cenário | Região | v3 | v4 |
|---|---|---|---|
| base_AHP | Paraná (média) | A2 (0,936) > A1 (0,673) > A5 (0,602) > A3 (0,319) > A6 (0,242) > A4 (0,068) | A2 (0,936) > A1 (0,699) > A5 (0,580) > A3 (0,331) > A6 (0,257) > A4 (0,068) |
| base_AHP | Oeste (média) | A2 (0,900) > A1 (0,709) > A5 (0,508) > A3 (0,303) > A6 (0,241) > A4 (0,067) | A2 (0,850) > A1 (0,721) > A5 (0,466) > A3 (0,295) > A6 (0,240) > A4 (0,064) |
| pequeno_produtor | Paraná (média) | A2 (0,942) > A1 (0,702) > A5 (0,578) > A3 (0,479) > A6 (0,201) > A4 (0,087) | A2 (0,942) > A1 (0,721) > A5 (0,562) > A3 (0,488) > A6 (0,211) > A4 (0,087) |
| pequeno_produtor | Oeste (média) | A2 (0,915) > A1 (0,728) > A5 (0,511) > A3 (0,466) > A6 (0,201) > A4 (0,086) | A2 (0,873) > A1 (0,736) > A5 (0,479) > A3 (0,454) > A6 (0,202) > A4 (0,083) |
| ambiental_saude | Paraná (média) | A2 (0,865) > A5 (0,738) > A3 (0,473) > A1 (0,430) > A6 (0,417) > A4 (0,138) | A2 (0,864) > A5 (0,727) > A3 (0,480) > A1 (0,451) > A6 (0,425) > A4 (0,139) |
| ambiental_saude | Oeste (média) | A2 (0,853) > A5 (0,685) > A3 (0,463) > A1 (0,462) > A6 (0,415) > A4 (0,137) | A2 (0,835) > A5 (0,654) > A1 (0,475) > A3 (0,454) > A6 (0,409) > A4 (0,134) |
| pesos_iguais | Paraná (média) | A2 (0,914) > A5 (0,635) > A1 (0,587) > A3 (0,496) > A6 (0,286) > A4 (0,105) | A2 (0,913) > A5 (0,622) > A1 (0,604) > A3 (0,504) > A6 (0,293) > A4 (0,105) |
| pesos_iguais | Oeste (média) | A2 (0,896) > A1 (0,612) > A5 (0,580) > A3 (0,484) > A6 (0,285) > A4 (0,104) | A2 (0,865) > A1 (0,622) > A5 (0,551) > A3 (0,473) > A6 (0,283) > A4 (0,101) |

| Teste | v3 | v4 |
|---|---|---|
| Ranking só ERA5 (C1 sem correção), base, Paraná (média) | A1 (0,754) > A2 (0,611) > A5 (0,477) > A3 (0,296) > A6 (0,246) > A4 (0,055) | A1 (0,755) > A2 (0,592) > A5 (0,462) > A3 (0,288) > A6 (0,240) > A4 (0,055) |
| Ranking só ERA5 (C1 sem correção), base, Oeste (média) | A1 (0,761) > A2 (0,525) > A5 (0,393) > A3 (0,270) > A6 (0,230) > A4 (0,053) | A1 (0,760) > A2 (0,515) > A5 (0,384) > A3 (0,265) > A6 (0,225) > A4 (0,054) |
| 1º lugar muda em algum teste de ±50 % no peso (Paraná, C1 corrigido)? | não | não |

## 10. T13f — estabilidade da validação por período (só v4)

| Indicador | 2000–2009 | 2010–2016 | 2017–2026 |
|---|---|---|---|
| Estações (n) | n=6: A835, A819, A820, A846, A816, A842 | n=6: A835, A819, A820, A846, A816, A842 | n=7: A835, A819, A820, A846, B803, A816, A842 |
| Estação-safras | 10 | 41 | 46 |
| Viés do vento a 10 m (km/h) | -0,54 | +0,12 | +0,28 |
| Calmaria noturna em fungicidas, estação × ERA5 (%) | 25,8 × 10,0 | 32,7 × 12,5 | 32,4 × 9,3 |
| Kappa A | 0,240 | 0,265 | 0,275 |
| Razão estação/ERA5 — Dessecação | 0,81 | 0,70 | 0,69 |
| Razão estação/ERA5 — Pós-emergência | 0,91 | 0,94 | 0,84 |
| Razão estação/ERA5 — Fungicidas | 1,13 | 1,04 | 0,96 |
| Razão estação/ERA5 — Pré-colheita | 0,88 | 0,87 | 0,88 |

Períodos pelo ano de término da safra (2000–2009 = safras 2000/01–2008/09; 2010–2016 = 2009/10–2015/16; 2017–2026 = 2016/17–2025/26). O conjunto de estações muda entre períodos (antes de 2006 não há estação automática a até 30 km dos municípios).

## 11. O que mudou de conclusão em relação à v3

- **Tendência no período de fungicidas deixou de ser significativa.** Na v3, o Paraná (média) tinha
  +46 h/década (p = 0,02), com os 24 municípios positivos e 5 significativos. Na v4, sem as safras 1995/96–1999/2000
  e com 2024/25–2025/26, fica +20,6 h/década (p = 0,34), 21 de 24 municípios positivos e nenhum
  significativo. A dessecação passou a ter tendência negativa (−24,5 h/década, p = 0,10). A afirmação
  de "aumento das horas aptas em fungicidas" não se sustenta mais; o resultado depende do recorte.
- **Fungicidas continua sendo a fase mais restritiva pelo ERA5** (25,2 % do tempo apto, 455 h e
  46,7 de 75 dias por safra; piores decêndios Fev-3, Jan-2 e Fev-2), mas **não pelas estações**: nas
  7 estações a fase mais restritiva é a dessecação (21,0 %), e fungicidas (26,1 %) fica empatado com
  pós-emergência (26,2 %). Igual à v3, só que agora com 98 estação-safras em vez de 7 anos.
- **A validação ficou mais robusta e quase não mudou**: 7 estações (entra A816 Novo Horizonte-SC e
  B803 passa a ter 4 safras válidas), kappa A 0,26 → 0,27, kappa B 0,17 → 0,20; o ERA5 continua
  superestimando as horas aptas (+35 h/mês no critério A), pelo vento (o ERA5 quase não tem calmaria:
  10 % × 30 % das horas noturnas em fungicidas) e, em sentido contrário, pela chuva.
- **A ordem entre estações piorou**: Spearman mensal (critério A) de +0,77 para +0,32; no período de
  fungicidas continua sem relação (−0,18). Reforça a nota de que as diferenças entre municípios no
  período de fungicidas não são confirmadas pelas estações.
- **Estabilidade (T13f)**: kappa A estável entre períodos (0,24 → 0,27 → 0,28); a razão
  estação/ERA5 no período de fungicidas cai de 1,13 (2000–2009, só 10 estação-safras) para 0,96
  (2017–2026). O viés do vento muda de sinal (−0,5 → +0,3 km/h), em parte porque o conjunto de
  estações muda entre os períodos.
- **Multicritério: conclusão mantida.** A2 (pontas antideriva) é 1º em todos os 4 cenários, no Paraná e
  no Oeste, e em todos os testes de ±50 % nos pesos. A razão estação/ERA5 do ganho de A1 sobe de 0,56
  para 0,66 (C1 corrigido do Paraná 88 → 112 h/safra), mas A1 segue em 2º. Só com o C1 do ERA5 sem
  correção, A1 continua 1º no cenário base (igual à v3). No Oeste, cenário ambiental, A1 e A3 trocam
  de posição (3º/4º).
- **Agrupamento e épocas: sem mudança relevante.** k = 2 com os mesmos 6 municípios no grupo
  restritivo; 25/09 continua a melhor época pela média em 23 dos 24 municípios (Marechal Cândido
  Rondon passa a 15/11); pelo P20, 25/09 em 15 municípios, 05/10 em 8 e 15/10 em 1. O município mais
  favorável em fungicidas passa a ser Marechal Cândido Rondon (33,6 %) e o menos favorável segue
  Castro (15,5 %).

