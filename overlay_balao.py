"""overlay_balao.py — Recorta e salva um balão específico com overlay de medição.
Uso:
  python overlay_balao.py "<scan.png>" <avaliador> <aluno> <criterio> <n_balao>
  ex.: python overlay_balao.py "G:/.../img20261003_22490841.png" S02 W01 movimento_sem_carga 3
Salva: overlay_<scan>_<criterio>_b<n>.png (o balão ampliado + círculo + disco + tinta)
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, ".")
from core import omr_reader as omr  # noqa: E402


def main() -> None:
    if len(sys.argv) != 6:
        print(__doc__); sys.exit(1)
    scan, av, aluno, criterio, n = sys.argv[1:6]
    n = int(n)
    img = omr.carregar_imagem(Path(scan))
    a4 = omr.normalizar_a4(img)
    cinza = omr._cinza(a4)
    escala = omr.A4_W_PX / omr.A4_W_MM
    janela = omr.JANELA_MM * escala

    m = omr._QR_EXAME.search(omr._payload_por_prefixo(img, "AVALIADOR") or "")
    if not m:
        print("QR do exame não encontrado"); sys.exit(1)
    exame = m.group(3)
    coords = omr._carregar_coordenadas(Path("output/pre_exame"), exame, av)
    al = next((a for a in coords["alunos"] if a["id"] == aluno), None)
    if al is None:
        print(f"aluno {aluno} não encontrado"); sys.exit(1)
    chave = next((k for k in al["frequencias"] if criterio in k), None)
    if chave is None:
        print(f"critério {criterio} não encontrado"); sys.exit(1)
    b = al["frequencias"][chave][n - 1]

    cx, cy = b["x_mm"] * escala, b["y_mm"] * escala
    r = b["r_mm"] * escala
    anel = omr._achar_anel(cinza, cx, cy, r, janela)
    taxa, blob = omr._densidade_balao(cinza, b, escala, janela)

    # amplia a região do balão
    margem = int(r * 3)
    x0, y0 = max(0, int(cx - margem)), max(0, int(cy - margem))
    x1 = min(a4.shape[1], int(cx + margem))
    y1 = min(a4.shape[0], int(cy + margem))
    recorte = cv2.cvtColor(a4[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)

    # desenha círculo nominal (verde) e anel detectado (azul) e disco (vermelho)
    def _desenhar(c, cor, raio, esp=2):
        cv2.circle(recorte, (int(c[0]-x0), int(c[1]-y0)), int(raio), cor, esp)
    _desenhar((cx, cy), (0, 255, 0), r)                      # nominal
    if anel:
        _desenhar((anel[0], anel[1]), (255, 0, 0), anel[2])   # anel detectado
        _desenhar((anel[0], anel[1]), (255, 0, 255), anel[2]*0.80, 1)  # disco medido
    else:
        _desenhar((cx, cy), (255, 0, 255), r*0.80, 1)         # disco nominal

    saida = f"overlay_{Path(scan).stem}_{criterio}_b{n}.png"
    cv2.imwrite(saida, cv2.cvtColor(recorte, cv2.COLOR_RGB2BGR))
    print(f"salvo: {saida}")
    print(f"anel_detectado={anel is not None} taxa={taxa:.3f} blob={blob:.3f}")
    print(f"centro_nominal=({cx/escala:.2f},{cy/escala:.2f})mm "
          f"anel=({anel[0]/escala:.2f},{anel[1]/escala:.2f})mm" if anel else "")


if __name__ == "__main__":
    main()