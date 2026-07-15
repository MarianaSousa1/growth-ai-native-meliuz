"""
ingest.py — Leitura e saneamento robusto de datasets de teste A/B de cashback.

Filosofia: o arquivo de entrada é SEMPRE tratado como potencialmente sujo.
Nunca imputamos valores nem "consertamos" um número no escuro. Toda linha que
não passa numa checagem é DESCARTADA ou colocada em QUARENTENA, e o motivo fica
registrado no relatório de qualidade — porque quem decide precisa saber em que
fração dos dados a decisão se apoia.

Saída: um objeto CleanResult com
  - df        : DataFrame limpo, tipado e ordenado (só linhas confiáveis)
  - quality   : dicionário serializável com o relatório de qualidade
Uso via CLI:
  python ingest.py <caminho_csv>            # imprime o relatório de qualidade em JSON
"""

import sys, json, re, unicodedata
from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Esquema esperado. As chaves são nomes CANÔNICOS internos; os valores são a
# lista de rótulos que já vimos ou que razoavelmente podem aparecer para a mesma
# coluna. A normalização de cabeçalho tolera acento, caixa e espaços extras.
# ---------------------------------------------------------------------------
SCHEMA = {
    "data":        ["data", "date", "dia"],
    "grupo":       ["grupos de usuarios", "grupo de usuarios", "grupo", "variante", "group"],
    "parceiro":    ["parceiro", "partner"],
    "compradores": ["compradores", "buyers", "usuarios unicos"],
    "comissao":    ["comissao", "commission"],
    "cashback":    ["cashback"],
    "gmv":         ["vendas totais", "gmv", "vendas", "faturamento"],
}
MONEY_COLS = ["comissao", "cashback", "gmv"]
NUMERIC_COLS = ["compradores"] + MONEY_COLS


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", _strip_accents(str(h)).strip().lower())


def _read_raw(path: str) -> pd.DataFrame:
    """Lê o CSV tolerando separador e encoding variáveis. Sniffing simples e barato."""
    last_err = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, "r", encoding=enc, errors="strict") as fh:
                sample = fh.read(4096)
            # heurística de separador: o que aparece mais no cabeçalho
            sep = ";" if sample.count(";") > sample.count(",") else ","
            df = pd.read_csv(path, dtype=str, keep_default_na=False, sep=sep, encoding=enc)
            df.attrs["encoding"] = enc
            df.attrs["sep"] = sep
            return df
        except (UnicodeDecodeError, UnicodeError) as e:
            last_err = e
            continue
    raise RuntimeError(f"Não foi possível decodificar o arquivo em utf-8/latin-1: {last_err}")


def _map_columns(df: pd.DataFrame):
    """Casa cabeçalhos do arquivo com os nomes canônicos. Retorna (rename_map, faltando)."""
    norm_to_orig = {_norm_header(c): c for c in df.columns}
    rename, missing = {}, []
    for canon, aliases in SCHEMA.items():
        hit = next((norm_to_orig[a] for a in aliases if a in norm_to_orig), None)
        if hit is None:
            missing.append(canon)
        else:
            rename[hit] = canon
    return rename, missing


_MONEY_RE = re.compile(r"[^\d,.\-]")

def _parse_money_br(x: str):
    """
    Converte moeda em formato brasileiro para float.
    Aceita 'R$ 10.273', '10.273,55', '1.234', '769', '-50,00'.
    Regra: ponto = separador de milhar, vírgula = decimal (padrão BR).
    Retorna np.nan se irrecuperável.
    """
    if x is None:
        return np.nan
    s = _MONEY_RE.sub("", str(x)).strip()
    if s in ("", "-", "."):
        return np.nan
    neg = s.startswith("-")
    s = s.lstrip("-")
    if "," in s:                       # vírgula presente => é o decimal
        s = s.replace(".", "").replace(",", ".")
    else:                              # sem vírgula => pontos são milhar
        s = s.replace(".", "")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return np.nan


