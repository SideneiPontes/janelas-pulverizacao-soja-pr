"""Estatística e figuras: Markov, Mann-Kendall/Sen, k-means e mapas.

Entrada : data/processed/indicadores_diarios.parquet, outputs/tables/T1_*.csv, T3_*.csv
Saídas  : outputs/tables/T5_markov.csv, T6_mann_kendall.csv, T7_clusters.csv,
          T7b_silhueta_k.csv; outputs/figures/F1..F5 e F_silhueta (PNG 300 dpi)
Critério de aptidão: A (proposto), salvo indicação.

Uso:  python src/estatistica.py
"""
from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib
import matplotlib.patheffects
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pymannkendall as mk
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy.stats import chi2_contingency
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_samples, silhouette_score
from sklearn.preprocessing import StandardScaler

from indicadores import (AGREG, CELULA, ESTADO, FASES_OP, MESES_SAFRA, MOTIVOS_A, NOME_MES,
                         OESTE, calendario, configurar_agregados, media_por_celula)

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
TAB = ROOT / "outputs" / "tables"
FIG = ROOT / "outputs" / "figures"
ALFA = 0.05
SEED = 42

# Paleta (referência dataviz, modo claro)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
          "#008300", "#6250d6", "#e34948"]
MARCADORES = ["o", "s", "^", "D", "v"]
SEQ = LinearSegmentedColormap.from_list(
    "azul", ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])
DIV = LinearSegmentedColormap.from_list(
    "div", ["#a12d2d", "#e34948", "#f0a3a2", "#f0efec", "#9ec5f4", "#2a78d6", "#184f95"])
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASE, SURF = "#e1e0d9", "#c3c2b7", "#ffffff"
CINZA_MUN = "#ecebe7"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
    "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9,
    "axes.edgecolor": BASE, "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2,
    "ytick.labelcolor": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": False, "grid.color": GRID, "grid.linewidth": 0.6,
    "legend.frameon": False, "savefig.dpi": 300, "savefig.bbox": "tight",
    "figure.facecolor": SURF, "axes.facecolor": SURF,
})


def salvar(fig, nome):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{nome}.png")
    plt.close(fig)
    print(f"  figura: {nome}.png")


# ----------------------------------------------------------------------------
# 1. Cadeia de Markov de 1ª ordem
# ----------------------------------------------------------------------------
def markov(D: pd.DataFrame, muns: list[str]) -> pd.DataFrame:
    D = D.sort_values(["municipio", "data"]).copy()
    D["F"] = D["dia_apto_A"].astype(int)
    D["F_ant"] = D.groupby("municipio")["F"].shift(1)
    D["data_ant"] = D.groupby("municipio")["data"].shift(1)
    D = D[(D["data"] - D["data_ant"]) == pd.Timedelta(days=1)]
    linhas = []
    for (mun, mes, dec), g in D.groupby(["municipio", "mes", "decendio"]):
        nF, n = g["F"].sum(), len(g)
        aF, aNF = g[g["F_ant"] == 1], g[g["F_ant"] == 0]
        tab = np.array([[aF["F"].sum(), len(aF) - aF["F"].sum()],
                        [aNF["F"].sum(), len(aNF) - aNF["F"].sum()]])
        p_ind = chi2_contingency(tab)[1] if (tab.sum(0) > 0).all() and (tab.sum(1) > 0).all() else np.nan
        linhas.append({
            "municipio": mun, "mes": mes, "decendio": dec,
            "decendio_rotulo": f"{NOME_MES[mes]}-{dec}", "n_dias": n,
            "P_F": nF / n,
            "P_F_dado_F": aF["F"].mean() if len(aF) else np.nan,
            "P_F_dado_NF": aNF["F"].mean() if len(aNF) else np.nan,
            "n_ant_F": len(aF), "n_ant_NF": len(aNF),
            "p_qui2_independencia": p_ind,
        })
    t = pd.DataFrame(linhas)
    t["persistencia"] = t["P_F_dado_F"] - t["P_F_dado_NF"]
    t["dependencia_sig_5pct"] = t["p_qui2_independencia"] < ALFA
    t["ordem"] = t["mes"].map({m: i for i, m in enumerate(MESES_SAFRA)}) * 3 + t["decendio"]
    t["municipio"] = pd.Categorical(t["municipio"], muns, ordered=True)
    t = t.sort_values(["municipio", "ordem"]).drop(columns="ordem")
    return t.round(4)


