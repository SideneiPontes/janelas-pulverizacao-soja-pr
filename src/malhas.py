"""Malhas do Paraná (IBGE 2020, versão simplificada do geobr) com cache no projeto.

O geobr consulta a API do GitHub a cada sessão para listar os arquivos, e a cota anônima
(60 consultas/hora) pode estourar. Aqui as malhas do PR são guardadas em
data/processed/malhas/*.gpkg na 1ª leitura e reutilizadas depois. Se o geobr falhar, os
mesmos arquivos são baixados direto do release (ipea/geobr_prep_data v2.0.0), que não usa a API.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import geopandas as gpd
import requests

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "processed" / "malhas"
RELEASE = "https://github.com/ipea/geobr_prep_data/releases/download/v2.0.0/{}.parquet"


def _release(nome: str) -> gpd.GeoDataFrame:
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / f"{nome}.parquet"
        r = requests.get(RELEASE.format(nome), timeout=300)
        r.raise_for_status()
        f.write_bytes(r.content)
        return gpd.read_parquet(f)


def malhas_pr() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    fe, fm = DIR / "pr_estado_2020.gpkg", DIR / "pr_municipios_2020.gpkg"
    if fe.exists() and fm.exists():
        return gpd.read_file(fe), gpd.read_file(fm)
    DIR.mkdir(parents=True, exist_ok=True)
    try:
        import geobr
        uf = geobr.read_state(code_state="PR", year=2020)
        mun = geobr.read_municipality(code_muni="PR", year=2020)
    except Exception:  # cota da API do GitHub / rede: usa o arquivo do release
        uf = _release("states_2020_simplified")
        uf = uf[uf["abbrev_state"] == "PR"].reset_index(drop=True)
        mun = _release("municipalities_2020_simplified")
        mun = mun[mun["abbrev_state"] == "PR"].reset_index(drop=True)
    mun["code_muni"] = mun["code_muni"].astype(int)
    uf.to_file(fe, driver="GPKG")
    mun.to_file(fm, driver="GPKG")
    return uf, mun
