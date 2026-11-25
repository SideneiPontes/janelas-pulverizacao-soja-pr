"""Resumo comparativo v3 (ERA5 1995-2024; INMET 2010-2016) x v4 (safras 2000/01-2025/26).

Lê apenas tabelas já calculadas:
  v3: outputs_v3_1995-2024/tables (cópia da versão anterior)
  v4: outputs/tables
Saída: outputs/RESUMO_V4.md

Uso:  python -I src/resumo_v4.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indicadores import ESTADO, OESTE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "outputs_v3_1995-2024" / "tables"
V4 = ROOT / "outputs" / "tables"
OUT = ROOT / "outputs" / "RESUMO_V4.md"
FUNG = "Fungicidas (R1-R5)"
DESS = "Dessecação pré-semeadura"
FASES = [DESS, "Pós-emergência", FUNG, "Pré-colheita e colheita"]
FASE_CURTA = {DESS: "Dessecação", "Pós-emergência": "Pós-emergência", FUNG: "Fungicidas",
              "Pré-colheita e colheita": "Pré-colheita"}
MES = {9: "set", 10: "out", 11: "nov", 12: "dez", 1: "jan", 2: "fev", 3: "mar", 4: "abr"}
ALTS = {"A1": "noturna", "A2": "antideriva", "A3": "adjuvante", "A4": "drone", "A5": "estação+SSD",
        "A6": "capacidade"}


def n(x, nd=1, sinal=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "–"
    s = f"{x:+.{nd}f}" if sinal else f"{x:.{nd}f}"
    if nd == 0:
        s = f"{x:+,.0f}" if sinal else f"{x:,.0f}"
        s = s.replace(",", ".")
        return s
    return s.replace(".", ",")


def ler(d: Path, nome: str) -> pd.DataFrame | None:
    f = d / f"{nome}.csv"
    return pd.read_csv(f, encoding="utf-8-sig") if f.exists() else None


# ----------------------------------------------------------------------------
def metricas(d: Path) -> dict:
    R = {}
    t12a = ler(d, "T12a_estacoes_inmet")
    sel = t12a[t12a["selecionada"]].sort_values("dist_km")
    R["n_est"] = len(sel)
    R["lista_est"] = "; ".join(f"{r.codigo} {r.estacao.title()} ({n(r.dist_km)} km de {r.municipio})"
                               for r in sel.itertuples())
    t12 = ler(d, "T12_validacao")
    R["periodo_val"] = t12["periodo_analise"].iloc[0]
    T = t12[t12["codigo"] == "TODAS"]

    def linha(esc, cen, var):
        x = T[(T["escala"] == esc) & (T["cenario"] == cen) & (T["variavel"] == var)]
        return x.iloc[0] if len(x) else None

    fs = linha("período de fungicidas", "base", "Horas aptas (safras) - critério A")
    R["n_est_safras_fung"] = int(fs["n"])
    inv = ler(d, "T_inventario_inmet")
    R["n_est_safras_validas"] = (int(inv.loc[inv["usada_na_validacao"], "n_safras_validas"].sum())
                                 if inv is not None else None)
    R["n_media"] = (int(inv["incluida_na_media"].sum()) if inv is not None else None)
    R["falhas_validas"] = None
    if inv is not None:
        S = pd.read_csv(ROOT / "data" / "processed" / "inmet_safras.csv", encoding="utf-8-sig")
        S = S[S["safra_valida"] & S["codigo"].isin(inv.loc[inv["usada_na_validacao"], "codigo"])]
        R["falhas_validas"] = ", ".join(f"{k} {n(100 - S[f'pct_validas_{c}'].mean())} %" for k, c in
                                        (("T", "T"), ("UR", "UR"), ("u10", "vento"), ("precip", "chuva")))

    vr = ler(d, "verificacao_raw")
    R["registros_mun"] = f"{n(vr['linhas'].min(), 0)} (todos os {len(vr)} municípios)" \
        if vr["linhas"].nunique() == 1 else f"{n(vr['linhas'].min(), 0)}–{n(vr['linhas'].max(), 0)}"
    R["periodo_raw"] = f"{str(vr['inicio_local'].min())[:10]} a {str(vr['fim_local'].max())[:10]}"
    q = ler(d, "relatorio_qualidade")
    e = q[q["fonte"] == "ERA5"].groupby("variavel")["fora_limites"].sum()
    R["outliers_era5"] = ", ".join(f"{v}: {int(k)}" for v, k in e.items() if k > 0) or "nenhum"
    i = q[q["fonte"] != "ERA5"]
    R["outliers_inmet"] = ", ".join(f"{v}: {int(k)}" for v, k in i.groupby("variavel")["fora_limites"].sum().items()
                                    if k > 0) or "nenhum (valores brutos dentro dos limites físicos)"
    R["falhas_inmet"] = ", ".join(f"{v} {n(x)} %" for v, x in
                                  i.groupby("variavel")["pct_faltantes"].mean().reindex(["T", "UR", "u10", "precip"]).items())

    for v, k in [("Temperatura (°C)", "T"), ("UR (%)", "UR"), ("Delta T (°C)", "dT"),
                 ("Vento a 10 m (km/h)", "u10")]:
        x = linha("horária", "-", v)
        R[f"h_{k}"] = f"{n(x['vies'], 2, True)} / {n(x['rmse'], 2)} / {n(x['r'], 3)}"
    for crit in ("A", "B"):
        for c in ("vento", "chuva"):
            x = linha("horária", "base", f"Condição {c} satisfeita - critério {crit}")
            R[f"cond_{c}_{crit}"] = f"{n(x['pct_apta_estacao'])} × {n(x['pct_apta_era5'])}"
        R[f"kappa_{crit}"] = n(linha("horária", "base", f"Classificação apta - critério {crit}")["kappa"], 3)
        R[f"aptas_{crit}"] = (f"{n(linha('horária', 'base', f'Classificação apta - critério {crit}')['pct_apta_estacao'])} × "
                              f"{n(linha('horária', 'base', f'Classificação apta - critério {crit}')['pct_apta_era5'])}")
        x = linha("mensal", "base", f"Horas aptas (meses) - critério {crit}")
        R[f"mensal_{crit}"] = f"{n(x['vies'], 1, True)} h / {n(x['rmse'], 1)} / {n(x['r'], 2)} (n={int(x['n'])})"
        x = linha("período de fungicidas", "base", f"Horas aptas (safras) - critério {crit}")
        R[f"fung_{crit}"] = f"{n(x['vies'], 1, True)} h / {n(x['rmse'], 1)} / {n(x['r'], 2)} (n={int(x['n'])})"
        for esc, k in (("mensal", "ano"), ("período de fungicidas", "fung")):
            x = linha(esc, "base", f"Spearman da ordem das estações - critério {crit}")
            R[f"sp_{k}_{crit}"] = f"{n(x['r_spearman'], 2, True)} (p={n(x['p_spearman'], 2)})"
    R["kappa_B_chuva"] = n(linha("horária", "ERA5 chuva<0,2 mm=0", "Classificação apta - critério B")["kappa"], 3)
    R["kappa_A_chuva"] = n(linha("horária", "ERA5 chuva<0,2 mm=0", "Classificação apta - critério A")["kappa"], 3)

    t13b = ler(d, "T13b_decomposicao_discrepancia")
    b = t13b[(t13b["criterio"] == "A") & (t13b["cenario"] == "base") & t13b["mes"].isin(MES)]
    R["decomp"] = ", ".join(f"{c} {n(b[c].mean(), 1, True)}" for c in
                            ["vento", "chuva", "UR", "DeltaT", "temperatura", "total"])
    t13 = ler(d, "T13_horas_aptas_estacao_vs_era5")
    r = t13[(t13["codigo"] == "TODAS") & (t13["criterio"] == "A") & (t13["cenario"] == "base")].set_index("mes")
    R["razao_mes"] = ", ".join(f"{MES[m]} {n(r.loc[m, 'razao_estacao_era5'], 2)}" for m in MES if m in r.index)

    c = ler(d, "T13c_fases_estacao_vs_era5")
    cm = c[c["codigo"] == "TODAS"].set_index("fase")
    R["t13c_media"] = "; ".join(f"{FASE_CURTA[f]} {n(cm.loc[f, 'pct_aptas_estacao'])} × {n(cm.loc[f, 'pct_aptas_era5'])} "
                                f"(razão {n(cm.loc[f, 'razao_estacao_era5'], 2)})" for f in FASES)
    ce = c[c["codigo"] != "TODAS"]
    R["t13c_est"] = {f: "; ".join(f"{r.codigo} {n(r.pct_aptas_estacao)}×{n(r.pct_aptas_era5)}"
                                  for r in ce[ce["fase"] == f].itertuples()) for f in FASES}
    t13d = ler(d, "T13d_noturno_estacao_vs_era5")
    dd = t13d[t13d["codigo"] == "TODAS"].iloc[0]
    R["t13d"] = (f"calmaria noturna (u2<3 km/h) {n(dd['pct_vento_lt3_noite_estacao'])} % × "
                 f"{n(dd['pct_vento_lt3_noite_era5'])} %; aptas à noite {n(dd['pct_aptas_noite_estacao'])} % × "
                 f"{n(dd['pct_aptas_noite_era5'])} %; aptas de dia {n(dd['pct_aptas_dia_estacao'])} % × "
                 f"{n(dd['pct_aptas_dia_era5'])} %; ganho A1 {n(dd['ganho_A1_h_por_safra_estacao'], 0)} × "
                 f"{n(dd['ganho_A1_h_por_safra_era5'], 0)} h/safra")
    t13e = ler(d, "T13e_horas_ajustadas").set_index("fase")
    R["t13e"] = "; ".join(f"{FASE_CURTA[f]} {n(t13e.loc[f, 'pct_tempo_apto_era5'])} → "
                          f"{n(t13e.loc[f, 'pct_tempo_apto_ajustado'])} %" for f in FASES)

    # --- ERA5: período de fungicidas
    t2 = ler(d, "T2_dias_aptos_fase")
    pr = t2[(t2["municipio"] == ESTADO)].set_index("fase")
    f = pr.loc[FUNG]
    R["fung_h"] = f"{n(f['horas_aptas_media'], 0)} h (DP {n(f['horas_aptas_dp'], 0)})"
    R["fung_pct"] = f"{n(f['pct_tempo_apto'])} %"
    R["fung_dias"] = f"{n(f['dias_aptos_media'])} de {n(f['dias_fase'], 0)}"
    R["fase_pct"] = "; ".join(f"{FASE_CURTA[x]} {n(pr.loc[x, 'pct_tempo_apto'])} %" for x in FASES)
    mun = t2[(~t2["municipio"].str.contains("média")) & (t2["fase"] == FUNG)].set_index("municipio")["pct_tempo_apto"]
    R["fung_mais_menos"] = (f"mais favorável {mun.idxmax()} {n(mun.max())} %; "
                            f"menos favorável {mun.idxmin()} {n(mun.min())} %")
    t1 = ler(d, "T1_horas_aptas_decendio")
    p1 = t1[t1["municipio"] == ESTADO].sort_values("media")
    R["piores_dec"] = ", ".join(f"{r.decendio_rotulo} {n(r.media)} h" for r in p1.head(3).itertuples())
    fdec = p1[p1["mes"].isin([12, 1, 2]) & ~((p1["mes"] == 12) & (p1["decendio"] < 2))]
    R["piores_dec_fung"] = ", ".join(f"{r.decendio_rotulo} {n(r.media)} h" for r in fdec.head(3).itertuples())
    t3 = ler(d, "T3_motivos_inaptidao")
    for fase, k in ((FUNG, "mot_fung"), (DESS, "mot_dess")):
        x = t3[(t3["regiao"] == ESTADO) & (t3["fase"] == fase)].sort_values("pct_motivo_principal", ascending=False)
        R[k] = ", ".join(f"{r.motivo} {n(r.pct_motivo_principal)} %" for r in x.head(3).itertuples())
    t4 = ler(d, "T4_noturno")
    x = t4[(~t4["municipio"].str.contains("média")) & (t4["fase"] == FUNG)].set_index("municipio")["pct_noturno"]
    R["noturno"] = f"mín. {n(x.min())} % ({x.idxmin()}); máx. {n(x.max())} % ({x.idxmax()})"

    t5 = ler(d, "T5_markov")
    R["markov_dep"] = f"{int(t5['dependencia_sig_5pct'].sum())} de {len(t5)} ({n(100 * t5['dependencia_sig_5pct'].mean())} %)"
    g = t5.groupby(["mes", "decendio", "decendio_rotulo"])[["P_F", "P_F_dado_F", "P_F_dado_NF"]].mean().reset_index()
    w = g.sort_values("P_F").iloc[0]
    R["markov_pior"] = (f"{w.decendio_rotulo}: P(apto) {n(w.P_F, 2)}; P(apto|ontem apto) {n(w.P_F_dado_F, 2)}; "
                        f"P(apto|ontem inapto) {n(w.P_F_dado_NF, 2)} (média dos municípios)")
    t6 = ler(d, "T6_mann_kendall")
    s6 = t6[t6["municipio"] == ESTADO].set_index("fase")
    R["sen"] = "; ".join(f"{FASE_CURTA[x]} {n(s6.loc[x, 'sen_h_por_decada'], 1, True)} h/déc (p={n(s6.loc[x, 'p_valor'], 2)})"
                         for x in FASES)
    m6 = t6[(~t6["municipio"].str.contains("média")) & (t6["fase"] == FUNG)]
    R["sen_mun_fung"] = (f"{int((m6['sen_h_por_decada'] > 0).sum())} de {len(m6)} positivas; "
                         f"{int(m6['significativo_5pct'].sum())} significativas")

    t7 = ler(d, "T7_clusters")
    t7b = ler(d, "T7b_silhueta_k")
    kb = t7b[t7b["escolhido"]].iloc[0]
    R["k"] = f"k = {int(kb['k'])}, silhueta {n(kb['silhueta_media'], 3)}"
    gm = t7.groupby("grupo")["horas_aptas_set_abr"]
    ordem = gm.mean().sort_values().index
    rot = {ordem[0]: "restritivo", ordem[-1]: "favorável"}
    R["grupos"] = {rot.get(gq, gq): (f"{len(x)} municípios: {', '.join(x['municipio'])}; "
                                     f"{n(x['horas_aptas_set_abr'].min(), 0)}–{n(x['horas_aptas_set_abr'].max(), 0)} h "
                                     f"(média {n(x['horas_aptas_set_abr'].mean(), 0)} h set–abr)")
                   for gq, x in t7.groupby("grupo")}

    t2b = ler(d, "T2b_horas_aptas_epoca")
    e = t2b[(t2b["municipio"] == ESTADO) & (t2b["fase"] == "Florescimento e enchimento")].set_index("epoca")
    R["epoca"] = f"25/09: {n(e.loc['25/09', 'horas_aptas_media'], 0)} h; 15/11: {n(e.loc['15/11', 'horas_aptas_media'], 0)} h"
    t2c = ler(d, "T2c_melhor_epoca_fungicida")
    m2 = t2c[~t2c["municipio"].str.contains("média")].set_index("municipio")
    R["ganho_epoca"] = (f"mín. {n(m2['ganho_melhor_vs_pior_h'].min())} h ({m2['ganho_melhor_vs_pior_h'].idxmin()}); "
                        f"máx. {n(m2['ganho_melhor_vs_pior_h'].max())} h ({m2['ganho_melhor_vs_pior_h'].idxmax()})")
    vc = m2["melhor_epoca_por_p20"].value_counts()
    R["p20"] = "; ".join(f"{ep}: {c} municípios" + f" ({', '.join(m2.index[m2['melhor_epoca_por_p20'] == ep])})" for ep, c in vc.items())

    t8b = ler(d, "T8b_C1_corrigido").set_index("alternativa")
    R["t8b"] = t8b
    t10b = ler(d, "T10b_cenarios_topsis")
    R["t10b"] = t10b
    t10e = ler(d, "T10_era5")
    R["t10e"] = t10e
    t11 = ler(d, "T11_sensibilidade")
    t11 = t11[t11["versao_C1"] == "corrigido_estacoes"] if "versao_C1" in t11 else t11
    R["t11"] = ("não" if not t11["primeiro_mudou"].any() else
                "sim: " + ", ".join(f"{r.criterio} {r.variacao_pct:+d}% → {r.primeiro}"
                                    for r in t11[t11["primeiro_mudou"]].itertuples()))
    R["t13f"] = ler(d, "T13f_estabilidade_periodos")
    return R


CONCLUSOES = """- **Tendência no período de fungicidas deixou de ser significativa.** Na v3, o Paraná (média) tinha
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
"""


def ranking(t10b: pd.DataFrame, cen: str, reg: str) -> str:
    x = t10b[(t10b["cenario"] == cen) & (t10b["regiao"] == reg)].sort_values("posicao")
    if "versao_C1" in x:
        x = x[x["versao_C1"] == "corrigido_estacoes"] if (x["versao_C1"] == "corrigido_estacoes").any() else x
    return " > ".join(f"{r.alternativa} ({n(r.CC, 3)})" for r in x.itertuples())


def main() -> None:
    a, b = metricas(V3), metricas(V4)
    L = []
    add = L.append
    add("# RESUMO V4 — janelas de pulverização na soja do Paraná\n")
    add("**v3**: ERA5 1995–2024 (safras 1995/96–2023/24, 29 safras); validação INMET 2010–2016 (anos civis "
        "completos, 6 estações).  ")
    add("**v4**: ERA5 safras 2000/01–2025/26 (1º/set/2000 a 30/abr/2026, 26 safras); validação INMET em todo o "
        "período disponível nos arquivos locais, só set–abr das estação-safras válidas (≥ 70 % de horas válidas "
        "em T, UR e vento). Critérios, limiares, fases, municípios, notas C2–C5, pesos AHP e cenários: iguais.  ")
    add("Gerado por `src/resumo_v4.py` a partir de `outputs_v3_1995-2024/tables` e `outputs/tables`. "
        "Formato \"estação × ERA5\" = estação primeiro. Viés = ERA5 − estação.\n")

    def tab(titulo, linhas):
        add(f"\n## {titulo}\n")
        add("| Indicador | v3 (ERA5 1995–2024; INMET 2010–2016) | v4 (2000–2026) |")
        add("|---|---|---|")
        for rot, k in linhas:
            va = k(a) if callable(k) else a.get(k)
            vb = k(b) if callable(k) else b.get(k)
            add(f"| {rot} | {'–' if va is None else va} | {'–' if vb is None else vb} |")

    tab("1. Dados e estações", [
        ("Período da validação", "periodo_val"),
        ("Nº de estações usadas", "n_est"),
        ("Nº de estações nas médias", lambda R: R["n_media"] if R["n_media"] is not None else "5 (B803 fora)"),
        ("Estação-safras válidas (set–abr, ≥ 70 %)", "n_est_safras_validas"),
        ("Estação-safras no período de fungicidas (T12)", "n_est_safras_fung"),
        ("Estações (distância ao município)", "lista_est"),
        ("Registros horários ERA5 por município", "registros_mun"),
        ("Período bruto ERA5 baixado", "periodo_raw"),
        ("Valores fora dos limites físicos — ERA5", "outliers_era5"),
        ("Valores fora dos limites físicos — INMET bruto", "outliers_inmet"),
        ("% de falhas INMET por variável, do 1º ao último registro (média das estações)", "falhas_inmet"),
        ("% de falhas INMET nas estação-safras válidas (set–abr)", "falhas_validas"),
    ])
    tab("2. Validação horária (viés / RMSE / r)", [
        ("Temperatura (°C)", "h_T"), ("UR (%)", "h_UR"), ("Delta T (°C)", "h_dT"),
        ("Vento a 10 m (km/h)", "h_u10"),
        ("% horas com vento OK, crit. A (estação × ERA5)", "cond_vento_A"),
        ("% horas com chuva OK, crit. A", "cond_chuva_A"),
        ("% horas com vento OK, crit. B", "cond_vento_B"),
        ("% horas com chuva OK, crit. B", "cond_chuva_B"),
        ("% horas aptas, crit. A", "aptas_A"), ("% horas aptas, crit. B", "aptas_B"),
        ("Kappa A", "kappa_A"), ("Kappa A (chuva ERA5 < 0,2 = 0)", "kappa_A_chuva"),
        ("Kappa B", "kappa_B"), ("Kappa B (chuva ERA5 < 0,2 = 0)", "kappa_B_chuva"),
    ])
    tab("3. Validação agregada (viés h / RMSE / r)", [
        ("Horas aptas mensais, A", "mensal_A"), ("Horas aptas mensais, B", "mensal_B"),
        ("Horas aptas por safra no período de fungicidas, A", "fung_A"),
        ("Horas aptas por safra no período de fungicidas, B", "fung_B"),
        ("Spearman entre estações, ano todo (mensal), A", "sp_ano_A"),
        ("Spearman entre estações, ano todo (mensal), B", "sp_ano_B"),
        ("Spearman entre estações, fungicidas, A", "sp_fung_A"),
        ("Spearman entre estações, fungicidas, B", "sp_fung_B"),
        ("Decomposição (estação − ERA5), crit. A, h/mês, média set–abr", "decomp"),
        ("Razão estação/ERA5 por mês, crit. A", "razao_mes"),
    ])
    tab("4. T13c, T13d e T13e", [
        ("T13c — % aptas por fase, média (estação × ERA5)", "t13c_media"),
        *[(f"T13c — {FASE_CURTA[f]}, por estação", (lambda f: lambda R: R["t13c_est"][f])(f)) for f in FASES],
        ("T13d — fungicidas, noite × dia", "t13d"),
        ("T13e — Paraná, % do tempo apto ERA5 bruto → ajustado", "t13e"),
    ])
    tab("5. ERA5 — período de fungicidas e fases (Paraná, média)", [
        ("Horas aptas por safra (média e DP)", "fung_h"), ("% do tempo apto", "fung_pct"),
        ("Dias aptos", "fung_dias"), ("% do tempo apto por fase", "fase_pct"),
        ("Piores decêndios (set–abr)", "piores_dec"), ("Piores decêndios do período de fungicidas", "piores_dec_fung"),
        ("Motivos de inaptidão — fungicidas (motivo principal)", "mot_fung"),
        ("Motivos de inaptidão — dessecação", "mot_dess"),
        ("Fração noturna das horas aptas em fungicidas", "noturno"),
        ("% apto em fungicidas: município mais e menos favorável", "fung_mais_menos"),
    ])
    tab("6. Markov, tendências e agrupamento", [
        ("Markov: pares município-decêndio dependentes (qui², 5 %)", "markov_dep"),
        ("Markov: pior decêndio", "markov_pior"),
        ("Sen/Mann-Kendall, Paraná (média)", "sen"),
        ("Sen nos municípios, fungicidas", "sen_mun_fung"),
        ("k-means", "k"),
        ("Grupo restritivo", lambda R: R["grupos"].get("restritivo")),
        ("Grupo favorável", lambda R: R["grupos"].get("favorável")),
    ])
    tab("7. Épocas de semeadura (fase de florescimento e enchimento, Paraná)", [
        ("Horas aptas por época", "epoca"),
        ("Ganho melhor × pior época por município", "ganho_epoca"),
        ("Melhor época pelo P20, por município", "p20"),
    ])

    add("\n## 8. T8b — C1 corrigido pelas estações (h/safra)\n")
    add("| Alt. | Estação v3 | ERA5 mesmos pontos v3 | Razão v3 | Estação v4 | ERA5 mesmos pontos v4 | Razão v4 | "
        "PR orig.→corr. v3 | PR orig.→corr. v4 | Oeste orig.→corr. v3 | Oeste orig.→corr. v4 |")
    add("|---|---|---|---|---|---|---|---|---|---|---|")
    for alt in ALTS:
        x, y = a["t8b"].loc[alt], b["t8b"].loc[alt]
        add(f"| {alt} {ALTS[alt]} | {n(x.ganho_estacao_h_safra)} | {n(x.ganho_era5_mesmos_pontos_h_safra)} | "
            f"{n(x.razao_estacao_era5, 2)} | {n(y.ganho_estacao_h_safra)} | {n(y.ganho_era5_mesmos_pontos_h_safra)} | "
            f"{n(y.razao_estacao_era5, 2)} | {n(x.C1_original_PR)}→{n(x.C1_corrigido_PR)} | "
            f"{n(y.C1_original_PR)}→{n(y.C1_corrigido_PR)} | {n(x.C1_original_Oeste)}→{n(x.C1_corrigido_Oeste)} | "
            f"{n(y.C1_original_Oeste)}→{n(y.C1_corrigido_Oeste)} |")

    add("\n## 9. TOPSIS (CC) com C1 corrigido — 4 cenários de pesos\n")
    add("| Cenário | Região | v3 | v4 |")
    add("|---|---|---|---|")
    for cen in ["base_AHP", "pequeno_produtor", "ambiental_saude", "pesos_iguais"]:
        for reg in (ESTADO, OESTE):
            add(f"| {cen} | {reg} | {ranking(a['t10b'], cen, reg)} | {ranking(b['t10b'], cen, reg)} |")
    add("\n| Teste | v3 | v4 |")
    add("|---|---|---|")
    for reg in (ESTADO, OESTE):
        def r_era(R, reg=reg):
            t = R["t10e"]
            t = t[t["regiao"] == reg].sort_values("ranking")
            return " > ".join(f"{r.alternativa} ({n(r.CC, 3)})" for r in t.itertuples())
        add(f"| Ranking só ERA5 (C1 sem correção), base, {reg} | {r_era(a)} | {r_era(b)} |")
    add(f"| 1º lugar muda em algum teste de ±50 % no peso (Paraná, C1 corrigido)? | {a['t11']} | {b['t11']} |")

    add("\n## 10. T13f — estabilidade da validação por período (só v4)\n")
    f = b["t13f"]
    f = f[f["codigo"] == "TODAS"].set_index("periodo")
    cols = [("Estações (n)", lambda r: r["estacao"].split("(")[1].rstrip(")")),
            ("Estação-safras", lambda r: n(r["n_estacao_safras"], 0)),
            ("Viés do vento a 10 m (km/h)", lambda r: n(r["vies_vento10_kmh"], 2, True)),
            ("Calmaria noturna em fungicidas, estação × ERA5 (%)",
             lambda r: f"{n(r['pct_calmaria_noturna_fung_estacao'])} × {n(r['pct_calmaria_noturna_fung_era5'])}"),
            ("Kappa A", lambda r: n(r["kappa_A"], 3)),
            *[(f"Razão estação/ERA5 — {FASE_CURTA[x]}", (lambda x: lambda r: n(r[f"razao_{x}"], 2))(x)) for x in FASES]]
    add("| Indicador | " + " | ".join(f.index) + " |")
    add("|---|" + "---|" * len(f))
    for rot, fn in cols:
        add(f"| {rot} | " + " | ".join(fn(f.loc[p]) for p in f.index) + " |")
    add("\nPeríodos pelo ano de término da safra (2000–2009 = safras 2000/01–2008/09; 2010–2016 = 2009/10–2015/16; "
        "2017–2026 = 2016/17–2025/26). O conjunto de estações muda entre períodos (antes de 2006 não há estação "
        "automática a até 30 km dos municípios).")

    add("\n## 11. O que mudou de conclusão em relação à v3\n")
    add(CONCLUSOES)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"salvo: {OUT}")


if __name__ == "__main__":
    main()