# ----------------------------------------------------------------------------
# 2. Mann-Kendall e Sen
# ----------------------------------------------------------------------------
def mann_kendall(D: pd.DataFrame, muns: list[str]) -> pd.DataFrame:
    dd = D[D["fase"] != ""]
    s = dd.groupby(["municipio", "fase", "safra_ini"])["horas_aptas_A"].sum().reset_index()
    partes = [s]
    for nome, membros in AGREG.items():
        est = media_por_celula(s[s["municipio"].isin(membros)], ["fase", "safra_ini"],
                               ["horas_aptas_A"])
        est["municipio"] = nome
        partes.append(est)
    s = pd.concat(partes, ignore_index=True)
    linhas = []
    for (mun, fase), g in s.groupby(["municipio", "fase"]):
        g = g.sort_values("safra_ini")
        assert len(g) == 29, (mun, fase, len(g))
        r = mk.original_test(g["horas_aptas_A"].to_numpy())
        media = g["horas_aptas_A"].mean()
        linhas.append({
            "municipio": mun, "fase": fase, "n_safras": len(g),
            "media_horas": media, "tau": r.Tau, "S": r.s, "z": r.z, "p_valor": r.p,
            "sen_h_por_decada": r.slope * 10,
            "sen_pct_media_por_decada": 100 * r.slope * 10 / media,
            "tendencia": r.trend, "significativo_5pct": r.p < ALFA,
        })
    t = pd.DataFrame(linhas)
    t["fase"] = pd.Categorical(t["fase"], FASES_OP, ordered=True)
    t["municipio"] = pd.Categorical(t["municipio"], muns + list(AGREG), ordered=True)
    return t.sort_values(["fase", "municipio"]).round(4)


# ----------------------------------------------------------------------------
# 3. k-means
# ----------------------------------------------------------------------------
def agrupamento(T1: pd.DataFrame, muns: list[str]):
    m = T1[~T1["municipio"].isin(list(AGREG))].copy()
    m["ordem"] = m["mes"].map({x: i for i, x in enumerate(MESES_SAFRA)}) * 3 + m["decendio"]
    X = m.pivot(index="municipio", columns="ordem", values="media").loc[muns]
    # Uma amostra por célula ERA5 (municípios na mesma célula são promediados),
    # para que séries praticamente iguais não contem duas vezes.
    cel = X.index.map(CELULA)
    Xc = X.groupby(cel, sort=False).mean()
    nomes_cel = pd.Series(X.index, index=cel).groupby(level=0, sort=False).agg(" + ".join)
    Z = StandardScaler().fit_transform(Xc.to_numpy())
    res, modelos = [], {}
    for k in range(2, 6):
        km = KMeans(n_clusters=k, n_init=100, random_state=SEED).fit(Z)
        modelos[k] = km
        res.append({"k": k, "silhueta_media": silhouette_score(Z, km.labels_),
                    "inercia": km.inertia_})
    sil_k = pd.DataFrame(res)
    sil_k["n_celulas"] = len(Xc)
    k_best = int(sil_k.loc[sil_k["silhueta_media"].idxmax(), "k"])
    lab = modelos[k_best].labels_
    # renumera grupos por média de horas aptas (1 = menor aptidão)
    media_cel = Xc.mean(axis=1).to_numpy()
    ordem = pd.Series(media_cel).groupby(lab).mean().sort_values().index
    mapa = {old: new + 1 for new, old in enumerate(ordem)}
    tc = pd.DataFrame({
        "celula_era5": Xc.index, "municipio": nomes_cel.loc[Xc.index].to_numpy(),
        "grupo": [mapa[x] for x in lab], "silhueta": silhouette_samples(Z, lab),
    })
    t = pd.DataFrame({
        "municipio": muns, "celula_era5": list(cel),
        "horas_aptas_media_decendio": X.mean(axis=1).to_numpy(),
        "horas_aptas_set_abr": X.sum(axis=1).to_numpy(),
    }).merge(tc[["celula_era5", "grupo", "silhueta"]], on="celula_era5")
    t = t[["municipio", "celula_era5", "grupo", "silhueta", "horas_aptas_media_decendio",
           "horas_aptas_set_abr"]]
    sil_k["escolhido"] = sil_k["k"] == k_best
    return t.round(4), sil_k.round(4), k_best, X, tc.round(4)


