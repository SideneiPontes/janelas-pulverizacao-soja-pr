"""Painel de especialistas (Google Forms) no multicritério: notas C2-C5, concordância e TOPSIS.

Uso:  python -I src/painel_especialistas.py
Pré-requisito: python -I src/ahp_topsis.py (T8, T8b e T9 já calculados). Não muda C1, pesos AHP
nem os cenários de pesos; só as notas qualitativas C2-C5.

Entrada : data/raw/painel_especialistas.csv (NÃO vai para o repositório)
Anonimização: o carimbo de data/hora e qualquer coluna de nome são descartados; os respondentes
são E1, E2, ... na ordem das linhas.
Critérios: Custo = C2 (custo), Risco = C3 (custo), Facilidade de adoção = C4 (benefício),
Conformidade e segurança = C5 (benefício); escala 1-9 com o mesmo sentido do código
(C2/C3: 9 = custo/risco muito alto; C4/C5: 9 = muito fácil/muito conforme).
Inclusão no painel principal: >= 1 ano de experiência com aplicação de defensivos. Todos os
respondentes entram numa análise de sensibilidade.

Saídas (outputs/tables): painel_especialistas_anonimizado.csv, T14_painel_respostas.csv,
T14b_painel_resumo.csv, T14c_concordancia_kendall.csv, T15_topsis_painel.csv,
T15b_sensibilidade_painel.csv, T15c_comparacao_versoes.csv
Figuras: F6b_cenarios_topsis.png (refeita com as notas do painel), F9_painel_vs_autores.png
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2, rankdata

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indicadores import ESTADO, OESTE, TAB  # noqa: E402
from ahp_topsis import (ALTERNATIVAS, CENARIOS_PESOS, CRITERIOS, FIG, fig_F6b, ler_xlsx,  # noqa: E402
                        sensibilidade, topsis)

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "raw" / "painel_especialistas.csv"
MAPA_CRIT = {"Custo": "C2", "Risco": "C3", "Facilidade de adoção": "C4", "Conformidade e segurança": "C5"}
COL_ANOS = "Anos de experiência com aplicação de defensivos"
COL_FORM, COL_ONDE = "Formação", "Onde atua"
ALTS = list(ALTERNATIVAS)
CODS = list(CRITERIOS)
QUAL = ["C2", "C3", "C4", "C5"]
BENEF = np.array([CRITERIOS[c][1] == "beneficio" for c in CODS])
MIN_ANOS = 1


# ----------------------------------------------------------------------------
def ler_painel() -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    bruto = pd.read_csv(CSV, encoding="utf-8")
    descartadas = [c for c in bruto.columns if re.search(r"carimbo|data/hora|timestamp|nome|e-?mail", c, re.I)]
    d = bruto.drop(columns=descartadas)
    d.insert(0, "respondente", [f"E{i + 1}" for i in range(len(d))])
    d.to_csv(TAB / "painel_especialistas_anonimizado.csv", index=False, encoding="utf-8-sig")

    linhas = []
    padrao = re.compile(r"^(.*?)\s*\[(A\d)\b.*\]$")
    for c in d.columns:
        m = padrao.match(c)
        if not m or m.group(1).strip() not in MAPA_CRIT:
            continue
        crit, alt = MAPA_CRIT[m.group(1).strip()], m.group(2)
        for _, r in d.iterrows():
            linhas.append({"respondente": r["respondente"], "alternativa": alt, "criterio": crit,
                           "nota": pd.to_numeric(r[c], errors="coerce")})
    L = pd.DataFrame(linhas)
    resp = d[["respondente", COL_FORM, COL_ANOS, COL_ONDE]].rename(
        columns={COL_FORM: "formacao", COL_ANOS: "anos_experiencia", COL_ONDE: "onde_atua"})
    resp["formacao"] = resp["formacao"].astype(str).str.strip()
    resp["anos_experiencia"] = pd.to_numeric(resp["anos_experiencia"], errors="coerce")
    resp["incluido"] = np.where(resp["anos_experiencia"] >= MIN_ANOS, "sim", "não")
    L = resp.merge(L, on="respondente")
    L["alternativa"] = pd.Categorical(L["alternativa"], ALTS, ordered=True)
    L["criterio"] = pd.Categorical(L["criterio"], QUAL, ordered=True)
    L = L.sort_values(["respondente", "alternativa", "criterio"]).reset_index(drop=True)
    return L, resp, descartadas


def kendall_w(M: np.ndarray) -> tuple[float, float, float, int, int]:
    """M: avaliadores x objetos (notas). W com correção para empates; p pelo qui-quadrado."""
    M = M[~np.isnan(M).any(axis=1)]
    m, n = M.shape
    R = np.vstack([rankdata(row) for row in M])
    S = ((R.sum(axis=0) - m * (n + 1) / 2) ** 2).sum()
    T = sum(((np.unique(row, return_counts=True)[1] ** 3) - np.unique(row, return_counts=True)[1]).sum()
            for row in M)
    den = m ** 2 * (n ** 3 - n) - m * T
    W = 12 * S / den if den > 0 else np.nan
    q = m * (n - 1) * W
    p = chi2.sf(q, n - 1) if not np.isnan(W) else np.nan
    return W, q, p, m, n


# ----------------------------------------------------------------------------
def main() -> None:
    pd.set_option("display.width", 220)
    L, resp, descartadas = ler_painel()
    autores, _ = ler_xlsx()                       # notas dos autores (C2-C5), versão "autores"
    autores = autores.loc[ALTS, QUAL]

    # T14
    T14 = L.assign(incluido=L["incluido"])[["respondente", "formacao", "anos_experiencia", "onde_atua",
                                            "incluido", "alternativa", "criterio", "nota"]]
    T14.to_csv(TAB / "T14_painel_respostas.csv", index=False, encoding="utf-8-sig")

    P = L[L["incluido"] == "sim"]
    g = P.groupby(["alternativa", "criterio"], observed=True)["nota"]
    T14b = pd.DataFrame({"mediana_painel": g.median(), "media_painel": g.mean(), "minimo_painel": g.min(),
                         "maximo_painel": g.max(), "n_painel": g.count()})
    T14b["mediana_todos"] = L.groupby(["alternativa", "criterio"], observed=True)["nota"].median()
    T14b = T14b.reset_index()
    T14b.insert(2, "nota_autores", [autores.loc[a, c] for a, c in zip(T14b["alternativa"], T14b["criterio"])])
    T14b.insert(3, "tipo", [CRITERIOS[c][1] for c in T14b["criterio"]])
    T14b.round(3).to_csv(TAB / "T14b_painel_resumo.csv", index=False, encoding="utf-8-sig")

    # T14c
    lin = []
    for grupo, D in (("painel principal (>= 1 ano)", P), ("todos os respondentes", L)):
        for c in QUAL:
            M = D[D["criterio"] == c].pivot(index="respondente", columns="alternativa", values="nota")[ALTS]
            W, q, p, m, n = kendall_w(M.to_numpy(float))
            lin.append({"grupo": grupo, "criterio": c, "descricao": CRITERIOS[c][0], "n_avaliadores": m,
                        "n_alternativas": n, "W_kendall": W, "qui2": q, "gl": n - 1, "p_valor": p,
                        "respondentes": ", ".join(M.index)})
    T14c = pd.DataFrame(lin)
    T14c.round(4).to_csv(TAB / "T14c_concordancia_kendall.csv", index=False, encoding="utf-8-sig")

    # matrizes de notas
    def matriz(stat: str, D: pd.DataFrame) -> pd.DataFrame:
        x = D.groupby(["alternativa", "criterio"], observed=True)["nota"].agg(stat).unstack()
        return x.loc[ALTS, QUAL].astype(float)
    NOTAS = {"autores": autores, "painel_mediana": matriz("median", P),
             "painel_media": matriz("mean", P), "todos_mediana": matriz("median", L)}

    # C1 e pesos (inalterados)
    t8b = pd.read_csv(TAB / "T8b_C1_corrigido.csv", encoding="utf-8-sig").set_index("alternativa")
    t8 = pd.read_csv(TAB / "T8_ganho_horas_alternativas.csv", encoding="utf-8-sig")
    C1 = {("corrigido_estacoes", ESTADO): t8b.loc[ALTS, "C1_corrigido_PR"],
          ("corrigido_estacoes", OESTE): t8b.loc[ALTS, "C1_corrigido_Oeste"]}
    for reg in (ESTADO, OESTE):
        C1[("ERA5", reg)] = t8[t8["municipio"] == reg].set_index("alternativa").loc[ALTS, "ganho_h_media"]
    t9 = pd.read_csv(TAB / "T9_pesos_ahp.csv", encoding="utf-8-sig").set_index("criterio")
    w_ahp = t9.loc[CODS, "peso"].to_numpy(float)

    def X(notas: pd.DataFrame, c1: pd.Series) -> np.ndarray:
        return pd.concat([c1.rename("C1"), notas], axis=1)[CODS].to_numpy(float)

    def pesos(cen):
        p = CENARIOS_PESOS[cen]
        return w_ahp if p is None else np.array(p, float)

    def posicoes(cc):
        return pd.Series(cc).rank(ascending=False, method="min").astype(int).to_numpy()

    # T15: 4 cenários x 2 regiões, painel (principal) e autores, C1 corrigido
    lin = []
    for versao in ("painel_mediana", "autores"):
        for cen in CENARIOS_PESOS:
            wc = pesos(cen)
            for reg in (ESTADO, OESTE):
                cc = topsis(X(NOTAS[versao], C1[("corrigido_estacoes", reg)]), wc, BENEF)[-1]
                for a, v, p in zip(ALTS, cc, posicoes(cc)):
                    lin.append({"cenario": cen, "regiao": reg, "versao_notas": versao,
                                "versao_C1": "corrigido_estacoes", "alternativa": a,
                                "descricao": ALTERNATIVAS[a], "CC": v, "posicao": int(p),
                                **{f"peso_{k}": x for k, x in zip(CODS, wc)}})
    T15 = pd.DataFrame(lin).sort_values(["versao_notas", "cenario", "regiao", "posicao"],
                                        key=lambda s: s.map(list(CENARIOS_PESOS).index)
                                        if s.name == "cenario" else s)
    T15.round(4).to_csv(TAB / "T15_topsis_painel.csv", index=False, encoding="utf-8-sig")

    # T15b: sensibilidade +-50 % (passo 10 %), pesos AHP, notas do painel, C1 corrigido
    sens = []
    for reg in (ESTADO, OESTE):
        s, lider0 = sensibilidade(X(NOTAS["painel_mediana"], C1[("corrigido_estacoes", reg)]),
                                  w_ahp, BENEF, CODS, ALTS)
        s.insert(0, "regiao", reg)
        s.insert(1, "versao_notas", "painel_mediana")
        s.insert(2, "versao_C1", "corrigido_estacoes")
        s["lider_base"] = lider0
        sens.append(s)
    T15b = pd.concat(sens, ignore_index=True)
    T15b.round(4).to_csv(TAB / "T15b_sensibilidade_painel.csv", index=False, encoding="utf-8-sig")

    # T15c: comparação de versões, cenário base, Paraná
    versoes = [("a", "autores", "autores", "corrigido_estacoes"),
               ("b", "painel_mediana", "painel_mediana", "corrigido_estacoes"),
               ("c", "painel_media", "painel_media", "corrigido_estacoes"),
               ("d", "todos_mediana", "todos_mediana", "corrigido_estacoes"),
               ("e", "painel_mediana", "painel_mediana", "ERA5")]
    for i, c in enumerate(QUAL):
        n_ = NOTAS["painel_mediana"].copy()
        n_[c] = autores[c]
        NOTAS[f"painel_mediana_{c}_autores"] = n_
        versoes.append((f"f{i + 1}", f"painel_mediana_{c}_autores", f"painel_mediana_{c}_autores",
                        "corrigido_estacoes"))
    DESC = {"a": "notas dos autores + C1 corrigido (resultado anterior)",
            "b": "mediana do painel principal + C1 corrigido (resultado principal)",
            "c": "média do painel principal + C1 corrigido",
            "d": "mediana de todos os respondentes + C1 corrigido",
            "e": "mediana do painel principal + C1 só ERA5",
            **{f"f{i + 1}": f"mediana do painel, com {c} dos autores + C1 corrigido" for i, c in enumerate(QUAL)}}
    lin = []
    for cod, nome, chave, vc1 in versoes:
        cc = topsis(X(NOTAS[chave], C1[(vc1, ESTADO)]), w_ahp, BENEF)[-1]
        pos = posicoes(cc)
        ordem = " > ".join(np.array(ALTS)[np.argsort(-cc, kind="stable")])
        for a, v, p in zip(ALTS, cc, pos):
            lin.append({"versao": cod, "descricao_versao": DESC[cod], "versao_notas": nome,
                        "versao_C1": vc1, "cenario": "base_AHP", "regiao": ESTADO, "alternativa": a,
                        "CC": v, "posicao": int(p), "ordem": ordem,
                        "primeiro": ALTS[int(np.argmax(cc))]})
    T15c = pd.DataFrame(lin)
    T15c.round(4).to_csv(TAB / "T15c_comparacao_versoes.csv", index=False, encoding="utf-8-sig")

    # figuras
    t6b = T15[(T15["versao_notas"] == "painel_mediana") & (T15["regiao"] == ESTADO)]
    fig_F6b(t6b, ALTS, notas_rotulo="notas do painel de especialistas, mediana")
    fig_F9(T15c)
    resumo_md(resp, T14b, T14c, T15, T15b, T15c)

    # ------------------------------------------------------------- resumo
    def titulo(s):
        print("\n" + "=" * 100 + f"\n{s}\n" + "=" * 100)

    print(f"Colunas descartadas na anonimização: {descartadas}")
    titulo("Respondentes")
    print(resp.to_string(index=False))
    print(f"Notas faltantes: {int(L['nota'].isna().sum())}; fora de 1-9: "
          f"{int(((L['nota'] < 1) | (L['nota'] > 9)).sum())}")
    titulo("T14b - autores x mediana do painel")
    print(T14b.pivot(index="alternativa", columns="criterio",
                     values=["nota_autores", "mediana_painel", "mediana_todos"]).to_string())
    titulo("T14c - W de Kendall")
    print(T14c[["grupo", "criterio", "n_avaliadores", "W_kendall", "qui2", "p_valor"]].round(3).to_string(index=False))
    titulo("T15 - TOPSIS, notas do painel (C1 corrigido)")
    for (cen, reg), d in T15[T15["versao_notas"] == "painel_mediana"].groupby(["cenario", "regiao"], sort=False):
        print(f"  {reg:15s} {cen:17s} " + "  ".join(f"{r.alternativa}({r.CC:.3f})" for r in d.itertuples()))
    titulo("T15b - o 1º lugar muda (+-50 %)?")
    print(T15b.groupby(["regiao", "criterio"])["primeiro_mudou"].any().unstack().to_string())
    titulo("T15c - comparação de versões (base, Paraná)")
    print(T15c.drop_duplicates("versao")[["versao", "descricao_versao", "ordem"]].to_string(index=False))


def v(x, nd=3):
    return "–" if pd.isna(x) else f"{x:.{nd}f}".replace(".", ",")


CONCLUSOES = """\
- **O 1º lugar muda: A1 (pulverização noturna) passa à frente de A2 (pontas antideriva)** com as notas
  do painel, nos 4 cenários de pesos, no Paraná e no Oeste. A2 fica em 2º em todos. No cenário base do
  Paraná a diferença é pequena (CC 0,948 × 0,909).
