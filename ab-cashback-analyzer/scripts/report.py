"""
report.py — Gera os entregáveis visuais a partir da saída de analyze.run():
  1) Dashboard HTML interativo, autocontido (Chart.js via CDN), cores Méliuz.
  2) PDF derivado compacto (1–2 páginas) via matplotlib + reportlab.

Identidade visual (paleta Méliuz):
  grafite  #302c2c   vermelho #e81c3c   rosa #fe9dbf   rosa claro #ffe8f3   branco #ffffff

Uso via CLI:
  python report.py <arquivo.csv> <dir_saida> ["Nome do teste"]
"""

import sys, os, json, html
import numpy as np

try:
    from analyze import run as analyze_run
except ImportError:
    from scripts.analyze import run as analyze_run

# paleta
GRAFITE, VERMELHO, ROSA, ROSA_CLARO, BRANCO = "#302c2c", "#e81c3c", "#fe9dbf", "#ffe8f3", "#ffffff"
SERIE_CORES = [VERMELHO, GRAFITE, ROSA, "#8a6d3b", "#5b9279"]  # até 5 variantes


def _brl(v):
    try:
        return "R$ " + f"{float(v):,.0f}".replace(",", ".")
    except Exception:
        return "—"


def _pct(v):
    return "—" if v is None else f"{float(v):.1f}%"


def _num(v):
    return "—" if v is None else f"{float(v):,.0f}".replace(",", ".")


