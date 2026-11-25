"""Dicionário de variáveis e relatório de qualidade dos dados brutos.

Uso:  python -I src/documentacao.py
Saídas: outputs/tables/dicionario_variaveis.csv
        outputs/tables/relatorio_qualidade.csv

Relatório de qualidade (por município e variável):
  - ERA5 (data/raw/<cod_ibge>_<municipio>.parquet), 24 municípios, 2000-01-01 a 2026-05-01;
  - INMET, dados BRUTOS (antes do controle de qualidade) das estações usadas na validação
    (T12a, selecionada = True), associadas ao município mais próximo, em todos os arquivos
    disponíveis no computador (2000-2026; ver src/inventario_inmet.py).
Limites físicos plausíveis em LIMITES (valores fora deles são contados, não alterados).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indicadores import PROC, RAW, TAB  # noqa: E402
from indicadores import ROTULO_SAFRAS  # noqa: E402
from inventario_inmet import fontes, ler_texto  # noqa: E402
from validacao_inmet import estacoes, periodo_estacoes  # noqa: E402

# (mínimo, máximo) plausíveis; None = sem limite naquele lado
LIMITES = {
    "temperature_2m": (-10, 45), "dew_point_2m": (-20, 35), "relative_humidity_2m": (0, 100),
    "precipitation": (0, 150), "wind_speed_10m": (0, 144), "wind_gusts_10m": (0, 200),
    "shortwave_radiation": (0, 1400), "is_day": (0, 1),
    "T": (-10, 45), "UR": (0, 100), "u10": (0, 144), "precip": (0, 150),
}
UNID = {"temperature_2m": "°C", "dew_point_2m": "°C", "relative_humidity_2m": "%",
        "precipitation": "mm/h", "wind_speed_10m": "km/h", "wind_gusts_10m": "km/h",
        "shortwave_radiation": "W/m²", "is_day": "0/1", "T": "°C", "UR": "%",
        "u10": "km/h", "precip": "mm/h"}
ERA5 = "ERA5 (ECMWF; Hersbach et al., 2020) via API histórica do Open-Meteo (models=era5)"
INMET_F = "INMET - estações meteorológicas automáticas (portal.inmet.gov.br/dadoshistoricos)"
P_ERA5 = "2000-01-01 a 2026-05-01 (análises: safras 2000/01 a 2025/26, 1º/set/2000 a 30/abr/2026)"
R_ERA5 = "horária; grade 0,25° (~28 km), extraída no ponto do município"


def dicionario() -> pd.DataFrame:
    L = []

    def add(var, desc, un, fonte, per, res, trat, arq):
        L.append({"variavel": var, "descricao": desc, "unidade": un, "fonte": fonte,
                  "periodo": per, "resolucao": res, "tratamento_aplicado": trat, "arquivo": arq})

    # --- municípios
    arq = "data/processed/municipios.csv"
    add("municipio", "Nome do município", "-", "Lista do estudo (16 originais + 8 do Oeste)",
        "-", "-", "-", arq)
    add("cod_ibge", "Código IBGE do município (7 dígitos)", "-", "geobr::read_municipality (IBGE, 2020)",
        "malha 2020", "-", "associado pelo nome normalizado (sem acentos)", arq)
    add("regiao", "Mesorregião/região de referência", "-", "definição do estudo", "-", "-", "-", arq)
    add("lat, lon", "Coordenadas do município", "graus decimais (WGS84)",
        "API de geocodificação do Open-Meteo (GeoNames), filtrada pelo Paraná", "-", "-",
        "sede municipal (preferência PPLA/maior população); originais mantidos na ampliação", arq)
    add("altitude_m", "Altitude do ponto geocodificado", "m", "Open-Meteo Geocoding", "-", "-", "-", arq)
    add("grupo_origem", "Origem: 'estado' (16 originais) ou 'zoneamento_oeste' (8 novos)", "-",
        "definição do estudo", "-", "-", "-", arq)
    add("celula_era5", "Célula da grade ERA5 usada (lat,lon do centro)", "graus", ERA5, "-",
        "0,25°", "Matelândia e Medianeira compartilham a célula -25,25/-54,00; médias regionais por célula",
        "outputs/tables/T7_clusters.csv")

    # --- ERA5 bruto
    arq = "data/raw/<cod_ibge>_<municipio>.parquet"
    tr = "sem alteração (dado bruto da API)"
    for v, d in [
        ("time_utc", "Instante da observação em UTC"),
        ("time_local", "Instante em horário local America/Sao_Paulo (com horário de verão até 2019)"),
    ]:
        add(v, d, "data-hora", ERA5, P_ERA5, "horária",
            "pedido em unixtime e convertido; sem ambiguidade de horário de verão", arq)
    add("temperature_2m", "Temperatura do ar a 2 m", "°C", ERA5, P_ERA5, R_ERA5,
        "Open-Meteo ajusta a temperatura à altitude do ponto pedido", arq)
    add("relative_humidity_2m", "Umidade relativa do ar a 2 m", "%", ERA5, P_ERA5, R_ERA5, tr, arq)
    add("dew_point_2m", "Temperatura do ponto de orvalho a 2 m", "°C", ERA5, P_ERA5, R_ERA5,
        "ajuste de altitude do Open-Meteo", arq)
    add("precipitation", "Precipitação total acumulada na hora ANTERIOR ao horário", "mm", ERA5,
        P_ERA5, R_ERA5 + "; resolução 0,1 mm", tr, arq)
    add("wind_speed_10m", "Velocidade do vento a 10 m", "km/h", ERA5, P_ERA5, R_ERA5,
        "wind_speed_unit=kmh", arq)
    add("wind_gusts_10m", "Rajada máxima do vento a 10 m", "km/h", ERA5, P_ERA5, R_ERA5, tr, arq)
    add("shortwave_radiation", "Radiação de onda curta incidente (média da hora anterior)", "W/m²",
        ERA5, P_ERA5, R_ERA5, tr, arq)
    add("is_day", "Indicador diurno (1) ou noturno (0) no instante", "0/1", ERA5, P_ERA5, "horária",
        tr, arq)
    add("grid_lat, grid_lon, grid_elevation", "Centro e altitude da célula usada pela API",
        "graus; m", ERA5, "-", "0,25°", tr, arq)

    # --- INMET bruto
    arq = ("'Anos Complementares/<ano>/' e zips 2010-2016 (CSV anuais do INMET) -> "
           "data/processed/inmet/<codigo>.parquet")
    inv = estacoes()
    per = periodo_estacoes(inv[inv["selecionada"]])
    qc = "-9999 = falha -> ausente; controle de qualidade: valores fora dos limites físicos -> ausente"
    add("precip (INMET)", "PRECIPITAÇÃO TOTAL, HORÁRIO (acumulada na hora anterior)", "mm",
        INMET_F, per, "horária, pontual; pluviômetro de báscula 0,2 mm", qc, arq)
    add("T (INMET)", "TEMPERATURA DO AR - BULBO SECO, HORARIA", "°C", INMET_F, per,
        "horária, pontual, abrigo a ~2 m", qc, arq)
    add("UR (INMET)", "UMIDADE RELATIVA DO AR, HORARIA", "%", INMET_F, per, "horária, pontual", qc, arq)
    add("u10 (INMET)", "VENTO, VELOCIDADE HORARIA, medido a 10 m", "km/h", INMET_F, per,
        "horária, pontual, anemômetro a 10 m", "m/s x 3,6; " + qc, arq)
    add("codigo, lat, lon, alt (INMET)", "Código WMO e localização da estação", "-; graus; m",
        INMET_F, per, "-", "lidos do cabeçalho do CSV", "outputs/tables/T12a_estacoes_inmet.csv")
    add("n_safras_validas, pct_validas_T/UR/vento/chuva, usada_na_validacao, incluida_na_media",
        "Inventário das estações automáticas (PR + SC/SP/MS a até 30 km dos 24 municípios)",
        "nº; %; booleano", INMET_F, "2000-2026", "estação; estação-safra (set-abr)",
        "safra válida: >= 70 % de horas válidas em T, UR e vento; média: >= 2 safras válidas",
        "outputs/tables/T_inventario_inmet.csv")

    # --- indicadores horários
    arq = "data/processed/indicadores_horarios.parquet"
    rh = "horária; por município"
    add("u2", "Vento a 2 m (perfil logarítmico FAO-56): u2 = u10 x 4,87/ln(67,8x10-5,42)",
        "km/h", "derivado de wind_speed_10m", P_ERA5, rh, "fator 0,748", arq)
    add("Tbu", "Temperatura de bulbo úmido (Stull, 2011)", "°C", "derivado de T e UR", P_ERA5, rh,
        "válida para UR 5-99 % e T -20 a 50 °C", arq)
    add("deltaT", "Delta T = T - Tbu", "°C", "derivado", P_ERA5, rh, "-", arq)
    add("chuva_hora", "Chuva durante a hora de aplicação [t, t+1h) = precipitation(t+1h)", "mm",
        "derivado", P_ERA5, rh, "deslocamento de 1 registro", arq)
    add("chuva_2h_seg", "Chuva nas 2 h após a aplicação = precipitation(t+2h)+(t+3h)", "mm",
        "derivado", P_ERA5, rh, "deslocamento de 2 e 3 registros", arq)
    add("apta_A", "Hora apta, critério A: Delta T 2-8 °C; u2 3-10 km/h; T<30 °C; UR>=50 %; "
        "chuva na hora = 0; chuva nas 2 h seguintes < 1 mm", "booleano", "derivado", P_ERA5, rh,
        "-", arq)
    add("apta_B", "Hora apta, critério B (Silva, Oliveira e Gandolfo, 2018): T<30 °C; UR>55 %; "
        "u10 3-12 km/h; chuva na hora < 0,2 mm", "booleano", "derivado", P_ERA5, rh, "-", arq)
    add("janela_A, janela_B", "Hora apta em sequência >= 2 h entre 06h e 20h locais", "booleano",
        "derivado", P_ERA5, rh, "-", arq)
    add("motivo_A, motivo_B", "Motivo principal de inaptidão (1º critério violado na ordem definida)",
        "categoria", "derivado", P_ERA5, rh, "ordem A: DeltaT baixo, DeltaT alto, vento fraco, "
        "vento forte, temperatura, UR, chuva, chuva logo depois", arq)

    # --- diários
    arq = "data/processed/indicadores_diarios.parquet"
    rd = "diária (data local); por município"
    add("horas_aptas_A/B", "Horas aptas no dia", "h", "derivado", P_ERA5, rd, "-", arq)
    add("horas_aptas_dia_A/B, horas_aptas_noite_A/B", "Horas aptas diurnas (is_day=1) e noturnas",
        "h", "derivado", P_ERA5, rd, "-", arq)
    add("horas_janela_A/B", "Horas aptas em janelas >= 2 h entre 06-20 h (horas utilizáveis)", "h",
        "derivado", P_ERA5, rd, "-", arq)
    add("dia_apto_A/B", "Dia com >= 1 janela de 2 h entre 06-20 h", "0/1", "derivado", P_ERA5, rd,
        "-", arq)
    add("viol_<crit>_<motivo>, princ_<crit>_<motivo>", "Horas inaptas com o critério violado / "
        "com ele como motivo principal", "h", "derivado", P_ERA5, rd, "-", arq)

    # --- tabelas de resultados
    T = "outputs/tables/"
    saf = f"safras {ROTULO_SAFRAS} (26)"
    add("horas aptas por decêndio (media, dp)", "Horas aptas por decêndio set-abr", "h/decêndio",
        "derivado", saf, "decêndio; município e médias regionais", "média e dp entre safras", T + "T1_*.csv")
    add("dias_aptos, horas_aptas, pct_tempo_apto por fase", "Por fase operacional da safra",
        "dias; h; %", "derivado", saf, "fase; município", "fungicidas: 16/dez até o fim de fev",
        T + "T2_*.csv")
    add("horas/dias aptos por época de semeadura (média, dp, p20)", "Fases fenológicas por DAS "
        "(15:30:60:35 reescaladas para 120 d) e dessecação -20 a 0 DAS", "h; dias", "derivado", saf,
        "época x fase", "-", T + "T2b_*.csv, T2c_*.csv")
    add("pct_horas_inaptas_com_violacao, pct_motivo_principal", "Motivos de inaptidão por fase",
        "%", "derivado", saf, "fase; região", "médias regionais por célula ERA5", T + "T3_*.csv")
    add("horas_aptas_diurnas/noturnas, pct_noturno", "Horas aptas por fase, dia x noite", "h; %",
        "derivado", saf, "fase", "-", T + "T4_*.csv")
    add("horas_aptas_A/B mensais, pct, razao_A_B", "Comparação dos critérios, média 2004-2014",
        "h/mês; %", "derivado", "2004-2014", "mês", "-", T + "T0_comparacao_criterios.csv")
    add("P_F, P_F_dado_F, P_F_dado_NF", "Cadeia de Markov de 1ª ordem dos dias aptos", "probabilidade",
        "derivado", saf, "decêndio; município", "qui² de independência", T + "T5_markov.csv")
    add("tau, p_valor, sen_h_por_decada", "Mann-Kendall e inclinação de Sen das horas aptas por fase",
        "-; -; h/década", "derivado", saf, "fase; município", "pymannkendall.original_test",
        T + "T6_mann_kendall.csv")
    add("grupo, silhueta", "k-means (k 2-5) sobre horas aptas médias por decêndio padronizadas",
        "-", "derivado", saf, "uma amostra por célula ERA5", "k pela silhueta", T + "T7_clusters.csv")
    add("ganho_h_media (C1)", "Ganho de horas utilizáveis no período de fungicidas por alternativa",
        "h/safra", "derivado", saf, "região", "suposições no cabeçalho de src/ahp_topsis.py",
        T + "T8_ganho_horas_alternativas.csv")
    add("peso, lambda_max, IC, RC", "Pesos AHP (autovetor principal) e consistência", "-",
        "config/ahp_criterios.csv", "-", "-", "RI de Saaty (n=5: 1,12)", T + "T9_pesos_ahp.csv")
    add("CC, ranking, posicao", "Coeficiente de proximidade TOPSIS (normalização vetorial)", "0-1",
        "derivado", "-", "região; cenário de pesos", "-", T + "T10_topsis.csv, T10b_cenarios_topsis.csv")
    add("CC_A1..A6 por variação de peso", "Sensibilidade do TOPSIS a +-50 % no peso de cada critério",
        "0-1", "derivado", "-", "-", "demais pesos renormalizados", T + "T11_sensibilidade.csv")
    add("vies, rmse, r, acuracia, kappa, r_spearman", "Validação ERA5 x INMET (horária e agregada)",
        "unid. da variável; -", "ERA5 no ponto da estação x INMET", per, "horária; mensal; safra",
        "viés = ERA5 - estação", T + "T12_validacao.csv")
    add("pct_aptas_estacao/era5, horas_aptas_*_extrap", "Horas aptas como fração das horas válidas "
        "comuns e extrapoladas para o mês", "%; h/mês", "derivado", per, "mês; estação",
        "nenhum dia descartado", T + "T13_horas_aptas_estacao_vs_era5.csv")
    add("contribuição por condição (Shapley)", "Decomposição de (estação - ERA5) entre as condições "
        "de cada critério", "h/mês", "derivado", per, "mês", "soma = diferença total",
        T + "T13b_decomposicao_discrepancia.csv")
    add("pct_aptas_estacao/era5 por fase, razao_estacao_era5", "Horas aptas por fase operacional, "
        "estação x ERA5 no mesmo ponto e nas mesmas horas válidas", "%; razão", "derivado", per,
        "fase; estação", "média das estações com >= 2 safras válidas", T + "T13c_fases_estacao_vs_era5.csv")
    add("pct_aptas_dia/noite, pct_vento_lt3, ganho_A1", "Período de fungicidas, dia (06-20 h) x noite "
        "(20-06 h); calmaria = u2 < 3 km/h", "%; h/safra", "derivado", per, "estação",
        "-", T + "T13d_noturno_estacao_vs_era5.csv")
    add("horas_aptas_ajustadas, fator_medio", "Paraná: horas aptas do ERA5 x ajustadas pela razão "
        "mensal estação/ERA5 (ajuste aproximado)", "h/fase; %", "derivado", saf, "fase",
        "não é correção de viés validada", T + "T13e_horas_ajustadas.csv")
    add("vies_vento10, calmaria noturna, kappa_A, razao por fase", "Estabilidade da validação por "
        "período (safras que terminam em 2000-2009, 2010-2016, 2017-2026)", "km/h; %; -; razão",
        "derivado", per, "período; estação", "kappa ponderado pelas horas; demais: média das estações",
        T + "T13f_estabilidade_periodos.csv")
    add("ganho_estacao, ganho_era5_mesmos_pontos, razao, C1_corrigido", "C1 corrigido pelas estações "
        "(razão estação/ERA5 do ganho de cada alternativa nos mesmos pontos e horas)", "h/safra; razão",
        "derivado", per, "alternativa; região", "A6 = 0", T + "T8b_C1_corrigido.csv")
    return pd.DataFrame(L)


def resumo(s: pd.Series, var: str) -> dict:
    lo, hi = LIMITES[var]
    v = s.dropna()
    fora = int(((v < lo) | (v > hi)).sum())
    if var == "is_day":
        fora = int((~v.isin([0, 1])).sum())
    return {"n_nan": int(s.isna().sum()), "fora_limites": fora,
            "limite_inferior": lo, "limite_superior": hi,
            "minimo": v.min() if len(v) else np.nan, "maximo": v.max() if len(v) else np.nan,
            "p01": v.quantile(0.01) if len(v) else np.nan,
            "p99": v.quantile(0.99) if len(v) else np.nan}


def qualidade() -> pd.DataFrame:
    linhas = []
    muns = pd.read_csv(PROC / "municipios.csv", encoding="utf-8")
    esperado = len(pd.date_range("2000-01-01", "2026-05-01", freq="D")) * 24
    for _, r in muns.iterrows():
        df = pd.read_parquet(next(RAW.glob(f"{r.cod_ibge}_*.parquet")))
        dup = int(df["time_utc"].duplicated().sum())
        ausentes = esperado - df["time_utc"].nunique()
        for v in ["temperature_2m", "relative_humidity_2m", "dew_point_2m", "precipitation",
                  "wind_speed_10m", "wind_gusts_10m", "shortwave_radiation", "is_day"]:
            s = resumo(df[v], v)
            linhas.append({"fonte": "ERA5", "municipio": r.municipio, "estacao": "-",
                           "variavel": v, "unidade": UNID[v], "periodo": P_ERA5,
                           "n_registros": len(df), "n_esperado": esperado,
                           "horarios_ausentes": ausentes, "duplicidades": dup,
                           "faltantes_total": ausentes + s["n_nan"],
                           "pct_faltantes": 100 * (ausentes + s["n_nan"]) / esperado, **s})
    sel = estacoes()
    sel = sel[sel["selecionada"]]
    arqs, _ = fontes()
    for _, e in sel.iterrows():
        partes = []
        for ano, nome, origem, ler in arqs:
            if f"_{e.codigo}_" in nome:
                partes.append(ler_texto(origem, ler())[1])   # BRUTO (antes do controle de qualidade)
        df = pd.concat(partes, ignore_index=True)
        dup = int(df["time_utc"].duplicated().sum())
        t = df["time_utc"].drop_duplicates()
        esperado_e = len(pd.date_range(t.min().floor("D"), t.max().ceil("D") - pd.Timedelta(hours=1),
                                       freq="h"))
        ausentes = esperado_e - t.nunique()
        for v in ["T", "UR", "u10", "precip"]:
            s = resumo(df[v], v)
            linhas.append({"fonte": "INMET (bruto, antes do QC)", "municipio": e.municipio,
                           "estacao": f"{e.codigo} {e.estacao} ({e.dist_km:.1f} km)",
                           "variavel": v, "unidade": UNID[v],
                           "periodo": f"{t.min():%Y-%m-%d} a {t.max():%Y-%m-%d}",
                           "n_registros": len(df), "n_esperado": esperado_e,
                           "horarios_ausentes": ausentes, "duplicidades": dup,
                           "faltantes_total": ausentes + s["n_nan"],
                           "pct_faltantes": 100 * (ausentes + s["n_nan"]) / esperado_e, **s})
    return pd.DataFrame(linhas)


def main() -> None:
    pd.set_option("display.width", 230)
    d = dicionario()
    d.to_csv(TAB / "dicionario_variaveis.csv", index=False, encoding="utf-8-sig")
    q = qualidade().round(3)
    q.to_csv(TAB / "relatorio_qualidade.csv", index=False, encoding="utf-8-sig")
    print(f"dicionario_variaveis.csv: {len(d)} entradas")
    print(f"relatorio_qualidade.csv: {len(q)} linhas")
    print("\nERA5 (24 municípios) - resumo por variável:")
    e = q[q["fonte"] == "ERA5"].groupby("variavel").agg(
        registros=("n_registros", "min"), faltantes=("faltantes_total", "sum"),
        duplicidades=("duplicidades", "sum"), fora_limites=("fora_limites", "sum"),
        minimo=("minimo", "min"), maximo=("maximo", "max"))
    print(e.to_string())
    print("\nINMET bruto (estações da validação):")
    print(q[q["fonte"] != "ERA5"][["estacao", "variavel", "n_registros", "n_esperado",
                                   "pct_faltantes", "duplicidades", "fora_limites", "minimo",
                                   "maximo", "p01", "p99"]].to_string(index=False))


if __name__ == "__main__":
    main()