- **O novo 1º lugar é estável**: A1 continua 1º em todos os testes de −50 % a +50 % em cada peso, no
  Paraná e no Oeste, e também com a média do painel, com todos os respondentes (incluindo E2) e com o
  C1 só do ERA5 (versões c, d, e).
- **A troca vem de C3, C4 e C5, não do custo.** Voltar só o C2 às notas dos autores mantém A1 em 1º
  (f1); voltar C3, C4 ou C5 (f2, f3, f4) devolve o 1º lugar a A2. O painel dá a A1 risco 2 (autores: 6) e
  a A2 facilidade de adoção 3 e conformidade 6 (autores: 8 e 9).
- **Concordância só nos critérios de custo e risco.** W de Kendall alto e significativo em C2 (0,79;
  p = 0,04) e C3 (0,88; p = 0,02); praticamente nulo em C4 (0,15; p = 0,81) e C5 (0,03; p = 0,99). As
  medianas de C4 e C5, que decidem parte da troca, não refletem consenso.
- **Alerta de interpretação da escala**: A2 recebeu facilidade de adoção 3, 3 e 6 (1 = muito difícil),
  abaixo do drone (6, 7, 1). Vale confirmar com os respondentes se o sentido da escala de C4/C5 (9 = mais
  fácil / mais conforme) foi entendido como no código.
