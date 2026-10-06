"""tools/diag_qr_pos.py — centro real (mm) dos QRs de aluno vs POS_QRS_ALUNO_MM.
  python tools/diag_qr_pos.py <pasta_scans>
Se o desvio (dx, dy) for ~CONSTANTE entre scans/avaliadores, o problema são as
constantes nominais (viés de projeto). Se variar, é deslocamento físico do papel.
"""
from __future__ import annotations
import statistics as st
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import omr_reader as R  # noqa: E402

def main(pasta: str) -> None:
    esc = R.A4_W_PX / R.A4_W_MM
    todos = []
    for p in sorted(Path(pasta).glob("*.png")):
        img = R.carregar_imagem(p)
        a4 = R.normalizar_a4(img)
        h, w = img.shape[:2]
        devs = []
        for texto, (x, y, ww, hh) in R._ler_qrs(a4):
            if "ALUNO=" not in texto:
                continue
            cx, cy = (x + ww / 2) / esc, (y + hh / 2) / esc
            ex, ey = min(R.POS_QRS_ALUNO_MM, key=lambda q: abs(q[0] - cx))
            devs.append((cx - ex, cy - ey, ww / esc, y / esc))
        if not devs:
            print(f"{p.name}: nenhum QR de aluno lido"); continue
        dx, dy = (st.median(d[i] for d in devs) for i in (0, 1))
        todos.append((dx, dy))
        print(f"{p.name}: aspecto={w/h:.4f} n_qr={len(devs)} "
              f"dx={dx:+.2f} dy={dy:+.2f} lado={devs[0][2]:.1f}mm topo={devs[0][3]:.1f}mm")
    if len(todos) > 1:
        for i, n in enumerate(("dx", "dy")):
            v = [t[i] for t in todos]
            print(f"{n}: mediana={st.median(v):+.2f} amplitude={max(v)-min(v):.2f} mm")

if __name__ == "__main__":
    main(sys.argv[1])