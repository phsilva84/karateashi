"""tools/diagnostico_foto.py — raio-x de UMA foto de folha.

Salva as binarizações, os contornos grandes e o resultado do alinhamento,
e testa o QR em cada etapa. Serve para entender POR QUE uma foto falha
no OMR (folha não detectada / QR não lido).

Uso:
    python tools/diagnostico_foto.py --foto output/fotos/IMG_9786.JPEG \
        --out output/diagnostico
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Bootstrap: garante que o pacote 'core' (raiz do projeto) seja importável
# mesmo quando o script é chamado como `python tools/diagnostico_foto.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402

from core import omr_reader  # noqa: E402

def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnóstico de foto de folha (Karate-Ashi)")
    ap.add_argument("--foto", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("output/diagnostico"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    imagem = cv2.imread(str(args.foto))
    if imagem is None:
        print(f"[ERRO] não abriu {args.foto}")
        return 2
    h, w = imagem.shape[:2]
    print(f"Foto: {args.foto.name} | {w}x{h}px")

    # 1. QR na foto ORIGINAL (sem nenhum processamento)
    print(f"QR (original): {omr_reader.decodificar_qr(imagem) or 'NÃO LIDO'}")

    # 2. Alinhamento (detecção + warp)
    try:
        alinhada = omr_reader.detectar_e_corrigir(imagem)
        cv2.imwrite(str(args.out / f"{args.foto.stem}_alinhada.png"), alinhada)
        print(f"Alinhada: {alinhada.shape[1]}x{alinhada.shape[0]}px")
        print(f"QR (alinhada): {omr_reader.decodificar_qr(alinhada) or 'NÃO LIDO'}")
    except Exception as exc:  # noqa: BLE001
        print(f"[FALHA] alinhamento: {exc}")

    # 3. Binarizações + contornos grandes (para ver o que o detector enxerga)
    escala = min(1.0, 1600 / max(h, w))
    pequena = (cv2.resize(imagem, None, fx=escala, fy=escala,
                          interpolation=cv2.INTER_AREA)
               if escala < 1 else imagem)
    cinza = cv2.cvtColor(pequena, cv2.COLOR_BGR2GRAY)
    for i, binaria in enumerate(omr_reader.binarizacoes(cinza)):
        cv2.imwrite(str(args.out / f"{args.foto.stem}_bin{i}.png"), binaria)
        contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        grandes = [c for c in contornos
                   if cv2.contourArea(c) >= 0.05 * binaria.size]
        print(f"bin{i}: {len(contornos)} contornos, {len(grandes)} grandes")
        overlay = pequena.copy()
        cv2.drawContours(overlay, grandes, -1, (0, 0, 255), 3)
        cv2.imwrite(str(args.out / f"{args.foto.stem}_cont{i}.png"), overlay)
        # 4. Âncora QR + fiduciais (fallback p/ folha cortada)
    local = omr_reader.localizar_qr(imagem)
    if local is not None:
        pontos_qr, dados = local
        print(f"QR (pyzbar): {dados}")
        print(f"QR polígono: {pontos_qr.astype(int).tolist()}")
        try:
            alinhada_ancora = omr_reader.warp_pela_ancora(imagem, pontos_qr)
            cv2.imwrite(str(args.out / f"{args.foto.stem}_ancora.png"),
                        alinhada_ancora)
            print(f"Âncora: {alinhada_ancora.shape[1]}x{alinhada_ancora.shape[0]}px | "
                  f"preta: {omr_reader._fracao_preta(alinhada_ancora):.1%}")
        except Exception as exc:  # noqa: BLE001
            print(f"[FALHA] âncora: {exc}")
    else:
        print("QR (pyzbar): NÃO LOCALIZADO")
        
    print(f"\nImagens salvas em {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())