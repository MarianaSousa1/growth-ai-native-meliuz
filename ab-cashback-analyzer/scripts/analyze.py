
import sys, json
import numpy as np
import pandas as pd

try:
    from ingest import clean
except ImportError:
    from scripts.ingest import clean


RNG = np.random.default_rng(42)  # semente fixa => resultado reproduzível


def _agg_por_variante(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("grupo").agg(
        dias=("data_parsed", "nunique"),
        compradores=("compradores", "sum"),
        gmv=("gmv", "sum"),
        comissao=("comissao", "sum"),
        cashback=("cashback", "sum"),
    )
    g["lucro"] = g["comissao"] - g["cashback"]
    # métricas normalizadas — as que sustentam a decisão quando o volume difere
    g["roi"] = np.where(g["cashback"] > 0, g["lucro"] / g["cashback"], np.nan)
    g["margem_pct"] = np.where(g["gmv"] > 0, 100 * g["lucro"] / g["gmv"], np.nan)
    g["ticket_medio"] = np.where(g["compradores"] > 0, g["gmv"] / g["compradores"], np.nan)
    g["cashback_por_comprador"] = np.where(g["compradores"] > 0, g["cashback"] / g["compradores"], np.nan)
    g["lucro_por_comprador"] = np.where(g["compradores"] > 0, g["lucro"] / g["compradores"], np.nan)
    g["cashback_pct_gmv"] = np.where(g["gmv"] > 0, 100 * g["cashback"] / g["gmv"], np.nan)
    g["take_rate_pct"] = np.where(g["gmv"] > 0, 100 * g["comissao"] / g["gmv"], np.nan)
    return g.sort_index()


def _daily_metric(df: pd.DataFrame, grupo: str) -> np.ndarray:
    """lucro/comprador por DIA para uma variante — a unidade amostral da inferência."""
    d = df[df["grupo"] == grupo]
    daily = d.groupby("data_parsed").agg(
        comissao=("comissao", "sum"), cashback=("cashback", "sum"), comp=("compradores", "sum")
    )
    lucro = daily["comissao"] - daily["cashback"]           # lucro = comissão − cashback
    daily["lpc"] = np.where(daily["comp"] > 0, lucro / daily["comp"], np.nan)
    return daily["lpc"].dropna().to_numpy()


def _bootstrap_ci(x: np.ndarray, n=5000, alpha=0.05):
    """IC da média por bootstrap. Robusto e sem supor normalidade."""
    if len(x) == 0:
        return (np.nan, np.nan, np.nan)
    if len(x) == 1:
        return (float(x[0]), float(x[0]), float(x[0]))
    means = RNG.choice(x, size=(n, len(x)), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return (float(x.mean()), float(lo), float(hi))


def _bootstrap_diff(a: np.ndarray, b: np.ndarray, n=5000, alpha=0.05):
    """
    IC e p-valor (bicaudal aproximado) da diferença de médias a-b por bootstrap.
    Serve para dizer se a vantagem da vencedora é distinguível de ruído.
    """
    if len(a) < 2 or len(b) < 2:
        return None
    da = RNG.choice(a, size=(n, len(a)), replace=True).mean(axis=1)
    db = RNG.choice(b, size=(n, len(b)), replace=True).mean(axis=1)
    diff = da - db
    lo, hi = np.percentile(diff, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    # p-valor bicaudal: proporção de reamostras que cruzam zero, dobrada
    p = 2 * min((diff <= 0).mean(), (diff >= 0).mean())
    return {
        "diferenca_media": float(diff.mean()),
        "ic95_baixo": float(lo),
        "ic95_alto": float(hi),
        "p_valor_aprox": float(min(p, 1.0)),
        "significativo": bool(lo > 0 or hi < 0),  # IC não cruza zero
    }


def _novelty_check(df: pd.DataFrame, grupo: str) -> dict:
    """
    Detecta efeito de novidade: a variante ganha só no início e decai?
    Compara a média de lucro/comprador da 1ª metade vs. 2ª metade do período.
    """
    x = _daily_metric(df, grupo)
    if len(x) < 6:
        return {"aplicavel": False}
    meio = len(x) // 2
    prim, seg = x[:meio], x[meio:]
    delta = (seg.mean() - prim.mean())
    rel = delta / abs(prim.mean()) if prim.mean() != 0 else 0.0
    return {
        "aplicavel": True,
        "media_1a_metade": float(prim.mean()),
        "media_2a_metade": float(seg.mean()),
        "variacao_relativa_pct": float(100 * rel),
        "decaimento_relevante": bool(rel < -0.20),  # caiu >20% => alerta
    }


def analyze(df: pd.DataFrame, quality: dict) -> dict:
    parceiros = sorted(df["parceiro"].unique())
    g = _agg_por_variante(df)

    # séries diárias (para gráficos) — uma linha por (data, grupo)
    daily = df.groupby(["data_parsed", "grupo"]).agg(
        compradores=("compradores", "sum"),
        gmv=("gmv", "sum"),
        comissao=("comissao", "sum"),
        cashback=("cashback", "sum"),
    ).reset_index()
    daily["lucro"] = daily["comissao"] - daily["cashback"]
    daily["data"] = daily["data_parsed"].dt.strftime("%Y-%m-%d")

    series = {}
    for grp in g.index:
        sub = daily[daily["grupo"] == grp].sort_values("data_parsed")
        series[grp] = {
            "data": sub["data"].tolist(),
            "lucro": sub["lucro"].round(2).tolist(),
            "lucro_acumulado": sub["lucro"].cumsum().round(2).tolist(),
            "compradores": sub["compradores"].tolist(),
            "gmv": sub["gmv"].round(2).tolist(),
            "cashback": sub["cashback"].round(2).tolist(),
        }

    # agregação semanal
    daily["semana"] = daily["data_parsed"].dt.to_period("W").dt.start_time.dt.strftime("%Y-%m-%d")
    semanal = {}
    for grp in g.index:
        sub = daily[daily["grupo"] == grp].groupby("semana").agg(
            lucro=("lucro", "sum"), gmv=("gmv", "sum"),
            compradores=("compradores", "sum"), cashback=("cashback", "sum")
        ).reset_index()
        semanal[grp] = {
            "semana": sub["semana"].tolist(),
            "lucro": sub["lucro"].round(2).tolist(),
            "gmv": sub["gmv"].round(2).tolist(),
        }

    # ---------- estatística: quem lidera em lucro/comprador e é confiável? ----------
    grupos = list(g.index)
    daily_series = {grp: _daily_metric(df, grp) for grp in grupos}
    ci = {grp: _bootstrap_ci(daily_series[grp]) for grp in grupos}

    # ranking pela MÉDIA diária de lucro/comprador (métrica normalizada de decisão)
    ranking = sorted(grupos, key=lambda gr: (ci[gr][0] if not np.isnan(ci[gr][0]) else -1e18), reverse=True)
    vencedora = ranking[0]
    segunda = ranking[1] if len(ranking) > 1 else None

    comparacao = None
    if segunda is not None:
        comparacao = _bootstrap_diff(daily_series[vencedora], daily_series[segunda])

    novelty = {grp: _novelty_check(df, grp) for grp in grupos}

    # ---------- decisão ----------
    # a variante mais lucrativa em TOTAL (lucro absoluto) e a de maior GMV
    lider_lucro_abs = g["lucro"].idxmax()
    lider_gmv = g["gmv"].idxmax()

    decisao = _montar_decisao(g, ci, vencedora, segunda, comparacao,
                              lider_lucro_abs, lider_gmv, novelty, quality)

    destaques = _destaques(g, ci, decisao, novelty, vencedora)
    curva_cashback = _curva_cashback(g, ci)
    decisao["destaques"] = destaques

    # monta saída
    def row(grp):
        r = g.loc[grp]
        return {k: (None if (isinstance(v, float) and np.isnan(v)) else
                    (round(float(v), 2) if isinstance(v, (int, float, np.floating)) else v))
                for k, v in r.to_dict().items()}

    return {
        "parceiros": parceiros,
        "periodo": {
            "inicio": df["data_parsed"].min().strftime("%Y-%m-%d"),
            "fim": df["data_parsed"].max().strftime("%Y-%m-%d"),
            "dias": int(df["data_parsed"].nunique()),
        },
        "premissas": [
            "Sem coluna de usuários expostos por variante: taxa de conversão não é calculável. "
            "Assume-se alocação de tráfego equilibrada; a inferência usa o dia como unidade amostral.",
            "Métrica de decisão = lucro (comissão − cashback).",
            "Sem grupo de controle; variantes comparadas entre si.",
        ],
        "por_variante": {grp: row(grp) for grp in grupos},
        "ic_lucro_por_comprador_diario": {
            grp: {"media": ci[grp][0], "ic95_baixo": ci[grp][1], "ic95_alto": ci[grp][2]} for grp in grupos
        },
        "comparacao_vencedora_vs_segunda": comparacao,
        "novelty": novelty,
        "destaques": destaques,
        "curva_cashback": curva_cashback,
        "series": series,
        "semanal": semanal,
        "decisao": decisao,
    }


def _fmt_brl(v):
    return f"R$ {v:,.0f}".replace(",", ".")


def _brl2(v):
    """Real brasileiro com 2 casas: R$ 1.234,56"""
    s = f"{v:,.2f}"  # formato US: 1,234.56
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _pctv(v):
    return f"{v:.1f}%".replace(".", ",")


def _join_e(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " e " + items[-1]


def _justificativa_detalhada(g, ci, vencedora, segunda, veredito, decaiu):
    """
    Frase de recomendação completa e number-driven (estilo 'Opção 2'), sempre
    coerente com os dados: compara a variante recomendada com as demais em lucro
    total, margem e lucro por comprador. Se a recomendada não liderar todas as
    métricas de rentabilidade, o texto se ajusta para não afirmar algo falso.
    """
    if segunda is None:
        return f"Há apenas uma variante válida ({vencedora}); não existe comparação a fazer."

    ranking_all = sorted(g.index, key=lambda gr: (ci[gr][0] if not np.isnan(ci[gr][0]) else -1e18), reverse=True)
    outros = [gr for gr in ranking_all if gr != vencedora]

    lpc_v = ci[vencedora][0]
    lucro_v = float(g.loc[vencedora, "lucro"])
    margem_v = float(g.loc[vencedora, "margem_pct"])

    lucro_outros = _join_e([_fmt_brl(float(g.loc[o, "lucro"])) for o in outros])
    margem_outros = _join_e([_pctv(float(g.loc[o, "margem_pct"])) for o in outros])
    lpc_outros = _join_e([_brl2(ci[o][0]) for o in outros])
    lista_outros = _join_e([f"o {o}" for o in outros])

    leads_lucro = (g["lucro"].idxmax() == vencedora)
    leads_margem = (g["margem_pct"].idxmax() == vencedora)

    if "INCONCLUSIVO" in veredito:
        return (f"O {vencedora} apresentou o maior lucro por comprador ({_brl2(lpc_v)}, ante {lpc_outros}), "
                f"mas a diferença para o {segunda} não se manteve consistente ao longo dos dias — "
                f"pode ser apenas variação do período. Recomenda-se estender o teste antes de decidir.")

    if leads_lucro and leads_margem:
        base = (f"Recomenda-se o {vencedora}, que superou {lista_outros} em todas as métricas de "
                f"rentabilidade: lucro total ({_fmt_brl(lucro_v)}, contra {lucro_outros}), "
                f"margem ({_pctv(margem_v)}, ante {margem_outros}) e lucro por comprador "
                f"({_brl2(lpc_v)}, ante {lpc_outros}).")
    else:
        base = (f"Recomenda-se o {vencedora} pelo maior lucro por comprador ({_brl2(lpc_v)}, "
                f"ante {lpc_outros} das demais variantes). No período, registrou lucro total de "
                f"{_fmt_brl(lucro_v)} e margem de {_pctv(margem_v)}; nas demais variantes o lucro foi "
                f"{lucro_outros} e a margem {margem_outros}.")

    if "CAUTELA" in veredito or decaiu:
        base += (" Ainda assim, a vantagem diminui da primeira para a segunda metade do período, "
                 "o que sugere um efeito de novidade; recomenda-se acompanhar após a adoção.")
    return base


def _dose_resposta(g, ci):
    """
    Descreve a relação entre a 'dose' do incentivo (taxa de cashback = % do GMV
    devolvido) e a 'resposta' do negócio (GMV e lucro por comprador). O texto se
    adapta ao padrão que os dados realmente mostram — não assume trade-off.
    """
    grupos = list(g.index)
    if len(grupos) < 2:
        return None
    taxa = {gr: float(g.loc[gr, "cashback_pct_gmv"]) for gr in grupos}
    ordem = sorted(grupos, key=lambda gr: taxa[gr])
    gmv = [float(g.loc[gr, "gmv"]) for gr in ordem]
    lpc = [ci[gr][0] for gr in ordem]
    menor, maior = ordem[0], ordem[-1]

    lpc_cai = all(lpc[i] >= lpc[i + 1] for i in range(len(lpc) - 1))
    gmv_sobe = all(gmv[i] <= gmv[i + 1] for i in range(len(gmv) - 1))
    gmv_cai = all(gmv[i] >= gmv[i + 1] for i in range(len(gmv) - 1))

    base = (f"A taxa de cashback é a 'dose' do incentivo (percentual do GMV devolvido ao usuário); "
            f"o GMV e o lucro por comprador são a 'resposta'. Do {menor} ao {maior}, a dose vai de "
            f"{_pctv(taxa[menor])} a {_pctv(taxa[maior])}. ")

    if lpc_cai and gmv_sobe:
        return base + (f"A resposta é o padrão clássico de trade-off: o GMV sobe "
                       f"({_fmt_brl(gmv[0])} → {_fmt_brl(gmv[-1])}), mas o lucro por comprador cai "
                       f"({_brl2(lpc[0])} → {_brl2(lpc[-1])}) — mais cashback compra volume à custa de margem.")
    if lpc_cai and gmv_cai:
        return base + (f"Aqui o incentivo maior piorou os dois lados: o lucro por comprador cai "
                       f"({_brl2(lpc[0])} → {_brl2(lpc[-1])}) e o GMV também recua "
                       f"({_fmt_brl(gmv[0])} → {_fmt_brl(gmv[-1])}) — o cashback adicional não se converteu em volume.")
    if lpc_cai:
        return base + (f"O lucro por comprador cai com a dose ({_brl2(lpc[0])} → {_brl2(lpc[-1])}), "
                       f"enquanto o GMV não responde de forma consistente.")
    return None


def _achados(g, ci, trade_off):
    """Lista objetiva de achados e exceções, gerada a partir dos dados (não fixa por parceiro)."""
    achados = []
    # exceção: variante que devolveu quase toda a comissão em cashback (lucro nulo/negativo)
    for grp in g.index:
        lucro = float(g.loc[grp, "lucro"]); comissao = float(g.loc[grp, "comissao"])
        if comissao > 0 and lucro <= 0.02 * comissao:
            pct_dev = 100 * float(g.loc[grp, "cashback"]) / comissao
            achados.append(
                f"Exceção — {grp}: devolveu {pct_dev:.0f}% da comissão em cashback e zerou o lucro "
                f"(lucro de {_fmt_brl(lucro)} sobre comissão de {_fmt_brl(comissao)}). Variante insustentável, não deve ser escalada.")
    # trade-off (quando existe)
    if trade_off and trade_off.get("existe"):
        achados.append("Trade-off — " + trade_off["texto"])
    # relação dose-resposta
    dr = _dose_resposta(g, ci)
    if dr:
        achados.append("Dose-resposta — " + dr)
    return achados


def _roi_fmt(v):
    return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.2f}".replace(".", ",")


def _curva_cashback(g, ci):
    """
    Curva de resposta ao cashback: variantes ordenadas pela intensidade de cashback
    (% do GMV devolvido) com o respectivo lucro por comprador. Evidencia como a
    rentabilidade unitária responde ao nível de incentivo.
    """
    pontos = []
    for grp in g.index:
        pontos.append({
            "grupo": grp,
            "cashback_pct_gmv": round(float(g.loc[grp, "cashback_pct_gmv"]), 2),
            "cashback_por_comprador": round(float(g.loc[grp, "cashback_por_comprador"]), 2),
            "lucro_por_comprador": round(float(ci[grp][0]), 2),
        })
    return sorted(pontos, key=lambda p: p["cashback_pct_gmv"])


def _destaques(g, ci, decisao, novelty, vencedora):
    """
    Achados analíticos detectados automaticamente, em frases curtas e formais.
    O objetivo é levar exceções e leituras críticas à superfície, em vez de deixá-las
    implícitas nos números.
    """
    out = []

    # 1. variante sem lucro / no ponto de equilíbrio
    for grp in g.index:
        lucro = float(g.loc[grp, "lucro"])
        comissao = float(g.loc[grp, "comissao"])
        cashback = float(g.loc[grp, "cashback"])
        repasse = (cashback / comissao) if comissao > 0 else 0.0
        if lucro <= 0 or repasse >= 0.98:
            out.append(
                f"{grp} não gera lucro: devolve em cashback {_pctv(100 * repasse)} da comissão, "
                f"com lucro de {_fmt_brl(lucro)} e ROI {_roi_fmt(g.loc[grp, 'roi'])}."
            )

    # 2. variantes com ROI abaixo de 1 (cashback investido supera o lucro gerado)
    roi_baixo = [grp for grp in g.index
                 if g.loc[grp, "roi"] is not None and not np.isnan(g.loc[grp, "roi"])
                 and 0 < g.loc[grp, "roi"] < 1]
    if roi_baixo:
        det = _join_e([f"{grp} (ROI {_roi_fmt(g.loc[grp, 'roi'])})" for grp in roi_baixo])
        out.append(f"ROI abaixo de 1 em {det}: nessas variantes o cashback investido supera o lucro gerado.")

    # 3. resposta monotônica ao cashback
    curva = _curva_cashback(g, ci)
    if len(curva) >= 2:
        lpcs = [p["lucro_por_comprador"] for p in curva]
        if all(lpcs[i] > lpcs[i + 1] for i in range(len(lpcs) - 1)):
            out.append("O lucro por comprador cai de forma consistente à medida que o cashback aumenta; "
                       "níveis mais altos de cashback não se pagaram em rentabilidade.")

    # 4. trade-off crescimento × margem
    t = decisao.get("trade_off")
    if t and t.get("existe"):
        out.append(f"A variante mais lucrativa ({t['variante_mais_lucrativa']}) não é a de maior GMV "
                   f"({t['variante_maior_gmv']}): há trade-off entre margem e crescimento (ver seção específica).")

    # 5. efeito de novidade na variante recomendada
    nv = novelty.get(vencedora, {})
    if nv.get("decaimento_relevante"):
        out.append("A vantagem da variante recomendada diminui na segunda metade do período, "
                   "sugerindo efeito de novidade; recomenda-se monitorar após a adoção.")

    return out


def _montar_decisao(g, ci, vencedora, segunda, comparacao,
                    lider_lucro_abs, lider_gmv, novelty, quality):
    alertas_qualidade = [a for a in quality.get("alertas", []) if "fantasma" in a or "diferente" in a]
    decaiu = novelty.get(vencedora, {}).get("decaimento_relevante", False)

    # estados possíveis: ESCALAR / INCONCLUSIVO
    significativo = bool(comparacao and comparacao["significativo"]) if segunda is not None else True

    if segunda is None:
        veredito = "ESCALAR"
        confianca = "N/A (variante única)"
        just = f"Há apenas uma variante válida ({vencedora}); não existe comparação a fazer."
    elif significativo and not decaiu:
        veredito = "ESCALAR"
        confianca = "alta"
        just = (f"Os dados indicam {vencedora} como o de maior lucro por comprador, com diferença para "
                f"{segunda} que se mantém consistente ao longo dos dias analisados.")
    elif significativo and decaiu:
        veredito = "ESCALAR COM CAUTELA"
        confianca = "média"
        just = (f"Os dados indicam {vencedora} como o de maior lucro por comprador, com diferença para "
                f"{segunda} consistente ao longo dos dias. Ainda assim, a vantagem diminui da primeira para "
                f"a segunda metade do período, o que sugere um efeito de novidade; vale acompanhar após a adoção.")
    else:
        veredito = "INCONCLUSIVO"
        confianca = "baixa"
        just = (f"Os dados apontam {vencedora} com a melhor média de lucro por comprador, mas a diferença para "
                f"{segunda} não se mantém consistente ao longo dos dias — pode ser apenas variação do período. "
                f"Recomenda-se estender o teste antes de decidir.")

    # trade-off explícito: a mais lucrativa não é a de maior GMV?
    trade_off = None
    if lider_lucro_abs != lider_gmv:
        lucro_venc = float(g.loc[lider_lucro_abs, "lucro"])
        lucro_gmv = float(g.loc[lider_gmv, "lucro"])
        gmv_venc = float(g.loc[lider_lucro_abs, "gmv"])
        gmv_lider = float(g.loc[lider_gmv, "gmv"])
        gmv_abdicado = gmv_lider - gmv_venc
        lucro_ganho = lucro_venc - lucro_gmv
        razao = (gmv_abdicado / lucro_ganho) if lucro_ganho > 0 else None
        trade_off = {
            "existe": True,
            "variante_mais_lucrativa": lider_lucro_abs,
            "variante_maior_gmv": lider_gmv,
            "lucro_da_mais_lucrativa": round(lucro_venc, 2),
            "lucro_da_maior_gmv": round(lucro_gmv, 2),
            "gmv_da_mais_lucrativa": round(gmv_venc, 2),
            "gmv_da_maior_gmv": round(gmv_lider, 2),
            "gmv_abdicado": round(gmv_abdicado, 2),
            "lucro_a_mais": round(lucro_ganho, 2),
            "gmv_abdicado_por_real_de_lucro": round(razao, 2) if razao else None,
            "texto": (
                f"Escalar {lider_lucro_abs} (mais lucrativa) em vez de {lider_gmv} (maior GMV) "
                f"troca {_fmt_brl(gmv_abdicado)} de GMV por {_fmt_brl(lucro_ganho)} de lucro extra"
                + (f" — abre-se mão de R$ {razao:.2f} de GMV para cada R$ 1,00 de lucro ganho.".replace(f"{razao:.2f}", f"{razao:.2f}".replace(".", ",")) if razao else ".")
            ),
        }

    just_detalhada = _justificativa_detalhada(g, ci, vencedora, segunda, veredito, decaiu)
    achados = _achados(g, ci, trade_off)

    return {
        "pergunta": "Qual variante de cashback escalar para 100% do tráfego?",
        "recomendacao": vencedora,
        "veredito": veredito,
        "confianca_estatistica": confianca,
        "justificativa": just,
        "justificativa_detalhada": just_detalhada,
        "trade_off": trade_off,
        "achados": achados,
        "ressalvas_qualidade": alertas_qualidade,
    }


def run(path: str) -> dict:
    res = clean(path)
    if res.df.empty:
        return {"erro": res.quality.get("erro_fatal", "sem linhas válidas após saneamento"),
                "qualidade": res.quality}
    out = analyze(res.df, res.quality)
    out["qualidade"] = res.quality
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("uso: python analyze.py <arquivo.csv>"); sys.exit(1)
    print(json.dumps(run(sys.argv[1]), ensure_ascii=False, indent=2, default=str))
