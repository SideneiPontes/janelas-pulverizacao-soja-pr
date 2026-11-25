"""Baixa os dados históricos anuais do INMET (estações automáticas) e extrai as do Paraná.

Fonte: https://portal.inmet.gov.br/dadoshistoricos  (arquivos uploads/dadoshistoricos/<ano>.zip)
- Os zips (~100 MB/ano) ficam FORA do projeto (padrão: %TEMP%/inmet_zips, ou a variável
  de ambiente INMET_ZIP_DIR), para não sobrecarregar o OneDrive.
- Só os CSVs das estações do PR são extraídos para data/raw/inmet/<ano>/.
- Arquivos já existentes são pulados (permite retomar).

Uso:  python src/download_inmet.py [ano_ini ano_fim]   (padrão 2010 2024)
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "raw" / "inmet"
ZIPS = Path(os.environ.get("INMET_ZIP_DIR", Path(tempfile.gettempdir()) / "inmet_zips"))
URL = "https://portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; pesquisa-academica)"}


SESSAO = requests.Session()
SESSAO.headers.update(HEADERS)
MAX_TENTATIVAS = 6   # o servidor derruba conexões; cada tentativa CONTINUA de onde parou.
# Muitas tentativas seguidas fazem o firewall do INMET bloquear o IP por algumas horas.
PAUSA_ENTRE_ANOS_S = 90


def baixar(ano: int) -> Path:
    z = ZIPS / f"{ano}.zip"
    if z.exists() and zipfile.is_zipfile(z):
        return z
    ZIPS.mkdir(parents=True, exist_ok=True)
    tmp = z.with_suffix(".part")
    total = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        ja = tmp.stat().st_size if tmp.exists() else 0
        try:
            if total is None:
                total = int(SESSAO.head(URL.format(ano=ano), timeout=60,
                                        allow_redirects=True).headers["Content-Length"])
            if ja < total:
                cab = {"Range": f"bytes={ja}-"} if ja else {}
                with SESSAO.get(URL.format(ano=ano), headers=cab, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    if ja and r.status_code != 206:  # servidor ignorou o Range: recomeça
                        ja = 0
                    with open(tmp, "ab" if ja else "wb") as f:
                        for bloco in r.iter_content(1 << 20):
                            f.write(bloco)
            if tmp.stat().st_size != total:
                raise IOError(f"incompleto: {tmp.stat().st_size / 1e6:.0f}/{total / 1e6:.0f} MB")
            if not zipfile.is_zipfile(tmp):
                tmp.unlink()
                raise IOError("zip corrompido; recomeçando do zero")
            tmp.replace(z)
            return z
        except (requests.RequestException, IOError, KeyError) as e:
            agora = tmp.stat().st_size / 1e6 if tmp.exists() else 0
            espera = 120 * tentativa  # 2, 4, 6... min
            print(f"  {ano}: tentativa {tentativa}/{MAX_TENTATIVAS} interrompida "
                  f"({agora:.0f} MB até agora; {str(e)[:90]}); retomando em {espera}s", flush=True)
            time.sleep(espera)
    sys.exit(f"ERRO: não foi possível baixar {ano}.zip após {MAX_TENTATIVAS} tentativas")


def extrair_pr(z: Path, ano: int) -> int:
    destino = DEST / str(ano)
    destino.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(z) as zf:
        for info in zf.infolist():
            nome = Path(info.filename).name  # ignora subpastas do zip (evita path traversal)
            if "_PR_" not in nome.upper() or not nome.upper().endswith(".CSV"):
                continue
            alvo = destino / nome
            if not alvo.exists():
                alvo.write_bytes(zf.read(info))
            n += 1
    return n


def main() -> None:
    a0, a1 = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) == 3 else (2010, 2024)
    print(f"zips em: {ZIPS}")
    for ano in range(a0, a1 + 1):
        ja_tinha = (ZIPS / f"{ano}.zip").exists()
        z = baixar(ano)
        if not ja_tinha and ano < a1:
            time.sleep(PAUSA_ENTRE_ANOS_S)  # espaça os downloads para não acionar o firewall
        n = extrair_pr(z, ano)
        print(f"  {ano}: {z.stat().st_size / 1e6:.0f} MB, {n} estações do PR", flush=True)
        if n == 0:
            sys.exit(f"ERRO: nenhuma estação do PR encontrada em {ano}.zip")
    print("Concluído.")


if __name__ == "__main__":
    main()