def fig_silhueta(t7, sil_k, k_best):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 3.8), gridspec_kw={"width_ratios": [1, 1.6]})
    a1.plot(sil_k["k"], sil_k["silhueta_media"], color=SERIES[0], lw=2, marker="o", ms=7,
            markeredgecolor=SURF, markeredgewidth=2)
    best = sil_k[sil_k["k"] == k_best].iloc[0]
    a1.annotate(f"k = {k_best}: {best['silhueta_media']:.3f}".replace(".", ","),
                (best["k"], best["silhueta_media"]), xytext=(10, 0),
                textcoords="offset points", color=INK, fontsize=8, va="center")
    a1.yaxis.set_major_formatter(virgula("{:.2f}"))
    a1.set_xticks(sil_k["k"])
    a1.set_xlabel("Número de grupos (k)")
    a1.set_ylabel("Índice de silhueta médio")
    a1.set_title("(a) Escolha de k", loc="left")
    a1.grid(axis="y")

    y = 0
    for g in sorted(t7["grupo"].unique()):
        d = t7[t7["grupo"] == g].sort_values("silhueta")
        cor = SERIES[g - 1]
        a2.barh(np.arange(y, y + len(d)), d["silhueta"], color=cor, height=0.8,
                edgecolor=SURF, linewidth=0.5)
        for i, (mun, s) in enumerate(zip(d["municipio"], d["silhueta"])):
            a2.text(max(s, 0) + 0.01, y + i, mun, va="center", fontsize=7, color=INK2)
        a2.text(-0.02, y + (len(d) - 1) / 2, f"Grupo {g}", ha="right", va="center",
                fontsize=8, color=INK)
        y += len(d) + 1
    a2.axvline(best["silhueta_media"], color=MUTED, ls="--", lw=1)
    a2.text(best["silhueta_media"], y - 0.3, " média", color=MUTED, fontsize=7, va="top")
    a2.set_yticks([])
    a2.spines["left"].set_visible(False)
    a2.set_xlim(min(-0.05, t7["silhueta"].min() - 0.05), 1)
    a2.xaxis.set_major_formatter(virgula("{:.1f}"))
    a2.set_xlabel("Coeficiente de silhueta")
    a2.set_title(f"(b) Silhueta por célula ERA5 (k = {k_best})", loc="left")
    fig.tight_layout()
    salvar(fig, "F_silhueta")


# ----------------------------------------------------------------------------
# Figuras
# ----------------------------------------------------------------------------
def malhas(muns_df):
    from malhas import malhas_pr  # IBGE 2020 (geobr), com cache local
    uf, mun = malhas_pr()
    mun["code_muni"] = mun["code_muni"].astype(int)
    sel = mun.merge(muns_df[["cod_ibge", "municipio"]], left_on="code_muni", right_on="cod_ibge")
    assert len(sel) == len(muns_df), "municípios não encontrados na malha"
    pts = sel.copy()
    pts_proj = pts.to_crs(5880).representative_point().to_crs(pts.crs)
    pts["x"], pts["y"] = pts_proj.x, pts_proj.y
    return uf, mun, sel, pts


def base_mapa(ax, uf, mun):
    mun.plot(ax=ax, color=CINZA_MUN, edgecolor="#ffffff", linewidth=0.25)
    uf.boundary.plot(ax=ax, color=BASE, linewidth=0.8)
    ax.set_axis_off()
    ax.set_aspect("equal")


# Posição dos rótulos (apenas tipografia, para evitar sobreposição): (dx, dy, alinhamento)
POS_ROTULO = {"Assis Chateaubriand": (-4, 9, "left"), "Ubiratã": (6, -11, "left"),
              "Toledo": (6, -11, "left"), "Maringá": (-6, 4, "right")}


def virgula(fmt="{:.2f}"):
    return matplotlib.ticker.FuncFormatter(lambda v, _: fmt.format(v).replace(".", ","))


# Posições no painel ampliado do Oeste (apenas tipografia)
POS_ZOOM: dict[str, tuple] = {
    "Assis Chateaubriand": (-7, 4, "right"), "Ubiratã": (-7, 6, "right"),
    "Santa Helena": (0, -15, "center"), "Cascavel": (0, -16, "center"),
    "Medianeira": (-7, 5, "right"), "São Miguel do Iguaçu": (10, -14, "left"),
    "Foz do Iguaçu": (0, -18, "center"), "Marechal Cândido Rondon": (-7, 5, "right"),
}


