# Janelas de pulverização na cadeia da soja no Paraná: ERA5 validado com estações do INMET e priorização multicritério

## Resumo

Este repositório traz o código e os resultados de uma análise das janelas meteorológicas para pulverização terrestre em soja em 24 municípios do Paraná (16 municípios distribuídos pelo estado e 8 do Oeste), com dados horários da reanálise ERA5 de 1995 a 2024. Para cada hora, a aptidão é avaliada por dois critérios:
- **critério A:** Delta T entre 2 e 8 °C, vento a 2 m entre 3 e 10 km/h, temperatura abaixo de 30 °C, umidade relativa de pelo menos 50 % e ausência de chuva na hora e nas 2 horas seguintes;
- **critério B:** o de Silva, Oliveira e Gandolfo (2018).

Com essas horas são calculados janelas, dias aptos por fase operacional (dessecação, pós-emergência, fungicidas e pré-colheita) e épocas de semeadura. Sobre esses indicadores aplicam-se cadeias de Markov, tendências de Mann-Kendall/Sen e agrupamento k-means. O ERA5 foi validado com 6 estações automáticas do INMET (2010–2016). As estratégias para ampliar a janela no período de fungicidas foram priorizadas por AHP-TOPSIS, com o critério de ganho de horas corrigido pelas estações. Pontas de indução de ar (antideriva) ficaram em 1º lugar em todos os cenários de pesos.

## Fontes dos dados

| Dado | Fonte | Licença / termos |
|---|---|---|
| Reanálise horária ERA5 (temperatura, umidade, vento, chuva etc.) | Copernicus Climate Change Service (C3S/ECMWF), obtida pela API histórica do [Open-Meteo](https://open-meteo.com/) | CC BY 4.0 (Open-Meteo); contém informação modificada do Copernicus Climate Change Service |
| Estações meteorológicas automáticas | [INMET – dados históricos](https://portal.inmet.gov.br/dadoshistoricos) | Dados públicos do INMET |
| Malhas estadual e municipal (2020) | IBGE, via pacote [geobr](https://github.com/ipea/geobr) (Ipea) | Dados públicos do IBGE |
| Coordenadas e altitude dos municípios | API de geocodificação do Open-Meteo (GeoNames) | CC BY 4.0 |

Os dados brutos **não** estão neste repositório. Os scripts `download_era5.py` e `download_inmet.py` baixam tudo de novo.

> **Aviso sobre a validação:** a validação com o INMET usou apenas **2010–2016**. Durante o trabalho, o portal de dados históricos do INMET ficou fora do ar (manutenção) e os anos 2017–2024 não puderam ser baixados. Quando o portal voltar, basta baixar o restante e rodar de novo com `INMET_ANO_FIM=2024` (veja abaixo).

## Estrutura

```
src/       scripts Python, na ordem de execução abaixo
config/    ahp_criterios.csv: matriz de comparação par a par do AHP (editável)
outputs/
  tables/  tabelas T0–T13e, matriz de decisão qualitativa, dicionário e relatório de qualidade
  figures/ figuras F1–F8
  mymaps_pontos.csv     pontos para importar no Google My Maps
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
| 2 | `python src/download_era5.py` | Baixa o ERA5 horário 1995–2024 por município (blocos de 5 anos, retomável) → `data/raw/` |
| 3 | `python src/verificar_raw.py` | Confere linhas, período e faltantes dos arquivos baixados → `verificacao_raw.csv` |
| 4 | `python src/indicadores.py` | Aptidão horária (critérios A e B), janelas, dias aptos por fase e época → T0–T4, T2b, T2c |
| 5 | `python src/estatistica.py` | Markov (T5), Mann-Kendall/Sen (T6), k-means (T7) e figuras F1–F5 |
| 6 | `python src/download_inmet.py 2010 2016` | Baixa os arquivos anuais do INMET e extrai as estações do PR → `data/raw/inmet/` |
| 7 | `python src/validacao_inmet.py` | Validação ERA5 × INMET → T12, T12a, T13, T13b, F7 |
| 8 | `python src/validacao_complementos.py` | Fases, período noturno e ajuste aproximado → T13c, T13d, T13e |
| 9 | `python src/ahp_topsis.py` | Ganho de horas (T8), C1 corrigido pelas estações (T8b, via `c1_corrigido.py`), AHP (T9), TOPSIS (T10, T10b), sensibilidade (T11) e figuras F6, F6b |
| 10 | `python src/documentacao.py` | Dicionário de variáveis e relatório de qualidade |
| 11 | `python src/mapa_final.py` | CSV do My Maps, mapa de apresentação (F8), mapa interativo e versão final de F1 e F5 |

Observações:
- **Limite do Open-Meteo:** o plano gratuito limita as requisições por hora e por dia. O download do ERA5 pode parar com erro 429. Nesse caso, rode o script de novo mais tarde: ele retoma de onde parou.
- **Validação até 2024:** para usar os anos 2017–2024 do INMET, rode `python src/download_inmet.py 2010 2024` e repita os passos 7 a 11 com a variável de ambiente `INMET_ANO_FIM=2024`.
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