- **O resto da ordem quase não muda**: A5 continua 3º no cenário base (com CC menor, porque o painel
  vê custo e risco altos), A3 4º, A6 5º e A4 (drone) último em todas as versões.
- **Painel pequeno**: 3 especialistas no painel principal (E2 ficou fora por ter 0 ano de
  experiência com aplicação). O resultado deve ser apresentado como indicativo.
"""


def resumo_md(resp, T14b, T14c, T15, T15b, T15c):
    L = []
    add = L.append
    add("# RESUMO PAINEL — notas de especialistas no multicritério\n")
    add("Gerado por `src/painel_especialistas.py`. C1 (ganho de horas, corrigido pelas estações), pesos AHP "
        "e os 4 cenários de pesos não mudaram; só as notas C2–C5. Escala 1–9: C2 custo e C3 risco "
        "(9 = muito alto, quanto menor melhor); C4 facilidade e C5 conformidade (9 = melhor). "
        "Respostas anonimizadas (sem data/hora e sem nomes).\n")
    add("## Respondentes\n")
    add("| Respondente | Formação | Anos de experiência com aplicação | Onde atua | Painel principal |")
    add("|---|---|---|---|---|")
    for r in resp.itertuples():
        add(f"| {r.respondente} | {r.formacao} | {r.anos_experiencia:g} | {r.onde_atua} | {r.incluido} |")
    add("\nCritério de inclusão: ≥ 1 ano de experiência com aplicação de defensivos. Sem notas faltantes.\n")
    add("## Notas: autores × mediana do painel principal (n = 3)\n")
    add("| Alternativa | C2 custo | C3 risco | C4 facilidade | C5 conformidade |")
    add("|---|---|---|---|---|")
    for a in ALTS:
        cel = []
        for c in QUAL:
            x = T14b[(T14b["alternativa"] == a) & (T14b["criterio"] == c)].iloc[0]
            cel.append(f"{x.nota_autores:g} → {x.mediana_painel:g} ({x.minimo_painel:g}–{x.maximo_painel:g})")
        add(f"| {a} {ALTERNATIVAS[a]} | " + " | ".join(cel) + " |")
    add("\nFormato: autores → mediana do painel (mínimo–máximo do painel).\n")
    add("## Concordância (W de Kendall, com correção para empates)\n")
    add("| Critério | Painel principal (n = 3): W (p) | Todos (n = 4): W (p) |")
    add("|---|---|---|")
    for c in QUAL:
        a_ = T14c[(T14c["criterio"] == c) & T14c["grupo"].str.startswith("painel")].iloc[0]
        b_ = T14c[(T14c["criterio"] == c) & T14c["grupo"].str.startswith("todos")].iloc[0]
        add(f"| {c} {CRITERIOS[c][0]} | {v(a_.W_kendall)} ({v(a_.p_valor)}) | {v(b_.W_kendall)} ({v(b_.p_valor)}) |")
    add("\n## Rankings TOPSIS (CC) com as notas do painel e C1 corrigido\n")
    add("| Cenário | Paraná (média) | Oeste (média) |")
    add("|---|---|---|")
    P = T15[T15["versao_notas"] == "painel_mediana"]
    for cen in CENARIOS_PESOS:
        cel = []
        for reg in (ESTADO, OESTE):
            d = P[(P["cenario"] == cen) & (P["regiao"] == reg)].sort_values("posicao")
            cel.append(" > ".join(f"{x.alternativa} ({v(x.CC)})" for x in d.itertuples()))
        add(f"| {cen} | " + " | ".join(cel) + " |")
    add("\n## O 1º lugar muda nos testes de ±50 % no peso de cada critério?\n")
    for reg in (ESTADO, OESTE):
        d = T15b[T15b["regiao"] == reg]
        mud = d[d["primeiro_mudou"]]
        txt = "não" if mud.empty else "sim: " + ", ".join(f"{x.criterio} {x.variacao_pct:+d}% → {x.primeiro}"
                                                          for x in mud.itertuples())
        add(f"- {reg}: {txt} (1º lugar na base: {d['lider_base'].iloc[0]}).")
    add("\n## Comparação de versões (cenário base, Paraná)\n")
    add("| Versão | Descrição | Ordem | CC A1 | CC A2 | CC A5 |")
    add("|---|---|---|---|---|---|")
    for cod, d in T15c.groupby("versao", sort=False):
        cc = d.set_index("alternativa")["CC"]
        add(f"| {cod} | {d['descricao_versao'].iloc[0]} | {d['ordem'].iloc[0]} | {v(cc['A1'])} | "
            f"{v(cc['A2'])} | {v(cc['A5'])} |")
    add("\n## O que mudou de conclusão\n")
    add(CONCLUSOES)
    (ROOT / "outputs" / "RESUMO_PAINEL.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def fig_F9(T15c: pd.DataFrame):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from estatistica import INK, SERIES, SURF, virgula  # aplica o estilo

    d = T15c[T15c["versao"].isin(["a", "b"])]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    larg = 0.38
    x = np.arange(len(ALTS))
    for i, (v, rot) in enumerate((("a", "Notas dos autores"), ("b", "Notas do painel (mediana, n = 3)"))):
        s = d[d["versao"] == v].set_index("alternativa").loc[ALTS]
        xs = x + (i - 0.5) * larg
        ax.bar(xs, s["CC"], width=larg, color=SERIES[i], edgecolor=SURF, linewidth=1.5, label=rot)
        for xi, cc, p in zip(xs, s["CC"], s["posicao"]):
            ax.text(xi, cc + 0.012, f"{cc:.2f}".replace(".", ",") + f"\n{p}º", ha="center", va="bottom",
                    fontsize=7.5, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{a}\n{ALTERNATIVAS[a]}" for a in ALTS], fontsize=7.5)
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, 1.08)
    ax.yaxis.set_major_formatter(virgula("{:.1f}"))
    ax.set_ylabel("Coeficiente de proximidade (TOPSIS)")
    ax.grid(axis="y")
    ax.legend(loc="upper right", fontsize=8, frameon=False)
    ax.set_title("TOPSIS no cenário base (pesos AHP), Paraná, C1 corrigido pelas estações INMET: "
                 "notas dos autores × painel de especialistas", loc="left", fontsize=9.5)
    import textwrap
    ax.set_xticklabels(["\n".join(textwrap.wrap(f"{a} — {ALTERNATIVAS[a]}", 22, break_long_words=False,
                                                break_on_hyphens=False)) for a in ALTS], fontsize=7.5)
    fig.tight_layout()
    fig.savefig(FIG / "F9_painel_vs_autores.png", dpi=300)
    plt.close(fig)


if __name__ == "__main__":
    main()
