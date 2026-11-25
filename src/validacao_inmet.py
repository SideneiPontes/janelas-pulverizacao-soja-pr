"""Validação ERA5 x estações automáticas do INMET (Paraná).

Uso:  python -I src/validacao_inmet.py
Pré-requisito: python -I src/inventario_inmet.py (séries em data/processed/inmet/, inventário
T_inventario_inmet.csv e estação-safras válidas em data/processed/inmet_safras.csv).

Período: safras 2000/01 a 2025/26, só set-abr (horário local), só nas ESTAÇÃO-SAFRAS VÁLIDAS
(>= 70 % de horas válidas em T, UR e vento). As médias "TODAS" usam só as estações com
>= 2 safras válidas (incluida_na_media); as demais aparecem por estação.

Etapas
1-2. Estações a até RAIO_KM de algum dos 24 municípios, do inventário (src/inventario_inmet.py).
3. Baixa o ERA5 (Open-Meteo, models=era5) NO PONTO DA ESTAÇÃO (mede o erro da reanálise,
   não a distância município-estação).
4. Escala HORÁRIA: viés (ERA5 - estação), RMSE e r de T, UR, vento a 10 m e Delta T;
   acurácia e kappa de Cohen da classificação apta/inapta (critérios A e B).
5. Escala AGREGADA (a usada no artigo): horas aptas mensais e do período de fungicidas
   (16/dez até o fim de fevereiro) por estação, estação x ERA5: viés, RMSE, r; e se a
   ordem entre as estações se mantém (Spearman).            -> T12 (coluna 'escala'), F7
6. Horas aptas mensais como FRAÇÃO DAS HORAS VÁLIDAS (estação e ERA5 nas mesmas horas;
   nenhum dia é descartado) e extrapoladas para o mês inteiro; fração de horas sem dado.
                                                            -> T13
7. Decomposição da diferença (estação - ERA5) entre as condições de cada critério pelo
   valor de Shapley (exata: soma = diferença total).        -> T13b
Cenários: 'base' e 'ERA5 chuva<0,2 mm=0' (a chuva do ERA5 abaixo da resolução do
pluviômetro de báscula, 0,2 mm, conta como sem chuva).

Convenções iguais às de src/indicadores.py: o registro t representa a hora [t, t+1h);
chuva "na hora" = precipitação do registro t+1h; "2 h seguintes" = t+2h + t+3h.
INMET e Open-Meteo registram a chuva acumulada na hora ANTERIOR ao horário (UTC).
VENTO: as estações automáticas do INMET medem a 10 m; o ERA5 fornece wind_speed_10m.
Para o critério A, os DOIS são convertidos para 2 m com o fator FAO-56
(u2 = u10 * 4,87 / ln(67,8*10 - 5,42) = 0,748 * u10). O critério B usa o vento a 10 m.
"""
from __future__ import annotations

import itertools
import math
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import cohen_kappa_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_era5 import DownloadError, requisitar  # noqa: E402
from indicadores import FATOR_U2, PROC, TAB, bulbo_umido_stull  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INMET = ROOT / "data" / "raw" / "inmet"
ERA5_EST = ROOT / "data" / "raw" / "era5_estacoes"
FIG = ROOT / "outputs" / "figures"
LOG = ROOT / "outputs" / "log_validacao_inmet.txt"
TZ = "America/Sao_Paulo"
ANOS = range(2000, 2027)            # anos civis cobertos (safras 2000/01 a 2025/26)
# horas de 1º/set/2000 00h a 30/abr/2026 23h (horário local, UTC-3 nas duas pontas)
IDX = pd.date_range("2000-09-01 03:00", "2026-05-01 02:00", freq="h", tz="UTC")
BLOCOS_ERA5 = [(f"{a}-01-01", f"{a + 4}-12-31") for a in range(2000, 2025, 5)] + [("2025-01-01", "2026-05-01")]
RAIO_KM = 30.0
MIN_VALIDO = 0.5   # mês/safra entra na concordância agregada se >= 50 % das horas válidas
CHUVA_RES = 0.2    # resolução do pluviômetro de báscula (mm)
VARS_ERA5 = ["temperature_2m", "relative_humidity_2m", "precipitation", "wind_speed_10m"]
NOME_MES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
CENARIOS = {"base": None, "ERA5 chuva<0,2 mm=0": CHUVA_RES}

COND = {
    "A": ["DeltaT", "vento", "temperatura", "UR", "chuva"],
    "B": ["vento", "temperatura", "UR", "chuva"],
}


class Tee:
    """Escreve na tela e no log ao mesmo tempo."""
    def __init__(self, f):
        self.f, self.o = f, sys.stdout

    def write(self, s):
        self.o.write(s)
        self.f.write(s)

    def flush(self):
        self.o.flush()
        self.f.flush()


