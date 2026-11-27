# Janelas de pulverização na cadeia da soja no Paraná: ERA5 validado com estações do INMET e priorização multicritério

## Resumo

Este repositório traz o código e os resultados de uma análise das janelas meteorológicas para pulverização terrestre em soja em 24 municípios do Paraná (16 municípios distribuídos pelo estado e 8 do Oeste), com dados horários da reanálise ERA5 nas safras 2000/01 a 2025/26 (1º/set/2000 a 30/abr/2026, 26 safras). Para cada hora, a aptidão é avaliada por dois critérios:
- **critério A:** Delta T entre 2 e 8 °C, vento a 2 m entre 3 e 10 km/h, temperatura abaixo de 30 °C, umidade relativa de pelo menos 50 % e ausência de chuva na hora e nas 2 horas seguintes;
- **critério B:** o de Silva, Oliveira e Gandolfo (2018).

Com essas horas são calculados janelas, dias aptos por fase operacional (dessecação, pós-emergência, fungicidas e pré-colheita) e épocas de semeadura. Sobre esses indicadores aplicam-se cadeias de Markov, tendências de Mann-Kendall/Sen e agrupamento k-means. O ERA5 foi validado com 7 estações automáticas do INMET a até 30 km dos municípios (A835 Maringá, A819 Castro, A820 Marechal Cândido Rondon, A846 Foz do Iguaçu, B803 Campina da Lagoa, A816 Novo Horizonte-SC e A842 Nova Fátima), em 98 estação-safras válidas entre 2006/07 e 2025/26 (set–abr, com pelo menos 70 % de horas válidas em temperatura, umidade e vento). As estratégias para ampliar a janela no período de fungicidas foram priorizadas por AHP-TOPSIS, com o critério de ganho de horas corrigido pelas estações. Com as notas dos autores, pontas de indução de ar (antideriva) ficaram em 1º lugar em todos os cenários de pesos; com as notas de um painel de 3 especialistas (versão principal), a pulverização noturna passa ao 1º lugar e as pontas antideriva ao 2º (ver [outputs/RESUMO_PAINEL.md](outputs/RESUMO_PAINEL.md)).

## Fontes dos dados

