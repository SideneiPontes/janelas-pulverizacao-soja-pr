"""AHP-TOPSIS: estratégias para ampliar a janela de pulverização no período de fungicidas.

Uso:  python src/ahp_topsis.py

Entradas
  data/raw/*.parquet                       (ERA5 horário, para recalcular C1)
  config/ahp_criterios.csv                 (comparação par a par, EDITÁVEL)
  outputs/tables/matriz_decisao_qualitativa.xlsx  (notas 1-9 de C2-C5, EDITÁVEL)
  -> os dois arquivos editáveis só são criados se não existirem (nunca sobrescritos).
Saídas
  outputs/tables/T8_ganho_horas_alternativas.csv, T9_pesos_ahp.csv, T10_topsis.csv,
  T11_sensibilidade.csv; outputs/figures/F6_sensibilidade_topsis.png

C1 - ganho de horas no período de fungicidas (16/dez até o fim de fevereiro)
-----------------------------------------------------------------------------
Medida-base = HORAS UTILIZÁVEIS: horas aptas (critério A) dentro de janelas de
>= 2 h consecutivas entre 06h e 20h locais (mesma definição do "dia apto").
Ganho de cada alternativa = horas utilizáveis com a alternativa - horas-base,
por safra (26 safras, 2000/01 a 2025/26), média entre safras. Suposições:
  A1 noturna: soma as horas aptas (critério A) com is_day = 0 que estão em
     sequências >= 2 h e que NÃO estão nas janelas diurnas de 06-20 h.
  A2 pontas antideriva: vento a 2 m entre 3 e 15 km/h (em vez de 3-10).
  A3 adjuvante: chuva < 1 mm só na 1ª hora após a aplicação (em vez de 2 h).
  A4 drone: vento a 2 m entre 0 e 8 km/h e Delta T entre 2 e 10 °C (demais iguais).
     O ganho pode ser negativo (o limite superior de vento fica mais restrito).
  A5 estação + SSD: SUPOSIÇÃO - com previsão local confiável, o operador se
     posiciona para usar horas aptas ISOLADAS (sequências de 1 h entre 06-20 h),
     que hoje não formam janela; ganho = número dessas horas.
  A6 capacidade operacional: ganho = 0 h (não muda o tempo). Como proxy do maior
     aproveitamento, T8 informa o nº médio de janelas >= 2 h por dia na fase.
O TOPSIS usa o C1 da média do Paraná (16 municípios originais, média por célula
ERA5); a média do Oeste é rodada como variante.
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indicadores import N_SAFRAS, SAFRAS  # noqa: E402
from indicadores import (AGREG, ESTADO, FATOR_U2, OESTE, PROC, RAW, TAB, bulbo_umido_stull,  # noqa: E402
                         configurar_agregados, janelas, media_por_celula)

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config"
FIG = ROOT / "outputs" / "figures"
AHP_CSV = CFG / "ahp_criterios.csv"
XLSX = TAB / "matriz_decisao_qualitativa.xlsx"
TZ = "America/Sao_Paulo"

ALTERNATIVAS = {
    "A1": "Pulverização noturna",
    "A2": "Pontas de indução de ar (antideriva)",
    "A3": "Adjuvante que reduz o tempo mínimo sem chuva",
    "A4": "Pulverização com drone",
    "A5": "Estação meteorológica + sistema de suporte à decisão",
    "A6": "Aumento da capacidade operacional (mais pulverizadores/terceirização)",
}
CRITERIOS = {
    "C1": ("Ganho de horas aptas no período de fungicidas", "beneficio"),
    "C2": ("Custo de implantação", "custo"),
    "C3": ("Risco ambiental, à saúde e de deriva", "custo"),
    "C4": ("Facilidade de adoção e inclusão de pequenos produtores", "beneficio"),
    "C5": ("Conformidade regulatória e segurança do aplicador", "beneficio"),
}
RI_SAATY = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45}

# Cenários de pesos (C1..C5) para T10b/F6b; None = pesos do AHP (T9)
CENARIOS_PESOS = {
    "base_AHP": None,
    "pequeno_produtor": [0.25, 0.25, 0.15, 0.25, 0.10],
    "ambiental_saude": [0.20, 0.10, 0.35, 0.10, 0.25],
    "pesos_iguais": [0.20, 0.20, 0.20, 0.20, 0.20],
}
ROTULO_CENARIO = {"base_AHP": "Base (pesos AHP)", "pequeno_produtor": "Pequeno produtor",
                  "ambiental_saude": "Ambiental e saúde", "pesos_iguais": "Pesos iguais"}

# Critério A (base) e variações. Vento = u2 (km/h); DeltaT em °C.
BASE = dict(dt_min=2, dt_max=8, u_min=3, u_max=10, t_max=30, ur_min=50, chuva_pos="2h")
VARIANTES = {
    "A2": dict(BASE, u_max=15),
    "A3": dict(BASE, chuva_pos="1h"),
    "A4": dict(BASE, u_min=0, u_max=8, dt_max=10),
}

# Notas provisórias (1-9). C2 e C3: 9 = custo/risco MUITO ALTO (critérios "menor melhor").
# C4 e C5: 9 = MUITO fácil / MUITO conforme ("maior melhor").
NOTAS_PROVISORIAS = {
    "A1": (2, 6, 6, 4, "Custo baixo (iluminação, turno); inversão térmica noturna eleva risco de deriva; "
                       "segurança do operador e restrições de bula à noite."),
    "A2": (2, 2, 8, 9, "Troca de pontas barata; reduz deriva; amplamente recomendada."),
    "A3": (3, 3, 8, 7, "Custo por aplicação; eficácia depende do produto/registro."),
    "A4": (8, 5, 3, 4, "Equipamento caro; gotas finas e deriva; exige operador habilitado e "
                       "cumprimento da regulamentação de aeronaves remotamente pilotadas."),
    "A5": (5, 1, 5, 9, "Estação + assinatura/SSD; não aumenta risco; requer capacitação."),
    "A6": (9, 3, 3, 7, "Alto investimento ou dependência de terceiros; pouco acessível a pequenos."),
}
# Matriz AHP provisória (linha i comparada à coluna j, escala de Saaty).
AHP_PROVISORIA = [
    ["1", "3", "2", "3", "2"],
    ["1/3", "1", "1/2", "1", "1/2"],
    ["1/2", "2", "1", "2", "1"],
    ["1/3", "1", "1/2", "1", "1/2"],
    ["1/2", "2", "1", "2", "1"],
]


# ----------------------------------------------------------------------------
# C1: recálculo das horas utilizáveis
# ----------------------------------------------------------------------------
def apta(h: pd.DataFrame, p: dict) -> pd.Series:
    pos = h["p_t2"] + h["p_t3"] if p["chuva_pos"] == "2h" else h["p_t2"]
    ok = (h["deltaT"].between(p["dt_min"], p["dt_max"]) & h["u2"].between(p["u_min"], p["u_max"])
          & (h["T"] < p["t_max"]) & (h["UR"] >= p["ur_min"]) & (h["p_t1"] == 0) & (pos < 1))
    return ok & h["p_t3"].notna()


def runs(m: pd.Series) -> pd.Series:
    """Tamanho da sequência de True a que cada hora pertence (0 se False)."""
    rid = (m != m.shift()).cumsum()
    return m.groupby(rid).transform("sum").where(m, 0)


def horas_municipio(f: Path) -> pd.DataFrame:
    df = pd.read_parquet(f).sort_values("time_utc").reset_index(drop=True)
    h = pd.DataFrame({"municipio": df["municipio"], "T": df["temperature_2m"],
                      "UR": df["relative_humidity_2m"], "is_day": df["is_day"]})
    h["u2"] = df["wind_speed_10m"] * FATOR_U2
    h["deltaT"] = h["T"] - bulbo_umido_stull(h["T"].to_numpy(), h["UR"].to_numpy())
    p = df["precipitation"]
    h["p_t1"], h["p_t2"], h["p_t3"] = p.shift(-1), p.shift(-2), p.shift(-3)
    loc = df["time_local"]
    h["hora_local"] = loc.dt.hour
    h["data"] = loc.dt.tz_localize(None).dt.normalize()

    base = apta(h, BASE)
    jan_base = janelas(base, h["hora_local"])
    out = pd.DataFrame({"municipio": h["municipio"], "data": h["data"]})
    out["base"] = jan_base
    for a, par in VARIANTES.items():
        out[a] = janelas(apta(h, par), h["hora_local"])
    noite = base & (h["is_day"] == 0)
    out["A1_extra"] = noite & (runs(noite) >= 2) & ~jan_base
    diurna = base & h["hora_local"].between(6, 19)
    out["A5_extra"] = diurna & (runs(diurna) == 1)
    # A6 proxy: nº de janelas (sequências >= 2 h em 06-19 h) por dia
    out["inicio_janela"] = jan_base & ~jan_base.shift(fill_value=False)

    # período de fungicidas (16/dez - fim de fev) e safra
    m, d, y = out["data"].dt.month, out["data"].dt.day, out["data"].dt.year
    fase = ((m == 12) & (d >= 16)) | (m == 1) | (m == 2)
    out["safra_ini"] = np.where(m == 12, y, y - 1)
    out = out[fase & out["safra_ini"].between(SAFRAS[0], SAFRAS[-1])]

    cols = ["base", "A2", "A3", "A4", "A1_extra", "A5_extra", "inicio_janela"]
    s = out.groupby(["municipio", "safra_ini"])[cols].sum()
    s["dias"] = out.groupby(["municipio", "safra_ini"])["data"].nunique()
    return s.reset_index()


def tabela_T8(muns_df: pd.DataFrame) -> pd.DataFrame:
    partes = []
    for _, r in muns_df.iterrows():
        partes.append(horas_municipio(next(RAW.glob(f"{r.cod_ibge}_*.parquet"))))
        print(f"  C1: {r.municipio}", flush=True)
    s = pd.concat(partes, ignore_index=True)
    assert s.groupby("municipio")["safra_ini"].nunique().eq(N_SAFRAS).all()

    # horas utilizáveis com cada alternativa (por safra)
    s["util_A1"] = s["base"] + s["A1_extra"]
    s["util_A2"], s["util_A3"], s["util_A4"] = s["A2"], s["A3"], s["A4"]
    s["util_A5"] = s["base"] + s["A5_extra"]
    s["util_A6"] = s["base"]
    s["janelas_por_dia"] = s["inicio_janela"] / s["dias"]
    vals = ["base"] + [f"util_{a}" for a in ALTERNATIVAS] + ["janelas_por_dia"]
    s = s.rename(columns={"safra_ini": "safra"})
    regs = []
    for nome, membros in AGREG.items():
        e = media_por_celula(s[s["municipio"].isin(membros)], ["safra"], vals)
        e["municipio"] = nome
        regs.append(e)
    s = pd.concat([s[["municipio", "safra"] + vals]] + regs, ignore_index=True)

    linhas = []
    for mun, g in s.groupby("municipio", sort=False):
        for a, nome in ALTERNATIVAS.items():
            ganho = g[f"util_{a}"] - g["base"]
            linhas.append({
                "municipio": mun, "alternativa": a, "descricao": nome,
                "horas_utilizaveis_base": g["base"].mean(),
                "horas_utilizaveis_alternativa": g[f"util_{a}"].mean(),
                "ganho_h_media": ganho.mean(), "ganho_h_dp": ganho.std(),
                "ganho_pct": 100 * ganho.mean() / g["base"].mean(),
                "proxy_janelas_2h_por_dia": g["janelas_por_dia"].mean() if a == "A6" else np.nan,
            })
    t = pd.DataFrame(linhas)
    ordem = muns_df["municipio"].tolist() + list(AGREG)
    t["municipio"] = pd.Categorical(t["municipio"], ordem, ordered=True)
    return t.sort_values(["municipio", "alternativa"]).round(3)


# ----------------------------------------------------------------------------
# Arquivos editáveis (criados só se não existirem)
# ----------------------------------------------------------------------------
def criar_ahp_csv():
    if AHP_CSV.exists():
        return False
    CFG.mkdir(parents=True, exist_ok=True)
    cods = list(CRITERIOS)
    with open(AHP_CSV, "w", encoding="utf-8", newline="") as f:
        f.write("# PROVISÓRIO - matriz de comparação par a par dos critérios (escala de Saaty 1-9).\n")
        f.write("# Célula (linha i, coluna j) = importância de i em relação a j; use frações como 1/3.\n")
        f.write("# Mantenha a recíproca: (j,i) = 1/(i,j). Diagonal = 1. "
                "C1 ganho de horas; C2 custo; C3 risco; C4 facilidade/inclusão; C5 conformidade.\n")
        f.write("criterio," + ",".join(cods) + "\n")
        for c, linha in zip(cods, AHP_PROVISORIA):
            f.write(c + "," + ",".join(linha) + "\n")
    return True


def ler_ahp() -> tuple[np.ndarray, bool]:
    txt = AHP_CSV.read_text(encoding="utf-8")
    provisorio = "PROVISÓRIO" in txt.upper()
    df = pd.read_csv(AHP_CSV, comment="#", dtype=str, encoding="utf-8").set_index("criterio")
    df = df.loc[list(CRITERIOS), list(CRITERIOS)]
    A = df.map(lambda v: float(Fraction(v.strip()))).to_numpy()
    n = len(A)
    if not np.allclose(np.diag(A), 1):
        sys.exit("AHP: a diagonal deve ser 1.")
    if not np.allclose(A * A.T, np.ones((n, n)), rtol=1e-3):
        sys.exit("AHP: matriz não recíproca: (j,i) deve ser 1/(i,j).")
    return A, provisorio


def criar_xlsx():
    if XLSX.exists():
        return False
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "notas"
    cab = ["codigo", "alternativa", "C2_custo", "C3_risco", "C4_facilidade_inclusao",
           "C5_conformidade_seguranca", "status", "justificativa"]
    ws.append(cab)
    vermelho = PatternFill("solid", fgColor="F8D7DA")
    for a, nome in ALTERNATIVAS.items():
        c2, c3, c4, c5, just = NOTAS_PROVISORIAS[a]
        ws.append([a, nome, c2, c3, c4, c5, "PROVISÓRIO", just])
        for col in range(3, 8):
            ws.cell(ws.max_row, col).fill = vermelho
    for c in ws[1]:
        c.font = Font(bold=True)
    for col, w in zip("ABCDEFGH", [8, 62, 10, 10, 22, 26, 13, 90]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "C2"

    info = wb.create_sheet("LEIA-ME", 0)
    linhas = [
        "MATRIZ DE DECISÃO QUALITATIVA - NOTAS PROVISÓRIAS (preencher e trocar status para FINAL)",
        "",
        "Escala 1 a 9 para cada alternativa (aba 'notas'):",
        "  C2 custo de implantação:        1 = muito baixo ... 9 = muito alto   (critério 'menor melhor')",
        "  C3 risco ambiental/saúde/deriva: 1 = muito baixo ... 9 = muito alto   (critério 'menor melhor')",
        "  C4 facilidade de adoção/inclusão: 1 = muito difícil ... 9 = muito fácil (critério 'maior melhor')",
        "  C5 conformidade e segurança:     1 = muito baixa ... 9 = muito alta  (critério 'maior melhor')",
        "",
        "C1 (ganho de horas) NÃO é preenchido aqui: é calculado pelos dados ERA5 (T8).",
        "Enquanto houver 'PROVISÓRIO' na coluna status, o script avisa que o ranking é provisório.",
        "Não altere os nomes das colunas nem dos códigos A1-A6.",
    ]
    for i, l in enumerate(linhas, 1):
        info.cell(i, 1, l)
    info["A1"].font = Font(bold=True, color="B00020", size=13)
    info.column_dimensions["A"].width = 110
    for row in info.iter_rows():
        for c in row:
            c.alignment = Alignment(wrap_text=False)
    TAB.mkdir(parents=True, exist_ok=True)
    wb.save(XLSX)
    return True


def ler_xlsx() -> tuple[pd.DataFrame, bool]:
    n = pd.read_excel(XLSX, sheet_name="notas").set_index("codigo").loc[list(ALTERNATIVAS)]
    cols = ["C2_custo", "C3_risco", "C4_facilidade_inclusao", "C5_conformidade_seguranca"]
    v = n[cols].astype(float)
    if ((v < 1) | (v > 9)).any().any():
        sys.exit("Notas fora da escala 1-9 em matriz_decisao_qualitativa.xlsx")
    v.columns = ["C2", "C3", "C4", "C5"]
    provisorio = n["status"].astype(str).str.upper().str.contains("PROVIS").any()
    return v, provisorio


# ----------------------------------------------------------------------------
# AHP e TOPSIS
# ----------------------------------------------------------------------------
def ahp(A: np.ndarray):
    vals, vecs = np.linalg.eig(A)
    i = np.argmax(vals.real)
    lam = vals[i].real
    w = np.abs(vecs[:, i].real)
    w = w / w.sum()
    n = len(A)
    ic = (lam - n) / (n - 1)
    rc = ic / RI_SAATY[n]
    return w, lam, ic, rc


def topsis(X: np.ndarray, w: np.ndarray, beneficio: np.ndarray):
    R = X / np.sqrt((X ** 2).sum(axis=0))
    V = R * w
    pos = np.where(beneficio, V.max(axis=0), V.min(axis=0))
    neg = np.where(beneficio, V.min(axis=0), V.max(axis=0))
    dp = np.sqrt(((V - pos) ** 2).sum(axis=1))
    dn = np.sqrt(((V - neg) ** 2).sum(axis=1))
    cc = dn / (dp + dn)
    return R, V, pos, neg, dp, dn, cc


def sensibilidade(X, w, beneficio, cods, alts, passos=np.arange(-50, 51, 10)):
    base_cc = topsis(X, w, beneficio)[-1]
    lider0 = alts[np.argmax(base_cc)]
    linhas = []
    for j, c in enumerate(cods):
        for p in passos:
            w2 = w.copy()
            w2[j] = w[j] * (1 + p / 100)
            outros = [k for k in range(len(w)) if k != j]
            w2[outros] = w[outros] * (1 - w2[j]) / w[outros].sum()
            cc = topsis(X, w2, beneficio)[-1]
            ordem = np.argsort(-cc)
            linhas.append({"criterio": c, "variacao_pct": int(p), "peso_criterio": w2[j],
                           **{f"CC_{a}": v for a, v in zip(alts, cc)},
                           "primeiro": alts[ordem[0]], "segundo": alts[ordem[1]],
                           "primeiro_mudou": alts[ordem[0]] != lider0})
    return pd.DataFrame(linhas), lider0


def fig_F6(T11, alts, lider0, provisorio):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from estatistica import INK, INK2, MUTED, SERIES, SURF, virgula  # aplica o estilo

    cods = list(CRITERIOS)
    fig, axs = plt.subplots(2, 3, figsize=(10, 6), sharey=True)
    axs = axs.ravel()
    for ax, c in zip(axs, cods):
        d = T11[T11["criterio"] == c]
        for i, a in enumerate(alts):
            ax.plot(d["variacao_pct"], d[f"CC_{a}"], color=SERIES[i], lw=2,
                    marker="o", ms=3.5, markeredgecolor=SURF, markeredgewidth=0.8, label=a)
        ax.axvline(0, color=MUTED, lw=0.8, ls="--")
        mud = d["primeiro_mudou"].any()
        txt = ("1º lugar muda: " + ", ".join(sorted(set(d.loc[d['primeiro_mudou'], 'primeiro']))) +
               f" ultrapassa {lider0}") if mud else f"1º lugar estável ({lider0})"
        curto = {"C1": "ganho de horas aptas", "C2": "custo de implantação",
                 "C3": "risco ambiental/saúde/deriva", "C4": "facilidade e inclusão",
                 "C5": "conformidade e segurança"}[c]
        ax.set_title(f"{c} — {curto}", loc="left", fontsize=8.5, pad=14)
        ax.text(0, 1.02, txt, transform=ax.transAxes, fontsize=7.5, va="bottom",
                color=INK if mud else INK2, fontweight="bold" if mud else "normal")
        ax.set_xticks(range(-50, 51, 25))
        ax.grid(axis="y")
        ax.yaxis.set_major_formatter(virgula("{:.2f}"))
    for ax in axs[3:5]:
        ax.set_xlabel("Variação do peso do critério (%)")
    axs[0].set_ylabel("Coeficiente de proximidade (TOPSIS)")
    axs[3].set_ylabel("Coeficiente de proximidade (TOPSIS)")
    axs[5].axis("off")
    hand, lab = axs[0].get_legend_handles_labels()
    axs[5].legend(hand, [f"{a} — {ALTERNATIVAS[a]}" for a in alts], loc="center left",
                  fontsize=7.5, title="Alternativas", title_fontsize=8)
    tit = "Sensibilidade do ranking TOPSIS à variação dos pesos AHP (Paraná; C1 corrigido pelas estações INMET)"
    if provisorio:
        tit += " — PESOS/NOTAS PROVISÓRIOS"
    fig.suptitle(tit, x=0.01, ha="left", fontsize=10, color=INK)
    fig.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / "F6_sensibilidade_topsis.png")
    plt.close(fig)


def fig_F6b(t: pd.DataFrame, alts: list[str], notas_rotulo: str = "notas dos autores"):
    """Barras agrupadas: CC por alternativa, um grupo por cenário (Paraná).
    src/painel_especialistas.py refaz esta figura com as notas do painel (versão principal)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from estatistica import INK, INK2, SERIES, SURF, virgula  # aplica o estilo

    cens = list(CENARIOS_PESOS)
    n = len(alts)
    larg = 0.8 / n
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for i, a in enumerate(alts):
        d = t[t["alternativa"] == a].set_index("cenario").loc[cens]
        x = np.arange(len(cens)) + (i - (n - 1) / 2) * larg
        ax.bar(x, d["CC"], width=larg, color=SERIES[i], edgecolor=SURF, linewidth=1.5,
               label=f"{a} — {ALTERNATIVAS[a]}")
        for xi, (cc, p) in zip(x, zip(d["CC"], d["posicao"])):
            if p == 1:  # rótulo seletivo: só o 1º lugar de cada cenário
                ax.text(xi, cc + 0.015, "1º", ha="center", va="bottom", fontsize=8,
                        color=INK, fontweight="bold")
    rot = []
    for c in cens:
        p = t[t["cenario"] == c].iloc[0]
        ws = "  ".join(f"{k} {p[f'peso_{k}']:.2f}".replace(".", ",") for k in CRITERIOS)
        rot.append(f"{ROTULO_CENARIO[c]}\n{ws}")
    ax.set_xticks(np.arange(len(cens)))
    ax.set_xticklabels(rot, fontsize=8)
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(virgula("{:.1f}"))
    ax.set_ylabel("Coeficiente de proximidade (TOPSIS)")
    ax.grid(axis="y")
    ax.legend(ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.2), fontsize=7.5)
    ax.set_title("Ranking TOPSIS das estratégias sob diferentes cenários de pesos — Paraná\n"
                 f"(C1 corrigido pelas estações INMET; {notas_rotulo})", loc="left")
    fig.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / "F6b_cenarios_topsis.png", dpi=300)
    plt.close(fig)