# ----------------------------------------------------------------------------
# 1. Leitura dos CSVs do INMET
# ----------------------------------------------------------------------------
def _num(s: pd.Series) -> pd.Series:
    v = pd.to_numeric(s.astype(str).str.strip().str.replace(",", ".", regex=False),
                      errors="coerce")
    return v.where(v > -9990)


def ler_csv(f: Path) -> tuple[dict, pd.DataFrame]:
    linhas = f.read_text(encoding="latin-1").splitlines()
    meta = {}
    for l in linhas[:8]:
        k, _, v = l.partition(";")
        meta[k.strip().rstrip(":").upper()] = v.strip().strip(";")
    cab = [c.strip() for c in linhas[8].split(";")]
    dados = [l.split(";") for l in linhas[9:] if l.strip()]
    df = pd.DataFrame(dados).iloc[:, :len(cab)]
    df.columns = cab[:df.shape[1]]

    def col(padrao):
        c = [x for x in df.columns if re.search(padrao, x.upper())]
        if not c:
            raise ValueError(f"{f.name}: coluna '{padrao}' não encontrada")
        return df[c[0]]

    data = df.iloc[:, 0].str.replace("/", "-", regex=False).str.strip()
    hora = df.iloc[:, 1].str.extract(r"(\d{2}):?(\d{2})")
    t = pd.to_datetime(data + " " + hora[0] + ":" + hora[1], format="%Y-%m-%d %H:%M",
                       errors="coerce", utc=True)
    out = pd.DataFrame({
        "time_utc": t,
        "precip": _num(col(r"PRECIPITA")),
        "T": _num(col(r"BULBO SECO")),
        "UR": _num(col(r"UMIDADE RELATIVA DO AR")),
        "u10": _num(col(r"VENTO, VELOCIDADE")) * 3.6,   # m/s -> km/h, medido a 10 m
    }).dropna(subset=["time_utc"])
    info = {
        "codigo": meta.get("CODIGO (WMO)"), "estacao": meta.get("ESTACAO", meta.get("ESTAÇÃO")),
        "lat": float(meta["LATITUDE"].replace(",", ".")),
        "lon": float(meta["LONGITUDE"].replace(",", ".")),
        "alt": float(meta["ALTITUDE"].replace(",", ".")),
    }
    return info, out


