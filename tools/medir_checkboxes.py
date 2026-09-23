"""medir_checkboxes.py — Mede a taxa de pixels escuros de cada checkbox OMR.

As coordenadas em config/coordenadas/branca.json estão em MILÍMETROS (mm).
A imagem digitalizada a 300 DPI tem ~2480x3505 px (A4). Este script converte
cada caixa de mm -> px usando a DPI real e mede a fração de pixels escuros.

Interpretação do "% Escuro":
  40%+  -> marcação forte; se o OMR não leu, é coordenada deslocada
  20-39%-> marca clara/leve; o limiar 0.40 está alto demais p/ essa caneta
  ~0%   -> ROI vazio; coordenada completamente fora da área da marca
  todos altos (inclusive vazios) -> borda impressa contando como marca

Uso: python tools/medir_checkboxes.py <imagem.png>
Ex.: python tools/medir_checkboxes.py output/_ingest/img..._p1.png
"""
import json
import sys
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# A4 em mm
A4_W_MM = 210.0
A4_H_MM = 297.0


def _taxa_escuros(imagem, box, dpi_x, dpi_y):
    """Fração de pixels escuros dentro da caixa, convertendo mm -> px."""
    x = int(box["x"] * dpi_x / 25.4)
    y = int(box["y"] * dpi_y / 25.4)
    w = int(box["w"] * dpi_x / 25.4)
    h = int(box["h"] * dpi_y / 25.4)
    if w < 1 or h < 1:
        return None
    regiao = imagem.crop((x, y, x + w, y + h))
    if regiao.width == 0 or regiao.height == 0:
        return None
    hist = regiao.histogram()
    total = sum(hist)
    if total == 0:
        return None
    escuros = sum(hist[:128])  # pixels com luminância < 128
    return escuros / total


def main():
    if len(sys.argv) < 2:
        print("Uso: python tools/medir_checkboxes.py <imagem.png>")
        return 1
    img_path = Path(sys.argv[1])
    if not img_path.exists():
        print(f"Arquivo não encontrado: {img_path}")
        return 1

    img = Image.open(img_path).convert("L")
    largura, altura = img.size
    dpi_x = largura / (A4_W_MM / 25.4)
    dpi_y = altura / (A4_H_MM / 25.4)
    print(f"Imagem: {img_path.name} ({largura}x{altura})")
    print(f"DPI estimado: {dpi_x:.1f} x {dpi_y:.1f}\n")

    coords = json.loads(
        (RAIZ / "config" / "coordenadas" / "branca.json")
        .read_text(encoding="utf-8")
    )

    print(f"{'Quesito':<20} {'Critério':<30} {'mm→px(x,y)':<18} {'%Escuro':>8}")
    print("=" * 78)
    for quesito in ["kihon", "kata", "bunkai", "kumite"]:
        bloco = coords.get(quesito, {})
        encontrou = False
        for criterio, box in bloco.items():
            if not isinstance(box, dict) or "x" not in box:
                continue
            encontrou = True
            taxa = _taxa_escuros(img, box, dpi_x, dpi_y)
            px_x = int(box["x"] * dpi_x / 25.4)
            px_y = int(box["y"] * dpi_y / 25.4)
            esc = f"{taxa:.1%}" if taxa is not None else "?"
            print(f"{quesito:<20} {criterio[:28]:<30} "
                  f"({px_x},{px_y}){'':<6} {esc:>8}")
        if not encontrou:
            print(f"{quesito:<20} [sem checkboxes]")

    # Observações estruturadas
    obs = {k: v for k, v in coords.items()
           if isinstance(v, dict) and "x" in v and k not in
           ("kihon", "kata", "bunkai", "kumite")}
    if obs:
        print("\n--- Observações estruturadas ---")
        for obs_id, box in sorted(obs.items()):
            taxa = _taxa_escuros(img, box, dpi_x, dpi_y)
            esc = f"{taxa:.1%}" if taxa is not None else "?"
            print(f"{obs_id:<15} {esc:>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())