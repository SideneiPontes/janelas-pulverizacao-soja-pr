"""Indicadores horários de aptidão para pulverização terrestre em soja (PR).

Entrada : data/raw/<cod_ibge>_<municipio>.parquet  (ERA5 horário, Open-Meteo)
Saídas  : data/processed/indicadores_horarios.parquet
          data/processed/indicadores_diarios.parquet
          outputs/tables/T0..T4, T2b, T2c (+ versões _critB) e tabelas_indicadores.xlsx

Uso:  python src/indicadores.py

Convenções adotadas (documentar na metodologia)
------------------------------------------------
* Hora: cada registro horário t representa a hora de aplicação [t, t+1h).
  Variáveis instantâneas (T, UR, vento) são as do instante t. No Open-Meteo, a
  precipitação do registro t é o acumulado da hora ANTERIOR (t-1h, t]; por isso:
    - chuva "na hora"            = precipitation[t+1h]           (cobre [t, t+1h))
    - chuva "nas 2 h seguintes"  = precipitation[t+2h] + [t+3h]  (cobre [t+1h, t+3h))
  A mesma convenção é usada no critério B.
* Horário local America/Sao_Paulo (inclui horário de verão até 2019). Dia, hora
  do dia, decêndio e fases usam a data/hora LOCAL.
* Vento a 2 m (FAO-56, Allen et al., 1998, eq. 47): u2 = u10 * 4.87 / ln(67.8*10 - 5.42)
  (fator ~0,748; independe da unidade).
* Bulbo úmido: Stull (2011), válido para UR 5-99 % e T -20 a 50 °C.
* Janela: >= 2 horas aptas consecutivas. Dia apto: >= 1 janela inteiramente entre
  06h e 20h locais (horas que começam de 06h a 19h).
* Hora noturna: is_day == 0 no instante t.
* Motivo principal de inaptidão: primeiro critério violado na ordem
  MOTIVOS_A / MOTIVOS_B abaixo. A tabela T3 traz também a contagem de TODOS os
  critérios violados (soma > 100 %).
* Médias regionais (Paraná = 16 originais; Oeste = 8 do zoneamento + Cascavel e Toledo)
  são calculadas por célula ERA5: municípios na mesma célula são promediados entre si
  antes da média regional (cada célula pesa 1).
* Fase de fungicidas: 16/dez até o último dia de fevereiro (inclui 29/fev).
* Safra Y/Y+1: 1/set de Y a 30/abr de Y+1; safras 2000/01 a 2025/26.
* Épocas de semeadura: ciclo de 120 dias, fases 15:30:60:35 reescaladas para 120 d
  -> inicial [0,13), desenvolvimento [13,39), florescimento/enchimento [39,90),
  maturação [90,120) DAS; dessecação pré-semeadura [-20, 0) DAS.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
TAB = ROOT / "outputs" / "tables"
TZ = "America/Sao_Paulo"
ESTADO = "Paraná (média)"
OESTE = "Oeste (média)"
# Média do Paraná: só os 16 municípios originais (grupo_origem == "estado").
# Média do Oeste: os 8 do zoneamento + estes 2 originais do Oeste (polos regionais
# mais próximos dos novos; Assis Chateaubriand fica na transição para o Noroeste).
OESTE_ORIGINAIS = ["Cascavel", "Toledo"]
AGREG: dict[str, list[str]] = {}
# Célula da grade ERA5 (0,25°) de cada município. As médias regionais são feitas
# POR CÉLULA: municípios na mesma célula (ex.: Matelândia e Medianeira) são primeiro
# promediados entre si e contam como uma única amostra.
CELULA: dict[str, str] = {}


def configurar_agregados(muns_df: pd.DataFrame) -> dict[str, list[str]]:
    AGREG.clear()
    AGREG[ESTADO] = muns_df.loc[muns_df["grupo_origem"] == "estado", "municipio"].tolist()
    AGREG[OESTE] = (muns_df.loc[muns_df["grupo_origem"] == "zoneamento_oeste", "municipio"]
                    .tolist() + OESTE_ORIGINAIS)
    CELULA.clear()
    for _, r in muns_df.iterrows():
        f = next(RAW.glob(f"{r.cod_ibge}_*.parquet"))
        g = pd.read_parquet(f, columns=["grid_lat", "grid_lon"]).iloc[0]
        CELULA[r.municipio] = f"{g.grid_lat:.2f},{g.grid_lon:.2f}"
    return AGREG


def pesos_celula(membros: list[str]) -> pd.Series:
    """Peso de cada município = 1 / nº de membros na mesma célula ERA5."""
    cel = pd.Series({m: CELULA[m] for m in membros})
    return 1.0 / cel.map(cel.value_counts())


def media_por_celula(df: pd.DataFrame, chaves: list[str], valores: list[str]) -> pd.DataFrame:
    """Média entre células: promedia municípios da mesma célula e depois entre células."""
    d = df.assign(_cel=df["municipio"].astype(str).map(CELULA))
    por_cel = d.groupby(chaves + ["_cel"], observed=True)[valores].mean()
    return por_cel.groupby(level=chaves, observed=True).mean().reset_index()

FATOR_U2 = 4.87 / np.log(67.8 * 10 - 5.42)

MOTIVOS_A = ["DeltaT baixo", "DeltaT alto", "vento fraco", "vento forte",
             "temperatura", "UR", "chuva", "chuva logo depois"]
MOTIVOS_B = ["temperatura", "UR", "vento fraco", "vento forte", "chuva"]
CRITERIOS = {"A": MOTIVOS_A, "B": MOTIVOS_B}

FASES_OP = ["Dessecação pré-semeadura", "Pós-emergência",
            "Fungicidas (R1-R5)", "Pré-colheita e colheita"]
FASES_EP = [("Dessecação pré-semeadura", -20, 0), ("Inicial", 0, 13),
            ("Desenvolvimento", 13, 39), ("Florescimento e enchimento", 39, 90),
            ("Maturação", 90, 120)]
EPOCAS = [(9, 25), (10, 5), (10, 15), (10, 25), (11, 5), (11, 15)]
SAFRAS = range(2000, 2026)  # ano de início da safra (2000/01 a 2025/26)
N_SAFRAS = len(SAFRAS)
ROTULO_SAFRAS = f"{SAFRAS[0]}/{str(SAFRAS[0] + 1)[2:]} a {SAFRAS[-1]}/{str(SAFRAS[-1] + 1)[2:]}"
PERIODO_ERA5 = f"{SAFRAS[0]}–{SAFRAS[-1] + 1}"  # rótulo das figuras (safras set/2000-abr/2026)
MESES_SAFRA = [9, 10, 11, 12, 1, 2, 3, 4]
NOME_MES = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
            7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}


# ----------------------------------------------------------------------------
# Cálculos horários
# ----------------------------------------------------------------------------
def bulbo_umido_stull(t: np.ndarray, ur: np.ndarray) -> np.ndarray:
    return (t * np.arctan(0.151977 * np.sqrt(ur + 8.313659))
            + np.arctan(t + ur) - np.arctan(ur - 1.676331)
            + 0.00391838 * ur ** 1.5 * np.arctan(0.023101 * ur)
            - 4.686035)


def janelas(apta: pd.Series, hora_local: pd.Series) -> pd.Series:
    """Horas pertencentes a sequências >= 2 h aptas entre 06h e 20h locais."""
    m = apta & hora_local.between(6, 19)
    run = (m != m.shift()).cumsum()
    tam = m.groupby(run).transform("sum")
    return m & (tam >= 2)


def indicadores_horarios(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("time_utc").reset_index(drop=True)
    if not (df["time_utc"].diff().dropna() == pd.Timedelta(hours=1)).all():
        raise ValueError(f"Série horária com buracos: {df['municipio'].iloc[0]}")

    t, ur = df["temperature_2m"], df["relative_humidity_2m"]
    out = pd.DataFrame({
        "cod_ibge": df["cod_ibge"], "municipio": df["municipio"],
        "time_utc": df["time_utc"], "time_local": df["time_local"],
    })
    out["data"] = df["time_local"].dt.tz_localize(None).dt.normalize()
    out["hora_local"] = df["time_local"].dt.hour.astype("int8")
    out["is_day"] = df["is_day"].astype("int8")
    out["T"], out["UR"] = t, ur
    out["u10"] = df["wind_speed_10m"]
    out["u2"] = df["wind_speed_10m"] * FATOR_U2
    out["Tbu"] = bulbo_umido_stull(t.to_numpy(), ur.to_numpy())
    out["deltaT"] = t - out["Tbu"]
    p = df["precipitation"]
    out["chuva_hora"] = p.shift(-1)
    out["chuva_2h_seg"] = p.shift(-2) + p.shift(-3)
    avaliavel = out["chuva_2h_seg"].notna()

    # Critério A (proposto)
    vA = {
        "DeltaT baixo": out["deltaT"] < 2,
        "DeltaT alto": out["deltaT"] > 8,
        "vento fraco": out["u2"] < 3,
        "vento forte": out["u2"] > 10,
        "temperatura": t >= 30,
        "UR": ur < 50,
        "chuva": out["chuva_hora"] != 0,
        "chuva logo depois": out["chuva_2h_seg"] >= 1,
    }
    # Critério B (Silva, Oliveira e Gandolfo, 2018)
    vB = {
        "temperatura": t >= 30,
        "UR": ur <= 55,
        "vento fraco": out["u10"] < 3,
        "vento forte": out["u10"] > 12,
        "chuva": out["chuva_hora"] >= 0.2,
    }
    for crit, viol in (("A", vA), ("B", vB)):
        viol = {k: v.fillna(True) for k, v in viol.items()}
        qualquer = np.logical_or.reduce(list(viol.values()))
        apta = pd.Series(~qualquer & avaliavel, index=out.index)
        out[f"apta_{crit}"] = apta
        out[f"janela_{crit}"] = janelas(apta, out["hora_local"])
        motivo = np.select(list(viol.values()), list(viol.keys()), default="")
        out[f"motivo_{crit}"] = pd.Categorical(np.where(apta, "", motivo))
        for k, v in viol.items():
            out[f"v{crit}_{k}"] = v & ~apta
    return out


# ----------------------------------------------------------------------------
# Agregação diária
# ----------------------------------------------------------------------------
def diario(h: pd.DataFrame) -> pd.DataFrame:
    g = {"horas": ("T", "size")}
    cols = h.copy()
    for crit, motivos in CRITERIOS.items():
        a = cols[f"apta_{crit}"]
        cols[f"ad_{crit}"] = a & (cols["is_day"] == 1)
        cols[f"an_{crit}"] = a & (cols["is_day"] == 0)
        cols[f"in_{crit}"] = ~a
        g |= {
            f"horas_aptas_{crit}": (f"apta_{crit}", "sum"),
            f"horas_aptas_dia_{crit}": (f"ad_{crit}", "sum"),
            f"horas_aptas_noite_{crit}": (f"an_{crit}", "sum"),
            f"horas_janela_{crit}": (f"janela_{crit}", "sum"),
            f"dia_apto_{crit}": (f"janela_{crit}", "any"),
            f"horas_inaptas_{crit}": (f"in_{crit}", "sum"),
        }
        for k in motivos:
            cols[f"p{crit}_{k}"] = cols[f"motivo_{crit}"] == k
            g[f"viol_{crit}_{k}"] = (f"v{crit}_{k}", "sum")
            g[f"princ_{crit}_{k}"] = (f"p{crit}_{k}", "sum")
    d = cols.groupby(["cod_ibge", "municipio", "data"], observed=True).agg(**g).reset_index()
    for crit in CRITERIOS:
        d[f"dia_apto_{crit}"] = d[f"dia_apto_{crit}"].astype(int)
    return d


def calendario(d: pd.DataFrame) -> pd.DataFrame:
    m, dia, ano = d["data"].dt.month, d["data"].dt.day, d["data"].dt.year
    d["mes"], d["ano"] = m, ano
    d["safra_ini"] = np.where(m >= 9, ano, np.where(m <= 4, ano - 1, -1))
    d["decendio"] = np.where(dia <= 10, 1, np.where(dia <= 20, 2, 3))
    md = m * 100 + dia
    d["fase"] = np.select(
        [(md >= 901) & (md <= 1031), (md >= 1101) & (md <= 1215),
         (md >= 1216) | (md <= 229), (md >= 301) & (md <= 430)],
        FASES_OP, default="")
    d = d[d["safra_ini"].isin(SAFRAS)].copy()
    d["safra"] = d["safra_ini"].astype(str) + "/" + (d["safra_ini"] + 1).astype(str).str[-2:]
    return d


# ----------------------------------------------------------------------------
# Tabelas
# ----------------------------------------------------------------------------
def com_estado(por_safra: pd.DataFrame, chaves: list[str], valores: list[str]) -> pd.DataFrame:
    """Acrescenta as médias regionais (AGREG): média entre células ERA5 em cada safra."""
    partes = [por_safra]
    for nome, membros in AGREG.items():
        est = media_por_celula(por_safra[por_safra["municipio"].isin(membros)],
                               chaves + ["safra"], valores)
        est["municipio"] = nome
        partes.append(est)
    return pd.concat(partes, ignore_index=True)


def ordem_mun(df: pd.DataFrame, muns: list[str]) -> pd.DataFrame:
    df["municipio"] = pd.Categorical(df["municipio"], muns + list(AGREG), ordered=True)
    return df


def tabela_T1(d, crit, muns):
    s = (d.groupby(["municipio", "safra", "mes", "decendio"])[f"horas_aptas_{crit}"]
         .sum().reset_index())
    s = com_estado(s, ["mes", "decendio"], [f"horas_aptas_{crit}"])
    t = (s.groupby(["municipio", "mes", "decendio"], observed=True)[f"horas_aptas_{crit}"]
         .agg(media="mean", dp="std").reset_index())
    t["ordem"] = t["mes"].map({m: i for i, m in enumerate(MESES_SAFRA)}) * 3 + t["decendio"]
    t["decendio_rotulo"] = t["mes"].map(NOME_MES) + "-" + t["decendio"].astype(str)
    t = ordem_mun(t, muns).sort_values(["municipio", "ordem"])
    return t[["municipio", "decendio_rotulo", "mes", "decendio", "media", "dp"]].round(2)


def tabela_T2(d, crit, muns):
    dd = d[d["fase"] != ""]
    s = dd.groupby(["municipio", "safra", "fase"]).agg(
        dias_fase=("data", "size"), horas_fase=("horas", "sum"),
        dias_aptos=(f"dia_apto_{crit}", "sum"),
        horas_aptas=(f"horas_aptas_{crit}", "sum")).reset_index()
    s = com_estado(s, ["fase"], ["dias_fase", "horas_fase", "dias_aptos", "horas_aptas"])
    s["pct_tempo_apto"] = 100 * s["horas_aptas"] / s["horas_fase"]
    s["pct_dias_aptos"] = 100 * s["dias_aptos"] / s["dias_fase"]
    t = s.groupby(["municipio", "fase"], observed=True).agg(
        dias_fase=("dias_fase", "mean"),
        dias_aptos_media=("dias_aptos", "mean"), dias_aptos_dp=("dias_aptos", "std"),
        horas_aptas_media=("horas_aptas", "mean"), horas_aptas_dp=("horas_aptas", "std"),
        pct_tempo_apto=("pct_tempo_apto", "mean"),
        pct_dias_aptos=("pct_dias_aptos", "mean")).reset_index()
    t["fase"] = pd.Categorical(t["fase"], FASES_OP, ordered=True)
    return ordem_mun(t, muns).sort_values(["municipio", "fase"]).round(2)


def tabela_T3(d, crit):
    """% das horas inaptas por motivo e fase, para cada média regional (AGREG)."""
    dd = d[d["fase"] != ""]
    motivos = CRITERIOS[crit]
    cols = ([f"horas_inaptas_{crit}"] + [f"viol_{crit}_{k}" for k in motivos]
            + [f"princ_{crit}_{k}" for k in motivos])
    linhas = []
    for regiao, membros in AGREG.items():
        sub = dd[dd["municipio"].isin(membros)]
        w = sub["municipio"].map(pesos_celula(membros))  # cada célula ERA5 pesa 1
        s = sub[cols].mul(w, axis=0).groupby(sub["fase"]).sum()
        for fase, r in s.iterrows():
            for k in motivos:
                linhas.append({
                    "regiao": regiao, "fase": fase, "motivo": k,
                    "pct_horas_inaptas_com_violacao": 100 * r[f"viol_{crit}_{k}"] / r[f"horas_inaptas_{crit}"],
                    "pct_motivo_principal": 100 * r[f"princ_{crit}_{k}"] / r[f"horas_inaptas_{crit}"],
                })
    t = pd.DataFrame(linhas)
    t["fase"] = pd.Categorical(t["fase"], FASES_OP, ordered=True)
    t["regiao"] = pd.Categorical(t["regiao"], list(AGREG), ordered=True)
    return t.sort_values(["regiao", "fase"], kind="stable").round(2)


def tabela_T4(d, crit, muns):
    dd = d[d["fase"] != ""]
    v = [f"horas_aptas_dia_{crit}", f"horas_aptas_noite_{crit}"]
    s = dd.groupby(["municipio", "safra", "fase"])[v].sum().reset_index()
    s = com_estado(s, ["fase"], v)
    t = s.groupby(["municipio", "fase"], observed=True)[v].mean().reset_index()
    t.columns = ["municipio", "fase", "horas_aptas_diurnas", "horas_aptas_noturnas"]
    t["pct_noturno"] = 100 * t["horas_aptas_noturnas"] / (
        t["horas_aptas_diurnas"] + t["horas_aptas_noturnas"])
    t["fase"] = pd.Categorical(t["fase"], FASES_OP, ordered=True)
    return ordem_mun(t, muns).sort_values(["municipio", "fase"]).round(2)


def tabela_T0(d_all, muns):
    """Horas aptas mensais (jan-dez), média 2004-2014, critérios A e B."""
    d = d_all[(d_all["ano"] >= 2004) & (d_all["ano"] <= 2014)]
    s = d.groupby(["municipio", "ano", "mes"]).agg(
        horas=("horas", "sum"), A=("horas_aptas_A", "sum"), B=("horas_aptas_B", "sum")
    ).reset_index()
    partes = [s]
    for nome, membros in AGREG.items():
        est = media_por_celula(s[s["municipio"].isin(membros)], ["ano", "mes"], ["horas", "A", "B"])
        est["municipio"] = nome
        partes.append(est)
    s = pd.concat(partes, ignore_index=True)
    t = s.groupby(["municipio", "mes"]).agg(
        horas_aptas_A=("A", "mean"), horas_aptas_B=("B", "mean"),
        horas_mes=("horas", "mean")).reset_index()
    t["pct_A"] = 100 * t["horas_aptas_A"] / t["horas_mes"]
    t["pct_B"] = 100 * t["horas_aptas_B"] / t["horas_mes"]
    t["razao_A_B"] = t["horas_aptas_A"] / t["horas_aptas_B"]
    t["mes_nome"] = t["mes"].map(NOME_MES)
    t = ordem_mun(t, muns).sort_values(["municipio", "mes"])
    return t[["municipio", "mes", "mes_nome", "horas_aptas_A", "horas_aptas_B",
              "pct_A", "pct_B", "razao_A_B"]].round(2)


def por_epoca(d_all: pd.DataFrame, crit: str) -> pd.DataFrame:
    """Horas e dias aptos por município x época x safra x fase fenológica."""
    partes = []
    for (m, dia) in EPOCAS:
        for y in SAFRAS:
            S = pd.Timestamp(year=y, month=m, day=dia)
            jan = d_all[(d_all["data"] >= S - pd.Timedelta(days=20))
                        & (d_all["data"] < S + pd.Timedelta(days=120))].copy()
            das = (jan["data"] - S).dt.days
            jan["fase"] = pd.cut(das, bins=[f[1] for f in FASES_EP] + [FASES_EP[-1][2]],
                                 right=False, labels=[f[0] for f in FASES_EP])
            g = jan.groupby(["municipio", "fase"], observed=True).agg(
                dias=("data", "size"), horas=("horas", "sum"),
                horas_aptas=(f"horas_aptas_{crit}", "sum"),
                dias_aptos=(f"dia_apto_{crit}", "sum")).reset_index()
            g["epoca"] = f"{dia:02d}/{m:02d}"
            g["safra"] = f"{y}/{str(y + 1)[-2:]}"
            partes.append(g)
    return pd.concat(partes, ignore_index=True)


def p20(x):
    return np.percentile(x, 20)


def tabela_T2b(e: pd.DataFrame, muns):
    e = com_estado(e, ["epoca", "fase"], ["dias", "horas", "horas_aptas", "dias_aptos"])
    e["pct_tempo_apto"] = 100 * e["horas_aptas"] / e["horas"]
    t = e.groupby(["municipio", "epoca", "fase"], observed=True).agg(
        horas_aptas_media=("horas_aptas", "mean"), horas_aptas_dp=("horas_aptas", "std"),
        horas_aptas_p20=("horas_aptas", p20),
        dias_aptos_media=("dias_aptos", "mean"), dias_aptos_dp=("dias_aptos", "std"),
        dias_aptos_p20=("dias_aptos", p20),
        pct_tempo_apto=("pct_tempo_apto", "mean")).reset_index()
    t["fase"] = pd.Categorical(t["fase"], [f[0] for f in FASES_EP], ordered=True)
    t["epoca"] = pd.Categorical(t["epoca"], [f"{d:02d}/{m:02d}" for m, d in EPOCAS], ordered=True)
    return ordem_mun(t, muns).sort_values(["municipio", "epoca", "fase"]).round(2)


def tabela_T2c(t2b: pd.DataFrame) -> pd.DataFrame:
    f = t2b[t2b["fase"] == "Florescimento e enchimento"].copy()
    linhas = []
    for mun, g in f.groupby("municipio", observed=True):
        g = g.sort_values("horas_aptas_media", ascending=False)
        melhor, pior = g.iloc[0], g.iloc[-1]
        linhas.append({
            "municipio": mun,
            "melhor_epoca": melhor["epoca"], "horas_aptas_media": melhor["horas_aptas_media"],
            "horas_aptas_p20": melhor["horas_aptas_p20"], "dias_aptos_media": melhor["dias_aptos_media"],
            "segunda_epoca": g.iloc[1]["epoca"], "horas_segunda": g.iloc[1]["horas_aptas_media"],
            "pior_epoca": pior["epoca"], "horas_pior": pior["horas_aptas_media"],
            "ganho_melhor_vs_pior_h": melhor["horas_aptas_media"] - pior["horas_aptas_media"],
            "melhor_epoca_por_p20": g.sort_values("horas_aptas_p20", ascending=False).iloc[0]["epoca"],
        })
    return pd.DataFrame(linhas).round(2)


# ----------------------------------------------------------------------------
def main() -> None:
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    muns_df = pd.read_csv(PROC / "municipios.csv", encoding="utf-8")
    muns = muns_df["municipio"].tolist()
    configurar_agregados(muns_df)
    for nome, membros in AGREG.items():
        print(f"  {nome}: {len(membros)} municípios")

    horarios, diarios = [], []
    for _, r in muns_df.iterrows():
        f = next(RAW.glob(f"{r.cod_ibge}_*.parquet"))
        h = indicadores_horarios(pd.read_parquet(f))
        diarios.append(diario(h))
        keep = ["cod_ibge", "municipio", "time_utc", "time_local", "hora_local", "is_day",
                "T", "UR", "u10", "u2", "Tbu", "deltaT", "chuva_hora", "chuva_2h_seg",
                "apta_A", "janela_A", "motivo_A", "apta_B", "janela_B", "motivo_B"]
        horarios.append(h[keep])
        print(f"  {r.municipio:22s} horas aptas A={h['apta_A'].mean() * 100:5.1f}%  "
              f"B={h['apta_B'].mean() * 100:5.1f}%  (ano todo)", flush=True)

    H = pd.concat(horarios, ignore_index=True)
    for c in ("municipio", "motivo_A", "motivo_B"):
        H[c] = H[c].astype("category")
    H.to_parquet(PROC / "indicadores_horarios.parquet", index=False)
    D_all = pd.concat(diarios, ignore_index=True)
    D_all["ano"], D_all["mes"] = D_all["data"].dt.year, D_all["data"].dt.month
    D_all.to_parquet(PROC / "indicadores_diarios.parquet", index=False)
    D = calendario(D_all.copy())
    assert D["safra"].nunique() == N_SAFRAS, D["safra"].nunique()

    TAB.mkdir(parents=True, exist_ok=True)
    tabelas = {}
    for crit in CRITERIOS:
        suf = "" if crit == "A" else "_critB"
        tabelas[f"T1_horas_aptas_decendio{suf}"] = tabela_T1(D, crit, muns)
        tabelas[f"T2_dias_aptos_fase{suf}"] = tabela_T2(D, crit, muns)
        tabelas[f"T3_motivos_inaptidao{suf}"] = tabela_T3(D, crit)
        tabelas[f"T4_noturno{suf}"] = tabela_T4(D, crit, muns)
        e = por_epoca(D_all, crit)
        t2b = tabela_T2b(e, muns)
        tabelas[f"T2b_horas_aptas_epoca{suf}"] = t2b
        tabelas[f"T2c_melhor_epoca_fungicida{suf}"] = tabela_T2c(t2b)
    tabelas["T0_comparacao_criterios"] = tabela_T0(D_all, muns)

    for nome, t in tabelas.items():
        t.to_csv(TAB / f"{nome}.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(TAB / "tabelas_indicadores.xlsx") as xw:
        for nome, t in sorted(tabelas.items()):
            t.to_excel(xw, sheet_name=nome[:31], index=False)

    # ---------------------------------------------------------------- resumo
    def titulo(s):
        print("\n" + "=" * 100 + f"\n{s}\n" + "=" * 100)

    T2 = tabelas["T2_dias_aptos_fase"]
    titulo(f"T2 - Critério A: % do tempo apto e dias aptos por fase (média {N_SAFRAS} safras)")
    print(T2.pivot(index="municipio", columns="fase", values="pct_tempo_apto").round(1).to_string())
    print("\nDias aptos (média) por fase:")
    print(T2.pivot(index="municipio", columns="fase", values="dias_aptos_media").round(1).to_string())
    T2B = tabelas["T2_dias_aptos_fase_critB"]
    titulo("T2_critB - Critério B: % do tempo apto por fase")
    print(T2B.pivot(index="municipio", columns="fase", values="pct_tempo_apto").round(1).to_string())

    T1 = tabelas["T1_horas_aptas_decendio"]
    titulo("T1 - Critério A: horas aptas por decêndio (média ± dp entre safras)")
    for reg in AGREG:
        e1 = T1[T1["municipio"] == reg]
        print(f"{reg}: " + " ".join(f"{r.decendio_rotulo}:{r.media:.0f}±{r.dp:.0f}"
                                    for r in e1.itertuples()))

    T3 = tabelas["T3_motivos_inaptidao"]
    for reg in AGREG:
        titulo(f"T3 - Critério A: % das horas inaptas por motivo ({reg})")
        t3 = T3[T3["regiao"] == reg]
        print("Com violação (cada critério contado; soma > 100%):")
        print(t3.pivot(index="motivo", columns="fase", values="pct_horas_inaptas_com_violacao")
              .reindex(MOTIVOS_A).round(1).to_string())
        print("\nMotivo principal (primeiro violado na ordem da lista; soma = 100%):")
        print(t3.pivot(index="motivo", columns="fase", values="pct_motivo_principal")
              .reindex(MOTIVOS_A).round(1).to_string())

    titulo("T4 - Critério A: horas aptas diurnas x noturnas por fase")
    T4 = tabelas["T4_noturno"]
    print(T4[T4["municipio"].isin(list(AGREG))].to_string(index=False))

    titulo("T0 - Horas aptas mensais, média 2004-2014 (A = proposto, B = Silva et al. 2018)")
    T0 = tabelas["T0_comparacao_criterios"]
    print(T0[T0["municipio"] == ESTADO].drop(columns=["municipio", "mes"]).to_string(index=False))

    titulo("T2c - Época com mais horas aptas no florescimento/enchimento (39-90 DAS), critério A")
    print(tabelas["T2c_melhor_epoca_fungicida"].to_string(index=False))
    titulo("T2c_critB - idem, critério B")
    print(tabelas["T2c_melhor_epoca_fungicida_critB"][
        ["municipio", "melhor_epoca", "horas_aptas_media", "pior_epoca", "horas_pior"]
    ].to_string(index=False))
    print(f"\nTabelas salvas em {TAB}")


if __name__ == "__main__":
    main()
