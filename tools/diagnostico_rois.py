"""tools/diagnostico_rois.py — sobrepõe as ROIs (critérios e observações) na
folha alinhada.

Serve para descobrir DESLOCAMENTO de ROI: se as caixas de observação não caem
sobre os quadradinhos impressos, a leitura sai trocada (lê o vizinho), mesmo
com a folha bem alinhada.

Uso:
    python tools/diagnostico_rois.py --foto output/fotos/IMG_9786.JPEG \
        --faixa branca --config config --out output/diagnostico
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402

from core import omr_reader  # noqa: E402

CORES = {
    "vazio": (60, 180, 75),
    "suspeito": (0, 200, 255),
    "marcado": (255, 80, 0),
}

def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnóstico de ROIs (Karate-Ashi)")
    ap.add_argument("--foto", required=True, type=Path)
    ap.add_argument("--faixa", required=True)
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--out", type=Path, default=Path("output/diagnostico"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    limiares = omr_reader.carregar_json(args.config / "omr_thresholds.json")
    coords = omr_reader.carregar_json(
        args.config / "coordenadas" / f"{args.faixa}.json")

    imagem = cv2.imread(str(args.foto))
    if imagem is None:
        print(f"[ERRO] não abriu {args.foto}")
        return 2
    alinhada = omr_reader.detectar_e_corrigir(imagem)
    h, w = alinhada.shape[:2]
    overlay = alinhada.copy()

    # --- critérios (vermelho fino) ---
    for quesito in omr_reader.QUESITOS:
        for chave, roi_mm in coords.get(quesito, {}).items():
            px = omr_reader.roi_mm_para_px(roi_mm, w, h)
            cv2.rectangle(overlay, (px["x"], px["y"]),
                          (px["x"] + px["w"], px["y"] + px["h"]),
                          (0, 0, 255), 1)

    # --- observações (cor = classificação) ---
    print(f"Folha: {args.foto.name} | faixa {args.faixa} | alinhada {w}x{h}px")
    for chave, roi_mm in coords.get("observacoes", {}).items():
        px = omr_reader.roi_mm_para_px(roi_mm, w, h)
        roi = alinhada[px["y"]:px["y"] + px["h"], px["x"]:px["x"] + px["w"]]
        if roi.size == 0:
            print(f"{chave}: ROI FORA DA IMAGEM @ {px}")
            continue
        classe = omr_reader.classificar_checkbox(roi, limiares)
        cor = CORES[classe]
        cv2.rectangle(overlay, (px["x"], px["y"]),
                      (px["x"] + px["w"], px["y"] + px["h"]), cor, 3)
        cv2.putText(overlay, chave.replace("obs_", ""),
                    (px["x"], max(12, px["y"] - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor, 2)
        print(f"{chave}: {classe:8s} @ ({px['x']},{px['y']}) {px['w']}x{px['h']}")

    saida = args.out / f"{args.foto.stem}_rois.png"
    cv2.imwrite(str(saida), overlay)
    print(f"\nSalvo: {saida}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())