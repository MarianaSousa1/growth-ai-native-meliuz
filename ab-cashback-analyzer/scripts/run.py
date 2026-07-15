"""
run.py — Ponto de entrada único da skill. Executa o fluxo completo:
  ingest (saneamento) -> analyze (métricas/estatística/decisão)
  -> report (dashboard HTML + PDF) -> registry (linha no CSV mestre).

Não sobe nada para o Google Sheets: isso é feito pelo Claude via conector,
porque a API do Google está fora da lista de domínios liberados do sandbox.
Esta etapa deixa pronto o CSV mestre (registro_mestre.csv) para o Claude subir.

Uso:
  python run.py --csv <arquivo.csv> --nome "Nome do teste" \
                [--descricao "..."] [--out <dir_saida>] [--master <master.csv>]

Saída: imprime um JSON com os caminhos gerados e um resumo da decisão.
"""

import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from report import generate
from registry import montar_linha, append_master, post_webhook, curl_para_webhook


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="caminho do CSV do teste A/B")
    ap.add_argument("--nome", required=True, help="nome do teste")
    ap.add_argument("--descricao", default="", help="descrição curta do teste")
    ap.add_argument("--out", default="outputs", help="diretório de saída dos relatórios")
    ap.add_argument("--master", default="registro_mestre.csv", help="CSV mestre do histórico")
    ap.add_argument("--webhook", default="", help="URL do Web App (Apps Script) para append automático na planilha")
    ap.add_argument("--secret", default="", help="segredo compartilhado do webhook")
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        print(json.dumps({"erro": f"arquivo não encontrado: {args.csv}"}, ensure_ascii=False)); sys.exit(1)

    g = generate(args.csv, args.out, args.nome)
    analise = g["analise"]

    linha = montar_linha(analise, args.nome, args.descricao)
    todas = append_master(linha, args.master)

    # opção de link fixo + append automático via Web App do Apps Script
    sheets_sync = None
    if args.webhook:
        if not args.secret:
            sheets_sync = {"ok": False, "erro": "informe --secret junto de --webhook"}
        else:
            res = post_webhook(linha, args.webhook, args.secret)
            if res.get("ok"):
                sheets_sync = {"ok": True, "detalhe": res}
            else:
                # de dentro do sandbox do Claude o Google é bloqueado: entrega o curl para rodar num ambiente com acesso
                sheets_sync = {
                    "ok": False,
                    "erro": res.get("erro", "falha ao contatar o webhook"),
                    "rode_este_curl": curl_para_webhook(linha, args.webhook, args.secret),
                }

    d = analise["decisao"]
    resumo = {
        "nome_teste": g["nome_teste"],
        "recomendacao": d["recomendacao"],
        "veredito": d["veredito"],
        "confianca": d["confianca_estatistica"],
        "tem_trade_off": bool(d.get("trade_off") and d["trade_off"].get("existe")),
        "arquivos": {"dashboard_html": g["html"], "relatorio_pdf": g["pdf"], "analise_json": g["json"]},
        "registro": {"master_csv": os.path.abspath(args.master), "total_testes_registrados": len(todas)},
        "sheets_sync": sheets_sync,
        "linha_registro": linha,
        "qualidade": {
            "linhas_validas": analise["qualidade"].get("linhas_validas"),
            "linhas_lidas": analise["qualidade"].get("linhas_lidas"),
            "aproveitamento_pct": analise["qualidade"].get("taxa_aproveitamento_pct"),
            "alertas": analise["qualidade"].get("alertas", []),
        },
    }
    print(json.dumps(resumo, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
