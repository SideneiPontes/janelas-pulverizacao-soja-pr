"""Mapas finais: CSV para o Google My Maps, mapa de apresentação (F8), mapa interativo (folium)
e versão final das figuras F1 e F5.

Uso:  python -I src/mapa_final.py
Lê apenas tabelas já calculadas (T2, T2c, T6, T7, T10, T12a, T13c) e
data/processed/indicadores_diarios.parquet (motivo principal por município). Não baixa dados,
as malhas do IBGE vêm de src/malhas.py (cache local em data/processed/malhas).

Saídas
  outputs/mymaps_pontos.csv                       (municípios + estações INMET usadas)
  outputs/mymaps/municipios.csv, estacoes_inmet.csv (simplificados: números já como texto,
                                                   vírgula decimal; UTF-8 com BOM)
  outputs/figures/F8_mapa_apresentacao.png        (16:9, 300 dpi)
  outputs/mapa_interativo.html                    (folium)
  outputs/figures/F1_mapa_clusters.png, F5_mapa_tendencia_fungicidas.png (refeitas)
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import estatistica as E  # noqa: E402  (estilo, paleta, malhas, F1, F5)
from indicadores import (FASES_OP, MOTIVOS_A, PERIODO_ERA5, PROC, ROTULO_SAFRAS, TAB,  # noqa: E402
                         calendario, configurar_agregados)
from validacao_inmet import estacoes, periodo_estacoes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
FUNG = "Fungicidas (R1-R5)"
_INV = estacoes()
_USADAS = _INV[_INV["selecionada"]]
N_EST = int(_USADAS["incluida_na_media"].sum())
PER_EST = periodo_estacoes(_USADAS).split(" (")[0].replace("safras ", "safras ")
NOTA = (f"ERA5 {PERIODO_ERA5}; validado com {N_EST} estações INMET ({PER_EST}); diferenças entre "
        "municípios no período de fungicidas não confirmadas pelas estações")
FONTE = (f"Fonte: ERA5 (ECMWF) via Open-Meteo, safras {ROTULO_SAFRAS}, critério A de aptidão; "
         "malhas IBGE 2020 (geobr).")
MOTIVO_TXT = {
    "DeltaT baixo": "Delta T baixo (< 2 °C, ar úmido)", "DeltaT alto": "Delta T alto (> 8 °C)",
    "vento fraco": "Vento fraco (< 3 km/h)", "vento forte": "Vento forte (> 10 km/h)",
    "temperatura": "Temperatura ≥ 30 °C", "UR": "Umidade relativa < 50 %",
    "chuva": "Chuva na hora", "chuva logo depois": "Chuva nas 2 h seguintes",
}
ESTRATEGIA = "Pontas antideriva (indução de ar)"


# ----------------------------------------------------------------------------
def dados_municipios() -> pd.DataFrame:
    muns = pd.read_csv(PROC / "municipios.csv", encoding="utf-8")
    t7 = pd.read_csv(TAB / "T7_clusters.csv", encoding="utf-8-sig")
    nomes = E.nomes_grupos(t7)
    t2 = pd.read_csv(TAB / "T2_dias_aptos_fase.csv", encoding="utf-8-sig")
    t2 = t2[t2["fase"] == FUNG].set_index("municipio")
    t2c = pd.read_csv(TAB / "T2c_melhor_epoca_fungicida.csv", encoding="utf-8-sig").set_index("municipio")
    t6 = pd.read_csv(TAB / "T6_mann_kendall.csv", encoding="utf-8-sig")
    t6 = t6[t6["fase"] == FUNG].set_index("municipio")
    t10 = pd.read_csv(TAB / "T10_topsis.csv", encoding="utf-8-sig")
    lider = t10[(t10["ranking"] == 1)]["descricao"].unique()
    assert len(lider) == 1 and "antideriva" in lider[0], f"T10 mudou: 1º lugar = {lider}"

    # motivo principal de inaptidão no período de fungicidas, por município
    D = calendario(pd.read_parquet(PROC / "indicadores_diarios.parquet"))
    D = D[D["fase"] == FUNG]
    cols = [f"princ_A_{m}" for m in MOTIVOS_A]
    s = D.groupby("municipio")[cols].sum()
    mot = s.idxmax(axis=1).str.replace("princ_A_", "", regex=False)
    pct = 100 * s.max(axis=1) / s.sum(axis=1)

    df = muns[["municipio", "cod_ibge", "lat", "lon", "grupo_origem"]].copy()
    g = t7.set_index("municipio")["grupo"]
    df["grupo"] = df["municipio"].map(g).map(nomes)
    df["horas_aptas_fungicidas_h_safra"] = df["municipio"].map(t2["horas_aptas_media"])
    df["pct_tempo_apto_fungicidas"] = df["municipio"].map(t2["pct_tempo_apto"])
    df["dias_aptos_fungicidas"] = df["municipio"].map(t2["dias_aptos_media"])
    df["melhor_epoca_semeadura"] = df["municipio"].map(t2c["melhor_epoca"])
    df["tendencia_sen_h_decada"] = df["municipio"].map(t6["sen_h_por_decada"])
    df["tendencia_significativa_5pct"] = df["municipio"].map(t6["significativo_5pct"]).map(
        {True: "sim", False: "não"})
    df["principal_motivo_perda_janela"] = df["municipio"].map(mot).map(MOTIVO_TXT)
    df["pct_horas_inaptas_motivo"] = df["municipio"].map(pct)
    df["estrategia_prioritaria"] = ESTRATEGIA
    return df


def dados_estacoes() -> pd.DataFrame:
    sel = _USADAS
    t13c = pd.read_csv(TAB / "T13c_fases_estacao_vs_era5.csv", encoding="utf-8-sig")
    t13c = t13c[t13c["codigo"] != "TODAS"]
    curto = {"Dessecação pré-semeadura": "dessecacao", "Pós-emergência": "pos_emergencia",
             "Fungicidas (R1-R5)": "fungicidas", "Pré-colheita e colheita": "pre_colheita"}
    linhas = []
    for _, e in sel.iterrows():
        r = {"codigo_estacao": e.codigo, "estacao": " ".join(w if w in ("do", "da", "de") else w.capitalize() for w in e.estacao.lower().split()), "lat": e.lat, "lon": e.lon,
             "municipio_associado": e.municipio, "dist_km": round(e.dist_km, 1), "uf": e.uf,
             "n_safras_validas": int(e.n_safras_validas),
             "safras_validas_periodo": f"{int(e.safra_ini_valida)}/{str(int(e.safra_ini_valida) + 1)[2:]}–"
                                       f"{int(e.safra_fim_valida)}/{str(int(e.safra_fim_valida) + 1)[2:]}"}
        t = t13c[t13c["codigo"] == e.codigo].set_index("fase")
        for f, c in curto.items():
            r[f"pct_aptas_estacao_{c}"] = t["pct_aptas_estacao"].get(f, np.nan)
            r[f"pct_aptas_era5_{c}"] = t["pct_aptas_era5"].get(f, np.nan)
        inc = bool(t["incluida_na_media"].iloc[0]) if len(t) else False
        r["observacao"] = "" if inc else "menos de 2 safras válidas; fora das médias de validação"
        if inc and e.n_safras_validas < 6:
            r["observacao"] = f"só {int(e.n_safras_validas)} safras válidas"
        linhas.append(r)
    return pd.DataFrame(linhas)


def csv_mymaps(dm: pd.DataFrame, de: pd.DataFrame) -> pd.DataFrame:
    m = dm.rename(columns={"municipio": "nome", "lat": "latitude", "lon": "longitude"})
    m.insert(0, "tipo", "Município")
    e = de.rename(columns={"estacao": "nome", "lat": "latitude", "lon": "longitude"})
    e.insert(0, "tipo", "Estação INMET (validação)")
    e["grupo"] = "Estação INMET (validação)"
    e["nome"] = "INMET " + e["codigo_estacao"] + " " + e["nome"]
    out = pd.concat([m, e], ignore_index=True)
    out["nota"] = NOTA
    ordem = (["tipo", "nome", "latitude", "longitude", "grupo", "horas_aptas_fungicidas_h_safra",
              "pct_tempo_apto_fungicidas", "dias_aptos_fungicidas", "melhor_epoca_semeadura",
              "tendencia_sen_h_decada", "tendencia_significativa_5pct",
              "principal_motivo_perda_janela", "pct_horas_inaptas_motivo", "estrategia_prioritaria",
              "codigo_estacao", "municipio_associado", "dist_km", "n_safras_validas",
              "safras_validas_periodo"]
             + [c for c in out.columns if c.startswith("pct_aptas_")] + ["observacao", "nota"])
    out = out[ordem]
    num = [c for c in out.select_dtypes("number").columns if c not in ("latitude", "longitude")]
    out[num] = out[num].round(2)
    out[["latitude", "longitude"]] = out[["latitude", "longitude"]].round(5)
    out.to_csv(OUT / "mymaps_pontos.csv", index=False, encoding="utf-8")
    return out


def _v(x, nd=1):
    return f"{x:.{nd}f}".replace(".", ",")


def csv_mymaps_simples(dm: pd.DataFrame, de: pd.DataFrame):
    """Versões simplificadas: cada indicador já escrito como texto (vírgula decimal)."""
    d = OUT / "mymaps"
    d.mkdir(exist_ok=True)
    m = pd.DataFrame({
        "nome": dm["municipio"], "latitude": dm["lat"].round(5), "longitude": dm["lon"].round(5),
        "grupo": dm["grupo"],
        "horas_aptas_fungicidas": [f"{h:.0f} h por safra ({_v(p, 0)}% do tempo)" for h, p in
                                   zip(dm["horas_aptas_fungicidas_h_safra"], dm["pct_tempo_apto_fungicidas"])],
        "dias_aptos_fungicidas": [f"{x:.0f} de 75 dias" for x in dm["dias_aptos_fungicidas"]],
        "tendencia": [f"{'+' if x >= 0 else '−'}{abs(x):.0f} h por década "
                      f"({'significativa' if sg == 'sim' else 'não significativa'})"
                      for x, sg in zip(dm["tendencia_sen_h_decada"], dm["tendencia_significativa_5pct"])],
        "melhor_epoca_semeadura": dm["melhor_epoca_semeadura"],
        "principal_motivo_perda": [f"{mt} ({_v(p, 0)}% das horas inaptas)" for mt, p in
                                   zip(dm["principal_motivo_perda_janela"], dm["pct_horas_inaptas_motivo"])],
        "estrategia_prioritaria": dm["estrategia_prioritaria"],
        "nota": NOTA})
    m.to_csv(d / "municipios.csv", index=False, encoding="utf-8-sig")
    fases = [("dessecacao", "dessecacao"), ("pos_emergencia", "pos_emergencia"),
             ("fungicidas", "fungicidas"), ("pre_colheita", "pre_colheita")]
    e = pd.DataFrame({
        "nome": "INMET " + de["codigo_estacao"] + " " + de["estacao"],
        "latitude": de["lat"].round(5), "longitude": de["lon"].round(5),
        "municipio_associado": [f"{mu} ({_v(dk)} km)" for mu, dk in zip(de["municipio_associado"], de["dist_km"])],
        "safras_validas": [f"{n} safras ({pp})" for n, pp in zip(de["n_safras_validas"], de["safras_validas_periodo"])]})
    for c, nome in fases:
        e[f"horas_aptas_{nome}"] = [f"estação {_v(a)}% × ERA5 {_v(b)}%" for a, b in
                                    zip(de[f"pct_aptas_estacao_{c}"], de[f"pct_aptas_era5_{c}"])]
    e["observacao"] = de["observacao"]
    e["nota"] = NOTA
    e.to_csv(d / "estacoes_inmet.csv", index=False, encoding="utf-8-sig")
    return m, e


# ----------------------------------------------------------------------------
def fig_F8(dm: pd.DataFrame, de: pd.DataFrame):
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    from matplotlib.lines import Line2D
    from matplotlib.patches import FancyArrow, Rectangle
    import matplotlib.patheffects as pe
    import geopandas as gpd
    from malhas import malhas_pr

    CRS = 5880  # SIRGAS 2000 / Brazil Polyconic (metros)
    uf, mun = malhas_pr()
    uf, mun = uf.to_crs(CRS), mun.to_crs(CRS)
    sel = mun.merge(dm, left_on="code_muni", right_on="cod_ibge")
    pts = sel.copy()
    rp = pts.representative_point()
    pts["x"], pts["y"] = rp.x, rp.y
    est = gpd.GeoDataFrame(de, geometry=gpd.points_from_xy(de["lon"], de["lat"]), crs=4674).to_crs(CRS)
    est["x"], est["y"] = est.geometry.x, est.geometry.y

    v = sel["horas_aptas_fungicidas_h_safra"]
    norm = Normalize(vmin=np.floor(v.min() / 50) * 50, vmax=np.ceil(v.max() / 50) * 50)
    fig = plt.figure(figsize=(13.333, 7.5))
    ax = fig.add_axes([0.01, 0.10, 0.60, 0.80])
    az = fig.add_axes([0.63, 0.30, 0.35, 0.60])

    oeste = dm.loc[dm["grupo_origem"] == "zoneamento_oeste", "municipio"].tolist() + ["Cascavel", "Toledo"]
    x0, y0, x1, y1 = sel[sel["municipio"].isin(oeste)].total_bounds
    pad = 25000
    x0, x1, y0, y1 = x0 - pad - 45000, x1 + pad, y0 - pad, y1 + pad

    def desenhar(a, rotular, fs):
        mun.plot(ax=a, color=E.CINZA_MUN, edgecolor="#ffffff", linewidth=0.25)
        uf.boundary.plot(ax=a, color=E.BASE, linewidth=0.9)
        sel.plot(ax=a, column="horas_aptas_fungicidas_h_safra", cmap=E.SEQ, norm=norm,
                 edgecolor="#ffffff", linewidth=0.5)
        a.scatter(est["x"], est["y"], marker="^", s=70, facecolor="#ffffff", edgecolor=E.INK,
                  linewidth=1.3, zorder=6)
        for _, r in pts[pts["municipio"].isin(rotular)].iterrows():
            dx, dy, ha = POS.get(r["municipio"], (6, 3, "left")) if a is az else \
                POS_MAIN.get(r["municipio"], (6, 3, "left"))
            a.annotate(r["municipio"], (r["x"], r["y"]), xytext=(dx, dy), textcoords="offset points",
                       ha=ha, fontsize=fs, color=E.INK,
                       path_effects=[pe.withStroke(linewidth=2.5, foreground="#ffffff")])
        a.set_aspect("equal")

    # rótulos que não devem encobrir os triângulos das estações
    POS_MAIN = {**E.POS_ROTULO, "Londrina": (-8, 6, "right")}
    POS = {**E.POS_ZOOM, "Foz do Iguaçu": (-9, 4, "right")}
    fora = pts[~(pts["x"].between(x0, x1) & pts["y"].between(y0, y1))]["municipio"].tolist()
    dentro = [m for m in pts["municipio"] if m not in fora]
    desenhar(ax, fora, 8.5)
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor=E.INK2, lw=1, zorder=7))
    ax.set_axis_off()
    desenhar(az, dentro, 9)
    az.set_xlim(x0, x1)
    az.set_ylim(y0, y1)
    az.set_xticks([])
    az.set_yticks([])
    az.set_xlabel("")
    az.set_ylabel("")
    for s in az.spines.values():
        s.set_visible(True)
        s.set_color(E.INK2)
    az.set_title("Oeste (ampliado)", loc="left", fontsize=11, color=E.INK2)

    # rosa dos ventos (seta do norte) e escala - no mapa principal (CRS métrico)
    xa0, xa1 = ax.get_xlim()
    ya0, ya1 = ax.get_ylim()
    w, h = xa1 - xa0, ya1 - ya0
    nx, ny = xa1 - 0.06 * w, ya1 - 0.20 * h
    ax.add_patch(FancyArrow(nx, ny, 0, 0.10 * h, width=0.012 * w, head_width=0.035 * w,
                            head_length=0.04 * h, length_includes_head=True, color=E.INK))
    ax.text(nx, ny + 0.115 * h, "N", ha="center", va="bottom", fontsize=14, fontweight="bold",
            color=E.INK)
    sx, sy = xa0 + 0.04 * w, ya0 + 0.05 * h
    for i, cor in enumerate([E.INK, "#ffffff", E.INK, "#ffffff"]):
        ax.add_patch(Rectangle((sx + i * 25000, sy), 25000, 0.012 * h, facecolor=cor,
                               edgecolor=E.INK, lw=0.8))
    for km in (0, 50, 100):
        ax.text(sx + km * 1000, sy + 0.02 * h, "100 km" if km == 100 else f"{km}",
                ha="center", va="bottom", fontsize=9)

    # legenda de cor e de símbolos
    cax = fig.add_axes([0.66, 0.225, 0.29, 0.025])
    sm = plt.cm.ScalarMappable(cmap=E.SEQ, norm=norm)
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cb.set_label("Horas aptas no período de fungicidas (16/dez–fev), média por safra",
                 fontsize=10, color=E.INK2)
    cb.outline.set_visible(False)
    leg = [Line2D([0], [0], marker="^", color="none", markerfacecolor="#ffffff",
                  markeredgecolor=E.INK, markeredgewidth=1.3, markersize=10,
                  label=f"Estação INMET usada na validação ({PER_EST})")]
    fig.legend(handles=leg, loc="upper left", bbox_to_anchor=(0.655, 0.135), fontsize=10,
               frameon=False)
    fig.text(0.01, 0.955, "Horas aptas para pulverização no período de fungicidas — Paraná",
             fontsize=18, color=E.INK, va="top")
    fig.text(0.01, 0.905, f"Média das safras {ROTULO_SAFRAS} · critério A (Delta T, vento, T, UR, chuva)",
             fontsize=11.5, color=E.INK2, va="top")
    fig.text(0.01, 0.045, FONTE, fontsize=9.5, color=E.INK2)
    fig.text(0.01, 0.018, "Nota: " + NOTA + ".", fontsize=9.5, color=E.INK2)
    fig.savefig(OUT / "figures" / "F8_mapa_apresentacao.png", dpi=300, facecolor="#ffffff")
    plt.close(fig)


# ----------------------------------------------------------------------------
def mapa_interativo(dm: pd.DataFrame, de: pd.DataFrame):
    import folium
    from malhas import malhas_pr

    cores = {}
    t7 = pd.read_csv(TAB / "T7_clusters.csv", encoding="utf-8-sig")
    for g, nome in E.nomes_grupos(t7).items():
        cores[nome] = E.SERIES[g - 1]       # mesmas cores da F1
    m = folium.Map(location=[-24.6, -51.6], zoom_start=7, tiles="OpenStreetMap",
                   control_scale=True)
    uf = malhas_pr()[0]
    uf["geometry"] = uf.geometry.simplify(0.01)
    folium.GeoJson(uf[["geometry"]].to_json(), name="Paraná",
                   style_function=lambda _: {"color": "#898781", "weight": 1.5, "fill": False}).add_to(m)

    def tabela(linhas):
        tr = "".join(f"<tr><td style='padding:2px 8px 2px 0;color:#52514e'>{html.escape(k)}</td>"
                     f"<td style='padding:2px 0'><b>{html.escape(str(v))}</b></td></tr>"
                     for k, v in linhas)
        return f"<table style='font-family:system-ui,sans-serif;font-size:12px'>{tr}</table>"

    def f1(x, nd=1):
        return "–" if pd.isna(x) else f"{x:.{nd}f}".replace(".", ",")

    camada_m = folium.FeatureGroup(name="Municípios").add_to(m)
    for _, r in dm.iterrows():
        pop = (f"<div style='font-family:system-ui,sans-serif'><b style='font-size:14px'>"
               f"{html.escape(r.municipio)}</b><br><span style='color:#52514e'>{html.escape(r.grupo)}"
               "</span></div>" + tabela([
                   ("Horas aptas, período de fungicidas", f"{f1(r.horas_aptas_fungicidas_h_safra, 0)} h/safra"),
                   ("% do tempo apto", f"{f1(r.pct_tempo_apto_fungicidas)} %"),
                   ("Dias aptos", f"{f1(r.dias_aptos_fungicidas)} por safra"),
                   ("Melhor época de semeadura", r.melhor_epoca_semeadura),
                   ("Tendência de Sen", f"{f1(r.tendencia_sen_h_decada, 0)} h/década "
                                        f"({'significativa' if r.tendencia_significativa_5pct == 'sim' else 'não significativa'})"),
                   ("Principal motivo de perda", f"{r.principal_motivo_perda_janela} "
                                                 f"({f1(r.pct_horas_inaptas_motivo, 0)} % das horas inaptas)"),
                   ("Estratégia prioritária", r.estrategia_prioritaria)]))
        folium.CircleMarker([r.lat, r.lon], radius=9, color="#ffffff", weight=2, fill=True,
                            fill_color=cores[r.grupo], fill_opacity=0.95,
                            tooltip=r.municipio, popup=folium.Popup(pop, max_width=420)).add_to(camada_m)

    camada_e = folium.FeatureGroup(name="Estações INMET (validação)").add_to(m)
    fases = [("dessecacao", "Dessecação"), ("pos_emergencia", "Pós-emergência"),
             ("fungicidas", "Fungicidas"), ("pre_colheita", "Pré-colheita")]
    for _, r in de.iterrows():
        linhas = [("Município associado", f"{r.municipio_associado} ({f1(r.dist_km)} km)"),
                  ("Safras válidas", f"{r.n_safras_validas} ({r.safras_validas_periodo})")]
        linhas += [(f"% aptas {n} (estação / ERA5)",
                    f"{f1(r[f'pct_aptas_estacao_{c}'])} / {f1(r[f'pct_aptas_era5_{c}'])}") for c, n in fases]
        if r.observacao:
            linhas.append(("Observação", r.observacao))
        pop = (f"<div style='font-family:system-ui,sans-serif'><b style='font-size:14px'>INMET "
               f"{html.escape(r.codigo_estacao)} – {html.escape(r.estacao)}</b><br>"
               f"<span style='color:#52514e'>Estação usada na validação, {html.escape(PER_EST)}</span></div>"
               + tabela(linhas))
        folium.RegularPolygonMarker([r.lat, r.lon], number_of_sides=3, radius=10, rotation=30,
                                    color="#0b0b0b", weight=2, fill=True, fill_color="#ffffff",
                                    fill_opacity=1, tooltip=f"INMET {r.codigo_estacao} {r.estacao}",
                                    popup=folium.Popup(pop, max_width=420)).add_to(camada_e)
    folium.LayerControl(collapsed=False).add_to(m)

    itens = "".join(f"<div><span style='display:inline-block;width:12px;height:12px;border-radius:50%;"
                    f"background:{c};margin-right:6px;vertical-align:middle'></span>{html.escape(n)}</div>"
                    for n, c in cores.items())
    itens += ("<div><span style='display:inline-block;width:0;height:0;border-left:7px solid transparent;"
              "border-right:7px solid transparent;border-bottom:12px solid #0b0b0b;margin-right:5px;"
              "vertical-align:middle'></span>Estação INMET (validação)</div>")
    caixa = ("position:fixed;z-index:9999;background:rgba(255,255,255,.94);padding:8px 12px;"
             "border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.25);font-family:system-ui,sans-serif;")
    m.get_root().html.add_child(folium.Element(
        f"<div style='{caixa}top:10px;left:60px;font-size:15px'><b>Janelas de pulverização no "
        "período de fungicidas — Paraná</b><br><span style='font-size:12px;color:#52514e'>"
        "Clique nos pontos para ver os indicadores</span></div>"
        f"<div style='{caixa}bottom:44px;left:10px;font-size:12px'>{itens}</div>"
        f"<div style='{caixa}bottom:8px;left:50%;transform:translateX(-50%);font-size:11.5px;"
        f"color:#52514e;max-width:90%;text-align:center'>{html.escape(NOTA)}</div>"))
    m.save(str(OUT / "mapa_interativo.html"))


# ----------------------------------------------------------------------------
def refazer_F1_F5():
    muns = pd.read_csv(PROC / "municipios.csv", encoding="utf-8")
    configurar_agregados(muns)
    t7 = pd.read_csv(TAB / "T7_clusters.csv", encoding="utf-8-sig")
    t6 = pd.read_csv(TAB / "T6_mann_kendall.csv", encoding="utf-8-sig")
    t6["fase"] = pd.Categorical(t6["fase"], FASES_OP, ordered=True)
    uf, mun, sel, pts = E.malhas(muns)
    E.fig_F1(uf, mun, sel, pts, t7, int(t7["grupo"].nunique()))
    E.fig_F5(uf, mun, sel, pts, t6)
    return E.nomes_grupos(t7), t7


def main() -> None:
    pd.set_option("display.width", 220)
    dm, de = dados_municipios(), dados_estacoes()
    out = csv_mymaps(dm, de)
    print(f"mymaps_pontos.csv: {len(out)} pontos ({(out['tipo'] == 'Município').sum()} municípios, "
          f"{(out['tipo'] != 'Município').sum()} estações)")
    ms, es = csv_mymaps_simples(dm, de)
    print(f"mymaps/municipios.csv: {len(ms)}; mymaps/estacoes_inmet.csv: {len(es)}")
    print(ms.head(3).to_string(index=False))
    print(es.to_string(index=False))
    fig_F8(dm, de)
    print("figura: F8_mapa_apresentacao.png")
    mapa_interativo(dm, de)
    print("mapa_interativo.html")
    nomes, t7 = refazer_F1_F5()
    m = t7.groupby("grupo")["horas_aptas_set_abr"].mean()
    for g, n in nomes.items():
        mem = ", ".join(t7.loc[t7["grupo"] == g, "municipio"])
        print(f"  grupo {g} = {n}: média {m[g]:.0f} h aptas set-abr; {mem}")
    print(dm[["municipio", "grupo", "horas_aptas_fungicidas_h_safra", "melhor_epoca_semeadura",
              "tendencia_sen_h_decada", "principal_motivo_perda_janela"]].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
