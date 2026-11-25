"""Complementos da validação ERA5 x INMET (2010-2016, 6 estações, critério A). Não baixa nada.

Uso:  python -I src/validacao_complementos.py
Pré-requisito: python -I src/validacao_inmet.py (estações em data/processed/inmet/, ERA5 no ponto
das estações em data/raw/era5_estacoes/, T12a e T13).

Em todas as contas entram só as HORAS VÁLIDAS COMUNS: horas em que estação e ERA5 (no ponto da
estação) têm todos os dados do critério A. Média das estações = média simples das 6 estações.

1. T13c: fração de horas aptas por fase operacional (estação x ERA5).
2. T13d: período de fungicidas (16/dez - fim de fev), dia (06-20 h) x noite (20-06 h):
   fração de horas aptas, fração de horas com vento a 2 m < 3 km/h e ganho da alternativa A1
   (horas aptas noturnas em sequências >= 2 h fora das janelas diurnas de 06-20 h).
   Valores por safra = taxa por hora válida x horas daquela parte do dia por safra
   (75,25 dias x 14 h de dia ou x 10 h de noite). Estações com < 30 dias no período ficam fora.
   Diferença em relação a T8: lá a noite é is_day = 0 (pôr ao nascer do sol); aqui 20-06 h.
3. T13e: ajuste aproximado das horas aptas do Paraná (16 municípios, ERA5) por fase, com a
   razão mensal estação/ERA5 da T13 (média das 6 estações, critério A, cenário base).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indicadores import (AGREG, ESTADO, FATOR_U2, PROC, TAB, calendario,  # noqa: E402
                         configurar_agregados, janelas)
from validacao_inmet import ANOS, COND, LOG, TZ, condicoes, era5_estacao  # noqa: E402

FASES = ["Dessecação pré-semeadura", "Pós-emergência", "Fungicidas (R1-R5)",
         "Pré-colheita e colheita"]
DIAS_FUNG = 16 + 31 + 28.25          # dias do período de fungicidas por safra
MIN_DIAS_FUNG = 30
MARCA = "#### COMPLEMENTOS (src/validacao_complementos.py) ####"


def fase_de(loc: pd.DatetimeIndex) -> np.ndarray:
    md = loc.month * 100 + loc.day
    return np.select([(md >= 901) & (md <= 1031), (md >= 1101) & (md <= 1215),
                      (md >= 1216) | (md <= 229), (md >= 301) & (md <= 430)], FASES, default="")


def runs(m: pd.Series) -> pd.Series:
    rid = (m != m.shift()).cumsum()
    return m.groupby(rid).transform("sum").where(m, 0)


def por_estacao(e: pd.Series):
    idx = pd.date_range(f"{ANOS[0]}-01-01 00:00", f"{ANOS[-1]}-12-31 23:00", freq="h", tz="UTC")
    loc = idx.tz_convert(TZ)
    est = pd.read_parquet(PROC / "inmet" / f"{e.codigo}.parquet").set_index("time_utc").reindex(idx)
    era = era5_estacao(e).set_index("time_utc").reindex(idx)
    A_s, _, vA_s, _ = condicoes(est)
    A_e, _, vA_e, _ = condicoes(era)
    val = vA_s & vA_e
    aptS = pd.Series(np.logical_and.reduce([A_s[c] for c in COND["A"]]), index=idx) & val
    aptE = pd.Series(np.logical_and.reduce([A_e[c] for c in COND["A"]]), index=idx) & val
    hora = pd.Series(loc.hour, index=idx)
    fase = pd.Series(fase_de(loc), index=idx)
    dia_loc = pd.Series(loc.tz_localize(None).normalize(), index=idx)

    # 1. fases
    linhas1 = []
    for f in FASES:
        m = fase == f
        linhas1.append({"codigo": e.codigo, "estacao": e.estacao, "municipio": e.municipio,
                        "fase": f, "horas_validas": int((val & m).sum()),
                        "aptas_estacao": int((aptS & m).sum()), "aptas_era5": int((aptE & m).sum())})

    # 2. fungicidas: dia x noite, vento fraco, ganho A1
    fung = fase == "Fungicidas (R1-R5)"
    diurno = hora.between(6, 19)
    linhas2 = {"codigo": e.codigo, "estacao": e.estacao, "municipio": e.municipio,
               "dias_no_periodo": int(dia_loc[fung & val].nunique())}
    for fonte, apt, d in (("estacao", aptS, est), ("era5", aptE, era)):
        u2 = d["u10"] * FATOR_U2
        jan = janelas(apt, pd.Series(loc.hour, index=idx))       # janelas >= 2 h em 06-20 h
        noite_apt = apt & ~diurno
        a1 = noite_apt & (runs(noite_apt) >= 2) & ~jan
        for parte, mp in (("dia", diurno), ("noite", ~diurno)):
            v = val & fung & mp
            linhas2[f"horas_validas_{parte}"] = int(v.sum())
            linhas2[f"pct_aptas_{parte}_{fonte}"] = 100 * apt[v].mean()
            linhas2[f"pct_vento_lt3_{parte}_{fonte}"] = 100 * (u2[v] < 3).mean()
        vd, vn = val & fung & diurno, val & fung & ~diurno
        linhas2[f"util_base_por_h_{fonte}"] = jan[vd].sum() / vd.sum()     # por hora diurna válida
        linhas2[f"ganho_A1_por_h_{fonte}"] = a1[vn].sum() / vn.sum()        # por hora noturna válida
    return linhas1, linhas2


def main() -> None:
    pd.set_option("display.width", 220)
    sel = pd.read_csv(TAB / "T12a_estacoes_inmet.csv", encoding="utf-8-sig")
    ms = sel[sel["selecionada"]].reset_index(drop=True)
    L1, L2 = [], []
    for _, e in ms.iterrows():
        a, b = por_estacao(e)
        L1 += a
        L2.append(b)

    # ---------------- T13c
    t = pd.DataFrame(L1)
    t["pct_aptas_estacao"] = 100 * t["aptas_estacao"] / t["horas_validas"]
    t["pct_aptas_era5"] = 100 * t["aptas_era5"] / t["horas_validas"]
    # média só com estações que têm >= 30 dias de horas válidas em TODAS as fases
    t["incluida_na_media"] = t.groupby("codigo")["horas_validas"].transform("min") >= MIN_DIAS_FUNG * 24
    tm = t[t["incluida_na_media"]]
    med = tm.groupby("fase")[["pct_aptas_estacao", "pct_aptas_era5"]].mean().reindex(FASES)
    med["n_estacoes"] = tm.groupby("fase").size().reindex(FASES)
    med = med.reset_index().assign(codigo="TODAS", estacao="média das estações", municipio="")
    T13c = pd.concat([t, med], ignore_index=True)
    T13c["razao_estacao_era5"] = T13c["pct_aptas_estacao"] / T13c["pct_aptas_era5"]
    T13c["fase"] = pd.Categorical(T13c["fase"], FASES, ordered=True)
    T13c = T13c.sort_values(["codigo", "fase"]).round(3)
    T13c.insert(0, "periodo_analise", f"{ANOS[0]}–{ANOS[-1]}")
    T13c.to_csv(TAB / "T13c_fases_estacao_vs_era5.csv", index=False, encoding="utf-8-sig")

    # ---------------- T13d
    d = pd.DataFrame(L2)
    d["incluida"] = d["dias_no_periodo"] >= MIN_DIAS_FUNG
    for f in ("estacao", "era5"):
        d[f"horas_utilizaveis_dia_por_safra_{f}"] = d[f"util_base_por_h_{f}"] * DIAS_FUNG * 14
        d[f"ganho_A1_h_por_safra_{f}"] = d[f"ganho_A1_por_h_{f}"] * DIAS_FUNG * 10
        d[f"horas_aptas_dia_por_safra_{f}"] = d[f"pct_aptas_dia_{f}"] / 100 * DIAS_FUNG * 14
        d[f"horas_aptas_noite_por_safra_{f}"] = d[f"pct_aptas_noite_{f}"] / 100 * DIAS_FUNG * 10
        d[f"ganho_A1_pct_{f}"] = 100 * d[f"ganho_A1_h_por_safra_{f}"] / d[f"horas_utilizaveis_dia_por_safra_{f}"]
    num = [c for c in d.columns if c not in ("codigo", "estacao", "municipio", "incluida")]
    m = d[d["incluida"]][num].mean().to_frame().T.assign(
        codigo="TODAS", estacao=f"média das estações (n={int(d['incluida'].sum())})", municipio="",
        incluida=True)
    T13d = pd.concat([d, m], ignore_index=True)
    t8 = pd.read_csv(TAB / "T8_ganho_horas_alternativas.csv", encoding="utf-8-sig")
    t8 = t8[t8["alternativa"] == "A1"].set_index("municipio")["ganho_h_media"]
    T13d["ganho_A1_T8_era5_municipio"] = T13d["municipio"].map(t8)
    T13d.loc[T13d["codigo"] == "TODAS", "ganho_A1_T8_era5_municipio"] = \
        T13d.loc[T13d["incluida"] & (T13d["codigo"] != "TODAS"), "municipio"].map(t8).mean()
    T13d.insert(0, "periodo_analise", f"{ANOS[0]}–{ANOS[-1]}")
    T13d.round(3).to_csv(TAB / "T13d_noturno_estacao_vs_era5.csv", index=False, encoding="utf-8-sig")

    # ---------------- T13e
    t13 = pd.read_csv(TAB / "T13_horas_aptas_estacao_vs_era5.csv", encoding="utf-8-sig")
    raz = t13[(t13["codigo"] == "TODAS") & (t13["criterio"] == "A") & (t13["cenario"] == "base")]
    raz = raz.set_index("mes")["razao_estacao_era5"]
    muns = pd.read_csv(PROC / "municipios.csv", encoding="utf-8")
    configurar_agregados(muns)
    D = calendario(pd.read_parquet(PROC / "indicadores_diarios.parquet",
                                   columns=["municipio", "data", "horas", "horas_aptas_A"]))
    D = D[D["municipio"].isin(AGREG[ESTADO]) & (D["fase"] != "")].copy()
    D["razao"] = D["mes"].map(raz)
    D["aptas_ajust"] = D["horas_aptas_A"] * D["razao"]
    s = D.groupby(["fase", "safra", "municipio"])[["horas", "horas_aptas_A", "aptas_ajust"]].sum()
    s = s.groupby(["fase", "safra"]).mean().groupby("fase").mean().reindex(FASES)
    T13e = pd.DataFrame({
        "regiao": ESTADO, "fase": FASES,
        "horas_fase": s["horas"].to_numpy(),
        "horas_aptas_era5": s["horas_aptas_A"].to_numpy(),
        "horas_aptas_ajustadas": s["aptas_ajust"].to_numpy()})
    T13e["pct_tempo_apto_era5"] = 100 * T13e["horas_aptas_era5"] / T13e["horas_fase"]
    T13e["pct_tempo_apto_ajustado"] = 100 * T13e["horas_aptas_ajustadas"] / T13e["horas_fase"]
    T13e["fator_medio"] = T13e["horas_aptas_ajustadas"] / T13e["horas_aptas_era5"]
    T13e["observacao"] = ("ajuste aproximado: razão mensal estação/ERA5 (critério A, média de 6 "
                          f"estações INMET, {ANOS[0]}–{ANOS[-1]}) aplicada às safras 1995/96–2023/24")
    T13e.round(3).to_csv(TAB / "T13e_horas_ajustadas.csv", index=False, encoding="utf-8-sig")

    # ---------------- log e resumo
    linhas = [MARCA,
              f"Período: {ANOS[0]}–{ANOS[-1]}; estações: " + ", ".join(
                  f"{r.codigo} {r.estacao}" for r in ms.itertuples()) + "; critério A.",
              "Horas válidas comuns: estação e ERA5 (no ponto da estação) com todos os dados.",
              "T13e: AJUSTE APROXIMADO. As horas aptas do ERA5 (Paraná, 16 municípios) foram",
              "multiplicadas pela razão mensal estação/ERA5 da T13 (média de apenas 6 estações do",
              f"INMET, {ANOS[0]}–{ANOS[-1]}). A razão supõe que o viés do ERA5 é o mesmo em todos os",
              "municípios e safras; não é uma correção de viés validada.",
              "Razões mensais usadas: " + ", ".join(f"{m}:{r:.2f}" for m, r in raz.items())]
    txt = LOG.read_text(encoding="utf-8") if LOG.exists() else ""
    txt = txt.split("\n" + MARCA)[0].rstrip("\n") + "\n\n" + "\n".join(linhas) + "\n"
    LOG.write_text(txt, encoding="utf-8")

    def titulo(x):
        print("\n" + "=" * 90 + f"\n{x}\n" + "=" * 90)

    titulo("T13c - % de horas aptas por fase (média das estações; mesmas horas válidas)")
    c = T13c[T13c["codigo"] == "TODAS"][["fase", "pct_aptas_estacao", "pct_aptas_era5",
                                         "razao_estacao_era5"]]
    print(c.round(1).to_string(index=False))
    titulo("T13c - por estação: % aptas pela estação")
    print(T13c[T13c["codigo"] != "TODAS"].pivot(index=["codigo", "estacao"], columns="fase",
                                                 values="pct_aptas_estacao").round(1).to_string())
    titulo("T13d - período de fungicidas, dia (06-20 h) x noite (20-06 h)")
    cols = ["codigo", "dias_no_periodo", "pct_aptas_dia_estacao", "pct_aptas_dia_era5",
            "pct_aptas_noite_estacao", "pct_aptas_noite_era5", "pct_vento_lt3_dia_estacao",
            "pct_vento_lt3_dia_era5", "pct_vento_lt3_noite_estacao", "pct_vento_lt3_noite_era5"]
    print(T13d[cols].round(1).to_string(index=False))
    print()
    print(T13d[["codigo", "incluida", "horas_utilizaveis_dia_por_safra_estacao",
                "horas_utilizaveis_dia_por_safra_era5", "ganho_A1_h_por_safra_estacao",
                "ganho_A1_h_por_safra_era5", "ganho_A1_T8_era5_municipio"]].round(1).to_string(index=False))
    titulo("T13e - Paraná: horas aptas por fase, ERA5 x ajustadas (AJUSTE APROXIMADO, 6 estações)")
    print(T13e.drop(columns=["regiao", "observacao"]).round(1).to_string(index=False))
    print(f"\nNota gravada em {LOG}")


if __name__ == "__main__":
    main()