def qc(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.loc[~df["T"].between(-10, 45), "T"] = np.nan
    df.loc[~df["UR"].between(1, 100), "UR"] = np.nan
    df.loc[~df["u10"].between(0, 144), "u10"] = np.nan          # 0-40 m/s
    df.loc[~df["precip"].between(0, 150), "precip"] = np.nan
    return df


def janela_safras(idx_utc: pd.DatetimeIndex) -> pd.Series:
    """Ano de início da safra de cada hora (set-abr, horário local); NaN fora da safra."""
    loc = idx_utc.tz_convert(TZ)
    m = loc.month
    v = np.where(m >= 9, loc.year, np.where(m <= 4, loc.year - 1, -1)).astype(float)
    v[v < 0] = np.nan
    return pd.Series(v, index=idx_utc)


SAFRA_IDX = janela_safras(IDX)


def safras_validas() -> pd.DataFrame:
    S = pd.read_csv(PROC / "inmet_safras.csv", encoding="utf-8-sig")
    return S[S["safra_valida"]]


def mascara_ativa(codigo: str, idx: pd.DatetimeIndex = IDX) -> pd.Series:
    """True nas horas set-abr das estação-safras válidas da estação."""
    sv = set(safras_validas().query("codigo == @codigo")["safra_ini"])
    saf = SAFRA_IDX if idx is IDX else janela_safras(idx)
    return saf.isin(sv)


def rotulo_safra(s0: int) -> str:
    return f"{s0}/{str(s0 + 1)[2:]}"


def estacoes() -> pd.DataFrame:
    """Inventário com a coluna 'selecionada' (= usada na validação)."""
    inv = pd.read_csv(TAB / "T_inventario_inmet.csv", encoding="utf-8-sig")
    inv["selecionada"] = inv["usada_na_validacao"]
    sv = safras_validas().groupby("codigo")["safra_ini"]
    inv["safra_ini_valida"] = inv["codigo"].map(sv.min())
    inv["safra_fim_valida"] = inv["codigo"].map(sv.max())
    return inv


def incluidas() -> set:
    inv = estacoes()
    return set(inv.loc[inv["incluida_na_media"], "codigo"])


def periodo_estacoes(ms: pd.DataFrame) -> str:
    return (f"safras {rotulo_safra(int(ms['safra_ini_valida'].min()))}–"
            f"{rotulo_safra(int(ms['safra_fim_valida'].max()))} (set–abr, estação-safras válidas)")


def dist_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


# ----------------------------------------------------------------------------
# 3. ERA5 no ponto da estação (2010-2024, cache em data/raw/era5_estacoes)
# ----------------------------------------------------------------------------
def era5_estacao(e: pd.Series) -> pd.DataFrame:
    """ERA5 no ponto da estação, só nos blocos que cobrem as safras válidas (cache por bloco em
    data/raw/era5_estacoes/_blocos; o cache antigo 2010-2024 por estação é reaproveitado)."""
    blocos = ERA5_EST / "_blocos"
    blocos.mkdir(parents=True, exist_ok=True)
    sv = safras_validas().query("codigo == @e.codigo")["safra_ini"]
    anos = set(sv) | {x + 1 for x in sv}
    antigo = ERA5_EST / f"{e.codigo}.parquet"
    partes = []
    for ini, fim in BLOCOS_ERA5:
        if not anos & set(range(int(ini[:4]), int(fim[:4]) + 1)):
            continue
        f = blocos / f"{e.codigo}_{ini[:4]}_{fim[:4]}.parquet"
        if not f.exists() and antigo.exists() and int(ini[:4]) >= 2010 and int(fim[:4]) <= 2024:
            d = pd.read_parquet(antigo)
            loc = d["time_utc"].dt.tz_convert(TZ).dt.tz_localize(None)
            d[(loc >= ini) & (loc < pd.Timestamp(fim) + pd.Timedelta(days=1))].to_parquet(f, index=False)
        if not f.exists():
            js = requisitar({
                "latitude": e.lat, "longitude": e.lon, "start_date": ini, "end_date": fim,
                "hourly": ",".join(VARS_ERA5), "models": "era5", "timezone": TZ,
                "wind_speed_unit": "kmh", "timeformat": "unixtime"})
            h = js["hourly"]
            d = pd.DataFrame({
                "time_utc": pd.to_datetime(h["time"], unit="s", utc=True),
                "T": h["temperature_2m"], "UR": h["relative_humidity_2m"],
                "precip": h["precipitation"], "u10": h["wind_speed_10m"]})
            d["grid_lat"], d["grid_lon"] = js.get("latitude"), js.get("longitude")
            d.to_parquet(f, index=False)
            time.sleep(1)
        partes.append(pd.read_parquet(f))
    return pd.concat(partes).drop_duplicates("time_utc").sort_values("time_utc")


# ----------------------------------------------------------------------------
# Critérios, métricas, Shapley
# ----------------------------------------------------------------------------
def condicoes(d: pd.DataFrame) -> tuple[dict, dict, pd.Series, pd.Series]:
    """Flags (True = condição satisfeita) e validade por critério.
    Critério A: vento a 2 m (u10 * FATOR_U2). Critério B: vento a 10 m."""
    dT = d["T"] - bulbo_umido_stull(d["T"].to_numpy(), d["UR"].to_numpy())
    u2 = d["u10"] * FATOR_U2
    p = d["precip"]
    p1, p2, p3 = p.shift(-1), p.shift(-2), p.shift(-3)
    A = {"DeltaT": dT.between(2, 8), "vento": u2.between(3, 10), "temperatura": d["T"] < 30,
         "UR": d["UR"] >= 50, "chuva": (p1 == 0) & ((p2 + p3) < 1)}
    B = {"vento": d["u10"].between(3, 12), "temperatura": d["T"] < 30, "UR": d["UR"] > 55,
         "chuva": p1 < 0.2}
    base = d[["T", "UR", "u10"]].notna().all(axis=1)
    valA = base & p1.notna() & p2.notna() & p3.notna()
    valB = base & p1.notna()
    return A, B, valA, valB


def metricas(x: pd.Series, y: pd.Series) -> dict:
    """x = ERA5, y = estação."""
    m = x.notna() & y.notna()
    x, y = x[m], y[m]
    if len(x) < 3:
        return {"n": int(len(x))}
    d = x - y
    r = np.corrcoef(x, y)[0, 1] if x.std() > 0 and y.std() > 0 else np.nan
    return {"n": int(len(x)), "media_era5": x.mean(), "media_estacao": y.mean(),
            "vies": d.mean(), "rmse": math.sqrt((d ** 2).mean()), "r": r}


def shapley(flags_era: dict, flags_est: dict, cond: list[str], valido: pd.Series,
            grupo: pd.Series) -> pd.DataFrame:
    """Contribuição de cada condição para (horas aptas estação - horas aptas ERA5)."""
    n = len(cond)
    E = {c: flags_era[c][valido].to_numpy() for c in cond}
    S = {c: flags_est[c][valido].to_numpy() for c in cond}
    g = grupo[valido].to_numpy()
    conta = {}
    for k in range(n + 1):
        for sub in itertools.combinations(cond, k):
            apt = np.ones(int(valido.sum()), dtype=bool)
            for c in cond:
                apt &= (S[c] if c in sub else E[c])
            conta[frozenset(sub)] = pd.Series(apt).groupby(g).sum()
    res = {}
    for c in cond:
        outros = [x for x in cond if x != c]
        tot = 0
        for k in range(n):
            peso = math.factorial(k) * math.factorial(n - k - 1) / math.factorial(n)
            for sub in itertools.combinations(outros, k):
                tot = tot + peso * (conta[frozenset(sub) | {c}] - conta[frozenset(sub)])
        res[c] = tot
    out = pd.DataFrame(res)
    out["total"] = conta[frozenset(cond)] - conta[frozenset()]
    return out


# ----------------------------------------------------------------------------
def analisar(ms: pd.DataFrame):
    idx = IDX
    loc = idx.tz_convert(TZ)
    mes = pd.Series(loc.month, index=idx)
    ano = pd.Series(loc.year, index=idx)
    dia = pd.Series(loc.tz_localize(None).normalize(), index=idx)
    fung = ((mes == 12) & (loc.day >= 16)) | (mes == 1) | (mes == 2)
    safra = SAFRA_IDX

    T12, mensal, fungi, dec, amostra, vento_log = [], [], [], [], [], []
    for _, e in ms.iterrows():
        print(f"  comparando {e.codigo} {e.estacao} ({e.municipio}, {e.dist_km:.1f} km)", flush=True)
        est = pd.read_parquet(PROC / "inmet" / f"{e.codigo}.parquet").set_index("time_utc").reindex(idx)
        era = era5_estacao(e).set_index("time_utc").reindex(idx)
        for d in (est, era):
            d["DeltaT"] = d["T"] - bulbo_umido_stull(d["T"].to_numpy(), d["UR"].to_numpy())
        ativo = mascara_ativa(e.codigo)          # set-abr das estação-safras válidas
        rot = {"codigo": e.codigo, "estacao": e.estacao, "municipio": e.municipio,
               "dist_km": round(e.dist_km, 1),
               "periodo": f"{rotulo_safra(int(e.safra_ini_valida))}–{rotulo_safra(int(e.safra_fim_valida))}"
                          f" ({int(e.n_safras_validas)} safras válidas)"}
        est, era = est.where(ativo), era.where(ativo)   # só horas das estação-safras válidas
        vento_log.append({"codigo": e.codigo, "u10_estacao_media": est["u10"].mean(),
                          "u2_estacao_media": (est["u10"] * FATOR_U2).mean(),
                          "u10_era5_media": era["u10"][est["u10"].notna()].mean(),
                          "u2_era5_media": (era["u10"] * FATOR_U2)[est["u10"].notna()].mean()})

        for v, nome in [("T", "Temperatura (°C)"), ("UR", "UR (%)"),
                        ("u10", "Vento a 10 m (km/h)"), ("DeltaT", "Delta T (°C)")]:
            T12.append({**rot, "escala": "horária", "cenario": "-", "variavel": nome,
                        **metricas(era[v], est[v])})
        amostra.append(pd.DataFrame({"codigo": e.codigo,
                                     **{f"{v}_est": est[v] for v in ["T", "UR", "u10", "DeltaT"]},
                                     **{f"{v}_era": era[v] for v in ["T", "UR", "u10", "DeltaT"]}}))

        cS = dict(zip(("A", "B", "vA", "vB"), condicoes(est)))
        for cen, lim in CENARIOS.items():
            er = era.copy()
            if lim is not None:
                er.loc[er["precip"] < lim, "precip"] = 0.0
            cE = dict(zip(("A", "B", "vA", "vB"), condicoes(er)))
            for crit in ("A", "B"):
                fe, fs = cE[crit], cS[crit]
                aptE = pd.Series(np.logical_and.reduce([fe[c] for c in COND[crit]]), index=idx)
                aptS = pd.Series(np.logical_and.reduce([fs[c] for c in COND[crit]]), index=idx)
                vs = cS["v" + crit] & ativo
                val = cE["v" + crit] & vs
                k = cohen_kappa_score(aptS[val], aptE[val])
                T12.append({**rot, "escala": "horária", "cenario": cen,
                            "variavel": f"Classificação apta - critério {crit}",
                            "n": int(val.sum()), "acuracia": (aptS[val] == aptE[val]).mean(),
                            "kappa": k, "pct_apta_era5": 100 * aptE[val].mean(),
                            "pct_apta_estacao": 100 * aptS[val].mean()})
                for c in COND[crit]:
                    T12.append({**rot, "escala": "horária", "cenario": cen,
                                "variavel": f"Condição {c} satisfeita - critério {crit}",
                                "n": int(val.sum()), "pct_apta_era5": 100 * fe[c][val].mean(),
                                "pct_apta_estacao": 100 * fs[c][val].mean()})
                h = pd.DataFrame({"ano": ano, "mes": mes, "dia": dia, "ativo": ativo, "val": val,
                                  "sem_dado": ativo & ~vs, "aptS": aptS & val, "aptE": aptE & val,
                                  "aptE_todas": aptE & cE["v" + crit] & ativo,
                                  "valE_todas": cE["v" + crit] & ativo})
                h = h[ativo]
                g = h.groupby(["ano", "mes"])
                m = g[["ativo", "val", "sem_dado", "aptS", "aptE", "aptE_todas", "valE_todas"]].sum()
                m["dias_com_falha"] = h[h["sem_dado"]].groupby(["ano", "mes"])["dia"].nunique()
                m["dias"] = g["dia"].nunique()
                m = m.fillna({"dias_com_falha": 0}).reset_index()
                m["horas_calendario"] = [pd.Period(year=a, month=mm, freq="M").days_in_month * 24
                                         for a, mm in zip(m["ano"], m["mes"])]
                m = m.assign(criterio=crit, cenario=cen, **rot)
                mensal.append(m)
                hf = pd.DataFrame({"safra": safra, "ativo": ativo, "val": val,
                                   "aptS": aptS & val, "aptE": aptE & val})[fung]
                f = hf.groupby("safra").agg(horas_fase=("ativo", "size"), ativo=("ativo", "sum"),
                                            val=("val", "sum"), aptS=("aptS", "sum"),
                                            aptE=("aptE", "sum")).reset_index()
                fungi.append(f.assign(criterio=crit, cenario=cen, **rot))
                s = shapley(fe, fs, COND[crit], val, ano * 100 + mes)
                s.index.name = "ym"
                s = s.reset_index()
                s["ano"], s["mes"] = s["ym"] // 100, s["ym"] % 100
                dec.append(s.drop(columns="ym").assign(criterio=crit, cenario=cen, codigo=e.codigo))
    return (pd.DataFrame(T12), pd.concat(mensal, ignore_index=True),
            pd.concat(fungi, ignore_index=True), pd.concat(dec, ignore_index=True),
            pd.concat(amostra), pd.DataFrame(vento_log))


def concordancia_agregada(M: pd.DataFrame, F: pd.DataFrame) -> pd.DataFrame:
    """Viés, RMSE e r das horas aptas extrapoladas (mensais e por safra no período de
    fungicidas) e Spearman da ordem entre estações."""
    linhas = []
    inc = incluidas()
    M = M[M["val"] >= MIN_VALIDO * M["ativo"]].copy()
    M["est"] = M["aptS"] / M["val"] * M["horas_calendario"]
    M["era"] = M["aptE"] / M["val"] * M["horas_calendario"]
    F = F[(F["ativo"] == F["horas_fase"]) & (F["val"] >= MIN_VALIDO * F["horas_fase"])].copy()
    F["est"] = F["aptS"] / F["val"] * F["horas_fase"]
    F["era"] = F["aptE"] / F["val"] * F["horas_fase"]
    for escala, D, unid in (("mensal", M, "meses"), ("período de fungicidas", F, "safras")):
        for (crit, cen), g in D.groupby(["criterio", "cenario"]):
            var = f"Horas aptas ({unid}) - critério {crit}"
            for cod, gg in g.groupby("codigo"):
                r0 = gg.iloc[0]
                linhas.append({"codigo": cod, "estacao": r0.estacao, "municipio": r0.municipio,
                               "dist_km": r0.dist_km, "periodo": r0.periodo, "escala": escala,
                               "cenario": cen, "variavel": var,
                               **metricas(gg["era"].reset_index(drop=True),
                                          gg["est"].reset_index(drop=True))})
            g = g[g["codigo"].isin(inc)]
            linhas.append({"codigo": "TODAS", "estacao": "todas as estações", "escala": escala,
                           "cenario": cen, "variavel": var,
                           **metricas(g["era"].reset_index(drop=True),
                                      g["est"].reset_index(drop=True))})
            # ordem entre estações (da mais restritiva à mais favorável)
            o = g.groupby("codigo")[["est", "era"]].mean()
            rho, p = spearmanr(o["est"], o["era"])
            linhas.append({"codigo": "TODAS", "estacao": "ordem entre estações",
                           "escala": escala, "cenario": cen,
                           "variavel": f"Spearman da ordem das estações - critério {crit}",
                           "n": len(o), "r_spearman": rho, "p_spearman": p,
                           "ordem_estacao": " < ".join(o["est"].sort_values().index),
                           "ordem_era5": " < ".join(o["era"].sort_values().index)})
    return pd.DataFrame(linhas)


def tabela_T13(M: pd.DataFrame) -> pd.DataFrame:
    """Frações das horas válidas (pooled nos anos) por estação e mês; extrapoladas."""
    soma = (M.groupby(["criterio", "cenario", "codigo", "estacao", "municipio", "mes"])
            [["ativo", "val", "sem_dado", "aptS", "aptE", "aptE_todas", "valE_todas",
              "dias_com_falha", "dias"]].sum())
    soma["horas_calendario_medias"] = (M.groupby(["criterio", "cenario", "codigo", "estacao",
                                                  "municipio", "mes"])["horas_calendario"].mean())
    t = pd.DataFrame(index=soma.index)
    t["horas_em_operacao"] = soma["ativo"]
    t["horas_validas"] = soma["val"]
    t["pct_horas_sem_dado"] = 100 * soma["sem_dado"] / soma["ativo"]
    t["pct_dias_com_alguma_falha"] = 100 * soma["dias_com_falha"] / soma["dias"]
    t["pct_aptas_estacao"] = 100 * soma["aptS"] / soma["val"]
    t["pct_aptas_era5_mesmas_horas"] = 100 * soma["aptE"] / soma["val"]
    t["pct_aptas_era5_todas_horas"] = 100 * soma["aptE_todas"] / soma["valE_todas"]
    h = soma["horas_calendario_medias"]
    t["horas_aptas_estacao_extrap"] = t["pct_aptas_estacao"] / 100 * h
    t["horas_aptas_era5_extrap"] = t["pct_aptas_era5_mesmas_horas"] / 100 * h
    t["diferenca_estacao_menos_era5_h"] = t["horas_aptas_estacao_extrap"] - t["horas_aptas_era5_extrap"]
    t["razao_estacao_era5"] = t["horas_aptas_estacao_extrap"] / t["horas_aptas_era5_extrap"]
    t["horas_mes"] = h
    t = t.reset_index()
    todas = (t[t["codigo"].isin(incluidas())].groupby(["criterio", "cenario", "mes"])
             .mean(numeric_only=True).reset_index())   # média simples das estações
    todas["razao_estacao_era5"] = todas["horas_aptas_estacao_extrap"] / todas["horas_aptas_era5_extrap"]
    todas["codigo"], todas["estacao"], todas["municipio"] = "TODAS", "média das estações", ""
    t = pd.concat([t, todas], ignore_index=True)
    t.insert(t.columns.get_loc("mes") + 1, "mes_nome", t["mes"].map(lambda m: NOME_MES[m - 1]))
    return t.round(3)


def tabela_T13b(D: pd.DataFrame, M: pd.DataFrame) -> pd.DataFrame:
    """Contribuições em h/mês extrapolado: soma por estação-mês / horas válidas x horas do mês;
    depois média simples das estações (soma das contribuições = diferença da T13)."""
    chaves = ["criterio", "cenario", "codigo", "ano", "mes"]
    D = M[chaves + ["val", "horas_calendario"]].merge(D, on=chaves, how="left").fillna(0)
    cols = [c for c in D.columns if c in ("DeltaT", "vento", "temperatura", "UR", "chuva", "total")]
    g = D.groupby(["criterio", "cenario", "codigo", "mes"])
    s = g[cols + ["val"]].sum()
    h = g["horas_calendario"].mean()
    por_est = s[cols].div(s["val"], axis=0).mul(h, axis=0).reset_index()
    por_est = por_est[por_est["codigo"].isin(incluidas())]
    t = por_est.groupby(["criterio", "cenario", "mes"])[cols].mean().reset_index()
    t.insert(3, "mes_nome", t["mes"].map(lambda m: NOME_MES[m - 1]))
    return t.round(3)


PERIODO_TXT = ""


def fig_F7(A: pd.DataFrame, T12: pd.DataFrame):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    from estatistica import INK, SEQ  # aplica o estilo do projeto

    vs = [("T", "Temperatura do ar (°C)"), ("UR", "Umidade relativa (%)"),
          ("u10", "Vento a 10 m (km/h)"), ("DeltaT", "Delta T (°C)")]
    nomes = {"T": "Temperatura (°C)", "UR": "UR (%)", "u10": "Vento a 10 m (km/h)",
             "DeltaT": "Delta T (°C)"}
    fig, axs = plt.subplots(2, 2, figsize=(9, 8.2))
    for ax, (v, rot) in zip(axs.ravel(), vs):
        x, y = A[f"{v}_est"], A[f"{v}_era"]
        m = x.notna() & y.notna()
        if v == "UR":  # UR inteira nas duas fontes: dispersão de +-0,5 % só no desenho (evita
            rng = np.random.default_rng(0)  # padrão de moiré dos hexágonos); métricas usam o dado
            x = x + rng.uniform(-0.5, 0.5, len(x))
            y = y + rng.uniform(-0.5, 0.5, len(y))
        lo, hi = np.nanpercentile(np.r_[x[m], y[m]], [0.1, 99.9])
        hb = ax.hexbin(x[m], y[m], gridsize=70, extent=(lo, hi, lo, hi), cmap=SEQ,
                       norm=LogNorm(), mincnt=1, linewidths=0)
        ax.plot([lo, hi], [lo, hi], color=INK, lw=1, ls="--")
        r = T12[(T12["codigo"] == "TODAS") & (T12["variavel"] == nomes[v])].iloc[0]
        txt = (f"n = {int(r['n']):,}".replace(",", ".") +
               f"\nviés = {r['vies']:+.2f}".replace(".", ",") +
               f"\nRMSE = {r['rmse']:.2f}".replace(".", ",") +
               f"\nr = {r['r']:.3f}".replace(".", ","))
        ax.text(0.03, 0.97, txt, transform=ax.transAxes, va="top", fontsize=8, color=INK,
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.8, pad=2))
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        ax.set_aspect("equal")
        ax.set_xlabel(f"Estação INMET — {rot}")
        ax.set_ylabel(f"ERA5 — {rot}")
        cb = fig.colorbar(hb, ax=ax, fraction=0.046, pad=0.03)
        cb.set_label("Nº de horas", fontsize=8)
        cb.outline.set_visible(False)
    fig.suptitle(f"ERA5 x estações automáticas do INMET (Paraná, {PERIODO_TXT}), "
                 "dados horários", x=0.01, ha="left", fontsize=10, color=INK)
    fig.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / "F7_dispersao_era5_estacao.png")
    plt.close(fig)