# =====================================================================
# DASHBOARD HTML
# =====================================================================
def build_html(a: dict, nome_teste: str) -> str:
    q = a["qualidade"]
    d = a["decisao"]
    grupos = list(a["por_variante"].keys())
    cor = {g: SERIE_CORES[i % len(SERIE_CORES)] for i, g in enumerate(grupos)}

    parceiros = ", ".join(a["parceiros"])
    per = a["periodo"]

    # ---- KPI cards por variante ----
    cards = ""
    for g in grupos:
        v = a["por_variante"][g]
        vencedora = (g == d["recomendacao"])
        badge = f'<span class="badge">recomendada</span>' if vencedora else ""
        cards += f"""
        <div class="vcard {'win' if vencedora else ''}" style="--accent:{cor[g]}">
          <div class="vhead"><span class="vdot"></span><h3>{html.escape(g)}</h3>{badge}</div>
          <div class="kpis">
            <div><span>{_num(v['compradores'])}</span><label>compradores</label></div>
            <div><span>{_brl(v['gmv'])}</span><label>GMV</label></div>
            <div><span>{_brl(v['lucro'])}</span><label>lucro</label></div>
            <div><span>{_pct(v['margem_pct'])}</span><label>margem</label></div>
            <div><span>{('—' if v['roi'] is None else f"{v['roi']:.2f}")}</span><label>ROI</label></div>
            <div><span>{_pct(v['cashback_pct_gmv'])}</span><label>taxa de cashback</label></div>
            <div><span>{_brl(v['ticket_medio'])}</span><label>ticket médio</label></div>
          </div>
        </div>"""

    # ---- trade-off callout ----
    trade_html = ""
    tradeoff_js = "const TO = null;"
    if d.get("trade_off") and d["trade_off"].get("existe"):
        t = d["trade_off"]
        cambio = t.get("gmv_abdicado_por_real_de_lucro")
        cambio_txt = (f"R$ {cambio:.2f}".replace(".", ",") if cambio else "—")
        tradeoff_js = ("const TO = " + json.dumps({
            "gmv_abdicado": t["gmv_abdicado"], "lucro_a_mais": t["lucro_a_mais"],
            "cambio": cambio, "mais_lucrativa": t["variante_mais_lucrativa"],
            "maior_gmv": t["variante_maior_gmv"],
        }, ensure_ascii=False) + ";")
        trade_html = f"""
        <section class="panel tradeoff">
          <h2><span class="tag">trade-off</span> Crescimento vs. margem</h2>
          <p>{html.escape(t['texto'])}</p>
          <div class="tradeoff-body">
            <div class="cambio">
              <label>Câmbio da decisão</label>
              <div class="cambio-val">{cambio_txt}</div>
              <small>de GMV abdicado para cada <b>R$ 1,00</b> de lucro a mais<br>
              ao escalar {html.escape(t['variante_mais_lucrativa'])} em vez de {html.escape(t['variante_maior_gmv'])}</small>
            </div>
            <div class="chartbox to-chart"><canvas id="cTradeoff"></canvas></div>
          </div>
          <div class="tgrid">
            <div><label>{html.escape(t['variante_mais_lucrativa'])} — mais lucrativa (recomendada)</label>
                 <b>{_brl(t['lucro_da_mais_lucrativa'])}</b><small>lucro · GMV {_brl(t['gmv_da_mais_lucrativa'])}</small></div>
            <div><label>{html.escape(t['variante_maior_gmv'])} — maior GMV</label>
                 <b>{_brl(t['lucro_da_maior_gmv'])}</b><small>lucro · GMV {_brl(t['gmv_da_maior_gmv'])}</small></div>
          </div>
          <div class="caption">O gráfico mostra a <b>troca</b>: escalar a variante mais lucrativa abre mão de uma
          fatia grande de GMV (barra clara) para ganhar uma fatia menor de lucro (barra vermelha). O câmbio é a razão entre as duas.</div>
        </section>"""
    else:
        # sem trade-off: a variante recomendada também lidera o GMV — vale afirmar isso com clareza
        trade_html = f"""
        <section class="panel tradeoff no-to">
          <h2><span class="tag">trade-off</span> Sem conflito neste teste</h2>
          <p>A variante recomendada (<b>{html.escape(d['recomendacao'])}</b>) é ao mesmo tempo a de maior lucro
          e a de maior GMV. Não há tensão entre crescimento e margem a resolver: escalar por lucro também maximiza o GMV.</p>
        </section>"""

    # ---- destaques e exceções ----
    achados = d.get("destaques", [])
    achados_html = ""
    if achados:
        itens = "".join(f"<li>{html.escape(x)}</li>" for x in achados)
        achados_html = f"""
        <section class="panel achados">
          <h2><span class="tag">análise</span> Destaques e exceções</h2>
          <ul class="achados-list">{itens}</ul>
        </section>"""

    # ---- ressalvas de qualidade ----
    def li(items): return "".join(f"<li>{html.escape(str(x))}</li>" for x in items)
    descartes = li([f"{x['motivo']}: {x['quantidade']}" for x in q.get("descartes", [])]) or "<li>nenhum</li>"
    quarentena = li([f"{x['motivo']}: {x['quantidade']}" for x in q.get("quarentena", [])]) or "<li>nenhuma</li>"
    alertas = li(q.get("alertas", [])) or "<li>nenhum</li>"

    ic = a["ic_lucro_por_comprador_diario"]
    comp = a["comparacao_vencedora_vs_segunda"]
    stat_line = ""
    if comp:
        def _f2(x): return f"{x:.2f}".replace(".", ",")
        sig = "diferença consistente ao longo do teste" if comp["significativo"] else "diferença que não se mantém consistente (pode ser variação do período)"
        stat_line = (f"A variante recomendada supera a 2ª colocada em "
                     f"R$ {_f2(comp['diferenca_media'])} de lucro por comprador a cada dia, em média "
                     f"(faixa provável: R$ {_f2(comp['ic95_baixo'])} a R$ {_f2(comp['ic95_alto'])}) — {sig}.")

    data_js = json.dumps({
        "grupos": grupos,
        "cor": cor,
        "series": a["series"],
        "por_variante": a["por_variante"],
        "ic": ic,
        "curva": a.get("curva_cashback", []),
    }, ensure_ascii=False)

    veredito_classe = {"ESCALAR": "go", "ESCALAR COM CAUTELA": "warn",
                       "ESCALAR COM CAUTELA".upper(): "warn"}.get(d["veredito"], "warn")
    if d["veredito"].startswith("ESCALAR") and "CAUTELA" not in d["veredito"]:
        veredito_classe = "go"
    elif "INCONCLUSIVO" in d["veredito"]:
        veredito_classe = "stop"

    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(nome_teste)} — Análise A/B Méliuz</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root{{--grafite:{GRAFITE};--vermelho:{VERMELHO};--rosa:{ROSA};--rosaclaro:{ROSA_CLARO};--branco:{BRANCO}}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--branco);color:var(--grafite);font-family:Inter,system-ui,sans-serif;line-height:1.5}}
  .wrap{{max-width:1120px;margin:0 auto;padding:32px 24px 64px}}
  h1,h2,h3{{font-family:Sora,sans-serif;margin:0}}
  .eyebrow{{font-family:Sora;font-weight:600;letter-spacing:.14em;text-transform:uppercase;font-size:12px;color:var(--vermelho)}}
  header.top{{border-bottom:2px solid var(--rosaclaro);padding-bottom:20px;margin-bottom:28px}}
  header.top h1{{font-size:30px;font-weight:800;margin:6px 0 4px}}
  header.top .meta{{color:#6b6666;font-size:14px}}
  /* HERO veredito */
  .hero{{background:var(--grafite);color:var(--branco);border-radius:20px;padding:30px 32px;margin-bottom:28px;
         display:grid;grid-template-columns:1fr auto;gap:24px;align-items:center}}
  .hero .q{{font-family:Sora;font-weight:600;color:var(--rosa);font-size:15px;margin-bottom:10px}}
  .hero .answer{{font-family:Sora;font-weight:800;font-size:40px;line-height:1.05}}
  .hero .just{{color:#d9d4d4;font-size:14px;max-width:60ch;margin-top:10px}}
  .verdict{{text-align:center;padding:16px 22px;border-radius:14px;font-family:Sora;font-weight:800;font-size:15px;white-space:nowrap}}
  .verdict small{{display:block;font-weight:600;font-size:11px;opacity:.85;margin-top:4px}}
  .verdict.go{{background:var(--vermelho);color:#fff}}
  .verdict.warn{{background:var(--rosa);color:var(--grafite)}}
  .verdict.stop{{background:#fff;color:var(--grafite);border:2px solid var(--rosa)}}
  /* cards */
  .vgrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin-bottom:28px}}
  .vcard{{border:1.5px solid var(--rosaclaro);border-radius:16px;padding:18px 18px 8px;background:#fff;position:relative}}
  .vcard.win{{border-color:var(--accent);box-shadow:0 6px 22px rgba(232,28,60,.10)}}
  .vhead{{display:flex;align-items:center;gap:8px;margin-bottom:12px}}
  .vhead h3{{font-size:18px;font-weight:700}}
  .vdot{{width:11px;height:11px;border-radius:50%;background:var(--accent)}}
  .badge{{margin-left:auto;background:var(--accent);color:#fff;font-family:Sora;font-weight:700;font-size:10px;
          letter-spacing:.06em;text-transform:uppercase;padding:4px 8px;border-radius:20px}}
  .kpis{{display:grid;grid-template-columns:1fr 1fr;gap:10px 14px}}
  .kpis>div{{padding-bottom:8px}}
  .kpis span{{font-family:Sora;font-weight:700;font-size:19px;display:block}}
  .kpis label{{font-size:11px;color:#8a8585;text-transform:uppercase;letter-spacing:.04em}}
  /* panels */
  .panel{{background:#fff;border:1.5px solid var(--rosaclaro);border-radius:16px;padding:22px 24px;margin-bottom:22px}}
  .panel h2{{font-size:17px;font-weight:700;margin-bottom:14px;display:flex;align-items:center;gap:10px}}
  .tag{{background:var(--rosaclaro);color:var(--vermelho);font-family:Sora;font-weight:700;font-size:11px;
        letter-spacing:.05em;text-transform:uppercase;padding:4px 9px;border-radius:6px}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:22px}}
  @media(max-width:820px){{.grid2{{grid-template-columns:1fr}}.hero{{grid-template-columns:1fr}}}}
  .chartbox{{position:relative;height:280px}}
  .caption{{font-size:12.5px;color:#8a8585;margin-top:8px}}
  .tradeoff{{border-color:var(--rosa);background:linear-gradient(0deg,var(--rosaclaro),#fff)}}
  .tradeoff.no-to{{background:#fff}}
  .achados-list{{margin:0;padding-left:0;list-style:none}}
  .achados-list li{{position:relative;padding:12px 14px 12px 16px;margin-bottom:10px;background:var(--rosaclaro);
    border-left:3px solid var(--vermelho);border-radius:8px;font-size:13.5px;color:#4a4646;line-height:1.5}}
  .achados-list li:last-child{{margin-bottom:0}}
  .tradeoff-body{{display:grid;grid-template-columns:260px 1fr;gap:22px;align-items:center;margin:16px 0 6px}}
  @media(max-width:820px){{.tradeoff-body{{grid-template-columns:1fr}}}}
  .cambio{{background:var(--grafite);color:#fff;border-radius:16px;padding:20px 22px;text-align:center}}
  .cambio label{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--rosa);font-family:Sora;font-weight:600}}
  .cambio-val{{font-family:Sora;font-weight:800;font-size:44px;line-height:1.05;margin:6px 0 8px;color:#fff}}
  .cambio small{{font-size:12px;color:#d9d4d4;line-height:1.45}}
  .to-chart{{height:210px}}
  .tgrid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:14px}}
  .tgrid>div{{background:#fff;border:1px solid var(--rosaclaro);border-radius:12px;padding:14px}}
  .tgrid label{{font-size:12px;color:#8a8585;display:block;margin-bottom:4px}}
  .tgrid b{{font-family:Sora;font-size:22px}}.tgrid small{{display:block;color:#8a8585;margin-top:2px}}
  .stat{{font-size:13.5px;color:#4a4646;background:var(--rosaclaro);border-radius:10px;padding:12px 14px;margin-top:12px}}
  .quality{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}
  @media(max-width:820px){{.quality{{grid-template-columns:1fr}}}}
  .quality h4{{font-family:Sora;font-size:13px;margin:0 0 6px;color:var(--grafite)}}
  .quality ul{{margin:0;padding-left:18px;font-size:12.5px;color:#6b6666}}
  .qbar{{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:14px}}
  .qbar div{{font-family:Sora}}.qbar b{{font-size:22px;color:var(--vermelho)}}
  .qbar small{{display:block;font-family:Inter;font-size:11px;color:#8a8585;text-transform:uppercase;letter-spacing:.04em}}
  footer{{margin-top:36px;font-size:12px;color:#a9a4a4;text-align:center}}
</style></head><body><div class="wrap">

<header class="top">
  <div class="eyebrow">Méliuz · Growth · Análise de teste A/B de cashback</div>
  <h1>{html.escape(nome_teste)}</h1>
  <div class="meta">Parceiro(s): <b>{html.escape(parceiros)}</b> &nbsp;·&nbsp; Período: {per['inicio']} a {per['fim']} ({per['dias']} dias) &nbsp;·&nbsp; {len(grupos)} variantes</div>
</header>

<div class="hero">
  <div>
    <div class="q">{html.escape(d['pergunta'])}</div>
    <div class="answer">{html.escape(d['recomendacao'])}</div>
    <div class="just">{html.escape(d['justificativa'])}</div>
  </div>
  <div class="verdict {veredito_classe}">{html.escape(d['veredito'])}<small>confiança {html.escape(str(d['confianca_estatistica']))}</small></div>
</div>

<div class="vgrid">{cards}</div>

{trade_html}

{achados_html}

<div class="grid2">
  <section class="panel"><h2><span class="tag">evolução</span> Lucro acumulado por variante</h2>
    <div class="chartbox"><canvas id="cAcum"></canvas></div>
    <div class="caption">Lucro acumulado por variante, obtido pela soma dos resultados diários.</div>
  </section>
  <section class="panel"><h2><span class="tag">decisão</span> Lucro por comprador (média diária ± IC95%)</h2>
    <div class="chartbox"><canvas id="cLpc"></canvas></div>
    <div class="caption">Média diária do lucro por comprador em cada variante; a barra indica a faixa provável de variação.</div>
  </section>
  <section class="panel"><h2><span class="tag">trade-off</span> GMV × Lucro por variante</h2>
    <div class="chartbox"><canvas id="cGmvLucro"></canvas></div>
    <div class="caption">Valores totais de GMV e de lucro para cada variante.</div>
  </section>
  <section class="panel"><h2><span class="tag">composição</span> Comissão, cashback e lucro</h2>
    <div class="chartbox"><canvas id="cComp"></canvas></div>
    <div class="caption">Comissão de cada variante repartida em cashback devolvido e lucro retido.</div>
  </section>
</div>

<section class="panel"><h2><span class="tag">resposta ao cashback</span> Nível de cashback × lucro por comprador</h2>
  <div class="chartbox" style="height:280px"><canvas id="cCurva"></canvas></div>
  <div class="caption">Variantes ordenadas pela intensidade de cashback (% do GMV devolvido). As barras mostram o cashback; a linha, o lucro por comprador. Evidencia como a rentabilidade unitária responde ao nível de incentivo.</div>
</section>

<section class="panel"><h2><span class="tag">série</span> Compradores por dia</h2>
  <div class="chartbox" style="height:240px"><canvas id="cComp2"></canvas></div>
  <div class="caption">Volume diário de compradores por variante ao longo do teste.</div>
  <div class="stat">{html.escape(stat_line)}</div>
</section>

<section class="panel"><h2><span class="tag">qualidade dos dados</span> Em que os números se apoiam</h2>
  <div class="qbar">
    <div><b>{q.get('linhas_lidas',0)}</b><small>linhas lidas</small></div>
    <div><b>{q.get('linhas_validas',0)}</b><small>linhas válidas</small></div>
    <div><b>{q.get('taxa_aproveitamento_pct',0)}%</b><small>aproveitamento</small></div>
    <div><b>{html.escape(str(q.get('encoding_detectado','—')))}</b><small>encoding</small></div>
  </div>
  <div class="quality">
    <div><h4>Linhas descartadas</h4><ul>{descartes}</ul></div>
    <div><h4>Em quarentena (isoladas)</h4><ul>{quarentena}</ul></div>
    <div><h4>Observações</h4><ul>{alertas}</ul></div>
  </div>
</section>

<footer>Gerado automaticamente pela skill <b>ab-cashback-analyzer</b> · premissa: alocação de tráfego equilibrada entre variantes (não há coluna de usuários expostos).</footer>
</div>
<script>
const D = {data_js};
{tradeoff_js}
const F = new Intl.NumberFormat('pt-BR');
const BRL = v => 'R$ ' + F.format(Math.round(v));
const BRL2 = v => 'R$ ' + v.toLocaleString('pt-BR', {{minimumFractionDigits:2, maximumFractionDigits:2}});
Chart.defaults.font.family = 'Inter, sans-serif';
Chart.defaults.color = '#6b6666';
const grid = {{color:'#f0e6ea'}};

// lucro acumulado
new Chart(cAcum, {{type:'line', data:{{
  labels: D.series[D.grupos[0]].data,
  datasets: D.grupos.map(g=>({{label:g, data:D.series[g].lucro_acumulado, borderColor:D.cor[g],
    backgroundColor:D.cor[g], tension:.25, pointRadius:0, borderWidth:2.5}}))
}}, options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},
  plugins:{{legend:{{position:'bottom'}},tooltip:{{callbacks:{{label:c=>c.dataset.label+': '+BRL(c.parsed.y)}}}}}},
  scales:{{y:{{grid,ticks:{{callback:v=>BRL(v)}}}},x:{{grid:{{display:false}},ticks:{{maxTicksLimit:8}}}}}}}}}});

// lucro por comprador com IC (barras + erro desenhado)
const lpcMean = D.grupos.map(g=>D.ic[g].media);
const lpcLo = D.grupos.map(g=>D.ic[g].ic95_baixo);
const lpcHi = D.grupos.map(g=>D.ic[g].ic95_alto);
const errorBars = {{id:'err', afterDatasetsDraw(c){{const {{ctx,scales:{{y}}}}=c;const meta=c.getDatasetMeta(0);
  ctx.save();ctx.strokeStyle='#302c2c';ctx.lineWidth=1.5;
  meta.data.forEach((bar,i)=>{{const x=bar.x;const yl=y.getPixelForValue(lpcLo[i]);const yh=y.getPixelForValue(lpcHi[i]);
    ctx.beginPath();ctx.moveTo(x,yh);ctx.lineTo(x,yl);ctx.moveTo(x-5,yh);ctx.lineTo(x+5,yh);
    ctx.moveTo(x-5,yl);ctx.lineTo(x+5,yl);ctx.stroke();}});ctx.restore();}}}};
new Chart(cLpc, {{type:'bar', data:{{labels:D.grupos,
  datasets:[{{label:'Lucro por comprador (R$/dia)', data:lpcMean,
    backgroundColor:D.grupos.map(g=>D.cor[g])}}]}},
  options:{{responsive:true,maintainAspectRatio:false,
  plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>BRL2(c.parsed.y)+
    ' [faixa provável: '+BRL2(lpcLo[c.dataIndex])+' a '+BRL2(lpcHi[c.dataIndex])+']'}}}}}},
  scales:{{y:{{grid,ticks:{{callback:v=>'R$ '+v}}}},x:{{grid:{{display:false}}}}}}}}, plugins:[errorBars]}});

// GMV x Lucro
new Chart(cGmvLucro, {{type:'bar', data:{{labels:D.grupos, datasets:[
  {{label:'GMV', data:D.grupos.map(g=>D.por_variante[g].gmv), backgroundColor:'{ROSA}'}},
  {{label:'Lucro', data:D.grupos.map(g=>D.por_variante[g].lucro), backgroundColor:'{VERMELHO}'}}]}},
  options:{{responsive:true,maintainAspectRatio:false,
  plugins:{{legend:{{position:'bottom'}},tooltip:{{callbacks:{{label:c=>c.dataset.label+': '+BRL(c.parsed.y)}}}}}},
  scales:{{y:{{grid,ticks:{{callback:v=>BRL(v)}}}},x:{{grid:{{display:false}}}}}}}}}});

// composição comissão/cashback/lucro (empilhado)
new Chart(cComp, {{type:'bar', data:{{labels:D.grupos, datasets:[
  {{label:'Cashback', data:D.grupos.map(g=>D.por_variante[g].cashback), backgroundColor:'{ROSA}'}},
  {{label:'Lucro', data:D.grupos.map(g=>D.por_variante[g].lucro), backgroundColor:'{VERMELHO}'}}]}},
  options:{{responsive:true,maintainAspectRatio:false,
  plugins:{{legend:{{position:'bottom'}},tooltip:{{callbacks:{{label:c=>c.dataset.label+': '+BRL(c.parsed.y),
    footer:items=>{{const g=D.grupos[items[0].dataIndex];return 'Comissão total: '+BRL(D.por_variante[g].comissao)}}}}}}}},
  scales:{{x:{{stacked:true,grid:{{display:false}}}},y:{{stacked:true,grid,ticks:{{callback:v=>BRL(v)}}}}}}}}}});

// compradores por dia
new Chart(cComp2, {{type:'line', data:{{labels:D.series[D.grupos[0]].data,
  datasets:D.grupos.map(g=>({{label:g,data:D.series[g].compradores,borderColor:D.cor[g],
    backgroundColor:D.cor[g],tension:.25,pointRadius:0,borderWidth:2}}))}},
  options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},
  plugins:{{legend:{{position:'bottom'}}}},
  scales:{{y:{{grid}},x:{{grid:{{display:false}},ticks:{{maxTicksLimit:8}}}}}}}}}});

// gráfico dedicado do trade-off: a TROCA (GMV abdicado vs lucro ganho)
if (TO && document.getElementById('cTradeoff')) {{
  new Chart(cTradeoff, {{type:'bar', data:{{
    labels:['GMV abdicado','Lucro ganho'],
    datasets:[{{data:[TO.gmv_abdicado, TO.lucro_a_mais],
      backgroundColor:['{ROSA}','{VERMELHO}'], borderRadius:6, barPercentage:.6}}]}},
    options:{{indexAxis:'y', responsive:true, maintainAspectRatio:false,
    plugins:{{legend:{{display:false}}, title:{{display:true,align:'start',
      text:'O que você troca ao escalar '+TO.mais_lucrativa+' em vez de '+TO.maior_gmv,
      color:'#6b6666', font:{{size:11, weight:'normal'}}}},
      tooltip:{{callbacks:{{label:c=>BRL(c.parsed.x)}}}}}},
    scales:{{x:{{grid, ticks:{{callback:v=>BRL(v)}}}}, y:{{grid:{{display:false}}}}}}}}}});
}}
// curva de resposta ao cashback: barras = % cashback/GMV, linha = lucro por comprador
if (D.curva && D.curva.length) {{
  const labels = D.curva.map(p=>p.grupo);
  new Chart(cCurva, {{data:{{labels, datasets:[
    {{type:'bar', label:'Cashback (% do GMV)', data:D.curva.map(p=>p.cashback_pct_gmv),
      backgroundColor:'{ROSA}', yAxisID:'y1', borderRadius:6, order:2}},
    {{type:'line', label:'Lucro por comprador', data:D.curva.map(p=>p.lucro_por_comprador),
      borderColor:'{VERMELHO}', backgroundColor:'{VERMELHO}', yAxisID:'y', tension:.2,
      borderWidth:3, pointRadius:4, order:1}}
  ]}}, options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{position:'bottom'}},tooltip:{{callbacks:{{label:c=>c.dataset.yAxisID==='y'
      ? 'Lucro/comprador: '+BRL2(c.parsed.y) : 'Cashback: '+c.parsed.y.toFixed(1).replace('.',',')+'% do GMV'}}}}}},
    scales:{{
      y:{{position:'left',grid,title:{{display:true,text:'Lucro por comprador (R$)'}},ticks:{{callback:v=>'R$ '+v}}}},
      y1:{{position:'right',grid:{{drawOnChartArea:false}},title:{{display:true,text:'% cashback do GMV'}},ticks:{{callback:v=>v+'%'}}}},
      x:{{grid:{{display:false}}}}
    }}}}}});
}}
</script></body></html>"""


# =====================================================================
# PDF DERIVADO (compacto, 1–2 páginas)
# =====================================================================
def build_pdf(a: dict, nome_teste: str, out_pdf: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    import matplotlib.font_manager as fm

    d = a["decisao"]; q = a["qualidade"]; per = a["periodo"]
    grupos = list(a["por_variante"].keys())
    cor = {g: SERIE_CORES[i % len(SERIE_CORES)] for i, g in enumerate(grupos)}

    plt.rcParams.update({"font.size": 8, "axes.edgecolor": "#d8cfd3",
                         "axes.linewidth": .8, "text.color": GRAFITE,
                         "axes.labelcolor": GRAFITE, "xtick.color": "#6b6666",
                         "ytick.color": "#6b6666", "text.parse_math": False})

    fig = plt.figure(figsize=(8.27, 11.05))  # A4 retrato
    fig.patch.set_facecolor("white")
    gs = fig.add_gridspec(5, 2, height_ratios=[1.05, 0.9, 1.0, 1.0, 0.85],
                          hspace=0.55, wspace=0.25,
                          left=0.07, right=0.95, top=0.95, bottom=0.05)

    # --- faixa de título + veredito ---
    axh = fig.add_subplot(gs[0, :]); axh.axis("off")
    axh.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0.02,rounding_size=0.03",
                  transform=axh.transAxes, facecolor=GRAFITE, edgecolor="none"))
    axh.text(0.03, 0.74, "MÉLIUZ · GROWTH · ANÁLISE A/B DE CASHBACK", transform=axh.transAxes,
             color=ROSA, fontsize=8, fontweight="bold")
    axh.text(0.03, 0.46, nome_teste, transform=axh.transAxes, color="white", fontsize=15, fontweight="bold")
    axh.text(0.03, 0.18, f"{', '.join(a['parceiros'])}  ·  {per['inicio']} a {per['fim']}  ·  "
             f"{per['dias']} dias  ·  {len(grupos)} variantes", transform=axh.transAxes,
             color="#d9d4d4", fontsize=8)
    vcolor = VERMELHO if d["veredito"].startswith("ESCALAR") and "CAUTELA" not in d["veredito"] else ROSA
    if "INCONCLUSIVO" in d["veredito"]:
        vcolor = "#ffffff"
    axh.add_patch(FancyBboxPatch((0.68, 0.2), 0.29, 0.6, boxstyle="round,pad=0.01,rounding_size=0.04",
                  transform=axh.transAxes, facecolor=vcolor, edgecolor="none"))
    txtcolor = "white" if vcolor == VERMELHO else GRAFITE
    axh.text(0.825, 0.62, d["veredito"], transform=axh.transAxes, ha="center", color=txtcolor,
             fontsize=10.5, fontweight="bold")
    axh.text(0.825, 0.42, f"→ {d['recomendacao']}", transform=axh.transAxes, ha="center",
             color=txtcolor, fontsize=12, fontweight="bold")
    axh.text(0.825, 0.28, f"confiança {d['confianca_estatistica']}", transform=axh.transAxes,
             ha="center", color=txtcolor, fontsize=7)

    # --- justificativa + trade-off (texto) ---
    axj = fig.add_subplot(gs[1, :]); axj.axis("off")
    axj.text(0, 0.92, "Recomendação", fontweight="bold", fontsize=9.5, color=VERMELHO, transform=axj.transAxes)
    just = d.get("justificativa_detalhada", d["justificativa"])
    axj.text(0, 0.74, _wrap(just, 128), fontsize=7.5, va="top", transform=axj.transAxes)
    if d.get("trade_off") and d["trade_off"]["existe"]:
        axj.text(0, 0.30, "Trade-off (crescimento × margem)", fontweight="bold", fontsize=9.5,
                 color=VERMELHO, transform=axj.transAxes)
        axj.text(0, 0.12, _wrap(d["trade_off"]["texto"], 120), fontsize=8, va="top", transform=axj.transAxes)

    # --- gráfico 1: lucro acumulado ---
    ax1 = fig.add_subplot(gs[2, 0])
    for g in grupos:
        ax1.plot(a["series"][g]["lucro_acumulado"], color=cor[g], lw=1.8, label=g)
    ax1.set_title("Lucro acumulado", fontsize=9, fontweight="bold", loc="left")
    ax1.legend(fontsize=6.5, frameon=False); ax1.grid(axis="y", color="#f0e6ea")
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.yaxis.set_major_formatter(_fmt_k())
    ax1.set_xlabel(_wrap("Lucro acumulado por variante, obtido pela soma dos resultados diários.", 58),
                   fontsize=6, color="#8a8585", labelpad=6)

    # --- gráfico 2: lucro por comprador com IC ---
    ax2 = fig.add_subplot(gs[2, 1])
    ic = a["ic_lucro_por_comprador_diario"]
    means = [ic[g]["media"] for g in grupos]
    lo = [ic[g]["media"] - ic[g]["ic95_baixo"] for g in grupos]
    hi = [ic[g]["ic95_alto"] - ic[g]["media"] for g in grupos]
    ax2.bar(range(len(grupos)), means, color=[cor[g] for g in grupos],
            yerr=[lo, hi], capsize=4, error_kw={"ecolor": GRAFITE, "elinewidth": 1})
    ax2.set_xticks(range(len(grupos))); ax2.set_xticklabels(grupos, fontsize=7)
    ax2.set_title("Lucro por comprador (R$/dia ± IC95%)", fontsize=9, fontweight="bold", loc="left")
    ax2.grid(axis="y", color="#f0e6ea"); ax2.spines[["top", "right"]].set_visible(False)
    ax2.set_xlabel(_wrap("Média diária do lucro por comprador em cada variante; a barra indica a faixa provável de variação.", 58),
                   fontsize=6, color="#8a8585", labelpad=6)

    # --- gráfico 3: GMV x Lucro ---
    ax3 = fig.add_subplot(gs[3, 0])
    x = np.arange(len(grupos)); w = 0.38
    ax3.bar(x - w/2, [a["por_variante"][g]["gmv"] for g in grupos], w, color=ROSA, label="GMV")
    ax3.bar(x + w/2, [a["por_variante"][g]["lucro"] for g in grupos], w, color=VERMELHO, label="Lucro")
    ax3.set_xticks(x); ax3.set_xticklabels(grupos, fontsize=7)
    ax3.set_title("GMV × Lucro", fontsize=9, fontweight="bold", loc="left")
    ax3.legend(fontsize=6.5, frameon=False); ax3.grid(axis="y", color="#f0e6ea")
    ax3.spines[["top", "right"]].set_visible(False); ax3.yaxis.set_major_formatter(_fmt_k())
    ax3.set_xlabel(_wrap("Valores totais de GMV e de lucro para cada variante.", 58),
                   fontsize=6, color="#8a8585", labelpad=6)

    # --- gráfico 4: composição empilhada ---
    ax4 = fig.add_subplot(gs[3, 1])
    cb = [a["por_variante"][g]["cashback"] for g in grupos]
    lu = [a["por_variante"][g]["lucro"] for g in grupos]
    ax4.bar(x, cb, color=ROSA, label="Cashback")
    ax4.bar(x, lu, bottom=cb, color=VERMELHO, label="Lucro")
    ax4.set_xticks(x); ax4.set_xticklabels(grupos, fontsize=7)
    ax4.set_title("Composição da comissão", fontsize=9, fontweight="bold", loc="left")
    ax4.legend(fontsize=6.5, frameon=False); ax4.grid(axis="y", color="#f0e6ea")
    ax4.spines[["top", "right"]].set_visible(False); ax4.yaxis.set_major_formatter(_fmt_k())
    ax4.set_xlabel(_wrap("Comissão de cada variante repartida em cashback devolvido e lucro retido.", 58),
                   fontsize=6, color="#8a8585", labelpad=6)

    # --- rodapé: tabela de métricas + qualidade ---
    ax5 = fig.add_subplot(gs[4, :]); ax5.axis("off")
    headers = ["Variante", "Compradores", "GMV", "Lucro", "ROI", "Margem", "Cashback %", "Ticket"]
    rows = []
    for g in grupos:
        v = a["por_variante"][g]
        rows.append([g, _num(v["compradores"]), _brl(v["gmv"]), _brl(v["lucro"]),
                     "—" if v["roi"] is None else f"{v['roi']:.2f}",
                     _pct(v["margem_pct"]), _pct(v["cashback_pct_gmv"]), _brl(v["ticket_medio"])])
    tbl = ax5.table(cellText=rows, colLabels=headers, loc="upper center", cellLoc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(7); tbl.scale(1, 1.35)
    for (r, c), cell in tbl.get_cells().items() if hasattr(tbl, "get_cells") else tbl.get_celld().items():
        cell.set_edgecolor("#e7dde1")
        if r == 0:
            cell.set_facecolor(GRAFITE); cell.set_text_props(color="white", fontweight="bold")
        elif grupos[r-1] == d["recomendacao"]:
            cell.set_facecolor(ROSA_CLARO)
    qtxt = (f"Qualidade: {q.get('linhas_validas',0)}/{q.get('linhas_lidas',0)} linhas válidas "
            f"({q.get('taxa_aproveitamento_pct',0)}%). "
            f"Descartes: {sum(i['quantidade'] for i in q.get('descartes',[]))} · "
            f"Quarentena: {sum(i['quantidade'] for i in q.get('quarentena',[]))} · "
            f"Observações: {len(q.get('alertas',[]))}.")
    ax5.text(0.5, 0.02, qtxt, transform=ax5.transAxes, ha="center", fontsize=7, color="#8a8585")

    from matplotlib.backends.backend_pdf import PdfPages
    with PdfPages(out_pdf) as pdf:
        pdf.savefig(fig, facecolor="white")
        plt.close(fig)
        fig2 = _pagina_achados(a, nome_teste)
        pdf.savefig(fig2, facecolor="white")
        plt.close(fig2)


def _pagina_achados(a, nome_teste):
    """Segunda página do relatório: destaques/exceções, curva de resposta e método."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle
    import textwrap

    d = a["decisao"]
    achados = d.get("destaques", [])
    premissas = a.get("premissas", [])
    curva = a.get("curva_cashback", [])

    fig = plt.figure(figsize=(8.27, 11.05)); fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    # faixa de título
    ax.add_patch(FancyBboxPatch((0.06, 0.925), 0.88, 0.055,
                 boxstyle="round,pad=0.003,rounding_size=0.012", facecolor=GRAFITE, edgecolor="none"))
    ax.text(0.085, 0.963, "MÉLIUZ · GROWTH · ANÁLISE A/B DE CASHBACK", color=ROSA,
            fontsize=8, fontweight="bold", va="center")
    ax.text(0.085, 0.941, f"Análise complementar — {nome_teste}", color="white",
            fontsize=12.5, fontweight="bold", va="center")

    y = 0.885
    ax.text(0.06, y, "Destaques e exceções", fontsize=10.5, fontweight="bold", color=VERMELHO)
    y -= 0.028
    for item in (achados or ["Sem destaques adicionais além da recomendação principal."]):
        wrapped = textwrap.wrap(item, width=104)
        h = 0.0165 * len(wrapped) + 0.016
        ax.add_patch(Rectangle((0.06, y - h), 0.88, h, facecolor=ROSA_CLARO, edgecolor="none"))
        ax.add_patch(Rectangle((0.06, y - h), 0.007, h, facecolor=VERMELHO, edgecolor="none"))
        ax.text(0.082, y - 0.012, "\n".join(wrapped), fontsize=8, va="top", color="#4a4646")
        y -= (h + 0.014)

    # --- curva de resposta ao cashback (combo barras + linha) ---
    if curva:
        y -= 0.015
        ax.text(0.06, y, "Resposta ao cashback", fontsize=10.5, fontweight="bold", color=VERMELHO)
        y -= 0.012
        chart_h = 0.20
        axc = fig.add_axes([0.10, y - chart_h, 0.80, chart_h])
        labels = [p["grupo"] for p in curva]
        cb_pct = [p["cashback_pct_gmv"] for p in curva]
        lpc = [p["lucro_por_comprador"] for p in curva]
        xpos = np.arange(len(labels))
        axc.bar(xpos, cb_pct, color=ROSA, width=0.5, label="Cashback (% do GMV)")
        axc.set_ylabel("% cashback do GMV", fontsize=7, color="#8a8585")
        axc.set_xticks(xpos); axc.set_xticklabels(labels, fontsize=7)
        axc.tick_params(labelsize=7); axc.spines[["top"]].set_visible(False)
        axl = axc.twinx()
        axl.plot(xpos, lpc, color=VERMELHO, lw=2.2, marker="o", ms=5, label="Lucro por comprador")
        axl.set_ylabel("Lucro por comprador (R$)", fontsize=7, color="#8a8585")
        axl.tick_params(labelsize=7); axl.spines[["top"]].set_visible(False)
        axl.set_ylim(bottom=min(0, min(lpc)))
        h1, l1 = axc.get_legend_handles_labels()
        h2, l2 = axl.get_legend_handles_labels()
        axc.legend(h1 + h2, l1 + l2, fontsize=6.5, frameon=False, loc="upper right")
        y -= (chart_h + 0.03)

    y -= 0.01
    ax.text(0.06, y, "Como a decisão foi tomada", fontsize=10.5, fontweight="bold", color=VERMELHO)
    y -= 0.026
    metodo = [
        "Métrica de decisão: lucro (comissão menos cashback). A variante recomendada é a de maior "
        "lucro por comprador, validada estatisticamente.",
        "Estatística: intervalos de confiança de 95% por reamostragem (bootstrap) sobre a série diária "
        "de lucro por comprador; a diferença para a 2ª colocada é consistente quando o intervalo não inclui o zero.",
    ] + list(premissas)
    for m in metodo:
        wrapped = textwrap.wrap("•  " + m, width=108)
        ax.text(0.06, y, "\n".join(wrapped), fontsize=8, va="top", color="#4a4646")
        y -= (0.016 * len(wrapped) + 0.012)

    ax.text(0.5, 0.03, "Gerado automaticamente pela skill ab-cashback-analyzer",
            ha="center", fontsize=7, color="#a9a4a4")
    return fig


def _wrap(txt, width):
    import textwrap
    return "\n".join(textwrap.wrap(txt, width=width))


def _fmt_k():
    import matplotlib.ticker as mticker
    def f(v, _):
        if abs(v) >= 1e6: return f"R${v/1e6:.1f}M"
        if abs(v) >= 1e3: return f"R${v/1e3:.0f}k"
        return f"R${v:.0f}"
    return mticker.FuncFormatter(f)


def generate(path: str, out_dir: str, nome_teste: str = None) -> dict:
    a = analyze_run(path)
    if "erro" in a:
        raise ValueError(f"Não foi possível analisar: {a['erro']}")
    if not nome_teste:
        nome_teste = f"Teste A/B — {', '.join(a['parceiros'])}"
    os.makedirs(out_dir, exist_ok=True)
    slug = "".join(c if c.isalnum() else "_" for c in nome_teste)[:40]
    html_path = os.path.join(out_dir, f"dashboard_{slug}.html")
    pdf_path = os.path.join(out_dir, f"relatorio_{slug}.pdf")
    json_path = os.path.join(out_dir, f"analise_{slug}.json")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(a, nome_teste))
    build_pdf(a, nome_teste, pdf_path)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(a, f, ensure_ascii=False, indent=2, default=str)

    return {"analise": a, "html": html_path, "pdf": pdf_path, "json": json_path, "nome_teste": nome_teste}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("uso: python report.py <arquivo.csv> <dir_saida> [\"Nome do teste\"]"); sys.exit(1)
    nome = sys.argv[3] if len(sys.argv) > 3 else None
    r = generate(sys.argv[1], sys.argv[2], nome)
    print(json.dumps({k: v for k, v in r.items() if k != "analise"}, ensure_ascii=False, indent=2))
