
import sys, os, csv, io
from datetime import date

try:
    from analyze import run as analyze_run
except ImportError:
    from scripts.analyze import run as analyze_run

CABECALHO = [
    "Data da análise", "Nome do teste", "Descrição", "Parceiro", "Período",
    "Variantes", "Métrica de decisão", "Resultado", "Decisão",
    "Confiança estatística",
    "Lucro/comprador (recomendada)", "ROI (recomendada)", "Margem % (recomendada)",
    "Taxa de cashback % (recomendada)", "Destaques",
    "Alertas de qualidade",
]


def _brl(v):
    try:
        return "R$ " + f"{float(v):,.0f}".replace(",", ".")
    except Exception:
        return "—"


def montar_linha(analise: dict, nome_teste: str, descricao: str) -> dict:
    d = analise["decisao"]
    q = analise["qualidade"]
    per = analise["periodo"]
    venc = d["recomendacao"]
    v = analise["por_variante"].get(venc, {})

    # "Resultado" = síntese numérica do que a variante recomendada entregou
    resultado = (f"{venc}: lucro {_brl(v.get('lucro'))}, "
                 f"ROI {'—' if v.get('roi') is None else f'{v.get('roi'):.2f}'}, "
                 f"margem {'—' if v.get('margem_pct') is None else f'{v.get('margem_pct'):.1f}%'}, "
                 f"{('—' if v.get('compradores') is None else format(int(v.get('compradores')), ',').replace(',', '.'))} compradores")

    if d.get("trade_off") and d["trade_off"].get("existe"):
        resultado += (f" | trade-off: {d['trade_off']['variante_maior_gmv']} tem maior GMV "
                      f"({_brl(d['trade_off']['gmv_da_maior_gmv'])}) mas menos lucro")

    n_desc = sum(i["quantidade"] for i in q.get("descartes", []))
    n_quar = sum(i["quantidade"] for i in q.get("quarentena", []))
    alertas = (f"{q.get('linhas_validas',0)}/{q.get('linhas_lidas',0)} válidas "
               f"({q.get('taxa_aproveitamento_pct',0)}%); descartes {n_desc}; quarentena {n_quar}"
               + (f"; {len(q.get('alertas',[]))} alerta(s)" if q.get("alertas") else ""))

    return {
        "Data da análise": date.today().isoformat(),
        "Nome do teste": nome_teste,
        "Descrição": descricao or f"Teste de cashback — {', '.join(analise['parceiros'])}",
        "Parceiro": ", ".join(analise["parceiros"]),
        "Período": f"{per['inicio']} a {per['fim']} ({per['dias']}d)",
        "Variantes": ", ".join(analise["por_variante"].keys()),
        "Métrica de decisão": "Lucro (comissão − cashback)",
        "Resultado": resultado,
        "Decisão": f"{d['veredito']} → {venc}",
        "Confiança estatística": str(d["confianca_estatistica"]),
        "Lucro/comprador (recomendada)": "—" if v.get("lucro_por_comprador") is None else ("R$ " + f"{v.get('lucro_por_comprador'):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")),
        "ROI (recomendada)": "—" if v.get("roi") is None else f"{v.get('roi'):.2f}".replace(".", ","),
        "Margem % (recomendada)": "—" if v.get("margem_pct") is None else f"{v.get('margem_pct'):.1f}".replace(".", ","),
        "Taxa de cashback % (recomendada)": "—" if v.get("cashback_pct_gmv") is None else f"{v.get('cashback_pct_gmv'):.1f}".replace(".", ","),
        "Destaques": " | ".join(d.get("destaques", [])) or "—",
        "Alertas de qualidade": alertas,
    }


def append_master(linha: dict, master_csv: str) -> list:
    """Acrescenta a linha ao CSV mestre (cria com cabeçalho se não existir). Retorna todas as linhas."""
    linhas = []
    if os.path.exists(master_csv):
        with open(master_csv, encoding="utf-8") as fh:
            linhas = list(csv.DictReader(fh))
    linhas.append(linha)
    with open(master_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CABECALHO)
        w.writeheader()
        for r in linhas:
            w.writerow({k: r.get(k, "") for k in CABECALHO})
    return linhas


def master_to_csv_text(master_csv: str) -> str:
    """Retorna o conteúdo do CSV mestre como texto (para subir à planilha Google)."""
    with open(master_csv, encoding="utf-8") as fh:
        return fh.read()


def post_webhook(linha: dict, url: str, secret: str, timeout: int = 15) -> dict:
    """
    Envia a linha para um Web App do Google Apps Script (opção de link fixo + append
    automático). Usa só a stdlib. Retorna {"ok": bool, ...}.

    Importante: de dentro do sandbox do Claude o domínio do Google é bloqueado, então
    esta chamada só funciona quando a skill roda num ambiente com acesso ao Google
    (ex.: máquina local via Claude Code). Em caso de falha de rede, quem chama deve
    cair no fallback do curl (ver run.py).
    """
    import json as _json, urllib.request, urllib.error
    payload = _json.dumps({"secret": secret, "row": linha}).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
        try:
            return _json.loads(body)
        except ValueError:
            return {"ok": True, "resposta_bruta": body[:500]}
    except urllib.error.URLError as e:
        return {"ok": False, "erro": str(e)}


def curl_para_webhook(linha: dict, url: str, secret: str) -> str:
    """Monta o comando curl equivalente, para o usuário rodar de um ambiente com acesso ao Google."""
    import json as _json, shlex
    payload = _json.dumps({"secret": secret, "row": linha}, ensure_ascii=False)
    return (f"curl -L -X POST {shlex.quote(url)} "
            f"-H 'Content-Type: application/json' "
            f"-d {shlex.quote(payload)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('uso: python registry.py <csv> "Nome" "Descrição" [master.csv]'); sys.exit(1)
    arq, nome = sys.argv[1], sys.argv[2]
    desc = sys.argv[3] if len(sys.argv) > 3 else ""
    master = sys.argv[4] if len(sys.argv) > 4 else "registro_mestre.csv"
    analise = analyze_run(arq)
    linha = montar_linha(analise, nome, desc)
    append_master(linha, master)
    print("Linha registrada no mestre:", master)
    for k, v in linha.items():
        print(f"  {k}: {v}")
