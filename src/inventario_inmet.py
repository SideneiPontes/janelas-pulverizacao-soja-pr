"""Inventário e séries horárias das estações automáticas do INMET (2000-2026). Não baixa nada.

Fontes (só arquivos que já estão no computador):
  - "Anos Complementares/<ano>/" (CSVs anuais de todo o Brasil, 2000-2009 e 2017-2026);
  - zips anuais 2010-2016 em %TEMP%/inmet_zips (ou INMET_ZIP_DIR), que têm todas as UFs;
    se o zip de um ano não existir, usa os CSVs do PR já extraídos em data/raw/inmet/<ano>/.

Etapas
1. Abre cada zip (testzip) e cada CSV (cabeçalho de 8 linhas, linha de colunas, nº de campos da
   última linha) e registra arquivos corrompidos.
2. Metadados dos próprios arquivos (código, nome, UF, lat, lon, altitude, data de fundação):
   todas as estações automáticas do PR e as de SC, SP e MS a até RAIO_KM de algum dos 24
   municípios.
3. Série horária por estação (UTC), mesmo controle de qualidade de antes (limites físicos;
   sem imputação; duplicidades removidas) -> data/processed/inmet/<codigo>.parquet.
4. Por estação e safra (1º/set a 30/abr, horário local): % de horas válidas de T, UR, vento e
   chuva. Estação-safra válida: >= 70 % de horas válidas em T, UR e vento.
   Estação incluída nas médias: >= 2 safras válidas.
Saídas: outputs/tables/T_inventario_inmet.csv, data/processed/inmet_safras.csv,
        data/processed/inmet_arquivos.csv (verificação de cada arquivo).

Uso:  python -I src/inventario_inmet.py
"""
from __future__ import annotations

import io
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indicadores import PROC, SAFRAS, TAB  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COMPLEMENTAR = Path(os.environ.get("INMET_COMPLEMENTAR", ROOT / "Anos Complementares"))
ZIPS = Path(os.environ.get("INMET_ZIP_DIR", Path(tempfile.gettempdir()) / "inmet_zips"))
EXTRAIDOS = ROOT / "data" / "raw" / "inmet"
ANOS_ZIP = range(2010, 2017)
TZ = "America/Sao_Paulo"
RAIO_KM = 30.0
UF_VIZINHAS = {"SC", "SP", "MS"}
MIN_SAFRA = 0.70      # fração mínima de horas válidas em T, UR e vento
MIN_SAFRAS_MEDIA = 2  # safras válidas para entrar nas médias
LIMITES = {"T": (-10, 45), "UR": (1, 100), "u10": (0, 144), "precip": (0, 150)}


# ----------------------------------------------------------------------------
def _num(s: pd.Series) -> pd.Series:
    v = pd.to_numeric(s.astype(str).str.strip().str.replace(",", ".", regex=False), errors="coerce")
    return v.where(v > -9990)


def meta_texto(linhas: list[str]) -> dict:
    meta = {}
    for l in linhas[:8]:
        k, _, v = l.partition(";")
        meta[k.strip().rstrip(":").upper()] = v.strip().strip(";")
    return meta


def _f(s: str) -> float:
    return float(s.replace(",", "."))


def info_meta(meta: dict) -> dict:
    def get(prefixo):
        for k, v in meta.items():
            if k.startswith(prefixo):
                return v
        return None
    fund = get("DATA DE FUNDA")
    dt = pd.NaT
    if fund:
        for fmt in ("%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y"):
            dt = pd.to_datetime(fund, format=fmt, errors="coerce")
            if pd.notna(dt):
                break
    return {"codigo": get("CODIGO"), "estacao": get("ESTA"), "uf": get("UF"),
            "lat": _f(get("LATITUDE")), "lon": _f(get("LONGITUDE")), "alt": _f(get("ALTITUDE")),
            "data_fundacao": dt}


