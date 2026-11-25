"""Baixa dados HORÁRIOS da reanálise ERA5 via API histórica do Open-Meteo.

- Período: 1995-01-01 a 2024-12-31, em blocos de 5 anos por município.
- Variáveis: ver VARIAVEIS.
- timezone=America/Sao_Paulo, wind_speed_unit=kmh, models=era5.
- Pausa de 1 s entre chamadas; até 5 tentativas com espera crescente
  em caso de HTTP 429 ou erro de rede.
- Cada bloco é salvo em data/raw/_blocos/ (permite retomar sem perder
  progresso); ao completar os 6 blocos, gera data/raw/<cod_ibge>_<slug>.parquet.
- Se o parquet final já existir, o município é pulado.

O tempo é pedido em unixtime (UTC) para evitar ambiguidade nas horas de
horário de verão (vigente no Brasil até 2019). O parquet guarda
`time_utc` e `time_local` (America/Sao_Paulo, com fuso).

Uso:  python src/download_era5.py
"""
from __future__ import annotations

import json
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
BLOCOS = RAW / "_blocos"
MUNICIPIOS_CSV = ROOT / "data" / "processed" / "municipios.csv"

URL = "https://archive-api.open-meteo.com/v1/archive"
VARIAVEIS = [
    "temperature_2m", "relative_humidity_2m", "dew_point_2m", "precipitation",
    "wind_speed_10m", "wind_gusts_10m", "shortwave_radiation", "is_day",
]
TZ = "America/Sao_Paulo"
PERIODOS = [(f"{a}-01-01", f"{a + 4}-12-31") for a in range(1995, 2025, 5)]
PAUSA_S = 1.0
MAX_TENTATIVAS = 5
ESPERA_BASE_S = 30  # 30, 60, 120, 240 s entre tentativas


class DownloadError(RuntimeError):
    pass


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.lower().replace(" ", "_")


def requisitar(params: dict) -> dict:
    ultimo_erro = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            r = requests.get(URL, params=params, timeout=180)
            if r.status_code == 429:
                ultimo_erro = f"HTTP 429: {r.text[:300]}"
            elif r.status_code != 200:
                # Erros 4xx/5xx que não são limite de taxa: não adianta repetir
                raise DownloadError(f"HTTP {r.status_code}: {r.text[:500]}")
            else:
                return r.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            ultimo_erro = f"Erro de rede: {e!r}"
        if tentativa < MAX_TENTATIVAS:
            espera = ESPERA_BASE_S * 2 ** (tentativa - 1)
            print(f"    tentativa {tentativa}/{MAX_TENTATIVAS} falhou ({ultimo_erro[:120]}); "
                  f"aguardando {espera}s", flush=True)
            time.sleep(espera)
    raise DownloadError(f"Falhou após {MAX_TENTATIVAS} tentativas. Último erro: {ultimo_erro}")


def baixar_bloco(mun: pd.Series, inicio: str, fim: str) -> Path:
    destino = BLOCOS / f"{mun.cod_ibge}_{inicio[:4]}_{fim[:4]}.parquet"
    if destino.exists():
        return destino
    params = {
        "latitude": mun.lat, "longitude": mun.lon,
        "start_date": inicio, "end_date": fim,
        "hourly": ",".join(VARIAVEIS),
        "models": "era5", "timezone": TZ, "wind_speed_unit": "kmh",
        "timeformat": "unixtime",
    }
    js = requisitar(params)
    h = js.get("hourly")
    if not h or "time" not in h:
        raise DownloadError(f"Resposta sem bloco 'hourly': {json.dumps(js)[:500]}")
    faltam = [v for v in VARIAVEIS if v not in h]
    if faltam:
        raise DownloadError(f"Variáveis ausentes na resposta: {faltam}")

    df = pd.DataFrame({v: h[v] for v in VARIAVEIS})
    t = pd.to_datetime(h["time"], unit="s", utc=True)
    df.insert(0, "time_utc", t)
    df.insert(1, "time_local", t.tz_convert(TZ))
    # metadados da célula usada pela API
    df["grid_lat"] = js.get("latitude")
    df["grid_lon"] = js.get("longitude")
    df["grid_elevation"] = js.get("elevation")
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(destino)
    return destino


def main() -> None:
    muns = pd.read_csv(MUNICIPIOS_CSV, encoding="utf-8")
    RAW.mkdir(parents=True, exist_ok=True)
    for _, mun in muns.iterrows():
        final = RAW / f"{mun.cod_ibge}_{slug(mun.municipio)}.parquet"
        if final.exists():
            print(f"[pula] {mun.municipio}: {final.name} já existe", flush=True)
            continue
        print(f"[baixa] {mun.municipio} ({mun.lat:.4f}, {mun.lon:.4f})", flush=True)
        partes = []
        for inicio, fim in PERIODOS:
            ja_tinha = (BLOCOS / f"{mun.cod_ibge}_{inicio[:4]}_{fim[:4]}.parquet").exists()
            try:
                p = baixar_bloco(mun, inicio, fim)
            except DownloadError as e:
                print(f"\nERRO em {mun.municipio} {inicio}..{fim}: {e}", flush=True)
                print("Download interrompido. Blocos já baixados estão em data/raw/_blocos/; "
                      "rode o script novamente para retomar.", flush=True)
                sys.exit(1)
            partes.append(p)
            print(f"    {inicio}..{fim} {'(cache)' if ja_tinha else 'ok'}", flush=True)
            if not ja_tinha:
                time.sleep(PAUSA_S)
        df = pd.concat([pd.read_parquet(p) for p in partes], ignore_index=True)
        df = df.sort_values("time_utc").drop_duplicates("time_utc").reset_index(drop=True)
        df.insert(0, "cod_ibge", mun.cod_ibge)
        df.insert(1, "municipio", mun.municipio)
        tmp = final.with_suffix(".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(final)
        print(f"    -> {final.name}: {len(df):,} linhas", flush=True)
    print("\nConcluído.")


if __name__ == "__main__":
    main()