def rotulos(ax, pts, extra=None, pos=None, fontsize=6.5):
    pos = POS_ROTULO if pos is None else pos
    for _, r in pts.iterrows():
        txt = r["municipio"] + (extra(r) if extra else "")
        dx, dy, ha = pos.get(r["municipio"], (6, 3, "left"))
        ax.annotate(txt, (r["x"], r["y"]), xytext=(dx, dy), textcoords="offset points",
                    ha=ha, fontsize=fontsize, color=INK, path_effects=[
                        matplotlib.patheffects.withStroke(linewidth=2, foreground=SURF)])


def caixa_oeste(sel, pad=0.12):
    """Retângulo que envolve os municípios da média do Oeste (graus)."""
    x0, y0, x1, y1 = sel[sel["municipio"].isin(AGREG[OESTE])].total_bounds
    return x0 - pad - 0.5, x1 + pad, y0 - pad, y1 + pad  # margem extra a oeste p/ rótulos


def mapa_com_zoom(uf, mun, sel, pts, desenhar, extra=None):
    """Mapa do estado (esq.) + painel ampliado do Oeste (dir.)."""
    fig, (ax, az) = plt.subplots(1, 2, figsize=(11, 5.0),
                                 gridspec_kw={"width_ratios": [1.65, 1], "wspace": 0.04})
    x0, x1, y0, y1 = caixa_oeste(sel)
    dentro = pts["x"].between(x0, x1) & pts["y"].between(y0, y1)
    for a in (ax, az):
        base_mapa(a, uf, mun)
        desenhar(a)
    rotulos(ax, pts[~dentro], extra)
    ax.add_patch(matplotlib.patches.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False,
                                              edgecolor=INK2, linewidth=0.9, zorder=7))
    xl = ax.get_xlim()
    ax.set_xlim(min(xl[0], x0 - 0.05), xl[1])
    az.set_xlim(x0, x1)
    az.set_ylim(y0, y1)
    rotulos(az, pts[dentro], extra, pos=POS_ZOOM, fontsize=7.5)
    for s in ("left", "right", "top", "bottom"):
        az.spines[s].set_visible(True)
        az.spines[s].set_color(INK2)
    az.set_axis_on()
    az.set_xticks([])
    az.set_yticks([])
    az.set_xlabel("")
    az.set_ylabel("")
    az.set_title("Oeste (ampliado)", loc="left", fontsize=9, color=INK2)
    return fig, ax, az


def nomes_grupos(t7: pd.DataFrame) -> dict:
    """Nome descritivo de cada grupo decidido pelas horas aptas (não pelo número do grupo)."""
    m = t7.groupby("grupo")["horas_aptas_set_abr"].mean().sort_values()
    if len(m) == 2:
        return {m.index[0]: "Grupo restritivo (Campos Gerais e Sul)",
                m.index[1]: "Grupo favorável (Norte e Oeste)"}
    return {g: f"Grupo {g}" for g in m.index}


def fig_F1(uf, mun, sel, pts, t7, k_best):
    sel = sel.merge(t7[["municipio", "grupo"]], on="municipio")
    pts = pts.merge(t7[["municipio", "grupo"]], on="municipio")

    def desenhar(a):
        for g in range(1, k_best + 1):
            sel[sel["grupo"] == g].plot(ax=a, color=SERIES[g - 1], edgecolor=SURF, linewidth=0.4)
            p = pts[pts["grupo"] == g]
            a.scatter(p["x"], p["y"], marker=MARCADORES[g - 1], s=28, color=SERIES[g - 1],
                      edgecolor=SURF, linewidth=1.2, zorder=5)

    fig, ax, az = mapa_com_zoom(uf, mun, sel, pts, desenhar)
    nomes = nomes_grupos(t7)
    leg = [Line2D([0], [0], marker=MARCADORES[g - 1], color="none", markerfacecolor=SERIES[g - 1],
                  markeredgecolor=SURF, markersize=8,
                  label=f"{nomes[g]} — {(t7['grupo'] == g).sum()} municípios")
           for g in range(1, k_best + 1)]
    ax.legend(handles=leg, loc="upper left", bbox_to_anchor=(0, 0.02), fontsize=8,
              title="Agrupamento k-means", title_fontsize=8, alignment="left")
    ax.set_title("Municípios estudados e grupos de aptidão para pulverização", loc="left")
    salvar(fig, "F1_mapa_clusters")


