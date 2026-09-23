"""validar_marcacoes.py — Cruzamento medição visual × leitura OMR.

Mede a escuridão APENAS do checkbox (primeiros ~4 mm da ROI)
e compara com as frequências que o OMR gravou no JSON da folha.

Status por checkbox:
  OK        = marcado visualmente E lido pelo OMR  → leitura correta
  FALSO NEG = marcado visualmente mas NÃO lido                  → OMR perdeu marcação
  FALSO POS = lido pelo OMR sem marcação visual                 → leitura fantasma
  vazio     = sem marcação e sem leitura                        → consistente

Uso:
  python tools/validar_marcacoes.py
  python tools/validar_marcacoes.py --pasta-scans output/scans/processados
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

A4_W_MM = 210.0
A4_H_MM = 297.0
EXT_IMAGEM = {".png", ".jpg", ".jpeg"}

# O checkbox fica na ponta esquerda da ROI — ~4 mm da largura de 38,5 mm
CHECKBOX_W_MM = 4.0
CHECKBOX_H_MM = 3.5


def _taxa_escuros_checkbox(imagem, box, dpi_x, dpi_y):
    """Mede a escuridão APENAS no checkbox (primeiros ~4 mm da ROI)."""
    x = int(box["x"] * dpi_x / 25.4)
    y = int(box["y"] * dpi_y / 25.4)
    w = int(box["w"] * dpi_x / 25.4)
    h = int(box["h"] * dpi_y / 25.4)

    # Isola só o checkbox: primeiros 4 mm da largura, altura ~3,5 mm
    cb_w = max(1, int(CHECKBOX_W_MM * dpi_x / 25.4))
    cb_h = max(1, int(CHECKBOX_H_MM * dpi_y / 25.4))

    # Recuo de 15% em cada lado para excluir a borda impressa da caixa
    recuo = max(1, int(cb_h * 0.15))

    regiao = imagem.crop((
        x + recuo,
        y + recuo,
        x + cb_w - recuo,
        y + cb_h - recuo,
    ))
    if regiao.width < 1 or regiao.height < 1:
        return None

    hist = regiao.histogram()
    total = sum(hist)
    if total == 0:
        return None
    escuros = sum(hist[:128])  # pixels com luminância < 128
    return escuros / total


def main() -> int:
    ap = argparse.ArgumentParser(description="Valida leitura OMR vs marcação real")
    ap.add_argument("--limiar", type=float, default=0.35,
                    help="escuridão mínima p/ considerar 'marcado' (default 0.35)")
    ap.add_argument("--pasta-scans", type=Path, default=Path("output/scans"))
    ap.add_argument("--pasta-json", type=Path, default=Path("output/teste_omr"))
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--faixa", default="branca")
    args = ap.parse_args()

    if not args.pasta_scans.is_dir():
        print(f"[ERRO] pasta de scans não existe: {args.pasta_scans}")
        return 2
    if not args.pasta_json.is_dir():
        print(f"[ERRO] pasta de JSONs não existe: {args.pasta_json}")
        return 2

    coords = json.loads(
        (args.config / "coordenadas" / f"{args.faixa}.json").read_text(encoding="utf-8")
    )

    # Coleta os checkboxes: quesito -> {criterio: box}
    checkboxes = {
        q: {c: b for c, b in bloco.items()
            if isinstance(b, dict) and {"x", "y", "w"} <= set(b)}
        for q, bloco in coords.items()
        if isinstance(bloco, dict) and q in ("kihon", "kata", "bunkai", "kumite")
    }

    imagens = sorted(p for p in args.pasta_scans.iterdir()
                     if p.suffix.casefold() in EXT_IMAGEM)

    if not imagens:
        print(f"[AVISO] nenhuma imagem em {args.pasta_scans}")
        return 3

    total_ok = total_fneg = total_fpos = 0
    for img_path in imagens:
        # JSON correspondente: mesmo stem (imagens diretas) ou _pN (PDF expandido)
        json_path = args.pasta_json / f"{img_path.stem}.json"
        if not json_path.exists():
            candidatos = sorted(args.pasta_json.glob(f"{img_path.stem}_p*.json"))
            if not candidatos:
                print(f"\n=== {img_path.name} === [SEM JSON — folha não processada]")
                continue
            json_path = candidatos[0]

        dados = json.loads(json_path.read_text(encoding="utf-8"))
        imagem = Image.open(img_path).convert("L")
        largura, altura = imagem.size
        dpi_x = largura / (A4_W_MM / 25.4)
        dpi_y = altura / (A4_H_MM / 25.4)

        print(f"\n=== {img_path.name} ({largura}x{altura}, ~{dpi_x:.0f} DPI) ===")
        print(f"    limiar de marcação: {args.limiar:.0%}")
        print(f"{'Quesito.critério':<42} {'%escuro':>8} {'visual':>8} "
              f"{'OMR':>5}  status")
        print("-" * 80)

        quesito_ok = quesito_fneg = quesito_fpos = 0
        for quesito in ("kihon", "kata", "bunkai", "kumite"):
            freq = dados.get("avaliacoes", {}).get(quesito, {}).get("frequencias", {})
            for criterio, box in checkboxes.get(quesito, {}).items():
                taxa = _taxa_escuros_checkbox(imagem, box, dpi_x, dpi_y)
                marcado = taxa is not None and taxa >= args.limiar
                lido = int(freq.get(criterio, 0)) > 0
                if marcado and lido:
                    status, quesito_ok = "OK", quesito_ok + 1
                elif marcado and not lido:
                    status, quesito_fneg = "FALSO NEG", quesito_fneg + 1
                elif not marcado and lido:
                    status, quesito_fpos = "FALSO POS", quesito_fpos + 1
                else:
                    status = "vazio"
                esc = f"{taxa:.1%}" if taxa is not None else "?"
                print(f"{quesito + '.' + criterio:<42} {esc:>8} "
                      f"{'SIM' if marcado else 'não':>8} "
                      f"{'sim' if lido else '—':>5}  {status}")

        total_ok += quesito_ok
        total_fneg += quesito_fneg
        total_fpos += quesito_fpos
        print(f"  -> folha: {quesito_ok} OK | {quesito_fneg} FALSO NEGATIVO "
              f"(marcou mas OMR não leu) | {quesito_fpos} FALSO POSITIVO "
              f"(leu sem marcação)")

    print("\n" + "=" * 80)
    print(f"TOTAL: {total_ok} OK | {total_fneg} falsos negativos "
          f"(marcações perdidas) | {total_fpos} falsos positivos (fantasmas)")
    if total_fneg == 0 and total_fpos == 0 and total_ok > 0:
        print("✅ Validação PERFEITA: toda marcação foi lida, nada foi inventado.")
    elif total_fneg == 0:
        print("⚠️ Nenhuma marcação perdida, mas há leituras sem marcação "
              "(ruído de borda — revisar limiar).")
    else:
        print("🔴 Há marcações que o OMR não leu — provável limiar alto ou "
              "coordenada levemente deslocada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())