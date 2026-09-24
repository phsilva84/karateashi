#!/usr/bin/env python3
"""tools/diagnosticar_texto.py — Mede posicao dos TEXTOS vs bordas das colunas.

Renderiza o PDF da folha e sobrepoe a grade de geometria que o pre_exame
usa: bordas das linhas, faixa de titulos, baselines dos criterios,
divisorias verticais e, no rodape, as caixas de observacao, o baseline do
NOME do aluno e a faixa BOM!/A MELHORAR.

Cores:
  verde   = borda da linha / caixa de observacao
  azul    = faixa de titulos (KIHON.. / BOM!..)
  ciano   = baseline do texto de cada criterio
  magenta = divisoria vertical entre colunas
  vermelho= baseline do NOME do aluno no rodape

Uso:
  python tools/diagnosticar_texto.py
  python tools/diagnosticar_texto.py --pdf output/pre_exame/folhas_S01.pdf
Saida: output/diagnostico/<folha>_texto.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

A4_W_MM, A4_H_MM = 297.0, 210.0
MM_PX = 300 / 25.4          # 300 dpi -> px por mm

# Geometria do pre_exame v5.8 (fonte unica — manter em sincronia)
HEADER_H = 14.0
FOOTER_H = 38.0
LINHA_H = (A4_H_MM - HEADER_H - FOOTER_H) / 3.0
FOOTER_Y0 = HEADER_H + 3 * LINHA_H
MARGEM = 10.0
QUESITO_X0 = MARGEM
QUESITO_LARG = (A4_W_MM - 2 * MARGEM) / 4.0
QUESITO_TITLE_Y0 = 1.2
QUESITO_TITLE_H = 3.0
CRIT_Y0 = 6.0
CRIT_ESPACO = 4.9
N_CRIT_MAX = 8
OBS_BOTTOM_MARGIN = 5.0
OBS_AREA_TOP = FOOTER_Y0 + 0.5
OBS_AREA_BOT = A4_H_MM - OBS_BOTTOM_MARGIN
OBS_NOME_BAND_H = 3.6
OBS_NOME_Y0 = OBS_AREA_TOP + 0.4
OBS_BAND_Y0 = OBS_NOME_Y0 + OBS_NOME_BAND_H + 0.8
OBS_BAND_H = 3.0
OBS_BLOCK_GAP = 2.0


def _px(x_mm: float) -> int:
    return int(round(x_mm * MM_PX))


def _renderizar(pdf_path: Path) -> np.ndarray:
    """Renderiza a 1a pagina do PDF a 300 dpi e devolve como BGR numpy."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf_path))
    bmp = doc[0].render(scale=300 / 72)
    pil = bmp.to_pil()                       # PdfBitmap -> PIL
    arr = np.array(pil.convert("RGB"))       # HxWx3 RGB
    return arr[:, :, ::-1].copy()            # RGB -> BGR (cv2)


def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnostico de texto vs bordas")
    ap.add_argument("--pdf", type=Path,
                    default=RAIZ / "output" / "pre_exame" / "folhas_S01.pdf")
    ap.add_argument("--saida", type=Path,
                    default=RAIZ / "output" / "diagnostico")
    args = ap.parse_args()

    if not args.pdf.exists():
        print(f"[ERRO] PDF nao encontrado: {args.pdf}")
        return 2

    vis = _renderizar(args.pdf)

    # --- Linhas de aluno (grade) ---
    for i in range(3):
        y0 = HEADER_H + i * LINHA_H
        y1 = y0 + LINHA_H
        # Borda da linha (verde)
        cv2.rectangle(vis, (_px(MARGEM), _px(y0)),
                      (_px(MARGEM + 4 * QUESITO_LARG), _px(y1)),
                      (0, 255, 0), 2)
        # Faixa de titulos (azul)
        cv2.rectangle(vis, (_px(QUESITO_X0), _px(y0 + QUESITO_TITLE_Y0)),
                      (_px(QUESITO_X0 + 4 * QUESITO_LARG),
                       _px(y0 + QUESITO_TITLE_Y0 + QUESITO_TITLE_H)),
                      (255, 0, 0), 2)
        # Baselines dos criterios (ciano)
        for k in range(N_CRIT_MAX):
            by = y0 + CRIT_Y0 + k * CRIT_ESPACO
            if by > y1 - 2:
                break
            cv2.line(vis, (_px(QUESITO_X0), _px(by)),
                     (_px(QUESITO_X0 + 4 * QUESITO_LARG), _px(by)),
                     (255, 255, 0), 1)
        # Divisorias verticais (magenta)
        for qi in range(1, 4):
            dx = QUESITO_X0 + qi * QUESITO_LARG
            cv2.line(vis, (_px(dx), _px(y0 + 2)), (_px(dx), _px(y1 - 2)),
                     (255, 0, 255), 2)

    # --- Rodape de observacoes ---
    larg_total = A4_W_MM - 2 * MARGEM
    bloco_larg = (larg_total - 2 * OBS_BLOCK_GAP) / 3
    for i in range(3):
        bx = MARGEM + i * (bloco_larg + OBS_BLOCK_GAP)
        # Caixa (verde)
        cv2.rectangle(vis, (_px(bx), _px(OBS_AREA_TOP)),
                      (_px(bx + bloco_larg), _px(OBS_AREA_BOT)),
                      (0, 255, 0), 2)
        # Faixa do NOME do aluno (vermelho)
        cv2.rectangle(vis, (_px(bx), _px(OBS_NOME_Y0)),
                      (_px(bx + bloco_larg),
                       _px(OBS_NOME_Y0 + OBS_NOME_BAND_H)),
                      (0, 0, 255), 2)
        # Faixa BOM!/A MELHORAR (azul)
        cv2.rectangle(vis, (_px(bx), _px(OBS_BAND_Y0)),
                      (_px(bx + bloco_larg), _px(OBS_BAND_Y0 + OBS_BAND_H)),
                      (255, 0, 0), 2)
        # Divisor central (magenta)
        cv2.line(vis, (_px(bx + bloco_larg / 2), _px(OBS_AREA_TOP)),
                 (_px(bx + bloco_larg / 2), _px(OBS_AREA_BOT)),
                 (255, 0, 255), 2)

    args.saida.mkdir(parents=True, exist_ok=True)
    saida = (args.saida / f"{args.pdf.stem}_texto.png").resolve()
    cv2.imwrite(str(saida), vis)
    print(f"  grade de texto sobreposta: {saida.relative_to(RAIZ)}")
    print("  verde=borda | azul=faixa titulos | ciano=baseline criterio | "
          "magenta=divisoria | vermelho=faixa NOME aluno (rodape)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())