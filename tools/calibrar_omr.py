"""tools/calibrar_omr.py — Mede densidade de pixels de folhas de teste.

Uso (job manual no GitHub Actions ou local):
    python tools/calibrar_omr.py --gabaritos data/gabaritos/teste/

Funcionalidade:
- Para cada imagem, aplica o pipeline OMR (correção de perspectiva);
- Para cada checkbox (coordenadas de config/coordenadas/.json), mede a
  densidade de pixels escuros;
- Agrupa por classe conhecida (vazio/suspeito/marcado) e exibe a média e o
  desvio padrão, para calibrar os limiares de omr_thresholds.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from core.omr_reader import carregar_json, detectar_e_corrigir

def medir_densidade(imagem_path: Path, coordenadas: dict) -> list[float]:
    img = cv2.imread(str(imagem_path))
    if img is None:
        raise ValueError(f"imagem não abriu: {imagem_path}")
    alinhada = detectar_e_corrigir(img)
    densidades: list[float] = []
    for quesito, criterios in coordenadas.items():
        if not criterios:
            continue
        for chave, roi in criterios.items():
            x, y, w, h = (int(v) for v in roi.values())
            celula = alinhada[y:y + h, x:x + w]
            cinza = cv2.cvtColor(celula, cv2.COLOR_BGR2GRAY)
            _, binaria = cv2.threshold(
                cinza, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            densidades.append(float(np.count_nonzero(binaria)) / binaria.size)
    return densidades

def main() -> int:
    ap = argparse.ArgumentParser(description="Calibração OMR Karate-Ashi")
    ap.add_argument("--gabaritos", type=Path, required=True,
                    help="pasta com as fotos/scan das folhas de teste")
    ap.add_argument("--faixa", default="branca")
    ap.add_argument("--config", type=Path, default=Path("config"))
    args = ap.parse_args()

    coordenadas = carregar_json(
        args.config / "coordenadas" / f"{args.faixa}.json")

    for img in sorted(args.gabaritos.glob("*.jpg")) + \
              sorted(args.gabaritos.glob("*.png")):
        densidades = medir_densidade(img, coordenadas)
        if densidades:
            print(f"{img.name}: média {np.mean(densidades):.3f} | "
                  f"min {min(densidades):.3f} | max {max(densidades):.3f}")
        else:
            print(f"{img.name}: nenhuma ROI com coordenadas preenchidas")

    print("Use os valores medidos para ajustar "
          "config/omr_thresholds.json (Fase 03).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())