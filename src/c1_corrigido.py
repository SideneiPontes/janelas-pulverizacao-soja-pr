"""C1 corrigido pelas estações do INMET (T8b). Não baixa nada.

Recalcula o ganho de horas utilizáveis no período de fungicidas (16/dez - fim de fev) de cada
alternativa A1-A5 com as MESMAS regras de src/ahp_topsis.py (T8), usando:
  - as estações do INMET incluídas nas médias (T13c: incluida_na_media = >= 2 safras válidas e
    >= 30 dias em todas as fases), só nas horas set-abr das estação-safras válidas (2000/01-2025/26);
  - o ERA5 NOS MESMOS PONTOS (data/raw/era5_estacoes) e nas MESMAS horas válidas
    (horas em que estação e ERA5 têm T, UR, vento e chuva t+1h..t+3h).
Ganho por safra = (horas utilizáveis com a alternativa - horas-base) / horas válidas no período
x 1806 h (75,25 dias x 24 h). Média simples das estações.
Razão = ganho médio estação / ganho médio ERA5 (mesmos pontos), aplicada ao C1 do Paraná e do
Oeste da T8. A6 = 0.

A1 usa "noite" = is_day = 0, como na T8. As estações não têm is_day: ele é calculado pela
elevação solar no instante (fórmulas da NOAA), com o mesmo critério para estação e ERA5; a
concordância com o is_day do Open-Meteo é verificada e informada.

Uso: python -I src/c1_corrigido.py   (ou chamado por src/ahp_topsis.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indicadores import ESTADO, FATOR_U2, OESTE, PROC, RAW, TAB, bulbo_umido_stull, janelas  # noqa: E402
from validacao_inmet import IDX, TZ, era5_estacao, estacoes, mascara_ativa, periodo_estacoes  # noqa: E402

H_FUNG_SAFRA = 75.25 * 24
ALTS = ["A1", "A2", "A3", "A4", "A5"]


def is_day_solar(t_utc: pd.DatetimeIndex, lat: float, lon: float) -> np.ndarray:
    """1 se o sol está acima do horizonte no instante (NOAA, precisão de ~minutos)."""
    doy = t_utc.day_of_year.to_numpy()
    hr = t_utc.hour.to_numpy() + t_utc.minute.to_numpy() / 60
    g = 2 * np.pi / 365 * (doy - 1 + (hr - 12) / 24)
    eqt = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g)
                    - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g))
    dec = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g)
           + 0.000907 * np.sin(2 * g) - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    tst = hr * 60 + eqt + 4 * lon
    ha = np.radians(tst / 4 - 180)
    phi = np.radians(lat)
    cosz = np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.cos(ha)
    return (cosz > 0).astype(int)


def checar_is_day() -> float:
    """Concordância do is_day solar com o is_day do Open-Meteo (Cascavel, 2000-2026)."""
    df = pd.read_parquet(next(RAW.glob("4104808_*.parquet")), columns=["time_utc", "is_day"])
    muns = pd.read_csv(PROC / "municipios.csv", encoding="utf-8").set_index("cod_ibge")
    lat, lon = muns.loc[4104808, ["lat", "lon"]]
    calc = is_day_solar(pd.DatetimeIndex(df["time_utc"]), lat, lon)
    return 100 * (calc == df["is_day"].to_numpy()).mean()


def quadro(d: pd.DataFrame, idx: pd.DatetimeIndex, lat: float, lon: float) -> pd.DataFrame:
    """Mesmas colunas usadas por ahp_topsis.apta()."""
    h = pd.DataFrame(index=idx)
    h["T"], h["UR"] = d["T"], d["UR"]
    h["u2"] = d["u10"] * FATOR_U2
    h["deltaT"] = h["T"] - bulbo_umido_stull(h["T"].to_numpy(), h["UR"].to_numpy())
    p = d["precip"]
    h["p_t1"], h["p_t2"], h["p_t3"] = p.shift(-1), p.shift(-2), p.shift(-3)
    loc = idx.tz_convert(TZ)
    h["hora_local"] = loc.hour
    h["is_day"] = is_day_solar(idx, lat, lon)
    return h


def ganhos(h: pd.DataFrame, val: pd.Series, fung: pd.Series) -> dict:
    from ahp_topsis import BASE, VARIANTES, apta, runs
    base = apta(h, BASE) & val
    jan = janelas(base, h["hora_local"])
    out = {}
    for a, par in VARIANTES.items():                       # A2, A3, A4
        ja = janelas(apta(h, par) & val, h["hora_local"])
        out[a] = int((ja & fung).sum()) - int((jan & fung).sum())
    noite = base & (h["is_day"] == 0)
    out["A1"] = int((noite & (runs(noite) >= 2) & ~jan & fung).sum())
    diurna = base & h["hora_local"].between(6, 19)
    out["A5"] = int((diurna & (runs(diurna) == 1) & fung).sum())
    out["base"] = int((jan & fung).sum())
    return out


def calcular_T8b(T8: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    sel = estacoes()
    t13c = pd.read_csv(TAB / "T13c_fases_estacao_vs_era5.csv", encoding="utf-8-sig")
    ok = set(t13c.loc[t13c["incluida_na_media"] == True, "codigo"])  # noqa: E712
    ms = sel[sel["selecionada"] & sel["codigo"].isin(ok)].reset_index(drop=True)
    idx = IDX
    loc = idx.tz_convert(TZ)
    fung = pd.Series(((loc.month == 12) & (loc.day >= 16)) | (loc.month == 1) | (loc.month == 2),
                     index=idx)
    linhas = []
    for _, e in ms.iterrows():
        est = pd.read_parquet(PROC / "inmet" / f"{e.codigo}.parquet").set_index("time_utc").reindex(idx)
        era = era5_estacao(e).set_index("time_utc").reindex(idx)
        hs, he = quadro(est, idx, e.lat, e.lon), quadro(era, idx, e.lat, e.lon)
        cols = ["T", "UR", "u2", "p_t1", "p_t2", "p_t3"]
        val = hs[cols].notna().all(axis=1) & he[cols].notna().all(axis=1) & mascara_ativa(e.codigo)
        nv = int((val & fung).sum())
        gs, ge = ganhos(hs, val, fung), ganhos(he, val, fung)
        for a in ALTS + ["base"]:
            linhas.append({"codigo": e.codigo, "estacao": e.estacao, "municipio": e.municipio,
                           "alternativa": a, "horas_validas_fung": nv,
                           "ganho_estacao": gs[a] / nv * H_FUNG_SAFRA,
                           "ganho_era5_mesmos_pontos": ge[a] / nv * H_FUNG_SAFRA})
    por_est = pd.DataFrame(linhas)
    m = por_est.groupby("alternativa")[["ganho_estacao", "ganho_era5_mesmos_pontos"]].mean()
    m["razao_estacao_era5"] = m["ganho_estacao"] / m["ganho_era5_mesmos_pontos"]
    c1 = T8[T8["municipio"].isin([ESTADO, OESTE])].pivot(
        index="alternativa", columns="municipio", values="ganho_h_media").astype(float)
    t = pd.DataFrame({"alternativa": ALTS + ["A6"]}).set_index("alternativa")
    t["ganho_estacao_h_safra"] = m["ganho_estacao"]
    t["ganho_era5_mesmos_pontos_h_safra"] = m["ganho_era5_mesmos_pontos"]
    t["razao_estacao_era5"] = m["razao_estacao_era5"]
    t["C1_original_PR"] = c1[ESTADO]
    t["C1_original_Oeste"] = c1[OESTE]
    t["C1_corrigido_PR"] = t["C1_original_PR"] * t["razao_estacao_era5"]
    t["C1_corrigido_Oeste"] = t["C1_original_Oeste"] * t["razao_estacao_era5"]
    t.loc["A6", ["ganho_estacao_h_safra", "ganho_era5_mesmos_pontos_h_safra",
                 "C1_corrigido_PR", "C1_corrigido_Oeste"]] = 0.0
    t["sinal_concorda"] = np.sign(t["ganho_estacao_h_safra"]) == np.sign(t["ganho_era5_mesmos_pontos_h_safra"])
    t["n_estacoes"] = len(ms)
    t["estacoes"] = ", ".join(ms["codigo"])
    t["periodo_validacao"] = periodo_estacoes(ms)
    t = t.reset_index()
    t.round(3).to_csv(TAB / "T8b_C1_corrigido.csv", index=False, encoding="utf-8-sig")
    por_est.round(3).to_csv(PROC / "c1_por_estacao.csv", index=False, encoding="utf-8-sig")
    return t, por_est, checar_is_day()


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    T8 = pd.read_csv(TAB / "T8_ganho_horas_alternativas.csv", encoding="utf-8-sig")
    t, pe, conc = calcular_T8b(T8)
    print(f"is_day solar x Open-Meteo (Cascavel): {conc:.2f} % de concordância")
    print(t.round(2).to_string(index=False))