# ----------------------------------------------------------------------------
def main() -> None:
    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 60)
    muns_df = pd.read_csv(PROC / "municipios.csv", encoding="utf-8")
    configurar_agregados(muns_df)

    if criar_ahp_csv():
        print(f"Criado (PROVISÓRIO): {AHP_CSV}")
    if criar_xlsx():
        print(f"Criado (PROVISÓRIO): {XLSX}")

    T8 = tabela_T8(muns_df)
    T8.to_csv(TAB / "T8_ganho_horas_alternativas.csv", index=False, encoding="utf-8-sig")

    A, prov_ahp = ler_ahp()
    w, lam, ic, rc = ahp(A)
    cods = list(CRITERIOS)
    T9 = pd.DataFrame({"criterio": cods, "descricao": [CRITERIOS[c][0] for c in cods],
                       "tipo": [CRITERIOS[c][1] for c in cods], "peso": w})
    T9["lambda_max"], T9["IC"], T9["RC"] = lam, ic, rc
    T9["consistente_RC_menor_0_10"] = rc < 0.10
    T9["status"] = "PROVISÓRIO" if prov_ahp else "FINAL"
    T9.round(4).to_csv(TAB / "T9_pesos_ahp.csv", index=False, encoding="utf-8-sig")

    notas, prov_xlsx = ler_xlsx()
    alts = list(ALTERNATIVAS)
    beneficio = np.array([CRITERIOS[c][1] == "beneficio" for c in cods])
    provisorio = prov_ahp or prov_xlsx

    # C1 corrigido pelas estações do INMET (T8b). Resultado PRINCIPAL = C1 corrigido;
    # a versão só com ERA5 é guardada como T10_era5 / T10b_era5.
    from c1_corrigido import calcular_T8b
    T8b, _, conc_isday = calcular_T8b(T8)
    c1_era5 = {reg: T8[T8["municipio"] == reg].set_index("alternativa").loc[alts, "ganho_h_media"]
               for reg in (ESTADO, OESTE)}
    t8b = T8b.set_index("alternativa")
    c1_corr = {ESTADO: t8b.loc[alts, "C1_corrigido_PR"], OESTE: t8b.loc[alts, "C1_corrigido_Oeste"]}

    def rodar(c1: dict, versao: str):
        res, Xs, ideais = [], {}, None
        for reg in (ESTADO, OESTE):
            X = pd.concat([c1[reg].rename("C1"), notas], axis=1)[cods].to_numpy(float)
            R, V, pos, neg, dp, dn, cc = topsis(X, w, beneficio)
            t = pd.DataFrame({"regiao": reg, "versao_C1": versao, "alternativa": alts,
                              "descricao": [ALTERNATIVAS[a] for a in alts]})
            for j, c in enumerate(cods):
                t[f"{c}_valor"] = X[:, j]
            for j, c in enumerate(cods):
                t[f"{c}_ponderado"] = V[:, j]
            t["dist_ideal_pos"], t["dist_ideal_neg"], t["CC"] = dp, dn, cc
            t["ranking"] = t["CC"].rank(ascending=False, method="min").astype(int)
            t["status"] = "PROVISÓRIO" if provisorio else "FINAL"
            res.append(t.sort_values("ranking"))
            Xs[reg] = X
            if reg == ESTADO:
                ideais = pd.DataFrame({"criterio": cods, "ideal_positivo": pos, "ideal_negativo": neg})
        T10 = pd.concat(res, ignore_index=True).round(4)
        linhas_b = []
        for cen, pesos in CENARIOS_PESOS.items():
            wc = w if pesos is None else np.array(pesos, float)
            assert abs(wc.sum() - 1) < 1e-9, cen
            for reg, X in Xs.items():
                cc = topsis(X, wc, beneficio)[-1]
                pos_ = pd.Series(cc).rank(ascending=False, method="min").astype(int).to_numpy()
                for a, c, p in zip(alts, cc, pos_):
                    linhas_b.append({"cenario": cen, "regiao": reg, "versao_C1": versao,
                                     "alternativa": a, "descricao": ALTERNATIVAS[a], "CC": c,
                                     "posicao": int(p), **{f"peso_{k}": v for k, v in zip(cods, wc)}})
        T10b = pd.DataFrame(linhas_b).sort_values(["cenario", "regiao", "posicao"],
                                                  key=lambda s: s.map(list(CENARIOS_PESOS).index)
                                                  if s.name == "cenario" else s).round(4)
        return T10, T10b, Xs, ideais

    # versão anterior (C1 só ERA5), para comparação
    T10e, T10be, _, _ = rodar(c1_era5, "ERA5")
    T10e.to_csv(TAB / "T10_era5.csv", index=False, encoding="utf-8-sig")
    T10be.to_csv(TAB / "T10b_era5.csv", index=False, encoding="utf-8-sig")
    # versão principal (C1 corrigido pelas estações)
    T10, T10b, Xs, ideais = rodar(c1_corr, "corrigido_estacoes")
    T10.to_csv(TAB / "T10_topsis.csv", index=False, encoding="utf-8-sig")
    T10b.to_csv(TAB / "T10b_cenarios_topsis.csv", index=False, encoding="utf-8-sig")
    fig_F6b(T10b[T10b["regiao"] == ESTADO], alts)
    T11, lider0 = sensibilidade(Xs[ESTADO], w, beneficio, cods, alts)
    T11.insert(0, "versao_C1", "corrigido_estacoes")
    T11.round(4).to_csv(TAB / "T11_sensibilidade.csv", index=False, encoding="utf-8-sig")
    fig_F6(T11, alts, lider0, provisorio)

    # ------------------------------------------------------------- resumo
    def titulo(s):
        print("\n" + "=" * 100 + f"\n{s}\n" + "=" * 100)

    titulo(f"T8 - C1: ganho de horas utilizáveis no período de fungicidas (h/safra, média {N_SAFRAS} safras)")
    piv = T8[T8["municipio"].isin([ESTADO, OESTE])].pivot(
        index="alternativa", columns="municipio", values=["ganho_h_media", "ganho_pct"])
    print(piv.round(1).to_string())
    base = T8[T8["municipio"] == ESTADO]["horas_utilizaveis_base"].iloc[0]
    prox = T8[(T8["municipio"] == ESTADO) & (T8["alternativa"] == "A6")]["proxy_janelas_2h_por_dia"].iloc[0]
    print(f"Horas utilizáveis-base (Paraná): {base:.1f} h/safra; A6 proxy: {prox:.2f} janelas >= 2 h/dia")

    titulo("T8b - C1 corrigido pelas estações do INMET (h/safra) - usado como resultado principal")
    print(f"is_day por elevação solar x Open-Meteo: {conc_isday:.1f} % de concordância")
    print(T8b[["alternativa", "ganho_estacao_h_safra", "ganho_era5_mesmos_pontos_h_safra",
               "razao_estacao_era5", "C1_original_PR", "C1_corrigido_PR", "C1_original_Oeste",
               "C1_corrigido_Oeste"]].round(2).to_string(index=False))

    titulo(f"T9 - Pesos AHP {'(PROVISÓRIO)' if prov_ahp else ''}")
    print(T9[["criterio", "descricao", "peso"]].round(4).to_string(index=False))
    print(f"lambda_max = {lam:.4f}  IC = {ic:.4f}  RC = {rc:.4f}  -> "
          f"{'consistente (RC < 0,10)' if rc < 0.10 else 'INCONSISTENTE: revise a matriz'}")

    titulo(f"T10 - TOPSIS {'(PROVISÓRIO)' if provisorio else ''}")
    print(ideais.round(4).to_string(index=False))
    print(T10[["regiao", "ranking", "alternativa", "descricao", "C1_valor", "CC"]].to_string(index=False))

    titulo("T11 - Sensibilidade (Paraná): o 1º lugar muda?")
    r = T11.groupby("criterio").apply(lambda g: ", ".join(
        f"{p:+d}%→{a}" for p, a in zip(g["variacao_pct"], g["primeiro"]) if a != lider0) or "não",
        include_groups=False)
    print(f"1º lugar na base: {lider0}")
    print(r.to_string())
    for nome, tb in (("C1 CORRIGIDO (principal)", T10b), ("C1 só ERA5 (anterior)", T10be)):
        titulo(f"T10b - Cenários de pesos, {nome}: ordem das alternativas (1º -> 6º)")
        for reg in (ESTADO, OESTE):
            for cen in CENARIOS_PESOS:
                o = tb[(tb["regiao"] == reg) & (tb["cenario"] == cen)].sort_values("posicao")
                print(f"  {reg:15s} {cen:17s} " + "  ".join(
                    f"{a}({c:.3f})" for a, c in zip(o["alternativa"], o["CC"])))
    if provisorio:
        print("\n*** ATENÇÃO: pesos AHP e/ou notas C2-C5 ainda PROVISÓRIOS - ranking não é final. ***")
    else:
        print("\nStatus: pesos AHP e notas C2-C5 FINAIS.")


if __name__ == "__main__":
    main()