| Dado | Fonte | Licença / termos |
|---|---|---|
| Reanálise horária ERA5 (temperatura, umidade, vento, chuva etc.) | Copernicus Climate Change Service (C3S/ECMWF), obtida pela API histórica do [Open-Meteo](https://open-meteo.com/) | CC BY 4.0 (Open-Meteo); contém informação modificada do Copernicus Climate Change Service |
| Estações meteorológicas automáticas | [INMET – dados históricos](https://portal.inmet.gov.br/dadoshistoricos) | Dados públicos do INMET |
| Malhas estadual e municipal (2020) | IBGE, via pacote [geobr](https://github.com/ipea/geobr) (Ipea) | Dados públicos do IBGE |
| Coordenadas e altitude dos municípios | API de geocodificação do Open-Meteo (GeoNames) | CC BY 4.0 |

Os dados brutos **não** estão neste repositório. O ERA5 é baixado de novo por `download_era5.py`. Os arquivos anuais do INMET (CSV de todas as estações, um zip por ano no portal) devem ser colocados em `Anos Complementares/<ano>/` (2000–2009 e 2017–2026) e os zips de 2010–2016 em `%TEMP%/inmet_zips` (ou na pasta indicada pela variável `INMET_ZIP_DIR`); `download_inmet.py` baixa esses zips quando o portal está no ar.

> **Versões:** a versão atual (v4) cobre as safras 2000/01–2025/26 e valida o ERA5 em todo o período disponível nas estações. A versão anterior (v3: ERA5 1995–2024, validação só com 2010–2016, porque o portal do INMET esteve fora do ar) está comparada com a atual em [outputs/RESUMO_V4.md](outputs/RESUMO_V4.md).

## Estrutura

```
src/       scripts Python, na ordem de execução abaixo
config/    ahp_criterios.csv: matriz de comparação par a par do AHP (editável)
outputs/
  tables/  tabelas T0–T13f, inventário das estações INMET, matriz de decisão qualitativa,
           dicionário e relatório de qualidade
  figures/ figuras F1–F8
  mymaps_pontos.csv     pontos para importar no Google My Maps
  mymaps/               versões simplificadas (municipios.csv, estacoes_inmet.csv)
  RESUMO_V4.md          comparação v3 × v4 e principais resultados
  mapa_interativo.html  mapa interativo (abre no navegador, precisa de internet)
```

## Como instalar

Requer Python 3.12.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements-lock.txt   # versões exatas usadas no artigo
# ou: pip install -r requirements.txt  # versões mais recentes
```

## Como rodar (na ordem)

| # | Comando | O que faz |
|---|---|---|
| 1 | `python src/municipios.py` | Lista os 24 municípios com coordenadas, altitude e código IBGE → `data/processed/municipios.csv` |
| 2 | `python src/download_era5.py` | Baixa o ERA5 horário de 2000-01-01 a 2026-05-01 por município (blocos de 5 anos, retomável) → `data/raw/` |
| 3 | `python src/verificar_raw.py` | Confere linhas, período e faltantes dos arquivos baixados → `verificacao_raw.csv` |
| 4 | `python src/indicadores.py` | Aptidão horária (critérios A e B), janelas, dias aptos por fase e época → T0–T4, T2b, T2c |
| 5 | `python src/estatistica.py` | Markov (T5), Mann-Kendall/Sen (T6), k-means (T7) e figuras F1–F5 |
| 6 | `python src/inventario_inmet.py` | Confere os arquivos do INMET, lista as estações do PR e vizinhas a até 30 km, monta as séries horárias e as estação-safras válidas → `T_inventario_inmet.csv` |
| 7 | `python src/validacao_inmet.py` | Validação ERA5 × INMET (baixa o ERA5 no ponto de cada estação) → T12, T12a, T13, T13b, F7 |
| 8 | `python src/validacao_complementos.py` | Fases, período noturno, ajuste aproximado e estabilidade por período → T13c, T13d, T13e, T13f |
| 9 | `python src/ahp_topsis.py` | Ganho de horas (T8), C1 corrigido pelas estações (T8b, via `c1_corrigido.py`), AHP (T9), TOPSIS (T10, T10b), sensibilidade (T11) e figuras F6, F6b |
| 10 | `python src/documentacao.py` | Dicionário de variáveis e relatório de qualidade |
| 11 | `python src/mapa_final.py` | CSVs do My Maps, mapa de apresentação (F8), mapa interativo e versão final de F1 e F5 |
| 12 | `python src/resumo_v4.py` | Comparação v3 × v4 → `outputs/RESUMO_V4.md` |
| 13 | `python src/painel_especialistas.py` | Notas C2–C5 do painel de especialistas (Google Forms, anonimizado): concordância (W de Kendall), TOPSIS com a mediana do painel (versão principal) × notas dos autores, sensibilidade e comparação de versões → T14–T15c, F6b, F9, `outputs/RESUMO_PAINEL.md` |

Depois do passo 9, rode de novo o passo 8 (a T13d usa a T8).

Observações:
- **Limite do Open-Meteo:** o plano gratuito limita as requisições por hora e por dia. O download do ERA5 pode parar com erro 429. Nesse caso, rode o script de novo mais tarde: ele retoma de onde parou.
- **Rodar só a análise de decisão:** a planilha `outputs/tables/matriz_decisao_qualitativa.xlsx` e `config/ahp_criterios.csv` guardam os julgamentos qualitativos usados no AHP-TOPSIS. Edite esses dois arquivos e rode de novo o passo 9.

## Dicionário de dados e qualidade

- [outputs/tables/dicionario_variaveis.csv](outputs/tables/dicionario_variaveis.csv): descrição, unidade, fonte, período, resolução e tratamento aplicado de cada variável bruta e derivada.
- [outputs/tables/relatorio_qualidade.csv](outputs/tables/relatorio_qualidade.csv): registros esperados e obtidos, horários ausentes, duplicidades, faltantes, valores fora dos limites físicos e percentis dos dados ERA5 (24 municípios) e das estações do INMET.

## Licenças

- **Código** (`src/`): [MIT](LICENSE).
- **Tabelas e figuras** (`outputs/`): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.pt-br). Você pode reutilizá-las, desde que cite a fonte.
- **Dados de terceiros:** os dados ERA5/Copernicus, INMET e IBGE seguem as licenças das fontes originais (tabela acima).

## Como citar

> MENDES, Sidenei. **Janelas de pulverização na cadeia da soja no Paraná: ERA5 validado com estações do INMET e priorização multicritério**. 2026. Código e dados derivados. Disponível em: https://github.com/SideneiPontes/janelas-pulverizacao-soja-pr.

```bibtex
@misc{mendes2026janelas,
  author = {Mendes, Sidenei},
  title  = {Janelas de pulverização na cadeia da soja no Paraná: ERA5 validado com estações do INMET e priorização multicritério},
  year   = {2026},
  url    = {https://github.com/SideneiPontes/janelas-pulverizacao-soja-pr}
}
```
