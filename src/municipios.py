"""Lista de municípios produtores de soja do Paraná e suas coordenadas.

Coordenadas (lat, lon, altitude) vêm da API de geocodificação do Open-Meteo,
filtradas pelo estado do Paraná. O código IBGE vem do geobr (malha 2020).

Uso:  python src/municipios.py
Saída: data/processed/municipios.csv
"""
from __future__ import annotations

import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed" / "municipios.csv"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

MUNICIPIOS = [
    ("Cascavel", "Oeste"),
    ("Toledo", "Oeste"),
    ("Assis Chateaubriand", "Oeste"),
    ("Guarapuava", "Centro-Sul"),
    ("Ponta Grossa", "Campos Gerais"),
    ("Castro", "Campos Gerais"),
    ("Tibagi", "Campos Gerais"),
    ("Londrina", "Norte Central"),
    ("Cornélio Procópio", "Norte Pioneiro"),
    ("Campo Mourão", "Centro-Ocidental"),
    ("Ubiratã", "Centro-Ocidental"),
    ("Pato Branco", "Sudoeste"),
    ("Palmas", "Sudoeste"),
    ("Umuarama", "Noroeste"),
    ("Ivaiporã", "Norte Central"),
    ("Maringá", "Norte Central"),
]
# Ampliação: municípios do zoneamento agroclimático do Oeste
MUNICIPIOS_OESTE = [
    ("São Pedro do Iguaçu", "Oeste"),
    ("Marechal Cândido Rondon", "Oeste"),
    ("Medianeira", "Oeste"),
    ("São Miguel do Iguaçu", "Oeste"),
    ("Foz do Iguaçu", "Oeste"),
    ("Matelândia", "Oeste"),
    ("Santa Helena", "Oeste"),
    ("Guaíra", "Oeste"),
]
TODOS = ([(n, r, "estado") for n, r in MUNICIPIOS]
         + [(n, r, "zoneamento_oeste") for n, r in MUNICIPIOS_OESTE])


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.lower().replace("-", " ").strip()


def geocode(nome: str) -> dict:
    r = requests.get(
        GEOCODE_URL,
        params={"name": nome, "country": "BR", "count": 20, "language": "pt", "format": "json"},
        timeout=30,
    )
    r.raise_for_status()
    results = r.json().get("results") or []
    cand = [
        x for x in results
        if norm(x.get("admin1", "")) == "parana" and norm(x["name"]) == norm(nome)
    ]
    if not cand:
        raise RuntimeError(f"Geocodificação sem resultado no Paraná para '{nome}'. "
                           f"Retornados: {[(x['name'], x.get('admin1')) for x in results]}")
    # Prefere a sede municipal (PPLA2/PPLA/PPL) com maior população
    cand.sort(key=lambda x: (x.get("feature_code", "").startswith("PPLA"), x.get("population") or 0),
              reverse=True)
    best = cand[0]
    return {
        "lat": best["latitude"],
        "lon": best["longitude"],
        "altitude_m": best.get("elevation"),
        "geocode_id": best.get("id"),
        "feature_code": best.get("feature_code"),
    }


def codigos_ibge() -> dict[str, int]:
    import geobr
    gdf = geobr.read_municipality(code_muni="PR", year=2020)
    return {norm(n): int(c) for n, c in zip(gdf["name_muni"], gdf["code_muni"])}


def main() -> None:
    # Municípios já presentes no CSV são mantidos sem nova geocodificação,
    # para que as coordenadas (e os downloads já feitos) não mudem.
    existentes = pd.read_csv(OUT, encoding="utf-8") if OUT.exists() else pd.DataFrame()
    ja = set(existentes["municipio"]) if len(existentes) else set()
    linhas = []
    for nome, meso, grupo in TODOS:
        if nome in ja:
            continue
        g = geocode(nome)
        linhas.append({"municipio": nome, "regiao": meso, **g})
        print(f"  {nome:24s} lat={g['lat']:.4f} lon={g['lon']:.4f} alt={g['altitude_m']} "
              f"({g['feature_code']})")
        time.sleep(0.3)
    novos = pd.DataFrame(linhas)
    if len(novos):
        ibge = codigos_ibge()
        novos.insert(1, "cod_ibge",
                     novos["municipio"].map(lambda n: ibge.get(norm(n))).astype("Int64"))
        faltando = novos.loc[novos["cod_ibge"].isna(), "municipio"].tolist()
        if faltando:
            sys.exit(f"Código IBGE não encontrado para: {faltando}")
    df = pd.concat([existentes, novos], ignore_index=True)
    grupo = {n: g for n, _, g in TODOS}
    df["grupo_origem"] = df["municipio"].map(grupo)
    ordem = {n: i for i, (n, _, _) in enumerate(TODOS)}
    df = df.sort_values("municipio", key=lambda s: s.map(ordem)).reset_index(drop=True)
    if df["cod_ibge"].duplicated().any():
        sys.exit("Código IBGE duplicado")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, encoding="utf-8")
    print(f"\nSalvo: {OUT} ({len(df)} municípios)")


if __name__ == "__main__":
    main()
