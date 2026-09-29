#!/usr/bin/env python3
"""tools/diagnostico_qr.py — Diagnóstico de decodificação QR nos scans.

Diz, por arquivo: dimensões (flatbed A4 300-400dpi vs foto), se o QR do
exame decodifica, e quais QRs de aluno (11mm) cada decoder consegue ler
(zxing-cpp e pyzbar, com upscaling e pré-processamento).

Uso:
    python tools/diagnostico_qr.py --pasta "G:\\Meu Drive\\documentos\\KarateAshi_Exames\\scans"
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import cv2
import numpy as np

EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".pdf"}


def _cinza(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _carregar(caminho: Path) -> np.ndarray:
    if caminho.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium
        pagina = pdfium.PdfDocument(str(caminho))[0]
        bmp = pagina.render(scale=400 / 72)
        arr = np.frombuffer(bmp.to_bits(), dtype=np.uint8).reshape(
            bmp.height, bmp.width, bmp.n_channels)
        return arr[..., :3][:, :, ::-1]
    img = cv2.imread(str(caminho), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"nao foi possivel ler: {caminho}")
    return img


def _zxing(imagem: np.ndarray) -> list[tuple[str, str]]:
    try:
        from zxingcpp import read_barcodes
    except ImportError:
        return []
    cinza = _cinza(imagem)
    h, w = cinza.shape[:2]
    saida: list[tuple[str, str]] = []
    for fator in (1, 2, 3):
        base = cinza if fator == 1 else cv2.resize(
            cinza, (w * fator, h * fator), interpolation=cv2.INTER_CUBIC)
        try:
            for bar in read_barcodes(base):
                if bar.format.name == "QRCode":
                    saida.append((f"zx-{fator}x", bar.text))
        except Exception:  # noqa: BLE001
            continue
    return saida


def _pyzbar(imagem: np.ndarray) -> list[tuple[str, str]]:
    try:
        from pyzbar import pyzbar
    except ImportError:
        return []
    cinza = _cinza(imagem)
    h, w = cinza.shape[:2]
    saida: list[tuple[str, str]] = []
    _, otsu = cv2.threshold(cinza, 0, 255,
                            cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adapt = cv2.adaptiveThreshold(cinza, 255,
                                  cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY, 51, 15)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cinza)
    variantes = [
        ("pyb-orig", cinza, 1.0),
        ("pyb-2x", cv2.resize(cinza, (w * 2, h * 2),
                              interpolation=cv2.INTER_CUBIC), 2.0),
        ("pyb-3x", cv2.resize(cinza, (w * 3, h * 3),
                              interpolation=cv2.INTER_CUBIC), 3.0),
        ("pyb-otsu", otsu, 1.0),
        ("pyb-adapt", adapt, 1.0),
        ("pyb-clahe", clahe, 1.0),
    ]
    for nome, img_v, fator in variantes:
        for qr in pyzbar.decode(img_v):
            saida.append((nome, qr.data.decode("utf-8", "replace")))
    return saida


def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnóstico QR dos scans")
    ap.add_argument("--pasta", type=Path, required=True,
                    help="pasta com os scans")
    args = ap.parse_args()

    arquivos = sorted(f for f in args.pasta.rglob("*")
                      if f.is_file() and f.suffix.casefold() in EXT)
    if not arquivos:
        print(f"[AVISO] nenhum arquivo em {args.pasta}")
        return 3

    try:
        import zxingcpp  # noqa: F401
        print("zxing-cpp: INSTALADO (recomendado)")
    except ImportError:
        print("zxing-cpp: NAO instalado (pip install zxing-cpp)")

    print(f"\n{'arquivo':<26} {'dims':<14} tipo            exame | qrs_aluno")
    for f in arquivos:
        try:
            img = _carregar(f)
        except Exception as exc:
            print(f"{f.name[:26]:<26} ERRO: {exc}")
            continue
        h, w = img.shape[:2]
        razao = w / h if h else 0.0
        if 1.20 <= razao <= 1.65:
            tipo = "A4-ish (flatbed/foto paisagem)"
        else:
            tipo = f"OUTRA razao {razao:.2f} (foto?)"
        qrs = _zxing(img) + _pyzbar(img)
        exame = [q for q in qrs if "AVALIADOR=" in q[1]]
        alunos = [q for q in qrs if "ALUNO=" in q[1]]
        seen = set()
        mal = []
        for nome, texto in alunos:
            chave = texto
            if chave in seen:
                continue
            seen.add(chave)
            mal.append(f"{nome}:{texto.split('ALUNO=')[1].split('|')[0]}")
        print(f"{f.name[:26]:<26} {w}x{h:<8} {tipo:<18} "
              f"{'SIM' if exame else 'nao':<5} | [{len(mal)}] {'; '.join(mal) or '-'}")
        for _, texto in exame:
            print(f"    exame payload: {texto}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())