def fig_F2(T1):
    T1 = T1.copy()
    T1["ordem"] = T1["mes"].map({x: i for i, x in enumerate(MESES_SAFRA)}) * 3 + T1["decendio"] - 1
    regs = {reg: T1[T1["municipio"] == reg].sort_values("ordem") for reg in AGREG}
    e = pd.concat(regs.values())
    x = regs[ESTADO]["ordem"].to_numpy()
    fig, ax = plt.subplots(figsize=(9, 4.2))
    # fases: limites em posições de decêndio (16/dez = meio de Dez-2)
    fases = [(-0.5, 5.5), (5.5, 10.0), (10.0, 17.5), (17.5, 23.5)]
    nomes = ["Dessecação\npré-semeadura", "Pós-emergência", "Fungicidas (R1–R5)",
             "Pré-colheita\ne colheita"]
    tons = ["#f4f3f0", "#ffffff", "#f4f3f0", "#ffffff"]
    ytop = (e["media"] + e["dp"]).max() * 1.12
    for (a, b), nome, tom in zip(fases, nomes, tons):
        ax.axvspan(a, b, color=tom, zorder=0, lw=0)
        ax.text((a + b) / 2, ytop * 0.985, nome, ha="center", va="top", fontsize=8, color=INK2)
    for a, _ in fases[1:]:
        ax.axvline(a, color=BASE, lw=0.8, zorder=1)
    rotulo = {ESTADO: f"Paraná ({len(AGREG[ESTADO])} municípios originais)",
              OESTE: f"Oeste ({len(AGREG[OESTE])} municípios do zoneamento)"}
    for i, (reg, d) in enumerate(regs.items()):
        cor = SERIES[i]
        ax.fill_between(x, d["media"] - d["dp"], d["media"] + d["dp"], color=cor,
                        alpha=0.13, lw=0, zorder=2)
        ax.plot(x, d["media"], color=cor, lw=2, zorder=3 + i, label=f"{rotulo[reg]}: média")
        ax.scatter(x, d["media"], color=cor, s=16, edgecolor=SURF, linewidth=1, zorder=4 + i)
    ax.fill_between([], [], [], color=MUTED, alpha=0.2, lw=0,
                    label="Faixas: ± 1 desvio-padrão entre safras")
    ax.set_xticks(x)
    ax.set_xticklabels(regs[ESTADO]["decendio_rotulo"], rotation=90, fontsize=7.5)
    ax.set_xlim(-0.5, 23.5)
    ax.set_ylim(0, ytop)
    ax.set_ylabel("Horas aptas por decêndio")
    ax.set_xlabel("Decêndio")
    ax.grid(axis="y")
    ax.legend(loc="lower left", fontsize=7.5, ncol=1)
    ax.set_title("Horas aptas para pulverização por decêndio, safras 1995/96 a 2023/24",
                 loc="left")
    salvar(fig, "F2_horas_aptas_decendio")


def fig_F3(T1, t7):
    m = T1[~T1["municipio"].isin(list(AGREG))].copy()
    m["ordem"] = m["mes"].map({x: i for i, x in enumerate(MESES_SAFRA)}) * 3 + m["decendio"]
    M = m.pivot(index="municipio", columns="ordem", values="media")
    rot = m.drop_duplicates("ordem").set_index("ordem")["decendio_rotulo"].sort_index()
    ordem = t7.sort_values(["grupo", "horas_aptas_set_abr"], ascending=[True, False])
    M = M.loc[ordem["municipio"]]
    fig, ax = plt.subplots(figsize=(10, 1.2 + 0.3 * len(M)))
    im = ax.imshow(M.to_numpy(), aspect="auto", cmap=SEQ)
    ax.set_xticks(range(M.shape[1]))
    ax.set_xticklabels(rot.values, rotation=90, fontsize=7.5)
    ax.set_yticks(range(M.shape[0]))
    ax.set_yticklabels(M.index, fontsize=8)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    # separação de grupos
    gs = ordem["grupo"].to_numpy()
    for i in np.where(np.diff(gs) != 0)[0]:
        ax.axhline(i + 0.5, color=SURF, lw=3)
    for g in np.unique(gs):
        idx = np.where(gs == g)[0]
        ax.text(M.shape[1] - 0.3, idx.mean(), f"  Grupo {g}", va="center", fontsize=8,
                color=INK2, transform=ax.transData, clip_on=False)
    # fases (eixo x)
    for b in (5.5, 10.0, 17.5):
        ax.axvline(b, color=SURF, lw=2)
    cb = fig.colorbar(im, ax=ax, pad=0.09, fraction=0.03)
    cb.set_label("Horas aptas por decêndio (média 29 safras)")
    cb.outline.set_visible(False)
    ax.set_title("Horas aptas para pulverização por município e decêndio (set–abr)", loc="left")
    salvar(fig, "F3_heatmap_municipio_decendio")


