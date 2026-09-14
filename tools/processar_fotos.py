"""tools/processar_fotos.py — processa uma pasta de fotos das folhas.

Para cada imagem: alinha, lê o QR (faixa/aluno/avaliador), roda o pipeline
completo do OMR e grava o JSON intermediário. Imprime um resumo por folha.

Uso:
    python tools/processar_fotos.py --fotos output/fotos --config config \
        --out output/json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Bootstrap: garante que o pacote 'core' (raiz do projeto) seja importável
# mesmo quando o script é chamado como `python tools/processar_fotos.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402  (import após o bootstrap do sys.path)

from core.omr_reader import (  # noqa: E402
    decodificar_qr,
    detectar_e_corrigir,
    parse_payload_qr,
    processar_imagem,
)

EXTENSOES = (".jpg", ".jpeg", ".png", ".webp")

def faixa_do_qr(caminho: Path) -> str | None:
    """Alinha a foto e lê a faixa do QR (para saber qual layout carregar)."""
    imagem = cv2.imread(str(caminho))
    if imagem is None:
        return None
    alinhada = detectar_e_corrigir(imagem)
    payload = decodificar_qr(alinhada)
    if not payload:
        return None
    return parse_payload_qr(payload)["faixa"].lower()

def main() -> int:
    ap = argparse.ArgumentParser(description="Processa fotos das folhas (Karate-Ashi)")
    ap.add_argument("--fotos", required=True, type=Path)
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--out", type=Path, default=Path("output/json"))
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    fotos = sorted(p for p in args.fotos.iterdir()
                   if p.suffix.lower() in EXTENSOES)
    if not fotos:
        print(f"[ERRO] nenhuma imagem em {args.fotos}")
        return 2

    ok, falhas = 0, 0
    for foto in fotos:
        try:
            faixa = faixa_do_qr(foto)
            if not faixa:
                print(f"[FALHA] {foto.name}: QR não lido — foto torta, "
                      f"sem foco ou sem QR no quadro")
                falhas += 1
                continue
            resultado = processar_imagem(foto, args.config, faixa)
            destino = args.out / f"{foto.stem}.json"
            destino.write_text(
                json.dumps(resultado, ensure_ascii=False, indent=2),
                encoding="utf-8")
            obs = resultado.get("observacao_montada", "")
            print(f"[OK] {foto.name} | aluno {resultado['aluno']['id']} | "
                  f"faixa {faixa} | obs: {obs or '-'}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[FALHA] {foto.name}: {exc}")
            falhas += 1

    print(f"\nProcessadas: {ok} | falhas: {falhas} | JSONs em {args.out}")
    return 0 if falhas == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())