def ler_texto(nome: str, texto: str) -> tuple[dict, pd.DataFrame]:
    linhas = texto.splitlines()
    info = info_meta(meta_texto(linhas))
    cab = [c.strip() for c in linhas[8].split(";")]
    dados = [l.split(";") for l in linhas[9:] if l.strip()]
    df = pd.DataFrame(dados).iloc[:, :len(cab)]
    df.columns = cab[:df.shape[1]]

    def col(padrao):
        c = [x for x in df.columns if re.search(padrao, x.upper())]
        if not c:
            raise ValueError(f"{nome}: coluna '{padrao}' não encontrada")
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
    return info, out


def checar_texto(texto: str) -> str:
    """'' se o arquivo abre e está íntegro; senão a descrição do problema."""
    linhas = texto.splitlines()
    if len(linhas) < 9:
        return "menos de 9 linhas (sem cabeçalho)"
    try:
        info_meta(meta_texto(linhas))
    except Exception as e:  # noqa: BLE001
        return f"metadados ilegíveis: {e!r}"
    ncab = len(linhas[8].rstrip(";").split(";"))
    ult = [l for l in linhas[9:] if l.strip()]
    if not ult:
        return "sem linhas de dados"
    if len(ult[-1].split(";")) < ncab:          # campos vazios contam (;;;)
        return "última linha truncada"
    return ""


# ----------------------------------------------------------------------------
def fontes():
    """(ano, nome, origem, função que devolve o texto) de todos os CSVs disponíveis."""
    arqs, problemas = [], []
    for d in sorted(p for p in COMPLEMENTAR.iterdir() if p.is_dir()):
        ano = int(d.name)
        for f in sorted(d.rglob("*")):
            if f.is_file() and f.suffix.lower() == ".csv":
                arqs.append((ano, f.name, f"Anos Complementares/{f.relative_to(COMPLEMENTAR).as_posix()}",
                             lambda f=f: f.read_bytes().decode("latin-1")))
    for ano in ANOS_ZIP:
        z = ZIPS / f"{ano}.zip"
        if z.exists():
            try:
                zf = zipfile.ZipFile(z)
                ruim = zf.testzip()
                if ruim:
                    problemas.append({"arquivo": f"{z.name}:{ruim}", "ano": ano, "problema": "CRC inválido no zip"})
                for n in zf.namelist():
                    if n.lower().endswith(".csv"):
                        arqs.append((ano, Path(n).name, f"inmet_zips/{z.name}:{n}",
                                     lambda zf=zf, n=n: zf.read(n).decode("latin-1")))
                continue
            except zipfile.BadZipFile as e:
                problemas.append({"arquivo": z.name, "ano": ano, "problema": f"zip corrompido: {e}"})
        for f in sorted((EXTRAIDOS / str(ano)).glob("*.[Cc][Ss][Vv]")):
            arqs.append((ano, f.name, f"data/raw/inmet/{ano}/{f.name}",
                         lambda f=f: f.read_bytes().decode("latin-1")))
    return arqs, problemas


def dist_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def janela_safras(idx_utc: pd.DatetimeIndex) -> pd.Series:
    """Ano de início da safra de cada hora (set-abr, horário local); NaN fora da safra."""
    loc = idx_utc.tz_convert(TZ)
    m = loc.month
    s = np.where(m >= 9, loc.year, np.where(m <= 4, loc.year - 1, -1)).astype(float)
    s[s < 0] = np.nan
    return pd.Series(s, index=idx_utc)