def _parse_int(x: str):
    s = re.sub(r"[^\d\-]", "", str(x)).strip()
    if s in ("", "-"):
        return np.nan
    try:
        return int(s)
    except ValueError:
        return np.nan


def _norm_grupo(g: str) -> str:
    """Normaliza rótulo de variante: 'grupo1', 'Gurpo 2', 'GRUPO 3' -> 'Grupo N' quando possível."""
    raw = str(g).strip()
    m = re.search(r"(\d+)", raw)
    low = _strip_accents(raw).lower()
    if ("grup" in low or "grop" in low or "gurp" in low or "variant" in low) and m:
        return f"Grupo {int(m.group(1))}"
    return raw  # deixa como veio; passará pelo filtro de "grupo suspeito"


@dataclass
class CleanResult:
    df: pd.DataFrame
    quality: dict
    quarantine: pd.DataFrame = field(default_factory=pd.DataFrame)


def clean(path: str) -> CleanResult:
    q = {
        "arquivo": path.split("/")[-1],
        "linhas_lidas": 0,
        "linhas_validas": 0,
        "descartes": [],           # lista de {motivo, quantidade}
        "quarentena": [],          # idem, mas linhas suspeitas isoladas
        "alertas": [],             # avisos que não descartam linhas
        "encoding_detectado": None,
        "separador_detectado": None,
    }
    reasons = {}  # motivo -> contagem, para descartes
    quar = {}     # motivo -> contagem, para quarentena
    def drop(mask, motivo):
        n = int(mask.sum())
        if n: reasons[motivo] = reasons.get(motivo, 0) + n
        return n
    def quarantine(mask, motivo):
        n = int(mask.sum())
        if n: quar[motivo] = quar.get(motivo, 0) + n
        return n

    raw = _read_raw(path)
    q["encoding_detectado"] = raw.attrs.get("encoding")
    q["separador_detectado"] = raw.attrs.get("sep")
    q["linhas_lidas"] = len(raw)

    rename, missing = _map_columns(raw)
    if missing:
        # Colunas essenciais ausentes => não dá para analisar com honestidade.
        q["erro_fatal"] = (
            f"Colunas essenciais não encontradas no arquivo: {missing}. "
            f"Cabeçalhos lidos: {list(raw.columns)}"
        )
        return CleanResult(df=pd.DataFrame(), quality=q)

    df = raw.rename(columns=rename)[list(SCHEMA.keys())].copy()

    # --- tipagem ---
    df["data_parsed"] = pd.to_datetime(df["data"], errors="coerce", format="mixed")
    for c in MONEY_COLS:
        df[c] = df[c].map(_parse_money_br)
    df["compradores"] = df["compradores"].map(_parse_int)
    df["grupo"] = df["grupo"].map(_norm_grupo)
    df["parceiro"] = df["parceiro"].astype(str).str.strip()

    quar_rows = []  # guardamos as linhas em quarentena para o anexo

    # --- 1. data inválida => descarte (sem data não há série temporal) ---
    m = df["data_parsed"].isna()
    if drop(m, "data ausente ou em formato inválido"):
        df = df[~m]

    # --- 2. campos numéricos essenciais vazios/inválidos => descarte ---
    for c in NUMERIC_COLS:
        m = df[c].isna()
        if drop(m, f"'{c}' vazio ou não numérico"):
            df = df[~m]

    # --- 3. valores negativos ilógicos => quarentena (lucro pode ser negativo; estes não) ---
    for c in NUMERIC_COLS:  # compradores, comissao, cashback, gmv nunca são < 0
        m = df[c] < 0
        if quarantine(m, f"'{c}' negativo (impossível)"):
            quar_rows.append(df[m]); df = df[~m]

    # --- 4. inconsistências lógicas => quarentena ---
    m = df["cashback"] > df["gmv"]
    if quarantine(m, "cashback maior que GMV"):
        quar_rows.append(df[m]); df = df[~m]
    m = df["comissao"] > df["gmv"]
    if quarantine(m, "comissão maior que GMV"):
        quar_rows.append(df[m]); df = df[~m]
    m = (df["compradores"] > 0) & (df["gmv"] <= 0)
    if quarantine(m, "compradores > 0 mas GMV = 0"):
        quar_rows.append(df[m]); df = df[~m]

    # --- 5. grupo suspeito (não casa 'Grupo N') => quarentena, não some calado ---
    m = ~df["grupo"].str.match(r"^Grupo \d+$", na=False)
    if quarantine(m, "rótulo de variante irreconhecível"):
        quar_rows.append(df[m]); df = df[~m]

    # --- 6. duplicatas ---
    m = df.duplicated(keep="first")
    if drop(m, "linha totalmente duplicada"):
        df = df[~m]
    # duplicata de chave (mesma Data+Grupo+Parceiro) com valores divergentes => quarentena inteira
    key = ["data_parsed", "grupo", "parceiro"]
    dupkey = df.duplicated(subset=key, keep=False)
    if dupkey.any():
        if quarantine(dupkey, "chave (data+variante+parceiro) repetida com valores divergentes"):
            quar_rows.append(df[dupkey]); df = df[~dupkey]

    # --- 7. ordenação cronológica (não é defeito, mas normalizamos) ---
    if not df["data_parsed"].is_monotonic_increasing:
        q["alertas"].append("linhas fora de ordem cronológica no arquivo; foram reordenadas")
    df = df.sort_values(["grupo", "data_parsed"]).reset_index(drop=True)

    # --- alertas de comparabilidade entre variantes (crucial para A/B) ---
    if not df.empty:
        janelas = df.groupby("grupo")["data_parsed"].agg(["min", "max", "nunique"])
        ndias = janelas["nunique"]
        if ndias.nunique() > 1:
            q["alertas"].append(
                "variantes com número de dias diferente — comparação de TOTAIS fica enviesada; "
                "a análise prioriza métricas normalizadas (por dia / por comprador)."
            )
        if janelas["min"].nunique() > 1 or janelas["max"].nunique() > 1:
            q["alertas"].append("variantes com janelas de datas diferentes; verifique se o teste foi simultâneo.")
        # variante com volume de dias irrisório costuma ser grupo fantasma ou typo em massa.
        # Referência é a MAIOR variante (a mediana degenera quando há vários grupos minúsculos).
        max_dias = ndias.max()
        for g, nd in ndias.items():
            if max_dias > 0 and nd < 0.3 * max_dias:
                q["alertas"].append(
                    f"variante '{g}' tem apenas {int(nd)} dia(s) de dados vs. {int(max_dias)} da maior variante — "
                    f"possível grupo fantasma ou erro de rotulagem; foi mantida, mas é sinalizada e não deve ser escalada."
                )
        if len(df["parceiro"].unique()) > 1:
            q["alertas"].append(f"múltiplos parceiros no mesmo arquivo: {sorted(df['parceiro'].unique())}")

    q["descartes"] = [{"motivo": k, "quantidade": v} for k, v in reasons.items()]
    q["quarentena"] = [{"motivo": k, "quantidade": v} for k, v in quar.items()]
    q["linhas_validas"] = len(df)
    total = q["linhas_lidas"] or 1
    q["taxa_aproveitamento_pct"] = round(100 * len(df) / total, 1)

    quarantine_df = pd.concat(quar_rows) if quar_rows else pd.DataFrame()
    return CleanResult(df=df, quality=q, quarantine=quarantine_df)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("uso: python ingest.py <arquivo.csv>"); sys.exit(1)
    res = clean(sys.argv[1])
    print(json.dumps(res.quality, ensure_ascii=False, indent=2))
    if not res.df.empty:
        print("\n--- amostra dos dados limpos ---")
        print(res.df.head().to_string())
