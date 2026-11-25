"""Resumo dos parquets ERA5 em data/raw/: linhas, período e valores faltantes.

Uso:  python src/verificar_raw.py
Saída: impressa na tela e em outputs/tables/verificacao_raw.csv
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "outputs" / "tables" / "verificacao_raw.csv"
VARIAVEIS = [
    "temperature_2m", "relative_humidity_2m", "dew_point_2m", "precipitation",
    "wind_speed_10m", "wind_gusts_10m", "shortwave_radiation", "is_day",
]
ESPERADO = len(pd.date_range("2000-01-01", "2026-05-01", freq="D")) * 24  # horas de 2000-01-01 a 2026-05-01 (local)


def main() -> None:
    muns = pd.read_csv(ROOT / "data" / "processed" / "municipios.csv", encoding="utf-8")
    linhas = []
    for f in sorted(RAW.glob("*.parquet")):
        df = pd.read_parquet(f)
        horas = df["time_utc"].diff().dropna()
        linhas.append({
            "arquivo": f.name,
            "municipio": df["municipio"].iloc[0],
            "linhas": len(df),
            "esperado": ESPERADO,
            "inicio_local": df["time_local"].min(),
            "fim_local": df["time_local"].max(),
            "buracos_tempo": int((horas != pd.Timedelta(hours=1)).sum()),
            "duplicatas_tempo": int(df["time_utc"].duplicated().sum()),
            **{f"na_{v}": int(df[v].isna().sum()) for v in VARIAVEIS},
        })
    res = pd.DataFrame(linhas)
    res["na_total"] = res[[f"na_{v}" for v in VARIAVEIS]].sum(axis=1)

    faltam = set(muns["municipio"]) - set(res["municipio"]) if len(res) else set(muns["municipio"])
    pd.set_option("display.width", 200)
    print(res[["municipio", "linhas", "esperado", "buracos_tempo", "duplicatas_tempo", "na_total"]]
          .to_string(index=False))
    print(f"\nArquivos: {len(res)}/{len(muns)}")
    if faltam:
        print(f"Municípios sem arquivo: {sorted(faltam)}")
    nas = res.loc[res["na_total"] > 0, ["municipio"] + [f"na_{v}" for v in VARIAVEIS]]
    if len(nas):
        print("\nValores faltantes por variável:")
        print(nas.loc[:, (nas != 0).any()].to_string(index=False))
    else:
        print("Nenhum valor faltante em nenhuma variável.")
    # Células da grade ERA5 (0,25°) usadas por cada município
    cel = pd.DataFrame([pd.read_parquet(f, columns=["municipio", "grid_lat", "grid_lon",
                                                    "grid_elevation"]).iloc[0]
                        for f in sorted(RAW.glob("*.parquet"))])
    res = res.merge(cel, on="municipio")
    res["celula"] = res["grid_lat"].astype(str) + ", " + res["grid_lon"].astype(str)
    rep = res.groupby("celula")["municipio"].agg(list)
    rep = rep[rep.str.len() > 1]
    print(f"\nCélulas ERA5 distintas: {res['celula'].nunique()} para {len(res)} municípios")
    if len(rep):
        print("Municípios na MESMA célula (séries idênticas):")
        for c, ms in rep.items():
            print(f"  ({c}): {', '.join(ms)}")
    else:
        print("Nenhum município compartilha célula.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT, index=False, encoding="utf-8")
    print(f"\nTabela salva em {OUT}")


if __name__ == "__main__":
    main()