def main() -> None:
    pd.set_option("display.width", 230)
    pd.set_option("display.max_columns", 30)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    flog = open(LOG, "w", encoding="utf-8")
    sys.stdout = Tee(flog)
    try:
        executar()
    finally:
        sys.stdout = sys.stdout.o
        flog.close()


def executar() -> None:
    def titulo(s):
        print("\n" + "=" * 100 + f"\n{s}\n" + "=" * 100)

    global PERIODO_TXT
    sel = estacoes()
    sel.round(3).to_csv(TAB / "T12a_estacoes_inmet.csv", index=False, encoding="utf-8-sig")
    ms = sel[sel["selecionada"]].reset_index(drop=True)
    per = periodo_estacoes(ms)
    PERIODO_TXT = per.split(" (")[0]
    titulo(f"VALIDAÇÃO ERA5 x INMET - {per}")
    print(f"Estações no inventário (PR + vizinhas a até {RAIO_KM:.0f} km): {len(sel)}; usadas "
          f"(<= {RAIO_KM:.0f} km de um dos 24 municípios e >= 1 safra válida): {len(ms)}; "
          f"nas médias (>= 2 safras válidas): {int(ms['incluida_na_media'].sum())}")
    print(ms[["codigo", "estacao", "uf", "municipio", "dist_km", "alt", "alt_municipio",
              "n_safras_validas", "safras_validas"]].round(1).to_string(index=False))
    if ms.empty:
        sys.exit("Nenhuma estação a até RAIO_KM dos municípios.")

    T12h, M, F, D, A, V = analisar(ms)

    titulo("ALTURA DO VENTO")
    print("Estação INMET: vento medido a 10 m (VENTO, VELOCIDADE HORARIA, m/s -> km/h).")
    print(f"ERA5: wind_speed_10m (10 m). Critério A: ambos convertidos de 10 m para 2 m com o fator "
          f"FAO-56 u2 = u10 x 4,87/ln(67,8x10-5,42) = {FATOR_U2:.4f}.")
    print("Critério B (Silva et al., 2018): vento a 10 m, sem conversão.")
    print("Médias nas horas com vento válido na estação (km/h): antes (10 m) -> depois (2 m)")
    print(V.round(2).to_string(index=False))

    titulo("CENÁRIOS DE CHUVA")
    print("base: chuva do ERA5 como fornecida (resolução 0,1 mm).")
    print(f"ERA5 chuva<0,2 mm=0: chuva horária do ERA5 abaixo de {CHUVA_RES} mm conta como zero "
          "(resolução do pluviômetro de báscula das estações).")

    # T12: horária (por estação + todas) e agregada
    tot = []
    A = A[A["codigo"].isin(incluidas())]
    for v, nome in [("T", "Temperatura (°C)"), ("UR", "UR (%)"),
                    ("u10", "Vento a 10 m (km/h)"), ("DeltaT", "Delta T (°C)")]:
        tot.append({"codigo": "TODAS", "estacao": "todas as estações", "escala": "horária",
                    "cenario": "-", "variavel": nome,
                    **metricas(A[f"{v}_era"], A[f"{v}_est"])})
    cl = T12h[T12h["variavel"].str.startswith(("Classificação", "Condição"))
              & T12h["codigo"].isin(incluidas())]
    for (cen, var), g in cl.groupby(["cenario", "variavel"]):
        w = g["n"] / g["n"].sum()
        r = {"codigo": "TODAS", "estacao": "todas (média ponderada por n)", "escala": "horária",
             "cenario": cen, "variavel": var, "n": int(g["n"].sum()),
             "pct_apta_era5": (g["pct_apta_era5"] * w).sum(),
             "pct_apta_estacao": (g["pct_apta_estacao"] * w).sum()}
        if var.startswith("Classificação"):
            r["acuracia"], r["kappa"] = (g["acuracia"] * w).sum(), (g["kappa"] * w).sum()
        tot.append(r)
    T12 = pd.concat([T12h, pd.DataFrame(tot), concordancia_agregada(M, F)], ignore_index=True)
    T12.insert(0, "periodo_analise", per)
    T12.round(4).to_csv(TAB / "T12_validacao.csv", index=False, encoding="utf-8-sig")
    T13 = tabela_T13(M)
    T13.insert(0, "periodo_analise", per)
    T13.to_csv(TAB / "T13_horas_aptas_estacao_vs_era5.csv", index=False, encoding="utf-8-sig")
    T13b = tabela_T13b(D, M)
    T13b.insert(0, "periodo_analise", per)
    T13b.to_csv(TAB / "T13b_decomposicao_discrepancia.csv", index=False, encoding="utf-8-sig")
    M.to_csv(PROC / "inmet_mensal_por_ano.csv", index=False, encoding="utf-8-sig")
    fig_F7(A, T12)

    # ------------------------------------------------------------ resumo
    titulo("T12 - escala HORÁRIA, todas as estações (viés = ERA5 - estação)")
    t = T12[(T12["codigo"] == "TODAS") & (T12["escala"] == "horária")
            & ~T12["variavel"].str.startswith("Condição")]
    print(t[["cenario", "variavel", "n", "vies", "rmse", "r", "acuracia", "kappa",
             "pct_apta_era5", "pct_apta_estacao"]].round(3).to_string(index=False))
    titulo("T12 - kappa hora a hora por estação")
    k = T12[T12["variavel"].str.startswith("Classificação") & (T12["codigo"] != "TODAS")]
    print(k.pivot_table(index=["codigo", "estacao"], columns=["cenario", "variavel"],
                        values="kappa").round(3).to_string())
    titulo("Condições satisfeitas (% das horas válidas, todas as estações)")
    c = T12[T12["variavel"].str.startswith("Condição") & (T12["codigo"] == "TODAS")]
    print(c.pivot_table(index="variavel", columns="cenario",
                        values=["pct_apta_era5", "pct_apta_estacao"]).round(1).to_string())
    titulo("T12 - escala AGREGADA (horas aptas extrapoladas; viés = ERA5 - estação)")
    ag = T12[T12["escala"].isin(["mensal", "período de fungicidas"]) & (T12["codigo"] == "TODAS")]
    print(ag[["escala", "cenario", "variavel", "n", "vies", "rmse", "r", "r_spearman",
              "p_spearman"]].round(3).to_string(index=False))
    print("\nOrdem das estações (mais restritiva < mais favorável), cenário base:")
    o = ag[(ag["cenario"] == "base") & ag["variavel"].str.startswith("Spearman")]
    for _, r in o.iterrows():
        print(f"  {r.escala} | {r.variavel[-10:]}: estação {r.ordem_estacao}")
        print(f"  {' ' * len(r.escala)} | {' ' * 10}  ERA5    {r.ordem_era5}")
    print("\nPor estação (cenário base, r das horas aptas mensais / por safra no período de fungicidas):")
    pe = T12[T12["escala"].isin(["mensal", "período de fungicidas"]) & (T12["codigo"] != "TODAS")
             & (T12["cenario"] == "base")]
    print(pe.pivot_table(index=["codigo", "estacao"], columns=["escala", "variavel"],
                         values="r").round(2).to_string())
    for crit in ("A", "B"):
        for cen in CENARIOS:
            titulo(f"T13 - critério {crit}, cenário '{cen}': horas aptas (média das estações)")
            print(T13[(T13["codigo"] == "TODAS") & (T13["criterio"] == crit) & (T13["cenario"] == cen)][[
                "mes_nome", "pct_horas_sem_dado", "pct_dias_com_alguma_falha", "pct_aptas_estacao",
                "pct_aptas_era5_mesmas_horas", "horas_aptas_estacao_extrap", "horas_aptas_era5_extrap",
                "razao_estacao_era5"]].round(1).to_string(index=False))
            titulo(f"T13b - critério {crit}, cenário '{cen}': contribuição para (estação - ERA5), h/mês")
            print(T13b[(T13b["criterio"] == crit) & (T13b["cenario"] == cen)]
                  .drop(columns=["periodo_analise", "criterio", "cenario", "mes"])
                  .set_index("mes_nome").round(1).to_string())


if __name__ == "__main__":
    try:
        main()
    except DownloadError as e:
        sys.exit(f"ERRO no download do ERA5 das estações: {e}")
