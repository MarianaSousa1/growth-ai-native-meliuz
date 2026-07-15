/**
 * Webhook de append para o "Registro de Testes A/B — Méliuz".
 *
 * Como usar:
 *   1. Abra a planilha (a editável, não o link /pubhtml).
 *   2. Extensões → Apps Script.
 *   3. Apague o conteúdo padrão e cole este arquivo inteiro.
 *   4. Troque o valor de SECRET por um segredo seu.
 *   5. Implantar → Nova implantação → tipo "App da Web".
 *        - Executar como: Eu
 *        - Quem tem acesso: Qualquer pessoa
 *   6. Autorize e copie a URL que termina em /exec.
 *
 * A skill (ou um curl) manda um POST com JSON:
 *   { "secret": "SEU_SEGREDO", "row": { "Data da análise": "...", ... } }
 * e este script acrescenta uma linha na primeira aba, mantendo o mesmo arquivo
 * (portanto o mesmo link público). Ele nunca apaga nem sobrescreve nada.
 */

const SECRET = "troque-este-segredo";

const COLS = [
  "Data da análise", "Nome do teste", "Descrição", "Parceiro", "Período",
  "Variantes", "Métrica de decisão", "Resultado", "Decisão",
  "Confiança estatística",
  "Lucro/comprador (recomendada)", "ROI (recomendada)", "Margem % (recomendada)",
  "Taxa de cashback % (recomendada)", "Destaques",
  "Alertas de qualidade"
];

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    if (body.secret !== SECRET) {
      return _json({ ok: false, error: "segredo inválido" });
    }
    const sh = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
    if (sh.getLastRow() === 0) {
      sh.appendRow(COLS); // cria cabeçalho se a aba estiver vazia
    }
    const row = body.row || {};
    const linha = COLS.map(function (c) { return row[c] != null ? row[c] : ""; });
    sh.appendRow(linha);
    return _json({ ok: true, added: linha, totalRows: sh.getLastRow() - 1 });
  } catch (err) {
    return _json({ ok: false, error: String(err) });
  }
}

// permite checar no navegador se o webhook está no ar
function doGet() {
  return _json({ ok: true, msg: "webhook ativo" });
}

function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
