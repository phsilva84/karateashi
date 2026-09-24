#!/usr/bin/env python3
"""tools/pre_exame.py — Folhas OMR v5.8 (faixa de titulos rente + nomes no
rodape) + JSON de coordenadas.

Comportamento padrao (configs):
- alunos ............ data/cadastro/alunos.json (todos)
- avaliadores ....... config/avaliadores.json (todos)
- layout ............ 3 alunos por folha (A4 paisagem 297x210mm)
- filtros opcionais . --aluno / --avaliador / --csv (nenhum e obrigatorio)

Layout v5.8 (ajustes definitivos de posicionamento):
- cabecalho compacto de 14mm (dojo/avaliador/exame + instrucao); grid sobe;
- faixa de titulos KIHON/KATA/BUNKAI/KUMITE RENTE a borda superior de cada
  linha (a 1,2mm), sem tira de nome acima — a identificacao da linha fica
  na PRESENCA no fim do Kihon (balao + "Nome (Faixa)");
- criterios numerados em UMA linha, primeiro a 6,0mm do topo (logo abaixo
  da faixa); 5 baloes de frequencia por criterio, centralizados no texto;
- divisorias verticais entre as colunas;
- RODAPE 38mm: 3 caixas com borda, faixa cinza compacta (3,6mm) com o NOME
  do aluno em negrito 6,5pt no topo de cada bloco; logo abaixo, a faixa
  BOM! / A MELHORAR (3mm) com divisor vertical e os 6+6 circulos.

Contrato OMR (este arquivo e core/omr_reader.py sao gemeos):
- a MESMA geometria em mm (origem topo-esquerda) desenha e e gravada em
  {exame}_{avaliador}_folha1_coordenadas.json: presenca, frequencias
  (5 baloes/criterio), observacoes obs_p1..obs_m6.
- --validar confere a estrutura e imprime a geometria de referencia.

Uso:
  python tools/pre_exame.py --exame EXA-D01-2026-10 --validar
  python tools/pre_exame.py --exame EXA-D01-2026-10 --avaliador S01 --validar
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import qrcode
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdfcanvas

from core import observacoes
from core.config import QUESITOS, carregar_json

MM = 72.0 / 25.4
A4_W_MM, A4_H_MM = 297.0, 210.0
ALUNOS_POR_FOLHA = 3
BALOES_POR_CRITERIO = 5

# ---------------------------------------------------------------------------
# Geometria (mm, origem topo-esquerda) — fonte unica folha/JSON
# ---------------------------------------------------------------------------
MARGEM = 10.0
HEADER_H = 14.0          # cabecalho compacto (sem titulo) — grid sobe
FOOTER_H = 38.0
LINHA_H = (A4_H_MM - HEADER_H - FOOTER_H) / ALUNOS_POR_FOLHA   # 52.67
FOOTER_Y0 = HEADER_H + 3 * LINHA_H                              # 172

QR_CAB_X = A4_W_MM - MARGEM - 12.0      # 275
QR_CAB_Y = 2.0
QR_CAB_TAM = 12.0
QR_ALUNO_X = (195.0, 214.0, 233.0)
QR_ALUNO_Y = 2.0
QR_ALUNO_TAM = 10.0

# Grade de quesitos
QUESITO_X0 = MARGEM
QUESITO_LARG = (A4_W_MM - 2 * MARGEM) / 4.0     # 69.25
QUESITO_TITLE_Y0 = 1.2      # RENTE a borda superior da linha (<- antes 4.2)
QUESITO_TITLE_H = 3.0
QUESITO_TITLE_CY = 2.7      # centro do texto na faixa
CRIT_Y0 = 6.0               # 1o criterio logo abaixo da faixa (<- antes 8.5)
CRIT_ESPACO = 4.9           # uma linha por criterio
TEXTO_CRIT_X = 1.0
BALAO_X0 = 34.0
BALAO_ESPACO = 5.0
BALAO_RAIO = 1.8
BALAO_Y_OFFSET = 0.6        # balao centralizado com o texto (<- antes 1.2)

# Presenca (fim da coluna Kihon)
PRES_RAIO = 1.8
PRES_LABEL_GAP = 1.5
PRES_BOT_OFFSET = 4.0

# Rodape de observacoes
OBS_BLOCK_GAP = 2.0
OBS_ITEM_ESPACO = 3.8
OBS_RAIO = 1.5
OBS_CHK_X_OFFSET = 3.5
OBS_TEXTO_GAP = 3.0
OBS_BOTTOM_MARGIN = 5.0

# Tipografia
F_TITULO = 13
F_SUBTITULO = 9
F_INSTRUCAO = 6.5
F_QUESITO = 6.5
F_CRITERIO = 6.0
F_CRITERIO_MIN = 5.5
F_OBS = 6.0
F_OBS_TITULO = 5.5
F_NOME_OBS = 6.5           # nome no rodape — proporcional (<- antes 8.0)


# ---------------------------------------------------------------------------
# Primitivas
# ---------------------------------------------------------------------------
def _y(y_topo_mm: float) -> float:
    return (A4_H_MM - y_topo_mm) * MM


def _texto(pdf, texto, x_mm, cy_topo_mm, tam, fonte="Helvetica",
           offset_pt=0.0):
    pdf.setFont(fonte, tam)
    pdf.drawString(x_mm * MM, _y(cy_topo_mm) - tam * 0.35 - offset_pt, texto)


def _texto_centrado(pdf, texto, cx_mm, cy_topo_mm, tam, fonte="Helvetica"):
    larg = stringWidth(texto, fonte, tam)
    _texto(pdf, texto, cx_mm - larg / (2 * MM), cy_topo_mm, tam, fonte)


def _quebrar(texto, tam, larg_max_mm):
    larg = larg_max_mm * MM
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = f"{atual} {palavra}".strip()
        if stringWidth(teste, "Helvetica", tam) <= larg:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas or [""]


def _balao(pdf, cx_mm, cy_topo_mm, r_mm):
    cy = _y(cy_topo_mm)
    pdf.ellipse((cx_mm - r_mm) * MM, cy - r_mm * MM,
                (cx_mm + r_mm) * MM, cy + r_mm * MM)


def _qr(pdf, texto, x_mm, y_topo_mm, lado_mm):
    img = qrcode.make(texto)
    pdf.drawInlineImage(img, x_mm * MM, _y(y_topo_mm) - lado_mm * MM,
                        width=lado_mm * MM, height=lado_mm * MM)


# ---------------------------------------------------------------------------
# Cargas (default = configs)
# ---------------------------------------------------------------------------
def _carregar_alunos(csv_path, raiz):
    if csv_path is not None:
        dados = []
        with open(csv_path, encoding="utf-8-sig", newline="") as fh:
            for i, linha in enumerate(csv.DictReader(fh), start=1):
                dados.append({
                    "id": (linha.get("id") or f"T{i:02d}").strip(),
                    "nome": linha.get("nome", "").strip(),
                    "faixa_atual": linha.get("faixa_atual", "").strip(),
                    "faixa_pretendida": linha.get("faixa_pretendida", "").strip(),
                    "dojo_id": (linha.get("dojo_id") or "D01").strip(),
                })
        return dados
    cfg = carregar_json(raiz / "data" / "cadastro" / "alunos.json")
    return [dict(a) for a in cfg.get("alunos", [])]


def _carregar_avaliadores(raiz, filtro):
    cfg = carregar_json(raiz / "config" / "avaliadores.json")
    avs = cfg.get("avaliadores", [])
    if filtro:
        avs = [a for a in avs if a["id"] in filtro]
    return avs


def _nome_dojo(raiz, dojo_id):
    cfg = carregar_json(raiz / "config" / "dojos.json")
    for d in cfg.get("dojos", []):
        if d["id"] == dojo_id:
            return d.get("nome", dojo_id)
    return dojo_id


# ---------------------------------------------------------------------------
# Desenho
# ---------------------------------------------------------------------------
def _desenhar_cabecalho(pdf, av, dojo_id, dojo_nome, exame):
    rotulo = (dojo_nome if dojo_nome.strip().lower().startswith("dojo")
              else f"Dojo {dojo_nome}")
    _texto(pdf, f"{rotulo} ({dojo_id}) | Avaliador: {av['nome']} ({av['id']}) "
                f"| Exame: {exame}", MARGEM, 3.5, F_SUBTITULO)
    _texto(pdf, "Instrucao: preencha os circulos com caneta. Marque o circulo "
                "de PRESENCA do aluno. Observacoes: marque as opcoes que se "
                "aplicam.", MARGEM, 8.0, F_INSTRUCAO)
    _qr(pdf, f"KA|AVALIADOR={av['id']}|DOJO={dojo_id}|EXAME={exame}",
        QR_CAB_X, QR_CAB_Y, QR_CAB_TAM)


def _desenhar_linha(pdf, aluno, idx, matriz_faixa, coords, pagina):
    y0 = HEADER_H + idx * LINHA_H
    y1 = y0 + LINHA_H

    # Borda da linha
    pdf.setStrokeColorRGB(0, 0, 0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.rect(MARGEM * MM, _y(y1), (A4_W_MM - 2 * MARGEM) * MM,
             LINHA_H * MM, stroke=1, fill=0)

    # Faixa cinza KIHON/KATA/BUNKAI/KUMITE — RENTE a borda superior
    pdf.setFillColorRGB(0.92, 0.92, 0.92)
    pdf.rect(QUESITO_X0 * MM,
             _y(y0 + QUESITO_TITLE_Y0 + QUESITO_TITLE_H),
             (4 * QUESITO_LARG) * MM, QUESITO_TITLE_H * MM, stroke=0, fill=1)
    pdf.setFillColorRGB(0, 0, 0)
    for i, quesito in enumerate(QUESITOS):
        x_col = QUESITO_X0 + i * QUESITO_LARG
        _texto_centrado(pdf, quesito.upper(), x_col + QUESITO_LARG / 2,
                        y0 + QUESITO_TITLE_CY, F_QUESITO, "Helvetica-Bold")

    # Criterios numerados (1 linha) + 5 baloes, centralizados no texto
    for i, quesito in enumerate(QUESITOS):
        x_col = QUESITO_X0 + i * QUESITO_LARG
        crits = matriz_faixa.get("quesitos", {}).get(quesito, {}).get(
            "criterios", [])
        for k, c in enumerate(crits):
            cy = y0 + CRIT_Y0 + k * CRIT_ESPACO
            rotulo = f"{k + 1}. {c.get('nome', c['chave'])}"
            tam = F_CRITERIO
            larg_txt = BALAO_X0 - TEXTO_CRIT_X - 1.0
            linhas = _quebrar(rotulo, tam, larg_txt)
            while len(linhas) > 1 and tam > F_CRITERIO_MIN:
                tam -= 0.5
                linhas = _quebrar(rotulo, tam, larg_txt)
            for li, linha in enumerate(linhas[:2]):
                _texto(pdf, linha, x_col + TEXTO_CRIT_X, cy, tam,
                       offset_pt=li * tam * 1.15)
            bcy = cy + BALAO_Y_OFFSET
            for b in range(BALOES_POR_CRITERIO):
                bx = x_col + BALAO_X0 + b * BALAO_ESPACO
                _balao(pdf, bx, bcy, BALAO_RAIO)
                coords.append({"aluno": idx + 1, "pagina": pagina,
                               "tipo": "freq",
                               "chave": f"{quesito}_{c['chave']}",
                               "x_mm": round(bx, 2), "y_mm": round(bcy, 2),
                               "r_mm": BALAO_RAIO})

    # PRESENCA no fim da coluna Kihon: balao + "Nome (Faixa)"
    pres_cx = QUESITO_X0 + 2.0
    pres_cy = y1 - PRES_BOT_OFFSET
    _balao(pdf, pres_cx, pres_cy, PRES_RAIO)
    rotulo_p = f"{aluno['nome']} ({aluno['faixa_atual'].capitalize()})"
    tam_p = 6.5
    while stringWidth(rotulo_p, "Helvetica", tam_p) > (QUESITO_LARG - 6.0) * MM and tam_p > 5.0:
        tam_p -= 0.5
    _texto(pdf, rotulo_p, pres_cx + PRES_RAIO + PRES_LABEL_GAP, pres_cy, tam_p)
    coords.append({"aluno": idx + 1, "pagina": pagina, "tipo": "presenca",
                   "x_mm": round(pres_cx, 2), "y_mm": round(pres_cy, 2),
                   "r_mm": PRES_RAIO})

    # Divisorias verticais
    for qi in range(1, 4):
        dx = QUESITO_X0 + qi * QUESITO_LARG
        pdf.line(dx * MM, _y(y1 - 2), dx * MM, _y(y0 + 2))


def _desenhar_rodape(pdf, alunos, coords, pagina):
    """3 caixas: faixa cinza compacta com o NOME do aluno (negrito) no topo
    de cada bloco e, logo abaixo, a faixa BOM!/A MELHORAR."""
    n = len(alunos)
    larg_total = A4_W_MM - 2 * MARGEM
    bloco_larg = (larg_total - (n - 1) * OBS_BLOCK_GAP) / n
    col_larg = bloco_larg / 2
    area_top = FOOTER_Y0 + 0.5
    area_bot = A4_H_MM - OBS_BOTTOM_MARGIN
    nome_band_h = 3.6                 # faixa do NOME (compacta)
    nome_y0 = area_top + 0.4
    band_y0 = nome_y0 + nome_band_h + 0.8   # faixa BOM!/A MELHORAR abaixo
    band_h = 3.0

    for i, aluno in enumerate(alunos):
        bx = MARGEM + i * (bloco_larg + OBS_BLOCK_GAP)
        # Caixa do bloco
        pdf.setStrokeColorRGB(0, 0, 0)
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(bx * MM, (A4_H_MM - area_bot) * MM,
                 bloco_larg * MM, (area_bot - area_top) * MM,
                 stroke=1, fill=0)
        # Faixa cinza do NOME do aluno (fundo destacado, fonte proporcional)
        pdf.setFillColorRGB(0.85, 0.85, 0.85)
        pdf.rect(bx * MM, (A4_H_MM - (nome_y0 + nome_band_h)) * MM,
                 bloco_larg * MM, nome_band_h * MM, stroke=0, fill=1)
        pdf.setFillColorRGB(0, 0, 0)
        _texto(pdf, aluno["nome"], bx + 2.0, nome_y0 + nome_band_h / 2,
               F_NOME_OBS, "Helvetica-Bold")
        # Faixa cinza BOM!/A MELHORAR
        pdf.setFillColorRGB(0.92, 0.92, 0.92)
        pdf.rect(bx * MM, (A4_H_MM - (band_y0 + band_h)) * MM,
                 bloco_larg * MM, band_h * MM, stroke=0, fill=1)
        pdf.setFillColorRGB(0, 0, 0)
        _texto_centrado(pdf, "BOM!", bx + col_larg / 2,
                        band_y0 + band_h / 2, F_OBS_TITULO, "Helvetica-Bold")
        _texto_centrado(pdf, "A MELHORAR", bx + col_larg + col_larg / 2,
                        band_y0 + band_h / 2, F_OBS_TITULO, "Helvetica-Bold")
        # Divisor vertical
        pdf.line((bx + col_larg) * MM, (A4_H_MM - area_bot) * MM,
                 (bx + col_larg) * MM, (A4_H_MM - (band_y0 + band_h)) * MM)
        # Itens 6+6
        for col, (titulo, dicio, prefixo) in enumerate(
                (("BOM!", observacoes.OBS_POSITIVAS, "obs_p"),
                 ("A MELHORAR", observacoes.OBS_MELHORAR, "obs_m"))):
            ox = bx + col * col_larg
            for oi, chave in enumerate(dicio):
                cy = band_y0 + band_h + 1.5 + oi * OBS_ITEM_ESPACO
                cx = ox + OBS_CHK_X_OFFSET
                _balao(pdf, cx, cy, OBS_RAIO)
                _texto(pdf, dicio[chave], cx + OBS_TEXTO_GAP, cy, F_OBS)
                coords.append({"aluno": i + 1, "pagina": pagina,
                               "tipo": f"{prefixo}{oi + 1}",
                               "x_mm": round(cx, 2), "y_mm": round(cy, 2),
                               "r_mm": OBS_RAIO})


# ---------------------------------------------------------------------------
# JSON de coordenadas
# ---------------------------------------------------------------------------
def _coords_por_aluno(coords, alunos_pag):
    saida = []
    for pos, (aluno, pagina) in enumerate(alunos_pag, start=1):
        itens = [c for c in coords if c["pagina"] == pagina and c["aluno"] == pos]
        pres = next((c for c in itens if c["tipo"] == "presenca"), None)
        freqs = {}
        for c in itens:
            if c["tipo"] == "freq":
                freqs.setdefault(c["chave"], []).append(
                    {"x_mm": c["x_mm"], "y_mm": c["y_mm"], "r_mm": c["r_mm"]})
        obs = {c["tipo"]: {"x_mm": c["x_mm"], "y_mm": c["y_mm"],
                           "r_mm": c["r_mm"]}
               for c in itens if c["tipo"].startswith("obs_")}
        saida.append({"id": aluno["id"],
                      "faixa": aluno["faixa_atual"].strip().lower(),
                      "pagina": pagina,
                      "presenca": pres if pres else {},
                      "frequencias": freqs,
                      "observacoes": obs})
    return saida


def _gerar_folhas(exame, alunos, avaliadores, dojo_id, matriz_faixa, saida):
    saida.mkdir(parents=True, exist_ok=True)
    dojo_nome = _nome_dojo(RAIZ, dojo_id)
    paginas = [alunos[k:k + ALUNOS_POR_FOLHA]
               for k in range(0, len(alunos), ALUNOS_POR_FOLHA)] or [[]]
    alunos_pag = [(a, p) for p, bloco in enumerate(paginas, start=1)
                  for a in bloco]
    gerados = []
    for av in avaliadores:
        pdf = pdfcanvas.Canvas(str(saida / f"folhas_{av['id']}.pdf"),
                               pagesize=landscape(A4))
        coords = []
        for pagina_i, bloco in enumerate(paginas, start=1):
            _desenhar_cabecalho(pdf, av, dojo_id, dojo_nome, exame)
            for i, aluno in enumerate(bloco):
                if i < len(QR_ALUNO_X):
                    _qr(pdf, f"KA|ALUNO={aluno['id']}"
                             f"|FAIXA={aluno['faixa_atual'].strip().lower()}",
                        QR_ALUNO_X[i], QR_ALUNO_Y, QR_ALUNO_TAM)
                _desenhar_linha(pdf, aluno, i, matriz_faixa, coords, pagina_i)
            _desenhar_rodape(pdf, bloco, coords, pagina_i)
            pdf.showPage()
        pdf.save()
        dados = {"versao": "v5.8-posicionado", "exame": exame,
                 "avaliador_id": av["id"], "dojo_id": dojo_id,
                 "pagina": "A4-paisagem (297x210mm)",
                 "alunos": _coords_por_aluno(coords, alunos_pag)}
        coords_path = saida / f"{exame}_{av['id']}_folha1_coordenadas.json"
        coords_path.write_text(json.dumps(dados, ensure_ascii=False,
                                          indent=2), encoding="utf-8")
        gerados.extend([saida / f"folhas_{av['id']}.pdf", coords_path])
    return gerados


def _validar(coords_path):
    dados = carregar_json(coords_path)
    erros = 0
    print(f"  geometria: HEADER_H={HEADER_H} LINHA_H={LINHA_H:.2f} "
          f"FOOTER_Y0={FOOTER_Y0}")
    for aluno in dados["alunos"]:
        p = aluno["presenca"]
        if not p or not (0 < p["x_mm"] < A4_W_MM and 0 < p["y_mm"] < A4_H_MM):
            erros += 1
            print(f"  [erro] presenca fora da pagina em {aluno['id']}: {p}")
        for chave, baloes in aluno["frequencias"].items():
            if len(baloes) != BALOES_POR_CRITERIO:
                erros += 1
                print(f"  [erro] {chave} tem {len(baloes)} baloes "
                      f"(esperado {BALOES_POR_CRITERIO})")
        if len(aluno["observacoes"]) != 12:
            erros += 1
            print(f"  [erro] observacoes em {aluno['id']}: "
                  f"{len(aluno['observacoes'])} (esperado 12)")
        if p:
            print(f"  {aluno['id']}: presenca y={p['y_mm']}  (linha {aluno['pagina']})")
    print(f"  alunos: {len(dados['alunos'])} | erros: {erros}")
    return erros


def main():
    ap = argparse.ArgumentParser(description="Pre-exame Karate-Ashi v5.8")
    ap.add_argument("--exame", required=True)
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--aluno", action="append", default=None)
    ap.add_argument("--avaliador", action="append", default=None)
    ap.add_argument("--dojo", default="D01")
    ap.add_argument("--saida", type=Path, default=RAIZ / "output" / "pre_exame")
    ap.add_argument("--validar", action="store_true")
    args = ap.parse_args()

    alunos = _carregar_alunos(args.csv, RAIZ)
    if args.aluno:
        alunos = [a for a in alunos if a["id"] in args.aluno]
    if not alunos:
        print("nenhum aluno selecionado (filtro vazio?)")
        return 2
    avaliadores = _carregar_avaliadores(RAIZ, args.avaliador)
    if not avaliadores:
        print("nenhum avaliador selecionado")
        return 2
    matriz = carregar_json(RAIZ / "config" / "faixas" / "branca.json")

    gerados = _gerar_folhas(args.exame, alunos, avaliadores, args.dojo,
                            matriz, args.saida)
    for p in gerados:
        print(f"  gerado: {p.relative_to(RAIZ)}")
    if args.validar:
        for p in gerados:
            if p.suffix == ".json":
                _validar(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())