def main() -> None:
    pd.set_option("display.width", 230)
    muns = pd.read_csv(PROC / "municipios.csv", encoding="utf-8")
    arqs, verif = fontes()
    print(f"Arquivos CSV encontrados: {len(arqs)}", flush=True)

    # 1-2. abrir todos, metadados
    metas = []
    textos = {}
    for i, (ano, nome, origem, ler) in enumerate(arqs):
        try:
            txt = ler()
        except Exception as e:  # noqa: BLE001
            verif.append({"arquivo": origem, "ano": ano, "problema": f"não abre: {e!r}"})
            continue
        prob = checar_texto(txt)
        if prob:
            verif.append({"arquivo": origem, "ano": ano, "problema": prob})
            if prob.startswith(("menos", "metadados")):
                continue
        info = info_meta(meta_texto(txt.splitlines()[:8]))
        metas.append({**info, "ano": ano, "origem": origem})
        if info["uf"] in ({"PR"} | UF_VIZINHAS) and str(info["codigo"]).startswith(("A", "B")):
            textos.setdefault(info["codigo"], []).append((ano, origem, ler))
        if i % 1000 == 0:
            print(f"  {i}/{len(arqs)} arquivos verificados", flush=True)
    meta = pd.DataFrame(metas)
    meta.to_csv(PROC / "inmet_arquivos.csv", index=False, encoding="utf-8-sig")
    V = pd.DataFrame(verif, columns=["arquivo", "ano", "problema"])
    print(f"Arquivos com problema: {len(V)}")
    if len(V):
        print(V.to_string(index=False))

    # estações candidatas: metadados mais recentes de cada código
    ult = meta.sort_values("ano").groupby("codigo").last().reset_index()
    ult = ult[ult["uf"].isin({"PR"} | UF_VIZINHAS) & ult["codigo"].str.match(r"^[AB]\d")]
    lin = []
    for _, e in ult.iterrows():
        d = dist_km(e.lat, e.lon, muns["lat"].to_numpy(), muns["lon"].to_numpy())
        i = int(np.argmin(d))
        lin.append({"codigo": e.codigo, "estacao": e.estacao, "uf": e.uf, "lat": e.lat, "lon": e.lon,
                    "alt": e.alt, "municipio": muns["municipio"].iloc[i],
                    "grupo_origem": muns["grupo_origem"].iloc[i], "dist_km": d[i],
                    "alt_municipio": muns["altitude_m"].iloc[i]})
    est = pd.DataFrame(lin)
    est["dentro_30km"] = est["dist_km"] <= RAIO_KM
    est = est[(est["uf"] == "PR") | est["dentro_30km"]].sort_values("dist_km").reset_index(drop=True)
    fund = meta.groupby("codigo")["data_fundacao"].min()
    est["data_fundacao"] = est["codigo"].map(fund)

    # 3. séries horárias
    out = PROC / "inmet"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.parquet"):
        f.unlink()
    idx = pd.date_range("2000-09-01 03:00", "2026-05-01 02:00", freq="h", tz="UTC")
    saf = janela_safras(idx)
    saf = saf[saf.between(SAFRAS[0], SAFRAS[-1])]
    linhas_saf, qcs = [], []
    for _, e in est.iterrows():
        dfs = []
        for ano, origem, ler in textos.get(e.codigo, []):
            try:
                dfs.append(ler_texto(origem, ler())[1])
            except Exception as ex:  # noqa: BLE001
                verif.append({"arquivo": origem, "ano": ano, "problema": f"dados ilegíveis: {ex!r}"})
        if not dfs:
            continue
        s = pd.concat(dfs).sort_values("time_utc")
        ndup = int(s.duplicated("time_utc").sum())
        s = s.drop_duplicates("time_utc")
        q = {"codigo": e.codigo, "duplicidades": ndup, "primeiro_dado": s["time_utc"].min(),
             "ultimo_dado": s["time_utc"].max()}
        for v, (lo, hi) in LIMITES.items():
            fora = s[v].notna() & ~s[v].between(lo, hi)
            q[f"n_fora_limites_{v}"] = int(fora.sum())
            s.loc[fora, v] = np.nan
        qcs.append(q)
        s.to_parquet(out / f"{e.codigo}.parquet", index=False)
        # 4. % de horas válidas por safra (set-abr)
        r = s.set_index("time_utc").reindex(saf.index)
        g = r.notna().groupby(saf.values)
        pv = g[["T", "UR", "u10", "precip"]].mean() * 100
        pv.index.name = "safra_ini"
        pv = pv.reset_index().rename(columns={"T": "pct_validas_T", "UR": "pct_validas_UR",
                                              "u10": "pct_validas_vento", "precip": "pct_validas_chuva"})
        pv["codigo"] = e.codigo
        linhas_saf.append(pv)
    S = pd.concat(linhas_saf, ignore_index=True)
    S["safra_ini"] = S["safra_ini"].astype(int)
    S["safra"] = S["safra_ini"].astype(str) + "/" + (S["safra_ini"] + 1).astype(str).str[2:]
    S["safra_valida"] = S[["pct_validas_T", "pct_validas_UR", "pct_validas_vento"]].min(axis=1) >= 100 * MIN_SAFRA
    S.round(2).to_csv(PROC / "inmet_safras.csv", index=False, encoding="utf-8-sig")
    Q = pd.DataFrame(qcs)

    # 5. inventário
    sv = S[S["safra_valida"]].groupby("codigo")
    est["n_safras_validas"] = est["codigo"].map(sv.size()).fillna(0).astype(int)
    est["safras_validas"] = est["codigo"].map(sv["safra"].agg(lambda x: ", ".join(x))).fillna("")
    com = S.groupby("codigo")
    for v in ("T", "UR", "vento", "chuva"):
        # % de horas válidas no conjunto das safras em que a estação operava (>0 % em T)
        op = S[S["pct_validas_T"] > 0].groupby("codigo")[f"pct_validas_{v}"].mean()
        est[f"pct_validas_{v}"] = est["codigo"].map(op)
    est = est.merge(Q, on="codigo", how="left")
    est["ano_inicio"] = est["data_fundacao"].dt.year.fillna(est["primeiro_dado"].dt.year).astype("Int64")
    est["usada_na_validacao"] = est["dentro_30km"] & (est["n_safras_validas"] >= 1)
    est["incluida_na_media"] = est["dentro_30km"] & (est["n_safras_validas"] >= MIN_SAFRAS_MEDIA)
    cols = ["codigo", "estacao", "uf", "municipio", "dist_km", "dentro_30km", "lat", "lon", "alt",
            "alt_municipio", "data_fundacao", "ano_inicio", "primeiro_dado", "ultimo_dado",
            "n_safras_validas", "safras_validas", "pct_validas_T", "pct_validas_UR", "pct_validas_vento",
            "pct_validas_chuva", "usada_na_validacao", "incluida_na_media", "duplicidades",
            "n_fora_limites_T", "n_fora_limites_UR", "n_fora_limites_u10", "n_fora_limites_precip",
            "grupo_origem"]
    est = est[cols]
    est["data_fundacao"] = est["data_fundacao"].dt.strftime("%Y-%m-%d")
    for c in ("primeiro_dado", "ultimo_dado"):
        est[c] = est[c].dt.strftime("%Y-%m-%d %H:%M UTC")
    est.round(3).to_csv(TAB / "T_inventario_inmet.csv", index=False, encoding="utf-8-sig")
    V = pd.DataFrame(verif, columns=["arquivo", "ano", "problema"])
    V.to_csv(PROC / "inmet_arquivos_com_problema.csv", index=False, encoding="utf-8-sig")
    print(f"\nEstações no inventário: {len(est)} (PR + vizinhas a até {RAIO_KM:.0f} km)")
    print(est[["codigo", "estacao", "uf", "municipio", "dist_km", "ano_inicio", "n_safras_validas",
               "pct_validas_T", "pct_validas_vento", "usada_na_validacao", "incluida_na_media"]]
          .round(1).to_string(index=False))


if __name__ == "__main__":
    main()
