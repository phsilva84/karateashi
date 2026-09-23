"""gerar_diagnostico_visual.py — Validação visual das marcações reais.

Para cada folha em output/scans, gera um PNG de diagnóstico com:
  1. a resolução e o DPI estimado da imagem;
  2. o resultado da detecção de contorno da folha (a etapa que falhou na 4ª);
  3. os retângulos de leitura (ROIs) desenhados sobre a imagem.

Assim você vê COM OS OLHOS se as caixas de leitura estão exatamente
sobre as marcações que você fez à mão.

Uso: python tools/gerar_diagnostico_visual.py
Saída: output/diagnostico/<folha>_rois.png (uma imagem por folha)
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

A4_W_MM, A4_H_MM = 210.0, 297.0          # tamanho do papel em milímetros
ENTRADA = Path("output/scans")           # pasta com as folhas digitalizadas
SAIDA = Path("output/diagnostico")       # pasta onde os PNGs serão salvos
COORD = RAIZ / "config" / "coordenadas" / "branca.json"


def mm_para_px(x_mm, y_mm, dpi):
    """Converte uma posição em milímetros para pixels, usando o DPI real."""
    return int(x_mm * dpi / 25.4), int(y_mm * dpi / 25.4)


def detectar_contorno_folha(img_bgr):
    """Tenta achar o contorno da folha (mesma lógica do alinhamento OMR).

    Se não achar um retângulo grande o suficiente, devolve None — que é
    exatamente o erro "nenhum contorno de folha encontrado".
    """
    cinza = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    _, binaria = cv2.threshold(cinza, 0, 255,
                               cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    maior = max(contornos, key=cv2.contourArea, default=None)
    # A folha deve ocupar pelo menos 30% da imagem
    if maior is None or cv2.contourArea(maior) < 0.3 * img_bgr.shape[0] * img_bgr.shape[1]:
        return None
    peri = cv2.arcLength(maior, True)
    approx = cv2.approxPolyDP(maior, 0.02 * peri, True)
    return approx


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    coords = json.loads(COORD.read_text(encoding="utf-8"))

    # 1. Coleta todas as ROIs (quesitos + observações) do arquivo de coordenadas
    rois = []  # (rótulo, x_mm, y_mm, w_mm, h_mm)
    for bloco_nome, bloco in coords.items():
        if not isinstance(bloco, dict):
            continue
        for nome, box in bloco.items():
            if isinstance(box, dict) and {"x", "y", "w", "h"} <= set(box):
                rois.append((f"{bloco_nome}.{nome}",
                             box["x"], box["y"], box["w"], box["h"]))

    imagens = sorted(ENTRADA.glob("*.png")) + sorted(ENTRADA.glob("*.jpg"))
    if not imagens:
        print(f"Nenhuma imagem em {ENTRADA}")
        return 1

    for caminho in imagens:
        img_bgr = cv2.imread(str(caminho))
        if img_bgr is None:
            print(f"[ERRO] não conseguiu abrir {caminho.name}")
            continue

        altura, largura = img_bgr.shape[:2]
        dpi_x = largura / (A4_W_MM / 25.4)
        dpi_y = altura / (A4_H_MM / 25.4)
        print(f"\n=== {caminho.name} | {largura}x{altura} | ~{dpi_x:.0f} DPI ===")

        # 2. Detecção de contorno — diagnostica a folha que falhou
        contorno = detectar_contorno_folha(img_bgr)
        if contorno is None:
            print("  [FALHA] nenhum contorno de folha encontrado"
                  " (é a que falhou no ingest?)")
        else:
            print(f"  contorno da folha OK ({len(contorno)} pontos)")

        # 3. Desenha as ROIs sobre a imagem (retângulos verdes)
        vis = img_bgr.copy()
        for rotulo, x_mm, y_mm, w_mm, h_mm in rois:
            x, y = mm_para_px(x_mm, y_mm, dpi_x)
            w, h = mm_para_px(w_mm, h_mm, dpi_x)
            cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 220, 0), 2)

        saida = SAIDA / f"{caminho.stem}_rois.png"
        cv2.imwrite(str(saida), vis)
        print(f"  diagnóstico salvo: {saida}")

    print(f"\nDiagnóstico visual completo em: {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())