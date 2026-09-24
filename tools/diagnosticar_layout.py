#!/usr/bin/env python3
"""tools/diagnosticar_layout.py — MEDE o deslocamento dos balões (scan vs JSON).

O problema NAO e de texto: e de posicao dos circulos no diagnostico.

Para cada scan em --scan, normaliza para A4 e, para cada balao do JSON de
coordenadas:
- acha o ANEL REAL impresso (mesma busca local do omr_reader, +-3mm);
- desenha o anel real em VERDE grosso e a posicao esperada em CIANO fino;
- liga os dois com seta VERMELHA quando o desvio > 0.5mm;
- acumula os desvios e imprime OFFSET medio (dx, dy em mm) por linha de
  aluno e o DRIFT (1a -> ultima linha) — o numero exato para calibrar.

Interpretacao da saida:
- OFFSET constante (dx/dy parecidos em todas as linhas) -> erro de ORIGEM:
  ajustar constantes do pre_exame (QUESITO_X0 / QUESITO_TITLE_Y0 / CRIT_Y0).
- DRIFT (dx/dy cresce da 1a para a ultima linha) -> erro de ESCALA no
  normalizar_a4 / render: corrigir a razao px/mm, NAO a folha.

Uso:
  python tools/diagnosticar_layout.py
Saida: output/diagnostico/<scan>_layout.png + relatorio numerico no console.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core import omr_reader  # noqa: E402

SCAN_PADRAO = Path("output/scans")
SAIDA_PADRAO = Path("output/diagnostico")
LIMIAR_SETA_MM = 0.5


def _auto_coords() -> Path | None:
    """Auto-detecta o JSON de coordenadas mais recente de output/pre_exame."""
    pasta = RAIZ / "output" / "pre_exame"
    candidatos = sorted(pasta.glob("*_coordenadas.json"))
    return candidatos[-1] if candidatos else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnostico de layout OMR v2")
    ap.add_argument("--scan", type=Path, default=SCAN_PADRAO,
                    help="pasta com os scans das folhas")
    ap.add_argument("--coords", type=Path, default=None,
                    help="JSON de coordenadas (auto-detecta se omitido)")
    ap.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    args = ap.parse_args()

    coords_path = args.coords or _auto_coords()
    if coords_path is None or not coords_path.exists():
        print("[ERRO] JSON de coordenadas nao encontrado. Gere a folha com "
              "pre_exame antes, ou passe --coords.")
        return 2
    coords = json.loads(coords_path.read_text(encoding="utf-8"))
    print(f"  coords: {coords_path.relative_to(RAIZ)} "
          f"(versao {coords.get('versao')})")

    scans = sorted(args.scan.glob("*.png")) + sorted(args.scan.glob("*.jpg"))
    if not scans:
        print(f"[ERRO] nenhum scan em {args.scan}")
        return 3

    args.saida.mkdir(parents=True, exist_ok=True)
    escala = omr_reader.A4_W_PX / omr_reader.A4_W_MM   # ~11.81 px/mm
    janela_px = omr_reader.JANELA_MM * escala

    for scan in scans:
        img = cv2.imread(str(scan))
        if img is None:
            print(f"[ERRO] nao abriu: {scan.name}")
            continue
        h0, w0 = img.shape[:2]
        a4 = omr_reader.normalizar_a4(img)
        h1, w1 = a4.shape[:2]
        cinza = omr_reader._cinza(a4)
        vis = a4.copy()

        print(f"\n== {scan.name} ==  entrada {w0}x{h0} -> normalizada {w1}x{h1}")
        print(f"   razao real {w1/297.0:.3f} px/mm (esperado {escala:.3f}) | "
              f"janela de busca +-{omr_reader.JANELA_MM}mm = {janela_px:.0f}px")

        desvios: dict[int, list[tuple[float, float]]] = {}
        for aluno in coords.get("alunos", []):
            linha = aluno.get("pagina", 1)
            itens = []
            p = aluno.get("presenca") or {}
            if p:
                itens.append(("presenca", p))
            for chave, lista in (aluno.get("frequencias") or {}).items():
                itens.extend((chave, b) for b in lista)
            for chave, b in (aluno.get("observacoes") or {}).items():
                itens.append((chave, b))

            for rotulo, b in itens:
                ex = b["x_mm"] * escala
                ey = b["y_mm"] * escala
                r = b["r_mm"] * escala
                anel = omr_reader._achar_anel(cinza, ex, ey, r, janela_px)
                if anel is None:
                    cv2.circle(vis, (int(ex), int(ey)), max(int(r), 3),
                               (0, 0, 255), -1)   # vermelho cheio: nao achou
                    continue
                ax, ay, ar = anel
                dx = ax - ex
                dy = ay - ey
                desvios.setdefault(linha, []).append((dx / escala, dy / escala))

                cv2.circle(vis, (int(ax), int(ay)), max(int(ar), 3),
                           (0, 220, 0), 3)          # anel real (leitura)
                cv2.circle(vis, (int(ex), int(ey)), max(int(r), 3),
                           (255, 255, 0), 1)         # posicao esperada (JSON)
                dist_mm = np.hypot(dx, dy) / escala
                if dist_mm > LIMIAR_SETA_MM:
                    cv2.arrowedLine(vis, (int(ex), int(ey)),
                                    (int(ax), int(ay)), (0, 0, 255), 2,
                                    tipLength=0.35)

        todas = [d for rows in desvios.values() for d in rows]
        if todas:
            dxs = [d[0] for d in todas]
            dys = [d[1] for d in todas]
            print(f"   baloes com anel: {len(todas)}")
            print(f"   OFFSET MEDIO: dx={np.mean(dxs):+.2f}mm  "
                  f"dy={np.mean(dys):+.2f}mm")
            print(f"   desvio max: {max(np.hypot(dx, dy) for dx, dy in todas):.2f}mm")
            for linha in sorted(desvios):
                d = desvios[linha]
                print(f"   linha {linha}: n={len(d)}  "
                      f"dx={np.mean([x for x, _ in d]):+.2f}mm  "
                      f"dy={np.mean([y for _, y in d]):+.2f}mm")
            linhas = sorted(desvios)
            if len(linhas) >= 2:
                dy1 = np.mean([y for _, y in desvios[linhas[0]]])
                dyN = np.mean([y for _, y in desvios[linhas[-1]]])
                dx1 = np.mean([x for x, _ in desvios[linhas[0]]])
                dxN = np.mean([x for x, _ in desvios[linhas[-1]]])
                print(f"   DRIFT 1a->ult linha: dy {dy1:+.2f} -> {dyN:+.2f}mm "
                      f"({dyN-dy1:+.2f}mm) | dx {dx1:+.2f} -> {dxN:+.2f}mm "
                      f"({dxN-dx1:+.2f}mm)")
        else:
            print("   nenhum balao com anel encontrado (tudo vermelho)?")

        saida = (args.saida / f"{scan.stem}_layout.png").resolve()
        cv2.imwrite(str(saida), vis)
        print(f"   imagem: {saida.relative_to(RAIZ)}")

    print("\nVerde grosso = anel real (onde o leitor mediu).")
    print("Ciano fino = posicao esperada no JSON.")
    print("Seta vermelha = desvio > 0.5mm (direcao/sentido do ajuste).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())