def fig_F4(T3):
    fig, axs = plt.subplots(2, 1, figsize=(9, 6.2), sharex=True)
    titulos = {ESTADO: f"(a) Paraná — {len(AGREG[ESTADO])} municípios originais",
               OESTE: f"(b) Oeste — {len(AGREG[OESTE])} municípios do zoneamento"}
    for ax, reg in zip(axs, AGREG):
        t = T3[T3["regiao"] == reg]
        P = t.pivot(index="fase", columns="motivo", values="pct_motivo_principal")
        P = P.loc[FASES_OP, MOTIVOS_A]
        esq = np.zeros(len(P))
        y = np.arange(len(P))[::-1]
        for i, mot in enumerate(MOTIVOS_A):
            v = P[mot].to_numpy()
            ax.barh(y, v, left=esq, color=SERIES[i], height=0.62, edgecolor=SURF,
                    linewidth=1.5, label=mot)
            for yy, l, val in zip(y, esq, v):
                if val >= 7:
                    cor_txt = INK if SERIES[i] == "#eda100" else "#ffffff"
                    ax.text(l + val / 2, yy, f"{val:.0f}", ha="center", va="center",
                            fontsize=7.5, color=cor_txt)
            esq += v
        ax.set_yticks(y)
        ax.set_yticklabels(P.index)
        ax.set_xlim(0, 100)
        ax.tick_params(axis="y", length=0)
        ax.spines["left"].set_visible(False)
        ax.set_title(titulos[reg], loc="left", fontsize=9)
    axs[-1].set_xlabel("% das horas inaptas (motivo principal)")
    axs[-1].legend(ncol=4, loc="upper center", bbox_to_anchor=(0.45, -0.3), fontsize=8)
    fig.suptitle("Motivo principal de inaptidão por fase da safra", x=0.01, ha="left",
                 fontsize=10, color=INK)
    fig.tight_layout()
    salvar(fig, "F4_motivos_inaptidao")


def fig_F5(uf, mun, sel, pts, T6):
    f = T6[(T6["fase"] == "Fungicidas (R1-R5)") & (~T6["municipio"].isin(list(AGREG)))]
    f = f[["municipio", "sen_h_por_decada", "p_valor", "significativo_5pct"]].astype(
        {"municipio": str})
    sel = sel.merge(f, on="municipio")
    pts = pts.merge(f, on="municipio")
    lim = np.abs(f["sen_h_por_decada"]).max()
    norm = TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim)

    def desenhar(a):
        sel.plot(ax=a, column="sen_h_por_decada", cmap=DIV, norm=norm, edgecolor=SURF,
                 linewidth=0.4)
        sig = pts[pts["significativo_5pct"]]
        nsig = pts[~pts["significativo_5pct"]]
        a.scatter(nsig["x"], nsig["y"], c=nsig["sen_h_por_decada"], cmap=DIV, norm=norm, s=40,
                  marker="o", edgecolor=MUTED, linewidth=0.8, zorder=5)
        a.scatter(sig["x"], sig["y"], c=sig["sen_h_por_decada"], cmap=DIV, norm=norm, s=70,
                  marker="o", edgecolor=INK, linewidth=1.8, zorder=6)

    fig, ax, az = mapa_com_zoom(
        uf, mun, sel, pts, desenhar,
        extra=lambda r: f" ({r['sen_h_por_decada']:+.0f}{'*' if r['significativo_5pct'] else ''})")
    sm = plt.cm.ScalarMappable(cmap=DIV, norm=norm)
    cb = fig.colorbar(sm, ax=[ax, az], fraction=0.025, pad=0.02)
    cb.set_label("Tendência de Sen (horas aptas por década)")
    cb.outline.set_visible(False)
    leg = [Line2D([0], [0], marker="o", color="none", markerfacecolor="#f0efec",
                  markeredgecolor=INK, markeredgewidth=1.8, markersize=9,
                  label="Significativo (Mann-Kendall, p < 0,05) *"),
           Line2D([0], [0], marker="o", color="none", markerfacecolor="#f0efec",
                  markeredgecolor=MUTED, markersize=7, label="Não significativo")]
    # legenda abaixo do mapa: não encosta no rótulo de Palmas nem em outros rótulos
    ax.legend(handles=leg, loc="upper left", bbox_to_anchor=(0, 0.02), ncol=2, fontsize=8,
              columnspacing=2.0, handletextpad=0.6)
    ax.set_title("Tendência de horas aptas no período de fungicidas (16/dez–fev), 1995/96–2023/24",
                 loc="left", fontsize=9.5)
    salvar(fig, "F5_mapa_tendencia_fungicidas")


