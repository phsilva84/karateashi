"""tools/diagnosticar_scan.py — Diagnóstico geométrico do scan (v3.8).

Imprime os fatos do scan (dimensões, folha detectada, rotação, QRs) e
salva a imagem normalizada para conferência visual.

Uso:
    python tools/diagnosticar_scan.py --imagem output/scans/img20260922_18093327.png
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

from core import omr_reader  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnóstico do scan")
    ap.add_argument("--imagem", type=Path, required=True)
    args = ap.parse_args()

    img = cv2.imread(str(args.imagem))
    if img is None:
        print(f"[ERRO] não abriu {args.imagem}")
        return 2
    h, w = img.shape[:2]
    print(f"Imagem: {w}x{h} px | proporção {w / h:.3f} "
          f"({'paisagem' if w >= h else 'RETRATO'})")

    # 1. Folha detectada por contorno
    quad = omr_reader._detectar_quad(img)
    if quad is None:
        print("Folha: NÃO detectada por contorno")
    else:
        ordem = omr_reader._ordenar_cantos(quad)
        largura = max(float(np.linalg.norm(ordem[1] - ordem[0])),
                      float(np.linalg.norm(ordem[2] - ordem[3])))
        altura = max(float(np.linalg.norm(ordem[3] - ordem[0])),
                     float(np.linalg.norm(ordem[2] - ordem[1])))
        print(f"Folha: detectada | {largura:.0f}x{altura:.0f} px | "
              f"proporção {largura / altura:.3f} "
              f"({'paisagem' if largura >= altura else 'RETRATO'})")
        print(f"  cantos: TL={ordem[0].round(0)} TR={ordem[1].round(0)} "
              f"BR={ordem[2].round(0)} BL={ordem[3].round(0)}")

    # 2. QR do cabeçalho (ordem nativa do OpenCV)
    local = omr_reader.localizar_qr_opencv(img)
    if local is None:
        print("QR cabeçalho: NÃO detectado")
    else:
        pontos, dados = local
        centro = pontos.mean(axis=0)
        print(f"QR cabeçalho: {dados}")
        print("  cantos (ordem nativa TL,TR,BR,BL):")
        for nome, p in zip(["TL", "TR", "BR", "BL"], pontos):
            print(f"    {nome}=({p[0]:.0f},{p[1]:.0f})")
        print(f"  centro: ({centro[0]:.0f}, {centro[1]:.0f}) px")
        if quad is not None:
            ordem = omr_reader._ordenar_cantos(quad)
            dists = [float(np.linalg.norm(centro - c)) for c in ordem]
            idx = int(np.argmin(dists))
            print(f"  canto mais próximo: {['TL', 'TR', 'BR', 'BL'][idx]} "
                  f"(dist {dists[idx]:.0f}px)")

    # 3. Resultado da normalização
    try:
        alinhada = omr_reader.detectar_e_corrigir(img)
        ah, aw = alinhada.shape[:2]
        print(f"\nNormalizada: {aw}x{ah} px (esperado 3508x2480)")
        payload = omr_reader.decodificar_qr_com_prefixo(alinhada, "AVALIADOR")
        print(f"QR cabeçalho após normalizar: {payload or 'NÃO lido'}")
        # Posição do QR no normalizado (esperado ~centro (3307, 177))
        local2 = omr_reader.localizar_qr_opencv(alinhada)
        if local2 is not None:
            p2, d2 = local2
            c2 = p2.mean(axis=0)
            print(f"  posição no normalizado: centro ({c2[0]:.0f},{c2[1]:.0f}) px "
                  f"(esperado ~(3307,177))")
        px_mm_x = aw / 297.0
        px_mm_y = ah / 210.0
        for j in range(3):
            box = {"x": omr_reader._QR_ALUNO_CAB_X_MM[j],
                   "y": omr_reader._QR_ALUNO_CAB_Y_MM,
                   "w": omr_reader._QR_ALUNO_CAB_TAM_MM,
                   "h": omr_reader._QR_ALUNO_CAB_TAM_MM}
            payload_aluno = omr_reader._ler_qr_em_mm(
                alinhada, box, px_mm_x, px_mm_y)
            print(f"QR aluno {j + 1}: {payload_aluno or 'NÃO lido'}")
        saida = RAIZ / "output" / "diagnostico_scan_normalizado.png"
        saida.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(saida), alinhada)
        print(f"Salvo: {saida}")
    except Exception as exc:  # noqa: BLE001
        print(f"\n[ERRO] normalização: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())