# ----------------------------------------------------------------------------
def main() -> None:

    pd.set_option("display.width", 220)
    muns_df = pd.read_csv(PROC / "municipios.csv", encoding="utf-8")
    muns = muns_df["municipio"].tolist()
    configurar_agregados(muns_df)
    D = calendario(pd.read_parquet(PROC / "indicadores_diarios.parquet"))
    T1 = pd.read_csv(TAB / "T1_horas_aptas_decendio.csv", encoding="utf-8-sig")
    T3 = pd.read_csv(TAB / "T3_motivos_inaptidao.csv", encoding="utf-8-sig")

    T5 = markov(D, muns)
    T5.to_csv(TAB / "T5_markov.csv", index=False, encoding="utf-8-sig")
    T6 = mann_kendall(D, muns)
    T6.to_csv(TAB / "T6_mann_kendall.csv", index=False, encoding="utf-8-sig")
    T7, sil_k, k_best, _, T7c = agrupamento(T1, muns)
    T7.to_csv(TAB / "T7_clusters.csv", index=False, encoding="utf-8-sig")
    sil_k.to_csv(TAB / "T7b_silhueta_k.csv", index=False, encoding="utf-8-sig")

    print("Figuras:")
    fig_silhueta(T7c, sil_k, k_best)
    uf, mun, sel, pts = malhas(muns_df)
    fig_F1(uf, mun, sel, pts, T7, k_best)
    fig_F2(T1)
    fig_F3(T1, T7)
    fig_F4(T3)
    fig_F5(uf, mun, sel, pts, T6)

    # ------------------------------------------------------------ resumo
    def titulo(s):
        print("\n" + "=" * 100 + f"\n{s}\n" + "=" * 100)

    titulo(f"T5 - Markov (média dos {len(muns)} municípios por decêndio)")
    r = T5.groupby("decendio_rotulo", sort=False)[
        ["P_F", "P_F_dado_F", "P_F_dado_NF", "dependencia_sig_5pct"]].mean()
    print(r.round(3).to_string())
    print(f"\nDecêndios × municípios com dependência significativa (qui², 5%): "
          f"{T5['dependencia_sig_5pct'].sum()} de {len(T5)}")

    titulo("T6 - Mann-Kendall / Sen (horas aptas por safra), significativos a 5%")
    sig = T6[T6["significativo_5pct"]]
    print(sig[["fase", "municipio", "tau", "p_valor", "sen_h_por_decada",
               "sen_pct_media_por_decada"]].to_string(index=False) if len(sig) else "nenhum")
    print(f"\nSignificativos: {len(sig)} de {len(T6)} (município × fase, incluindo Paraná)")
    for reg in AGREG:
        print(f"\n{reg}:")
        print(T6[T6["municipio"] == reg][["fase", "tau", "p_valor", "sen_h_por_decada",
                                           "significativo_5pct"]].to_string(index=False))

    titulo(f"T7 - k-means (k escolhido = {k_best})")
    print(sil_k.to_string(index=False))
    print()
    print(T7.sort_values(["grupo", "horas_aptas_set_abr"]).to_string(index=False))


if __name__ == "__main__":
    main()
